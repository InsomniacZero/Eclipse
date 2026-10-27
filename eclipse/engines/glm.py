#!/usr/bin/env python3
"""
Eclipse Native GLM (Zhipu AI) Authentic Webscraper Engine
==========================================================
Authentic, zero-legacy reverse-proxy driver for Zhipu AI GLM models (GLM-4, GLM-5.3, GLM-Zero).
Direct webscraper routing with:
- Zero guardrail interference / minimal content filtering for authentic roleplay
- Automatic Free Guest Token Generation on-the-fly (zero config, works worldwide)
- Self-healing on HTTP 429 / 10061 with immediate dynamic token renewal
- Background conversation session cleanup (prevents lingering server busy locks)
- User Refresh Token authentication from Eclipse SQLite vault
- Monotonic delta streaming (eliminates token stuttering, chunk duplication)
- Deep thinking / reasoning traces (reasoning_content)
"""

import asyncio
import hashlib
import json
import logging
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

logger = logging.getLogger("eclipse.engines.glm")

GLM_BASE_URL = os.getenv("GLM_BASE_URL", "https://chatglm.cn/chatglm")
DEFAULT_ASSISTANT_ID = os.getenv("GLM_ASSISTANT_ID", "65940acff94777010aa6b796")
SIGN_SECRET = "8a1317a7468aa3ad86e997d08f3f31cb"
ASSISTANT_ID_PATTERN = re.compile(r"^[0-9a-f]{24}$", re.IGNORECASE)

# In-memory token cache: { "cache_key": { "token": str, "expires_at": float } }
_TOKEN_CACHE: Dict[str, Dict[str, Any]] = {}
_TOKEN_LOCK = asyncio.Lock()


def build_sign() -> Tuple[str, str, str]:
    """Compute Zhipu dynamic anti-replay signature."""
    now = str(int(time.time() * 1000))
    digits = [int(char) for char in now]
    checksum = (sum(digits) - digits[-2]) % 10
    timestamp = now[:-2] + str(checksum) + now[-1]
    nonce = uuid.uuid4().hex
    sign = hashlib.md5(f"{timestamp}-{nonce}-{SIGN_SECRET}".encode("utf-8")).hexdigest()
    return timestamp, nonce, sign


def _format_messages_to_prompt(messages: List[Dict[str, Any]]) -> str:
    """Flatten conversation history to a clean transcript prompt for GLM Web."""
    transcript = []
    for m in messages:
        role = str(m.get("role", "user")).lower().strip()
        content = m.get("content", "")
        if isinstance(content, list):
            text_parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
                elif isinstance(item, str):
                    text_parts.append(item)
            content = " ".join(text_parts)
        content_str = str(content).strip()
        if not content_str:
            continue

        if role == "system":
            transcript.append(f"System: {content_str}")
        elif role == "assistant":
            transcript.append(f"Assistant: {content_str}")
        else:
            transcript.append(f"User: {content_str}")

    return "\n\n".join(transcript).strip()


async def get_valid_access_token(raw_refresh_token: Optional[str] = None, force_refresh: bool = False) -> str:
    """
    Acquire valid access token:
    1. If user provided a refresh token in vault, refresh user session.
    2. Otherwise, automatically request a fresh anonymous Guest Token.
    Works anywhere, across all devices, seamlessly.
    """
    async with _TOKEN_LOCK:
        now = time.time()
        cache_key = raw_refresh_token.strip() if raw_refresh_token and raw_refresh_token.strip() else "__guest__"
        cached = _TOKEN_CACHE.get(cache_key)

        if not force_refresh and cached and cached.get("expires_at", 0) > now + 60:
            return cached["token"]

        t, n, s = build_sign()
        base_headers = {
            "Accept": "application/json, text/plain, */*",
            "App-Name": "chatglm",
            "Origin": "https://chatglm.cn",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "X-App-Fr": "default",
            "X-App-Platform": "pc",
            "X-App-Version": "0.0.1",
            "X-Device-Id": uuid.uuid4().hex,
            "X-Nonce": n,
            "X-Request-Id": uuid.uuid4().hex,
            "X-Sign": s,
            "X-Timestamp": t,
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            if cache_key != "__guest__":
                # Refresh user token
                refresh_url = f"{GLM_BASE_URL}/user-api/user/refresh"
                headers = {**base_headers, "Authorization": f"Bearer {raw_refresh_token}"}
                try:
                    resp = await client.post(refresh_url, headers=headers, json={})
                    data = resp.json()
                    res = data.get("result", {})
                    acc_token = res.get("access_token")
                    if acc_token:
                        _TOKEN_CACHE[cache_key] = {
                            "token": acc_token,
                            "expires_at": now + 3500,
                        }
                        return acc_token
                except Exception:
                    pass  # Fall back to guest token if refresh token failed

            # Guest Mode Token Generation
            guest_url = f"{GLM_BASE_URL}/user-api/guest/access"
            resp = await client.post(guest_url, headers=base_headers, json={})
            data = resp.json()
            res = data.get("result", {})
            acc_token = res.get("access_token")
            if not acc_token:
                raise RuntimeError(f"GLM Guest authentication failed: {data}")

            _TOKEN_CACHE["__guest__"] = {
                "token": acc_token,
                "expires_at": now + 3500,
            }
            return acc_token


async def _delete_conversation(conversation_id: str, assistant_id: str, access_token: str) -> None:
    """Clean up server session to release the busy lock immediately."""
    if not conversation_id or not access_token:
        return
    try:
        t, n, s = build_sign()
        headers = {
            "Accept": "application/json, text/plain, */*",
            "App-Name": "chatglm",
            "Origin": "https://chatglm.cn",
            "Referer": "https://chatglm.cn/main/alltoolsdetail",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            "Authorization": f"Bearer {access_token}",
            "X-Device-Id": uuid.uuid4().hex,
            "X-Nonce": n,
            "X-Request-Id": uuid.uuid4().hex,
            "X-Sign": s,
            "X-Timestamp": t,
        }
        async with httpx.AsyncClient(timeout=8.0) as client:
            await client.post(
                f"{GLM_BASE_URL}/backend-api/assistant/conversation/delete",
                headers=headers,
                json={"assistant_id": assistant_id, "conversation_id": conversation_id},
            )
    except Exception:
        pass


async def stream_glm_chat(
    model: str,
    messages: List[Dict[str, Any]],
    accounts: Optional[List[Dict[str, Any]]] = None,
    raw_token: Optional[str] = None,
    stream: bool = True,
    **kwargs,
) -> AsyncIterator[Dict[str, Any]]:
    """
    Stream chat completion directly from Zhipu GLM Web with clean monotonic deltas
    and automatic self-healing retry for HTTP 429 busy errors.
    Yields OpenAI-compatible chunks.
    """
    chat_id = f"chatcmpl-glm-{uuid.uuid4().hex[:12]}"
    created_ts = int(time.time())

    # 1. Assistant & Chat Mode Resolution
    lower_model = (model or "").lower()
    if ASSISTANT_ID_PATTERN.fullmatch(model):
        assistant_id = model
    else:
        assistant_id = DEFAULT_ASSISTANT_ID

    is_reasoning = (
        "zero" in lower_model
        or "think" in lower_model
        or "r1" in lower_model
        or kwargs.get("reasoning_effort") is not None
    )
    chat_mode = "zero" if is_reasoning else ""
    is_networking = bool(kwargs.get("web_search")) or "search" in lower_model or "online" in lower_model

    # 2. Format Prompt & Sampling Parameters
    prompt = _format_messages_to_prompt(messages)
    # Append invisible zero-width spaces (U+200B) to bust upstream prompt deduplication caching on rerolls
    cache_buster = "\u200b" * random.randint(10, 500)
    glm_messages = [{"role": "user", "content": [{"type": "text", "text": prompt + "\n\nAssistant: " + cache_buster}]}]
    turn_draft_id = uuid.uuid4().hex

    # Forward sampling parameters for authentic roleplay variation on rerolls
    raw_temp = kwargs.get("temperature")
    try:
        temperature = float(raw_temp) if raw_temp is not None else 0.95
    except (ValueError, TypeError):
        temperature = 0.95

    raw_top_p = kwargs.get("top_p")
    try:
        top_p = float(raw_top_p) if raw_top_p is not None else 0.9
    except (ValueError, TypeError):
        top_p = 0.9

    request_body = {
        "assistant_id": assistant_id,
        "conversation_id": "",
        "project_id": "",
        "chat_type": "user_chat",
        "messages": glm_messages,
        "temperature": temperature,
        "top_p": top_p,
        "meta_data": {
            "channel": "",
            "chat_mode": chat_mode,
            "draft_id": turn_draft_id,
            "if_plus_model": True,
            "input_question_type": "xxxx",
            "is_networking": is_networking,
            "is_test": False,
            "platform": "pc",
            "quote_log_id": "",
            "temperature": temperature,
            "top_p": top_p,
            "cogview": {"rm_label_watermark": False},
        },
    }

    # Resolve token candidates
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

    num_candidates = len(candidate_tokens)
    stream_url = f"{GLM_BASE_URL}/backend-api/assistant/stream"
    accumulated_text: Dict[str, str] = {}
    accumulated_think: Dict[str, str] = {}
    started_streaming = False
    conversation_id = ""
    active_access_token = ""

    MAX_RETRIES = max(4, num_candidates * 2) if num_candidates > 0 else 4
    acc_idx = 0

    for attempt in range(MAX_RETRIES):
        current_token = candidate_tokens[acc_idx % num_candidates] if candidate_tokens else None
        # Always obtain a fresh guest session on retries or initial guest requests to prevent collision
        force_fresh = (attempt > 0) or (current_token is None)
        if attempt > 0:
            retry_draft_id = uuid.uuid4().hex
            request_body["meta_data"]["draft_id"] = retry_draft_id
            request_body["meta_data"]["quote_log_id"] = ""
            retry_zws = "\u200b" * random.randint(10, 500)
            request_body["messages"][0]["content"][0]["text"] = prompt + "\n\nAssistant: " + retry_zws

        try:
            access_token = await get_valid_access_token(current_token, force_refresh=force_fresh)
            active_access_token = access_token
        except Exception as e:
            if attempt == MAX_RETRIES - 1:
                raise RuntimeError(f"GLM Auth Error: {str(e)}")
            acc_idx += 1
            await asyncio.sleep(0.5)
            continue

        t, n, s = build_sign()
        stream_headers = {
            "Accept": "text/event-stream",
            "Accept-Encoding": "identity",  # Keep uncompressed for clean incremental SSE
            "App-Name": "chatglm",
            "Origin": "https://chatglm.cn",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "X-App-Fr": "browser_extension",
            "X-App-Platform": "pc",
            "X-App-Version": "0.0.1",
            "Authorization": f"Bearer {access_token}",
            "X-Device-Id": uuid.uuid4().hex,
            "X-Nonce": n,
            "X-Request-Id": uuid.uuid4().hex,
            "X-Sign": s,
            "X-Timestamp": t,
        }

        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                async with client.stream("POST", stream_url, headers=stream_headers, json=request_body) as response:
                    # Catch 429 busy error ("请等待其他对话生成完毕")
                    if response.status_code == 429:
                        if attempt < MAX_RETRIES - 1:
                            async with _TOKEN_LOCK:
                                _TOKEN_CACHE.pop("__guest__", None)
                            acc_idx += 1
                            await asyncio.sleep(0.5 * (attempt + 1))
                            continue
                        raise RuntimeError("GLM Server Busy (429): Other conversation generating.")

                    if response.status_code in (401, 403):
                        if attempt < MAX_RETRIES - 1:
                            acc_idx += 1
                            continue
                        raise RuntimeError(f"GLM Authorization Error (HTTP {response.status_code})")

                    if response.status_code != 200:
                        err_msg = await response.aread()
                        raise RuntimeError(f"GLM Upstream HTTP {response.status_code}: {err_msg.decode('utf-8', errors='ignore')[:200]}")

                    hit_busy_event = False
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

                        # Check for inline busy error status 10061
                        if data.get("status") == 10061 or "请等待其他对话生成完毕" in str(data.get("message", "")):
                            hit_busy_event = True
                            break

                        if not conversation_id and data.get("conversation_id"):
                            conversation_id = str(data["conversation_id"])

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

                        parts = data.get("parts", [])
                        for p in parts:
                            lid = p.get("logic_id", "default")
                            p_status = p.get("status")

                            for c in p.get("content", []):
                                c_type = c.get("type")
                                c_text = c.get("text", "")
                                if not c_text:
                                    continue

                                # Text Content Processing (Monotonic Clean Slicing)
                                if c_type == "text":
                                    if p_status == "init":
                                        accumulated_text[lid] = accumulated_text.get(lid, "") + c_text
                                        yield {
                                            "id": chat_id,
                                            "object": "chat.completion.chunk",
                                            "created": created_ts,
                                            "model": model,
                                            "choices": [{"index": 0, "delta": {"content": c_text}, "finish_reason": None}],
                                        }
                                    elif p_status == "finish":
                                        cur = accumulated_text.get(lid, "")
                                        if len(c_text) > len(cur):
                                            delta = c_text[len(cur):]
                                            accumulated_text[lid] = c_text
                                            yield {
                                                "id": chat_id,
                                                "object": "chat.completion.chunk",
                                                "created": created_ts,
                                                "model": model,
                                                "choices": [{"index": 0, "delta": {"content": delta}, "finish_reason": None}],
                                            }

                                # Reasoning / Thinking Processing
                                elif c_type == "think":
                                    if p_status == "init":
                                        accumulated_think[lid] = accumulated_think.get(lid, "") + c_text
                                        yield {
                                            "id": chat_id,
                                            "object": "chat.completion.chunk",
                                            "created": created_ts,
                                            "model": model,
                                            "choices": [{"index": 0, "delta": {"reasoning_content": c_text}, "finish_reason": None}],
                                        }
                                    elif p_status == "finish":
                                        cur = accumulated_think.get(lid, "")
                                        if len(c_text) > len(cur):
                                            delta = c_text[len(cur):]
                                            accumulated_think[lid] = c_text
                                            yield {
                                                "id": chat_id,
                                                "object": "chat.completion.chunk",
                                                "created": created_ts,
                                                "model": model,
                                                "choices": [{"index": 0, "delta": {"reasoning_content": delta}, "finish_reason": None}],
                                            }

                    if hit_busy_event and attempt < MAX_RETRIES - 1:
                        async with _TOKEN_LOCK:
                            _TOKEN_CACHE.pop("__guest__", None)
                        acc_idx += 1
                        await asyncio.sleep(0.5 * (attempt + 1))
                        continue

            if started_streaming:
                break

        except Exception as exc:
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(0.5 * (attempt + 1))
                continue
            raise
        finally:
            if conversation_id and active_access_token:
                asyncio.create_task(_delete_conversation(conversation_id, assistant_id, active_access_token))

    # Final stop chunk
    yield {
        "id": chat_id,
        "object": "chat.completion.chunk",
        "created": created_ts,
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
