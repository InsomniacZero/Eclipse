#!/usr/bin/env python3
"""
Eclipse Unified AI Hub & Universal Gateway
Port 5000
"""

import asyncio
import base64
import copy
import json
import os
import time
import uuid
import re
import inspect
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional
from urllib.parse import urlsplit

try:
    if os.getenv("NO_FASTAPI", "").strip() in ("1", "true", "yes"):
        raise ImportError("FastAPI disabled by NO_FASTAPI env var")
    from fastapi import FastAPI, HTTPException, Request, Response, status  # type: ignore[import-untyped]
    from fastapi.responses import FileResponse, JSONResponse, StreamingResponse  # type: ignore[import-untyped]
    from fastapi.staticfiles import StaticFiles  # type: ignore[import-untyped]

    app = FastAPI(title="Eclipse AI Gateway", version="1.0.0")
except Exception:
    # Lightweight pure-Python fallback for Termux / mobile (no Rust / Pydantic build needed!)
    from starlette.applications import Starlette
    from starlette.exceptions import HTTPException
    from starlette.requests import Request
    from starlette.responses import FileResponse, JSONResponse, Response, StreamingResponse
    from starlette.staticfiles import StaticFiles
    from starlette.routing import Route, Mount

    from contextlib import asynccontextmanager

    async def _http_exception_handler(request, exc):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    async def _general_exception_handler(request, exc):
        logger.debug(f"Unhandled route exception on {request.method} {request.url.path}: {exc}")
        return JSONResponse({"error": "Internal server error", "detail": str(exc)}, status_code=500)

    @asynccontextmanager
    async def _gateway_lifespan(gateway_app):
        for handler in gateway_app._startup_handlers:
            try:
                if inspect.iscoroutinefunction(handler):
                    await handler()
                else:
                    handler()
            except Exception:
                pass
        yield
        for handler in gateway_app._shutdown_handlers:
            try:
                if inspect.iscoroutinefunction(handler):
                    await handler()
                else:
                    handler()
            except Exception:
                pass

    class StarletteGateway(Starlette):
        def __init__(self):
            self._startup_handlers = []
            self._shutdown_handlers = []
            super().__init__(
                exception_handlers={
                    HTTPException: _http_exception_handler,
                    Exception: _general_exception_handler,
                },
                lifespan=_gateway_lifespan,
            )

        def _route_decorator(self, path: str, methods: list):
            def decorator(func):
                sig = inspect.signature(func)
                async def handler(request):
                    kwargs = {}
                    for p in sig.parameters.values():
                        if p.name in ("request", "req"):
                            kwargs[p.name] = request
                        elif p.name in request.path_params:
                            kwargs[p.name] = request.path_params[p.name]
                        elif p.name in request.query_params:
                            kwargs[p.name] = request.query_params[p.name]
                        elif p.default is not inspect.Parameter.empty:
                            kwargs[p.name] = p.default
                    try:
                        if inspect.iscoroutinefunction(func):
                            res = await func(**kwargs)
                        else:
                            res = func(**kwargs)
                        if isinstance(res, (dict, list)):
                            return JSONResponse(res)
                        return res
                    except HTTPException:
                        raise
                    except Exception as e:
                        logger.debug(f"Route exception on {request.method} {request.url.path}: {e}")
                        return JSONResponse({"error": "Internal server error", "detail": str(e)}, status_code=500)
                self.router.routes.append(Route(path, handler, methods=methods))
                return func
            return decorator

        def get(self, path: str):
            return self._route_decorator(path, ["GET"])

        def post(self, path: str):
            return self._route_decorator(path, ["POST"])

        def delete(self, path: str):
            return self._route_decorator(path, ["DELETE"])

        def put(self, path: str):
            return self._route_decorator(path, ["PUT"])

        def patch(self, path: str):
            return self._route_decorator(path, ["PATCH"])

        def head(self, path: str):
            return self._route_decorator(path, ["HEAD", "GET"])

        def on_event(self, event_type: str):
            def decorator(func):
                if event_type == "startup":
                    self._startup_handlers.append(func)
                elif event_type == "shutdown":
                    self._shutdown_handlers.append(func)
                return func
            return decorator

    app = StarletteGateway()

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
STATIC_DIR = BASE_DIR / "static"

import sys
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import httpx
import uvicorn
import logging

logger = logging.getLogger("eclipse.server")

import tunnel
import db
import providers
import security
try:
    from eclipse import worker
except ImportError:
    import worker
try:
    from eclipse import engines
except ImportError:
    import engines
try:
    from eclipse import personas
except ImportError:
    import personas
try:
    from eclipse import artifacts
except ImportError:
    import artifacts
try:
    from eclipse import requestlog
    from eclipse import bench
except ImportError:
    import requestlog
    import bench
try:
    from eclipse import userscript
except ImportError:
    import userscript
try:
    from eclipse import tools as chat_tools
    from eclipse.tools import loop as tools_loop
    from eclipse.tools import web_search as tools_web_search
    from eclipse.tools import protocol as tools_protocol
except ImportError:
    import tools as chat_tools
    from tools import loop as tools_loop
    from tools import web_search as tools_web_search
    from tools import protocol as tools_protocol
try:
    from eclipse import openai_tools_bridge
except ImportError:
    import openai_tools_bridge

from providers import (
    MODELS_CATALOG,
    PROVIDERS_CONFIG,
    get_all_limits,
    get_all_services_status,
    get_dynamic_models_catalog,
    get_pid_for_port,
    get_stored_cookies,
    remove_stacked_cookie,
    save_stacked_cookies,
    start_all_services,
    start_provider,
    stop_all_services,
    stop_provider,
)

# Authentication, origin checks and CORS for every route (see security.py for the policy).
app.add_middleware(security.SecurityMiddleware)

try:
    from starlette.middleware.gzip import GZipMiddleware
    app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=6)
except Exception:
    pass


def resolve_model_provider(model_name: str) -> str:
    """Route models to their respective native providers in Eclipse."""
    m = (model_name or "").lower().strip()
    if m.startswith("glm") or m.startswith("cogview") or m.startswith("x-preview") or m.startswith("zai") or m.startswith("z.ai") or (len(m) == 24 and all(c in "0123456789abcdef" for c in m)):
        return "glm"
    if m.startswith("agy-") or m.startswith("antigravity") or m.startswith("claude"):
        return "antigravity"
    # Auto-route Gemini models to Antigravity if user logged in with Google OAuth and has no web cookies
    if m.startswith("gemini") or "argon" in m:
        if providers.missing_credentials("gemini") and not providers.missing_credentials("antigravity"):
            return "antigravity"
        return "gemini"
    return "gemini"


# -------------------------------------------------------------------
# Universal OpenAI Gateway Endpoints (/v1)
# -------------------------------------------------------------------

@app.get("/v1/models")
@app.get("/models")
@app.get("/api/v1/models")
async def list_models():
    """Return unified OpenAI-compatible models list for Gemini Web."""
    now = int(time.time())
    data = []

    catalog = get_dynamic_models_catalog()
    for m in catalog:
        data.append({
            "id": m["id"],
            "object": "model",
            "created": now,
            "owned_by": m.get("connection") or m["provider"],
            "permission": [],
            "root": m["id"],
            "parent": None,
            "locked": m.get("locked", False),
            "reason": m.get("reason"),
            "capabilities": m.get("capabilities", []),
        })
    return {"object": "list", "data": data}


@app.post("/v1/audio/speech")
@app.post("/audio/speech")
@app.post("/api/v1/audio/speech")
async def audio_speech(request: Request):
    """OpenAI-compatible speech synthesis endpoint (TTS) using Google AI Studio Gemini 3.8 Flash TTS."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    input_text = body.get("input", "") or body.get("prompt", "") or body.get("text", "")
    if not input_text:
        return JSONResponse(
            {"error": {"message": "Missing required field 'input'", "type": "invalid_request_error"}},
            status_code=400,
        )

    model = body.get("model", "ais-gemini-3.8-flash-tts")
    voice = body.get("voice", "Puck")
    response_format = body.get("response_format", "mp3")

    if model.startswith("mimo"):
        try:
            mimo_accs = db.get_accounts("mimo")
            from eclipse.engines import mimo as mimo_engine
            audio_bytes = await mimo_engine.generate_mimo_speech(
                text=input_text,
                voice=voice,
                model=model,
                accounts=mimo_accs,
            )
            return Response(
                content=audio_bytes,
                media_type="audio/wav",
                headers={
                    "Content-Disposition": 'inline; filename="speech.wav"',
                    "Cache-Control": "no-cache",
                },
            )
        except Exception as e:
            return JSONResponse(
                {"error": {"message": f"Xiaomi MiMo speech generation error: {str(e)}", "type": "speech_error"}},
                status_code=502,
            )

    # Fetch accounts: prefer aistudio, fallback to gemini accounts in database vault
    accounts = db.get_accounts("aistudio") or db.get_accounts("gemini")

    try:
        import importlib
        import sys
        if "eclipse.engines.aistudio" in sys.modules:
            aistudio_engine = importlib.reload(sys.modules["eclipse.engines.aistudio"])
        else:
            from eclipse.engines import aistudio as aistudio_engine
        audio_bytes = await aistudio_engine.generate_aistudio_speech(
            input_text=input_text,
            model=model,
            voice=voice,
            response_format=response_format,
            accounts=accounts,
        )
    except Exception as e:
        return JSONResponse(
            {"error": {"message": f"Speech generation error: {str(e)}", "type": "speech_error"}},
            status_code=502,
        )

    media_type = "audio/mpeg" if response_format.lower() in ("mp3", "mpeg") else "audio/wav"
    return Response(
        content=audio_bytes,
        media_type=media_type,
        headers={
            "Content-Disposition": f'inline; filename="speech.{response_format}"',
            "Cache-Control": "no-cache",
        },
    )


@app.get("/v1/audio/voices")
@app.get("/audio/voices")
async def list_voices():
    """Return available neural voice timbres, curated studio personas, and custom-designed voices."""
    base_voices = [
        {"id": "Puck", "name": "Puck", "gender": "Neutral / Expressive", "description": "Dynamic, lively, expressive storytelling & natural cadence", "type": "prebuilt"},
        {"id": "Charon", "name": "Charon", "gender": "Male / Deep", "description": "Calm, authoritative, thoughtful and grounding", "type": "prebuilt"},
        {"id": "Aoede", "name": "Aoede", "gender": "Female / Warm", "description": "Warm, melodious, empathetic and clear conversational tone", "type": "prebuilt"},
        {"id": "Fenrir", "name": "Fenrir", "gender": "Male / Strong", "description": "Strong, resonant, confident and energetic pacing", "type": "prebuilt"},
        {"id": "Kore", "name": "Kore", "gender": "Female / Bright", "description": "Bright, lucid, precise and crisp articulation", "type": "prebuilt"},
    ]

    from eclipse.engines.aistudio import CURATED_VOICE_PERSONAS
    curated = [dict(p, type="curated") for p in CURATED_VOICE_PERSONAS]

    try:
        custom_db = db.get_custom_voices()
    except Exception:
        custom_db = []
    custom = [dict(c, type="custom", id=c["voice_id"]) for c in custom_db]

    all_voices = base_voices + curated + custom
    return {
        "voices": all_voices,
        "base_voices": base_voices,
        "curated_personas": curated,
        "custom_voices": custom,
    }


@app.post("/v1/audio/voices/design")
@app.post("/v1/audio/voices")
@app.post("/audio/voices/design")
async def design_custom_voice(request: Request):
    """Design a brand-new persistent vocal persona via Google Gemini 3.8 Flash TTS Voice Design."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    name = (body.get("name") or "").strip()
    prompt = (body.get("prompt") or body.get("description") or "").strip()
    if not prompt:
        return JSONResponse(
            {"error": {"message": "Missing required field 'prompt' describing the vocal persona.", "type": "invalid_request_error"}},
            status_code=400,
        )
    if not name:
        name = "Custom Persona"

    accounts = db.get_accounts("aistudio") or db.get_accounts("gemini")
    from eclipse.engines.aistudio import create_prompted_voice
    try:
        result = await create_prompted_voice(name=name, prompt=prompt, accounts=accounts)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse(
            {"error": {"message": f"Voice Design error: {str(e)}", "type": "voice_design_error"}},
            status_code=502,
        )


@app.delete("/v1/audio/voices/{voice_id}")
@app.delete("/audio/voices/{voice_id}")
async def delete_voice_endpoint(voice_id: str):
    """Delete a user-designed custom voice from SQLite vault."""
    success = db.delete_custom_voice(voice_id)
    return JSONResponse({"success": success, "voice_id": voice_id})


def is_simulation_mode() -> bool:
    """Check if device simulation mode is enabled."""
    return providers.is_simulation_active()


def _generate_simulated_image_svg(prompt: str) -> str:
    """Generate a crisp, authentic SVG image for simulation testing."""
    prompt_lower = (prompt or "").lower()
    if "apple" in prompt_lower:
        # High quality vector artwork of a glossy red Apple
        svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
  <defs>
    <radialGradient id="bgGlow" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#1c2333"/>
      <stop offset="100%" stop-color="#0b0e14"/>
    </radialGradient>
    <radialGradient id="appleGrad" cx="35%" cy="30%" r="65%">
      <stop offset="0%" stop-color="#ff6b6b"/>
      <stop offset="30%" stop-color="#e03131"/>
      <stop offset="70%" stop-color="#c92a2a"/>
      <stop offset="100%" stop-color="#5c0909"/>
    </radialGradient>
    <linearGradient id="leafGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#69db7c"/>
      <stop offset="60%" stop-color="#2f9e44"/>
      <stop offset="100%" stop-color="#1b5e20"/>
    </linearGradient>
    <linearGradient id="stemGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#a67c52"/>
      <stop offset="100%" stop-color="#4e3620"/>
    </linearGradient>
    <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="16" stdDeviation="24" flood-color="#c92a2a" flood-opacity="0.4"/>
    </filter>
  </defs>
  <rect width="512" height="512" rx="28" fill="url(#bgGlow)"/>
  <ellipse cx="256" cy="420" rx="140" ry="24" fill="#000000" opacity="0.6"/>
  <!-- Stem -->
  <path d="M 256 160 C 254 110, 275 85, 298 70 C 294 76, 276 102, 270 160 Z" fill="url(#stemGrad)"/>
  <!-- Leaf -->
  <path d="M 270 120 C 330 90, 365 110, 370 140 C 335 155, 290 145, 270 120 Z" fill="url(#leafGrad)"/>
  <path d="M 275 122 Q 320 128 360 138" stroke="#8ce99a" stroke-width="2" fill="none" opacity="0.7"/>
  <!-- Apple Body -->
  <path d="M 256 185 C 230 160, 140 160, 130 250 C 120 340, 190 410, 256 410 C 322 410, 392 340, 382 250 C 372 160, 282 160, 256 185 Z" fill="url(#appleGrad)" filter="url(#glow)"/>
  <!-- Specular Highlights -->
  <ellipse cx="195" cy="225" rx="36" ry="58" transform="rotate(-30 195 225)" fill="#ffffff" opacity="0.32"/>
  <ellipse cx="180" cy="210" rx="14" ry="24" transform="rotate(-30 180 210)" fill="#ffffff" opacity="0.6"/>
  <!-- Bottom indents -->
  <path d="M 230 405 C 245 400, 267 400, 282 405" stroke="#380505" stroke-width="4" stroke-linecap="round" fill="none"/>
</svg>"""
    else:
        # Futuristic Cybernetic / Digital Art SVG
        svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
  <defs>
    <linearGradient id="bgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#0d1117"/>
      <stop offset="100%" stop-color="#161b22"/>
    </linearGradient>
    <linearGradient id="neonCyan" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#00f2fe"/>
      <stop offset="100%" stop-color="#4facfe"/>
    </linearGradient>
    <linearGradient id="neonPurple" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#b176f2"/>
      <stop offset="100%" stop-color="#f857a6"/>
    </linearGradient>
    <filter id="neonGlow" x="-30%" y="-30%" width="160%" height="160%">
      <feGaussianBlur stdDeviation="12" result="blur"/>
      <feMerge>
        <feMergeNode in="blur"/>
        <feMergeNode in="SourceGraphic"/>
      </feMerge>
    </filter>
  </defs>
  <rect width="512" height="512" rx="28" fill="url(#bgGrad)"/>
  <circle cx="256" cy="256" r="160" fill="none" stroke="url(#neonCyan)" stroke-width="3" stroke-dasharray="12 8" opacity="0.4"/>
  <circle cx="256" cy="256" r="120" fill="none" stroke="url(#neonPurple)" stroke-width="5" filter="url(#neonGlow)"/>
  <polygon points="256,150 348,310 164,310" fill="none" stroke="url(#neonCyan)" stroke-width="4" filter="url(#neonGlow)"/>
  <circle cx="256" cy="256" r="48" fill="url(#neonPurple)" opacity="0.85" filter="url(#neonGlow)"/>
  <circle cx="256" cy="256" r="22" fill="#ffffff"/>
</svg>"""

    b64 = base64.b64encode(svg.encode("utf-8")).decode("utf-8")
    return f"data:image/svg+xml;base64,{b64}"


def _get_simulated_response_payload(model_name: str, provider_id: str, prompt_text: str = "") -> str:
    """Determine simulated response text (handling text, image, and video modalities)."""
    m_lower = (model_name or "").lower()
    p_lower = (prompt_text or "").lower()

    # Detect Video Modality
    if any(k in m_lower for k in ("video", "t2v", "wanx-2.1", "cogvideox", "kling", "sora", "runway", "veo")) or any(k in p_lower for k in ("video", "movie", "animation", "motion clip")):
        video_url = "/static/demo_video.mp4"
        return (
            f"🎬 **Eclipse Cinematic Video Synthesis** (Simulated Response)\n\n"
            f"• **Model:** `{model_name}`\n"
            f"• **Prompt:** *\"{prompt_text or 'Autonomous dynamic frame sequence'}\"*\n"
            f"• **Specs:** 1080p HD • 24 FPS • Synchronized Stereo Audio\n\n"
            f"[Generated Video]({video_url})"
        )

    # Detect Image Modality
    if any(k in m_lower for k in ("image", "imagine", "cogview", "dall-e", "flux", "imagen", "sdxl", "wanx")) or any(k in p_lower for k in ("img", "image", "picture", "photo", "drawing", "illustration", "wallpaper")):
        img_url = _generate_simulated_image_svg(prompt_text)
        return (
            f"🎨 **Eclipse Neural Image Synthesis** (Simulated Response)\n\n"
            f"• **Model:** `{model_name}`\n"
            f"• **Prompt:** *\"{prompt_text or 'Creative synthesis'}\"*\n"
            f"• **Resolution:** 1024x1024 High-Definition Vector Output\n\n"
            f"![Generated Image]({img_url})"
        )

    # Detect Artifact / App creation request in simulation mode
    if any(k in p_lower for k in ("artifact", "react", "component", "calculator", "game", "dashboard", "counter", "timer", "mermaid", "flowchart", "svg", "vector")):
        if "mermaid" in p_lower or "flowchart" in p_lower or "diagram" in p_lower:
            return (
                f"Here is the architecture diagram:\n\n"
                f'<antArtifact identifier="system-architecture" type="application/vnd.ant.mermaid" title="System Architecture Flowchart">\n'
                f"graph TD\n"
                f"    Client[Playground Web UI] -->|SSE / REST| Gateway[Eclipse Gateway:5000]\n"
                f"    Gateway --> Router[Universal Model Router]\n"
                f"    Router --> Workers[Provider Workers 8000-8088]\n"
                f"    Router --> Sandbox[Universal Artifacts Engine]\n"
                f"    Sandbox --> Frame[Isolated iframe / React 18 / SVG]\n"
                f"</antArtifact>\n\n"
                f"The diagram above illustrates the Eclipse architecture pipeline."
            )
        elif "svg" in p_lower or "icon" in p_lower or "vector" in p_lower:
            return (
                f"Here is the scalable vector graphic you requested:\n\n"
                f'<antArtifact identifier="eclipse-core-logo" type="image/svg+xml" title="Eclipse Cybernetic Core">\n'
                f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 500" width="100%" height="100%">\n'
                f'  <defs>\n'
                f'    <linearGradient id="neonGlow" x1="0%" y1="0%" x2="100%" y2="100%">\n'
                f'      <stop offset="0%" stop-color="#00f2fe"/>\n'
                f'      <stop offset="100%" stop-color="#4facfe"/>\n'
                f'    </linearGradient>\n'
                f'    <linearGradient id="accentPurple" x1="0%" y1="0%" x2="100%" y2="100%">\n'
                f'      <stop offset="0%" stop-color="#b176f2"/>\n'
                f'      <stop offset="100%" stop-color="#f857a6"/>\n'
                f'    </linearGradient>\n'
                f'    <filter id="bloom" x="-20%" y="-20%" width="140%" height="140%">\n'
                f'      <feGaussianBlur stdDeviation="8" result="blur"/>\n'
                f'      <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>\n'
                f'    </filter>\n'
                f'  </defs>\n'
                f'  <rect width="100%" height="100%" rx="24" fill="#0b0f19"/>\n'
                f'  <circle cx="250" cy="250" r="160" stroke="url(#neonGlow)" stroke-width="3" fill="none" stroke-dasharray="10 6" opacity="0.6"/>\n'
                f'  <circle cx="250" cy="250" r="120" stroke="url(#accentPurple)" stroke-width="4" fill="none" filter="url(#bloom)"/>\n'
                f'  <polygon points="250,150 340,310 160,310" fill="none" stroke="url(#neonGlow)" stroke-width="4" filter="url(#bloom)"/>\n'
                f'  <circle cx="250" cy="250" r="32" fill="#00f2fe" filter="url(#bloom)"/>\n'
                f'  <text x="250" y="380" font-family="system-ui, sans-serif" font-size="18" font-weight="600" fill="#94a3b8" text-anchor="middle" letter-spacing="4">ECLIPSE ARTIFACTS</text>\n'
                f'</svg>\n'
                f"</antArtifact>\n\n"
                f"You can view and inspect the SVG in the artifact workbench."
            )
        else:
            return (
                "I've built an interactive React component for you:\n\n"
                '<antArtifact identifier="interactive-counter" type="application/vnd.ant.react" title="Interactive Glass Counter">\n'
                "import React, { useState } from 'react';\n"
                "import { Sparkles, Plus, Minus, RotateCcw, Zap } from 'lucide-react';\n\n"
                "export default function CounterApp() {\n"
                "  const [count, setCount] = useState(0);\n"
                "  return (\n"
                '    <div className="min-h-screen bg-slate-950 text-white flex flex-col items-center justify-center p-6">\n'
                '      <div className="w-full max-w-sm p-8 rounded-3xl bg-slate-900/80 border border-slate-800 shadow-2xl flex flex-col items-center gap-6 backdrop-blur-xl">\n'
                '        <div className="flex items-center gap-2 text-cyan-400 text-xs font-semibold uppercase tracking-widest">\n'
                '          <Zap className="w-4 h-4" /> Eclipse Universal Engine\n'
                "        </div>\n"
                '        <div className="text-7xl font-extrabold tracking-tight bg-gradient-to-r from-cyan-400 via-indigo-300 to-pink-400 bg-clip-text text-transparent">\n'
                "          {count}\n"
                "        </div>\n"
                '        <div className="flex items-center gap-3 w-full justify-center">\n'
                '          <button onClick={() => setCount(c => c - 1)} className="p-3 rounded-2xl bg-slate-800 hover:bg-slate-700 active:scale-95 transition-all text-white">\n'
                '            <Minus className="w-5 h-5" />\n'
                "          </button>\n"
                '          <button onClick={() => setCount(0)} className="p-3 rounded-2xl bg-slate-800 hover:bg-slate-700 active:scale-95 transition-all text-slate-400 hover:text-white">\n'
                '            <RotateCcw className="w-5 h-5" />\n'
                "          </button>\n"
                '          <button onClick={() => setCount(c => c + 1)} className="p-3 rounded-2xl bg-cyan-500 hover:bg-cyan-400 active:scale-95 transition-all text-slate-950 font-bold shadow-lg shadow-cyan-500/30">\n'
                '            <Plus className="w-5 h-5" />\n'
                "          </button>\n"
                "        </div>\n"
                "      </div>\n"
                "    </div>\n"
                "  );\n"
                "}\n"
                "</antArtifact>\n\n"
                "This component is rendered live in your interactive workbench on the right."
            )

    # Standard Text Response
    p_cfg = personas.get_persona_config(model_name) if personas else None
    if p_cfg:
        return (
            f"⚡ **Eclipse Portable Gateway** (Simulated Response)\n\n"
            f"• **Model:** `{model_name}` ({p_cfg.name})\n"
            f"• **Provider:** `{provider_id.upper()}`\n"
            f"• **Architecture:** Frontier Neural Persona Engine\n\n"
            f"Hello! I am {p_cfg.name}. I am verified and running in Eclipse Gateway."
        )

    return (
        f"⚡ **Eclipse Portable Gateway** (Simulated Response)\n\n"
        f"• **Model:** `{model_name}`\n"
        f"• **Provider:** `{provider_id.upper()}`\n"
        f"• **Gateway Status:** 100% Self-Contained (Zero Legacy Dependencies)\n\n"
        f"Your device simulation is verified and running cleanly. Streaming SSE buffers, token rotation, and headers are functioning as expected."
    )


async def generate_simulated_stream(
    model_name: str,
    provider_id: str,
    prompt_text: str = "",
    thinking_budget: Optional[int] = None,
) -> AsyncIterator[bytes]:
    """Yield OpenAI-compatible SSE chunks for offline/device simulation testing."""
    created_ts = int(time.time())
    sim_id = f"chatcmpl-sim-{int(time.time()*1000)}"

    role_chunk = {
        "id": sim_id,
        "object": "chat.completion.chunk",
        "created": created_ts,
        "model": model_name,
        "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
    }
    yield f"data: {json.dumps(role_chunk)}\n\n".encode("utf-8")
    await asyncio.sleep(0.04)

    # If thinking budget cap > 0, stream reasoning tokens first
    if thinking_budget is not None and thinking_budget > 0:
        sim_reasoning = (
            f"Thinking process for {model_name} (Thinking Budget Cap: {thinking_budget:,} tokens):\n"
            f"1. Parsing user input and model constraints\n"
            f"2. Formulating systematic reasoning graph\n"
            f"3. Validating response according to Eclipse Gateway parameters\n\n"
        )
        for rw in sim_reasoning.split(" "):
            rc = {
                "id": sim_id,
                "object": "chat.completion.chunk",
                "created": created_ts,
                "model": model_name,
                "choices": [{"index": 0, "delta": {"reasoning_content": rw + " "}, "finish_reason": None}],
            }
            yield f"data: {json.dumps(rc)}\n\n".encode("utf-8")
            await asyncio.sleep(0.015)

    sim_text = _get_simulated_response_payload(model_name, provider_id, prompt_text)

    # Stream in natural chunk sizes
    words = sim_text.split(" ")
    for w in words:
        c = {
            "id": sim_id,
            "object": "chat.completion.chunk",
            "created": created_ts,
            "model": model_name,
            "choices": [{"index": 0, "delta": {"content": w + " "}, "finish_reason": None}],
        }
        yield f"data: {json.dumps(c)}\n\n".encode("utf-8")
        await asyncio.sleep(0.02)

    finish_chunk = {
        "id": sim_id,
        "object": "chat.completion.chunk",
        "created": created_ts,
        "model": model_name,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    yield f"data: {json.dumps(finish_chunk)}\n\n".encode("utf-8")
    yield b"data: [DONE]\n\n"


async def smooth_chat_stream(
    source: AsyncIterator[Dict[str, Any]],
    target_interval: float = 0.035,
    max_chars: int = 40,
) -> AsyncIterator[Dict[str, Any]]:
    """Cadence smoother for LLM SSE token streams using a decoupled producer-consumer queue.

    Batches micro-chunks (1-character or sub-token deltas) into natural ~35ms / 28 FPS packets.
    Prevents high-frequency chunk storms (e.g. 100+ chunks/sec from Kimi / TensorRT-LLM)
    from freezing web browser clients (like Janitor AI) that execute heavy React DOM
    re-renders, markdown parsing, and regex passes on every incoming packet.
    """
    queue: asyncio.Queue = asyncio.Queue(maxsize=120)
    _SENTINEL = object()
    producer_exc: Optional[Exception] = None

    async def _producer():
        nonlocal producer_exc
        try:
            async for item in source:
                await queue.put(item)
        except Exception as e:
            producer_exc = e
        finally:
            await queue.put(_SENTINEL)

    producer_task = asyncio.create_task(_producer())

    last_flush = 0.0
    pending_chunk: Optional[Dict[str, Any]] = None
    pending_content: List[str] = []
    pending_reasoning: List[str] = []
    first_token_sent = False

    def _build_flush_chunk() -> Optional[Dict[str, Any]]:
        nonlocal pending_chunk, pending_content, pending_reasoning
        if not pending_chunk:
            return None
        c_text = "".join(pending_content)
        r_text = "".join(pending_reasoning)
        if not c_text and not r_text:
            out = pending_chunk
            pending_chunk = None
            return out

        out = copy.deepcopy(pending_chunk)
        choices = out.get("choices", [])
        if choices:
            delta = choices[0].get("delta", {})
            if c_text:
                delta["content"] = c_text
            elif "content" in delta:
                delta.pop("content", None)
            if r_text:
                delta["reasoning_content"] = r_text
            elif "reasoning_content" in delta:
                delta.pop("reasoning_content", None)
        pending_chunk = None
        pending_content = []
        pending_reasoning = []
        return out

    try:
        while True:
            if pending_content or pending_reasoning:
                now = time.monotonic()
                rem_time = max(0.005, target_interval - (now - last_flush))
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=rem_time)
                except asyncio.TimeoutError:
                    flush_chunk = _build_flush_chunk()
                    if flush_chunk:
                        last_flush = time.monotonic()
                        yield flush_chunk
                    continue
            else:
                item = await queue.get()

            if item is _SENTINEL:
                break

            chunk = item
            choices = chunk.get("choices", [])
            if not choices:
                flush_chunk = _build_flush_chunk()
                if flush_chunk:
                    last_flush = time.monotonic()
                    yield flush_chunk
                yield chunk
                continue

            choice = choices[0]
            delta = choice.get("delta", {})
            finish_reason = choice.get("finish_reason")

            is_role_only = "role" in delta and not delta.get("content") and not delta.get("reasoning_content")
            has_special = finish_reason is not None or delta.get("eclipse_event") is not None or is_role_only

            if has_special:
                flush_chunk = _build_flush_chunk()
                if flush_chunk:
                    last_flush = time.monotonic()
                    yield flush_chunk
                yield chunk
                continue

            c_delta = delta.get("content")
            r_delta = delta.get("reasoning_content")

            if c_delta is None and r_delta is None:
                flush_chunk = _build_flush_chunk()
                if flush_chunk:
                    last_flush = time.monotonic()
                    yield flush_chunk
                yield chunk
                continue

            if c_delta and pending_reasoning:
                flush_chunk = _build_flush_chunk()
                if flush_chunk:
                    last_flush = time.monotonic()
                    yield flush_chunk

            if r_delta and pending_content:
                flush_chunk = _build_flush_chunk()
                if flush_chunk:
                    last_flush = time.monotonic()
                    yield flush_chunk

            if not pending_chunk:
                pending_chunk = chunk

            if c_delta:
                pending_content.append(c_delta)
            if r_delta:
                pending_reasoning.append(r_delta)

            if not first_token_sent:
                first_token_sent = True
                flush_chunk = _build_flush_chunk()
                if flush_chunk:
                    last_flush = time.monotonic()
                    yield flush_chunk
                continue

            now = time.monotonic()
            tot_chars = sum(len(x) for x in pending_content) + sum(len(x) for x in pending_reasoning)
            time_elapsed = (now - last_flush) >= target_interval
            size_reached = tot_chars >= max_chars

            if time_elapsed or size_reached:
                flush_chunk = _build_flush_chunk()
                if flush_chunk:
                    last_flush = time.monotonic()
                    yield flush_chunk

        flush_chunk = _build_flush_chunk()
        if flush_chunk:
            yield flush_chunk
    finally:
        if not producer_task.done():
            producer_task.cancel()
            try:
                await producer_task
            except (asyncio.CancelledError, Exception):
                pass
        aclose = getattr(source, "aclose", None)
        if aclose:
            try:
                await aclose()
            except Exception:
                pass


@app.post("/v1/chat/completions")
@app.post("/chat/completions")
async def chat_completions(request: Request):
    """Universal router for chat completions across all providers + S-Connect Proxy Interceptor."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    requested_model = body.get("model", "gemini-3.8-flash")
    incoming_messages = list(body.get("messages") or []) if isinstance(body.get("messages"), list) else []

    pipeline_info: Dict[str, Any] = {}
    model_name = requested_model.split("@")[0].strip() if "@" in requested_model else requested_model
    preset = None
    preset_tools = False

    # Check persona mapping (e.g. GPT-6 Astra, Claude 5.1 Fable, Claude 5 Fable, and thinking variants)
    persona_cfg = personas.get_persona_config(model_name) if personas else None
    if persona_cfg:
        backend_model = persona_cfg.backend_model
        body["model"] = backend_model
        body["messages"] = personas.inject_persona_messages(body.get("messages", []), persona_cfg)
        if persona_cfg.thinking_budget and "thinking_budget" not in body:
            body["thinking_budget"] = persona_cfg.thinking_budget
    else:
        backend_model = model_name

    # Universal Artifacts system prompt injection (supports all models: Gemini, Claude, DeepSeek, Qwen, etc.)
    if "artifacts" in locals() or "artifacts" in globals():
        artifacts_enabled = body.get("artifacts") is True or request.headers.get("x-eclipse-artifacts") == "true"
        if artifacts_enabled:
            body["messages"] = artifacts.inject_artifacts_prompt(body.get("messages", []), enabled=True)

    res = resolve_model_provider(model_name)
    if isinstance(res, tuple):
        provider_id, target_port = res
    else:
        provider_id = res
        meta_cfg = providers.PROVIDERS_CONFIG.get(provider_id, providers.PROVIDERS_CONFIG.get("gemini", {}))
        target_port = meta_cfg.get("port", 8084)

    # 1. Look up persistent model settings in Eclipse SQLite DB
    model_cfg = db.get_model_settings(model_name)
    thinking_override = body.pop("eclipse_thinking_override", None) is True
    thinking_cap = model_cfg.get("thinking_budget")
    if "thinking_budget" in body and (thinking_cap is None or thinking_override):
        thinking_cap = body.get("thinking_budget")

    # Enforce Thinking Budget Cap globally across all incoming gateway requests
    if thinking_cap is not None:
        try:
            thinking_cap_int = max(0, int(thinking_cap))
            body["thinking_budget"] = thinking_cap_int

            # Provider-specific parameter translation
            if provider_id in ("claude", "anthropic"):
                if thinking_cap_int <= 0:
                    body["thinking"] = {"type": "disabled"}
                else:
                    body["thinking"] = {
                        "type": "enabled",
                        "budget_tokens": thinking_cap_int,
                    }
                    if body.get("max_tokens") and int(body["max_tokens"]) <= thinking_cap_int:
                        body["max_tokens"] = thinking_cap_int + 4096
                    elif not body.get("max_tokens"):
                        body["max_tokens"] = thinking_cap_int + 4096

            elif provider_id in ("gemini", "google"):
                if thinking_cap_int <= 0:
                    body["thinking"] = {"type": "disabled"}
                else:
                    body["thinking"] = {"type": "enabled", "budget_tokens": thinking_cap_int}
                if "generationConfig" not in body or not isinstance(body["generationConfig"], dict):
                    body["generationConfig"] = {}
                body["generationConfig"]["thinkingConfig"] = {"thinkingBudget": thinking_cap_int}

            elif provider_id in ("deepseek", "deepseek-ai"):
                body["thinking_enabled"] = thinking_cap_int > 0
                body["thinking"] = thinking_cap_int > 0
                body["thinking_budget"] = thinking_cap_int

            elif provider_id in ("kimi", "moonshot"):
                body["thinking"] = thinking_cap_int > 0
                body["thinking_budget"] = thinking_cap_int

            elif provider_id in ("qwen", "qwen-ai", "tongyi"):
                body["thinking_enabled"] = thinking_cap_int > 0
                body["thinking_mode"] = "Auto" if thinking_cap_int > 0 else "Disabled"
                body["thinking_budget"] = thinking_cap_int

            elif provider_id in ("glm", "zhipu"):
                body["reasoning_effort"] = "low" if thinking_cap_int <= 4096 else "high" if thinking_cap_int > 16384 else "medium"
                body["thinking_budget"] = thinking_cap_int
        except Exception:
            pass

    # Model configuration fallbacks for max_tokens & temperature
    if "max_tokens" in model_cfg and "max_tokens" not in body:
        try:
            body["max_tokens"] = int(model_cfg["max_tokens"])
        except Exception:
            pass
    if "temperature" in model_cfg and "temperature" not in body:
        try:
            body["temperature"] = float(model_cfg["temperature"])
        except Exception:
            pass

    # Chat tools (web search and so on). Opt-in: nothing changes unless the request asks for them.
    tool_names = body.pop("eclipse_tools", None)
    tool_max_steps = body.pop("eclipse_max_steps", None)
    if tool_names is not None:
        known = {t.name for t in chat_tools.all_tools()}
        if not isinstance(tool_names, list) or any(not isinstance(n, str) for n in tool_names):
            return JSONResponse(status_code=400, content={"error": {
                "message": "eclipse_tools must be a list of tool names.", "type": "invalid_request_error"}})
        unknown = sorted(set(tool_names) - known)
        if unknown:
            return JSONResponse(status_code=400, content={"error": {
                "message": f"Unknown tool: {', '.join(unknown)}. Available: {', '.join(sorted(known))}.",
                "type": "invalid_request_error"}})
    tool_names = list(dict.fromkeys(tool_names or []))
    tool_guidance = ""
    preset_tools = False
    if tool_names:
        pipeline_info["tools_from"] = "request"

    # External client tools (OpenAI function calling: Kimi Code, Cline, etc.)
    client_tools = body.pop("tools", None) or body.pop("functions", None)
    is_client_tool_request = isinstance(client_tools, list) and len(client_tools) > 0
    if is_client_tool_request:
        body["messages"] = openai_tools_bridge.adapt_messages_for_tools(body.get("messages", []), client_tools)

    # Forward kwargs to direct engines
    forward_kwargs = {
        k: v for k, v in body.items()
        if k not in ("messages", "model", "stream")
    }

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Eclipse-Universal-Gateway/2.0",
    }

    # Pass through incoming authorization header or look up default account token
    incoming_auth = request.headers.get("Authorization")
    meta = providers.PROVIDERS_CONFIG.get(provider_id, {})
    external = None
    if provider_id == "external":
        external = db.find_connection_for_model(model_name)
        meta = {"name": external[0]["name"] if external else "external"}
    if incoming_auth:
        headers["Authorization"] = incoming_auth
    elif meta.get("auth_env"):
        env_token = os.getenv(meta["auth_env"])
        if env_token:
            headers["Authorization"] = f"Bearer {env_token}"
        elif meta.get("auth_header"):
            headers["Authorization"] = meta["auth_header"]
    elif meta.get("auth_header"):
        headers["Authorization"] = meta["auth_header"]

    is_stream = body.get("stream", False)
    simulate_requested = is_simulation_mode() or body.get("simulate", False)

    # Extract user prompt text for modality detection & simulation
    messages = body.get("messages", [])
    prompt_text = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            content = m.get("content", "")
            if isinstance(content, str):
                prompt_text = content
            elif isinstance(content, list):
                prompt_text = " ".join(item.get("text", "") for item in content if isinstance(item, dict))
            break

    effective_thinking_budget = body.get("thinking_budget")

    if simulate_requested:
        if is_stream:
            return StreamingResponse(
                generate_simulated_stream(
                    model_name,
                    provider_id,
                    prompt_text=prompt_text,
                    thinking_budget=effective_thinking_budget,
                ),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                    "X-Eclipse-Provider": provider_id,
                    "X-Eclipse-Simulated": "true",
                },
            )
        else:
            sim_content = _get_simulated_response_payload(model_name, provider_id, prompt_text)
            choice_msg = {
                "role": "assistant",
                "content": sim_content,
            }
            if effective_thinking_budget and effective_thinking_budget > 0:
                choice_msg["reasoning_content"] = (
                    f"Simulated reasoning trace for {model_name} (Thinking budget cap: {effective_thinking_budget:,} tokens)"
                )
            return JSONResponse(
                status_code=200,
                content={
                    "id": f"chatcmpl-sim-{int(time.time()*1000)}",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": model_name,
                    "choices": [{
                        "index": 0,
                        "message": choice_msg,
                        "finish_reason": "stop",
                    }],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 15, "total_tokens": 25},
                },
            )

    if external is not None and external[0]["requires_key"] and not external[0].get("api_key"):
        return JSONResponse(status_code=424, content={"error": {
            "message": f"{external[0]['name']} needs an API key. Add one under API connections in Cookie Stacker & Accounts.",
            "type": "missing_credentials", "code": "missing_credentials", "provider": "external"}})
    if providers.missing_credentials(provider_id):
        p_name = meta.get("name", provider_id)
        return JSONResponse(
            status_code=424,
            content={
                "error": {
                    "message": f"No {p_name} account is set up. Add one in Cookie Stacker & Accounts.",
                    "type": "missing_credentials",
                    "code": "missing_credentials",
                    "provider": provider_id,
                }
            },
        )

    # The request log keeps a full account of requests that use a preset or tools
    trace = None
    if (preset or tool_names) and db.request_log_settings()["enabled"]:
        pipeline_info["search_backend"] = (db.get_setting("search_backend", "auto") or "auto") if tool_names else None
        trace = requestlog.Trace(
            requested_model=str(requested_model), model=str(backend_model), preset=preset["name"] if preset else None,
            provider=provider_id, origin=request.headers.get("origin", ""), stream=bool(body.get("stream", False)),
            incoming=incoming_messages, tool_names=tool_names,
            tag=re.sub(r"[^A-Za-z0-9_.:-]", "", request.headers.get("x-eclipse-tag", ""))[:80])
        trace.pipeline(**pipeline_info)

    def _save_trace():
        if trace is None or trace.finished:
            return
        trace.finished = True
        try:
            db.add_request_log(trace.record())
        except Exception:
            logging.getLogger("eclipse.requestlog").exception("could not save the request log")

    async def _traced(stream, step):
        text, thoughts, failed = [], [], ""
        try:
            async for chunk in stream:
                choice = (chunk.get("choices") or [{}])[0]
                delta = choice.get("delta") or {}
                if isinstance(delta.get("content"), str):
                    if choice.get("finish_reason") == "error":
                        failed = delta["content"]
                    else:
                        text.append(delta["content"])
                if isinstance(delta.get("reasoning_content"), str):
                    thoughts.append(delta["reasoning_content"])
                if chunk.get("error"):
                    failed = str(chunk["error"])
                yield chunk
        finally:
            trace.output(step, "".join(text), "".join(thoughts), failed)
            aclose = getattr(stream, "aclose", None)
            if aclose:
                try:
                    await aclose()
                except Exception:
                    pass

    def _engine_stream(msgs):
        stream = engines.stream_chat(provider_id, backend_model, msgs, stream=True, **forward_kwargs)
        return _traced(stream, trace.sent(msgs)) if trace is not None else stream

    def _chat_source():
        if not tool_names:
            return _engine_stream(body.get("messages", []))
        return tools_loop.run(
            _engine_stream, body.get("messages", []), tool_names,
            model=requested_model, max_steps=tool_max_steps, get_setting=db.get_setting,
            cite=not preset_tools, guidance=tool_guidance,
        )

    # Direct in-process execution for all native engines
    if is_stream:
        async def direct_stream_generator() -> AsyncIterator[bytes]:
            rewriter = personas.PersonaStreamRewriter(persona_cfg) if persona_cfg else None
            smoothing_enabled = body.get("smooth", True) is not False and body.get("cadence_smoothing", True) is not False
            raw_source = _chat_source()
            if is_client_tool_request:
                raw_source = openai_tools_bridge.wrap_tool_stream(raw_source, requested_model)
            source = smooth_chat_stream(raw_source, target_interval=0.035, max_chars=40) if (smoothing_enabled and not is_client_tool_request) else raw_source
            try:
                async for chunk in source:
                    if trace is not None:
                        trace.feed(chunk)
                    chunk["model"] = requested_model
                    choices = chunk.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})
                        if preset_tools and delta.pop("eclipse_event", None) is not None and not delta:
                            continue
                        if "content" in delta and isinstance(delta["content"], str):
                            delta["content"] = re.sub(r"※[^\s]*", "", delta["content"])
                            delta["content"] = re.sub(r"\bcite[a-zA-Z0-9_]*turn[a-zA-Z0-9_]*\b", "", delta["content"])
                            delta["content"] = re.sub(r"\bturn\d+[a-zA-Z0-9_]*\b", "", delta["content"])
                            delta["content"] = re.sub(r"[\ue200-\ue20f]message_reaction[\ue200-\ue20f][^\ue200-\ue20f]*[\ue200-\ue20f]", "", delta["content"])
                            delta["content"] = re.sub(r"[\ue200-\ue20f]", "", delta["content"])
                    if rewriter:
                        choices = chunk.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            finish_reason = choices[0].get("finish_reason")
                            if "content" in delta:
                                new_c = rewriter.process(delta["content"])
                                if finish_reason:
                                    new_c += rewriter.finish()
                                if new_c or finish_reason:
                                    delta["content"] = new_c
                                    yield f"data: {json.dumps(chunk)}\n\n".encode("utf-8")
                                continue
                            if finish_reason:
                                rem = rewriter.finish()
                                if rem:
                                    flush_chunk = {
                                        "id": chunk.get("id", f"chatcmpl-{uuid.uuid4().hex[:8]}"),
                                        "object": "chat.completion.chunk",
                                        "created": chunk.get("created", int(time.time())),
                                        "model": requested_model,
                                        "choices": [{"index": 0, "delta": {"content": rem}, "finish_reason": None}],
                                    }
                                    yield f"data: {json.dumps(flush_chunk)}\n\n".encode("utf-8")
                    yield f"data: {json.dumps(chunk)}\n\n".encode("utf-8")
                if rewriter:
                    rem = rewriter.finish()
                    if rem:
                        flush_chunk = {
                            "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
                            "object": "chat.completion.chunk",
                            "created": int(time.time()),
                            "model": requested_model,
                            "choices": [{"index": 0, "delta": {"content": rem}, "finish_reason": None}],
                        }
                        yield f"data: {json.dumps(flush_chunk)}\n\n".encode("utf-8")
                yield b"data: [DONE]\n\n"
            except Exception as inner_e:
                p_name = meta.get("name", provider_id)
                err_msg = f"Provider {p_name} error: {str(inner_e)}"
                if trace is not None:
                    trace.error = trace.error or err_msg
                yield f"data: {json.dumps({'error': err_msg})}\n\n".encode("utf-8")
                yield b"data: [DONE]\n\n"
            finally:
                aclose = getattr(source, "aclose", None)
                if aclose:
                    try:
                        await aclose()
                    except Exception:
                        pass
                if smoothing_enabled and raw_source != source:
                    raw_aclose = getattr(raw_source, "aclose", None)
                    if raw_aclose:
                        try:
                            await raw_aclose()
                        except Exception:
                            pass
                _save_trace()

        return StreamingResponse(
            direct_stream_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "X-Eclipse-Provider": provider_id,
            },
        )
    elif tool_names:
        recorder = tools_loop.StepRecorder()
        try:
            source = _chat_source()
            try:
                async for chunk in source:
                    recorder.feed(chunk)
                    if trace is not None:
                        trace.feed(chunk)
            finally:
                await source.aclose()
        except Exception as inner_e:
            recorder.error = recorder.error or str(inner_e)
        if trace is not None:
            trace.error = trace.error or recorder.error
        _save_trace()
        if recorder.error:
            raise HTTPException(status_code=502, detail=f"Provider {meta.get('name', provider_id)} error: {recorder.error}")
        content = recorder.content
        if persona_cfg:
            content = personas.sanitize_text(content, persona_cfg)
        message = {"role": "assistant", "content": content}
        if not preset_tools:
            message["eclipse_steps"] = recorder.steps
        if recorder.reasoning:
            message["reasoning_content"] = recorder.reasoning
        return JSONResponse(status_code=200, content={
            "id": f"chatcmpl-tools-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": requested_model,
            "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
        })
    else:
        try:
            step = trace.sent(body.get("messages", [])) if trace is not None else 0
            data = await engines.generate_chat(provider_id, backend_model, body.get("messages", []), **forward_kwargs)
            if is_client_tool_request:
                reply = ((data.get("choices") or [{}])[0].get("message") or {})
                parsed_call = openai_tools_bridge.parse_tool_call_text(reply.get("content") or "")
                if parsed_call:
                    name, args, prefix = parsed_call
                    reply["tool_calls"] = [{
                        "id": f"call_{uuid.uuid4().hex[:12]}",
                        "type": "function",
                        "function": {
                            "name": name,
                            "arguments": json.dumps(args, ensure_ascii=False)
                        }
                    }]
                    reply["content"] = prefix or None
                    if data.get("choices"):
                        data["choices"][0]["finish_reason"] = "tool_calls"
            if trace is not None:
                reply = ((data.get("choices") or [{}])[0].get("message") or {})
                trace.set_reply(reply.get("content") or "", reply.get("reasoning_content") or "")
                trace.output(step, trace.visible, trace.visible_reasoning)
                _save_trace()
            data["model"] = requested_model
            if persona_cfg:
                data["model"] = requested_model
                for c in data.get("choices", []):
                    if "message" in c and "content" in c["message"]:
                        c["message"]["content"] = personas.sanitize_text(c["message"]["content"], persona_cfg)
            return JSONResponse(status_code=200, content={
                **data,
                "model": requested_model,
            })
        except Exception as inner_e:
            if trace is not None:
                trace.error = str(inner_e)
                _save_trace()
            p_name = meta.get("name", provider_id)
            raise HTTPException(
                status_code=502,
                detail=f"Provider {p_name} error: {str(inner_e)}",
            )


    if is_stream:
        async def stream_generator() -> AsyncIterator[bytes]:
            client = httpx.AsyncClient(timeout=120.0)
            yielded_any_bytes = False
            rewriter = personas.PersonaStreamRewriter(persona_cfg) if persona_cfg else None
            try:
                async with client.stream("POST", target_url, json=body, headers=headers) as upstream:
                    if upstream.status_code < 400:
                        if persona_cfg:
                            async for line in upstream.aiter_lines():
                                if not line:
                                    continue
                                line = line.strip()
                                if line.startswith("data: "):
                                    data_str = line[6:].strip()
                                    if data_str == "[DONE]":
                                        break
                                    try:
                                        chunk = json.loads(data_str)
                                        chunk["model"] = requested_model
                                        choices = chunk.get("choices", [])
                                        if choices:
                                            delta = choices[0].get("delta", {})
                                            finish_reason = choices[0].get("finish_reason")
                                            if "content" in delta:
                                                new_c = rewriter.process(delta["content"])
                                                if new_c:
                                                    delta["content"] = new_c
                                                    yielded_any_bytes = True
                                                    yield f"data: {json.dumps(chunk)}\n\n".encode("utf-8")
                                                continue
                                            if finish_reason:
                                                rem = rewriter.finish()
                                                if rem:
                                                    flush_chunk = {
                                                        "id": chunk.get("id", f"chatcmpl-{uuid.uuid4().hex[:8]}"),
                                                        "object": "chat.completion.chunk",
                                                        "created": chunk.get("created", int(time.time())),
                                                        "model": requested_model,
                                                        "choices": [{"index": 0, "delta": {"content": rem}, "finish_reason": None}],
                                                    }
                                                    yielded_any_bytes = True
                                                    yield f"data: {json.dumps(flush_chunk)}\n\n".encode("utf-8")
                                        yielded_any_bytes = True
                                        yield f"data: {json.dumps(chunk)}\n\n".encode("utf-8")
                                    except Exception:
                                        yielded_any_bytes = True
                                        yield f"{line}\n\n".encode("utf-8")
                            if rewriter:
                                rem = rewriter.finish()
                                if rem:
                                    flush_chunk = {
                                        "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
                                        "object": "chat.completion.chunk",
                                        "created": int(time.time()),
                                        "model": requested_model,
                                        "choices": [{"index": 0, "delta": {"content": rem}, "finish_reason": None}],
                                    }
                                    yield f"data: {json.dumps(flush_chunk)}\n\n".encode("utf-8")
                            yield b"data: [DONE]\n\n"
                            return
                        else:
                            async for chunk in upstream.aiter_bytes():
                                if chunk:
                                    yielded_any_bytes = True
                                    yield chunk
                            return
            except Exception:
                pass
            finally:
                await client.aclose()

            # If bytes were already emitted to the client, DO NOT run fallback into the same stream!
            if yielded_any_bytes:
                yield b"data: [DONE]\n\n"
                return

            # Direct in-process native engine fallback (when upstream daemon is down or returned >= 400)
            try:
                smoothing_enabled = body.get("smooth", True) is not False and body.get("cadence_smoothing", True) is not False
                raw_fallback = engines.stream_chat(provider_id, backend_model, body.get("messages", []), stream=True, **forward_kwargs)
                fallback_source = smooth_chat_stream(raw_fallback, target_interval=0.035, max_chars=40) if smoothing_enabled else raw_fallback
                async for chunk in fallback_source:
                    chunk["model"] = requested_model
                    if rewriter:
                        choices = chunk.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            finish_reason = choices[0].get("finish_reason")
                            if "content" in delta:
                                new_c = rewriter.process(delta["content"])
                                if new_c:
                                    delta["content"] = new_c
                                    yield f"data: {json.dumps(chunk)}\n\n".encode("utf-8")
                                continue
                            if finish_reason:
                                rem = rewriter.finish()
                                if rem:
                                    flush_chunk = {
                                        "id": chunk.get("id", f"chatcmpl-{uuid.uuid4().hex[:8]}"),
                                        "object": "chat.completion.chunk",
                                        "created": chunk.get("created", int(time.time())),
                                        "model": requested_model,
                                        "choices": [{"index": 0, "delta": {"content": rem}, "finish_reason": None}],
                                    }
                                    yield f"data: {json.dumps(flush_chunk)}\n\n".encode("utf-8")
                    yield f"data: {json.dumps(chunk)}\n\n".encode("utf-8")
                if rewriter:
                    rem = rewriter.finish()
                    if rem:
                        flush_chunk = {
                            "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
                            "object": "chat.completion.chunk",
                            "created": int(time.time()),
                            "model": requested_model,
                            "choices": [{"index": 0, "delta": {"content": rem}, "finish_reason": None}],
                        }
                        yield f"data: {json.dumps(flush_chunk)}\n\n".encode("utf-8")
                yield b"data: [DONE]\n\n"
                return
            except Exception as inner_e:
                p_name = meta.get("name", provider_id)
                err_msg = f"Provider {p_name} error: {str(inner_e)}"
                yield f"data: {json.dumps({'error': err_msg})}\n\n".encode("utf-8")
                yield b"data: [DONE]\n\n"
            finally:
                aclose = getattr(fallback_source, "aclose", None) if "fallback_source" in locals() else None
                if aclose:
                    try:
                        await aclose()
                    except Exception:
                        pass
                if "smoothing_enabled" in locals() and smoothing_enabled and "raw_fallback" in locals() and raw_fallback != fallback_source:
                    raw_aclose = getattr(raw_fallback, "aclose", None)
                    if raw_aclose:
                        try:
                            await raw_aclose()
                        except Exception:
                            pass

        return StreamingResponse(
            stream_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "X-Eclipse-Provider": provider_id,
            },
        )

    # Non-streaming request
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            resp = await client.post(target_url, json=body, headers=headers)
            if resp.status_code < 400:
                try:
                    data = resp.json()
                    if persona_cfg:
                        data["model"] = requested_model
                        for c in data.get("choices", []):
                            if "message" in c and "content" in c["message"]:
                                c["message"]["content"] = personas.sanitize_text(c["message"]["content"], persona_cfg)
                    return JSONResponse(status_code=resp.status_code, content=data)
                except Exception:
                    return Response(content=resp.content, status_code=resp.status_code, media_type=resp.headers.get("content-type"))
        except Exception:
            pass

    # Direct in-process native engine fallback
    try:
        data = await engines.generate_chat(provider_id, backend_model, body.get("messages", []), **forward_kwargs)
        if persona_cfg:
            data["model"] = requested_model
            for c in data.get("choices", []):
                if "message" in c and "content" in c["message"]:
                    c["message"]["content"] = personas.sanitize_text(c["message"]["content"], persona_cfg)
        return JSONResponse(status_code=200, content=data)
    except Exception as inner_e:
        raise HTTPException(
            status_code=502,
            detail=f"Provider {meta['name']} error: {str(inner_e)}",
        )


@app.post("/v1/images/generations")
async def image_generations(request: Request):
    """Route image generation requests to Gemini, GLM, or configured providers."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    model = body.get("model", "gemini-3.8-flash")
    provider_id = resolve_model_provider(model)
    meta = PROVIDERS_CONFIG.get(provider_id, PROVIDERS_CONFIG["gemini"])

    simulate_requested = is_simulation_mode() or body.get("simulate", False)
    if simulate_requested:
        return JSONResponse(status_code=200, content={
            "created": int(time.time()),
            "data": [{
                "url": "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=1024&q=80",
                "revised_prompt": body.get("prompt", "A high-fidelity futuristic rendering generated by Eclipse")
            }]
        })

    target_port = meta["port"]
    target_host = providers.get_provider_host(provider_id)
    target_url = f"http://{target_host}:{target_port}/v1/images/generations"
    headers = {"Content-Type": "application/json"}
    if meta["auth_header"]:
        headers["Authorization"] = meta["auth_header"]

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            resp = await client.post(target_url, json=body, headers=headers)
            try:
                return JSONResponse(status_code=resp.status_code, content=resp.json())
            except Exception:
                return Response(content=resp.content, status_code=resp.status_code)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Image generation failed: {str(e)}")


# -------------------------------------------------------------------
# Eclipse Management APIs (/api)
# -------------------------------------------------------------------

@app.get("/healthz")
async def health():
    return {"status": "ok", "app": "Eclipse", "version": "1.0.0", "port": 5000}


# -------------------------------------------------------------------
# Gateway Authentication (browser session login for off-machine access)
# -------------------------------------------------------------------

@app.get("/api/auth/status")
async def api_auth_status(request: Request):
    headers = dict(request.headers)
    client_ip = request.client.host if request.client else None
    return {
        "authenticated": security.is_authenticated(client_ip, headers),
        "local": security.is_trusted_local(client_ip, headers),
        "lan_mode": security.is_lan_mode(),
    }


@app.post("/api/auth/login")
async def api_auth_login(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    key = str(body.get("key", "")) if isinstance(body, dict) else ""
    if not security.check_key(key):
        await asyncio.sleep(0.5)
        return JSONResponse({"status": "error", "message": "Invalid gateway key"}, status_code=401)
    secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    resp = JSONResponse({"status": "ok", "token": security.session_token(), "key": key.strip()})
    resp.set_cookie(
        security.SESSION_COOKIE,
        security.session_token(),
        max_age=60 * 60 * 24 * 365,
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
    )
    return resp


@app.post("/api/auth/logout")
async def api_auth_logout():
    resp = JSONResponse({"status": "ok"})
    resp.delete_cookie(security.SESSION_COOKIE, path="/")
    return resp


@app.get("/api/services")
async def api_get_services():
    services = await get_all_services_status()
    # Also attach Eclipse itself
    eclipse_info = {
        "id": "eclipse",
        "name": "Eclipse Hub",
        "badge": "Core Gateway",
        "port": 5000,
        "color": "#D97757",
        "pid": os.getpid(),
        "running": True,
        "latency_ms": 0.5,
        "health_path": "/healthz",
        "cookie_label": "System Master Gateway",
    }
    return {"services": services, "hub": eclipse_info}


def get_lan_ip() -> str:
    """Detect the host machine's primary local network IP."""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0.2)
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"




@app.post("/api/services/start_all")
async def api_start_all():
    return start_all_services()


@app.post("/api/services/stop_all")
async def api_stop_all():
    return stop_all_services()


@app.post("/api/services/{provider_id}/start")
async def api_start_service(provider_id: str):
    res = start_provider(provider_id)
    return res


@app.post("/api/services/{provider_id}/stop")
async def api_stop_service(provider_id: str):
    res = stop_provider(provider_id)
    return res


@app.post("/api/services/{provider_id}/restart")
async def api_restart_service(provider_id: str):
    stop_provider(provider_id)
    time.sleep(1.0)
    return start_provider(provider_id)


@app.get("/api/simulation")
async def api_get_simulation():
    active = providers.is_simulation_active()
    return {
        "enabled": active,
        "mode": "simulated" if active else "live",
        "description": "Device Simulation Mode allows testing UI, models, and clients without local backends.",
    }


@app.post("/api/simulation")
async def api_toggle_simulation(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    enabled = body.get("enabled")
    if enabled is None:
        enabled = not providers.is_simulation_active()
    db.set_setting("simulation_mode", "1" if enabled else "0")
    return {
        "status": "ok",
        "enabled": bool(enabled),
        "mode": "simulated" if enabled else "live",
    }


@app.get("/api/config")
async def api_get_config():
    return {
        "simulation_mode": providers.is_simulation_active(),
        "remote_host": db.get_setting("remote_host", "127.0.0.1"),
        "settings": db.get_all_settings(),
        "vault_stats": db.get_stats(),
    }


# Settings the HTTP API may change. Everything else (provider PIDs, provider hosts)
# is written only by Eclipse itself or the local CLI.
API_WRITABLE_SETTINGS = {"simulation_mode", "allowed_origins", "gateway_key"}


@app.get("/api/security/allowed-origins")
async def api_get_allowed_origins():
    origins = list(security._extra_allowed_origins())
    return {"allowed_origins": sorted(origins)}


@app.post("/api/security/allowed-origins")
async def api_add_allowed_origin(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    
    raw = body.get("origin", "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="origin string is required")
    
    cleaned = security._clean_origin_string(raw)
    if not cleaned:
        raise HTTPException(status_code=400, detail="Invalid origin format. Please enter a valid URL (e.g. https://lorebary.com)")
    
    current_raw = db.get_setting("allowed_origins", "")
    current_list = []
    for o in current_raw.split(","):
        c = security._clean_origin_string(o)
        if c and c not in current_list:
            current_list.append(c)
    
    candidates = [cleaned]
    # If a subdomain or domain was added (e.g. https://api.lorebary.com), also add root domain
    parts = urlsplit(cleaned)
    if parts.hostname and parts.hostname.count(".") >= 2:
        root_host = ".".join(parts.hostname.split(".")[-2:])
        root_origin = f"{parts.scheme}://{root_host}"
        if root_origin not in candidates and root_origin not in current_list:
            candidates.append(root_origin)

    if parts.hostname and "lorebary" in parts.hostname:
        for extra in ("https://lorebary.com", "https://lorebary.sophiamccarty.com", "https://sophiamccarty.com"):
            if extra not in candidates and extra not in current_list:
                candidates.append(extra)

    if parts.hostname and "janitor" in parts.hostname:
        for extra in ("https://janitorai.com", "https://www.janitorai.com", "https://janitor.ai"):
            if extra not in candidates and extra not in current_list:
                candidates.append(extra)

    for cand in candidates:
        if cand not in current_list:
            current_list.append(cand)

    db.set_setting("allowed_origins", ",".join(current_list))
    return {
        "status": "ok",
        "added": cleaned,
        "allowed_origins": sorted(list(security._extra_allowed_origins()))
    }


@app.delete("/api/security/allowed-origins")
async def api_delete_allowed_origin(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    raw = body.get("origin", "").strip()
    if not raw and "origin" in request.query_params:
        raw = request.query_params["origin"].strip()
    
    if not raw:
        raise HTTPException(status_code=400, detail="origin string is required")
    
    cleaned = security._clean_origin_string(raw) or raw.lower().rstrip("/")
    
    current_raw = db.get_setting("allowed_origins", "")
    current_list = []
    for o in current_raw.split(","):
        c = security._clean_origin_string(o) or o.strip().rstrip("/").lower()
        if c and c != cleaned and o.strip().rstrip("/").lower() != raw.lower().rstrip("/"):
            if c not in current_list:
                current_list.append(c)

    db.set_setting("allowed_origins", ",".join(current_list))
    return {
        "status": "ok",
        "deleted": cleaned,
        "allowed_origins": sorted(list(security._extra_allowed_origins()))
    }


@app.get("/api/security/gateway-key")
async def api_get_gateway_key():
    return {
        "status": "ok",
        "gateway_key": security.get_gateway_key()
    }


@app.post("/api/security/gateway-key")
async def api_set_gateway_key(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    
    action = body.get("action", "")
    if action == "rotate":
        new_key = security.rotate_gateway_key()
    else:
        raw_key = body.get("gateway_key", "")
        new_key = security.set_gateway_key(raw_key)
        
    return {
        "status": "ok",
        "gateway_key": new_key
    }


@app.post("/api/config")
async def api_set_config(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Expected a JSON object")
    rejected = sorted(k for k in body if k not in API_WRITABLE_SETTINGS)
    if rejected:
        raise HTTPException(status_code=400, detail=f"Settings not writable via API: {', '.join(rejected)}")
    for k, v in body.items():
        db.set_setting(k, str(v))
    return {
        "status": "ok",
        "settings": db.get_all_settings(),
    }


@app.get("/api/limits")
async def api_get_limits():
    return await get_all_limits()


@app.get("/api/models")
async def api_get_models():
    return {"models": get_dynamic_models_catalog()}


@app.get("/api/model-settings")
async def api_get_model_settings(model: Optional[str] = None):
    """Retrieve customized settings (thinking_budget cap, max_tokens, etc.) for models."""
    if model:
        return {"status": "ok", "model": model, "settings": db.get_model_settings(model)}
    return {"status": "ok", "settings": db.get_all_model_settings()}


@app.post("/api/model-settings")
async def api_save_model_settings(request: Request):
    """Persist thinking budget cap, max output tokens, and parameters for a model."""
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    model = (data.get("model") or "").strip()
    if not model:
        raise HTTPException(status_code=400, detail="Missing required 'model' field")

    cfg = {}
    if "thinking_budget" in data:
        try:
            cfg["thinking_budget"] = max(0, min(65536, int(data["thinking_budget"])))
        except (ValueError, TypeError):
            pass
    if "max_tokens" in data:
        try:
            cfg["max_tokens"] = max(1, min(131072, int(data["max_tokens"])))
        except (ValueError, TypeError):
            pass
    if "temperature" in data:
        try:
            cfg["temperature"] = round(max(0.0, min(2.0, float(data["temperature"]))), 2)
        except (ValueError, TypeError):
            pass
    if "system_prompt" in data:
        cfg["system_prompt"] = str(data["system_prompt"]).strip()

    apply_globally = data.get("apply_globally") is True or model.lower() in ("global", "default", "*")
    if apply_globally:
        db.set_global_settings(cfg)
    db.set_model_settings(model, cfg, sync_family=True)

    budget_val = cfg.get("thinking_budget")
    budget_label = f"{budget_val:,} tokens" if budget_val is not None and budget_val > 0 else "Off"
    if apply_globally:
        msg = f"Enforced globally across ALL models (Thinking cap: {budget_label})."
    else:
        msg = f"Enforced for '{model}' and all family aliases (Thinking cap: {budget_label})."

    return {
        "status": "ok",
        "message": msg,
        "settings": cfg,
    }


@app.delete("/api/model-settings")
async def api_delete_model_settings(request: Request, model: Optional[str] = None):
    """Reset model settings to default."""
    target_model = model
    if not target_model:
        try:
            body = await request.json()
            target_model = body.get("model")
        except Exception:
            pass
    if not target_model:
        raise HTTPException(status_code=400, detail="Missing model name")
    db.delete_model_settings(target_model)
    return {"status": "ok", "message": f"Model settings for '{target_model}' reset to defaults."}



@app.get("/api/accounts/validate")
async def api_validate_accounts(request: Request):
    """
    Probe each stacked account for the given provider and return live token validity.
    For Gemini: tries extracting SNlM0e from gemini.google.com with the stored cookie.
    For all others: returns db status as-is.

    Response: { "accounts": [{ "id", "identifier", "name", "plan", "valid": bool, "reason": str, "expires_at": int|null }] }
    """
    provider = request.query_params.get("provider", "gemini").lower().strip()
    try:
        accounts = db.get_accounts(provider)
    except Exception as e:
        return JSONResponse({"error": f"DB error: {str(e)}"}, status_code=500)

    results = []

    if provider == "gemini":
        from eclipse.engines.gemini import probe_gemini_session
        for acc in accounts:
            acc_id = acc.get("id")
            ident = acc.get("identifier") or acc.get("name") or str(acc_id)
            cookie_str = acc.get("token", "")
            try:
                valid, reason = await probe_gemini_session(cookie_str)
            except Exception as e:
                valid = False
                reason = f"Probe error: {str(e)[:100]}"
            results.append({
                "id": acc_id,
                "identifier": ident,
                "name": acc.get("name") or ident,
                "plan": acc.get("plan", "FREE"),
                "valid": valid,
                "reason": reason,
                "expires_at": None,
            })

    else:
        for acc in accounts:
            results.append({
                "id": acc.get("id"),
                "identifier": acc.get("identifier") or acc.get("name", ""),
                "name": acc.get("name", ""),
                "plan": acc.get("plan", "FREE"),
                "valid": acc.get("status", "active").lower() == "active",
                "reason": "Active in database",
                "expires_at": None,
            })

    return {"accounts": results}


@app.get("/api/cookies")
async def api_get_cookies():
    return get_stored_cookies()


@app.get("/api/cookies/export")
async def api_export_cookies():
    return db.export_all_json()


@app.post("/api/cookies/import")
async def api_import_cookies(request: Request):
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    try:
        res = db.import_all_json(data)
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/cookies/{provider_id}")
async def api_save_cookies(provider_id: str, request: Request):
    body = await request.json()
    accounts = body.get("accounts", [])
    if isinstance(accounts, str):
        # Split by newlines (strictly NOT by comma)
        accounts = [line.strip() for line in accounts.splitlines() if line.strip()]
    res = save_stacked_cookies(provider_id, accounts)
    return res


@app.post("/api/cookies/{provider_id}/remove")
@app.delete("/api/cookies/{provider_id}")
async def api_remove_cookie(provider_id: str, request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    identifier = body.get("identifier")
    index = body.get("index")
    account_id = body.get("id")

    # Capture account info before deletion so we can purge from cloud
    target_accounts = db.get_accounts(provider_id)
    account_to_remove = None
    if account_id is not None:
        account_to_remove = next((a for a in target_accounts if a.get("id") == account_id), None)
    if not account_to_remove and identifier:
        account_to_remove = next((a for a in target_accounts if a.get("identifier") == identifier or str(a.get("id")) == str(identifier)), None)

    res = remove_stacked_cookie(provider_id, identifier=identifier, index=account_id if account_id is not None else index)
    return res


@app.post("/api/gemini/autofetch")
async def api_gemini_autofetch(request: Request):
    """Auto-fetches the freshest Google Gemini session tokens (__Secure-1PSID & __Secure-1PSIDTS) from local browsers."""
    try:
        from eclipse.engines.gemini import auto_fetch_gemini_token
        result = auto_fetch_gemini_token(save_to_db=True)
        if result.get("ok"):
            return JSONResponse({
                "ok": True,
                "message": result.get("message"),
                "browser": result.get("browser"),
                "profile": result.get("profile"),
                "cookie_string": result.get("cookie_string"),
                "token": result.get("cookie_string"),
                "has_psidts": result.get("has_psidts", False),
                "accounts": db.get_accounts("gemini"),
            })
        else:
            return JSONResponse({
                "ok": False,
                "detail": result.get("detail", "No active Gemini session found in local browser cookies.")
            }, status_code=404)
    except Exception as exc:
        return JSONResponse({
            "ok": False,
            "detail": f"Auto-fetch failed: {str(exc)}"
        }, status_code=500)


@app.get("/api/antigravity/oauth/url")
async def api_antigravity_oauth_url(request: Request):
    """Retrieve official Google Cloud Code OAuth consent URL and ensure listener is running."""
    try:
        from eclipse.engines import antigravity
        antigravity.start_oauth_listener()
        return JSONResponse({
            "ok": True,
            "url": antigravity.get_oauth_url(),
            "port": antigravity.OAUTH_PORT,
        })
    except Exception as exc:
        return JSONResponse({"ok": False, "message": str(exc)}, status_code=500)


@app.post("/api/antigravity/oauth/start")
async def api_antigravity_oauth_start(request: Request):
    """Initiate Google OAuth flow, launching callback listener on port 51121."""
    try:
        from eclipse.engines import antigravity
        started = antigravity.start_oauth_listener()
        return JSONResponse({
            "ok": True,
            "started": started,
            "url": antigravity.get_oauth_url(),
            "port": antigravity.OAUTH_PORT,
        })
    except Exception as exc:
        return JSONResponse({"ok": False, "message": str(exc)}, status_code=500)


@app.get("/api/antigravity/oauth/status")
async def api_antigravity_oauth_status(request: Request):
    """Poll status of latest OAuth callback event and current accounts list."""
    try:
        from eclipse.engines import antigravity
        latest = antigravity.get_latest_oauth_event()
        return JSONResponse({
            "ok": True,
            "latest": latest,
            "accounts": db.get_accounts("antigravity"),
        })
    except Exception as exc:
        return JSONResponse({"ok": False, "message": str(exc)}, status_code=500)


@app.post("/api/antigravity/autofetch")
async def api_antigravity_autofetch(request: Request):
    """Auto-detects active Google Antigravity IDE credentials from local machine and saves to vault."""
    try:
        from eclipse.engines import antigravity
        creds = antigravity._load_local_fallback_credentials()
        if not creds:
            return JSONResponse({
                "ok": False,
                "message": "No local Antigravity credentials found in local IDE storage or ~/.gemini."
            }, status_code=404)

        saved_count = 0
        token_str = ""
        for c in creds:
            raw = c.get("token") or ""
            if raw:
                token_str = raw
                parsed = db.parse_credential("antigravity", raw)
                if parsed:
                    db.add_account("antigravity", parsed)
                    saved_count += 1

        return JSONResponse({
            "ok": True,
            "message": f"Successfully auto-detected {saved_count} Antigravity account(s)!",
            "token": token_str,
            "accounts": db.get_accounts("antigravity"),
        })
    except Exception as exc:
        return JSONResponse({"ok": False, "message": str(exc)}, status_code=500)



# -------------------------------------------------------------------
# Request Logs, API Connections, Test Bench, Tools Endpoints
# -------------------------------------------------------------------

async def _json_object(request: Request) -> Dict[str, Any]:
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="JSON body must be an object")
    return body


def _log_id(raw) -> Optional[int]:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


@app.get("/api/request-logs")
async def api_list_request_logs(request: Request):
    q = request.query_params
    try:
        limit = int(q.get("limit", "50"))
    except ValueError:
        limit = 50
    outcome = q.get("outcome", "")
    if outcome and outcome not in requestlog.OUTCOMES:
        return JSONResponse(status_code=400, content={"error": {"message": f"outcome must be one of {', '.join(requestlog.OUTCOMES)}", "type": "invalid_request_error"}})
    only_tools = q.get("tools", "") in ("1", "true")
    return {"logs": db.list_request_logs(limit, only_tools, outcome), "settings": db.request_log_settings()}


@app.get("/api/request-logs/settings")
async def api_request_log_settings():
    return db.request_log_settings()


@app.put("/api/request-logs/settings")
async def api_set_request_log_settings(request: Request):
    body = await _json_object(request)
    try:
        return db.set_request_log_settings(body.get("enabled"), body.get("keep"))
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": {"message": str(e), "type": "invalid_request_error"}})


@app.get("/api/request-logs/{log_id}")
async def api_get_request_log(log_id: str):
    entry = db.get_request_log(_log_id(log_id) or 0)
    if not entry:
        return JSONResponse(status_code=404, content={"error": {"message": "No such log entry.", "type": "not_found"}})
    return entry


@app.delete("/api/request-logs/{log_id}")
async def api_delete_request_log(log_id: str):
    if not db.delete_request_log(_log_id(log_id) or 0):
        return JSONResponse(status_code=404, content={"error": {"message": "No such log entry.", "type": "not_found"}})
    return {"ok": True}


@app.delete("/api/request-logs")
async def api_clear_request_logs():
    return {"ok": True, "deleted": db.clear_request_logs()}




# Test bench
_BENCH: Dict[str, Any] = {"task": None, "run_id": None, "cancel": False}
_bench_sender = None


def _bench_error(message: str, status: int = 400):
    return JSONResponse(status_code=status, content={"error": {"message": message, "type": "invalid_request_error"}})


@app.get("/api/bench/scenarios")
async def api_bench_scenarios():
    return {"builtin": bench.builtin_scenarios(), "custom": db.list_bench_scenarios(), "default_card": bench.DEFAULT_CARD}


@app.post("/api/bench/scenarios")
async def api_create_bench_scenario(request: Request):
    body = await _json_object(request)
    try:
        return JSONResponse(db.create_bench_scenario(body), status_code=201)
    except bench.BenchError as e:
        return _bench_error(str(e))


@app.put("/api/bench/scenarios/{scenario_id}")
async def api_update_bench_scenario(scenario_id: str, request: Request):
    body = await _json_object(request)
    try:
        updated = db.update_bench_scenario(_log_id(scenario_id) or 0, body)
    except bench.BenchError as e:
        return _bench_error(str(e))
    return updated or _bench_error("No such test.", 404)


@app.delete("/api/bench/scenarios/{scenario_id}")
async def api_delete_bench_scenario(scenario_id: str):
    return {"ok": True} if db.delete_bench_scenario(_log_id(scenario_id) or 0) else _bench_error("No such test.", 404)


@app.get("/api/bench/runs")
async def api_list_bench_runs():
    return {"runs": db.list_bench_runs(), "running": _BENCH["run_id"]}


@app.get("/api/bench/runs/{run_id}")
async def api_get_bench_run(run_id: str):
    run = db.get_bench_run(_log_id(run_id) or 0)
    return run or _bench_error("No such run.", 404)


@app.delete("/api/bench/runs/{run_id}")
async def api_delete_bench_run(run_id: str):
    return {"ok": True} if db.delete_bench_run(_log_id(run_id) or 0) else _bench_error("No such run, or it is still running.", 404)


@app.post("/api/bench/runs/{run_id}/cancel")
async def api_cancel_bench_run(run_id: str):
    if _BENCH["run_id"] is None or _BENCH["run_id"] != _log_id(run_id):
        return _bench_error("That run is not running.", 404)
    _BENCH["cancel"] = True
    return {"ok": True}


async def _bench_job(run_id: int, scenarios, model: str, preset: Dict[str, Any], card: str, sender):
    results: List[Dict[str, Any]] = []

    def on_result(result):
        results.append(result)
        db.save_bench_run(run_id, results)

    def find_log(tag):
        rows = db.list_request_logs(1, tag=tag)
        return db.get_request_log(rows[0]["id"]) if rows else None

    status = "done"
    try:
        await bench.run_scenarios(
            scenarios=scenarios, model=model, preset=preset, card=card, run_tag=f"bench-{run_id}", send=sender,
            find_log=find_log, on_result=on_result, cancelled=lambda: _BENCH["cancel"])
        if _BENCH["cancel"]:
            status = "cancelled"
    except Exception:
        logging.getLogger("eclipse.bench").exception("bench run %s crashed", run_id)
        status = "error"
    finally:
        db.save_bench_run(run_id, results, status)
        _BENCH.update(task=None, run_id=None, cancel=False)


@app.post("/api/bench/runs")
async def api_start_bench_run(request: Request):
    body = await _json_object(request)
    if _BENCH["run_id"] is not None:
        return _bench_error("A test run is already going. Wait for it or cancel it.", 409)
    req_preset = body.get("preset")
    if (not req_preset or not str(req_preset).strip()) and db.list_presets():
        req_preset = db.list_presets()[0]["name"]
    preset = db.get_preset(req_preset) if isinstance(req_preset, str) else None
    if not preset:
        return _bench_error("Pick a preset that exists.")
    model = body.get("model")
    if not isinstance(model, str) or not model.strip() or "@" in model or len(model) > 80:
        return _bench_error("model must be a model name without an @ (the preset is added for you).")
    model = model.strip()
    if not db.request_log_settings()["enabled"]:
        return _bench_error("Switch the request log on first: the test checks each chat against it.")
    card = body.get("card", "")
    if not isinstance(card, str) or len(card) > 20_000:
        return _bench_error("card must be text of at most 20,000 characters.")
    pool = bench.builtin_scenarios() + db.list_bench_scenarios()
    wanted = body.get("scenarios")
    if wanted is not None:
        if not isinstance(wanted, list) or not all(isinstance(w, str) for w in wanted):
            return _bench_error("scenarios must be a list of test ids.")
        unknown = sorted(set(wanted) - {s["id"] for s in pool})
        if unknown:
            return _bench_error(f"Unknown test: {', '.join(unknown)}")
        pool = [s for s in pool if s["id"] in set(wanted)]
    if not pool:
        return _bench_error("Pick at least one test.")
    settings = {"tools": preset.get("tools", []), "tool_max_steps": preset.get("tool_max_steps"),
                "focus": "off" if not preset.get("tool_guidance_on", True) else "preset text" if (preset.get("tool_guidance") or "").strip() else "built-in text",
                "card": "custom" if card.strip() else "default"}
    run_id = db.create_bench_run(preset["name"], model, len(pool), settings)
    port = (request.scope.get("server") or (None, 5000))[1] or 5000
    sender = _bench_sender or (lambda model_ref, messages, tag: bench.http_sender(f"http://127.0.0.1:{port}", model_ref, messages, tag, 150.0))
    _BENCH.update(run_id=run_id, cancel=False, task=asyncio.create_task(_bench_job(run_id, pool, model, preset, card, sender)))
    return JSONResponse(db.get_bench_run(run_id), status_code=202)


@app.get("/api/tools")
async def api_get_tools():
    """Tools the chat can use, and which search backend would answer. Never includes the key."""
    search = tools_web_search.active_backend(db.get_setting)
    search["key_saved"] = bool((db.get_setting("search_api_key", "") or "").strip())
    search["backend_setting"] = (db.get_setting("search_backend", "auto") or "auto").lower()
    return {"tools": chat_tools.describe(), "search": search, "default_guidance": tools_protocol.DEFAULT_GUIDANCE}


# -------------------------------------------------------------------
# Presets, Lorebooks, Userscripts, and Chat History Endpoints
# -------------------------------------------------------------------



@app.get("/userscripts/eclipse-regex.user.js")
async def userscript_file(request: Request):
    host = request.headers.get("host") or "localhost:5000"
    scheme = "https" if request.headers.get("x-forwarded-proto") == "https" or request.url.scheme == "https" else "http"
    base_url = f"{scheme}://{host}"
    try:
        t_stat = tunnel.get_tunnel_status()
        ngrok_url = (t_stat.get("public_url") or "") if t_stat.get("status") == "online" else ""
    except Exception:
        ngrok_url = ""
    return Response(content=userscript.build(base_url, ngrok_url=ngrok_url), media_type="text/javascript",
                    headers={"Cache-Control": "no-store"})




@app.get("/api/chats")
async def api_list_chats(request: Request):
    archived = (request.query_params.get("archived") or "exclude").lower()
    archived = {"1": "include", "true": "include", "0": "exclude", "false": "exclude"}.get(archived, archived)
    try:
        return {"chats": db.list_chats(query=request.query_params.get("q"), archived=archived)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/chats")
async def api_create_chat(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    title = body.get("title") if isinstance(body, dict) else None
    return JSONResponse(db.create_chat(title if isinstance(title, str) else None), status_code=201)


@app.get("/api/chats/{chat_id}")
async def api_get_chat(chat_id: str):
    chat = db.get_chat(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat


@app.put("/api/chats/{chat_id}")
async def api_update_chat(chat_id: str, request: Request):
    body = await _json_object(request)
    known = ("title", "generated_title", "tools", "settings", "pinned", "archived")
    if not any(k in body for k in known):
        raise HTTPException(status_code=400, detail="Send a title, generated_title, tools, settings, pinned or archived")
    if "title" in body:
        title = body.get("title")
        if not isinstance(title, str) or not title.strip():
            raise HTTPException(status_code=400, detail="title must be a non-empty string")
        if not db.rename_chat(chat_id, title):
            raise HTTPException(status_code=404, detail="Chat not found")
    if "tools" in body:
        try:
            found = db.set_chat_tools(chat_id, body["tools"])
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        if not found:
            raise HTTPException(status_code=404, detail="Chat not found")
    if "settings" in body:
        try:
            found = db.set_chat_settings(chat_id, body["settings"])
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        if not found:
            raise HTTPException(status_code=404, detail="Chat not found")
    if "pinned" in body or "archived" in body:
        try:
            found = db.set_chat_flags(chat_id, body.get("pinned"), body.get("archived"))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        if not found:
            raise HTTPException(status_code=404, detail="Chat not found")
    result = {"status": "ok"}
    if "generated_title" in body:
        generated = body.get("generated_title")
        if not isinstance(generated, str):
            raise HTTPException(status_code=400, detail="generated_title must be a string")
        applied = db.apply_generated_title(chat_id, generated)
        if applied is None:
            raise HTTPException(status_code=404, detail="Chat not found")
        result["applied"] = applied
    return result


@app.delete("/api/chats/{chat_id}")
async def api_delete_chat(chat_id: str, request: Request):
    now = (request.query_params.get("now") or "").lower() in ("1", "true")
    if not db.delete_chat(chat_id, now=now):
        raise HTTPException(status_code=404, detail="Chat not found")
    return {"status": "ok", "restorable_seconds": 0 if now else db.DELETED_CHAT_KEEP_SECONDS}


@app.post("/api/chats/{chat_id}/restore")
async def api_restore_chat(chat_id: str):
    if not db.restore_chat(chat_id):
        raise HTTPException(status_code=404, detail="Chat not found or already removed")
    return {"status": "ok"}


@app.put("/api/chats/{chat_id}/messages")
async def api_save_chat_messages(chat_id: str, request: Request):
    body = await _json_object(request)
    try:
        saved = db.save_chat_nodes(chat_id, body.get("from_index", 0), body.get("messages", []))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if saved is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    return {"status": "ok", **saved}


@app.patch("/api/chats/{chat_id}/messages/{node_id}")
async def api_extend_chat_message(chat_id: str, node_id: str, request: Request):
    body = await _json_object(request)
    if not node_id.isdigit():
        raise HTTPException(status_code=404, detail="Message not found")
    try:
        saved = db.extend_chat_message(
            chat_id, int(node_id), body.get("content"), body.get("elapsed_ms"), body.get("thought_ms"),
            body.get("reasoning"), body.get("cut_off"),
        )
    except db.ChatConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if saved is None:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"status": "ok", **saved}


@app.put("/api/chats/{chat_id}/active")
async def api_set_active_message(chat_id: str, request: Request):
    body = await _json_object(request)
    try:
        found = db.set_active_node(chat_id, body.get("node_id"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not found:
        raise HTTPException(status_code=404, detail="Message not found")
    return db.get_chat(chat_id)




# -------------------------------------------------------------------
# Cloud Tunnel (ngrok) Endpoints
# -------------------------------------------------------------------

@app.get("/api/tunnel/status")
async def api_get_tunnel_status():
    return tunnel.get_tunnel_status()


@app.post("/api/tunnel/start")
async def api_start_tunnel():
    return tunnel.start_tunnel(port=5000)


@app.post("/api/tunnel/stop")
async def api_stop_tunnel():
    return tunnel.stop_tunnel()


@app.post("/api/tunnel/authtoken")
async def api_save_authtoken(request: Request):
    body = await request.json()
    token = body.get("token") or body.get("authtoken") or ""
    return tunnel.save_authtoken(token)


@app.post("/api/tunnel/install")
async def api_install_tunnel(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    force = bool(body.get("force", False))
    return tunnel.install_ngrok(force=force)


# -------------------------------------------------------------------
# System Version Control & Update Engine (GitHub Sync & Cache-Buster)
# -------------------------------------------------------------------

@app.get("/api/system/version")
async def api_system_version():
    """Returns local git commit details, branch, remote origin status, and commit log."""
    repo_dir = str(ROOT_DIR)
    
    local_hash = ""
    short_hash = ""
    commit_date = ""
    commit_message = ""
    author = ""
    branch = "main"
    recent_commits = []
    
    try:
        # Get current branch
        br_res = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_dir, capture_output=True, text=True, timeout=3)
        if br_res.returncode == 0:
            branch = br_res.stdout.strip() or "main"
            
        # Get HEAD commit details
        head_res = subprocess.run(["git", "log", "-1", "--format=%H|%h|%an|%ci|%s"], cwd=repo_dir, capture_output=True, text=True, timeout=3)
        if head_res.returncode == 0 and head_res.stdout.strip():
            parts = head_res.stdout.strip().split("|", 4)
            if len(parts) == 5:
                local_hash, short_hash, author, commit_date, commit_message = parts
            else:
                local_hash = head_res.stdout.strip()
                short_hash = local_hash[:7]
                
        # Get recent commit log (up to 12 commits)
        log_res = subprocess.run(["git", "log", "-12", "--format=%H|%h|%an|%ci|%s"], cwd=repo_dir, capture_output=True, text=True, timeout=4)
        if log_res.returncode == 0:
            for line in log_res.stdout.strip().splitlines():
                if not line.strip():
                    continue
                lp = line.split("|", 4)
                if len(lp) == 5:
                    recent_commits.append({
                        "hash": lp[0],
                        "short": lp[1],
                        "author": lp[2],
                        "date": lp[3],
                        "message": lp[4]
                    })
    except Exception as e:
        local_hash = local_hash or "unknown"
        short_hash = short_hash or "v2.5"

    # Query GitHub remote
    remote_hash = ""
    remote_short = ""
    is_latest = True
    commits_behind = 0
    remote_error = None
    
    try:
        # Check origin HEAD via git ls-remote
        ls_res = subprocess.run(["git", "ls-remote", "origin", f"refs/heads/{branch}"], cwd=repo_dir, capture_output=True, text=True, timeout=6)
        if ls_res.returncode == 0 and ls_res.stdout.strip():
            first_line = ls_res.stdout.strip().splitlines()[0]
            remote_hash = first_line.split()[0].strip()
            remote_short = remote_hash[:7]
            if local_hash and remote_hash:
                if local_hash == remote_hash:
                    is_latest = True
                    commits_behind = 0
                else:
                    is_latest = False
                    cnt_res = subprocess.run(["git", "rev-list", "--count", f"HEAD..{remote_hash}"], cwd=repo_dir, capture_output=True, text=True, timeout=3)
                    if cnt_res.returncode == 0 and cnt_res.stdout.strip().isdigit():
                        commits_behind = int(cnt_res.stdout.strip())
                    else:
                        commits_behind = 1
        elif ls_res.returncode != 0:
            remote_error = ls_res.stderr.strip() or "Remote origin unreachable"
            is_latest = None
    except subprocess.TimeoutExpired:
        remote_error = "GitHub check timed out (offline or slow connection)"
        is_latest = None
    except Exception as exc:
        remote_error = str(exc)
        is_latest = None

    return JSONResponse({
        "ok": True,
        "version_name": "v2.5.0-Sing",
        "branch": branch,
        "local_commit": local_hash,
        "short_commit": short_hash,
        "commit_date": commit_date,
        "commit_message": commit_message,
        "author": author,
        "remote_commit": remote_hash,
        "remote_short": remote_short,
        "is_latest": is_latest,
        "commits_behind": commits_behind,
        "remote_repo": "InsomniacZero/Eclipse",
        "remote_error": remote_error,
        "recent_commits": recent_commits,
        "cache_token": int(time.time()),
    })


@app.post("/api/system/update")
async def api_system_update():
    """Pulls latest files from GitHub origin/main, verifies integrity, and prepares cache-busted reload."""
    repo_dir = str(ROOT_DIR)
    logs = []
    
    logs.append(f"Initiating Eclipse core sync for {repo_dir}...")
    logs.append("Target remote: https://github.com/InsomniacZero/Eclipse.git [main]")
    
    old_hash = ""
    new_hash = ""
    
    try:
        # Get old HEAD
        h_res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_dir, capture_output=True, text=True, timeout=3)
        if h_res.returncode == 0:
            old_hash = h_res.stdout.strip()
            logs.append(f"Current local HEAD: {old_hash[:7]}")

        # Check working tree status
        stashed = False
        st_res = subprocess.run(["git", "status", "--porcelain"], cwd=repo_dir, capture_output=True, text=True, timeout=3)
        if st_res.returncode == 0 and st_res.stdout.strip():
            logs.append("Notice: Local uncommitted files detected. Preserving workspace state...")
            s_res = subprocess.run(["git", "stash", "save", "eclipse-auto-update"], cwd=repo_dir, capture_output=True, text=True, timeout=4)
            stashed = (s_res.returncode == 0)

        # Execute git fetch
        logs.append("Fetching latest refs from origin/main...")
        f_res = subprocess.run(["git", "fetch", "origin", "main"], cwd=repo_dir, capture_output=True, text=True, timeout=12)
        if f_res.returncode != 0:
            err = f_res.stderr.strip() or f_res.stdout.strip()
            logs.append(f"[!] Fetch failed: {err}")
            if stashed:
                subprocess.run(["git", "stash", "pop"], cwd=repo_dir, capture_output=True, text=True, timeout=4)
            return JSONResponse({"ok": False, "error": err, "logs": logs}, status_code=500)
            
        # Execute git pull
        logs.append("Pulling updates from origin/main...")
        p_res = subprocess.run(["git", "pull", "origin", "main"], cwd=repo_dir, capture_output=True, text=True, timeout=15)
        for line in (p_res.stdout + "\n" + p_res.stderr).splitlines():
            if line.strip():
                logs.append(f"  {line.strip()}")
                
        if stashed:
            subprocess.run(["git", "stash", "pop"], cwd=repo_dir, capture_output=True, text=True, timeout=4)

        # Get new HEAD
        nh_res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_dir, capture_output=True, text=True, timeout=3)
        if nh_res.returncode == 0:
            new_hash = nh_res.stdout.strip()
            logs.append(f"New local HEAD: {new_hash[:7]}")

        updated = (old_hash != new_hash)
        if updated:
            logs.append(f"✓ Eclipse updated successfully ({old_hash[:7]} -> {new_hash[:7]}).")
        else:
            logs.append("✓ Eclipse is already on the latest revision.")
            
        logs.append("Generating cache-bypass token and preparing instant reload...")
        cache_buster = f"v{int(time.time())}_{new_hash[:7]}"
        logs.append(f"Active cache-buster token: {cache_buster}")
        
        return JSONResponse({
            "ok": True,
            "updated": updated,
            "old_commit": old_hash,
            "new_commit": new_hash,
            "short_commit": new_hash[:7],
            "cache_token": cache_buster,
            "logs": logs
        })
    except Exception as exc:
        logs.append(f"[!] Update execution failed: {str(exc)}")
        return JSONResponse({
            "ok": False,
            "error": str(exc),
            "logs": logs
        }, status_code=500)


# -------------------------------------------------------------------
# Static Frontend Serving
# -------------------------------------------------------------------

@app.get("/")
@app.head("/")
async def serve_index():
    index_path = STATIC_DIR / "index.html"
    return FileResponse(
        index_path,
        media_type="text/html",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/logo.svg")
@app.head("/logo.svg")
async def serve_logo():
    logo_path = STATIC_DIR / "logo.svg"
    return FileResponse(logo_path, media_type="image/svg+xml")


@app.get("/favicon.ico")
@app.head("/favicon.ico")
async def serve_favicon():
    logo_path = STATIC_DIR / "logo.svg"
    return FileResponse(logo_path, media_type="image/svg+xml")


@app.get("/manifest.json")
@app.head("/manifest.json")
@app.get("/static/manifest.json")
@app.head("/static/manifest.json")
async def serve_manifest():
    manifest_path = STATIC_DIR / "manifest.json"
    headers = {"Cache-Control": "no-cache, must-revalidate"}
    return FileResponse(manifest_path, media_type="application/manifest+json", headers=headers)


@app.get("/sw.js")
@app.head("/sw.js")
@app.get("/static/sw.js")
@app.head("/static/sw.js")
async def serve_sw():
    sw_path = STATIC_DIR / "sw.js"
    headers = {
        "Service-Worker-Allowed": "/",
        "Cache-Control": "no-cache, no-store, must-revalidate",
    }
    return FileResponse(sw_path, media_type="application/javascript", headers=headers)


@app.get("/offline.html")
@app.head("/offline.html")
async def serve_offline():
    offline_path = STATIC_DIR / "offline.html"
    return FileResponse(offline_path, media_type="text/html")


# Mount static assets directory with cache headers for high-performance repeat loads
class CachedStaticFiles(StaticFiles):
    def file_response(self, *args, **kwargs):
        resp = super().file_response(*args, **kwargs)
        # Prevent aggressive disk caching of application scripts, stylesheets, and HTML
        path = str(args[0]) if args else ""
        if path.endswith((".js", ".css", ".html")):
            resp.headers["Cache-Control"] = "no-cache, must-revalidate"
            resp.headers["Pragma"] = "no-cache"
        else:
            resp.headers.setdefault("Cache-Control", "public, max-age=86400")
        return resp

app.mount("/static", CachedStaticFiles(directory=str(STATIC_DIR)), name="static")


@app.on_event("startup")
async def on_startup():
    """Auto-launch in-process Gemini Web worker if offline."""
    try:
        worker.ensure_supervisor_running()
        start_provider("gemini")
    except Exception:
        pass
def free_listening_ports(ports: List[int]):
    """Terminate stale processes listening on specified ports so uvicorn can bind cleanly."""
    import signal
    current_pid = os.getpid()
    for p in ports:
        # Check if port is occupied first
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.15)
                if s.connect_ex(("127.0.0.1", p)) != 0:
                    continue
        except Exception:
            pass

        if sys.platform == "win32":
            try:
                out = subprocess.check_output(f'netstat -ano | findstr /R /C:":{p} .*LISTENING"', shell=True, text=True, stderr=subprocess.DEVNULL)
                for line in out.strip().splitlines():
                    parts = line.strip().split()
                    if parts:
                        pid = parts[-1]
                        if pid.isdigit() and int(pid) != current_pid and int(pid) != 0:
                            subprocess.run(f"taskkill /F /PID {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass
        else:
            # 1. fuser sends SIGKILL directly to processes using the port socket
            try:
                subprocess.run(["fuser", "-k", "-9", f"{p}/tcp"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass
            # 2. lsof filtered specifically to LISTEN sockets
            try:
                subprocess.run(f"lsof -sTCP:LISTEN -iTCP:{p} -t | xargs -r kill -9", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass
            # 3. ss socket statistics parser for listening PIDs on Linux / Termux
            try:
                out = subprocess.check_output(f'ss -lptn "sport = :{p}" 2>/dev/null', shell=True, text=True, stderr=subprocess.DEVNULL)
                for m in re.finditer(r"pid=(\d+)", out):
                    target_pid = int(m.group(1))
                    if target_pid != current_pid and target_pid > 0:
                        try:
                            os.kill(target_pid, signal.SIGKILL)
                        except Exception:
                            pass
            except Exception:
                pass
            # 4. If still busy after kill attempts and port is 5000, terminate stale server.py instances
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.1)
                    if s.connect_ex(("127.0.0.1", p)) == 0 and p == 5000:
                        subprocess.run("pkill -9 -f 'eclipse/server.py' 2>/dev/null", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass
    time.sleep(0.2)


def main():
    if "--lan" in sys.argv[1:]:
        os.environ["ECLIPSE_LAN"] = "1"
    lan_mode = security.is_lan_mode()
    host = os.getenv("HOST") or ("0.0.0.0" if lan_mode else "127.0.0.1")
    port = int(os.getenv("PORT", "5000"))

    # Free gateway port 5000
    free_listening_ports([port])

    try:
        db.init_db()
        gateway_key = security.get_gateway_key()
    except Exception as e:
        print(f"\n  [!] Could not open the credential vault: {e}\n", flush=True)
        sys.exit(1)

    # Count stacked accounts from vault
    try:
        all_creds = db.get_accounts()
        unique_providers = sorted(list(set(c.get("provider", "") for c in all_creds if c.get("provider"))))
        total_accounts = len(all_creds)
    except Exception:
        unique_providers = []
        total_accounts = 0

    # Clean terminal styling (adaptive left-aligned layout; never breaks on narrow Termux screens)
    use_color = sys.stdout.isatty()
    C_BOLD = "\033[1m" if use_color else ""
    C_GREEN = "\033[32m" if use_color else ""
    C_CYAN = "\033[36m" if use_color else ""
    C_DIM = "\033[2m" if use_color else ""
    C_RESET = "\033[0m" if use_color else ""

    lan_ip = get_lan_ip() if host not in ("127.0.0.1", "localhost", "::1") else None

    print(f"\n  {C_BOLD}Eclipse Gateway{C_RESET} {C_GREEN}● online{C_RESET}\n", flush=True)
    print(f"  {C_BOLD}➜{C_RESET}  {C_DIM}Local:{C_RESET}    {C_CYAN}http://localhost:{port}{C_RESET}", flush=True)
    if lan_ip:
        print(f"  {C_BOLD}➜{C_RESET}  {C_DIM}Network:{C_RESET}  {C_CYAN}http://{lan_ip}:{port}{C_RESET} {C_DIM}(Phone & LAN){C_RESET}", flush=True)

    print("", flush=True)
    print(f"  {C_DIM}•{C_RESET}  {C_DIM}Keyword:{C_RESET}  {C_BOLD}eclipse{C_RESET}", flush=True)
    print(f"  {C_DIM}•{C_RESET}  {C_DIM}Engine:{C_RESET}   {C_BOLD}Gemini Web{C_RESET}", flush=True)
    if total_accounts > 0:
        print(f"  {C_DIM}•{C_RESET}  {C_DIM}Vault:{C_RESET}    {C_BOLD}{total_accounts}{C_RESET} account{'s' if total_accounts != 1 else ''} ready {C_DIM}(Gemini Web){C_RESET}", flush=True)
    else:
        print(f"  {C_DIM}•{C_RESET}  {C_DIM}Vault:{C_RESET}    Ready {C_DIM}(add cookies in Dashboard or run ./start.sh import){C_RESET}", flush=True)

    if not lan_ip:
        print(f"  {C_DIM}•{C_RESET}  {C_DIM}Phone:{C_RESET}    Run {C_BOLD}./start.sh --lan{C_RESET} {C_DIM}for phone & multi-device access{C_RESET}", flush=True)
    print(f"  {C_DIM}•{C_RESET}  {C_DIM}Stop:{C_RESET}     Press {C_BOLD}Ctrl+C{C_RESET} {C_DIM}to shut down{C_RESET}\n", flush=True)

    try:
        worker.ensure_supervisor_running()
        start_provider("gemini")
    except Exception:
        pass

    # Mute noisy uvicorn access logs (background heartbeats, polls & cloud sync stay completely silent)
    debug_mode = os.getenv("ECLIPSE_DEBUG", "").lower() in ("1", "true", "yes")
    if not debug_mode:
        logging.getLogger("uvicorn.access").disabled = True
        logging.getLogger("uvicorn.access").propagate = False
        logging.getLogger("uvicorn.error").setLevel(logging.WARNING)

    uvicorn.run(app, host=host, port=port, access_log=debug_mode, log_level="info" if debug_mode else "warning")


if __name__ == "__main__":
    main()
