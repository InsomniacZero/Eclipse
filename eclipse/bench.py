#!/usr/bin/env python3
"""
Test bench: scripted chats sent through the gateway the way JanitorAI would send them (`model@preset`, streaming),
then checked against the request log, so nobody has to roleplay to find out whether search, the search focus and
the clean-up of the reply work.

A scenario is a short chat plus what should be true afterwards. The checks read the request log entry the gateway
wrote for that chat (did the model search, what did it ask) and the reply the client got. Nothing here judges
quality with another model: every check is a plain, readable rule.

Real requests go to the real provider, so a run uses the provider's quota. Nothing is simulated.
"""

import asyncio
import json
import re
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional

DEFAULT_CARD = (
    "You are Mira, a cheerful barista in a small seaside café, playing a casual roleplay with the user. "
    "Stay in character, write short replies and use *actions* in asterisks."
)
MAX_SCENARIOS = 60
MAX_SECONDS_DEFAULT = 120
PAUSE_SECONDS = 1.5   # between chats, so a provider is not asked in a burst
SEARCH_EXPECTATIONS = ("yes", "no", "any")
LEAK_PATTERNS = [
    ("a tool tag", re.compile(r"</?(tool_call|tool_result|tools_info)", re.I)),
    ("a source marker like [1]", re.compile(r"\[\d{1,2}\]")),
    ("a web address", re.compile(r"https?://", re.I)),
    ("an internal event", re.compile(r"eclipse_event|eclipse_steps")),
]

# Expectations marked focus_only assume the built-in search focus (pop culture, songs, historical accuracy).
BUILTIN: List[Dict[str, Any]] = [
    {"id": "song-artist", "name": "Song: who sings it, and when", "focus_only": False,
     "messages": [{"role": "user", "content": "*hums along to the radio* Mira, this song is stuck in my head, 'Bad Guy'. Who sings it, and what year did it come out?"}],
     "expect": {"search": "yes", "query_any": ["bad guy", "billie"], "reply_any": ["Billie", "Eilish"]}},
    {"id": "anime-fact", "name": "Anime: air date and studio", "focus_only": False,
     "messages": [{"role": "user", "content": "Do you know when the anime 'Frieren: Beyond Journey's End' started airing, and which studio made it?"}],
     "expect": {"search": "yes", "query_any": ["frieren"], "reply_any": ["2023", "Madhouse"]}},
    {"id": "history-period", "name": "History: London in 1851", "focus_only": False,
     "messages": [{"role": "user", "content": "I'm writing a scene set in London during the Great Exhibition of 1851. What was the Crystal Palace, and what would visitors actually have been wearing?"}],
     "expect": {"search": "yes", "query_any": ["1851", "crystal palace", "great exhibition", "victorian"], "reply_any": ["Crystal Palace"]}},
    {"id": "film-recent", "name": "Pop culture: a recent film", "focus_only": False,
     "messages": [{"role": "user", "content": "Which film won the Oscar for Best Picture most recently, and who directed it?"}],
     "expect": {"search": "yes", "query_any": ["oscar", "best picture", "academy"]}},
    {"id": "chitchat", "name": "Plain chit-chat (must not search)", "focus_only": False,
     "messages": [{"role": "user", "content": "*waves* Morning, Mira! Can I get my usual?"}],
     "expect": {"search": "no"}},
    {"id": "about-character", "name": "About the character (must not search)", "focus_only": False,
     "messages": [{"role": "user", "content": "Tell me about yourself, Mira. Where did you grow up?"}],
     "expect": {"search": "no"}},
    {"id": "scene-continues", "name": "Scene continues (must not search)", "focus_only": False,
     "messages": [{"role": "user", "content": "Hi Mira!"}, {"role": "assistant", "content": "*looks up from the espresso machine* Oh, hey! The usual?"},
                  {"role": "user", "content": "*sips the coffee and smiles* And then?"}],
     "expect": {"search": "no"}},
    {"id": "off-focus-code", "name": "Off-focus: a software version", "focus_only": True,
     "messages": [{"role": "user", "content": "Random question, Mira: what's the latest stable version of Python right now?"}],
     "expect": {"search": "no"}},
    {"id": "off-focus-weather", "name": "Off-focus: the weather", "focus_only": True,
     "messages": [{"role": "user", "content": "Do you know what the weather is like in Tokyo today?"}],
     "expect": {"search": "no"}},
]


class BenchError(ValueError):
    """A scenario or run request that cannot be used."""


def _list_of_text(value: Any, field: str, limit: int = 20) -> List[str]:
    if value in (None, ""):
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise BenchError(f"{field} must be a list of words")
    out = [v.strip() for v in value if v.strip()]
    if len(out) > limit:
        raise BenchError(f"{field} can have at most {limit} entries")
    return [v[:200] for v in out]


def clean_scenario(data: Any, *, builtin: bool = False) -> Dict[str, Any]:
    if not isinstance(data, dict):
        raise BenchError("A scenario must be an object")
    name = data.get("name")
    if not isinstance(name, str) or not name.strip() or len(name) > 120:
        raise BenchError("name must be 1 to 120 characters")
    messages = data.get("messages")
    if not isinstance(messages, list) or not 1 <= len(messages) <= 40:
        raise BenchError("messages must be a list of 1 to 40 messages")
    cleaned = []
    for m in messages:
        if not isinstance(m, dict) or m.get("role") not in ("system", "user", "assistant") or not isinstance(m.get("content"), str):
            raise BenchError("every message needs a role (system, user or assistant) and text")
        if len(m["content"]) > 20_000:
            raise BenchError("a message is longer than 20,000 characters")
        cleaned.append({"role": m["role"], "content": m["content"]})
    if cleaned[-1]["role"] != "user":
        raise BenchError("the last message must be from the user")
    expect = data.get("expect") or {}
    if not isinstance(expect, dict):
        raise BenchError("expect must be an object")
    search = expect.get("search", "any")
    if search not in SEARCH_EXPECTATIONS:
        raise BenchError("expect.search must be yes, no or any")
    seconds = expect.get("max_seconds", MAX_SECONDS_DEFAULT)
    if isinstance(seconds, bool) or not isinstance(seconds, int) or not 5 <= seconds <= 600:
        raise BenchError("expect.max_seconds must be a whole number from 5 to 600")
    out = {
        "name": name.strip(),
        "messages": cleaned,
        "focus_only": bool(data.get("focus_only", False)),
        "expect": {
            "search": search,
            "query_any": _list_of_text(expect.get("query_any"), "expect.query_any"),
            "reply_any": _list_of_text(expect.get("reply_any"), "expect.reply_any"),
            "reply_none": _list_of_text(expect.get("reply_none"), "expect.reply_none"),
            "max_seconds": seconds,
        },
    }
    if builtin:
        out["id"] = data["id"]
    return out


def builtin_scenarios() -> List[Dict[str, Any]]:
    return [{**clean_scenario(s, builtin=True), "builtin": True} for s in BUILTIN]


def with_card(scenario: Dict[str, Any], card: str) -> List[Dict[str, Any]]:
    """The messages JanitorAI would send: the character card first (unless the scenario brings its own), then the chat."""
    msgs = [dict(m) for m in scenario["messages"]]
    if msgs[0]["role"] != "system":
        msgs.insert(0, {"role": "system", "content": card or DEFAULT_CARD})
    return msgs


# ---------------------------------------------------------------- checks

def _check(name: str, ok: bool, detail: str = "") -> Dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def evaluate(scenario: Dict[str, Any], sent: Dict[str, Any], entry: Optional[Dict[str, Any]], *, tools_on: bool, focus_builtin: bool) -> Dict[str, Any]:
    """Judge one finished chat. `sent` is what the client side saw; `entry` is the request log entry (or None)."""
    expect = scenario["expect"]
    checks: List[Dict[str, Any]] = []
    notes: List[str] = []
    reply = sent.get("content") or ""

    if sent.get("error"):
        checks.append(_check("The request worked", False, sent["error"]))
        return {"status": "error", "checks": checks, "notes": notes}
    checks.append(_check("The request worked", True, f"HTTP {sent.get('status', 200)}"))
    checks.append(_check("There is a reply", bool(reply.strip()), f"{len(reply)} characters"))
    leaks = [label for label, pat in LEAK_PATTERNS if pat.search(reply)]
    checks.append(_check("Nothing internal leaks into the reply", not leaks, ("found " + ", ".join(leaks)) if leaks else "clean"))
    seconds = (sent.get("ms") or 0) / 1000
    checks.append(_check(f"Done within {expect['max_seconds']} seconds", seconds <= expect["max_seconds"], f"{seconds:.1f} s"))

    trace = (entry or {}).get("trace") or {}
    searches = trace.get("searches") or []
    queries = [s.get("what", "") for s in searches]
    searched = bool(searches)
    wanted = expect["search"]
    if scenario.get("focus_only") and not (tools_on and focus_builtin):
        wanted = "any"
        notes.append("Search expectation skipped: it assumes the built-in search focus, which this preset does not use.")
    if not tools_on:
        wanted = "any"
        notes.append("This preset has no tools, so whether the model searched is not checked.")
    if entry is None:
        checks.append(_check("The gateway logged the request", False, "no request-log entry was found (is the log switched off?)"))
    else:
        if wanted == "yes":
            ok = searched and any(s.get("ok") for s in searches)
            checks.append(_check("The model searched, and the search worked", ok,
                                 "searched: " + "; ".join(queries) if searched else "it answered without searching"))
        elif wanted == "no":
            checks.append(_check("The model did not search", not searched, ("it searched: " + "; ".join(queries)) if searched else "no search"))
        if expect["query_any"] and wanted == "yes":
            hit = [q for q in queries if any(w.lower() in q.lower() for w in expect["query_any"])]
            checks.append(_check("The search asked about the right thing", bool(hit),
                                 f"queries: {'; '.join(queries) or 'none'} (wanted one of: {', '.join(expect['query_any'])})"))
    if expect["reply_any"]:
        hit = [w for w in expect["reply_any"] if w.lower() in reply.lower()]
        checks.append(_check("The reply has the facts", bool(hit), ("found " + ", ".join(hit)) if hit else f"none of: {', '.join(expect['reply_any'])}"))
    if expect["reply_none"]:
        bad = [w for w in expect["reply_none"] if w.lower() in reply.lower()]
        checks.append(_check("The reply avoids forbidden words", not bad, ("found " + ", ".join(bad)) if bad else "clean"))
    return {"status": "pass" if all(c["ok"] for c in checks) else "fail", "checks": checks, "notes": notes}


# ---------------------------------------------------------------- running

Sender = Callable[..., Awaitable[Dict[str, Any]]]


async def http_sender(base_url: str, model_ref: str, messages: List[Dict[str, Any]], tag: str, timeout: float) -> Dict[str, Any]:
    """Send one streaming chat to the gateway like JanitorAI does and collect what a client would see."""
    import httpx
    started = time.monotonic()
    content, reasoning, status, error = [], [], 0, ""
    body = {"model": model_ref, "messages": messages, "stream": True}
    headers = {"Origin": "https://janitorai.com", "X-Eclipse-Tag": tag, "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", f"{base_url}/v1/chat/completions", json=body, headers=headers) as res:
                status = res.status_code
                if status >= 400:
                    raw = (await res.aread()).decode("utf-8", "replace")
                    try:
                        err = json.loads(raw).get("error", raw)
                        error = err.get("message", raw) if isinstance(err, dict) else str(err)
                    except ValueError:
                        error = raw[:500]
                else:
                    async for line in res.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data = line[6:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                        except ValueError:
                            continue
                        if chunk.get("error"):
                            error = str(chunk["error"])
                            continue
                        choice = (chunk.get("choices") or [{}])[0]
                        delta = choice.get("delta") or {}
                        if choice.get("finish_reason") == "error":
                            error = str(delta.get("content") or "error")
                        elif isinstance(delta.get("content"), str):
                            content.append(delta["content"])
                        if isinstance(delta.get("reasoning_content"), str):
                            reasoning.append(delta["reasoning_content"])
    except Exception as e:  # connection refused, timeout, and so on: report it, never crash the run
        error = error or f"{e.__class__.__name__}: {e}"
    return {"status": status, "content": "".join(content), "reasoning": "".join(reasoning), "error": error,
            "ms": int((time.monotonic() - started) * 1000)}


async def run_scenarios(*, scenarios: List[Dict[str, Any]], model: str, preset: Dict[str, Any], card: str, run_tag: str,
                        send: Sender, find_log: Callable[[str], Optional[Dict[str, Any]]],
                        on_result: Callable[[Dict[str, Any]], None], cancelled: Callable[[], bool],
                        pause: Optional[float] = None, log_wait: float = 4.0) -> None:
    pause = PAUSE_SECONDS if pause is None else pause
    tools_on = bool(preset.get("tools"))
    focus_builtin = bool(preset.get("tool_guidance_on", True)) and not (preset.get("tool_guidance") or "").strip()
    model_ref = f"{model}@{preset['name']}"
    for i, scenario in enumerate(scenarios):
        if cancelled():
            return
        tag = f"{run_tag}-{i + 1}"
        sent = await send(model_ref, with_card(scenario, card), tag)
        entry = None
        deadline = time.monotonic() + (1.0 if sent.get("error") else log_wait)
        while time.monotonic() < deadline:   # the gateway saves the log just after the stream ends
            entry = find_log(tag)
            if entry:
                break
            await asyncio.sleep(0.25)
        verdict = evaluate(scenario, sent, entry, tools_on=tools_on, focus_builtin=focus_builtin)
        on_result({
            "id": scenario.get("id") or f"custom-{scenario.get('db_id', i + 1)}", "name": scenario["name"], **verdict,
            "ms": sent.get("ms"), "log_id": (entry or {}).get("id"),
            "queries": [s.get("what", "") for s in ((entry or {}).get("trace") or {}).get("searches", [])],
            "reply": (sent.get("content") or "")[:4000], "thinking_chars": len(sent.get("reasoning") or ""),
            "error": sent.get("error") or "",
        })
        if i + 1 < len(scenarios) and not cancelled():
            await asyncio.sleep(pause)


def summarize(results: List[Dict[str, Any]], total: int) -> Dict[str, int]:
    counts = {"pass": 0, "fail": 0, "error": 0}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {"total": total, "done": len(results), **counts}
