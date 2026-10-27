#!/usr/bin/env python3
"""
Eclipse Native Z.ai / GLM Global Engine
========================================
Authentic, zero-legacy reverse-proxy driver for Z.ai (chat.z.ai) Global models.
Provides full international access to GLM-5.3, GLM-5.2, and GLM-Flash models.

Key Features:
- Pure global Z.ai routing (chat.z.ai) — accessible worldwide with 1-click Google/Email login
- Zero Chinese phone (+86) or WeChat requirement
- Automatic free guest session acquisition via /api/v1/auths/
- Multi-account pooling & failover from Eclipse SQLite vault
- Monotonic streaming with reasoning/thinking traces (reasoning_content)
"""

import asyncio
import base64
import json
import os
import random
import re
import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

import httpx

try:
    from eclipse import db
except Exception:
    db = None

ZAI_BASE_URL = os.getenv("ZAI_BASE_URL", "https://chat.z.ai")
ZAI_API_URL = f"{ZAI_BASE_URL}/api/v2/chat/completions"
ZAI_AUTHS_URL = f"{ZAI_BASE_URL}/api/v1/auths/"

# In-memory token cache: { "cache_key": { "token": str, "expires_at": float } }
_TOKEN_CACHE: Dict[str, Dict[str, Any]] = {}
_TOKEN_LOCK = asyncio.Lock()


def _inspect_jwt(jwt_str: str) -> Dict[str, Any]:
    """Inspect unverified JWT payload for type and expiration without cryptographic overhead."""
    if not jwt_str or not isinstance(jwt_str, str):
        return {}
    try:
        parts = jwt_str.strip().split(".")
        if len(parts) >= 2:
            padded = parts[1] + "=" * ((4 - len(parts[1]) % 4) % 4)
            payload_bytes = base64.urlsafe_b64decode(padded.encode("ascii"))
            return json.loads(payload_bytes.decode("utf-8"))
    except Exception:
        pass
    return {}


def _is_guest_jwt(jwt_str: str) -> bool:
    """Check if the given JWT token belongs to an anonymous guest session."""
    meta = _inspect_jwt(jwt_str)
    if not meta:
        return True
    email = str(meta.get("email", "")).lower()
    role = str(meta.get("role", "")).lower()
    return "guest" in email or role == "guest"


async def get_valid_access_token(raw_token: Optional[str] = None, force_refresh: bool = False) -> str:
    """
    Acquire valid access token for chat.z.ai:
    1. If user provided a token in vault, validate and return.
    2. Otherwise, request a free session token from chat.z.ai/api/v1/auths/.
    """
    raw_tok = (raw_token or "").strip()

    # Handle JSON string from localStorage dump or credential objects
    if raw_tok.startswith("{"):
        try:
            d = json.loads(raw_tok)
            if isinstance(d, dict):
                raw_tok = (
                    d.get("token")
                    or d.get("access_token")
                    or d.get("chatglm_refresh_token")
                    or d.get("refresh_token")
                    or raw_tok
                ).strip()
        except Exception:
            pass

    # Clean Bearer prefix or surrounding quotes
    raw_tok = re.sub(r"^Bearer\s+", "", raw_tok, flags=re.IGNORECASE).strip("\"' \t\r\n")
    cache_key = raw_tok if raw_tok else "__guest__"
    now = time.time()

    async with _TOKEN_LOCK:
        cached = _TOKEN_CACHE.get(cache_key)
        if not force_refresh and cached and cached.get("expires_at", 0) > now + 60:
            return cached["token"]

        # If user supplied a valid, unexpired token directly, use it!
        if cache_key != "__guest__":
            jwt_meta = _inspect_jwt(raw_tok)
            exp = jwt_meta.get("exp", 0)
            # If exp is present and still valid, or if token has no exp (session token), cache it
            expires_at = exp if exp > now else now + 86400 * 7
            _TOKEN_CACHE[cache_key] = {
                "token": raw_tok,
                "expires_at": expires_at,
            }
            return raw_tok

        # Anonymous Guest Session Generation from chat.z.ai
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Origin": ZAI_BASE_URL,
            "Referer": f"{ZAI_BASE_URL}/",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        }

        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            resp = await client.get(ZAI_AUTHS_URL, headers=headers)
            if resp.status_code != 200:
                raise RuntimeError(f"Z.ai Guest session failed (HTTP {resp.status_code}): {resp.text}")

            data = resp.json()
            acc_token = data.get("token")
            if not acc_token:
                raise RuntimeError(f"Z.ai Guest authentication returned no token: {data}")

            _TOKEN_CACHE["__guest__"] = {
                "token": acc_token,
                "expires_at": now + 3500,
            }
            return acc_token


def _resolve_model_name(requested_model: str) -> str:
    """Map user/OpenAI model name to the corresponding model identifier on chat.z.ai."""
    low = (requested_model or "").lower()
    if "5.2" in low:
        return "glm-5.2"
    elif "flash" in low or "preview" in low or "x-preview" in low:
        return "x-preview-l"
    return "glm-5.3"


async def stream_glm_chat(
    model: str,
    messages: List[Dict[str, Any]],
    accounts: Optional[List[Dict[str, Any]]] = None,
    raw_token: Optional[str] = None,
    stream: bool = True,
    **kwargs,
) -> AsyncIterator[Dict[str, Any]]:
    """
    Stream chat completion directly from Z.ai Global (chat.z.ai) with clean monotonic deltas,
    multi-account pool rotation, reasoning traces, and error auto-healing.
    Yields standard OpenAI-compatible chunks.
    """
    chat_id = f"chatcmpl-zai-{uuid.uuid4().hex[:12]}"
    created_ts = int(time.time())

    # 1. Model & Features Resolution
    lower_model = (model or "").lower()
    clean_model = _resolve_model_name(model)
    is_reasoning = (
        "zero" in lower_model
        or "think" in lower_model
        or "r1" in lower_model
        or kwargs.get("reasoning_effort") is not None
    )

    # 2. Format Messages
    formatted_messages = []
    for m in messages:
        role = str(m.get("role", "user")).lower().strip()
        content = m.get("content", "")
        if isinstance(content, list):
            text_parts = [
                item.get("text", "") if isinstance(item, dict) else str(item)
                for item in content
            ]
            content = " ".join(text_parts)
        formatted_messages.append({"role": role, "content": str(content)})

    request_body = {
        "model": clean_model,
        "messages": formatted_messages,
        "stream": True,
        "params": {},
        "features": {
            "enable_thinking": is_reasoning,
        },
    }

    # 3. Account Pool & Candidates Resolution
    candidate_tokens: List[str] = []
    if raw_token and str(raw_token).strip():
        candidate_tokens.append(str(raw_token).strip())

    if not accounts and db is not None:
        try:
            accounts = db.get_accounts("glm")
        except Exception:
            accounts = []

    for acc in (accounts or []):
        if acc.get("status") == "active":
            tok = acc.get("token") or acc.get("refresh_token")
            if tok and str(tok).strip() and str(tok).strip() not in candidate_tokens:
                candidate_tokens.append(str(tok).strip())

    if not candidate_tokens:
        candidate_tokens = ["__guest__"]

    num_candidates = len(candidate_tokens)
    has_authenticated_accounts = any(
        t != "__guest__" and not _is_guest_jwt(t)
        for t in candidate_tokens
    )
    MAX_RETRIES = max(4, num_candidates * 2)
    acc_idx = 0
    started_streaming = False

    for attempt in range(MAX_RETRIES):
        current_token = candidate_tokens[acc_idx % num_candidates]
        force_fresh_token = (attempt > 0)
        try:
            access_token = await get_valid_access_token(current_token, force_refresh=force_fresh_token)
        except Exception as e:
            if attempt == MAX_RETRIES - 1:
                raise RuntimeError(f"Z.ai auth error: {e}")
            acc_idx += 1
            await asyncio.sleep(0.5)
            continue

        stream_headers = {
            "Accept": "text/event-stream",
            "Accept-Language": "en-US",
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Origin": ZAI_BASE_URL,
            "Referer": f"{ZAI_BASE_URL}/",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "X-FE-Version": "prod-fe-1.1.118",
        }

        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                async with client.stream("POST", ZAI_API_URL, headers=stream_headers, json=request_body) as response:
                    if response.status_code in (401, 403):
                        err_bytes = await response.aread()
                        err_text = err_bytes.decode("utf-8", errors="ignore")
                        if has_authenticated_accounts and attempt < MAX_RETRIES - 1:
                            acc_idx += 1
                            continue
                        raise RuntimeError(f"Z.ai authorization failed (HTTP {response.status_code}): {err_text[:200]}")

                    if response.status_code == 429:
                        if num_candidates > 1 and attempt < MAX_RETRIES - 1:
                            acc_idx += 1
                            continue
                        if attempt < MAX_RETRIES - 1:
                            await asyncio.sleep(1.0 * (attempt + 1))
                            continue
                        raise RuntimeError("Z.ai upstream rate limit exceeded (HTTP 429)")

                    if response.status_code != 200:
                        err_msg = await response.aread()
                        raise RuntimeError(f"Z.ai upstream HTTP {response.status_code}: {err_msg.decode('utf-8', errors='ignore')[:200]}")

                    async for line in response.aiter_lines():
                        trimmed = line.strip()
                        if not trimmed.startswith("data:"):
                            continue
                        payload = trimmed[5:].strip()
                        if payload == "[DONE]":
                            break

                        try:
                            data = json.loads(payload)
                        except Exception:
                            continue

                        # Check for inline error objects
                        err_obj = None
                        if isinstance(data, dict):
                            if data.get("error"):
                                err_obj = data["error"]
                            elif isinstance(data.get("data"), dict) and data["data"].get("error"):
                                err_obj = data["data"]["error"]
                            elif isinstance(data.get("data"), dict) and isinstance(data["data"].get("data"), dict) and data["data"]["data"].get("error"):
                                err_obj = data["data"]["data"]["error"]

                        if err_obj:
                            err_str = json.dumps(err_obj).lower() if isinstance(err_obj, dict) else str(err_obj).lower()
                            err_detail = (
                                err_obj.get("detail")
                                or err_obj.get("message")
                                or err_obj.get("code")
                                or str(err_obj)
                            ) if isinstance(err_obj, dict) else str(err_obj)

                            # If we have multiple accounts, rotate to the next candidate
                            if num_candidates > 1 and attempt < MAX_RETRIES - 1:
                                acc_idx += 1
                                break

                            # Clean exception to trigger upstream router Auto-Healer without leaking error text to user
                            raise RuntimeError(f"Z.ai upstream error: {err_detail}")

                        # Emit first role chunk upon receiving initial valid frame
                        if not started_streaming:
                            started_streaming = True
                            yield {
                                "id": chat_id,
                                "object": "chat.completion.chunk",
                                "created": created_ts,
                                "model": model,
                                "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
                            }

                        # Standard OpenAI chunks format
                        choices = data.get("choices")
                        if choices and isinstance(choices, list) and choices[0].get("delta"):
                            delta = choices[0]["delta"]
                            yield {
                                "id": chat_id,
                                "object": "chat.completion.chunk",
                                "created": created_ts,
                                "model": model,
                                "choices": [{"index": 0, "delta": delta, "finish_reason": choices[0].get("finish_reason")}],
                            }
                            continue

                        # Z.ai Chat Completion Format
                        if data.get("type") == "chat:completion":
                            inner = data.get("data")
                            if isinstance(inner, dict):
                                delta_text = inner.get("delta_content")
                                phase = inner.get("phase", "answer")
                                if not delta_text and "content" in inner and isinstance(inner["content"], str):
                                    delta_text = inner["content"]

                                if delta_text:
                                    if phase == "thinking":
                                        yield {
                                            "id": chat_id,
                                            "object": "chat.completion.chunk",
                                            "created": created_ts,
                                            "model": model,
                                            "choices": [{
                                                "index": 0,
                                                "delta": {"reasoning_content": delta_text},
                                                "finish_reason": None,
                                            }],
                                        }
                                    else:
                                        yield {
                                            "id": chat_id,
                                            "object": "chat.completion.chunk",
                                            "created": created_ts,
                                            "model": model,
                                            "choices": [{
                                                "index": 0,
                                                "delta": {"content": delta_text},
                                                "finish_reason": None,
                                            }],
                                        }

            if started_streaming:
                break

        except Exception as exc:
            if attempt < MAX_RETRIES - 1:
                acc_idx += 1
                await asyncio.sleep(0.6 * (attempt + 1))
                continue
            yield {
                "id": chat_id,
                "object": "chat.completion.chunk",
                "created": created_ts,
                "model": model,
                "choices": [{
                    "index": 0,
                    "delta": {"content": f"\n\n[Z.ai Stream Connection Error: {str(exc)}]"},
                    "finish_reason": "error",
                }],
            }
            return

    # Final stop or error chunk
    if not started_streaming:
        yield {
            "id": chat_id,
            "object": "chat.completion.chunk",
            "created": created_ts,
            "model": model,
            "choices": [{
                "index": 0,
                "delta": {"content": "⚠️ Eclipse Notice: Upstream session returned no content. Please refresh your Z.ai or Gemini account in Eclipse Dashboard."},
                "finish_reason": "error",
            }],
        }
    else:
        yield {
            "id": chat_id,
            "object": "chat.completion.chunk",
            "created": created_ts,
            "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
