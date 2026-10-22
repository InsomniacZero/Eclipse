#!/usr/bin/env python3
"""
Agent loop: lets a model reason in several steps and call tools.

`run()` wraps an engine stream. It yields OpenAI-style chunks (`reasoning_content`,
`content`) exactly like the engine does, plus chunks whose delta carries an
`eclipse_event`:

    {"type": "step_start",  "step": 1}
    {"type": "tool_start",  "id": "1", "name": "web_search", "arguments": {...}}
    {"type": "tool_result", "id": "1", "name": "web_search", "ok": true, "summary": "5 results",
     "backend": "Bing", "ms": 812, "sources": [{"n": 1, "title": ..., "url": ..., "snippet": ...}]}
    {"type": "step_limit"}

Clients that do not know about events ignore them. Each step calls the engine again with the
whole transcript, because the engines have no tool calling of their own.
"""

import asyncio
import logging
import time
import uuid
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

from . import ToolContext, ToolError, ToolResult
from . import get as get_tool
from . import protocol

log = logging.getLogger("eclipse.tools.loop")

DEFAULT_MAX_STEPS = 6
MAX_STEPS_LIMIT = 10
TOOL_TIMEOUT = 20.0
TOOL_TIME_BUDGET = 90.0
MAX_RESULT_CHARS = 6000
TRANSCRIPT_BUDGET = 30000
SHRUNK_RESULT_CHARS = 1200

StreamFactory = Callable[[List[Dict[str, Any]]], AsyncIterator[Dict[str, Any]]]


def _chunk(chat_id: str, model: str, delta: Dict[str, Any], finish: Optional[str] = None) -> Dict[str, Any]:
    return {
        "id": chat_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }


def _event(chat_id: str, model: str, **event: Any) -> Dict[str, Any]:
    return _chunk(chat_id, model, {"eclipse_event": event})


def clamp_steps(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return DEFAULT_MAX_STEPS
    return max(1, min(MAX_STEPS_LIMIT, value))


class _Transcript:
    """The conversation sent upstream, with tool results kept within a size budget."""

    def __init__(self, messages: List[Dict[str, Any]]) -> None:
        self.messages = messages
        self._results: List[Dict[str, Any]] = []   # {"index", "id", "name", "text", "ok", "note"}

    def add_assistant(self, text: str) -> None:
        self.messages.append({"role": "assistant", "content": text})

    def add_result(self, call_id: str, name: str, text: str, ok: bool, note: str = "") -> None:
        record = {"index": len(self.messages), "id": call_id, "name": name, "text": text, "ok": ok, "note": note}
        self._results.append(record)
        self.messages.append({"role": "user", "content": self._render(record)})
        self._shrink()

    @staticmethod
    def _render(record: Dict[str, Any]) -> str:
        body = protocol.format_result(record["id"], record["name"], record["text"], record["ok"])
        return f"{body}\n\n{record['note']}".strip()

    def _size(self) -> int:
        return sum(len(r["text"]) for r in self._results)

    def _shrink(self) -> None:
        for record in self._results:
            if self._size() <= TRANSCRIPT_BUDGET:
                break
            if len(record["text"]) > SHRUNK_RESULT_CHARS:
                record["text"] = record["text"][:SHRUNK_RESULT_CHARS] + "\n[older result shortened]"
                self.messages[record["index"]] = {"role": "user", "content": self._render(record)}


async def run(
    stream_factory: StreamFactory,
    messages: List[Dict[str, Any]],
    tool_names: List[str],
    *,
    model: str = "",
    max_steps: int = DEFAULT_MAX_STEPS,
    get_setting: Optional[Callable[[str, Optional[str]], Optional[str]]] = None,
    tool_timeout: float = TOOL_TIMEOUT,
    time_budget: float = TOOL_TIME_BUDGET,
    cite: bool = True,
    guidance: str = "",
) -> AsyncIterator[Dict[str, Any]]:
    tools = []
    for name in dict.fromkeys(tool_names or []):
        tool = get_tool(name) if isinstance(name, str) else None
        if tool:
            tools.append(tool)
    if not tools:
        async for chunk in stream_factory(messages):
            yield chunk
        return

    by_name = {t.name: t for t in tools}
    ctx = ToolContext(get_setting=get_setting) if get_setting else ToolContext()
    transcript = _Transcript(protocol.inject_tools_prompt(messages, tools, cite, guidance))
    chat_id = f"chatcmpl-tools-{uuid.uuid4().hex[:12]}"
    max_steps = clamp_steps(max_steps)

    calls_made = 0
    repairs = 0
    tool_time = 0.0
    final_turn = False
    step = 0

    yield _chunk(chat_id, model, {"role": "assistant"})

    while True:
        step += 1
        yield _event(chat_id, model, type="step_start", step=step)

        scanner = protocol.CallScanner()
        shown: List[str] = []
        call_raw: Optional[str] = None
        unterminated = False

        upstream = stream_factory(transcript.messages)
        try:
            async for chunk in upstream:
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                choice = choices[0]
                if choice.get("finish_reason") == "error":
                    yield chunk
                    return
                delta = dict(choice.get("delta") or {})
                delta.pop("role", None)
                content = delta.pop("content", None)
                if isinstance(content, str) and content:
                    text, raw = scanner.feed(content)
                    if text:
                        shown.append(text)
                        delta["content"] = text
                    if raw is not None:
                        call_raw = raw
                if delta:
                    yield _chunk(chat_id, model, delta)
                if call_raw is not None:
                    break
        finally:
            aclose = getattr(upstream, "aclose", None)
            if aclose:
                try:
                    await aclose()
                except Exception:  # closing a half-read upstream must never hide the real result
                    log.debug("closing upstream failed", exc_info=True)

        if call_raw is None:
            tail, raw, unterminated = scanner.finish()
            if tail:
                shown.append(tail)
                yield _chunk(chat_id, model, {"content": tail})
            if unterminated:
                call_raw = raw

        if call_raw is None:
            break  # a turn without a tool call is the final answer

        if final_turn:
            break  # the model was told not to use tools; drop the call and finish with what it wrote

        calls_made += 1
        call_id = str(calls_made)
        turn_text = "".join(shown)

        name, args, failure = "", {}, ""
        if unterminated:
            failure = "The tool call was not closed with </tool_call>."
        else:
            try:
                name, args = protocol.parse_call(call_raw)
            except ToolError as e:
                failure = str(e)
        tool = by_name.get(name) if not failure else None
        if not failure and tool is None:
            failure = f"There is no tool named {name!r}. Available: {', '.join(by_name)}."

        yield _event(chat_id, model, type="tool_start", id=call_id, name=name or "?", arguments=args)

        ok, result, error = False, None, failure
        started = time.monotonic()
        if tool is not None:
            try:
                result = await asyncio.wait_for(tool.run(args, ctx), timeout=tool_timeout)
                ok = True
            except ToolError as e:
                error = str(e)
            except asyncio.TimeoutError:
                error = f"{name} timed out after {tool_timeout:.0f} seconds."
            except Exception as e:
                log.exception("tool %s crashed", name)
                error = f"{name} failed ({e.__class__.__name__})."
        elapsed = time.monotonic() - started
        tool_time += elapsed

        if ok:
            text = result.text
            if len(text) > MAX_RESULT_CHARS:
                text = text[:MAX_RESULT_CHARS] + "\n[result cut]"
            yield _event(
                chat_id, model, type="tool_result", id=call_id, name=name, ok=True,
                summary=result.summary, backend=result.meta.get("backend", ""),
                ms=int(elapsed * 1000), sources=result.sources, detail=result.meta,
            )
        else:
            text = error
            repairs += 1
            yield _event(
                chat_id, model, type="tool_result", id=call_id, name=name or "?", ok=False,
                summary="", error=error, ms=int(elapsed * 1000), sources=[],
            )

        transcript.add_assistant(f"{turn_text}{protocol.TOOL_OPEN}{call_raw}{protocol.TOOL_CLOSE}".strip())

        if calls_made >= max_steps or tool_time >= time_budget or repairs > 1:
            final_turn = True
            note = "You have used all the tool calls you can. Write the final answer now from what you have. Do not call a tool."
            yield _event(chat_id, model, type="step_limit")
        elif ok:
            note = (
                "Continue. Call another tool if you still need information; otherwise write the final answer"
                + (" and cite sources as [n]." if cite else " without source markers.")
            )
        else:
            note = "That tool call failed. Fix it and call the tool again, or write the final answer without it."
        transcript.add_result(call_id, name or "tool", text, ok, note)

    yield _chunk(chat_id, model, {}, "stop")


class StepRecorder:
    """Builds the `steps` list (what the dashboard stores) from the chunks `run()` yields."""

    def __init__(self) -> None:
        self.steps: List[Dict[str, Any]] = []
        self.content = ""
        self.reasoning = ""
        self.limit_reached = False
        self.error = ""

    def _current(self) -> Dict[str, Any]:
        if not self.steps:
            self.steps.append({"step": 1, "reasoning": "", "calls": []})
        return self.steps[-1]

    def feed(self, chunk: Dict[str, Any]) -> None:
        if chunk.get("error"):
            self.error = str(chunk["error"])
            return
        choices = chunk.get("choices") or []
        if not choices:
            return
        if choices[0].get("finish_reason") == "error":
            self.error = (choices[0].get("delta") or {}).get("content") or "error"
            return
        delta = choices[0].get("delta") or {}
        if delta.get("reasoning_content"):
            self.reasoning += delta["reasoning_content"]
            self._current()["reasoning"] += delta["reasoning_content"]
        if isinstance(delta.get("content"), str):
            self.content += delta["content"]
        ev = delta.get("eclipse_event")
        if not ev:
            return
        kind = ev.get("type")
        if kind == "step_start":
            self.steps.append({"step": ev.get("step", len(self.steps) + 1), "reasoning": "", "calls": []})
        elif kind == "tool_start":
            self._current()["calls"].append({
                "id": ev.get("id"), "name": ev.get("name"), "arguments": ev.get("arguments") or {},
                "ok": None, "summary": "", "sources": [], "backend": "", "ms": 0, "error": "",
            })
        elif kind == "tool_result":
            for call in self._current()["calls"]:
                if call["id"] == ev.get("id"):
                    call.update({
                        "ok": bool(ev.get("ok")), "summary": ev.get("summary", ""),
                        "sources": ev.get("sources") or [], "backend": ev.get("backend", ""),
                        "ms": ev.get("ms", 0), "error": ev.get("error", ""),
                    })
        elif kind == "step_limit":
            self.limit_reached = True
