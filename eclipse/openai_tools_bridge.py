#!/usr/bin/env python3
"""
OpenAI Native Tool Calling Bridge for Web / Direct LLM Engines.

Enables IDE coding agents (Kimi Code, Cline, Roo Code, etc.) to use tools
via models that do not natively support OpenAI function calling.

CRITICAL INVARIANT:
If incoming request has no `tools` or `functions`, this module is a NO-OP.
RP (roleplay), SillyTavern, Janitor, and regular chats remain 100% untouched.
"""

import json
import re
import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

TOOL_OPEN = "<tool_call>"
TOOL_CLOSE = "</tool_call>"

def is_tool_request(body: Dict[str, Any]) -> bool:
    """Return True ONLY if the request explicitly asks for tools/functions."""
    tools = body.get("tools")
    if isinstance(tools, list) and len(tools) > 0:
        return True
    functions = body.get("functions")
    if isinstance(functions, list) and len(functions) > 0:
        return True
    return False


def build_tools_instruction(tools_or_functions: List[Dict[str, Any]]) -> str:
    """Format OpenAI tools/functions into a strict system prompt instruction."""
    tool_lines = []
    for item in tools_or_functions:
        fn = item.get("function") if item.get("type") == "function" else item
        if not isinstance(fn, dict):
            continue
        name = fn.get("name", "")
        desc = fn.get("description", "")
        params = fn.get("parameters", {})
        props = params.get("properties", {}) if isinstance(params, dict) else {}
        required = set(params.get("required", [])) if isinstance(params, dict) else set()
        
        arg_strs = []
        for k, v in props.items():
            arg_type = v.get("type", "any") if isinstance(v, dict) else "any"
            opt = "" if k in required else " (optional)"
            arg_strs.append(f'"{k}": {arg_type}{opt}')
        args_formatted = ", ".join(arg_strs)
        tool_lines.append(f"- {name}: {desc}\n  Arguments: {{{args_formatted}}}")

    tools_block = "\n".join(tool_lines)

    return (
        "\n\n[SYSTEM: LOCAL TOOL EXECUTION ENVIRONMENT]\n"
        "You are an expert coding assistant operating inside the user's local workspace.\n"
        "You have direct access to execute actions and inspect files through the tools listed below.\n"
        "IMPORTANT: You are NOT in a remote cloud sandbox or /mnt/agents. You are running on the user's machine.\n"
        "If the user asks you to read, write, edit files, check directories, or run commands, YOU MUST CALL A TOOL.\n"
        "Do NOT hallucinate or pretend to execute commands in your reasoning or text.\n\n"
        "AVAILABLE TOOLS:\n"
        f"{tools_block}\n\n"
        "TOOL CALLING PROTOCOL:\n"
        "When you decide to call a tool, you MUST output ONLY the following format:\n"
        "<tool_call>\n"
        '{"name": "tool_name", "arguments": {"arg1": "value1"}}\n'
        "</tool_call>\n\n"
        "RULES:\n"
        "1. Output the <tool_call>...</tool_call> and STOP immediately. Do NOT write conversational explanations when calling a tool.\n"
        "2. The tool result will be supplied in the next message as <tool_result>...</tool_result>.\n"
        "3. When you have all information and no further tool is needed, answer the user directly in normal text.\n"
    )


def adapt_messages_for_tools(messages: List[Dict[str, Any]], tools_or_functions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Format message history so previous tool calls and tool outputs
    are represented clearly to the model, and inject the tool system instructions.
    """
    instruction = build_tools_instruction(tools_or_functions)
    adapted: List[Dict[str, Any]] = []

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        tool_calls = msg.get("tool_calls")
        
        # If assistant previously called tools in OpenAI format
        if role == "assistant" and tool_calls and isinstance(tool_calls, list):
            parts = []
            if content:
                parts.append(str(content).strip())
            for tc in tool_calls:
                fn = tc.get("function", {})
                name = fn.get("name", "")
                args_str = fn.get("arguments", "{}")
                try:
                    args_obj = json.loads(args_str) if isinstance(args_str, str) else args_str
                except Exception:
                    args_obj = args_str
                parts.append(f"{TOOL_OPEN}\n{json.dumps({'name': name, 'arguments': args_obj}, ensure_ascii=False)}\n{TOOL_CLOSE}")
            adapted.append({"role": "assistant", "content": "\n".join(parts)})
            continue

        # If previous message is a tool output (role: "tool")
        if role == "tool":
            tool_id = msg.get("tool_call_id", "")
            tool_name = msg.get("name", "tool")
            content_str = str(content) if content is not None else ""
            tool_res = f'<tool_result id="{tool_id}" name="{tool_name}">\n{content_str}\n</tool_result>'
            adapted.append({"role": "user", "content": tool_res})
            continue

        # Regular message
        adapted.append(dict(msg))

    # Inject instruction into system prompt or as first message
    system_found = False
    for i, m in enumerate(adapted):
        if m.get("role") == "system":
            adapted[i] = {**m, "content": f"{m.get('content', '')}\n{instruction}"}
            system_found = True
            break
            
    if not system_found:
        adapted.insert(0, {"role": "system", "content": instruction})

    return adapted


_TOOL_CALL_REGEX = re.compile(
    r"(?:<tool_call>|```(?:tool_call|json)?\s*<tool_call>|```tool_call\s*)([\s\S]*?)(?:</tool_call>|```|$)",
    re.IGNORECASE
)

def parse_tool_call_text(text: str) -> Optional[Tuple[str, Dict[str, Any], str]]:
    """
    Inspect text for tool call syntax.
    Returns (tool_name, arguments_dict, remaining_text_before_tool_call) or None.
    """
    if not text:
        return None
        
    # Match <tool_call>...</tool_call>
    start_tag = text.find(TOOL_OPEN)
    if start_tag != -1:
        end_tag = text.find(TOOL_CLOSE, start_tag)
        if end_tag != -1:
            raw_json = text[start_tag + len(TOOL_OPEN):end_tag].strip()
            before_text = text[:start_tag].strip()
            parsed = _extract_name_and_args(raw_json)
            if parsed:
                return parsed[0], parsed[1], before_text

    # Fallback: check for ```tool_call ... ```
    m = re.search(r"```tool_call\s*([\s\S]*?)```", text, re.IGNORECASE)
    if m:
        before_text = text[:m.start()].strip()
        parsed = _extract_name_and_args(m.group(1).strip())
        if parsed:
            return parsed[0], parsed[1], before_text

    return None


def _extract_name_and_args(raw: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    """Parse JSON string into tool name and arguments dictionary."""
    clean = raw.strip()
    # Strip markdown fences if present
    if clean.startswith("```"):
        clean = re.sub(r"^```[a-zA-Z0-9_-]*\s*|\s*```$", "", clean).strip()
    
    first_brace = clean.find("{")
    last_brace = clean.rfind("}")
    if first_brace == -1 or last_brace <= first_brace:
        return None
        
    try:
        data = json.loads(clean[first_brace:last_brace + 1])
    except Exception:
        return None

    if not isinstance(data, dict):
        return None

    name = data.get("name") or data.get("tool")
    if not name or not isinstance(name, str):
        return None

    args = data.get("arguments", data.get("args", data.get("parameters", {})))
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except Exception:
            args = {}
    if not isinstance(args, dict):
        args = {}

    return name.strip(), args


async def wrap_tool_stream(
    raw_source: AsyncIterator[Dict[str, Any]],
    requested_model: str,
) -> AsyncIterator[Dict[str, Any]]:
    """
    Filter and intercept streamed chunks.
    If the model outputs <tool_call>...</tool_call>, convert it into
    standard OpenAI `delta.tool_calls` chunk with `finish_reason: "tool_calls"`.
    """
    buffer = ""
    in_tool_call = False
    tool_call_detected = False
    chat_id = f"chatcmpl-call-{uuid.uuid4().hex[:12]}"
    created_ts = int(time.time())

    async for chunk in raw_source:
        choices = chunk.get("choices") or [{}]
        delta = choices[0].get("delta") or {}

        # Pass reasoning content through immediately
        if "reasoning_content" in delta and delta["reasoning_content"]:
            yield chunk
            continue

        content_piece = delta.get("content")
        if not content_piece:
            # Maybe finish or empty delta
            if not in_tool_call and not tool_call_detected:
                yield chunk
            continue

        buffer += content_piece

        # Check if we are inside or encountering <tool_call>
        if not in_tool_call:
            tag_idx = buffer.find(TOOL_OPEN)
            if tag_idx != -1:
                # Flush everything before <tool_call> as normal text
                prefix = buffer[:tag_idx]
                if prefix:
                    yield {
                        "id": chunk.get("id", chat_id),
                        "object": "chat.completion.chunk",
                        "created": chunk.get("created", created_ts),
                        "model": requested_model,
                        "choices": [{"index": 0, "delta": {"content": prefix}, "finish_reason": None}]
                    }
                buffer = buffer[tag_idx:]
                in_tool_call = True
            else:
                # Hold back only if buffer ends with a partial prefix of <tool_call>
                # Length of partial tag
                hold = 0
                for n in range(min(len(TOOL_OPEN) - 1, len(buffer)), 0, -1):
                    if TOOL_OPEN.startswith(buffer[-n:]):
                        hold = n
                        break
                
                if hold > 0:
                    emit_text = buffer[:-hold]
                    buffer = buffer[-hold:]
                else:
                    emit_text = buffer
                    buffer = ""

                if emit_text:
                    yield {
                        "id": chunk.get("id", chat_id),
                        "object": "chat.completion.chunk",
                        "created": chunk.get("created", created_ts),
                        "model": requested_model,
                        "choices": [{"index": 0, "delta": {"content": emit_text}, "finish_reason": None}]
                    }

        # Check if tool call has closed
        if in_tool_call:
            close_idx = buffer.find(TOOL_CLOSE)
            if close_idx != -1:
                parsed = parse_tool_call_text(buffer[:close_idx + len(TOOL_CLOSE)])
                if parsed:
                    name, args, _ = parsed
                    tool_call_detected = True
                    call_id = f"call_{uuid.uuid4().hex[:12]}"
                    # Yield standard OpenAI tool_calls delta
                    yield {
                        "id": chunk.get("id", chat_id),
                        "object": "chat.completion.chunk",
                        "created": chunk.get("created", created_ts),
                        "model": requested_model,
                        "choices": [{
                            "index": 0,
                            "delta": {
                                "role": "assistant",
                                "tool_calls": [{
                                    "index": 0,
                                    "id": call_id,
                                    "type": "function",
                                    "function": {
                                        "name": name,
                                        "arguments": json.dumps(args, ensure_ascii=False)
                                    }
                                }]
                            },
                            "finish_reason": "tool_calls"
                        }]
                    }
                    buffer = ""
                    in_tool_call = False
                    return  # Turn finished after tool call

    # Stream ended: flush any remaining buffer
    if buffer and not tool_call_detected:
        parsed = parse_tool_call_text(buffer)
        if parsed:
            name, args, prefix = parsed
            if prefix:
                yield {
                    "id": chat_id,
                    "object": "chat.completion.chunk",
                    "created": created_ts,
                    "model": requested_model,
                    "choices": [{"index": 0, "delta": {"content": prefix}, "finish_reason": None}]
                }
            call_id = f"call_{uuid.uuid4().hex[:12]}"
            yield {
                "id": chat_id,
                "object": "chat.completion.chunk",
                "created": created_ts,
                "model": requested_model,
                "choices": [{
                    "index": 0,
                    "delta": {
                        "role": "assistant",
                        "tool_calls": [{
                            "index": 0,
                            "id": call_id,
                            "type": "function",
                            "function": {
                                "name": name,
                                "arguments": json.dumps(args, ensure_ascii=False)
                            }
                        }]
                    },
                    "finish_reason": "tool_calls"
                }]
            }
        else:
            yield {
                "id": chat_id,
                "object": "chat.completion.chunk",
                "created": created_ts,
                "model": requested_model,
                "choices": [{"index": 0, "delta": {"content": buffer}, "finish_reason": "stop"}]
            }
