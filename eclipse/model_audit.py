"""Diagnostics for verifying which Gemini Web model bucket actually served a request.

Google's batchexecute format is private and may change. This module deliberately reports
"unverified" when response history or current account model metadata is unavailable; it
never treats the requested OpenAI-compatible model label as proof of model identity.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

GEMINI_WEB = "https://gemini.google.com"
BATCH_EXEC = f"{GEMINI_WEB}/_/BardChatUi/data/batchexecute"
USER_STATUS_RPC = "otAQ7b"
READ_CHAT_RPC = "hNvQHb"
HEX_MODEL_ID = re.compile(r"^[0-9a-f]{16}$", re.IGNORECASE)
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
)


def extract_gemini_access_token(html: str) -> str:
    """Extract Gemini Web's current XSRF token, including its alternate field name."""
    page = html or ""
    for key in ("SNlM0e", "thykhd"):
        match = re.search(rf'"{key}"\s*:\s*"([^"]+)"', page)
        if match:
            return match.group(1)
    return ""


def _utf16_frame_end(text: str, start: int, length: int) -> Optional[int]:
    """Return the end offset after length JavaScript UTF-16 code units."""
    units = 0
    pos = start
    while pos < len(text) and units < length:
        units += len(text[pos].encode("utf-16-le")) // 2
        pos += 1
    return pos if units == length else None


def parse_batchexecute_frames(response_text: str) -> List[Any]:
    """Parse Google's length-prefixed JSON frames, with a raw-JSON fallback for fixtures."""
    text = (response_text or "").lstrip("\ufeff \t\r\n")
    if text.startswith(")]}'"):
        newline = text.find("\n")
        text = text[newline + 1:] if newline >= 0 else ""

    frames: List[Any] = []
    pos = 0
    while pos < len(text):
        while pos < len(text) and text[pos] in "\r\n \t":
            pos += 1
        if pos >= len(text):
            break

        line_end = text.find("\n", pos)
        if line_end >= 0:
            marker = text[pos:line_end].strip()
            if marker.isdigit():
                payload_start = line_end + 1
                payload_end = _utf16_frame_end(text, payload_start, int(marker))
                if payload_end is not None:
                    frame_text = text[payload_start:payload_end]
                    try:
                        frames.append(json.loads(frame_text))
                    except (ValueError, TypeError):
                        pass
                    pos = payload_end
                    continue

        # Tolerate direct JSON bodies or newline-separated JSON frames for diagnostics.
        candidate = text[pos:].strip()
        try:
            frames.append(json.loads(candidate))
            break
        except (ValueError, TypeError):
            if line_end < 0:
                break
            pos = line_end + 1

    return frames


def extract_rpc_payloads(response_text: str, rpc_id: str) -> List[Any]:
    """Find batchexecute RPC parts and decode the JSON payload stored at index 2."""
    found: List[Any] = []

    def visit(node: Any) -> None:
        if not isinstance(node, list):
            return
        if len(node) > 2 and node[1] == rpc_id and isinstance(node[2], str):
            try:
                found.append(json.loads(node[2]))
            except (ValueError, TypeError):
                pass
            return
        for child in node:
            visit(child)

    for frame in parse_batchexecute_frames(response_text):
        visit(frame)
    return found


def _at(value: Any, path: Sequence[int], default: Any = None) -> Any:
    current = value
    for index in path:
        if not isinstance(current, list) or index < 0 or index >= len(current):
            return default
        current = current[index]
    return default if current is None else current


def _hex_ids(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        if HEX_MODEL_ID.fullmatch(value):
            yield value.lower()
    elif isinstance(value, list):
        for item in value:
            yield from _hex_ids(item)


def build_variant_owners(user_status_payload: Any) -> Dict[str, List[Dict[str, str]]]:
    """Map observed 16-hex variant IDs to current account model rows that list them."""
    rows = _at(user_status_payload, [15], [])
    owners: Dict[str, List[Dict[str, str]]] = {}
    if not isinstance(rows, list):
        return owners

    for row in rows:
        if not isinstance(row, list) or not row:
            continue
        model_id = str(_at(row, [0], "") or "")
        name = str(
            _at(row, [11], "")
            or _at(row, [19], "")
            or _at(row, [1], "")
            or model_id
        ).strip()
        if not name:
            continue
        owner = {"model_id": model_id.lower(), "name": name}
        variants = set(_hex_ids(_at(row, [6], [])))
        if HEX_MODEL_ID.fullmatch(model_id):
            variants.add(model_id.lower())
        for variant in variants:
            matches = owners.setdefault(variant, [])
            if owner not in matches:
                matches.append(owner)
    return owners


def _has_thoughts(turn: Any) -> bool:
    """Use private candidate metadata, not model prose, to disambiguate shared buckets."""
    thoughts = _at(turn, [3, 0, 0, 37, 0, 0], "")
    if isinstance(thoughts, str):
        return bool(thoughts.strip())
    if isinstance(thoughts, list):
        return any(isinstance(item, str) and item.strip() for item in thoughts)
    return bool(thoughts)


def observed_turn(turns: Any, response_id: Optional[str]) -> Tuple[Optional[Any], str]:
    """Choose the turn generated by this request; avoid silently examining an older turn."""
    if not isinstance(turns, list) or not turns:
        return None, "no_history_turns"
    if response_id:
        for turn in turns:
            rid = _at(turn, [0, 1])
            if rid and str(rid) == str(response_id):
                return turn, "response_id_match"
        return None, "response_id_not_found"
    return turns[0], "latest_turn_no_response_id"


def classify_variant(variant_id: str, turn: Any, owners: Dict[str, List[Dict[str, str]]]) -> Dict[str, Any]:
    candidates = [dict(item) for item in owners.get((variant_id or "").lower(), [])]
    has_thoughts = _has_thoughts(turn)

    if len(candidates) > 1:
        if has_thoughts:
            filtered = [x for x in candidates if re.search(r"think|reason|pro", x["name"], re.I)]
        else:
            filtered = [x for x in candidates if not re.search(r"think|reason", x["name"], re.I)]
        if filtered:
            candidates = filtered

    names = sorted({item["name"] for item in candidates})
    ids = sorted({item["model_id"] for item in candidates if item["model_id"]})
    return {
        "variant_id": variant_id,
        "model_names": names,
        "model_ids": ids,
        "resolved_name": names[0] if len(names) == 1 else None,
        "ambiguous": len(names) > 1,
        "has_thoughts_metadata": has_thoughts,
    }


def compare_selection(
    selection_hash: Optional[str],
    observed_variant_id: Optional[str],
    expected_owners: List[Dict[str, str]],
    observed: Dict[str, Any],
    selection_header_sent: bool,
) -> str:
    """Compare actual response evidence to the requested selection without overstating proof."""
    if not selection_header_sent or not selection_hash:
        return "unverified"
    if observed_variant_id and selection_hash.lower() == observed_variant_id.lower():
        return "variant_id_match"
    expected_names = {item["name"] for item in expected_owners}
    observed_names = set(observed.get("model_names") or [])
    if len(expected_names) == 1 and len(observed_names) == 1:
        return "bucket_match" if expected_names == observed_names else "bucket_mismatch"
    if len(expected_names) == 1 and len(observed_names) > 1:
        return "ambiguous"
    return "unverified"


def _sapisid_authorization(cookie: str) -> Optional[str]:
    match = re.search(r"(?:SAPISID|__Secure-1PAPISID|__Secure-3PAPISID)=([^;]+)", cookie or "")
    if not match:
        return None
    timestamp = int(time.time())
    digest = hashlib.sha1(
        f"{timestamp} {match.group(1).strip()} {GEMINI_WEB}".encode("utf-8")
    ).hexdigest()
    return f"SAPISIDHASH {timestamp}_{digest}"


async def _post_rpc(
    client: httpx.AsyncClient,
    rpc_id: str,
    payload: Any,
    *,
    cookie: str,
    access_token: str,
    build_label: str,
    session_id: str,
    header_session_id: str,
    request_id: int,
) -> Tuple[Optional[Any], str]:
    import httpx

    headers = {
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        "Origin": GEMINI_WEB,
        "Referer": f"{GEMINI_WEB}/app",
        "X-Same-Domain": "1",
        "User-Agent": USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9",
        # Mirrors the default batchexecute header used by current reverse-engineered clients.
        "x-goog-ext-73010989-jspb": "[0]",
    }
    model_header = [1, None, None, None, None, None, None, None, [4, 5, 6, 8], None, None, None, None, None, None, None]
    if header_session_id:
        model_header.append(header_session_id)
    headers["x-goog-ext-525001261-jspb"] = json.dumps(model_header, separators=(",", ":"))
    if cookie:
        headers["Cookie"] = cookie
    authorization = _sapisid_authorization(cookie)
    if authorization:
        headers["Authorization"] = authorization

    params = {
        "rpcids": rpc_id,
        "bl": build_label,
        "hl": "en",
        "_reqid": str(request_id),
        "rt": "c",
        "source-path": "/app",
    }
    if session_id:
        params["f.sid"] = session_id
    body = {
        "at": access_token or "",
        "f.req": json.dumps([[[rpc_id, json.dumps(payload, separators=(",", ":")), None, "generic"]]]),
    }
    try:
        response = await client.post(BATCH_EXEC, params=params, data=body, headers=headers)
    except httpx.HTTPError as exc:
        return None, f"{rpc_id} request failed ({type(exc).__name__})"
    if response.status_code >= 400:
        return None, f"{rpc_id} returned HTTP {response.status_code}"
    values = extract_rpc_payloads(response.text, rpc_id)
    if not values:
        return None, f"{rpc_id} payload was not found in response"
    return values[0], ""


async def enrich_model_diagnostics(
    diagnostics: Dict[str, Any],
    *,
    cookie: str,
    access_token: str,
    build_label: str,
    session_id: str,
    selection_hash: Optional[str],
) -> None:
    """Read current account model metadata and this response's saved turn, without leaking secrets."""
    cid = diagnostics.get("conversation_id")
    response_id = diagnostics.get("response_id")
    diagnostics.setdefault("notes", [])
    diagnostics["cookie_bundle_supplied"] = bool(cookie)
    diagnostics["access_token_available"] = bool(access_token)
    diagnostics["session_id_available"] = bool(session_id)
    diagnostics["secure_psid_present"] = "__Secure-1PSID=" in (cookie or "")
    diagnostics["session_cookie_cc_present"] = any(
        marker in (cookie or "")
        for marker in ("__Secure-1PSIDCC=", "SIDCC=")
    )

    if not cid:
        diagnostics["identity_verification"] = "unverified"
        diagnostics["notes"].append("Gemini did not return a conversation ID; response history could not be checked.")
        return
    if not cookie:
        diagnostics["identity_verification"] = "unverified"
        diagnostics["notes"].append(
            "No Gemini cookie bundle reached the audit. Check whether the running engine loaded the stacked account."
        )
        return
    if not access_token:
        diagnostics["identity_verification"] = "unverified"
        diagnostics["notes"].append(
            "The session bootstrap did not provide either SNlM0e or thykhd. Gemini Web can still return a one-shot "
            "StreamGenerate answer, but this audit uses batchexecute history/model lookups that need that token. "
            "This does not prove the stacked cookie was ignored; it means the actual serving bucket cannot be verified by this path."
        )
        return

    header_session_id = str(uuid.uuid4()).upper()
    try:
        import httpx

        async with httpx.AsyncClient(timeout=httpx.Timeout(12.0, connect=8.0), follow_redirects=True) as client:
            status_payload, status_error = await _post_rpc(
                client, USER_STATUS_RPC, [], cookie=cookie, access_token=access_token,
                build_label=build_label, session_id=session_id, header_session_id=header_session_id, request_id=int(time.time() * 1000) % 900000,
            )
            history_payload, history_error = await _post_rpc(
                client, READ_CHAT_RPC, [cid, 10, None, 1, [1], [4], None, 1],
                cookie=cookie, access_token=access_token, build_label=build_label,
                session_id=session_id, header_session_id=header_session_id, request_id=(int(time.time() * 1000) + 1) % 900000,
            )
    except Exception as exc:  # Keep optional diagnostics from breaking a successful completion.
        diagnostics["identity_verification"] = "unverified"
        diagnostics["notes"].append(f"Model identity lookup failed ({type(exc).__name__}).")
        return

    owners = build_variant_owners(status_payload) if status_payload is not None else {}
    expected_owners = owners.get((selection_hash or "").lower(), []) if selection_hash else []
    diagnostics["expected_model_names"] = sorted({item["name"] for item in expected_owners})

    if status_error:
        diagnostics["notes"].append(status_error)
    if history_error or history_payload is None:
        diagnostics["identity_verification"] = "unverified"
        if history_error:
            diagnostics["notes"].append(history_error)
        return

    turns = _at(history_payload, [0], [])
    turn, turn_match = observed_turn(turns, str(response_id) if response_id else None)
    diagnostics["history_turn_match"] = turn_match
    if turn is None:
        diagnostics["identity_verification"] = "unverified"
        diagnostics["notes"].append("Could not identify the exact saved turn for this response.")
        return

    variant_id = _at(turn, [2, 4])
    if not isinstance(variant_id, str) or not HEX_MODEL_ID.fullmatch(variant_id):
        diagnostics["identity_verification"] = "unverified"
        diagnostics["notes"].append("The saved turn did not contain a recognized 16-character model variant ID.")
        return

    observed = classify_variant(variant_id, turn, owners)
    diagnostics["observed_variant_id"] = variant_id.lower()
    diagnostics["observed_model_names"] = observed["model_names"]
    diagnostics["observed_model_ids"] = observed["model_ids"]
    diagnostics["observed_bucket_ambiguous"] = observed["ambiguous"]
    diagnostics["has_thoughts_metadata"] = observed["has_thoughts_metadata"]
    diagnostics["bucket_comparison"] = compare_selection(
        selection_hash,
        variant_id,
        expected_owners,
        observed,
        bool(diagnostics.get("selection_header_sent")),
    )
    diagnostics["identity_verification"] = diagnostics["bucket_comparison"]

    if status_payload is None:
        diagnostics["notes"].append("Current account model metadata was unavailable; bucket labels may be incomplete.")
    if not expected_owners and selection_hash:
        diagnostics["notes"].append("The request's selection hash was not present in the current account model catalogue.")
    diagnostics["notes"].append(
        "Evidence is the private Gemini Web conversation-history model variant, not an official model-version attestation."
    )
