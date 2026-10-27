#!/usr/bin/env python3
"""
Eclipse AI Inference Engines Package
====================================
Self-contained Gemini Web and Zhipu AI GLM inference engines.
Zero external provider dependencies.
"""

import asyncio
import json
import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional

from .gemini import stream_gemini_chat
from .glm import stream_glm_chat
from .antigravity import stream_antigravity_chat


try:
    from eclipse import db
except Exception:
    db = None


async def stream_chat(
    provider_id: str,
    model: str,
    messages: List[Dict[str, Any]],
    accounts: Optional[List[Dict[str, Any]]] = None,
    stream: bool = True,
    **kwargs,
) -> AsyncIterator[Dict[str, Any]]:
    """
    Universal router for authentic AI model inference across supported providers.
    All provider engines are strictly isolated:
    - GLM requests are routed exclusively to the authentic GLM engine with its own
      internal 429 session auto-healer and zero Google fallback.
    - Google Antigravity & Gemini requests run through their respective engines.
    """
    pid = (provider_id or "").lower().strip()

    # 1. Zhipu AI GLM (Authentic Webscraper with internal 429 session auto-healer)
    if pid in ("glm", "zhipu", "chatglm"):
        token = ""
        if accounts:
            token = accounts[0].get("token", "")
            if not token:
                token = accounts[0].get("refresh_token", "")

        async for chunk in stream_glm_chat(
            model, messages, accounts=accounts, raw_token=token or None, stream=stream, **kwargs
        ):
            yield chunk
        return

    # 2. Google Antigravity (OAuth)
    if pid in ("antigravity", "agy", "google-antigravity"):
        async for chunk in stream_antigravity_chat(model, messages, accounts=accounts, stream=stream, **kwargs):
            yield chunk
        return

    # 3. Google Gemini (Web)
    async for chunk in stream_gemini_chat(model, messages, accounts=accounts, stream=stream, **kwargs):
        yield chunk


async def generate_chat(
    provider_id: str,
    model: str,
    messages: List[Dict[str, Any]],
    accounts: Optional[List[Dict[str, Any]]] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Execute complete non-streaming chat completion."""
    pid = (provider_id or "ai").lower().strip()
    full_content = []
    full_reasoning = []
    created_ts = int(time.time())
    chat_id = f"chatcmpl-{pid}-{uuid.uuid4().hex[:12]}"

    async for chunk in stream_chat(provider_id, model, messages, accounts=accounts, stream=False, **kwargs):
        choices = chunk.get("choices", [])
        if choices:
            if choices[0].get("finish_reason") == "error":
                raise RuntimeError(str((choices[0].get("delta") or {}).get("content") or "error"))
            delta = choices[0].get("delta", {})
            c = delta.get("content")
            r = delta.get("reasoning_content")
            if c:
                full_content.append(c)
            if r:
                full_reasoning.append(r)

    content_str = "".join(full_content)
    reasoning_str = "".join(full_reasoning) if full_reasoning else None

    msg_obj = {"role": "assistant", "content": content_str}
    if reasoning_str:
        msg_obj["reasoning_content"] = reasoning_str

    return {
        "id": chat_id,
        "object": "chat.completion",
        "created": created_ts,
        "model": model,
        "choices": [{
            "index": 0,
            "message": msg_obj,
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": len(str(messages)) // 4,
            "completion_tokens": len(content_str) // 4,
            "total_tokens": (len(str(messages)) + len(content_str)) // 4,
        },
    }
