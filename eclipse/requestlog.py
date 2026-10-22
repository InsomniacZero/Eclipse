#!/usr/bin/env python3
"""
Request log: what happened to one request that used a preset or tools.

A `Trace` is filled while `chat_completions` runs and then stored whole (see db.add_request_log). It keeps, for
every call to the model, exactly what was sent, what came back (reasoning and text), the tool call the model
wrote, what the tool did (query, backend, results, time) and the final reply, so a person can tell whether a
search happened, what it asked, and what the model was given.

Pure Python, no I/O: the gateway decides when to save. Everything is capped so one request cannot fill the DB.
"""

import time
from typing import Any, Dict, List, Optional

MAX_TEXT = 30_000          # characters kept per message or text field
MAX_TRACE_CHARS = 600_000  # whole trace, serialised; above this the long fields are cut harder
SHRUNK_TEXT = 3_000
MAX_SOURCES = 12

OUTCOMES = ("answered", "searched", "no_search", "search_failed", "error")


def clip(text: Any, limit: int = MAX_TEXT) -> str:
    text = text if isinstance(text, str) else ("" if text is None else str(text))
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n… [{len(text) - limit:,} more characters not logged]"


def message_view(message: Any) -> Dict[str, Any]:
    """One chat message as the log keeps it: role, text (clipped), real length."""
    if not isinstance(message, dict):
        return {"role": "?", "content": clip(message), "chars": len(str(message))}
    content = message.get("content")
    extra = ""
    if isinstance(content, list):
        parts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
        others = len(content) - len(parts)
        content = "\n".join(parts)
        extra = f"[+{others} non-text part{'s' if others != 1 else ''}]" if others else ""
    content = content if isinstance(content, str) else ""
    return {"role": str(message.get("role", "?")), "content": clip(content) + (("\n" + extra) if extra else ""), "chars": len(content)}


class Trace:
    def __init__(self, *, requested_model: str, model: str, preset: Optional[str], provider: str,
                 origin: str, stream: bool, incoming: List[Dict[str, Any]], tool_names: List[str], tag: str = "") -> None:
        self.started = time.time()
        self._t0 = time.monotonic()
        self.requested_model, self.model, self.preset = requested_model, model, preset
        self.provider, self.origin, self.stream = provider, origin, bool(stream)
        self.tool_names = list(tool_names)
        self.tag = tag
        self.incoming = {
            "messages": len(incoming),
            "roles": _count_roles(incoming),
            "chars": sum(m["chars"] for m in map(message_view, incoming)),
        }
        self.pipeline_info: Dict[str, Any] = {}
        self.steps: List[Dict[str, Any]] = []
        self._sent_count = 0
        self.visible = ""
        self.visible_reasoning = ""
        self.error = ""
        self.finish = ""
        self.finished = False

    # ---- what the gateway did before the model was called ----
    def pipeline(self, **info: Any) -> None:
        self.pipeline_info.update(info)

    # ---- one call to the model ----
    def sent(self, messages: List[Dict[str, Any]]) -> int:
        """Record a call to the model. The first call keeps every message; later calls keep only what was added."""
        step = len(self.steps) + 1
        added = messages[self._sent_count:] if step > 1 and len(messages) >= self._sent_count else messages
        self.steps.append({
            "step": step, "sent_total": len(messages), "sent_from": len(messages) - len(added),
            "sent": [message_view(m) for m in added], "output": "", "reasoning": "", "ms_model": None,
            "call": None, "tool": None, "_t": time.monotonic(),
        })
        self._sent_count = len(messages)
        return step

    def output(self, step: int, text: str, reasoning: str, failed: str = "") -> None:
        if not 1 <= step <= len(self.steps):
            return
        s = self.steps[step - 1]
        s["output"], s["reasoning"] = clip(text), clip(reasoning)
        s["output_chars"], s["reasoning_chars"] = len(text), len(reasoning)
        s["ms_model"] = int((time.monotonic() - s["_t"]) * 1000)
        if failed:
            s["model_error"] = clip(failed, 2000)

    # ---- what the loop reports (the same events the dashboard gets) ----
    def feed(self, chunk: Dict[str, Any]) -> None:
        if chunk.get("error"):
            self.error = self.error or clip(str(chunk["error"]), 2000)
            return
        choices = chunk.get("choices") or []
        if not choices:
            return
        choice = choices[0]
        delta = choice.get("delta") or {}
        if choice.get("finish_reason") == "error":
            self.error = self.error or clip(delta.get("content") or "error", 2000)
        elif choice.get("finish_reason"):
            self.finish = str(choice["finish_reason"])
        if isinstance(delta.get("content"), str) and choice.get("finish_reason") != "error":
            self.visible += delta["content"]
        if isinstance(delta.get("reasoning_content"), str):
            self.visible_reasoning += delta["reasoning_content"]
        ev = delta.get("eclipse_event")
        if not isinstance(ev, dict) or not self.steps:
            return
        step = self.steps[-1]
        kind = ev.get("type")
        if kind == "tool_start":
            step["call"] = {"id": ev.get("id"), "name": ev.get("name"), "arguments": ev.get("arguments") or {}}
        elif kind == "tool_result":
            sources = [{k: clip(src.get(k), 400) for k in ("n", "title", "url", "snippet")}
                       for src in (ev.get("sources") or [])[:MAX_SOURCES] if isinstance(src, dict)]
            step["tool"] = {
                "name": ev.get("name"), "ok": bool(ev.get("ok")), "summary": ev.get("summary", ""),
                "backend": ev.get("backend", ""), "ms": ev.get("ms", 0), "error": clip(ev.get("error", ""), 2000),
                "sources": sources, "detail": ev.get("detail") or {},
            }
        elif kind == "step_limit":
            step["limit_reached"] = True

    def set_reply(self, content: str, reasoning: str = "") -> None:
        """For a request that did not stream through `feed` (a plain non-streaming reply)."""
        self.visible, self.visible_reasoning = content or "", reasoning or ""

    # ---- result ----
    def searches(self) -> List[Dict[str, Any]]:
        out = []
        for s in self.steps:
            call = s.get("call")
            if not call:
                continue
            tool = s.get("tool") or {}
            args = call.get("arguments") or {}
            what = args.get("query") or args.get("url") or ""
            out.append({"step": s["step"], "tool": call.get("name") or "?", "what": clip(what, 300), "ok": bool(tool.get("ok")),
                        "results": len(tool.get("sources") or []), "backend": tool.get("backend", ""), "ms": tool.get("ms", 0)})
        return out

    def outcome(self) -> str:
        if self.error:
            return "error"
        calls = self.searches()
        if calls:
            return "searched" if any(c["ok"] for c in calls) else "search_failed"
        return "no_search" if self.tool_names else "answered"

    def record(self) -> Dict[str, Any]:
        """Everything the DB stores: summary columns plus the full trace."""
        calls = self.searches()
        trace = {
            "request": {
                "requested_model": self.requested_model, "model": self.model, "preset": self.preset, "provider": self.provider,
                "origin": self.origin, "stream": self.stream, "tools": self.tool_names, "incoming": self.incoming,
            },
            "pipeline": self.pipeline_info,
            "steps": [{k: v for k, v in s.items() if not k.startswith("_")} for s in self.steps],
            "searches": calls,
            "reply": {"content": clip(self.visible), "reasoning": clip(self.visible_reasoning), "chars": len(self.visible),
                      "finish": self.finish, "error": self.error},
        }
        _fit(trace)
        return {
            "requested_model": self.requested_model, "model": self.model, "preset": self.preset or "", "provider": self.provider,
            "origin": self.origin or "", "tag": self.tag, "stream": self.stream, "tools": bool(self.tool_names),
            "searches": len(calls), "searches_ok": sum(1 for c in calls if c["ok"]),
            "outcome": self.outcome(), "queries": [c["what"] for c in calls],
            "ms": int((time.monotonic() - self._t0) * 1000), "error": self.error, "reply_chars": len(self.visible),
            "trace": trace,
        }


def _count_roles(messages: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for m in messages:
        role = str(m.get("role", "?")) if isinstance(m, dict) else "?"
        counts[role] = counts.get(role, 0) + 1
    return counts


def _size(obj: Any) -> int:
    import json
    return len(json.dumps(obj, ensure_ascii=False))


def _fit(trace: Dict[str, Any]) -> None:
    """Keep a trace under MAX_TRACE_CHARS by cutting the longest text fields harder."""
    if _size(trace) <= MAX_TRACE_CHARS:
        return
    for step in trace["steps"]:
        for m in step["sent"]:
            m["content"] = clip(m["content"], SHRUNK_TEXT)
    if _size(trace) <= MAX_TRACE_CHARS:
        return
    for step in trace["steps"]:
        step["output"], step["reasoning"] = clip(step["output"], SHRUNK_TEXT), clip(step["reasoning"], SHRUNK_TEXT)
    trace["reply"]["content"] = clip(trace["reply"]["content"], SHRUNK_TEXT)
    trace["reply"]["reasoning"] = clip(trace["reply"]["reasoning"], SHRUNK_TEXT)
