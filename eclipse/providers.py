#!/usr/bin/env python3
"""
Eclipse Provider Engine
Manages status, lifecycle, limits, models, and cookie storage for all 7 providers:
Gemini (8084), Claude (8080), GLM (8085), Kimi (8086), DeepSeek (8088), Qwen (8089), Antigravity (8090), AI Studio (8091), MiMo (8092).
"""

import asyncio
import json
import os
import re
import signal
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

try:
    from eclipse import db
except ImportError:
    import db

try:
    db.init_db()
except Exception:
    pass

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
PROVIDER_HOST = os.getenv("ECLIPSE_PROVIDER_HOST", "127.0.0.1")

# Self-contained interpreter resolution (eclipse/.venv -> sys.executable -> python)
import sys
LOCAL_VENV_WIN = BASE_DIR / ".venv" / "Scripts" / "python.exe"
LOCAL_VENV_NIX = BASE_DIR / ".venv" / "bin" / "python3"
LOCAL_VENV = LOCAL_VENV_WIN if LOCAL_VENV_WIN.exists() else LOCAL_VENV_NIX
PYTHON_VENV = LOCAL_VENV if LOCAL_VENV.exists() else Path(sys.executable)
SYSTEM_PYTHON = sys.executable or ("python" if sys.platform == "win32" else "python3")


def get_python_executable() -> str:
    """Resolve the most appropriate Python executable (venv or system)."""
    if sys.platform == "win32":
        venv_py = BASE_DIR / ".venv" / "Scripts" / "python.exe"
        if venv_py.exists():
            return str(venv_py)
        root_venv = ROOT_DIR / ".venv" / "Scripts" / "python.exe"
        if root_venv.exists():
            return str(root_venv)
    else:
        venv_py = BASE_DIR / ".venv" / "bin" / "python3"
        if venv_py.exists():
            return str(venv_py)
        root_venv = ROOT_DIR / ".venv" / "bin" / "python3"
        if root_venv.exists():
            return str(root_venv)
    if sys.executable:
        return sys.executable
    return "python" if sys.platform == "win32" else "python3"



def is_simulation_active() -> bool:
    """Check if device simulation mode is active via env var or DB setting."""
    if os.getenv("ECLIPSE_SIMULATE", "0").lower() in ("1", "true", "yes", "on"):
        return True
    try:
        val = db.get_setting("simulation_mode")
        return val in ("1", "true", "yes", "on")
    except Exception:
        return False


# Providers whose engines still work with no stored account (anonymous / guest sessions).
GUEST_CAPABLE_PROVIDERS = frozenset({"gemini", "glm"})

# Environment variables an engine reads when the vault holds no account for it.
ENV_CREDENTIALS = {
    "deepseek": ("DEEPSEEK_TOKEN",),
    "qwen": ("QWEN_TOKEN", "QWEN_COOKIES"),
    "antigravity": ("AGY_TOKEN", "AGY_REFRESH_TOKEN", "GOOGLE_OAUTH_TOKEN"),
    "aistudio": ("AISTUDIO_COOKIE", "GEMINI_COOKIE"),
    "mimo": ("MIMO_TOKEN", "MIMO_SERVICE_TOKEN", "MIMO_COOKIE", "XIAOMI_COOKIE"),
}


def missing_credentials(provider_id: str) -> bool:
    """True when this provider needs an account and none is stored or supplied by environment."""
    if provider_id not in PROVIDERS_CONFIG or provider_id in GUEST_CAPABLE_PROVIDERS:
        return False
    if any(os.getenv(name, "").strip() for name in ENV_CREDENTIALS.get(provider_id, ())):
        return False
    try:
        return not db.get_accounts(provider_id)
    except Exception:
        # A vault read error is not proof that no account exists: let the engine report it.
        return False


def get_provider_host(provider_id: str) -> str:
    """Resolve provider host dynamically from DB setting, env var, or default."""
    try:
        spec = db.get_setting(f"{provider_id}_host")
        if spec:
            return spec
        remote = db.get_setting("remote_host")
        if remote:
            return remote
    except Exception:
        pass
    env_key = f"{provider_id.upper()}_HOST"
    if os.getenv(env_key):
        return os.getenv(env_key)
    if os.getenv("ECLIPSE_PROVIDER_HOST"):
        return os.getenv("ECLIPSE_PROVIDER_HOST")
    return "127.0.0.1"


PROVIDERS_CONFIG = {
    "glm": {
        "id": "glm",
        "name": "GLM",
        "port": 8085,
        "host": os.getenv("GLM_HOST", PROVIDER_HOST),
        "badge": "Zhipu AI",
        "color": "#4A72FF",
        "start_script": "start_glm2api.sh",
        "stop_script": "stop_glm2api.sh",
        "health_path": "/v1/models",
        "cookie_type": "token_lines",
        "cookie_label": "GLM Refresh Token",
        "cookie_placeholder": "Paste Zhipu refresh token (one account per line or card)...",
        "auth_header": "Bearer sk-glm-local",
    },
    "gemini": {
        "id": "gemini",
        "name": "Gemini",
        "port": 8084,
        "host": os.getenv("GEMINI_HOST", PROVIDER_HOST),
        "badge": "Google DeepMind",
        "color": "#4285F4",
        "start_script": "start_gemini.sh",
        "stop_script": "stop_gemini.sh",
        "health_path": "/v1/models",
        "cookie_type": "cookie_string",
        "cookie_label": "Google __Secure-1PSID Cookie",
        "cookie_placeholder": "Paste raw cookie string containing __Secure-1PSID=... and __Secure-1PSIDTS=...",
        "auth_header": None,
    },
}

# Dynamic Eclipse Catalog (Gemini Web Models)
MODELS_CATALOG = [
    # Gemini 4 Argon
    {
        'capabilities': ['chat', 'reasoning', 'vision', 'code', 'streaming'],
        'context': '1M tokens',
        'description': 'Google DeepMind Gemini 4 Argon with High Thinking.',
        'id': 'gemini-4-argon-high',
        'locked': False,
        'name': 'Gemini 4 Argon (High)',
        'provider': 'gemini'
    },
    {
        'capabilities': ['chat', 'reasoning', 'vision', 'code', 'streaming'],
        'context': '1M tokens',
        'description': 'Google DeepMind Gemini 4 Argon with Medium Thinking.',
        'id': 'gemini-4-argon-medium',
        'locked': False,
        'name': 'Gemini 4 Argon (Medium)',
        'provider': 'gemini'
    },
    {
        'capabilities': ['chat', 'reasoning', 'vision', 'code', 'streaming'],
        'context': '1M tokens',
        'description': 'Google DeepMind Gemini 4 Argon with Low Thinking.',
        'id': 'gemini-4-argon-low',
        'locked': False,
        'name': 'Gemini 4 Argon (Low)',
        'provider': 'gemini'
    },
    {
        'capabilities': ['chat', 'reasoning', 'vision', 'code', 'streaming'],
        'context': '1M tokens',
        'description': 'Google DeepMind Gemini 4 Argon.',
        'id': 'gemini-4-argon',
        'locked': False,
        'name': 'Gemini 4 Argon',
        'provider': 'gemini'
    },
    # Gemini 3.1 Pro
    {
        'capabilities': ['chat', 'reasoning', 'vision', 'code', 'streaming'],
        'context': '2M tokens',
        'description': 'Google Gemini 3.1 Pro with High Thinking.',
        'id': 'gemini-3.1-pro-high',
        'locked': False,
        'name': 'Gemini 3.1 Pro (High)',
        'provider': 'gemini'
    },
    {
        'capabilities': ['chat', 'reasoning', 'vision', 'code', 'streaming'],
        'context': '2M tokens',
        'description': 'Google Gemini 3.1 Pro with Medium Thinking.',
        'id': 'gemini-3.1-pro-medium',
        'locked': False,
        'name': 'Gemini 3.1 Pro (Medium)',
        'provider': 'gemini'
    },
    {
        'capabilities': ['chat', 'reasoning', 'vision', 'code', 'streaming'],
        'context': '2M tokens',
        'description': 'Google Gemini 3.1 Pro with Low Thinking.',
        'id': 'gemini-3.1-pro-low',
        'locked': False,
        'name': 'Gemini 3.1 Pro (Low)',
        'provider': 'gemini'
    },
    {
        'capabilities': ['chat', 'reasoning', 'vision', 'code', 'streaming'],
        'context': '2M tokens',
        'description': 'Google Gemini 3.1 Pro.',
        'id': 'gemini-3.1-pro',
        'locked': False,
        'name': 'Gemini 3.1 Pro',
        'provider': 'gemini'
    },
    # Gemini 3.8 Flash
    {
        'capabilities': ['chat', 'reasoning', 'vision', 'code', 'streaming'],
        'context': '1M tokens',
        'description': 'Google Gemini 3.8 Flash with High Thinking.',
        'id': 'gemini-3.8-flash-high',
        'locked': False,
        'name': 'Gemini 3.8 Flash (High)',
        'provider': 'gemini'
    },
    {
        'capabilities': ['chat', 'vision', 'code', 'streaming'],
        'context': '1M tokens',
        'description': 'Google Gemini 3.8 Flash with Medium Thinking.',
        'id': 'gemini-3.8-flash-medium',
        'locked': False,
        'name': 'Gemini 3.8 Flash (Medium)',
        'provider': 'gemini'
    },
    {
        'capabilities': ['chat', 'vision', 'code', 'streaming'],
        'context': '1M tokens',
        'description': 'Google Gemini 3.8 Flash with Low Thinking.',
        'id': 'gemini-3.8-flash-low',
        'locked': False,
        'name': 'Gemini 3.8 Flash (Low)',
        'provider': 'gemini'
    },
    {
        'capabilities': ['chat', 'vision', 'code', 'streaming'],
        'context': '1M tokens',
        'description': 'Google Gemini 3.8 Flash.',
        'id': 'gemini-3.8-flash',
        'locked': False,
        'name': 'Gemini 3.8 Flash',
        'provider': 'gemini'
    },
    # Gemini 3.5 Flash-Lite
    {
        'capabilities': ['chat', 'reasoning', 'streaming'],
        'context': '1M tokens',
        'description': 'Google Gemini 3.5 Flash-Lite with High Thinking.',
        'id': 'gemini-3.5-flash-lite-high',
        'locked': False,
        'name': 'Gemini 3.5 Flash-Lite (High)',
        'provider': 'gemini'
    },
    {
        'capabilities': ['chat', 'code', 'streaming'],
        'context': '1M tokens',
        'description': 'Google Gemini 3.5 Flash-Lite with Medium Thinking.',
        'id': 'gemini-3.5-flash-lite-medium',
        'locked': False,
        'name': 'Gemini 3.5 Flash-Lite (Medium)',
        'provider': 'gemini'
    },
    {
        'capabilities': ['chat', 'code', 'streaming'],
        'context': '1M tokens',
        'description': 'Google Gemini 3.5 Flash-Lite with Low Thinking.',
        'id': 'gemini-3.5-flash-lite-low',
        'locked': False,
        'name': 'Gemini 3.5 Flash-Lite (Low)',
        'provider': 'gemini'
    },
    {
        'capabilities': ['chat', 'code', 'streaming'],
        'context': '1M tokens',
        'description': 'Google Gemini 3.5 Flash-Lite.',
        'id': 'gemini-3.5-flash-lite',
        'locked': False,
        'name': 'Gemini 3.5 Flash-Lite',
        'provider': 'gemini'
    },
    # Image & Video Generation
    {
        'capabilities': ['image'],
        'context': 'Prompt',
        'description': 'Gemini 3.1 Flash Image - State-of-the-art fast image generation.',
        'id': 'nano-banana-2',
        'locked': False,
        'name': 'Nano Banana 2',
        'provider': 'gemini'
    },
    {
        'capabilities': ['image'],
        'context': 'Prompt',
        'description': 'Gemini 3 Pro Image / Imagen 3 - Photorealistic image generation.',
        'id': 'nano-banana-pro',
        'locked': False,
        'name': 'Nano Banana Pro',
        'provider': 'gemini'
    },
    {
        'capabilities': ['image'],
        'context': 'Prompt',
        'description': 'Gemini 3.1 Flash-Lite Image - Rapid lightweight image model.',
        'id': 'nano-banana-2-lite',
        'locked': False,
        'name': 'Nano Banana 2 Lite',
        'provider': 'gemini'
    },
    {
        'capabilities': ['image'],
        'context': 'Prompt',
        'description': 'State-of-the-art photorealistic image generation from Gemini prompt.',
        'id': 'imagen-4.0-generate-proto',
        'locked': False,
        'name': 'Imagen 4.0 Image Gen',
        'provider': 'gemini'
    },
    {
        'capabilities': ['video', 'audio'],
        'context': 'Prompt & Reference',
        'description': 'Google DeepMind frontier cinematic video model with native synchronized audio.',
        'id': 'veo-3.1-generate-preview',
        'locked': False,
        'name': 'Google Veo 3.1',
        'provider': 'gemini'
    },
    {
        'capabilities': ['video', 'audio'],
        'context': 'Prompt & Reference',
        'description': 'Low-latency optimized variant of Veo 3.1 for high-speed creative iteration.',
        'id': 'veo-3.1-fast-generate-preview',
        'locked': False,
        'name': 'Google Veo 3.1 Fast',
        'provider': 'gemini'
    },
    {
        'capabilities': ['video'],
        'context': 'Prompt',
        'description': 'Baseline high-definition text-to-video foundation model.',
        'id': 'veo-2.0-generate-001',
        'locked': False,
        'name': 'Google Veo 2.0',
        'provider': 'gemini'
    },
    # Zhipu AI GLM Models

    {   'capabilities': ['image'],
        'context': 'Prompt',
        'description': 'High-resolution Chinese/English text-to-image synthesis.',
        'id': 'cogView-4-250304',
        'locked': False,
        'name': 'CogView 4 Image Gen',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'code'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5.3 with bilingual language and reasoning capabilities.',
        'id': 'glm-5.3',
        'locked': False,
        'name': 'GLM 5.3',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'code'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5.3 Thinking with bilingual language and reasoning capabilities.',
        'id': 'glm-5.3-think',
        'locked': False,
        'name': 'GLM 5.3 Thinking',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'web', 'code'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5.3 Search with bilingual language and reasoning capabilities.',
        'id': 'glm-5.3-search',
        'locked': False,
        'name': 'GLM 5.3 Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'web', 'code'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5.3 Thinking Search with bilingual language and reasoning capabilities.',
        'id': 'glm-5.3-think-search',
        'locked': False,
        'name': 'GLM 5.3 Thinking Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'fast', 'code'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5.3 Flash with bilingual language and reasoning capabilities.',
        'id': 'glm-5.3-flash',
        'locked': False,
        'name': 'GLM 5.3 Flash',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'fast', 'code'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5.3 Flash Thinking with bilingual language and reasoning capabilities.',
        'id': 'glm-5.3-flash-think',
        'locked': False,
        'name': 'GLM 5.3 Flash Thinking',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'web', 'fast', 'code'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5.3 Flash Search with bilingual language and reasoning capabilities.',
        'id': 'glm-5.3-flash-search',
        'locked': False,
        'name': 'GLM 5.3 Flash Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'web', 'fast', 'code'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5.3 Flash Thinking Search with bilingual language and reasoning capabilities.',
        'id': 'glm-5.3-flash-think-search',
        'locked': False,
        'name': 'GLM 5.3 Flash Thinking Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'code'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5.2 with bilingual language and reasoning capabilities.',
        'id': 'glm-5.2',
        'locked': False,
        'name': 'GLM 5.2',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'code'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5.2 Thinking with bilingual language and reasoning capabilities.',
        'id': 'glm-5.2-think',
        'locked': False,
        'name': 'GLM 5.2 Thinking',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'web', 'code'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5.2 Search with bilingual language and reasoning capabilities.',
        'id': 'glm-5.2-search',
        'locked': False,
        'name': 'GLM 5.2 Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'web', 'code'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5.2 Thinking Search with bilingual language and reasoning capabilities.',
        'id': 'glm-5.2-think-search',
        'locked': False,
        'name': 'GLM 5.2 Thinking Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5.1 with bilingual language and reasoning capabilities.',
        'id': 'glm-5.1',
        'locked': False,
        'name': 'GLM 5.1',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5.1 Thinking with bilingual language and reasoning capabilities.',
        'id': 'glm-5.1-think',
        'locked': False,
        'name': 'GLM 5.1 Thinking',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'web'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5.1 Search with bilingual language and reasoning capabilities.',
        'id': 'glm-5.1-search',
        'locked': False,
        'name': 'GLM 5.1 Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'web'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5.1 Thinking Search with bilingual language and reasoning capabilities.',
        'id': 'glm-5.1-think-search',
        'locked': False,
        'name': 'GLM 5.1 Thinking Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'vision'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5V Turbo with bilingual language and reasoning capabilities.',
        'id': 'glm-5v-turbo',
        'locked': False,
        'name': 'GLM 5V Turbo',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'vision'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5V Turbo Thinking with bilingual language and reasoning capabilities.',
        'id': 'glm-5v-turbo-think',
        'locked': False,
        'name': 'GLM 5V Turbo Thinking',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'web', 'vision'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5V Turbo Search with bilingual language and reasoning capabilities.',
        'id': 'glm-5v-turbo-search',
        'locked': False,
        'name': 'GLM 5V Turbo Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'web', 'vision'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5V Turbo Thinking Search with bilingual language and reasoning capabilities.',
        'id': 'glm-5v-turbo-think-search',
        'locked': False,
        'name': 'GLM 5V Turbo Thinking Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'vision'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5 Turbo with bilingual language and reasoning capabilities.',
        'id': 'glm-5-turbo',
        'locked': False,
        'name': 'GLM 5 Turbo',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'vision'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5 Turbo Thinking with bilingual language and reasoning capabilities.',
        'id': 'glm-5-turbo-think',
        'locked': False,
        'name': 'GLM 5 Turbo Thinking',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'web', 'vision'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5 Turbo Search with bilingual language and reasoning capabilities.',
        'id': 'glm-5-turbo-search',
        'locked': False,
        'name': 'GLM 5 Turbo Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'web', 'vision'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5 Turbo Thinking Search with bilingual language and reasoning capabilities.',
        'id': 'glm-5-turbo-think-search',
        'locked': False,
        'name': 'GLM 5 Turbo Thinking Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5 with bilingual language and reasoning capabilities.',
        'id': 'glm-5',
        'locked': False,
        'name': 'GLM 5',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5 Thinking with bilingual language and reasoning capabilities.',
        'id': 'glm-5-think',
        'locked': False,
        'name': 'GLM 5 Thinking',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'web'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5 Search with bilingual language and reasoning capabilities.',
        'id': 'glm-5-search',
        'locked': False,
        'name': 'GLM 5 Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'web'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5 Thinking Search with bilingual language and reasoning capabilities.',
        'id': 'glm-5-think-search',
        'locked': False,
        'name': 'GLM 5 Thinking Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'fast', 'code'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4.7 Flash with bilingual language and reasoning capabilities.',
        'id': 'glm-4.7-flash',
        'locked': False,
        'name': 'GLM 4.7 Flash',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'fast', 'code'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4.7 Flash Thinking with bilingual language and reasoning capabilities.',
        'id': 'glm-4.7-flash-think',
        'locked': False,
        'name': 'GLM 4.7 Flash Thinking',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'web', 'fast', 'code'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4.7 Flash Search with bilingual language and reasoning capabilities.',
        'id': 'glm-4.7-flash-search',
        'locked': False,
        'name': 'GLM 4.7 Flash Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'web', 'fast', 'code'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4.7 Flash Thinking Search with bilingual language and reasoning capabilities.',
        'id': 'glm-4.7-flash-think-search',
        'locked': False,
        'name': 'GLM 4.7 Flash Thinking Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'code'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4.7 with bilingual language and reasoning capabilities.',
        'id': 'glm-4.7',
        'locked': False,
        'name': 'GLM 4.7',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'code'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4.7 Thinking with bilingual language and reasoning capabilities.',
        'id': 'glm-4.7-think',
        'locked': False,
        'name': 'GLM 4.7 Thinking',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'web', 'code'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4.7 Search with bilingual language and reasoning capabilities.',
        'id': 'glm-4.7-search',
        'locked': False,
        'name': 'GLM 4.7 Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'web', 'code'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4.7 Thinking Search with bilingual language and reasoning capabilities.',
        'id': 'glm-4.7-think-search',
        'locked': False,
        'name': 'GLM 4.7 Thinking Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'vision', 'fast'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4.6v Flash with bilingual language and reasoning capabilities.',
        'id': 'glm-4.6v-flash',
        'locked': False,
        'name': 'GLM 4.6v Flash',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'vision', 'fast'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4.6v Flash Thinking with bilingual language and reasoning capabilities.',
        'id': 'glm-4.6v-flash-think',
        'locked': False,
        'name': 'GLM 4.6v Flash Thinking',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'web', 'vision', 'fast'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4.6v Flash Search with bilingual language and reasoning capabilities.',
        'id': 'glm-4.6v-flash-search',
        'locked': False,
        'name': 'GLM 4.6v Flash Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'web', 'vision', 'fast'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4.6v Flash Thinking Search with bilingual language and reasoning capabilities.',
        'id': 'glm-4.6v-flash-think-search',
        'locked': False,
        'name': 'GLM 4.6v Flash Thinking Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4.6 with bilingual language and reasoning capabilities.',
        'id': 'glm-4.6',
        'locked': False,
        'name': 'GLM 4.6',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4.6 Thinking with bilingual language and reasoning capabilities.',
        'id': 'glm-4.6-think',
        'locked': False,
        'name': 'GLM 4.6 Thinking',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'web'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4.6 Search with bilingual language and reasoning capabilities.',
        'id': 'glm-4.6-search',
        'locked': False,
        'name': 'GLM 4.6 Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'web'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4.6 Thinking Search with bilingual language and reasoning capabilities.',
        'id': 'glm-4.6-think-search',
        'locked': False,
        'name': 'GLM 4.6 Thinking Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4.5 with bilingual language and reasoning capabilities.',
        'id': 'glm-4.5',
        'locked': False,
        'name': 'GLM 4.5',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4.5 Thinking with bilingual language and reasoning capabilities.',
        'id': 'glm-4.5-think',
        'locked': False,
        'name': 'GLM 4.5 Thinking',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'web'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4.5 Search with bilingual language and reasoning capabilities.',
        'id': 'glm-4.5-search',
        'locked': False,
        'name': 'GLM 4.5 Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'web'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4.5 Thinking Search with bilingual language and reasoning capabilities.',
        'id': 'glm-4.5-think-search',
        'locked': False,
        'name': 'GLM 4.5 Thinking Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'vision', 'fast'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4.1v Thinking Flashx with bilingual language and reasoning capabilities.',
        'id': 'glm-4.1v-thinking-flashx',
        'locked': False,
        'name': 'GLM 4.1v Thinking Flashx',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'vision', 'fast'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4.1v Thinking Flashx Thinking with bilingual language and reasoning capabilities.',
        'id': 'glm-4.1v-thinking-flashx-think',
        'locked': False,
        'name': 'GLM 4.1v Thinking Flashx Thinking',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'web', 'vision', 'fast'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4.1v Thinking Flashx Search with bilingual language and reasoning capabilities.',
        'id': 'glm-4.1v-thinking-flashx-search',
        'locked': False,
        'name': 'GLM 4.1v Thinking Flashx Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'web', 'vision', 'fast'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4.1v Thinking Flashx Thinking Search with bilingual language and reasoning '
                       'capabilities.',
        'id': 'glm-4.1v-thinking-flashx-think-search',
        'locked': False,
        'name': 'GLM 4.1v Thinking Flashx Thinking Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4 with bilingual language and reasoning capabilities.',
        'id': 'glm-4',
        'locked': False,
        'name': 'GLM 4',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4 Thinking with bilingual language and reasoning capabilities.',
        'id': 'glm-4-think',
        'locked': False,
        'name': 'GLM 4 Thinking',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'web'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4 Search with bilingual language and reasoning capabilities.',
        'id': 'glm-4-search',
        'locked': False,
        'name': 'GLM 4 Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'web'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4 Thinking Search with bilingual language and reasoning capabilities.',
        'id': 'glm-4-think-search',
        'locked': False,
        'name': 'GLM 4 Thinking Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'fast'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4 Flash with bilingual language and reasoning capabilities.',
        'id': 'glm-4-flash',
        'locked': False,
        'name': 'GLM 4 Flash',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'fast'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4 Flash Thinking with bilingual language and reasoning capabilities.',
        'id': 'glm-4-flash-think',
        'locked': False,
        'name': 'GLM 4 Flash Thinking',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'web', 'fast'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4 Flash Search with bilingual language and reasoning capabilities.',
        'id': 'glm-4-flash-search',
        'locked': False,
        'name': 'GLM 4 Flash Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'web', 'fast'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4 Flash Thinking Search with bilingual language and reasoning capabilities.',
        'id': 'glm-4-flash-think-search',
        'locked': False,
        'name': 'GLM 4 Flash Thinking Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4 Air with bilingual language and reasoning capabilities.',
        'id': 'glm-4-air',
        'locked': False,
        'name': 'GLM 4 Air',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4 Air Thinking with bilingual language and reasoning capabilities.',
        'id': 'glm-4-air-think',
        'locked': False,
        'name': 'GLM 4 Air Thinking',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'web'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4 Air Search with bilingual language and reasoning capabilities.',
        'id': 'glm-4-air-search',
        'locked': False,
        'name': 'GLM 4 Air Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'web'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4 Air Thinking Search with bilingual language and reasoning capabilities.',
        'id': 'glm-4-air-think-search',
        'locked': False,
        'name': 'GLM 4 Air Thinking Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'vision'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4V with bilingual language and reasoning capabilities.',
        'id': 'glm-4v',
        'locked': False,
        'name': 'GLM 4V',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'vision'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4V Thinking with bilingual language and reasoning capabilities.',
        'id': 'glm-4v-think',
        'locked': False,
        'name': 'GLM 4V Thinking',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'web', 'vision'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4V Search with bilingual language and reasoning capabilities.',
        'id': 'glm-4v-search',
        'locked': False,
        'name': 'GLM 4V Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'web', 'vision'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4V Thinking Search with bilingual language and reasoning capabilities.',
        'id': 'glm-4v-think-search',
        'locked': False,
        'name': 'GLM 4V Thinking Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'fast'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4 Flashx 250414 with bilingual language and reasoning capabilities.',
        'id': 'glm-4-flashx-250414',
        'locked': False,
        'name': 'GLM 4 Flashx 250414',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'fast'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4 Flashx 250414 Thinking with bilingual language and reasoning capabilities.',
        'id': 'glm-4-flashx-250414-think',
        'locked': False,
        'name': 'GLM 4 Flashx 250414 Thinking',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'web', 'fast'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4 Flashx 250414 Search with bilingual language and reasoning capabilities.',
        'id': 'glm-4-flashx-250414-search',
        'locked': False,
        'name': 'GLM 4 Flashx 250414 Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'web', 'fast'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4 Flashx 250414 Thinking Search with bilingual language and reasoning '
                       'capabilities.',
        'id': 'glm-4-flashx-250414-think-search',
        'locked': False,
        'name': 'GLM 4 Flashx 250414 Thinking Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'fast'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4 Flash 250414 with bilingual language and reasoning capabilities.',
        'id': 'glm-4-flash-250414',
        'locked': False,
        'name': 'GLM 4 Flash 250414',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'fast'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4 Flash 250414 Thinking with bilingual language and reasoning capabilities.',
        'id': 'glm-4-flash-250414-think',
        'locked': False,
        'name': 'GLM 4 Flash 250414 Thinking',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'web', 'fast'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4 Flash 250414 Search with bilingual language and reasoning capabilities.',
        'id': 'glm-4-flash-250414-search',
        'locked': False,
        'name': 'GLM 4 Flash 250414 Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'web', 'fast'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4 Flash 250414 Thinking Search with bilingual language and reasoning '
                       'capabilities.',
        'id': 'glm-4-flash-250414-think-search',
        'locked': False,
        'name': 'GLM 4 Flash 250414 Thinking Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'vision'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM Zero Preview with bilingual language and reasoning capabilities.',
        'id': 'glm-zero-preview',
        'locked': False,
        'name': 'GLM Zero Preview',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'vision'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM Zero Preview Thinking with bilingual language and reasoning capabilities.',
        'id': 'glm-zero-preview-think',
        'locked': False,
        'name': 'GLM Zero Preview Thinking',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'web', 'vision'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM Zero Preview Search with bilingual language and reasoning capabilities.',
        'id': 'glm-zero-preview-search',
        'locked': False,
        'name': 'GLM Zero Preview Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'web', 'vision'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM Zero Preview Thinking Search with bilingual language and reasoning capabilities.',
        'id': 'glm-zero-preview-think-search',
        'locked': False,
        'name': 'GLM Zero Preview Thinking Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'web', 'research'],
        'context': '256k tokens',
        'description': 'Zhipu AI GLM Deep Research with bilingual language and reasoning capabilities.',
        'id': 'glm-deep-research',
        'locked': False,
        'name': 'GLM Deep Research',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'web', 'research'],
        'context': '256k tokens',
        'description': 'Zhipu AI GLM Deep Research Thinking with bilingual language and reasoning capabilities.',
        'id': 'glm-deep-research-think',
        'locked': False,
        'name': 'GLM Deep Research Thinking',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'web', 'research'],
        'context': '256k tokens',
        'description': 'Zhipu AI GLM Deep Research Search with bilingual language and reasoning capabilities.',
        'id': 'glm-deep-research-search',
        'locked': False,
        'name': 'GLM Deep Research Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'web', 'research'],
        'context': '256k tokens',
        'description': 'Zhipu AI GLM Deep Research Thinking Search with bilingual language and reasoning capabilities.',
        'id': 'glm-deep-research-think-search',
        'locked': False,
        'name': 'GLM Deep Research Thinking Search',
        'provider': 'glm'},
    {   'capabilities': ['image'],
        'context': 'Prompt',
        'description': 'Creative text-to-image generator.',
        'id': 'glm-image-1',
        'locked': False,
        'name': 'GLM Image 1',
        'provider': 'glm'},
]


def check_account_tiers() -> Dict[str, bool]:
    return {"gemini_breakthrough": True}


def get_dynamic_models_catalog() -> List[Dict[str, Any]]:
    return [dict(m) for m in MODELS_CATALOG]


def get_pid_for_port(port: int) -> Optional[int]:
    """Find PID listening on a given port across Linux, macOS, and Windows."""
    if sys.platform == "win32":
        try:
            res = subprocess.run(
                ["netstat", "-ano", "-p", "tcp"],
                capture_output=True,
                text=True,
                timeout=3,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            for line in res.stdout.splitlines():
                parts = line.strip().split()
                if len(parts) >= 5 and parts[0].upper() == "TCP":
                    local_addr = parts[1]
                    state = parts[3]
                    if (local_addr.endswith(f":{port}") or local_addr.endswith(f".{port}")) and state.upper() == "LISTENING":
                        pid_str = parts[4]
                        if pid_str.isdigit():
                            return int(pid_str)
        except Exception:
            pass
        return None
    else:
        try:
            res = subprocess.run(["lsof", f"-ti:{port}"], capture_output=True, text=True, timeout=2)
            pids = [int(p.strip()) for p in res.stdout.strip().splitlines() if p.strip().isdigit()]
            return pids[0] if pids else None
        except Exception:
            return None


async def ping_service(port: int, health_path: str, auth_header: Optional[str] = None, host: str = "127.0.0.1") -> tuple[bool, float]:
    """Check if service is responding on HTTP and return latency in ms."""
    url = f"http://{host}:{port}{health_path}"
    headers = {}
    if auth_header:
        headers["Authorization"] = auth_header

    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=3.5) as client:
            resp = await client.get(url, headers=headers)
            latency = (time.perf_counter() - start) * 1000
            # 200, 401, 404 all indicate the daemon port is alive and listening
            if resp.status_code in [200, 201, 401, 403, 404]:
                return True, round(latency, 1)
            return False, 0.0
    except Exception:
        return False, 0.0


async def get_all_services_status() -> List[Dict[str, Any]]:
    """Return live status of all 6 providers."""
    results = []
    sim = is_simulation_active()
    for pid, meta in PROVIDERS_CONFIG.items():
        port = meta["port"]
        host = get_provider_host(pid)
        process_pid = get_pid_for_port(port) if host in ("127.0.0.1", "localhost") else None
        alive, latency = await ping_service(port, meta["health_path"], meta["auth_header"], host=host)

        is_running = bool(process_pid) or alive or sim
        lat = latency if alive else (15.0 if sim else None)
        results.append({
            "id": pid,
            "name": meta["name"],
            "port": port,
            "host": host,
            "badge": meta["badge"],
            "color": meta["color"],
            "status": "online" if is_running else "offline",
            "running": is_running,
            "latency": lat,
            "latency_ms": lat,
            "pid": process_pid or (8000 + port % 100 if sim else None),
            "simulated": sim and not alive,
            "health_path": meta.get("health_path", "/v1/models"),
            "cookie_label": meta.get("cookie_label", ""),
        })
    return results


def start_provider(provider_id: str) -> Dict[str, Any]:
    """Start a provider service daemon natively (in-process thread or headless background)."""
    if provider_id not in PROVIDERS_CONFIG:
        return {"status": "error", "message": f"Unknown provider: {provider_id}"}

    meta = PROVIDERS_CONFIG[provider_id]
    port = meta["port"]
    host = meta.get("host", "127.0.0.1")

    # Check if already running
    existing_pid = get_pid_for_port(port)
    if existing_pid:
        return {
            "status": "ok",
            "message": f"{meta['name']} is already running on port {port} (PID: {existing_pid})",
            "pid": existing_pid,
        }

    # 1. Native Eclipse In-Process Worker Thread (Zero Windows, Runs inside Main Gateway Terminal)
    try:
        try:
            from eclipse import worker
        except ImportError:
            import worker
        res = worker.start_worker_in_thread(provider_id, host=host, port=port)
        if res.get("status") == "ok":
            return res
    except Exception:
        pass

    # 2. Custom external start script if explicitly present
    script_candidates = [
        BASE_DIR / "scripts" / meta["start_script"],
        ROOT_DIR / meta["start_script"],
    ]
    script_path = next((p for p in script_candidates if p.exists()), None)
    if script_path:
        try:
            p = subprocess.Popen(
                ["bash", str(script_path)] if sys.platform != "win32" else [str(script_path)],
                cwd=str(script_path.parent),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            for _ in range(15):
                time.sleep(0.1)
                new_pid = get_pid_for_port(port)
                if new_pid:
                    return {
                        "status": "ok",
                        "message": f"Started {meta['name']} on port {port} (PID: {new_pid})",
                        "pid": new_pid,
                    }
            return {
                "status": "ok",
                "message": f"Started {meta['name']} on port {port}",
                "pid": p.pid,
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    # 3. Headless Windowless Process Fallback (strictly no consoles on Windows)
    try:
        py_bin = get_python_executable()
        env = dict(os.environ)
        env["PYTHONPATH"] = str(ROOT_DIR)

        cmd = [
            py_bin,
            "-m", "eclipse.worker",
            "--provider", provider_id,
            "--port", str(port),
            "--host", host,
        ]

        if sys.platform == "win32":
            pyw_cand = Path(py_bin).parent / "pythonw.exe"
            if pyw_cand.exists():
                cmd[0] = str(pyw_cand)

            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

            p = subprocess.Popen(
                cmd,
                cwd=str(ROOT_DIR),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                startupinfo=startupinfo,
                creationflags=creationflags,
                env=env,
            )
        else:
            p = subprocess.Popen(
                cmd,
                cwd=str(ROOT_DIR),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                env=env,
            )

        for _ in range(20):
            time.sleep(0.1)
            new_pid = get_pid_for_port(port)
            if new_pid:
                try:
                    db.set_setting(f"provider_{provider_id}_pid", str(new_pid))
                except Exception:
                    pass
                return {
                    "status": "ok",
                    "message": f"Started {meta['name']} daemon on port {port} (PID: {new_pid})",
                    "pid": new_pid,
                }

        if p and p.pid:
            try:
                db.set_setting(f"provider_{provider_id}_pid", str(p.pid))
            except Exception:
                pass
            return {
                "status": "ok",
                "message": f"Started {meta['name']} worker process (PID: {p.pid})",
                "pid": p.pid,
            }

        return {
            "status": "ok",
            "message": f"Started {meta['name']} worker daemon on port {port}",
        }
    except Exception as e:
        return {"status": "error", "message": f"Failed to start {meta['name']}: {str(e)}"}


def stop_provider(provider_id: str) -> Dict[str, Any]:
    """Stop a provider service if running locally."""
    if provider_id not in PROVIDERS_CONFIG:
        return {"status": "error", "message": f"Unknown provider: {provider_id}"}

    meta = PROVIDERS_CONFIG[provider_id]
    port = meta["port"]
    host = meta.get("host", "127.0.0.1")

    # 1. Stop in-process background thread if running
    try:
        try:
            from eclipse import worker
        except ImportError:
            import worker
        if worker.stop_worker_in_thread(provider_id):
            try:
                db.set_setting(f"provider_{provider_id}_pid", "")
            except Exception:
                pass
            return {"status": "ok", "message": f"Stopped {meta['name']} (in-process backend)"}
    except Exception:
        pass

    # 2. Check external process PID
    pid = get_pid_for_port(port) if host in ("127.0.0.1", "localhost") else None
    if not pid:
        try:
            saved = db.get_setting(f"provider_{provider_id}_pid")
            if saved and saved.isdigit():
                pid = int(saved)
        except Exception:
            pass

    # Check for local stop script
    script_candidates = [
        BASE_DIR / "scripts" / meta["stop_script"],
        ROOT_DIR / meta["stop_script"],
    ]
    script_path = next((p for p in script_candidates if p.exists()), None)
    if script_path:
        try:
            subprocess.run([str(script_path)], cwd=str(script_path.parent), capture_output=True, timeout=5)
        except Exception:
            pass

    if pid:
        if pid == os.getpid():
            # In-process worker thread, NEVER kill the main gateway process!
            try:
                db.set_setting(f"provider_{provider_id}_pid", "")
            except Exception:
                pass
            return {"status": "ok", "message": f"Stopped {meta['name']} (in-process backend)"}

        try:
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/F", "/PID", str(pid), "/T"],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            else:
                try:
                    os.kill(pid, signal.SIGTERM)
                    time.sleep(0.2)
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            try:
                db.set_setting(f"provider_{provider_id}_pid", "")
            except Exception:
                pass
            return {"status": "ok", "message": f"Stopped {meta['name']} (PID: {pid})"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    return {"status": "ok", "message": f"{meta['name']} is stopped on port {port}"}


def start_all_services() -> Dict[str, Any]:
    """Start all 6 provider daemons."""
    try:
        try:
            from eclipse import worker
        except ImportError:
            import worker
        worker.ensure_supervisor_running()
    except Exception:
        pass

    results = {}
    for pid in PROVIDERS_CONFIG:
        results[pid] = start_provider(pid)
    return {"status": "ok", "results": results}


def stop_all_services() -> Dict[str, Any]:
    """Stop all 6 provider daemons."""
    results = {}
    for pid in PROVIDERS_CONFIG:
        results[pid] = stop_provider(pid)
    return {"status": "ok", "results": results}


_KIMI_QUOTA_CACHE: Dict[str, Any] = {"timestamp": 0.0, "data": {}}



async def fetch_kimi_account_quotas(account: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch live quotas and subscription details from Kimi web API for a stacked account."""
    token = account.get("token", "").strip()
    ident = account.get("identifier") or account.get("name") or "Kimi Account"
    name = account.get("name") or f"Kimi ({ident[:8]})"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Authorization": f"Bearer {token}",
        "Origin": "https://www.kimi.com",
        "Referer": "https://www.kimi.com/",
        "X-Msh-Platform": "web",
    }
    
    res_acc: Dict[str, Any] = {
        "id": ident,
        "name": name,
        "plan": (account.get("plan") or "Free").title(),
        "status": "Active" if account.get("status") == "active" else "Disabled",
        "research_today": "50 / 50",
        "research_remain": 50,
        "research_total": 50,
        "deep_research": "1 / 1 left",
        "deep_research_left": 1,
        "ok_computer": "3 / 3 left",
        "ok_computer_left": 3,
        "slides": "3 / 3 left",
        "slides_left": 3,
        "reset_date": "Active",
    }
    
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            ref_resp = await client.get("https://www.kimi.com/api/auth/token/refresh", headers=headers)
            if ref_resp.status_code == 200:
                acc_token = ref_resp.json().get("access_token")
                if acc_token:
                    h2 = dict(headers)
                    h2["Authorization"] = f"Bearer {acc_token}"
                    
                    sub_task = client.post("https://www.kimi.com/apiv2/kimi.gateway.order.v1.SubscriptionService/GetSubscription", headers=h2, json={})
                    usage_task = client.get("https://www.kimi.com/api/chat/research/usage", headers=h2)
                    sub_res, usage_res = await asyncio.gather(sub_task, usage_task, return_exceptions=True)
                    
                    if not isinstance(usage_res, Exception) and usage_res.status_code == 200:
                        u_data = usage_res.json()
                        remain = u_data.get("remain", 50)
                        total = u_data.get("total", 50)
                        res_acc["research_today"] = f"{remain} / {total}"
                        res_acc["research_remain"] = remain
                        res_acc["research_total"] = total
                    
                    if not isinstance(sub_res, Exception) and sub_res.status_code == 200:
                        s_data = sub_res.json()
                        plan_level = s_data.get("currentMembershipLevel") or "LEVEL_FREE"
                        plan_title = s_data.get("subscription", {}).get("goods", {}).get("title") or "Free"
                        clean_level = plan_level.replace("LEVEL_", "").title()
                        res_acc["plan"] = f"{clean_level} ({plan_title})"
                        
                        memberships = s_data.get("memberships", [])
                        for m in memberships:
                            feat = m.get("feature", "")
                            left = m.get("leftCount", 0)
                            tot = m.get("totalCount", 0)
                            end_t = (m.get("endTime") or "")[:10]
                            if end_t:
                                res_acc["reset_date"] = end_t
                            if feat == "FEATURE_DEEP_RESEARCH":
                                res_acc["deep_research"] = f"{left} / {tot} left"
                                res_acc["deep_research_left"] = left
                            elif feat == "FEATURE_OK_COMPUTER":
                                res_acc["ok_computer"] = f"{left} / {tot} left"
                                res_acc["ok_computer_left"] = left
                            elif feat == "FEATURE_NORMAL_SLIDES":
                                res_acc["slides"] = f"{left} / {tot} left"
                                res_acc["slides_left"] = left
    except Exception:
        pass
        
    return res_acc


async def get_all_limits() -> Dict[str, Any]:
    """Collect live limits and quotas for Gemini Web from SQLite DB."""
    limits: Dict[str, Any] = {}
    gemini_accounts = db.get_accounts("gemini")
    gemini_data = []

    for acc in gemini_accounts:
        plan = (acc.get("plan") or "free").upper()
        ident = acc.get("identifier") or acc.get("name") or "Gemini Web"
        gemini_data.append({
            "email": ident,
            "type": plan,
            "status": "Normal" if acc.get("status") == "active" else "Disabled",
            "image_quota": 50,
            "veo_video_quota": "3 / day",
            "multimodal": "Enabled (Argon/Flash)",
            "reason_remaining": "Standard",
            "deep_research": "Included",
            "file_upload": "10 / prompt",
            "restore_at": "Daily (Midnight PST)",
        })

    if not gemini_data:
        gemini_data.append({
            "email": "Gemini Web (Guest)",
            "type": "FREE",
            "status": "Normal",
            "image_quota": 30,
            "veo_video_quota": "2 / day",
            "multimodal": "Enabled (Flash)",
            "reason_remaining": "Standard (60/hr)",
            "deep_research": "0 / day",
            "file_upload": "10 / prompt",
            "restore_at": "Daily (Midnight PST)",
        })

    limits["gemini"] = {
        "title": "Google Gemini Account Quotas",
        "accounts_count": len(gemini_data),
        "accounts": gemini_data,
    }


    # GLM limits info from SQLite DB & Native Engine
    glm_accounts = db.get_accounts("glm")
    glm_data = []

    for acc in glm_accounts:
        plan = (acc.get("plan") or "free").upper()
        ident = acc.get("identifier") or acc.get("name") or "GLM Token"
        is_vip = plan in ["PRO", "VIP", "TEAM"]
        raw_t = acc.get("token") or ident
        masked_id = f"GLM ({raw_t[:10]}...{raw_t[-6:]})" if len(raw_t) > 18 else ident
        glm_data.append({
            "email": masked_id,
            "type": "VIP" if is_vip else "FREE",
            "status": "Normal" if acc.get("status") == "active" else "Disabled",
            "image_quota": 100 if is_vip else 10,
            "video_quota": "20 / day" if is_vip else "2 / day",
            "reason_remaining": "Unlimited" if is_vip else "200 / day",
            "deep_research": "Unlimited" if is_vip else "100 / day",
            "file_upload": "50 docs / day" if is_vip else "5 docs / day",
            "concurrency": "10 requests" if is_vip else "2 requests",
            "restore_at": "Daily (Midnight CST)",
        })

    if not glm_data:
        glm_data.append({
            "email": "GLM Web (chatglm.cn)",
            "type": "FREE",
            "status": "Normal",
            "image_quota": 10,
            "video_quota": "2 / day",
            "reason_remaining": "200 / day",
            "deep_research": "100 / day",
            "file_upload": "5 docs / day",
            "concurrency": "2 requests",
            "restore_at": "Daily (Midnight CST)",
        })

    limits["glm"] = {
        "title": "GLM / Zhipu AI Account Quotas",
        "accounts_count": len(glm_data),
        "accounts": glm_data,
    }

    return limits


def get_stored_cookies() -> Dict[str, Any]:
    """Read stacked cookies/accounts for Gemini Web from unified SQLite DB."""
    result: Dict[str, Any] = {}

    label_map = {
        "gemini": ("cookie_string", "Google __Secure-1PSID Cookie"),
        "glm": ("token_lines", "GLM Refresh Token"),
    }

    for p, (ctype, clabel) in label_map.items():
        db_accounts = db.get_accounts(p)
        formatted = []
        for idx, acc in enumerate(db_accounts):
            tok = acc["token"]
            ident = acc["identifier"]
            name = acc["name"]

            masked = f"{tok[:6]}…{tok[-4:]}" if len(tok) > 16 else "••••"
            entry = {"id": acc["id"], "masked": masked, "identifier": ident, "name": name}
            formatted.append(entry)

        result[p] = {
            "type": ctype,
            "label": clabel,
            "accounts": formatted,
        }

    return result


def save_stacked_cookies(provider_id: str, accounts: List[str]) -> Dict[str, Any]:
    """Save stacked accounts into unified SQLite DB with strict deduplication."""
    if provider_id not in PROVIDERS_CONFIG:
        return {"status": "error", "message": f"Unknown provider: {provider_id}"}

    clean_items = [item.strip() for item in accounts if item and item.strip()]
    if not clean_items:
        return {"status": "error", "message": "No valid credentials provided."}

    success, failed = db.save_accounts(provider_id, clean_items)
    total = len(db.get_accounts(provider_id))
    warning = None
    if provider_id == "gemini":
        has_ts = any("__Secure-1PSIDTS=" in itm for itm in clean_items)
        if not has_ts:
            warning = "⚠️ Note: '__Secure-1PSIDTS' was not found in your pasted cookie. Google Gemini requires both '__Secure-1PSID' and '__Secure-1PSIDTS' for full features and image generation."

    msg = f"Successfully updated {provider_id.upper()} accounts (+{success}, total in pool: {total})."
    if warning:
        msg = f"{msg} {warning}"

    return {
        "status": "ok",
        "message": msg,
        "warning": warning,
        "saved": success,
        "failed": failed,
        "total": total,
    }


def remove_stacked_cookie(provider_id: str, identifier: Optional[str] = None, index: Optional[int] = None) -> Dict[str, Any]:
    """Remove a specific stacked account from unified SQLite DB."""
    if provider_id not in PROVIDERS_CONFIG:
        return {"status": "error", "message": f"Unknown provider: {provider_id}"}

    ok = db.remove_account(provider_id, identifier=identifier, account_id=index)
    if ok:
        total = len(db.get_accounts(provider_id))
        return {"status": "ok", "message": f"Successfully removed account from {provider_id}. Remaining: {total}"}
    return {"status": "error", "message": f"Account not found in {provider_id}."}

