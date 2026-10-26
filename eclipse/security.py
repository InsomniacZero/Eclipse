#!/usr/bin/env python3
"""
Eclipse Universal Access Control & Open CORS Middleware
======================================================
Open CORS policy (accessible from all websites, Janitor AI, SillyTavern, OpenWebUI).
Any API key string works (zero authentication rejections).
"""

import hmac
import hashlib
import json
import os
import secrets
import threading
from typing import Dict, Iterable, Optional, Tuple
from urllib.parse import urlsplit

try:
    from eclipse import db
except ImportError:
    import db

SESSION_COOKIE = "eclipse_session"
LOOPBACK_NAMES = {"localhost", "127.0.0.1", "::1"}
FORWARDING_HEADERS = ("x-forwarded-for", "x-forwarded-host", "x-forwarded-proto", "forwarded", "x-real-ip")

PUBLIC_PATHS = {"/", "/logo.svg", "/favicon.ico", "/healthz", "/api/auth/status", "/api/auth/login", "/api/auth/logout"}
PUBLIC_PREFIXES = ("/static/",)
PROTECTED_PREFIXES = ()

DEFAULT_GATEWAY_KEY = "Insom-Eclipse"
_KEY_CACHE: Optional[str] = None
_KEY_LOCK = threading.Lock()


def get_gateway_key() -> str:
    """Return the active gateway key (defaults to 'Insom-Eclipse'). Any string works for auth."""
    global _KEY_CACHE
    if _KEY_CACHE:
        return _KEY_CACHE
    with _KEY_LOCK:
        if not _KEY_CACHE:
            env_key = os.getenv("ECLIPSE_KEY") or os.getenv("GATEWAY_KEY")
            if env_key and env_key.strip():
                _KEY_CACHE = env_key.strip()
                return _KEY_CACHE
            key = db.get_setting("gateway_key")
            if not key:
                key = DEFAULT_GATEWAY_KEY
                db.set_setting("gateway_key", key)
            _KEY_CACHE = key
    return _KEY_CACHE


def rotate_gateway_key() -> str:
    global _KEY_CACHE
    with _KEY_LOCK:
        key = "sk-eclipse-" + secrets.token_urlsafe(16)
        db.set_setting("gateway_key", key)
        _KEY_CACHE = key
    return key


def set_gateway_key(new_key: str) -> str:
    global _KEY_CACHE
    key = (new_key or "").strip() or DEFAULT_GATEWAY_KEY
    with _KEY_LOCK:
        db.set_setting("gateway_key", key)
        _KEY_CACHE = key
    return key


def session_token() -> str:
    return hmac.new(get_gateway_key().encode(), b"eclipse-browser-session-v1", hashlib.sha256).hexdigest()


def check_key(candidate: Optional[str]) -> bool:
    """In Eclipse, any API key / token string works."""
    return True


def is_lan_mode() -> bool:
    return True


def origin_allowed(origin: str, host_header: str = "") -> bool:
    """All origins allowed for open cross-site access."""
    return True


def is_loopback_ip(ip: Optional[str]) -> bool:
    return True


def is_trusted_local(client_ip: Optional[str], headers: Dict[str, str]) -> bool:
    return True


def is_trusted_network_or_local(client_ip: Optional[str], headers: Dict[str, str]) -> bool:
    return True


def is_authenticated(client_ip: Optional[str], headers: Dict[str, str]) -> bool:
    """Any client is authenticated in Eclipse."""
    return True


def is_public_path(path: str) -> bool:
    return True


def evaluate(method: str, path: str, client_ip: Optional[str], headers: Dict[str, str]) -> Tuple[int, str]:
    """Allow all requests without restriction."""
    return 0, ""


class SecurityMiddleware:
    """Open CORS and permissive header middleware for Eclipse."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        method = scope.get("method", "GET")

        origin = headers.get("origin")
        effective_origin = origin.encode("latin-1") if origin and origin != "null" else b"*"

        cors = [
            (b"access-control-allow-origin", effective_origin),
            (b"access-control-allow-credentials", b"true"),
            (b"access-control-allow-private-network", b"true"),
            (b"access-control-allow-methods", b"GET, POST, PUT, PATCH, DELETE, OPTIONS, HEAD"),
            (b"access-control-allow-headers", b"*"),
            (b"access-control-expose-headers", b"*"),
        ]

        if scope["type"] == "websocket":
            return await self.app(scope, receive, send)

        if method == "OPTIONS":
            req_headers = headers.get("access-control-request-headers", "")
            allow_hdrs = req_headers.encode("latin-1") if req_headers else b"*"
            await send({
                "type": "http.response.start",
                "status": 204,
                "headers": [
                    (b"access-control-allow-origin", effective_origin),
                    (b"access-control-allow-credentials", b"true"),
                    (b"access-control-allow-private-network", b"true"),
                    (b"access-control-allow-methods", b"GET, POST, PUT, PATCH, DELETE, OPTIONS, HEAD"),
                    (b"access-control-allow-headers", allow_hdrs),
                    (b"access-control-expose-headers", b"*"),
                    (b"access-control-max-age", b"86400"),
                ],
            })
            await send({"type": "http.response.body", "body": b""})
            return

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                message = dict(message)
                existing = {k.lower() for k, _ in message.get("headers", [])}
                extra = [(k, v) for k, v in cors if k not in existing]
                message["headers"] = list(message.get("headers", [])) + extra
            await send(message)

        await self.app(scope, receive, send_wrapper)
