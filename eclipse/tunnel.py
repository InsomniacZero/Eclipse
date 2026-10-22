"""
Ngrok Tunnel Manager for Eclipse AI Gateway
Exposes port 9000 securely to the public internet for remote mobile/tablet use.
Native cross-platform support: Android (Termux), Linux, Windows, and macOS.
Features auto-architecture validation and [Errno 8] Exec format error self-healing.
"""

import io
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Dict, Optional, Union

import httpx

NGROK_INSPECT_URL = "http://127.0.0.1:4040/api/tunnels"
DEFAULT_PORT = 5000
SCRIPT_DIR = Path(__file__).resolve().parent
_tunnel_started_at: Optional[float] = None


def get_ngrok_process_start_time() -> Optional[float]:
    """Retrieve the real process start timestamp of the active ngrok process across Linux/Termux/macOS/Windows."""
    try:
        if sys.platform != "win32":
            res = subprocess.run(["pgrep", "-x", "ngrok"], capture_output=True, text=True, timeout=1.5)
            if res.returncode == 0:
                pids = [int(p) for p in res.stdout.split() if p.isdigit()]
                for p in pids:
                    proc_dir = f"/proc/{p}"
                    if os.path.exists(proc_dir):
                        return os.path.getmtime(proc_dir)
        else:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "(Get-Process ngrok -ErrorAction SilentlyContinue).StartTime.ToString('o')"],
                capture_output=True, text=True, timeout=2
            )
            if res.returncode == 0 and res.stdout.strip():
                from datetime import datetime
                dt = datetime.fromisoformat(res.stdout.strip())
                return dt.timestamp()
    except Exception:
        pass
    return None


def is_termux() -> bool:
    """Return True if running inside Termux on Android."""
    prefix = os.environ.get("PREFIX", "")
    return "termux" in prefix.lower() or os.path.isdir("/data/data/com.termux")


def is_binary_runnable(bin_path: Union[str, Path]) -> bool:
    """Verify that a binary can actually be executed without [Errno 8] Exec format error or crashing."""
    try:
        res = subprocess.run([str(bin_path), "version"], capture_output=True, text=True, timeout=4)
        return res.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def get_device_arch() -> str:
    """Accurately detect the exact CPU and userland architecture (64-bit vs 32-bit)."""
    is_64bit = sys.maxsize > 2**32
    machine = platform.machine().lower()

    if is_termux():
        try:
            res = subprocess.run(["dpkg", "--print-architecture"], capture_output=True, text=True, timeout=2)
            if res.returncode == 0:
                darch = res.stdout.strip().lower()
                if darch in ("arm64", "aarch64"):
                    return "arm64"
                elif darch in ("arm", "armhf", "armeabi", "armeabi-v7a"):
                    return "arm"
                elif darch in ("amd64", "x86_64"):
                    return "amd64"
                elif darch in ("i686", "x86", "i386"):
                    return "386"
        except Exception:
            pass

    if "aarch64" in machine or "arm64" in machine or "armv8" in machine:
        return "arm64" if is_64bit else "arm"
    elif "arm" in machine:
        return "arm"
    elif "x86_64" in machine or "amd64" in machine:
        return "amd64" if is_64bit else "386"
    return "arm64" if (is_64bit and ("arm" in machine or "aarch" in machine)) else machine


def get_ngrok_bin_path() -> Optional[str]:
    """Find a verified, runnable ngrok binary on the system or in local eclipse/bin."""
    bin_name = "ngrok.exe" if sys.platform == "win32" else "ngrok"
    candidates = []

    # 1. System PATH
    found = shutil.which("ngrok") or shutil.which("ngrok.exe")
    if found:
        candidates.append(found)

    # 2. Termux environment path
    prefix = os.environ.get("PREFIX")
    if prefix:
        candidates.append(str(Path(prefix) / "bin" / bin_name))

    # 3. Local eclipse/bin directory
    candidates.append(str(SCRIPT_DIR / "bin" / bin_name))

    # 4. Standard user home directories
    home = Path.home()
    candidates.append(str(home / ".local" / "bin" / bin_name))
    candidates.append(str(home / "bin" / bin_name))

    if sys.platform == "win32":
        local_app = os.environ.get("LOCALAPPDATA", "")
        app_data = os.environ.get("APPDATA", "")
        if local_app:
            candidates.append(str(Path(local_app) / "ngrok" / bin_name))
            candidates.append(str(Path(local_app) / "Programs" / "ngrok" / bin_name))
        if app_data:
            candidates.append(str(Path(app_data) / "ngrok" / bin_name))

    # Check candidates: MUST BE RUNNABLE without [Errno 8] Exec format error
    for cand in candidates:
        p = Path(cand)
        if p.is_file() and (sys.platform == "win32" or os.access(p, os.X_OK)):
            if is_binary_runnable(cand):
                p_str = str(p.parent)
                if p_str not in os.environ.get("PATH", ""):
                    os.environ["PATH"] = p_str + os.pathsep + os.environ.get("PATH", "")
                return str(p)

    return None


def check_ngrok_installed() -> bool:
    """Check if a verified, runnable ngrok executable is present."""
    return get_ngrok_bin_path() is not None


def get_ngrok_download_info(arch_override: Optional[str] = None) -> Dict[str, str]:
    """Determine the official Equinox download URL and format for this system architecture."""
    sys_plat = sys.platform
    machine = arch_override or get_device_arch()
    base = "https://bin.equinox.io/c/bNyj1mQVY4c"

    # Android / Termux or Linux
    if sys_plat.startswith("linux"):
        if machine in ("aarch64", "arm64", "armv8", "armv8l"):
            return {
                "url": f"{base}/ngrok-v3-stable-linux-arm64.tgz",
                "format": "tgz",
                "arch": "linux-arm64 (64-bit Android/Termux)",
            }
        elif "arm" in machine:
            return {
                "url": f"{base}/ngrok-v3-stable-linux-arm.tgz",
                "format": "tgz",
                "arch": "linux-arm (32-bit Android/Termux)",
            }
        else:
            return {
                "url": f"{base}/ngrok-v3-stable-linux-amd64.tgz",
                "format": "tgz",
                "arch": "linux-amd64",
            }
    elif sys_plat == "win32":
        return {
            "url": f"{base}/ngrok-v3-stable-windows-amd64.zip",
            "format": "zip",
            "arch": "windows-amd64",
        }
    elif sys_plat == "darwin":
        if machine in ("arm64", "aarch64"):
            return {
                "url": f"{base}/ngrok-v3-stable-darwin-arm64.zip",
                "format": "zip",
                "arch": "darwin-arm64 (Apple Silicon)",
            }
        else:
            return {
                "url": f"{base}/ngrok-v3-stable-darwin-amd64.zip",
                "format": "zip",
                "arch": "darwin-amd64 (Intel)",
            }
    elif sys_plat.startswith("freebsd"):
        return {
            "url": f"{base}/ngrok-v3-stable-freebsd-amd64.tgz",
            "format": "tgz",
            "arch": "freebsd-amd64",
        }

    return {
        "url": f"{base}/ngrok-v3-stable-linux-arm64.tgz" if "arm" in machine else f"{base}/ngrok-v3-stable-linux-amd64.tgz",
        "format": "tgz",
        "arch": f"generic-{machine}",
    }


def install_ngrok(force: bool = False, specific_arch: Optional[str] = None) -> Dict[str, Any]:
    """Download and install the verified native ngrok binary for this device with auto-fallback."""
    existing = get_ngrok_bin_path()
    if existing and not force:
        return {
            "status": "ok",
            "installed": True,
            "message": f"ngrok is already installed and verified at: {existing}",
            "path": existing,
        }

    info = get_ngrok_download_info(arch_override=specific_arch)
    url = info["url"]
    fmt = info["format"]
    arch_label = info["arch"]

    bin_name = "ngrok.exe" if sys.platform == "win32" else "ngrok"
    prefix = os.environ.get("PREFIX")
    termux_bin = Path(prefix) / "bin" if (prefix and is_termux()) else None
    local_bin = SCRIPT_DIR / "bin"
    local_bin.mkdir(parents=True, exist_ok=True)
    dest_bin = local_bin / bin_name

    # Clear any old/broken candidate binary
    if dest_bin.is_file():
        try:
            dest_bin.unlink(missing_ok=True)
        except Exception:
            pass

    try:
        headers = {"User-Agent": "Eclipse-Gateway/1.0 (Native Installer)"}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = resp.read()

        if fmt == "tgz":
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
                found = False
                for member in tar.getmembers():
                    if member.name == "ngrok" or member.name.endswith("/ngrok"):
                        extracted_f = tar.extractfile(member)
                        if extracted_f:
                            with open(dest_bin, "wb") as f_out:
                                shutil.copyfileobj(extracted_f, f_out)
                            found = True
                            break
                if not found:
                    return {"status": "error", "message": "ngrok binary not found in downloaded archive."}
        elif fmt == "zip":
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                found = False
                for name in zf.namelist():
                    base_n = Path(name).name.lower()
                    if base_n in ("ngrok.exe", "ngrok"):
                        with zf.open(name) as src, open(dest_bin, "wb") as dst:
                            shutil.copyfileobj(src, dst)
                        found = True
                        break
                if not found:
                    return {"status": "error", "message": "ngrok executable not found in zip archive."}

        # Set execution permissions
        dest_bin.chmod(0o755)

        # CRITICAL TEST: Verify that the binary runs on this device without [Errno 8] Exec format error
        if not is_binary_runnable(dest_bin):
            # Auto-fallback between 64-bit and 32-bit ARM on Android phones
            current_arch = specific_arch or get_device_arch()
            if current_arch in ("arm64", "aarch64") and specific_arch is None:
                return install_ngrok(force=True, specific_arch="arm")
            elif current_arch == "arm" and specific_arch is None:
                return install_ngrok(force=True, specific_arch="arm64")
            else:
                return {
                    "status": "error",
                    "installed": False,
                    "message": f"Downloaded {arch_label} binary cannot be executed on this kernel/OS (Exec format error).",
                }

        # If Termux, replace any broken binary in $PREFIX/bin/ngrok with the verified working binary
        if termux_bin and termux_bin.is_dir():
            termux_target = termux_bin / "ngrok"
            try:
                if termux_target.is_file():
                    termux_target.unlink(missing_ok=True)
                shutil.copy2(dest_bin, termux_target)
                termux_target.chmod(0o755)
                dest_bin = termux_target
            except Exception:
                pass

        p_str = str(dest_bin.parent)
        if p_str not in os.environ.get("PATH", ""):
            os.environ["PATH"] = p_str + os.pathsep + os.environ.get("PATH", "")

        ver_str = "unknown"
        try:
            chk = subprocess.run([str(dest_bin), "version"], capture_output=True, text=True, timeout=5)
            if chk.returncode == 0:
                ver_str = chk.stdout.strip()
        except Exception:
            pass

        return {
            "status": "ok",
            "installed": True,
            "message": f"Successfully installed and verified native ngrok ({arch_label})!",
            "path": str(dest_bin),
            "version": ver_str,
            "arch": arch_label,
        }

    except Exception as e:
        return {
            "status": "error",
            "installed": False,
            "message": f"Failed to auto-install ngrok for {arch_label}: {e}",
        }


def get_ngrok_config_path() -> Path:
    """Return the default path for ngrok.yml across platforms."""
    candidates = []
    if sys.platform == "win32":
        local_app = os.environ.get("LOCALAPPDATA")
        if local_app:
            candidates.append(Path(local_app) / "ngrok" / "ngrok.yml")
        candidates.append(Path.home() / "AppData" / "Local" / "ngrok" / "ngrok.yml")
    candidates.append(Path.home() / ".config" / "ngrok" / "ngrok.yml")
    candidates.append(Path.home() / ".ngrok2" / "ngrok.yml")

    for p in candidates:
        if p.exists():
            return p
    return candidates[0]


def has_authtoken() -> bool:
    """Check if an authtoken has already been configured in ngrok.yml."""
    cfg = get_ngrok_config_path()
    if not cfg.exists():
        return False
    try:
        content = cfg.read_text(encoding="utf-8")
        return "authtoken:" in content and len(content.strip()) > 15
    except Exception:
        return False


def get_tunnel_status() -> Dict[str, Any]:
    """Check if an ngrok tunnel is currently online and return its public URL."""
    bin_path = get_ngrok_bin_path()
    installed = bin_path is not None
    has_token = has_authtoken()
    termux_env = is_termux()
    download_info = get_ngrok_download_info()

    if not installed:
        device_hint = "Android/Termux" if termux_env else platform.system()
        return {
            "status": "not_installed",
            "installed": False,
            "url": None,
            "public_url": None,
            "api_url": None,
            "has_authtoken": False,
            "is_termux": termux_env,
            "arch": download_info.get("arch"),
            "message": f"ngrok is not yet installed for {device_hint}. Click 'Install ngrok' to install natively with zero commands.",
        }

    try:
        resp = httpx.get(NGROK_INSPECT_URL, timeout=1.5)
        if resp.status_code == 200:
            data = resp.json()
            tunnels = data.get("tunnels", [])
            if tunnels:
                global _tunnel_started_at
                proc_start = get_ngrok_process_start_time()
                if proc_start:
                    _tunnel_started_at = proc_start
                elif _tunnel_started_at is None:
                    _tunnel_started_at = time.time()
                uptime_seconds = max(0, int(time.time() - _tunnel_started_at))
                https_tunnels = [t for t in tunnels if t.get("proto") == "https" or str(t.get("public_url", "")).startswith("https")]
                t = https_tunnels[0] if https_tunnels else tunnels[0]
                public_url = (t.get("public_url") or "").rstrip("/")
                return {
                    "status": "online",
                    "installed": True,
                    "bin_path": bin_path,
                    "has_authtoken": True,
                    "is_termux": termux_env,
                    "url": public_url,
                    "public_url": public_url,
                    "api_url": f"{public_url}/v1",
                    "chat_completions_url": f"{public_url}/v1/chat/completions",
                    "proto": t.get("proto", "https"),
                    "name": t.get("name", "eclipse-access"),
                    "started_at": _tunnel_started_at,
                    "uptime_seconds": uptime_seconds,
                }
    except Exception:
        pass

    return {
        "status": "offline",
        "installed": installed,
        "bin_path": bin_path,
        "has_authtoken": has_token,
        "is_termux": termux_env,
        "url": None,
        "public_url": None,
        "api_url": None,
        "chat_completions_url": None,
        "started_at": None,
        "uptime_seconds": 0,
        "message": "Tunnel is offline. Click Start ngrok Tunnel to expose Eclipse to the internet.",
    }


def start_tunnel(port: int = DEFAULT_PORT) -> Dict[str, Any]:
    """Spawn an ngrok tunnel for the specified local port. Auto-installs ngrok natively if missing."""
    current = get_tunnel_status()
    if current.get("status") == "online":
        return current

    # Auto-install or repair ngrok natively if missing or broken
    bin_path = get_ngrok_bin_path()
    if not bin_path:
        inst_res = install_ngrok(force=True)
        if inst_res.get("status") != "ok":
            return {
                "status": "error",
                "message": f"Could not auto-install ngrok: {inst_res.get('message')}",
            }
        bin_path = get_ngrok_bin_path()

    if not bin_path:
        return {
            "status": "error",
            "message": "ngrok binary could not be verified on this device.",
        }

    # Launch ngrok process detached from parent across Windows, Termux, and Unix
    try:
        global _tunnel_started_at
        _tunnel_started_at = time.time()
        popen_kwargs: Dict[str, Any] = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if sys.platform == "win32":
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
            popen_kwargs["creationflags"] = creationflags
        else:
            popen_kwargs["preexec_fn"] = os.setpgrp

        subprocess.Popen([bin_path, "http", str(port)], **popen_kwargs)
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to spawn ngrok process: {e}",
        }

    # Poll inspect endpoint for up to 8 seconds
    start_time = time.time()
    while time.time() - start_time < 8.0:
        time.sleep(0.5)
        status = get_tunnel_status()
        if status.get("status") == "online":
            return status

    return {
        "status": "error",
        "message": "Tunnel process started, but connection timed out. Check your ngrok authtoken or terminal logs.",
    }


def stop_tunnel() -> Dict[str, Any]:
    """Stop all active ngrok tunnels by terminating the process."""
    global _tunnel_started_at
    _tunnel_started_at = None
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/IM", "ngrok.exe", "/T"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            subprocess.run(["pkill", "-x", "ngrok"], check=False)
        time.sleep(0.5)
    except Exception as e:
        return {"status": "error", "message": str(e)}

    return get_tunnel_status()


def save_authtoken(token: str) -> Dict[str, Any]:
    """Configure a new ngrok authtoken across all platforms."""
    clean_token = (token or "").strip()
    if not clean_token:
        return {"status": "error", "message": "Authtoken cannot be empty."}
    # ngrok authtokens are [A-Za-z0-9_-]; anything else (newlines, quotes, colons) could inject ngrok config.
    if not re.fullmatch(r"[A-Za-z0-9_\-]{20,200}", clean_token):
        return {"status": "error", "message": "That doesn't look like an ngrok authtoken (letters, digits, '_' and '-' only)."}

    bin_path = get_ngrok_bin_path()
    if not bin_path:
        inst_res = install_ngrok(force=True)
        if inst_res.get("status") == "ok":
            bin_path = get_ngrok_bin_path()

    if bin_path:
        try:
            res = subprocess.run(
                [bin_path, "config", "add-authtoken", clean_token],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
            if res.returncode == 0:
                return {
                    "status": "ok",
                    "message": "ngrok authtoken configured successfully!",
                    "has_authtoken": True,
                }
        except Exception:
            pass

    # Fallback direct YAML write if ngrok CLI is restricted (e.g. sandbox/permission)
    try:
        cfg = get_ngrok_config_path()
        cfg.parent.mkdir(parents=True, exist_ok=True)
        # Keep the rest of an existing ngrok.yml; only replace (or add) the authtoken line.
        lines = cfg.read_text(encoding="utf-8").splitlines() if cfg.exists() else ['version: "2"']
        lines = [ln for ln in lines if not ln.lstrip().startswith("authtoken:")]
        lines.append(f"authtoken: {clean_token}")
        cfg.write_text("\n".join(lines) + "\n", encoding="utf-8")
        try:
            os.chmod(cfg, 0o600)
        except OSError:
            pass
        return {
            "status": "ok",
            "message": "ngrok authtoken saved directly to configuration file!",
            "has_authtoken": True,
        }
    except Exception as e:
        return {"status": "error", "message": f"Failed to save authtoken: {e}"}
