#!/usr/bin/env python3
"""
Eclipse Vault Encryption
============================
Encrypts credential secrets at rest using only the Python standard library, so
installs stay pure-Python (no `cryptography` wheel, no Rust toolchain on Termux).

Construction (encrypt-then-MAC):
    enc_key = HMAC-SHA256(master, "eclipse-vault-enc")
    mac_key = HMAC-SHA256(master, "eclipse-vault-mac")
    block_i = BLAKE2b-512(key=enc_key, data=nonce || i)      keyed BLAKE2b is a PRF
    ct      = plaintext XOR (block_0 || block_1 || ...)
    tag     = HMAC-SHA256(mac_key, "sv1" || nonce || ct)
Stored as "enc:v1:" + urlsafe_b64(nonce[16] || ct || tag[32]).

Master key lookup (first hit wins):
    1. ECLIPSE_VAULT_KEY environment variable (64 hex chars)
    2. OS keychain: macOS Keychain, Linux Secret Service, Windows DPAPI-protected file
    3. eclipse/data/vault.key (mode 0600), used on Termux / headless machines
A new key is only generated when no key exists anywhere AND the vault holds no
encrypted data, so a temporarily locked keychain can never orphan stored tokens.
"""

import base64
import hashlib
import hmac
import os
import secrets
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Optional

MODULE_DIR = Path(__file__).resolve().parent
DATA_DIR = MODULE_DIR / "data"
KEY_FILE = DATA_DIR / "vault.key"
DPAPI_KEY_FILE = DATA_DIR / "vault.key.dpapi"

PREFIX = "enc:v1:"
_NONCE_LEN = 16
_TAG_LEN = 32
_BLOCK_LEN = 64

_KEYCHAIN_SERVICE = "Eclipse Vault Key"
_KEYCHAIN_ACCOUNT = "eclipse"

_MASTER_KEY: Optional[bytes] = None
_KEY_BACKEND: Optional[str] = None
_KEY_LOCK = threading.Lock()


class VaultKeyError(RuntimeError):
    """Raised when encrypted data exists but its master key cannot be found."""


# ==============================================================================
# Cipher
# ==============================================================================

def _subkeys(master: bytes):
    enc_key = hmac.new(master, b"eclipse-vault-enc", hashlib.sha256).digest()
    mac_key = hmac.new(master, b"eclipse-vault-mac", hashlib.sha256).digest()
    return enc_key, mac_key


def _keystream_xor(enc_key: bytes, nonce: bytes, data: bytes) -> bytes:
    blocks = []
    for i in range((len(data) + _BLOCK_LEN - 1) // _BLOCK_LEN):
        blocks.append(hashlib.blake2b(nonce + i.to_bytes(8, "big"), key=enc_key, digest_size=_BLOCK_LEN).digest())
    stream = b"".join(blocks)[: len(data)]
    if not data:
        return b""
    return (int.from_bytes(data, "big") ^ int.from_bytes(stream, "big")).to_bytes(len(data), "big")


def is_encrypted(value: Optional[str]) -> bool:
    return isinstance(value, str) and value.startswith(PREFIX)


def encrypt(plaintext: str, master: bytes) -> str:
    enc_key, mac_key = _subkeys(master)
    nonce = secrets.token_bytes(_NONCE_LEN)
    ct = _keystream_xor(enc_key, nonce, plaintext.encode("utf-8"))
    tag = hmac.new(mac_key, b"sv1" + nonce + ct, hashlib.sha256).digest()
    return PREFIX + base64.urlsafe_b64encode(nonce + ct + tag).decode("ascii")


def decrypt(value: str, master: bytes) -> str:
    raw = base64.urlsafe_b64decode(value[len(PREFIX):].encode("ascii"))
    if len(raw) < _NONCE_LEN + _TAG_LEN:
        raise ValueError("Vault value is truncated")
    nonce, ct, tag = raw[:_NONCE_LEN], raw[_NONCE_LEN:-_TAG_LEN], raw[-_TAG_LEN:]
    enc_key, mac_key = _subkeys(master)
    expected = hmac.new(mac_key, b"sv1" + nonce + ct, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected):
        raise ValueError("Vault value failed authentication (wrong key or tampered data)")
    return _keystream_xor(enc_key, nonce, ct).decode("utf-8")


# ==============================================================================
# Key storage backends
# ==============================================================================

def _run(cmd, input_text: Optional[str] = None, timeout: float = 5.0) -> Optional[str]:
    try:
        res = subprocess.run(cmd, input=input_text, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    if res.returncode != 0:
        return None
    return res.stdout


def _parse_hex_key(text: Optional[str]) -> Optional[bytes]:
    if not text:
        return None
    text = text.strip()
    try:
        key = bytes.fromhex(text)
    except ValueError:
        return None
    return key if len(key) == 32 else None


# --- macOS Keychain -----------------------------------------------------------

def _mac_load() -> Optional[bytes]:
    if sys.platform != "darwin" or not shutil.which("security"):
        return None
    out = _run(["security", "find-generic-password", "-a", _KEYCHAIN_ACCOUNT, "-s", _KEYCHAIN_SERVICE, "-w"])
    return _parse_hex_key(out)


def _mac_store(key: bytes) -> bool:
    if sys.platform != "darwin" or not shutil.which("security"):
        return False
    # `security -i` reads the command from stdin so the key never appears in the process list.
    cmd = f'add-generic-password -U -a "{_KEYCHAIN_ACCOUNT}" -s "{_KEYCHAIN_SERVICE}" -w "{key.hex()}"\n'
    if _run(["security", "-i"], input_text=cmd) is None:
        return False
    return _mac_load() == key


# --- Linux Secret Service -----------------------------------------------------

def _linux_available() -> bool:
    return sys.platform.startswith("linux") and not os.getenv("PREFIX", "").startswith("/data/data/com.termux") \
        and bool(shutil.which("secret-tool")) and bool(os.getenv("DBUS_SESSION_BUS_ADDRESS"))


def _linux_load() -> Optional[bytes]:
    if not _linux_available():
        return None
    out = _run(["secret-tool", "lookup", "service", "eclipse-vault", "account", _KEYCHAIN_ACCOUNT])
    return _parse_hex_key(out)


def _linux_store(key: bytes) -> bool:
    if not _linux_available():
        return False
    cmd = ["secret-tool", "store", "--label", _KEYCHAIN_SERVICE, "service", "eclipse-vault", "account", _KEYCHAIN_ACCOUNT]
    if _run(cmd, input_text=key.hex()) is None:
        return False
    return _linux_load() == key


# --- Windows DPAPI ------------------------------------------------------------

def _dpapi(data: bytes, protect: bool) -> Optional[bytes]:
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class _DataBlob(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        buf = ctypes.create_string_buffer(data, len(data))
        blob_in = _DataBlob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
        blob_out = _DataBlob()
        fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
        CRYPTPROTECT_UI_FORBIDDEN = 0x01
        if not fn(ctypes.byref(blob_in), None, None, None, None, CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out)):
            return None
        try:
            return ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            kernel32.LocalFree(ctypes.cast(blob_out.pbData, ctypes.c_void_p))
    except Exception:
        return None


def _win_load() -> Optional[bytes]:
    if sys.platform != "win32" or not DPAPI_KEY_FILE.exists():
        return None
    try:
        out = _dpapi(DPAPI_KEY_FILE.read_bytes(), protect=False)
    except OSError:
        return None
    return out if out and len(out) == 32 else None


def _win_store(key: bytes) -> bool:
    blob = _dpapi(key, protect=True)
    if not blob:
        return False
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DPAPI_KEY_FILE.write_bytes(blob)
    return _win_load() == key


# --- Plain key file (0600) ----------------------------------------------------

def _file_load() -> Optional[bytes]:
    try:
        return _parse_hex_key(KEY_FILE.read_text(encoding="ascii"))
    except OSError:
        return None


def _file_store(key: bytes) -> bool:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(KEY_FILE), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return _file_load() == key
    with os.fdopen(fd, "w", encoding="ascii") as f:
        f.write(key.hex())
    return True


_BACKENDS = [
    ("keychain", _mac_load, _mac_store),
    ("secret-service", _linux_load, _linux_store),
    ("dpapi", _win_load, _win_store),
    ("file", _file_load, _file_store),
]


def _find_key():
    env_key = os.getenv("ECLIPSE_VAULT_KEY")
    if env_key:
        key = _parse_hex_key(env_key)
        if not key:
            raise VaultKeyError("ECLIPSE_VAULT_KEY must be 64 hex characters (32 bytes).")
        return key, "env"
    for name, load, _store in _BACKENDS:
        key = load()
        if key:
            return key, name
    return None, None


def get_master_key(vault_has_encrypted_data: bool) -> bytes:
    """Return the vault master key, creating one only for a vault with no encrypted data."""
    global _MASTER_KEY, _KEY_BACKEND
    if _MASTER_KEY is not None:
        return _MASTER_KEY
    with _KEY_LOCK:
        if _MASTER_KEY is not None:
            return _MASTER_KEY
        key, backend = _find_key()
        if key is None:
            if vault_has_encrypted_data:
                raise VaultKeyError(
                    "The credential vault is encrypted but its key was not found. "
                    "Unlock your OS keychain (or restore eclipse/data/vault.key, "
                    "or set ECLIPSE_VAULT_KEY) and restart Eclipse."
                )
            key = secrets.token_bytes(32)
            for name, _load, store in _BACKENDS:
                if store(key):
                    backend = name
                    break
            else:
                raise VaultKeyError("Could not store a new vault key in the keychain or in eclipse/data/vault.key.")
        _MASTER_KEY, _KEY_BACKEND = key, backend
        return key


def key_backend() -> Optional[str]:
    return _KEY_BACKEND
