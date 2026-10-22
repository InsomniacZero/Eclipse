#!/usr/bin/env python3
"""
Eclipse Unified Provider Worker Daemon
==========================================
A lightweight, 100% self-contained micro-server providing native backend daemons
for each AI provider (Gemini, Claude, Kimi, GLM, DeepSeek, Qwen, Antigravity, AI Studio, MiMo) across Windows,
Linux, macOS, and Android/Termux without requiring any legacy scripts or binaries.

Supports:
- Zero-Window in-process background threading mode (all in 1 terminal)
- Standalone headless background mode (Windows pythonw / SW_HIDE)
- /healthz and /v1/models (OpenAI format)
- /v1/chat/completions (streaming SSE & standard JSON)
- /v1/images/generations
- Automatic credential loading from Eclipse SQLite vault
"""

import argparse
import asyncio
import http.server
import json
import os
import socketserver
import sys
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

# Ensure Eclipse root is in python path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(CURRENT_DIR)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

try:
    from eclipse import db
    from eclipse.providers import PROVIDERS_CONFIG, MODELS_CATALOG
    from eclipse import engines
    from eclipse import security
except ImportError:
    import db
    from providers import PROVIDERS_CONFIG, MODELS_CATALOG
    import engines
    import security


# ==============================================================================
# Standard Library Threaded HTTP Worker (Zero Dependencies, Zero Terminal Windows)
# ==============================================================================

class WorkerHTTPHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        pass  # Completely quiet logging to keep main terminal clean

    @property
    def provider_id(self) -> str:
        return getattr(self.server, "provider_id", "gemini")

    @property
    def port(self) -> int:
        return getattr(self.server, "port", 8000)

    @property
    def meta(self) -> Dict[str, Any]:
        return PROVIDERS_CONFIG.get(self.provider_id, {
            "id": self.provider_id,
            "name": self.provider_id.title(),
            "badge": "AI Provider",
            "port": self.port,
        })

    def send_cors_headers(self):
        # Workers are internal backends for the gateway: no CORS headers, so browsers can never
        # read their responses. Kept as a hook so every response path stays uniform.
        self.send_header("X-Content-Type-Options", "nosniff")

    def reject_unauthorized(self) -> bool:
        """Send 401/403 and return True unless the request is from a trusted local client or has the key."""
        headers = {k.lower(): v for k, v in self.headers.items()}
        client_ip = self.client_address[0] if self.client_address else None
        if "origin" in headers or headers.get("sec-fetch-site") == "cross-site":
            status, msg = 403, "Browser requests are not accepted by Eclipse workers"
        elif security.is_authenticated(client_ip, headers):
            return False
        else:
            status, msg = 401, "Eclipse gateway key required"
        try:
            payload = json.dumps({"error": {"message": msg, "code": status}}).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass
        return True

    def do_OPTIONS(self):
        try:
            self.send_response(403)
            self.send_header("Content-Length", "0")
            self.end_headers()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass

    def do_GET(self):
        if self.reject_unauthorized():
            return
        try:
            path = self.path.split("?")[0]
            pid = self.provider_id
            meta = self.meta
            port = self.port

            if path in ("/healthz", "/health"):
                payload = json.dumps({
                    "status": "ok",
                    "provider": pid,
                    "name": meta["name"],
                    "port": port,
                    "timestamp": int(time.time()),
                }).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_cors_headers()
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(payload)

            elif path in ("/v1/models", "/models"):
                matching = [
                    {
                        "id": m["id"],
                        "object": "model",
                        "created": int(time.time()),
                        "owned_by": pid,
                        "permission": [],
                        "root": m["id"],
                        "parent": None,
                    }
                    for m in MODELS_CATALOG
                    if m.get("provider") == pid
                ]
                if not matching:
                    matching = [{
                        "id": f"{pid}-default",
                        "object": "model",
                        "created": int(time.time()),
                        "owned_by": pid,
                        "permission": [],
                        "root": f"{pid}-default",
                        "parent": None,
                    }]
                payload = json.dumps({"object": "list", "data": matching}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_cors_headers()
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(payload)

            else:
                payload = json.dumps({
                    "service": f"Eclipse {meta['name']} Worker",
                    "status": "online",
                    "provider": pid,
                    "port": port,
                }).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_cors_headers()
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass

    def do_POST(self):
        if self.reject_unauthorized():
            return
        try:
            path = self.path.split("?")[0]
            pid = self.provider_id
            port = self.port

            content_length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(content_length).decode("utf-8", errors="ignore") if content_length > 0 else "{}"
            try:
                body = json.loads(raw_body)
            except Exception:
                body = {}

            if path == "/v1/chat/completions":
                model = body.get("model", f"{pid}-default")
                messages = body.get("messages", [])
                is_stream = body.get("stream", False)

                if not messages:
                    prompt_input = body.get("prompt", "")
                    if prompt_input:
                        messages = [{"role": "user", "content": prompt_input}]

                accounts = []
                try:
                    accounts = db.get_accounts(pid)
                except Exception:
                    pass

                if is_stream:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Connection", "close")
                    self.send_cors_headers()
                    self.end_headers()
                    self.close_connection = True

                    async def run_stream():
                        try:
                            async for chunk in engines.stream_chat(pid, model, messages, accounts=accounts, stream=True):
                                line = f"data: {json.dumps(chunk)}\n\n"
                                try:
                                    self.wfile.write(line.encode("utf-8"))
                                    self.wfile.flush()
                                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                                    break
                            try:
                                self.wfile.write(b"data: [DONE]\n\n")
                                self.wfile.flush()
                            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                                pass
                        except Exception as inner_err:
                            try:
                                err_chunk = {
                                    "id": f"chatcmpl-err",
                                    "object": "chat.completion.chunk",
                                    "created": int(time.time()),
                                    "model": model,
                                    "choices": [{"index": 0, "delta": {"content": f"\n\n[Worker Stream Error: {str(inner_err)}]"}, "finish_reason": "error"}],
                                }
                                self.wfile.write(f"data: {json.dumps(err_chunk)}\n\n".encode("utf-8"))
                                self.wfile.write(b"data: [DONE]\n\n")
                                self.wfile.flush()
                            except Exception:
                                pass

                    try:
                        asyncio.run(run_stream())
                    except Exception:
                        pass
                else:
                    async def run_gen():
                        return await engines.generate_chat(pid, model, messages, accounts=accounts)

                    try:
                        result = asyncio.run(run_gen())
                        payload = json.dumps(result).encode("utf-8")
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.send_cors_headers()
                        self.send_header("Content-Length", str(len(payload)))
                        self.send_header("Connection", "close")
                        self.end_headers()
                        self.wfile.write(payload)
                    except Exception as e:
                        err_payload = json.dumps({"error": str(e)}).encode("utf-8")
                        self.send_response(500)
                        self.send_header("Content-Type", "application/json")
                        self.send_cors_headers()
                        self.send_header("Content-Length", str(len(err_payload)))
                        self.send_header("Connection", "close")
                        self.end_headers()
                        self.wfile.write(err_payload)

            elif path == "/v1/images/generations":
                # Route to the actual engine (same as the gateway does) so workers
                # can serve image requests independently when needed.
                prompt = body.get("prompt", "Generate an image")
                model = body.get("model", f"{pid}-default")
                reference_image = body.get("reference_image") or body.get("referenceImage")

                if reference_image:
                    if reference_image.startswith("data:"):
                        try:
                            header, b64_data = reference_image.split(",", 1)
                            img_mime = header.split(":")[1].split(";")[0]
                        except Exception:
                            b64_data = reference_image
                            img_mime = "image/png"
                    else:
                        b64_data = reference_image
                        img_mime = "image/png"
                    user_content = [
                        {"type": "image_url", "image_url": {"url": f"data:{img_mime};base64,{b64_data}"}},
                        {"type": "text", "text": prompt},
                    ]
                else:
                    user_content = prompt

                messages = [{"role": "user", "content": user_content}]

                accounts = []
                try:
                    accounts = db.get_accounts(pid)
                except Exception:
                    pass

                try:
                    async def run_img_gen():
                        return await engines.generate_chat(pid, model, messages, accounts=accounts)

                    result = asyncio.run(run_img_gen())
                    content_str = ""
                    choices = result.get("choices", [])
                    if choices:
                        msg_obj = choices[0].get("message", {})
                        content_str = msg_obj.get("content", "")

                    import re as _re
                    uri_pat = _re.compile(r"data:(image/[^;]+);base64,([A-Za-z0-9+/=]+)")
                    matches = uri_pat.findall(content_str)
                    if matches:
                        found_mime, b64_payload = matches[0]
                        result_payload = json.dumps({
                            "created": int(time.time()),
                            "data": [{"b64_json": b64_payload, "revised_prompt": prompt}],
                        }).encode("utf-8")
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.send_cors_headers()
                        self.send_header("Content-Length", str(len(result_payload)))
                        self.send_header("Connection", "close")
                        self.end_headers()
                        self.wfile.write(result_payload)
                    else:
                        error_hint = content_str.strip()[:400] if content_str.strip() else "Image generation returned no image data."
                        err_payload = json.dumps({"error": error_hint}).encode("utf-8")
                        self.send_response(502)
                        self.send_header("Content-Type", "application/json")
                        self.send_cors_headers()
                        self.send_header("Content-Length", str(len(err_payload)))
                        self.send_header("Connection", "close")
                        self.end_headers()
                        self.wfile.write(err_payload)
                except Exception as img_err:
                    err_payload = json.dumps({"error": str(img_err)}).encode("utf-8")
                    self.send_response(502)
                    self.send_header("Content-Type", "application/json")
                    self.send_cors_headers()
                    self.send_header("Content-Length", str(len(err_payload)))
                    self.send_header("Connection", "close")
                    self.end_headers()
                    self.wfile.write(err_payload)

            else:
                self.send_response(404)
                self.end_headers()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass


class ThreadedWorkerServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 128

    def __init__(self, host: str, port: int, provider_id: str):
        self.host = host
        self.port = port
        self.provider_id = provider_id
        super().__init__((host, port), WorkerHTTPHandler)

    def handle_error(self, request, client_address):
        # Gracefully suppress broken pipes and client resets
        exctype, value, tb = sys.exc_info()
        if exctype in (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, TimeoutError):
            return
        super().handle_error(request, client_address)


# ==============================================================================
# In-Process Thread Management & Auto-Healing Watchdog
# ==============================================================================

# Structure: { provider_id: { "server": server, "thread": thread, "host": host, "port": port, "active": True } }
_RUNNING_WORKERS: Dict[str, Dict[str, Any]] = {}
_WORKER_LOCK = threading.Lock()
_WATCHDOG_THREAD: Optional[threading.Thread] = None
_WATCHDOG_ACTIVE = False


def _server_worker_loop(server_info: Dict[str, Any]):
    """Keep worker HTTP server running continuously with auto-restart on socket errors."""
    server = server_info.get("server")
    pid = server_info.get("provider_id", "worker")
    port = server_info.get("port", 0)

    while server_info.get("active", True):
        try:
            if server:
                server.serve_forever(poll_interval=0.5)
        except Exception:
            if not server_info.get("active", True):
                break
            time.sleep(0.5)


def _watchdog_loop():
    """Background supervisor thread that ensures all active workers stay alive and heals any drops."""
    global _WATCHDOG_ACTIVE
    while _WATCHDOG_ACTIVE:
        try:
            time.sleep(5.0)
            with _WORKER_LOCK:
                for pid, info in list(_RUNNING_WORKERS.items()):
                    if not info.get("active", False):
                        continue
                    thread = info.get("thread")
                    port = info.get("port")
                    host = info.get("host", "127.0.0.1")

                    # Check if thread died or server is closed
                    if thread is None or not thread.is_alive():
                        try:
                            old_srv = info.get("server")
                            if old_srv:
                                try:
                                    old_srv.shutdown()
                                    old_srv.server_close()
                                except Exception:
                                    pass
                            new_server = ThreadedWorkerServer(host, port, pid)
                            info["server"] = new_server
                            new_thread = threading.Thread(
                                target=_server_worker_loop,
                                args=(info,),
                                daemon=True,
                                name=f"Worker-{pid}-{port}",
                            )
                            info["thread"] = new_thread
                            new_thread.start()
                        except Exception:
                            pass
        except Exception:
            pass


def ensure_supervisor_running():
    """Start the background self-healing watchdog thread if not already running."""
    global _WATCHDOG_THREAD, _WATCHDOG_ACTIVE
    with _WORKER_LOCK:
        if not _WATCHDOG_ACTIVE or _WATCHDOG_THREAD is None or not _WATCHDOG_THREAD.is_alive():
            _WATCHDOG_ACTIVE = True
            _WATCHDOG_THREAD = threading.Thread(
                target=_watchdog_loop,
                daemon=True,
                name="Eclipse-Worker-Watchdog",
            )
            _WATCHDOG_THREAD.start()


def start_worker_in_thread(provider_id: str, host: str = "127.0.0.1", port: Optional[int] = None) -> Dict[str, Any]:
    """
    Start a provider worker inside a background daemon thread with supervisor monitoring.
    Guarantees ZERO external terminal windows open on Windows or any OS.
    Automatically monitored and auto-healed by the supervisor watchdog.
    """
    ensure_supervisor_running()
    with _WORKER_LOCK:
        if port is None:
            port = PROVIDERS_CONFIG.get(provider_id, {}).get("port", 8000)

        # Check if actively running in-process
        existing = _RUNNING_WORKERS.get(provider_id)
        if existing and existing.get("active") and existing.get("thread") and existing["thread"].is_alive():
            return {
                "status": "ok",
                "message": f"{provider_id.upper()} daemon already running (in-process backend)",
                "pid": os.getpid(),
                "in_process": True,
            }
        elif existing:
            # Thread died or inactive; cleanly close old socket
            try:
                old_srv = existing.get("server")
                if old_srv:
                    old_srv.shutdown()
                    old_srv.server_close()
            except Exception:
                pass
            _RUNNING_WORKERS.pop(provider_id, None)

        try:
            server = ThreadedWorkerServer(host, port, provider_id)
            info = {
                "server": server,
                "provider_id": provider_id,
                "host": host,
                "port": port,
                "active": True,
            }
            thread = threading.Thread(
                target=_server_worker_loop,
                args=(info,),
                daemon=True,
                name=f"Worker-{provider_id}-{port}",
            )
            info["thread"] = thread
            thread.start()
            _RUNNING_WORKERS[provider_id] = info

            # Save gateway PID for status checks
            try:
                db.init_db()
                db.set_setting(f"provider_{provider_id}_pid", str(os.getpid()))
            except Exception:
                pass

            meta = PROVIDERS_CONFIG.get(provider_id, {"name": provider_id.title()})
            return {
                "status": "ok",
                "message": f"Started {meta['name']} background server on port {port} (in-process backend)",
                "pid": os.getpid(),
                "in_process": True,
            }
        except Exception as e:
            return {"status": "error", "message": f"Failed to bind {provider_id} on port {port}: {str(e)}"}


def stop_worker_in_thread(provider_id: str) -> bool:
    """Stop an in-process worker thread and release the port."""
    with _WORKER_LOCK:
        info = _RUNNING_WORKERS.pop(provider_id, None)
        if info:
            info["active"] = False
            server = info.get("server")
            if server:
                try:
                    server.shutdown()
                    server.server_close()
                except Exception:
                    pass
            return True
        return False


def is_worker_in_thread(provider_id: str) -> bool:
    """Check if worker is actively running in-process."""
    with _WORKER_LOCK:
        info = _RUNNING_WORKERS.get(provider_id)
        return bool(info and info.get("active") and info.get("thread") and info["thread"].is_alive())


def get_running_thread_workers() -> List[str]:
    """List of provider IDs running in-process."""
    with _WORKER_LOCK:
        return [
            pid for pid, info in _RUNNING_WORKERS.items()
            if info.get("active") and info.get("thread") and info["thread"].is_alive()
        ]


# ==============================================================================
# Standalone CLI Entry Point
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="Eclipse Provider Worker Daemon")
    parser.add_argument("--provider", required=True, help="Provider ID (gemini, claude, kimi, glm, deepseek, qwen, antigravity, aistudio, mimo)")
    parser.add_argument("--port", type=int, required=True, help="Port to listen on")
    parser.add_argument("--host", default="127.0.0.1", help="Host address (default: 127.0.0.1)")
    args = parser.parse_args()

    pid = args.provider.lower()
    port = args.port
    host = args.host

    server = ThreadedWorkerServer(host, port, pid)
    print(f"[+] Eclipse {pid.upper()} Worker listening on {host}:{port}")
    try:
        server.serve_forever()
    except (KeyboardInterrupt, SystemExit):
        server.server_close()


if __name__ == "__main__":
    main()
