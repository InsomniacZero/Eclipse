#!/usr/bin/env python3
"""
Eclipse Unified Credential Database Manager
Zero-dependency SQLite store for multi-account stacking across all 6 AI providers:
Claude, Gemini, GLM, Kimi, DeepSeek, Qwen, Antigravity, AI Studio, and MiMo.

Designed to be 100% self-contained within the Eclipse repository for
effortless cross-device portability (PC, Android Termux, laptops).
"""

import base64
import hashlib
import json
import os
import re
import sqlite3
import threading
import time
import uuid
from contextlib import closing
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from eclipse import vault
except ImportError:
    import vault
try:
    from eclipse import bench
except ImportError:
    try:
        import bench
    except ImportError:
        bench = None

preset_schema = None
lore = None
preset_defaults = None
conn_rules = None

MODULE_DIR = Path(__file__).resolve().parent
DATA_DIR = MODULE_DIR / "data"
DB_PATH = DATA_DIR / "eclipse.db"
ROOT_DIR = MODULE_DIR.parent

# Settings whose values are secrets: stored encrypted, never returned by get_all_settings().
SECRET_SETTINGS = {"gateway_key", "search_api_key"}

_INIT_DONE = False
_INIT_LOCK = threading.Lock()


def _restrict_permissions() -> None:
    """Keep the vault readable by the owning user only (no-op where chmod is unsupported)."""
    try:
        os.chmod(DATA_DIR, 0o700)
    except OSError:
        pass
    for suffix in ("", "-wal", "-shm", "-journal"):
        p = Path(str(DB_PATH) + suffix)
        if p.exists():
            try:
                os.chmod(p, 0o600)
            except OSError:
                pass


def get_db_connection() -> sqlite3.Connection:
    """Ensure data directory exists and return an SQLite connection with optimized concurrency pragmas."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=15.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA cache_size = -32000;")
        conn.execute("PRAGMA temp_store = MEMORY;")
        conn.execute("PRAGMA busy_timeout = 15000;")
    except Exception:
        pass
    return conn


# ==============================================================================
# Encryption at rest
# ==============================================================================

def _vault_has_encrypted_data(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT 1 FROM credentials WHERE token LIKE 'enc:%' OR metadata LIKE 'enc:%' LIMIT 1"
    ).fetchone()
    if row:
        return True
    row = conn.execute("SELECT 1 FROM settings WHERE value LIKE 'enc:%' LIMIT 1").fetchone()
    return row is not None


def _master_key() -> bytes:
    if vault._MASTER_KEY is not None:
        return vault._MASTER_KEY
    with get_db_connection() as conn:
        return vault.get_master_key(_vault_has_encrypted_data(conn))


def encrypt_value(plaintext: Optional[str]) -> Optional[str]:
    if plaintext is None or vault.is_encrypted(plaintext):
        return plaintext
    return vault.encrypt(plaintext, _master_key())


def decrypt_value(value: Optional[str]) -> Optional[str]:
    if not vault.is_encrypted(value):
        return value
    return vault.decrypt(value, _master_key())


def _fingerprint_identifier(provider: str, identifier: str) -> str:
    return f"{provider}_{hashlib.sha256(identifier.encode('utf-8')).hexdigest()[:16]}"


def _redact_identifier(provider: str, identifier: str, token: str, metadata_json: Optional[str]) -> str:
    """Replace identifiers derived from secrets (session keys, token prefixes) with a stable fingerprint.

    The identifier column stays plaintext for de-duplication, so it must never hold secret material.
    Emails and user IDs that don't appear inside the credential are kept as-is.
    """
    if not identifier or "@" in identifier:
        return identifier
    if identifier.startswith(f"{provider}_") and len(identifier) == len(provider) + 17:
        return identifier
    bare = identifier
    for prefix in ("user_", "kimi_", "ds_", "qwen_"):
        if bare.startswith(prefix):
            bare = bare[len(prefix):]
            break
    haystacks = [token or "", metadata_json or ""]
    if len(bare) >= 8 and any(bare in h or bare.lower() in h.lower() for h in haystacks):
        return _fingerprint_identifier(provider, identifier)
    return identifier


def _migrate_plaintext_rows(conn: sqlite3.Connection) -> None:
    """Encrypt legacy plaintext tokens/metadata and redact secret identifiers in place."""
    rows = conn.execute(
        "SELECT id, provider, identifier, token, metadata FROM credentials "
        "WHERE token NOT LIKE 'enc:%' OR (metadata IS NOT NULL AND metadata NOT LIKE 'enc:%')"
    ).fetchall()
    secret_settings = conn.execute(
        f"SELECT key, value FROM settings WHERE key IN ({','.join('?' * len(SECRET_SETTINGS))}) AND value NOT LIKE 'enc:%'",
        tuple(SECRET_SETTINGS),
    ).fetchall()
    if not rows and not secret_settings:
        return
    key = vault.get_master_key(_vault_has_encrypted_data(conn))
    for r in rows:
        token = r["token"]
        metadata = r["metadata"]
        plain_token = vault.decrypt(token, key) if vault.is_encrypted(token) else token
        plain_meta = vault.decrypt(metadata, key) if vault.is_encrypted(metadata) else metadata
        new_ident = _redact_identifier(r["provider"], r["identifier"], plain_token, plain_meta)
        clash = conn.execute(
            "SELECT id FROM credentials WHERE provider = ? AND identifier = ? AND id != ?",
            (r["provider"], new_ident, r["id"]),
        ).fetchone()
        if clash:
            new_ident = f"{new_ident}_{r['id']}"
        conn.execute(
            "UPDATE credentials SET identifier = ?, token = ?, metadata = ? WHERE id = ?",
            (
                new_ident,
                token if vault.is_encrypted(token) else vault.encrypt(token, key),
                metadata if (metadata is None or vault.is_encrypted(metadata)) else vault.encrypt(metadata, key),
                r["id"],
            ),
        )
    for s in secret_settings:
        conn.execute("UPDATE settings SET value = ? WHERE key = ?", (vault.encrypt(s["value"], key), s["key"]))
    conn.commit()


def init_db() -> None:
    """Initialize database tables, then encrypt any legacy plaintext secrets (once per process)."""
    global _INIT_DONE
    if _INIT_DONE:
        return
    with _INIT_LOCK:
        if _INIT_DONE:
            return
        _create_tables()
        with get_db_connection() as conn:
            _migrate_plaintext_rows(conn)
            _purge_deleted_chats(conn, DELETED_CHAT_KEEP_SECONDS)
        _restrict_permissions()
        _INIT_DONE = True


def _create_tables() -> None:
    with get_db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS credentials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL,
                identifier TEXT NOT NULL,
                name TEXT,
                token TEXT NOT NULL,
                plan TEXT DEFAULT 'free',
                status TEXT DEFAULT 'active',
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(provider, identifier)
            );
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_provider_status 
            ON credentials(provider, status);
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_nodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT NOT NULL,
                parent_id INTEGER,              -- NULL for a first message
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                reasoning TEXT,
                model TEXT,
                elapsed_ms INTEGER,
                thought_ms INTEGER,
                attachments TEXT,
                steps TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                active_child_id INTEGER         -- the child shown under this message; NULL ends the path
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_nodes_chat_parent ON chat_nodes(chat_id, parent_id);")
        _ensure_chat_columns(conn)
        _ensure_node_columns(conn)
        _migrate_legacy_chat_messages(conn)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_chats_updated
            ON chats(updated_at DESC);
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS presets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL DEFAULT '',
                blocks TEXT NOT NULL DEFAULT '[]',
                placement TEXT NOT NULL DEFAULT 'merge',
                separator TEXT NOT NULL,
                char_name TEXT NOT NULL DEFAULT '',
                user_name TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        preset_columns = {row["name"] for row in conn.execute("PRAGMA table_info(presets)")}
        if "regex_scripts" not in preset_columns:
            conn.execute("ALTER TABLE presets ADD COLUMN regex_scripts TEXT NOT NULL DEFAULT '[]'")
        if "lorebooks" not in preset_columns:
            conn.execute("ALTER TABLE presets ADD COLUMN lorebooks TEXT NOT NULL DEFAULT '[]'")
        if "tools" not in preset_columns:
            conn.execute("ALTER TABLE presets ADD COLUMN tools TEXT NOT NULL DEFAULT '[]'")
        if "tool_guidance" not in preset_columns:
            conn.execute("ALTER TABLE presets ADD COLUMN tool_guidance TEXT NOT NULL DEFAULT ''")
        if "tool_guidance_on" not in preset_columns:
            conn.execute("ALTER TABLE presets ADD COLUMN tool_guidance_on INTEGER NOT NULL DEFAULT 1")
        if "tool_max_steps" not in preset_columns:
            conn.execute("ALTER TABLE presets ADD COLUMN tool_max_steps INTEGER NOT NULL DEFAULT 3")
        _seed_default_presets(conn)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS lorebooks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL DEFAULT '',
                scan_depth INTEGER NOT NULL DEFAULT 4,
                token_budget INTEGER NOT NULL DEFAULT 3000,
                recursive INTEGER NOT NULL DEFAULT 0,
                entries TEXT NOT NULL DEFAULT '[]',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS request_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                requested_model TEXT NOT NULL DEFAULT '',
                model TEXT NOT NULL DEFAULT '',
                preset TEXT NOT NULL DEFAULT '',
                provider TEXT NOT NULL DEFAULT '',
                origin TEXT NOT NULL DEFAULT '',
                stream INTEGER NOT NULL DEFAULT 0,
                tools INTEGER NOT NULL DEFAULT 0,
                searches INTEGER NOT NULL DEFAULT 0,
                searches_ok INTEGER NOT NULL DEFAULT 0,
                outcome TEXT NOT NULL DEFAULT '',
                queries TEXT NOT NULL DEFAULT '[]',
                ms INTEGER NOT NULL DEFAULT 0,
                error TEXT NOT NULL DEFAULT '',
                reply_chars INTEGER NOT NULL DEFAULT 0,
                trace TEXT NOT NULL DEFAULT '{}'
            );
        """)
        request_log_columns = {row["name"] for row in conn.execute("PRAGMA table_info(request_logs)")}
        if "tag" not in request_log_columns:
            conn.execute("ALTER TABLE request_logs ADD COLUMN tag TEXT NOT NULL DEFAULT ''")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bench_scenarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                data TEXT NOT NULL DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bench_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                finished_at TIMESTAMP,
                preset TEXT NOT NULL DEFAULT '',
                model TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'running',
                total INTEGER NOT NULL DEFAULT 0,
                settings TEXT NOT NULL DEFAULT '{}',
                results TEXT NOT NULL DEFAULT '[]'
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS connections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                base_url TEXT NOT NULL,
                api_key TEXT NOT NULL DEFAULT '',
                requires_key INTEGER NOT NULL DEFAULT 1,
                headers TEXT NOT NULL DEFAULT '{}',
                models TEXT NOT NULL DEFAULT '[]',
                models_at TIMESTAMP,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS connect_cards (
                bot_id TEXT PRIMARY KEY,
                name TEXT NOT NULL DEFAULT '',
                avatar TEXT NOT NULL DEFAULT '',
                creator_id TEXT NOT NULL DEFAULT '',
                creator_name TEXT NOT NULL DEFAULT '',
                creator_avatar TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                personality TEXT NOT NULL DEFAULT '',
                scenario TEXT NOT NULL DEFAULT '',
                first_message TEXT NOT NULL DEFAULT '',
                greetings_json TEXT NOT NULL DEFAULT '[]',
                tags_json TEXT NOT NULL DEFAULT '[]',
                tokens INTEGER NOT NULL DEFAULT 0,
                chats INTEGER NOT NULL DEFAULT 0,
                messages INTEGER NOT NULL DEFAULT 0,
                is_unmasked BOOLEAN NOT NULL DEFAULT 0,
                definition_private BOOLEAN NOT NULL DEFAULT 1,
                source TEXT NOT NULL DEFAULT 'janitorai',
                raw_payload_json TEXT NOT NULL DEFAULT '{}',
                created_at REAL NOT NULL DEFAULT 0.0,
                updated_at REAL NOT NULL DEFAULT 0.0
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS connect_intercepts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_id TEXT NOT NULL DEFAULT '',
                bot_name TEXT NOT NULL DEFAULT '',
                model TEXT NOT NULL DEFAULT '',
                system_prompt TEXT NOT NULL DEFAULT '',
                user_prompt TEXT NOT NULL DEFAULT '',
                detected_persona TEXT NOT NULL DEFAULT '',
                intercepted_at REAL NOT NULL DEFAULT 0.0,
                raw_body_json TEXT NOT NULL DEFAULT '{}'
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS connect_saved_cards (
                bot_id TEXT PRIMARY KEY,
                saved_at REAL NOT NULL DEFAULT 0.0
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS connect_chat_sessions (
                session_id TEXT PRIMARY KEY,
                bot_id TEXT NOT NULL DEFAULT '',
                bot_name TEXT NOT NULL DEFAULT '',
                bot_avatar TEXT NOT NULL DEFAULT '',
                bot_description TEXT NOT NULL DEFAULT '',
                created_at REAL NOT NULL DEFAULT 0.0,
                updated_at REAL NOT NULL DEFAULT 0.0,
                summary TEXT NOT NULL DEFAULT '',
                message_count INTEGER NOT NULL DEFAULT 0,
                greeting_idx INTEGER NOT NULL DEFAULT 0,
                persona_id TEXT NOT NULL DEFAULT '',
                persona_name TEXT NOT NULL DEFAULT '',
                persona_avatar TEXT NOT NULL DEFAULT '',
                is_published BOOLEAN NOT NULL DEFAULT 0,
                messages_json TEXT NOT NULL DEFAULT '[]',
                settings_json TEXT NOT NULL DEFAULT '{}'
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS connect_user_vault (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT '',
                updated_at REAL NOT NULL DEFAULT 0.0
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS connect_creators (
                creator_id TEXT PRIMARY KEY,
                username TEXT NOT NULL DEFAULT '',
                display_name TEXT NOT NULL DEFAULT '',
                avatar_url TEXT NOT NULL DEFAULT '',
                bio TEXT NOT NULL DEFAULT '',
                followers INTEGER NOT NULL DEFAULT 0,
                total_bots INTEGER NOT NULL DEFAULT 0,
                badges_json TEXT NOT NULL DEFAULT '[]',
                style_json TEXT NOT NULL DEFAULT '{}',
                raw_payload_json TEXT NOT NULL DEFAULT '{}',
                updated_at REAL NOT NULL DEFAULT 0.0
            );
        """)
        conn.execute("""
            INSERT OR IGNORE INTO connect_creators (
                creator_id, username, display_name, avatar_url, bio, followers, total_bots, updated_at
            )
            SELECT 
                creator_id, 
                creator_name, 
                creator_name, 
                creator_avatar, 
                'JanitorAI author with ' || count(*) || ' character cards', 
                0, 
                count(*), 
                strftime('%s', 'now')
            FROM connect_cards 
            WHERE length(creator_id) > 0 
            GROUP BY creator_id
        """)
        conn.execute("""
            UPDATE connect_creators 
            SET avatar_url = REPLACE(avatar_url, '/bot-avatars/', '/avatars/')
            WHERE avatar_url LIKE '%/bot-avatars/%'
        """)
        conn.execute("""
            UPDATE connect_cards 
            SET creator_avatar = REPLACE(creator_avatar, '/bot-avatars/', '/avatars/')
            WHERE creator_avatar LIKE '%/bot-avatars/%'
        """)
        conn.execute("""
            UPDATE connect_creators 
            SET bio = ''
            WHERE bio LIKE 'Creator of %' OR bio LIKE 'JanitorAI author of %'
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_connect_cards_creator ON connect_cards(creator_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_connect_cards_updated ON connect_cards(updated_at DESC);")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS custom_voices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                voice_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                prompt TEXT NOT NULL DEFAULT '',
                voice_type TEXT NOT NULL DEFAULT 'prompted',
                sample_audio TEXT NOT NULL DEFAULT '',
                created_at REAL NOT NULL DEFAULT 0.0
            );
        """)
        conn.execute("UPDATE bench_runs SET status = 'interrupted', finished_at = CURRENT_TIMESTAMP WHERE status = 'running'")
        conn.commit()


def _ensure_chat_columns(conn: sqlite3.Connection) -> None:
    """Add the columns a chats table from an older version lacks."""
    chat_columns = {row["name"] for row in conn.execute("PRAGMA table_info(chats)")}
    if "tools" not in chat_columns:
        conn.execute("ALTER TABLE chats ADD COLUMN tools TEXT")
    if "root_active_id" not in chat_columns:
        conn.execute("ALTER TABLE chats ADD COLUMN root_active_id INTEGER")
    for column, sql_type in (("pinned_at", "TEXT"), ("archived_at", "TIMESTAMP"), ("deleted_at", "TIMESTAMP"),
                             ("title_source", "TEXT"), ("settings", "TEXT")):
        if column not in chat_columns:
            conn.execute(f"ALTER TABLE chats ADD COLUMN {column} {sql_type}")


def _ensure_node_columns(conn: sqlite3.Connection) -> None:
    """Add the columns a chat_nodes table from an older version lacks."""
    node_columns = {row["name"] for row in conn.execute("PRAGMA table_info(chat_nodes)")}
    if "cut_off" not in node_columns:
        conn.execute("ALTER TABLE chat_nodes ADD COLUMN cut_off INTEGER")   # 1 = the reply stopped early


def _migrate_legacy_chat_messages(conn: sqlite3.Connection) -> None:
    """Turn the old linear chat_messages table into single-chain chat_nodes, once.

    Runs inside the caller's transaction. The old table is renamed, never dropped, so a failed
    or unwanted migration can be undone by hand.
    """
    exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'chat_messages'").fetchone()
    if not exists:
        return
    have_nodes = {row[0] for row in conn.execute("SELECT DISTINCT chat_id FROM chat_nodes")}
    chats = {row["id"] for row in conn.execute("SELECT id FROM chats")}
    optional = ("reasoning", "model", "elapsed_ms", "thought_ms", "attachments", "steps", "created_at")
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(chat_messages)")}
    select = ", ".join(["chat_id", "role", "content"] + [c if c in columns else f"NULL AS {c}" for c in optional])
    previous_chat, previous_node = None, None
    for row in conn.execute(f"SELECT {select} FROM chat_messages ORDER BY chat_id, idx").fetchall():
        chat_id = row["chat_id"]
        if chat_id in have_nodes or chat_id not in chats:
            continue
        if chat_id != previous_chat:
            previous_chat, previous_node = chat_id, None
        cur = conn.execute(
            "INSERT INTO chat_nodes (chat_id, parent_id, role, content, reasoning, model, elapsed_ms, thought_ms, "
            "attachments, steps, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))",
            (chat_id, previous_node, row["role"], row["content"], row["reasoning"], row["model"], row["elapsed_ms"],
             row["thought_ms"], row["attachments"], row["steps"], row["created_at"]),
        )
        node_id = cur.lastrowid
        if previous_node is None:
            conn.execute("UPDATE chats SET root_active_id = ? WHERE id = ?", (node_id, chat_id))
        else:
            conn.execute("UPDATE chat_nodes SET active_child_id = ? WHERE id = ?", (node_id, previous_node))
        previous_node = node_id
    target = "chat_messages_legacy"
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (target,)).fetchone():
        target = f"chat_messages_legacy_{int(time.time())}"
    conn.execute(f"ALTER TABLE chat_messages RENAME TO {target}")


# ==============================================================================
# Token & Credential Parsers
# ==============================================================================

def _clean_jwt_string(raw: str) -> str:
    """Extract and unwrap clean JWT string from raw input (JSON, quotes, cookies, or Bearer prefix)."""
    if not raw:
        return ""
    t = raw.strip().replace("\r", "")
    # Strip wrapping quotes
    if (t.startswith('"') and t.endswith('"')) or (t.startswith("'") and t.endswith("'")):
        t = t[1:-1].strip()
    # If JSON object, look for refresh_token, kimi-refresh-token, access_token, token, or value
    if (t.startswith("{") and t.endswith("}")) or (t.startswith("[") and t.endswith("]")):
        try:
            data = json.loads(t)
            if isinstance(data, dict):
                cand = (
                    data.get("refresh_token")
                    or data.get("kimi-refresh-token")
                    or data.get("access_token")
                    or data.get("token")
                    or data.get("value")
                )
                if cand:
                    t = str(cand).strip()
            elif isinstance(data, list) and data:
                if isinstance(data[0], str):
                    t = data[0].strip()
                elif isinstance(data[0], dict):
                    cand = (
                        data[0].get("refresh_token")
                        or data[0].get("kimi-refresh-token")
                        or data[0].get("access_token")
                        or data[0].get("token")
                        or data[0].get("value")
                    )
                    if cand:
                        t = str(cand).strip()
        except Exception:
            pass
    # Strip Bearer prefix if present
    if t.lower().startswith("bearer "):
        t = t[7:].strip()
    
    # If string contains a valid 3-part JWT pattern, extract it cleanly
    jwt_match = re.search(r"(eyJ[A-Za-z0-9_\-]+\.eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+)", t)
    if jwt_match:
        return jwt_match.group(1).strip()

    return t.strip().strip('"').strip("'")


def _decode_jwt_payload(token_str: str) -> Optional[Dict[str, Any]]:
    """Safely decode JWT payload without verification."""
    try:
        clean = _clean_jwt_string(token_str)
        parts = clean.split(".")
        if len(parts) >= 2:
            payload_b64 = parts[1]
            payload_b64 += "=" * ((4 - len(payload_b64) % 4) % 4)
            decoded_bytes = base64.urlsafe_b64decode(payload_b64)
            return json.loads(decoded_bytes.decode("utf-8", errors="ignore"))
    except Exception:
        pass
    return None


def parse_credential(provider: str, raw: str) -> Optional[Dict[str, Any]]:
    """Parse raw user input into structured credential object."""
    raw = raw.strip()
    if not raw or raw.startswith("#"):
        return None

    # 1. Kimi
    if provider == "kimi":
        raw = _clean_jwt_string(raw)
        # Check if cookie / env format: KIMI_TOKEN=..., kimi-refresh-token=..., refresh_token=...
        cookie_m = re.search(r"(?:kimi[-_]?refresh[-_]?token|refresh[-_]?token|kimi[-_]?token)=([^\s;]+)", raw, re.IGNORECASE)
        if cookie_m:
            raw = _clean_jwt_string(cookie_m.group(1))
        elif "KIMI_TOKEN=" in raw:
            m = re.search(r"KIMI_TOKEN=([^\s]+)", raw)
            if m:
                raw = _clean_jwt_string(m.group(1))

        jwt = _decode_jwt_payload(raw)
        sub = None
        device_id = None
        exp = None
        name = "Kimi Account"
        if jwt:
            sub = jwt.get("sub") or jwt.get("abstract_user_id") or jwt.get("jti")
            device_id = jwt.get("device_id")
            exp = jwt.get("exp")
            region = jwt.get("region", "global")
            name = f"Kimi ({sub[:8]})" if sub else f"Kimi ({region})"

        identifier = sub or f"kimi_{raw[-16:]}"
        return {
            "provider": "kimi",
            "identifier": identifier,
            "name": name,
            "token": raw,
            "plan": "free",
            "status": "active",
            "metadata": json.dumps({"sub": sub, "device_id": device_id, "exp": exp}),
        }

    # 3. Claude
    elif provider == "claude":
        # Check if sessionKey: "..."
        m = re.search(r'sessionKey:\s*"([^"]+)"', raw)
        key = m.group(1).strip() if m else raw.strip()
        if key.startswith('"') and key.endswith('"'):
            key = key[1:-1].strip()

        identifier = key
        masked = key[:12] + "..." + key[-6:] if len(key) > 20 else key
        return {
            "provider": "claude",
            "identifier": identifier,
            "name": f"Claude ({masked})",
            "token": key,
            "plan": "pro",
            "status": "active",
            "metadata": json.dumps({"sessionKey": key}),
        }

    # 3. Gemini
    elif provider == "gemini":
        raw_str = raw.strip()

        # If user pasted a full cURL command or request header block, extract the Cookie header directly
        curl_cookie_m = re.search(
            r"""(?:-H\s+['"]cookie:\s*([^'"]+)['"]|-b\s+['"]([^'"]+)['"]|(?:^|[\r\n])cookie:\s*([^\r\n]+))""",
            raw_str,
            re.IGNORECASE,
        )
        if curl_cookie_m:
            raw_str = (curl_cookie_m.group(1) or curl_cookie_m.group(2) or curl_cookie_m.group(3) or "").strip()
        elif raw_str.lower().startswith("cookie:"):
            raw_str = raw_str[7:].strip()

        raw_str = re.sub(r'[\r\n]+', '; ', raw_str)

        # Check if user passed an AI Studio / Gemini API key
        if raw_str.startswith("AIzaSy") or raw_str.startswith("AQ."):
            api_key = raw_str
            identifier = f"key_{api_key[:12]}"
            return {
                "provider": "gemini",
                "identifier": identifier,
                "name": f"Gemini API ({api_key[:8]}...)",
                "token": api_key,
                "plan": "Google Gemini API Key",
                "status": "active",
                "metadata": json.dumps({"api_key": api_key}),
            }

        psid_m = re.search(r"__Secure-1PSID=([^; '\"\\]+)", raw_str)
        if not psid_m:
            # Strictly reject lines that do not contain a valid __Secure-1PSID cookie
            return None

        psid = psid_m.group(1).strip()
        psidts_m = re.search(r"__Secure-1PSIDTS=([^; '\"\\]+)", raw_str)
        sapisid_m = re.search(r"(?:SAPISID|__Secure-1PAPISID)=([^; '\"\\]+)", raw_str)

        has_psidts = bool(psidts_m)
        metadata = {
            "psid": psid,
            "has_psidts": has_psidts,
            "has_sapisid": bool(sapisid_m),
        }
        if not has_psidts:
            metadata["warning"] = "Missing __Secure-1PSIDTS cookie. Google requires both __Secure-1PSID and __Secure-1PSIDTS for full authentication & image generation."

        identifier = psid
        return {
            "provider": "gemini",
            "identifier": identifier,
            "name": f"Gemini ({psid[:8]}...)",
            "token": raw_str,
            "plan": "pro",
            "status": "active",
            "metadata": json.dumps(metadata),
        }

    # 6. GLM (Z.ai Global)
    elif provider == "glm":
        raw_str = raw.strip()
        token = raw_str
        metadata = {}
        if raw_str.startswith("{"):
            try:
                d = json.loads(raw_str)
                if isinstance(d, dict):
                    token = (
                        d.get("token")
                        or d.get("access_token")
                        or d.get("chatglm_refresh_token")
                        or d.get("refresh_token")
                        or d.get("chatglm_token")
                        or raw_str
                    )
                    metadata = d
            except Exception:
                pass
        token = re.sub(r"^Bearer\s+", "", str(token), flags=re.IGNORECASE).strip("\"' \t\r\n")
        identifier = token[:32] if token else "zai_account"

        # Try extracting email or name from JWT payload if available
        email_label = None
        try:
            parts = token.split(".")
            if len(parts) >= 2:
                import base64
                padded = parts[1] + "=" * ((4 - len(parts[1]) % 4) % 4)
                jwt_meta = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
                email_label = jwt_meta.get("email") or jwt_meta.get("name")
        except Exception:
            pass

        account_name = f"Z.ai ({email_label})" if email_label else f"Z.ai ({identifier[:8]}...)"
        return {
            "provider": "glm",
            "identifier": identifier,
            "name": account_name,
            "token": token,
            "plan": "free",
            "status": "active",
            "metadata": json.dumps(metadata),
        }

    # 7. DeepSeek
    elif provider == "deepseek":
        raw_str = raw.strip()
        email = ""
        token = raw_str
        uid = ""
        if raw_str.startswith("{"):
            try:
                d = json.loads(raw_str)
                if isinstance(d, dict):
                    email = d.get("email", "")
                    token = d.get("token") or d.get("userToken") or d.get("user_token") or d.get("value") or raw_str
                    uid = d.get("uid") or ""
            except Exception:
                pass

        if not email and token:
            jwt = _decode_jwt_payload(token)
            if jwt:
                email = jwt.get("email") or ""
                uid = jwt.get("sub") or jwt.get("uid") or ""

        identifier = (email or uid or f"ds_{token[:20]}").strip().lower()
        name = f"DeepSeek ({identifier[:8]})" if not email else email.split("@")[0]
        return {
            "provider": "deepseek",
            "identifier": identifier,
            "name": name,
            "token": token,
            "plan": "free",
            "status": "active",
            "metadata": json.dumps({"email": email, "uid": uid}),
        }

    # 8. Qwen (Alibaba Cloud)
    elif provider in ("qwen", "tongyi"):
        raw_str = raw.strip()
        email = ""
        token = raw_str
        uid = ""
        cookies = ""
        if raw_str.startswith("{"):
            try:
                d = json.loads(raw_str)
                if isinstance(d, dict):
                    email = d.get("email", "")
                    token = (
                        d.get("token")
                        or d.get("userToken")
                        or d.get("user_token")
                        or d.get("value")
                        or d.get("access_token")
                        or raw_str
                    )
                    uid = d.get("uid") or d.get("id") or ""
                    cookies = d.get("cookies") or d.get("cookie") or ""
            except Exception:
                pass

        if "token=eyJ" in raw_str:
            tok_m = re.search(r'token=(eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+)', raw_str)
            if tok_m:
                token = tok_m.group(1).strip()
                cookies = raw_str
        else:
            jwt_match = re.search(r'(?:Bearer\s+)?(eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+)', raw_str)
            if jwt_match:
                token = jwt_match.group(1).strip()
                if ";" in raw_str and not cookies:
                    remainder = raw_str.replace(jwt_match.group(0), "").strip()
                    remainder = re.sub(r'^[;\s]+|[;\s]+$', '', remainder)
                    if remainder:
                        cookies = remainder
            elif ";" in raw_str:
                parts = [p.strip() for p in raw_str.split(";", 1)]
                if "eyJ" in parts[0]:
                    token = parts[0]
                    cookies = parts[1]
                elif "eyJ" in parts[1]:
                    cookies = parts[0]
                    token = parts[1]

        if token.lower().startswith("bearer "):
            token = token[7:].strip()

        if not email and token:
            jwt = _decode_jwt_payload(token)
            if jwt:
                email = jwt.get("email") or ""
                uid = jwt.get("id") or jwt.get("sub") or jwt.get("uid") or jwt.get("user_id") or ""

        identifier = (email or uid or f"qwen_{token[:20]}").strip().lower()
        name = f"Qwen ({identifier[:8]})" if not email else email.split("@")[0]
        return {
            "provider": "qwen",
            "identifier": identifier,
            "name": name,
            "token": token,
            "plan": "free",
            "status": "active",
            "metadata": json.dumps({"email": email, "uid": uid, "cookies": cookies}),
        }

    # 9. Google Antigravity (AGY)
    # 9. Google Antigravity (AGY)
    elif provider in ("antigravity", "agy", "google-antigravity"):
        raw_str = raw.strip()
        email = ""
        access_token = ""
        refresh_token = ""
        project_id = "aicode-consumers"
        plan = "Google AI Pro (Antigravity)"

        if raw_str.startswith("{"):
            try:
                d = json.loads(raw_str)
                if isinstance(d, dict):
                    email = d.get("email") or d.get("user") or ""
                    access_token = d.get("access_token") or d.get("accessToken") or ""
                    refresh_token = d.get("refresh_token") or d.get("refreshToken") or ""
                    project_id = d.get("project_id") or d.get("project") or project_id
                    if not email and d.get("active"):
                        email = d.get("active")
            except Exception:
                pass

        if not email and access_token:
            jwt = _decode_jwt_payload(access_token)
            if jwt:
                email = jwt.get("email") or ""

        if not email and not refresh_token and not access_token:
            if raw_str.startswith("ya29."):
                access_token = raw_str
            else:
                refresh_token = raw_str

        identifier = (email or (f"agy_{refresh_token[:16]}" if refresh_token else f"agy_{access_token[:16]}")).strip().lower()
        name = f"AGY ({email.split('@')[0]})" if email and "@" in email else f"Antigravity ({identifier[:10]}...)"

        return {
            "provider": "antigravity",
            "identifier": identifier,
            "name": name,
            "token": raw_str,
            "plan": plan,
            "status": "active",
            "metadata": json.dumps({
                "email": email,
                "project_id": project_id,
                "refresh_token": refresh_token,
                "access_token": access_token,
                "has_refresh_token": bool(refresh_token),
                "has_access_token": bool(access_token),
            }),
        }

    # 10. Google AI Studio (MakerSuite)
    elif provider in ("aistudio", "ais", "google-aistudio", "makersuite"):
        raw_str = raw.strip()
        if raw_str.lower().startswith("cookie:"):
            raw_str = raw_str[7:].strip()
        raw_str = re.sub(r'[\r\n]+', '; ', raw_str)
        email = ""
        api_key = ""
        cookie_str = raw_str

        if raw_str.startswith("{") or raw_str.startswith("["):
            try:
                d = json.loads(raw_str)
                if isinstance(d, dict):
                    email = d.get("email") or d.get("user") or ""
                    api_key = d.get("api_key") or d.get("apiKey") or d.get("key") or ""
                    if "cookies" in d:
                        cookies_val = d["cookies"]
                        if isinstance(cookies_val, list):
                            cookie_str = "; ".join(f"{c.get('name')}={c.get('value')}" for c in cookies_val if isinstance(c, dict) and "name" in c and "value" in c)
                        elif isinstance(cookies_val, str):
                            cookie_str = cookies_val
                        elif isinstance(cookies_val, dict):
                            cookie_str = "; ".join(f"{k}={v}" for k, v in cookies_val.items())
                    elif "cookie" in d:
                        cookie_str = str(d["cookie"])
                elif isinstance(d, list):
                    cookie_str = "; ".join(f"{c.get('name')}={c.get('value')}" for c in d if isinstance(c, dict) and "name" in c and "value" in c)
            except Exception:
                pass

        if not api_key and (raw_str.startswith("AIzaSy") or raw_str.startswith("AQ.")):
            api_key = raw_str

        if api_key and not cookie_str.startswith("__Secure-"):
            identifier = f"key_{api_key[:12]}"
            name = f"AI Studio ({api_key[:8]}...)"
            return {
                "provider": "aistudio",
                "identifier": identifier,
                "name": name,
                "token": api_key,
                "plan": "Google AI Studio API Key",
                "status": "active",
                "metadata": json.dumps({"api_key": api_key}),
            }

        psid_m = re.search(r"__Secure-1PSID=([^;]+)", cookie_str)
        psidts_m = re.search(r"__Secure-1PSIDTS=([^;]+)", cookie_str)
        sapisid_m = re.search(r"(?:__Secure-3PAPISID|__Secure-1PAPISID|SAPISID)=([^;]+)", cookie_str)
        psid = psid_m.group(1).strip() if psid_m else ""
        has_psidts = bool(psidts_m)
        has_sapisid = bool(sapisid_m)

        identifier = (email or (f"psid_{psid[:12]}" if psid else (f"key_{api_key[:12]}" if api_key else f"ais_{raw_str[:15]}"))).strip().lower()
        name = f"AI Studio ({email.split('@')[0]})" if email and "@" in email else (f"AI Studio ({psid[:8]}...)" if psid else f"AI Studio ({identifier[:12]})")

        metadata = {
            "email": email,
            "has_psid": bool(psid),
            "has_psidts": has_psidts,
            "has_sapisid": has_sapisid,
            "api_key": api_key,
        }
        if not psid and not api_key:
            metadata["warning"] = "Missing __Secure-1PSID or API key. MakerSuite RPC requires authenticated Google cookies or API key."

        return {
            "provider": "aistudio",
            "identifier": identifier,
            "name": name,
            "token": raw_str,
            "plan": "Google AI Studio Pro",
            "status": "active",
            "metadata": json.dumps(metadata),
        }

    # 11. Xiaomi MiMo AI
    elif provider in ("mimo", "xiaomi", "xiaomimimo"):
        raw_str = raw.strip()
        if raw_str.lower().startswith("cookie:"):
            raw_str = raw_str[7:].strip()
        raw_str = re.sub(r'[\r\n]+', '; ', raw_str)

        st = ""
        uid = ""
        ph = ""
        pass_token = ""

        if raw_str.startswith("{") or raw_str.startswith("["):
            try:
                d = json.loads(raw_str)
                if isinstance(d, dict):
                    st = d.get("serviceToken") or d.get("token") or d.get("accessToken") or ""
                    uid = str(d.get("userId") or d.get("user_id") or d.get("uid") or "")
                    ph = d.get("xiaomichatbot_ph") or ""
                    pass_token = d.get("passToken") or ""
                    if "cookies" in d and isinstance(d["cookies"], list):
                        for c in d["cookies"]:
                            if isinstance(c, dict):
                                n, v = c.get("name"), c.get("value")
                                if n == "serviceToken": st = v
                                elif n == "userId": uid = str(v)
                                elif n == "xiaomichatbot_ph": ph = v
                                elif n == "passToken": pass_token = v
                elif isinstance(d, list):
                    for c in d:
                        if isinstance(c, dict):
                            n, v = c.get("name"), c.get("value")
                            if n == "serviceToken": st = v
                            elif n == "userId": uid = str(v)
                            elif n == "xiaomichatbot_ph": ph = v
                            elif n == "passToken": pass_token = v
            except Exception:
                pass

        if not st:
            st_m = re.search(r"(?:xiaomichatbot_)?serviceToken=([^;\s&]+)", raw_str)
            if st_m:
                st = st_m.group(1).strip()
            elif len(raw_str) > 30 and not raw_str.startswith("{") and "=" not in raw_str:
                st = raw_str.strip()

        if not uid:
            uid_m = re.search(r"userId=([^;\s&]+)", raw_str)
            if uid_m:
                uid = uid_m.group(1).strip()

        if not ph:
            ph_m = re.search(r"xiaomichatbot_ph=([^;\s&]+)", raw_str)
            if ph_m:
                ph = ph_m.group(1).strip()

        if not pass_token:
            pass_m = re.search(r"passToken=([^;\s&]+)", raw_str)
            if pass_m:
                pass_token = pass_m.group(1).strip()

        def _clean_c(val: str) -> str:
            s = str(val or "").strip()
            if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
                s = s[1:-1].strip()
            return s

        st = _clean_c(st)
        uid = _clean_c(uid)
        ph = _clean_c(ph)
        pass_token = _clean_c(pass_token)

        identifier = (uid or (f"mimo_{st[:16]}" if st else f"mimo_{raw_str[:16]}")).strip().lower()
        name = f"Xiaomi MiMo ({uid})" if uid else f"MiMo ({identifier[:10]}...)"
        metadata = {
            "serviceToken": st,
            "userId": uid,
            "xiaomichatbot_ph": ph,
            "passToken": pass_token,
            "has_pass_token": bool(pass_token),
        }
        if not ph:
            metadata["warning"] = "Missing xiaomichatbot_ph cookie. MiMo chat endpoints require xiaomichatbot_ph."

        return {
            "provider": "mimo",
            "identifier": identifier,
            "name": name,
            "token": raw_str,
            "plan": "Xiaomi AI Studio",
            "status": "active",
            "metadata": json.dumps(metadata),
        }

    return None



# ==============================================================================
# CRUD Operations
# ==============================================================================

def get_accounts(provider: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve accounts from database."""
    init_db()
    with get_db_connection() as conn:
        if provider:
            rows = conn.execute(
                "SELECT * FROM credentials WHERE provider = ? ORDER BY id DESC",
                (provider,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM credentials ORDER BY provider, id DESC"
            ).fetchall()

        results = []
        for r in rows:
            metadata = decrypt_value(r["metadata"])
            results.append({
                "id": r["id"],
                "provider": r["provider"],
                "identifier": r["identifier"],
                "name": r["name"] or r["identifier"],
                "token": decrypt_value(r["token"]),
                "plan": r["plan"] or "free",
                "status": r["status"] or "active",
                "metadata": json.loads(metadata) if metadata else {},
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
            })
        return results


def save_account(
    provider: str,
    raw_credential: str,
    name: Optional[str] = None,
    plan: Optional[str] = None,
    status: str = "active",
) -> Tuple[bool, str]:
    """Insert or update a single credential with deduplication."""
    init_db()
    parsed = parse_credential(provider, raw_credential)
    if not parsed:
        return False, "Failed to parse credential"

    identifier = _redact_identifier(provider, parsed["identifier"], parsed["token"], parsed["metadata"])
    final_name = name or parsed["name"]
    final_plan = plan or parsed["plan"]
    token = encrypt_value(parsed["token"])
    metadata = encrypt_value(parsed["metadata"])

    with get_db_connection() as conn:
        conn.execute("""
            INSERT INTO credentials (provider, identifier, name, token, plan, status, metadata, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(provider, identifier) DO UPDATE SET
                name = excluded.name,
                token = excluded.token,
                plan = excluded.plan,
                status = excluded.status,
                metadata = excluded.metadata,
                updated_at = CURRENT_TIMESTAMP
        """, (provider, identifier, final_name, token, final_plan, status, metadata))
        conn.commit()

    return True, f"Saved account '{final_name}' for {provider}."


def add_account(provider: str, credential_or_raw: Any) -> Tuple[bool, str]:
    """Helper to save an account given either a raw string or parsed dict."""
    if isinstance(credential_or_raw, dict):
        raw = credential_or_raw.get("token") or json.dumps(credential_or_raw)
        return save_account(
            provider,
            raw,
            name=credential_or_raw.get("name"),
            plan=credential_or_raw.get("plan"),
            status=credential_or_raw.get("status", "active"),
        )
    return save_account(provider, str(credential_or_raw))


def save_accounts(provider: str, items: List[str]) -> Tuple[int, int]:
    """Bulk stack credentials with deduplication. Returns (added_or_updated, failed)."""
    init_db()
    success = 0
    failed = 0
    for item in items:
        if not item or not item.strip():
            continue
        ok, _ = save_account(provider, item.strip())
        if ok:
            success += 1
        else:
            failed += 1

    return success, failed


def remove_account(provider: str, identifier: Optional[str] = None, account_id: Optional[int] = None) -> bool:
    """Delete a specific account by identifier or database ID."""
    init_db()
    with get_db_connection() as conn:
        if account_id is not None:
            cur = conn.execute(
                "DELETE FROM credentials WHERE provider = ? AND id = ?",
                (provider, account_id),
            )
        elif identifier:
            ident_clean = identifier.strip()
            num_id = int(ident_clean) if ident_clean.isdigit() else -1
            cur = conn.execute(
                "DELETE FROM credentials WHERE provider = ? AND (identifier = ? OR identifier = ? OR id = ?)",
                (provider, ident_clean, _fingerprint_identifier(provider, ident_clean), num_id),
            )
            if cur.rowcount == 0:
                # Tokens are encrypted, so matching by raw token has to happen after decryption.
                for r in conn.execute("SELECT id, token FROM credentials WHERE provider = ?", (provider,)).fetchall():
                    if decrypt_value(r["token"]) == ident_clean:
                        cur = conn.execute("DELETE FROM credentials WHERE id = ?", (r["id"],))
                        break
        else:
            return False

        deleted = cur.rowcount > 0
        conn.commit()

    return deleted


def clear_accounts(provider: str) -> int:
    """Remove all accounts for a given provider."""
    init_db()
    with get_db_connection() as conn:
        cur = conn.execute("DELETE FROM credentials WHERE provider = ?", (provider,))
        count = cur.rowcount
        conn.commit()
    return count


_ROTATION_INDEX: Dict[str, int] = {}

def get_next_token(provider: str) -> Optional[str]:
    """Return the next active account's token in round-robin order."""
    init_db()
    with get_db_connection() as conn:
        rows = conn.execute(
            "SELECT token FROM credentials WHERE provider = ? AND status = 'active' ORDER BY id ASC",
            (provider,),
        ).fetchall()
        if not rows:
            return None
        idx = _ROTATION_INDEX.get(provider, 0) % len(rows)
        token = decrypt_value(rows[idx]["token"])
        _ROTATION_INDEX[provider] = (idx + 1) % len(rows)
        return token



# ==============================================================================
# Cross-Device Export & Import (1-Click Sync)
# ==============================================================================

def get_stats() -> Dict[str, Any]:
    """Return summary counts of accounts per provider."""
    init_db()
    with get_db_connection() as conn:
        rows = conn.execute("""
            SELECT provider, status, COUNT(*) as count 
            FROM credentials 
            GROUP BY provider, status
        """).fetchall()

    grouped: Dict[str, Dict[str, int]] = {}
    total = 0
    for r in rows:
        p = r["provider"]
        st = r["status"]
        cnt = r["count"]
        total += cnt
        if p not in grouped:
            grouped[p] = {"total": 0, "active": 0, "disabled": 0}
        grouped[p]["total"] += cnt
        if st == "active":
            grouped[p]["active"] += cnt
        else:
            grouped[p]["disabled"] += cnt

    return {
        "total_accounts": total,
        "providers": grouped,
    }


def export_all_json() -> Dict[str, Any]:
    """Export all stored credentials across all providers as a portable JSON structure."""
    accounts = get_accounts()
    grouped: Dict[str, List[Dict[str, Any]]] = {
        "claude": [],
        "gemini": [],
        "glm": [],
        "kimi": [],
        "deepseek": [],
        "qwen": [],
        "antigravity": [],
        "aistudio": [],
        "mimo": [],
    }

    for acc in accounts:
        p = acc["provider"]
        if p not in grouped:
            grouped[p] = []
        grouped[p].append({
            "identifier": acc["identifier"],
            "name": acc["name"],
            "token": acc["token"],
            "plan": acc["plan"],
            "status": acc["status"],
            "metadata": acc["metadata"],
        })

    return {
        "version": 1,
        "format": "eclipse_credentials",
        "exported_at": int(time.time()),
        "total_accounts": len(accounts),
        "providers": grouped,
    }


def import_all_json(data: Any) -> Dict[str, Any]:
    """Import credentials from a JSON dictionary or file dump."""
    init_db()
    if isinstance(data, str):
        data = json.loads(data)

    if not isinstance(data, dict):
        raise ValueError("Invalid credentials payload: expected JSON object")

    # Check if single account dictionary was passed
    if "provider" in data and ("token" in data or "refresh_token" in data or "access_token" in data or "raw" in data):
        prov = data["provider"]
        tok = data.get("token") or (json.dumps(data) if "refresh_token" in data else data.get("refresh_token") or data.get("access_token") or data.get("raw"))
        name = data.get("name") or data.get("email")
        plan = data.get("plan")
        status = data.get("status", "active")
        ok, _ = save_account(prov, str(tok), name=name, plan=plan, status=status)
        return {
            "status": "ok",
            "imported_accounts": 1 if ok else 0,
            "message": f"Successfully imported {1 if ok else 0} accounts across providers.",
        }

    providers_data = data.get("providers") if "providers" in data else data
    imported_count = 0

    for provider, acc_list in providers_data.items():
        if not isinstance(acc_list, list):
            continue
        for acc in acc_list:
            token = acc.get("token") or acc.get("raw") or (acc if isinstance(acc, str) else None)
            if not token:
                continue
            name = acc.get("name") if isinstance(acc, dict) else None
            plan = acc.get("plan") if isinstance(acc, dict) else None
            status = acc.get("status", "active") if isinstance(acc, dict) else "active"
            ok, _ = save_account(provider, token, name=name, plan=plan, status=status)
            if ok:
                imported_count += 1

    return {
        "status": "ok",
        "imported_accounts": imported_count,
        "message": f"Successfully imported {imported_count} accounts across providers.",
    }


def get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    """Retrieve a configuration value from settings table."""
    init_db()
    with get_db_connection() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if not row:
        return default
    return decrypt_value(row["value"]) if key in SECRET_SETTINGS else row["value"]


def set_setting(key: str, value: str) -> None:
    """Insert or update a configuration value in settings table."""
    init_db()
    value = encrypt_value(str(value)) if key in SECRET_SETTINGS else str(value)
    with get_db_connection() as conn:
        conn.execute("""
            INSERT INTO settings (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
        """, (key, value))
        conn.commit()


def get_all_settings() -> Dict[str, str]:
    """Retrieve all persistent key-value configuration settings."""
    init_db()
    with get_db_connection() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return {r["key"]: r["value"] for r in rows if r["key"] not in SECRET_SETTINGS}


def _clean_model_key(m: str) -> str:
    """Normalize model string: strip @preset, path prefixes, whitespace and lowercase."""
    if not m:
        return ""
    m = m.lower().strip()
    if "@" in m:
        m = m.split("@")[0].strip()
    if "/" in m:
        m = m.split("/")[-1].strip()
    return m


def _get_family_candidates(model: str) -> List[str]:
    """Generate family alias candidates to resolve settings across model naming variations."""
    m = _clean_model_key(model)
    if not m:
        return []
    candidates = [m]

    # Strip common descriptive suffixes
    base = m
    for suffix in ("-thinking-search", "-thinking", "-search", "-preview", "-chat", "-direct", "-flash", "-pro"):
        if base.endswith(suffix):
            base = base[:-len(suffix)]
            candidates.append(base)
            break

    # Provider family alias clusters
    if "kimi" in m:
        candidates.extend([
            "kimi-k3-thinking-search",
            "kimi-k3-thinking",
            "kimi-k3",
            "kimi-k3-search",
            "kimi-k2.5",
            "kimi",
        ])
    elif "deepseek" in m:
        candidates.extend([
            "deepseek-v3-thinking",
            "deepseek-v3",
            "deepseek-r1",
            "deepseek-chat",
            "deepseek-reasoner",
            "deepseek",
        ])
    elif "qwen" in m or "qwq" in m:
        candidates.extend([
            "qwen-max-thinking",
            "qwen-plus-thinking",
            "qwq-32b",
            "qwen-max",
            "qwen-plus",
            "qwen",
        ])
    elif "claude" in m:
        candidates.extend([
            "claude-3-7-sonnet-thinking",
            "claude-3-7-sonnet",
            "claude-3-5-sonnet",
            "claude",
        ])
    elif "gemini" in m or "argon" in m:
        candidates.extend([
            "gemini-4-argon",
            "gemini-4-argon-thinking",
            "gemini-4-pro",
            "gemini-4-flash",
            "gemini-3.8-flash",
            "gemini-3.8-flash-thinking",
            "gemini-3.1-pro",
            "gemini-2.5-flash-thinking",
            "gemini-2.5-flash",
            "gemini-2.5-pro",
            "gemini",
        ])


    return list(dict.fromkeys(candidates))


def get_global_settings() -> Dict[str, Any]:
    """Retrieve gateway-wide global default settings across all models."""
    for key in ("model_cfg:global", "model_cfg:default"):
        raw = get_setting(key)
        if raw:
            try:
                cfg = json.loads(raw)
                if isinstance(cfg, dict) and cfg:
                    return cfg
            except Exception:
                pass
    global_cfg = {}
    tb = get_setting("global_thinking_budget")
    if tb is not None:
        try:
            global_cfg["thinking_budget"] = int(tb)
        except Exception:
            pass
    return global_cfg


def set_global_settings(cfg: Dict[str, Any]) -> None:
    """Set gateway-wide global default settings applied when no specific model override exists."""
    clean_cfg = dict(cfg)
    clean_cfg["model"] = "global"
    clean_cfg["updated_at"] = time.time()
    raw = json.dumps(clean_cfg)
    set_setting("model_cfg:global", raw)
    set_setting("model_cfg:default", raw)
    if "thinking_budget" in clean_cfg:
        set_setting("global_thinking_budget", str(clean_cfg["thinking_budget"]))


def get_model_settings(model: str) -> Dict[str, Any]:
    """Retrieve customized settings (thinking_budget, max_tokens, etc.) for a model,
    checking exact key, family aliases, provider fallback, and global defaults."""
    if not model or model.lower().strip() in ("global", "default", "*"):
        return get_global_settings()

    m = _clean_model_key(model)

    # 1. Exact match
    raw = get_setting(f"model_cfg:{m}")
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass

    # 2. Check family alias candidates (e.g. kimi-k3-thinking-search <-> kimi-k3)
    for cand in _get_family_candidates(m):
        if cand != m:
            raw = get_setting(f"model_cfg:{cand}")
            if raw:
                try:
                    return json.loads(raw)
                except Exception:
                    pass

    # 3. Check base provider prefix (e.g. "kimi", "deepseek")
    if "-" in m:
        prefix = m.split("-")[0]
        raw = get_setting(f"model_cfg:{prefix}")
        if raw:
            try:
                return json.loads(raw)
            except Exception:
                pass

    # 4. Fallback to global defaults if configured
    return get_global_settings()


def set_model_settings(model: str, cfg: Dict[str, Any], sync_family: bool = True) -> None:
    """Persist customized settings (thinking_budget, max_tokens, etc.) for a model,
    optionally syncing family variants and supporting global scope."""
    if not model:
        return
    m = _clean_model_key(model)

    if m in ("global", "default", "*"):
        set_global_settings(cfg)
        return

    clean_cfg = dict(cfg)
    clean_cfg["model"] = m
    clean_cfg["updated_at"] = time.time()
    raw = json.dumps(clean_cfg)
    set_setting(f"model_cfg:{m}", raw)

    # Also keep base family variants synchronized so Janitor AI / client variants inherit settings
    if sync_family:
        candidates = _get_family_candidates(m)
        for cand in candidates:
            if cand != m:
                cand_cfg = dict(clean_cfg)
                cand_cfg["model"] = cand
                set_setting(f"model_cfg:{cand}", json.dumps(cand_cfg))


def delete_model_settings(model: str) -> None:
    """Delete customized model settings for a model, reverting to defaults."""
    if not model:
        return
    m = _clean_model_key(model)
    init_db()
    with get_db_connection() as conn:
        for cand in _get_family_candidates(m):
            conn.execute("DELETE FROM settings WHERE key = ?", (f"model_cfg:{cand}",))
        conn.commit()


def get_all_model_settings() -> Dict[str, Dict[str, Any]]:
    """Retrieve all model settings overrides across all registered models."""
    all_s = get_all_settings()
    res = {}
    for k, v in all_s.items():
        if k.startswith("model_cfg:"):
            m = k[len("model_cfg:"):]
            try:
                res[m] = json.loads(v)
            except Exception:
                pass
    return res


# ==============================================================================
# Playground chat history
# ==============================================================================
# Chats are stored as plain text. Only credentials and secret settings are encrypted.

CHAT_ID_RE = re.compile(r"^[0-9a-f]{32}$")
CHAT_ROLES = ("user", "assistant", "system")
MAX_CHAT_TITLE = 120
DELETED_CHAT_KEEP_SECONDS = 600   # a deleted chat can be restored for this long, then it is purged
TITLE_SOURCES = ("auto", "model", "user")
MAX_MESSAGE_CHARS = 25_000_000  # generated images arrive inline as base64 data URIs
MAX_MESSAGES_PER_SAVE = 2000
MAX_ATTACHMENTS_PER_MESSAGE = 10
MAX_ATTACHMENT_CHARS = 2_000_000


def _clean_chat_title(title: Optional[str]) -> str:
    cleaned = re.sub(r"\s+", " ", title or "").strip()[:MAX_CHAT_TITLE].strip()
    return cleaned or "New chat"


def _iso_utc(value: Optional[str]) -> Optional[str]:
    """SQLite CURRENT_TIMESTAMP is UTC text ('YYYY-MM-DD HH:MM:SS'); return it as ISO 8601."""
    return value.replace(" ", "T") + "Z" if value else None


def _like_pattern(text: str) -> str:
    """Escape LIKE wildcards so a search for '50%' or 'a_b' matches those characters literally."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _purge_deleted_chats(conn: sqlite3.Connection, max_age_seconds: int) -> int:
    """Remove chats that were deleted more than max_age_seconds ago, with all their messages."""
    ids = [
        row[0] for row in conn.execute(
            "SELECT id FROM chats WHERE deleted_at IS NOT NULL AND deleted_at <= datetime('now', ?)",
            (f"-{int(max_age_seconds)} seconds",),
        )
    ]
    for chat_id in ids:
        conn.execute("DELETE FROM chat_nodes WHERE chat_id = ?", (chat_id,))
        conn.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
    if ids:
        conn.commit()
    return len(ids)


def purge_deleted(max_age_seconds: int = DELETED_CHAT_KEEP_SECONDS) -> int:
    init_db()
    with closing(get_db_connection()) as conn:
        return _purge_deleted_chats(conn, max_age_seconds)


def list_chats(limit: int = 500, query: Optional[str] = None, archived: str = "exclude") -> List[Dict[str, Any]]:
    """Return chat summaries (no message bodies): pinned chats first, then most recently updated.

    archived: "exclude" (default), "include" or "only". With `query`, only chats whose title or any
    stored message (every version, not only the active one) contains it (ASCII case-insensitive), and
    archived chats are included unless archived="only" is asked for. message_count counts every version.
    """
    init_db()
    if archived not in ("exclude", "include", "only"):
        raise ValueError("archived must be exclude, include or only")
    clauses, params = ["c.deleted_at IS NULL"], []
    needle = (query or "").strip()
    if needle and archived == "exclude":
        archived = "include"
    if archived == "exclude":
        clauses.append("c.archived_at IS NULL")
    elif archived == "only":
        clauses.append("c.archived_at IS NOT NULL")
    if needle:
        pattern = _like_pattern(needle[:200])
        clauses.append(
            "(c.title LIKE ? ESCAPE '\\' OR EXISTS ("
            "SELECT 1 FROM chat_nodes m2 WHERE m2.chat_id = c.id AND m2.content LIKE ? ESCAPE '\\'))"
        )
        params = [pattern, pattern]
    with closing(get_db_connection()) as conn:
        _purge_deleted_chats(conn, DELETED_CHAT_KEEP_SECONDS)
        rows = conn.execute(
            f"""
            SELECT c.id, c.title, c.created_at, c.updated_at, c.pinned_at, c.archived_at,
                   COALESCE(c.title_source, 'user') AS title_source,
                   (SELECT COUNT(*) FROM chat_nodes m WHERE m.chat_id = c.id) AS message_count
            FROM chats c
            WHERE {" AND ".join(clauses)}
            ORDER BY (c.pinned_at IS NULL), c.pinned_at DESC, c.updated_at DESC, c.rowid DESC
            LIMIT ?
            """,
            (*params, max(1, int(limit))),
        ).fetchall()
    return [_chat_summary(r) for r in rows]


def _chat_summary(r) -> Dict[str, Any]:
    return {
        "id": r["id"],
        "title": r["title"],
        "created_at": _iso_utc(r["created_at"]),
        "updated_at": _iso_utc(r["updated_at"]),
        "message_count": r["message_count"],
        "pinned": r["pinned_at"] is not None,
        "archived": r["archived_at"] is not None,
        "title_source": r["title_source"],
    }


def create_chat(title: Optional[str] = None) -> Dict[str, Any]:
    init_db()
    chat_id = uuid.uuid4().hex
    with closing(get_db_connection()) as conn:
        conn.execute("INSERT INTO chats (id, title, title_source) VALUES (?, ?, 'auto')", (chat_id, _clean_chat_title(title)))
        conn.commit()
        row = conn.execute(
            "SELECT *, COALESCE(title_source, 'user') AS ts, 0 AS message_count FROM chats WHERE id = ?", (chat_id,)
        ).fetchone()
    summary = _chat_summary({**dict(row), "title_source": row["ts"]})
    summary["tools"] = []
    summary["settings"] = {}
    return summary


def _load_attachments(raw: Optional[str]) -> List[Dict[str, Any]]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except ValueError:
        return []
    return value if isinstance(value, list) else []


def _clean_attachments(value: Any, offset: int) -> Optional[str]:
    """Validate a message's attachments and return them as JSON text (None when there are none)."""
    if value in (None, []):
        return None
    if not isinstance(value, list) or len(value) > MAX_ATTACHMENTS_PER_MESSAGE:
        raise ValueError(f"message {offset}: attachments must be a list of at most {MAX_ATTACHMENTS_PER_MESSAGE} items")
    cleaned = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError(f"message {offset}: each attachment must be an object")
        name, text, mime, size = item.get("name"), item.get("text"), item.get("mime"), item.get("size")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"message {offset}: attachment name must be a non-empty string")
        if not isinstance(text, str) or len(text) > MAX_ATTACHMENT_CHARS:
            raise ValueError(f"message {offset}: attachment text must be a string of at most {MAX_ATTACHMENT_CHARS} characters")
        cleaned.append({
            "name": name.strip()[:255],
            "mime": mime[:100] if isinstance(mime, str) else "text/plain",
            "size": int(size) if isinstance(size, (int, float)) and not isinstance(size, bool) and size >= 0 else len(text),
            "text": text,
        })
    return json.dumps(cleaned, ensure_ascii=False)


MAX_STEPS_PER_MESSAGE = 12
MAX_CALLS_PER_STEP = 12
MAX_STEPS_JSON_CHARS = 200_000
TOOL_NAME_RE = re.compile(r"^[a-z0-9_]{1,40}$")


def _load_json_list(raw: Optional[str]) -> List[Any]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except ValueError:
        return []
    return value if isinstance(value, list) else []


def _nonneg_int(value: Any, default: int = 0) -> int:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
        return int(value)
    return default


def _http_url(value: Any) -> str:
    return value if isinstance(value, str) and value.startswith(("http://", "https://")) and len(value) <= 2000 else ""


def _clean_steps(value: Any, offset: int) -> Optional[str]:
    """Validate the tool steps of an assistant message and return them as JSON text (None when empty).

    Page text is never stored, only what the dashboard shows: queries, result titles, URLs and
    snippets. URLs must be http(s).
    """
    if value in (None, []):
        return None
    if not isinstance(value, list) or len(value) > MAX_STEPS_PER_MESSAGE:
        raise ValueError(f"message {offset}: steps must be a list of at most {MAX_STEPS_PER_MESSAGE} items")
    cleaned = []
    for step in value:
        if not isinstance(step, dict):
            raise ValueError(f"message {offset}: each step must be an object")
        raw_calls = step.get("calls") or []
        if not isinstance(raw_calls, list) or len(raw_calls) > MAX_CALLS_PER_STEP:
            raise ValueError(f"message {offset}: a step has at most {MAX_CALLS_PER_STEP} calls")
        calls = []
        for call in raw_calls:
            if not isinstance(call, dict) or not isinstance(call.get("name"), str) or not call["name"].strip():
                raise ValueError(f"message {offset}: each call needs a name")
            sources = []
            for src in (call.get("sources") or [])[:20]:
                url = _http_url(src.get("url")) if isinstance(src, dict) else ""
                if not url:
                    continue
                sources.append({
                    "n": _nonneg_int(src.get("n"), len(sources) + 1),
                    "title": str(src.get("title") or url)[:200],
                    "url": url,
                    "snippet": str(src.get("snippet") or "")[:300],
                })
            args = call.get("arguments") if isinstance(call.get("arguments"), dict) else {}
            if len(json.dumps(args, ensure_ascii=False)) > 2000:
                args = {}
            calls.append({
                "id": str(call.get("id") or "")[:20],
                "name": call["name"].strip()[:60],
                "arguments": args,
                "ok": call["ok"] if isinstance(call.get("ok"), bool) else None,
                "summary": str(call.get("summary") or "")[:200],
                "backend": str(call.get("backend") or "")[:60],
                "ms": _nonneg_int(call.get("ms")),
                "error": str(call.get("error") or "")[:500],
                "sources": sources,
            })
        entry = {
            "step": _nonneg_int(step.get("step"), len(cleaned) + 1),
            "reasoning": str(step.get("reasoning") or "")[:20000],
            "calls": calls,
        }
        if isinstance(step.get("ms"), (int, float)) and not isinstance(step.get("ms"), bool) and step["ms"] >= 0:
            entry["ms"] = int(step["ms"])
        if step.get("limit") is True:
            entry["limit"] = True
        if step.get("error"):
            entry["error"] = str(step["error"])[:500]
        cleaned.append(entry)
    text = json.dumps(cleaned, ensure_ascii=False)
    if len(text) > MAX_STEPS_JSON_CHARS:
        raise ValueError(f"message {offset}: steps are too large")
    return text


def set_chat_tools(chat_id: str, names: Any) -> bool:
    """Remember which tools are switched on for a chat. Returns False if the chat does not exist."""
    if not CHAT_ID_RE.match(chat_id or ""):
        return False
    if names is None:
        names = []
    if not isinstance(names, list) or len(names) > 10 or any(not isinstance(n, str) or not TOOL_NAME_RE.match(n) for n in names):
        raise ValueError("tools must be a list of at most 10 tool names")
    init_db()
    with closing(get_db_connection()) as conn:
        cur = conn.execute(
            "UPDATE chats SET tools = ? WHERE id = ? AND deleted_at IS NULL",
            (json.dumps(list(dict.fromkeys(names))) if names else None, chat_id),
        )
        conn.commit()
        return cur.rowcount > 0


# Overrides a chat may carry. A key that is absent follows the model's saved setting.
CHAT_SETTING_KEYS = ("thinking_budget", "max_tokens", "temperature", "system_prompt")
MAX_CHAT_SYSTEM_PROMPT = 20_000


def _load_chat_settings(raw: Optional[str]) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except ValueError:
        return {}
    return {k: value[k] for k in CHAT_SETTING_KEYS if isinstance(value, dict) and k in value}


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value or value in (float("inf"), float("-inf")):
        raise ValueError(f"{name} must be a number")
    return value


def _clean_chat_settings(value: Any) -> Dict[str, Any]:
    """Validate a chat's overrides. Numbers are clamped like the model settings API does."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("settings must be an object or null")
    unknown = sorted(set(value) - set(CHAT_SETTING_KEYS))
    if unknown:
        raise ValueError(f"Unknown chat setting: {', '.join(unknown)}")
    clean: Dict[str, Any] = {}
    if "thinking_budget" in value:
        clean["thinking_budget"] = max(0, min(65536, int(_number(value["thinking_budget"], "thinking_budget"))))
    if "max_tokens" in value:
        clean["max_tokens"] = max(1, min(131072, int(_number(value["max_tokens"], "max_tokens"))))
    if "temperature" in value:
        clean["temperature"] = round(max(0.0, min(2.0, float(_number(value["temperature"], "temperature")))), 2)
    if "system_prompt" in value:
        prompt = value["system_prompt"]
        if not isinstance(prompt, str) or len(prompt) > MAX_CHAT_SYSTEM_PROMPT:
            raise ValueError(f"system_prompt must be text of at most {MAX_CHAT_SYSTEM_PROMPT} characters")
        clean["system_prompt"] = prompt
    return clean


def set_chat_settings(chat_id: str, settings: Any) -> bool:
    """Replace a chat's overrides (None or {} clears them). Returns False if the chat does not exist."""
    clean = _clean_chat_settings(settings)
    if not CHAT_ID_RE.match(chat_id or ""):
        return False
    init_db()
    with closing(get_db_connection()) as conn:
        cur = conn.execute(
            "UPDATE chats SET settings = ? WHERE id = ? AND deleted_at IS NULL",
            (json.dumps(clean) if clean else None, chat_id),
        )
        conn.commit()
        return cur.rowcount > 0


def _active_path(chat_row, rows):
    """The nodes on a chat's active path, in order, and the children of every node (None = roots)."""
    by_id = {r["id"]: r for r in rows}
    children: Dict[Optional[int], List[int]] = {}
    for r in rows:
        children.setdefault(r["parent_id"], []).append(r["id"])   # rows come ordered by id
    path, seen = [], set()
    current = chat_row["root_active_id"]
    while current is not None and current in by_id and current not in seen:
        seen.add(current)
        node = by_id[current]
        path.append(node)
        current = node["active_child_id"]
    return path, children


_NODE_COLUMNS = (
    "id, parent_id, role, content, reasoning, model, elapsed_ms, thought_ms, created_at, attachments, steps, active_child_id, cut_off"
)


def _node_versions(node_id: int, parent_id: Optional[int], children) -> Dict[str, Any]:
    ids = children.get(parent_id, [node_id])
    return {"ids": ids, "index": ids.index(node_id) if node_id in ids else 0}


def get_chat(chat_id: str) -> Optional[Dict[str, Any]]:
    """Return a chat with its active path of messages, or None if it does not exist.

    Each message carries its node `id`, `parent_id` and `versions` ({ids, index}: the messages that
    share its parent, in creation order, and which one this is).
    """
    if not CHAT_ID_RE.match(chat_id or ""):
        return None
    init_db()
    with closing(get_db_connection()) as conn:
        chat = conn.execute("SELECT * FROM chats WHERE id = ? AND deleted_at IS NULL", (chat_id,)).fetchone()
        if not chat:
            return None
        rows = conn.execute(
            f"SELECT {_NODE_COLUMNS} FROM chat_nodes WHERE chat_id = ? ORDER BY id", (chat_id,)
        ).fetchall()
    path, children = _active_path(chat, rows)
    return {
        "id": chat["id"],
        "title": chat["title"],
        "created_at": _iso_utc(chat["created_at"]),
        "updated_at": _iso_utc(chat["updated_at"]),
        "tools": _load_json_list(chat["tools"]),
        "settings": _load_chat_settings(chat["settings"]),
        "pinned": chat["pinned_at"] is not None,
        "archived": chat["archived_at"] is not None,
        "title_source": chat["title_source"] or "user",
        "messages": [
            {
                "id": r["id"],
                "parent_id": r["parent_id"],
                "versions": _node_versions(r["id"], r["parent_id"], children),
                "role": r["role"],
                "content": r["content"],
                "reasoning": r["reasoning"],
                "model": r["model"],
                "elapsed_ms": r["elapsed_ms"],
                "thought_ms": r["thought_ms"],
                "created_at": _iso_utc(r["created_at"]),
                "attachments": _load_attachments(r["attachments"]),
                "steps": _load_json_list(r["steps"]),
                "cut_off": bool(r["cut_off"]),
            }
            for r in path
        ],
    }


def rename_chat(chat_id: str, title: str) -> bool:
    """A name typed by the user. It also stops generated titles from replacing it."""
    if not CHAT_ID_RE.match(chat_id or ""):
        return False
    init_db()
    with closing(get_db_connection()) as conn:
        cur = conn.execute(
            "UPDATE chats SET title = ?, title_source = 'user' WHERE id = ? AND deleted_at IS NULL",
            (_clean_chat_title(title), chat_id),
        )
        conn.commit()
        return cur.rowcount > 0


def apply_generated_title(chat_id: str, title: str) -> Optional[bool]:
    """Use a model-written title. Returns None if the chat does not exist, False if the chat already
    has a title the user wrote (or one generated before), True when the title was applied."""
    if not CHAT_ID_RE.match(chat_id or ""):
        return None
    init_db()
    cleaned = _clean_chat_title(title)
    with closing(get_db_connection()) as conn:
        row = conn.execute(
            "SELECT title_source FROM chats WHERE id = ? AND deleted_at IS NULL", (chat_id,)
        ).fetchone()
        if not row:
            return None
        if row["title_source"] != "auto" or not (title or "").strip():
            return False
        conn.execute("UPDATE chats SET title = ?, title_source = 'model' WHERE id = ?", (cleaned, chat_id))
        conn.commit()
        return True


def set_chat_flags(chat_id: str, pinned: Optional[bool] = None, archived: Optional[bool] = None) -> bool:
    """Pin/unpin and archive/restore a chat. None leaves a flag alone. False if the chat does not exist."""
    if not CHAT_ID_RE.match(chat_id or ""):
        return False
    for value in (pinned, archived):
        if value is not None and not isinstance(value, bool):
            raise ValueError("pinned and archived must be true or false")
    init_db()
    with closing(get_db_connection()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            if not conn.execute("SELECT 1 FROM chats WHERE id = ? AND deleted_at IS NULL", (chat_id,)).fetchone():
                conn.rollback()
                return False
            if pinned is True:
                # Millisecond precision keeps two pins in one second in the order they were made.
                conn.execute("UPDATE chats SET pinned_at = strftime('%Y-%m-%d %H:%M:%f', 'now') WHERE id = ? AND pinned_at IS NULL", (chat_id,))
            elif pinned is False:
                conn.execute("UPDATE chats SET pinned_at = NULL WHERE id = ?", (chat_id,))
            if archived is True:
                conn.execute("UPDATE chats SET archived_at = CURRENT_TIMESTAMP WHERE id = ? AND archived_at IS NULL", (chat_id,))
            elif archived is False:
                conn.execute("UPDATE chats SET archived_at = NULL WHERE id = ?", (chat_id,))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return True


def delete_chat(chat_id: str, now: bool = False) -> bool:
    """Soft delete: hide the chat so it can be restored for DELETED_CHAT_KEEP_SECONDS, then it is purged.
    With now=True the chat and all its messages are removed at once. False if there is no such chat."""
    if not CHAT_ID_RE.match(chat_id or ""):
        return False
    init_db()
    with closing(get_db_connection()) as conn:
        if now:
            conn.execute("DELETE FROM chat_nodes WHERE chat_id = ?", (chat_id,))
            cur = conn.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
        else:
            cur = conn.execute(
                "UPDATE chats SET deleted_at = CURRENT_TIMESTAMP WHERE id = ? AND deleted_at IS NULL", (chat_id,)
            )
        conn.commit()
        return cur.rowcount > 0


def restore_chat(chat_id: str) -> bool:
    """Undo a soft delete. False if the chat was not deleted, or has already been purged."""
    if not CHAT_ID_RE.match(chat_id or ""):
        return False
    init_db()
    with closing(get_db_connection()) as conn:
        _purge_deleted_chats(conn, DELETED_CHAT_KEEP_SECONDS)
        cur = conn.execute("UPDATE chats SET deleted_at = NULL WHERE id = ? AND deleted_at IS NOT NULL", (chat_id,))
        conn.commit()
        return cur.rowcount > 0


MAX_VERSIONS_PER_PARENT = 50


def _point_to(conn: sqlite3.Connection, chat_id: str, parent_id: Optional[int], child_id: Optional[int]) -> None:
    """Make child_id the shown child of parent_id (or the shown first message when parent_id is None)."""
    if parent_id is None:
        conn.execute("UPDATE chats SET root_active_id = ? WHERE id = ?", (child_id, chat_id))
    else:
        conn.execute("UPDATE chat_nodes SET active_child_id = ? WHERE id = ?", (child_id, parent_id))


def save_chat_nodes(chat_id: str, from_index: int, messages: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Save `messages` at position `from_index` of the chat's active path. Nothing is deleted.

    The messages become a chain under the node at from_index - 1. Appending at the end extends the
    chat; anywhere earlier (retry, edit) the first new message becomes a sibling of the node that was
    there, which is a new version, and the new chain turns active. An empty list with from_index below
    the end makes the path stop at from_index (the old messages stay as hidden versions).

    Returns {"message_count", "nodes": [{"id", "versions"}]} or None if the chat does not exist.
    Raises ValueError for invalid input, a from_index that would leave a gap, or too many versions.
    """
    if not CHAT_ID_RE.match(chat_id or ""):
        return None
    if not isinstance(from_index, int) or isinstance(from_index, bool) or from_index < 0:
        raise ValueError("from_index must be a non-negative integer")
    if not isinstance(messages, list) or len(messages) > MAX_MESSAGES_PER_SAVE:
        raise ValueError(f"messages must be a list of at most {MAX_MESSAGES_PER_SAVE} items")

    rows = []
    for offset, msg in enumerate(messages):
        if not isinstance(msg, dict) or msg.get("role") not in CHAT_ROLES:
            raise ValueError(f"message {offset}: role must be one of {', '.join(CHAT_ROLES)}")
        content = msg.get("content")
        if not isinstance(content, str) or len(content) > MAX_MESSAGE_CHARS:
            raise ValueError(f"message {offset}: content must be a string of at most {MAX_MESSAGE_CHARS} characters")
        reasoning = msg.get("reasoning")
        model = msg.get("model")
        elapsed = msg.get("elapsed_ms")
        thought = msg.get("thought_ms")
        rows.append((
            msg["role"],
            content,
            reasoning if isinstance(reasoning, str) and reasoning else None,
            model[:200] if isinstance(model, str) and model else None,
            int(elapsed) if isinstance(elapsed, (int, float)) and not isinstance(elapsed, bool) and elapsed >= 0 else None,
            int(thought) if isinstance(thought, (int, float)) and not isinstance(thought, bool) and thought >= 0 else None,
            _clean_attachments(msg.get("attachments"), offset),
            _clean_steps(msg.get("steps"), offset) if msg["role"] == "assistant" else None,
            1 if msg["role"] == "assistant" and msg.get("cut_off") is True else None,
        ))

    init_db()
    with closing(get_db_connection()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            chat = conn.execute("SELECT * FROM chats WHERE id = ? AND deleted_at IS NULL", (chat_id,)).fetchone()
            if not chat:
                conn.rollback()
                return None
            nodes = conn.execute(
                f"SELECT {_NODE_COLUMNS} FROM chat_nodes WHERE chat_id = ? ORDER BY id", (chat_id,)
            ).fetchall()
            path, children = _active_path(chat, nodes)
            if from_index > len(path):
                raise ValueError(f"from_index {from_index} is beyond the stored length {len(path)}")
            parent_id = path[from_index - 1]["id"] if from_index > 0 else None

            if not rows:
                if from_index < len(path):
                    _point_to(conn, chat_id, parent_id, None)
                conn.commit()
                return {"message_count": from_index, "nodes": []}

            siblings = list(children.get(parent_id, []))
            if len(siblings) >= MAX_VERSIONS_PER_PARENT:
                raise ValueError(f"this message already has {MAX_VERSIONS_PER_PARENT} versions")

            saved, previous = [], parent_id
            for row in rows:
                cur = conn.execute(
                    "INSERT INTO chat_nodes (chat_id, parent_id, role, content, reasoning, model, elapsed_ms, "
                    "thought_ms, attachments, steps, cut_off) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (chat_id, previous, *row),
                )
                node_id = cur.lastrowid
                _point_to(conn, chat_id, previous, node_id)
                saved.append(node_id)
                previous = node_id
            # Using an archived chat again brings it back to the main list.
            conn.execute("UPDATE chats SET updated_at = CURRENT_TIMESTAMP, archived_at = NULL WHERE id = ?", (chat_id,))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    first_versions = siblings + [saved[0]]
    return {
        "message_count": from_index + len(saved),
        "nodes": [
            {"id": node_id, "versions": {"ids": first_versions, "index": len(first_versions) - 1} if i == 0
             else {"ids": [node_id], "index": 0}}
            for i, node_id in enumerate(saved)
        ],
    }


class ChatConflictError(Exception):
    """The request is valid but does not fit the chat as it is now (HTTP 409)."""


def _optional_ms(value: Any, name: str) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value or value < 0:
        raise ValueError(f"{name} must be a non-negative number")
    return int(value)


def extend_chat_message(chat_id: str, node_id: Any, content: Any, elapsed_ms: Any = None, thought_ms: Any = None,
                        reasoning: Any = None, cut_off: Any = None) -> Optional[Dict[str, Any]]:
    """Add to a saved reply in place (Continue). No new version is made.

    Only the last message of the chat's active path may be extended, it must be an assistant reply, and
    `content` must start with the stored text, so this can not be used to edit what was said. Fields
    that are None stay as they were; `cut_off` False clears the flag. Returns {"id", "cut_off"}, or None
    if the chat does not exist. Raises ValueError for invalid input and ChatConflictError when the
    message is not the last one shown.
    """
    if not CHAT_ID_RE.match(chat_id or ""):
        return None
    if not isinstance(node_id, int) or isinstance(node_id, bool):
        raise ValueError("node id must be an integer")
    if not isinstance(content, str) or len(content) > MAX_MESSAGE_CHARS:
        raise ValueError(f"content must be a string of at most {MAX_MESSAGE_CHARS} characters")
    elapsed = _optional_ms(elapsed_ms, "elapsed_ms")
    thought = _optional_ms(thought_ms, "thought_ms")
    if reasoning is not None and not isinstance(reasoning, str):
        raise ValueError("reasoning must be a string")
    if cut_off is not None and not isinstance(cut_off, bool):
        raise ValueError("cut_off must be true or false")

    init_db()
    with closing(get_db_connection()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            chat = conn.execute("SELECT * FROM chats WHERE id = ? AND deleted_at IS NULL", (chat_id,)).fetchone()
            node = conn.execute(
                f"SELECT {_NODE_COLUMNS} FROM chat_nodes WHERE id = ? AND chat_id = ?", (node_id, chat_id)
            ).fetchone() if chat else None
            if not chat or not node:
                conn.rollback()
                return None
            rows = conn.execute(f"SELECT {_NODE_COLUMNS} FROM chat_nodes WHERE chat_id = ? ORDER BY id", (chat_id,)).fetchall()
            path, _ = _active_path(chat, rows)
            if node["role"] != "assistant" or not path or path[-1]["id"] != node_id:
                raise ChatConflictError("Only the last reply of the chat can be continued")
            if not content.startswith(node["content"]):
                raise ValueError("The new text must start with the text that is already saved")
            flag = node["cut_off"] if cut_off is None else (1 if cut_off else None)
            conn.execute(
                "UPDATE chat_nodes SET content = ?, reasoning = ?, elapsed_ms = ?, thought_ms = ?, cut_off = ? WHERE id = ?",
                (
                    content,
                    (reasoning or None) if reasoning is not None else node["reasoning"],
                    node["elapsed_ms"] if elapsed is None else elapsed,
                    node["thought_ms"] if thought is None else thought,
                    flag,
                    node_id,
                ),
            )
            conn.execute("UPDATE chats SET updated_at = CURRENT_TIMESTAMP, archived_at = NULL WHERE id = ?", (chat_id,))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return {"id": node_id, "cut_off": bool(flag)}


def save_chat_messages(chat_id: str, from_index: int, messages: List[Dict[str, Any]]) -> Optional[int]:
    """save_chat_nodes() returning only the new message count (None if the chat does not exist)."""
    result = save_chat_nodes(chat_id, from_index, messages)
    return None if result is None else result["message_count"]


def set_active_node(chat_id: str, node_id: Any) -> bool:
    """Show the given version: it, and every message above it, becomes the active branch.

    Messages below it follow the branch that was last shown under them. Returns False if the chat
    or the node does not exist (a node of another chat counts as not existing).
    """
    if not CHAT_ID_RE.match(chat_id or ""):
        return False
    if not isinstance(node_id, int) or isinstance(node_id, bool):
        raise ValueError("node_id must be an integer")
    init_db()
    with closing(get_db_connection()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            node = conn.execute(
                "SELECT n.id, n.parent_id FROM chat_nodes n JOIN chats c ON c.id = n.chat_id "
                "WHERE n.id = ? AND n.chat_id = ? AND c.deleted_at IS NULL",
                (node_id, chat_id),
            ).fetchone()
            if not node:
                conn.rollback()
                return False
            current = node
            while True:
                _point_to(conn, chat_id, current["parent_id"], current["id"])
                if current["parent_id"] is None:
                    break
                current = conn.execute("SELECT id, parent_id FROM chat_nodes WHERE id = ?", (current["parent_id"],)).fetchone()
            conn.execute("UPDATE chats SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (chat_id,))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return True


if __name__ == "__main__":
    init_db()
    all_acc = get_accounts()
    print(f"[+] Eclipse Credential DB initialized. Stored accounts: {len(all_acc)}")
    for a in all_acc:
        print(f"  - [{a['provider'].upper()}] {a['name']} ({a['identifier']})")


# ==============================================================================
# Presets (see presets/: a preset is applied to a request that asks for `model@name`)
# ==============================================================================

def _preset_row(row: sqlite3.Row) -> Dict[str, Any]:
    try:
        blocks = json.loads(row["blocks"] or "[]")
    except ValueError:
        blocks = []
    try:
        scripts = json.loads(row["regex_scripts"] or "[]")
    except ValueError:
        scripts = []
    try:
        links = json.loads(row["lorebooks"] or "[]")
    except ValueError:
        links = []
    try:
        tool_list = json.loads(row["tools"] or "[]")
    except ValueError:
        tool_list = []
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "tools": [t for t in tool_list if isinstance(t, str)] if isinstance(tool_list, list) else [],
        "tool_max_steps": row["tool_max_steps"] or preset_schema.DEFAULT_TOOL_STEPS,
        "tool_guidance": row["tool_guidance"] or "",
        "tool_guidance_on": bool(row["tool_guidance_on"]),
        "blocks": blocks if isinstance(blocks, list) else [],
        "regex_scripts": scripts if isinstance(scripts, list) else [],
        "lorebooks": links if isinstance(links, list) else [],
        "placement": row["placement"],
        "separator": row["separator"],
        "char_name": row["char_name"],
        "user_name": row["user_name"],
        "created_at": _iso_utc(row["created_at"]),
        "updated_at": _iso_utc(row["updated_at"]),
    }


def list_presets() -> List[Dict[str, Any]]:
    init_db()
    with closing(get_db_connection()) as conn:
        rows = conn.execute("SELECT * FROM presets ORDER BY name").fetchall()
    return [_preset_row(r) for r in rows]


def get_preset(name: str) -> Optional[Dict[str, Any]]:
    init_db()
    if not isinstance(name, str) or not name.strip():
        return None
    with closing(get_db_connection()) as conn:
        row = conn.execute("SELECT * FROM presets WHERE name = ? COLLATE NOCASE", (name.strip(),)).fetchone()
    return _preset_row(row) if row else None


def _check_lorebook_links(names: List[str]) -> None:
    if not names:
        return
    with closing(get_db_connection()) as conn:
        marks = ",".join("?" for _ in names)
        known = {r["name"] for r in conn.execute(f"SELECT name FROM lorebooks WHERE name IN ({marks})", names)}
    missing = [n for n in names if n not in known]
    if missing:
        raise preset_schema.PresetError(f"Unknown lorebook: {', '.join(missing)}")


def create_preset(data: Any) -> Dict[str, Any]:
    """Store a new preset. Raises PresetError for a bad body or a name that is taken."""
    init_db()
    clean = preset_schema.clean_preset(data)
    _check_lorebook_links(clean["lorebooks"])
    try:
        with closing(get_db_connection()) as conn:
            conn.execute(
                "INSERT INTO presets (name, description, blocks, placement, separator, char_name, user_name, regex_scripts, lorebooks,"
                " tools, tool_max_steps, tool_guidance, tool_guidance_on) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (clean["name"], clean["description"], json.dumps(clean["blocks"]), clean["placement"],
                 clean["separator"], clean["char_name"], clean["user_name"], json.dumps(clean["regex_scripts"]),
                 json.dumps(clean["lorebooks"]), json.dumps(clean["tools"]), clean["tool_max_steps"],
                 clean["tool_guidance"], int(clean["tool_guidance_on"])),
            )
            conn.commit()
    except sqlite3.IntegrityError:
        raise preset_schema.PresetError(f"A preset named '{clean['name']}' already exists")
    return get_preset(clean["name"])


def update_preset(name: str, data: Any) -> Optional[Dict[str, Any]]:
    """Change the fields that were sent (the name too). Returns None when the preset does not exist."""
    init_db()
    current = get_preset(name)
    if not current:
        return None
    clean = preset_schema.clean_preset(data, partial=True)
    if not clean:
        return current
    _check_lorebook_links(clean.get("lorebooks", []))
    fields = []
    values: List[Any] = []
    for key, value in clean.items():
        fields.append(f"{key} = ?")
        values.append(json.dumps(value) if key in ("blocks", "regex_scripts", "lorebooks", "tools") else int(value) if key == "tool_guidance_on" else value)
    try:
        with closing(get_db_connection()) as conn:
            conn.execute(
                f"UPDATE presets SET {', '.join(fields)}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (*values, current["id"]),
            )
            conn.commit()
    except sqlite3.IntegrityError:
        raise preset_schema.PresetError(f"A preset named '{clean.get('name')}' already exists")
    return get_preset(clean.get("name", current["name"]))


def delete_preset(name: str) -> bool:
    init_db()
    if not isinstance(name, str):
        return False
    with closing(get_db_connection()) as conn:
        cur = conn.execute("DELETE FROM presets WHERE name = ?", (name.strip().lower(),))
        conn.commit()
    return cur.rowcount > 0


def _seed_default_presets(conn: sqlite3.Connection) -> None:
    try:
        defaults = preset_defaults.get_default_presets()
    except Exception:
        return
    existing = {row["name"] for row in conn.execute("SELECT name FROM presets").fetchall()}
    for d in defaults:
        try:
            clean = preset_schema.clean_preset(d)
        except Exception:
            continue
        if clean["name"] in existing:
            continue
        conn.execute(
            "INSERT INTO presets (name, description, blocks, placement, separator, char_name, user_name, regex_scripts, lorebooks,"
            " tools, tool_max_steps, tool_guidance, tool_guidance_on) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                clean["name"],
                clean["description"],
                json.dumps(clean["blocks"]),
                clean["placement"],
                clean["separator"],
                clean["char_name"],
                clean["user_name"],
                json.dumps(clean["regex_scripts"]),
                json.dumps(clean["lorebooks"]),
                json.dumps(clean["tools"]),
                clean["tool_max_steps"],
                clean["tool_guidance"],
                int(clean["tool_guidance_on"]),
            ),
        )
        existing.add(clean["name"])


# ==============================================================================
# Lorebooks (see presets/lorebook.py: entries added to the prompt when the chat mentions them)
# ==============================================================================

def _lorebook_row(row: sqlite3.Row, with_entries: bool = True) -> Dict[str, Any]:
    try:
        entries = json.loads(row["entries"] or "[]")
    except ValueError:
        entries = []
    entries = entries if isinstance(entries, list) else []
    out = {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "scan_depth": row["scan_depth"],
        "token_budget": row["token_budget"],
        "recursive": bool(row["recursive"]),
        "entry_count": len(entries),
        "enabled_count": sum(1 for e in entries if isinstance(e, dict) and not e.get("disabled")),
        "created_at": _iso_utc(row["created_at"]),
        "updated_at": _iso_utc(row["updated_at"]),
    }
    if with_entries:
        out["entries"] = entries
    return out


def list_lorebooks() -> List[Dict[str, Any]]:
    """Every lorebook without its entries (they can be large)."""
    init_db()
    with closing(get_db_connection()) as conn:
        rows = conn.execute("SELECT * FROM lorebooks ORDER BY name").fetchall()
    return [_lorebook_row(r, with_entries=False) for r in rows]


def get_lorebook(name: str) -> Optional[Dict[str, Any]]:
    init_db()
    if not isinstance(name, str):
        return None
    with closing(get_db_connection()) as conn:
        row = conn.execute("SELECT * FROM lorebooks WHERE name = ?", (name.strip().lower(),)).fetchone()
    return _lorebook_row(row) if row else None


def create_lorebook(data: Any) -> Dict[str, Any]:
    """Store a new lorebook. Raises LoreError for a bad body or a name that is taken."""
    init_db()
    clean = lore.clean_lorebook(data)
    try:
        with closing(get_db_connection()) as conn:
            conn.execute(
                "INSERT INTO lorebooks (name, description, scan_depth, token_budget, recursive, entries) VALUES (?, ?, ?, ?, ?, ?)",
                (clean["name"], clean["description"], clean["scan_depth"], clean["token_budget"], int(clean["recursive"]),
                 json.dumps(clean["entries"])),
            )
            conn.commit()
    except sqlite3.IntegrityError:
        raise lore.LoreError(f"A lorebook named '{clean['name']}' already exists")
    return get_lorebook(clean["name"])


def update_lorebook(name: str, data: Any) -> Optional[Dict[str, Any]]:
    """Change the fields that were sent (the name too, which updates the presets that link it)."""
    init_db()
    current = get_lorebook(name)
    if not current:
        return None
    clean = lore.clean_lorebook(data, partial=True)
    if not clean:
        return current
    fields, values = [], []
    for key, value in clean.items():
        fields.append(f"{key} = ?")
        values.append(json.dumps(value) if key == "entries" else int(value) if key == "recursive" else value)
    try:
        with closing(get_db_connection()) as conn:
            conn.execute(f"UPDATE lorebooks SET {', '.join(fields)}, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (*values, current["id"]))
            conn.commit()
    except sqlite3.IntegrityError:
        raise lore.LoreError(f"A lorebook named '{clean.get('name')}' already exists")
    new_name = clean.get("name", current["name"])
    if new_name != current["name"]:
        _relink_lorebook(current["name"], new_name)
    return get_lorebook(new_name)


def _relink_lorebook(old: str, new: Optional[str]) -> None:
    """Rename (or, with new=None, remove) a lorebook in every preset that links it."""
    with closing(get_db_connection()) as conn:
        for row in conn.execute("SELECT id, lorebooks FROM presets").fetchall():
            try:
                links = json.loads(row["lorebooks"] or "[]")
            except ValueError:
                continue
            if old not in links:
                continue
            links = [new if n == old else n for n in links]
            links = [n for n in dict.fromkeys(links) if n]
            conn.execute("UPDATE presets SET lorebooks = ? WHERE id = ?", (json.dumps(links), row["id"]))
        conn.commit()


# ==============================================================================
# External provider connections (see connections.py and engines/openai_compat.py)
# ==============================================================================

def _connection_row(row: sqlite3.Row, with_key: bool = False) -> Dict[str, Any]:
    try:
        headers = json.loads(row["headers"] or "{}")
    except ValueError:
        headers = {}
    try:
        models = json.loads(row["models"] or "[]")
    except ValueError:
        models = []
    stored = row["api_key"] or ""
    out = {
        "id": row["id"], "name": row["name"], "base_url": row["base_url"], "requires_key": bool(row["requires_key"]),
        "key_saved": bool(stored), "headers": headers if isinstance(headers, dict) else {},
        "models": [m for m in models if isinstance(m, str)] if isinstance(models, list) else [],
        "models_at": _iso_utc(row["models_at"]) if row["models_at"] else None, "enabled": bool(row["enabled"]),
    }
    if with_key:
        out["api_key"] = decrypt_value(stored) if stored else ""
    return out


def list_connections() -> List[Dict[str, Any]]:
    """Every connection, without keys."""
    init_db()
    with closing(get_db_connection()) as conn:
        rows = conn.execute("SELECT * FROM connections ORDER BY name").fetchall()
    return [_connection_row(r) for r in rows]


def get_connection(name: str, with_key: bool = False) -> Optional[Dict[str, Any]]:
    init_db()
    if not isinstance(name, str):
        return None
    with closing(get_db_connection()) as conn:
        row = conn.execute("SELECT * FROM connections WHERE name = ?", (name.strip().lower(),)).fetchone()
    return _connection_row(row, with_key) if row else None


def create_connection(data: Any) -> Dict[str, Any]:
    init_db()
    clean = conn_rules.clean_connection(data)
    try:
        with closing(get_db_connection()) as conn:
            conn.execute(
                "INSERT INTO connections (name, base_url, api_key, requires_key, headers, models, enabled) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (clean["name"], clean["base_url"], encrypt_value(clean["api_key"]) if clean.get("api_key") else "", int(clean["requires_key"]),
                 json.dumps(clean["headers"]), json.dumps(clean["models"]), int(clean["enabled"])),
            )
            conn.commit()
    except sqlite3.IntegrityError:
        raise conn_rules.ConnectionConfigError(f"A connection named '{clean['name']}' already exists")
    return get_connection(clean["name"])


def update_connection(name: str, data: Any) -> Optional[Dict[str, Any]]:
    """Change the fields that were sent. A missing api_key keeps the stored one; an empty one removes it."""
    init_db()
    current = get_connection(name)
    if not current:
        return None
    clean = conn_rules.clean_connection(data, partial=True)
    if not clean:
        return current
    fields, values = [], []
    for key, value in clean.items():
        if key == "api_key":
            fields.append("api_key = ?")
            values.append(encrypt_value(value) if value else "")
        elif key in ("headers", "models"):
            fields.append(f"{key} = ?")
            values.append(json.dumps(value))
        elif key in ("requires_key", "enabled"):
            fields.append(f"{key} = ?")
            values.append(int(value))
        else:
            fields.append(f"{key} = ?")
            values.append(value)
    try:
        with closing(get_db_connection()) as conn:
            conn.execute(f"UPDATE connections SET {', '.join(fields)} WHERE id = ?", (*values, current["id"]))
            conn.commit()
    except sqlite3.IntegrityError:
        raise conn_rules.ConnectionConfigError(f"A connection named '{clean.get('name')}' already exists")
    return get_connection(clean.get("name", current["name"]))


def set_connection_models(name: str, models: List[str]) -> None:
    init_db()
    with closing(get_db_connection()) as conn:
        conn.execute("UPDATE connections SET models = ?, models_at = CURRENT_TIMESTAMP WHERE name = ?",
                     (json.dumps(conn_rules.clean_models(models)), name))
        conn.commit()


def delete_connection(name: str) -> bool:
    init_db()
    if not isinstance(name, str):
        return False
    with closing(get_db_connection()) as conn:
        cur = conn.execute("DELETE FROM connections WHERE name = ?", (name.strip().lower(),))
        conn.commit()
    return cur.rowcount > 0


def find_connection_for_model(model: Any) -> Optional[Tuple[Dict[str, Any], str]]:
    """(connection with its key, upstream model id) when `model` is `<enabled connection>/<model>`, else None."""
    if not isinstance(model, str) or "/" not in model:
        return None
    init_db()
    with closing(get_db_connection()) as conn:
        rows = conn.execute("SELECT * FROM connections WHERE enabled = 1").fetchall()
    names = [r["name"] for r in rows]
    hit = conn_rules.split_model(model, names)
    if not hit:
        return None
    row = next(r for r in rows if r["name"] == hit[0])
    return _connection_row(row, with_key=True), hit[1]


# ==============================================================================
# Test bench (see bench.py): custom scenarios and finished runs
# ==============================================================================

BENCH_RUNS_KEEP = 30


def _scenario_row(row: sqlite3.Row) -> Dict[str, Any]:
    try:
        data = json.loads(row["data"] or "{}")
    except ValueError:
        data = {}
    return {**data, "db_id": row["id"], "id": f"custom-{row['id']}", "builtin": False}


def list_bench_scenarios() -> List[Dict[str, Any]]:
    init_db()
    with closing(get_db_connection()) as conn:
        rows = conn.execute("SELECT * FROM bench_scenarios ORDER BY id").fetchall()
    return [_scenario_row(r) for r in rows]


def create_bench_scenario(data: Any) -> Dict[str, Any]:
    init_db()
    clean = bench.clean_scenario(data)
    with closing(get_db_connection()) as conn:
        if conn.execute("SELECT COUNT(*) FROM bench_scenarios").fetchone()[0] >= bench.MAX_SCENARIOS:
            raise bench.BenchError(f"You can keep at most {bench.MAX_SCENARIOS} custom tests")
        cur = conn.execute("INSERT INTO bench_scenarios (name, data) VALUES (?, ?)", (clean["name"], json.dumps(clean, ensure_ascii=False)))
        conn.commit()
        new_id = cur.lastrowid
    return get_bench_scenario(new_id)


def get_bench_scenario(scenario_id: int) -> Optional[Dict[str, Any]]:
    init_db()
    with closing(get_db_connection()) as conn:
        row = conn.execute("SELECT * FROM bench_scenarios WHERE id = ?", (scenario_id,)).fetchone()
    return _scenario_row(row) if row else None


def update_bench_scenario(scenario_id: int, data: Any) -> Optional[Dict[str, Any]]:
    if not get_bench_scenario(scenario_id):
        return None
    clean = bench.clean_scenario(data)
    with closing(get_db_connection()) as conn:
        conn.execute("UPDATE bench_scenarios SET name = ?, data = ? WHERE id = ?", (clean["name"], json.dumps(clean, ensure_ascii=False), scenario_id))
        conn.commit()
    return get_bench_scenario(scenario_id)


def delete_bench_scenario(scenario_id: int) -> bool:
    init_db()
    with closing(get_db_connection()) as conn:
        cur = conn.execute("DELETE FROM bench_scenarios WHERE id = ?", (scenario_id,))
        conn.commit()
    return cur.rowcount > 0


def _bench_run_row(row: sqlite3.Row, full: bool = False) -> Dict[str, Any]:
    try:
        results = json.loads(row["results"] or "[]")
    except ValueError:
        results = []
    try:
        settings = json.loads(row["settings"] or "{}")
    except ValueError:
        settings = {}
    out = {
        "id": row["id"], "created_at": _iso_utc(row["created_at"]), "finished_at": _iso_utc(row["finished_at"]) if row["finished_at"] else None,
        "preset": row["preset"], "model": row["model"], "status": row["status"], "total": row["total"], "settings": settings,
        "summary": bench.summarize(results, row["total"]),
    }
    if full:
        out["results"] = results
    return out


def create_bench_run(preset: str, model: str, total: int, settings: Dict[str, Any]) -> int:
    init_db()
    with closing(get_db_connection()) as conn:
        cur = conn.execute("INSERT INTO bench_runs (preset, model, total, settings) VALUES (?, ?, ?, ?)", (preset, model, total, json.dumps(settings)))
        conn.commit()
        run_id = cur.lastrowid
        conn.execute("DELETE FROM bench_runs WHERE id NOT IN (SELECT id FROM bench_runs ORDER BY id DESC LIMIT ?)", (BENCH_RUNS_KEEP,))
        conn.commit()
    return run_id


def save_bench_run(run_id: int, results: List[Dict[str, Any]], status: Optional[str] = None) -> None:
    init_db()
    with closing(get_db_connection()) as conn:
        if status:
            conn.execute("UPDATE bench_runs SET results = ?, status = ?, finished_at = CURRENT_TIMESTAMP WHERE id = ?",
                         (json.dumps(results, ensure_ascii=False), status, run_id))
        else:
            conn.execute("UPDATE bench_runs SET results = ? WHERE id = ?", (json.dumps(results, ensure_ascii=False), run_id))
        conn.commit()


def get_bench_run(run_id: int) -> Optional[Dict[str, Any]]:
    init_db()
    with closing(get_db_connection()) as conn:
        row = conn.execute("SELECT * FROM bench_runs WHERE id = ?", (run_id,)).fetchone()
    return _bench_run_row(row, full=True) if row else None


def list_bench_runs(limit: int = 30) -> List[Dict[str, Any]]:
    init_db()
    with closing(get_db_connection()) as conn:
        rows = conn.execute("SELECT * FROM bench_runs ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit))),)).fetchall()
    return [_bench_run_row(r) for r in rows]


def delete_bench_run(run_id: int) -> bool:
    init_db()
    with closing(get_db_connection()) as conn:
        cur = conn.execute("DELETE FROM bench_runs WHERE id = ? AND status != 'running'", (run_id,))
        conn.commit()
    return cur.rowcount > 0


# ==============================================================================
# Request log (see requestlog.py: what a preset or tool request did, kept so a person can check it)
# ==============================================================================

REQUEST_LOG_KEEP_DEFAULT = 200
REQUEST_LOG_KEEP_RANGE = (10, 2000)


def request_log_settings() -> Dict[str, Any]:
    keep = REQUEST_LOG_KEEP_DEFAULT
    try:
        keep = int(get_setting("request_log_keep", str(REQUEST_LOG_KEEP_DEFAULT)) or REQUEST_LOG_KEEP_DEFAULT)
    except ValueError:
        pass
    lo, hi = REQUEST_LOG_KEEP_RANGE
    return {"enabled": (get_setting("request_log_enabled", "1") or "1") != "0", "keep": max(lo, min(hi, keep))}


def set_request_log_settings(enabled: Any = None, keep: Any = None) -> Dict[str, Any]:
    lo, hi = REQUEST_LOG_KEEP_RANGE
    if enabled is not None:
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be true or false")
        set_setting("request_log_enabled", "1" if enabled else "0")
    if keep is not None:
        if isinstance(keep, bool) or not isinstance(keep, int) or not lo <= keep <= hi:
            raise ValueError(f"keep must be a whole number from {lo} to {hi}")
        set_setting("request_log_keep", str(keep))
        _prune_request_logs(keep)
    return request_log_settings()


def _prune_request_logs(keep: int) -> None:
    with closing(get_db_connection()) as conn:
        conn.execute("DELETE FROM request_logs WHERE id NOT IN (SELECT id FROM request_logs ORDER BY id DESC LIMIT ?)", (keep,))
        conn.commit()


def add_request_log(record: Dict[str, Any]) -> int:
    """Store one finished request (a `requestlog.Trace.record()`). Returns its id."""
    init_db()
    with closing(get_db_connection()) as conn:
        cur = conn.execute(
            "INSERT INTO request_logs (requested_model, model, preset, provider, origin, stream, tools, searches, searches_ok,"
            " outcome, queries, ms, error, reply_chars, trace, tag) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (record["requested_model"], record["model"], record["preset"], record["provider"], record["origin"],
             int(record["stream"]), int(record["tools"]), record["searches"], record["searches_ok"], record["outcome"],
             json.dumps(record["queries"], ensure_ascii=False), record["ms"], record["error"], record["reply_chars"],
             json.dumps(record["trace"], ensure_ascii=False), record.get("tag", "")),
        )
        conn.commit()
        new_id = cur.lastrowid
    _prune_request_logs(request_log_settings()["keep"])
    return new_id


def _request_log_row(row: sqlite3.Row, with_trace: bool = False) -> Dict[str, Any]:
    try:
        queries = json.loads(row["queries"] or "[]")
    except ValueError:
        queries = []
    out = {
        "id": row["id"], "created_at": _iso_utc(row["created_at"]), "requested_model": row["requested_model"],
        "model": row["model"], "preset": row["preset"], "provider": row["provider"], "origin": row["origin"],
        "stream": bool(row["stream"]), "tools": bool(row["tools"]), "searches": row["searches"],
        "searches_ok": row["searches_ok"], "outcome": row["outcome"], "queries": queries if isinstance(queries, list) else [],
        "ms": row["ms"], "error": row["error"], "reply_chars": row["reply_chars"], "tag": row["tag"],
    }
    if with_trace:
        try:
            out["trace"] = json.loads(row["trace"] or "{}")
        except ValueError:
            out["trace"] = {}
    return out


def list_request_logs(limit: int = 50, only_tools: bool = False, outcome: str = "", tag: str = "") -> List[Dict[str, Any]]:
    init_db()
    limit = max(1, min(500, int(limit)))
    where, args = [], []
    if only_tools:
        where.append("tools = 1")
    if outcome:
        where.append("outcome = ?")
        args.append(outcome)
    if tag:
        where.append("tag = ?")
        args.append(tag)
    sql = ("SELECT id, created_at, requested_model, model, preset, provider, origin, stream, tools, searches, searches_ok,"
           " outcome, queries, ms, error, reply_chars, tag FROM request_logs"
           + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY id DESC LIMIT ?")
    with closing(get_db_connection()) as conn:
        rows = conn.execute(sql, (*args, limit)).fetchall()
    return [_request_log_row(r) for r in rows]


def get_request_log(log_id: int) -> Optional[Dict[str, Any]]:
    init_db()
    with closing(get_db_connection()) as conn:
        row = conn.execute("SELECT * FROM request_logs WHERE id = ?", (log_id,)).fetchone()
    return _request_log_row(row, with_trace=True) if row else None


def delete_request_log(log_id: int) -> bool:
    init_db()
    with closing(get_db_connection()) as conn:
        cur = conn.execute("DELETE FROM request_logs WHERE id = ?", (log_id,))
        conn.commit()
    return cur.rowcount > 0


def clear_request_logs() -> int:
    init_db()
    with closing(get_db_connection()) as conn:
        cur = conn.execute("DELETE FROM request_logs")
        conn.commit()
    return cur.rowcount


def delete_lorebook(name: str) -> bool:
    init_db()
    if not isinstance(name, str):
        return False
    name = name.strip().lower()
    with closing(get_db_connection()) as conn:
        cur = conn.execute("DELETE FROM lorebooks WHERE name = ?", (name,))
        conn.commit()
    if cur.rowcount > 0:
        _relink_lorebook(name, None)
    return cur.rowcount > 0


def _write_entries(lorebook_id: int, entries: List[Dict[str, Any]]) -> None:
    with closing(get_db_connection()) as conn:
        conn.execute("UPDATE lorebooks SET entries = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (json.dumps(entries), lorebook_id))
        conn.commit()


def add_lorebook_entry(name: str, entry: Any) -> Optional[Dict[str, Any]]:
    """Append an entry. Returns the stored entry, or None when the lorebook does not exist."""
    book = get_lorebook(name)
    if not book:
        return None
    entries = book["entries"]
    raw = dict(entry) if isinstance(entry, dict) else entry
    if isinstance(raw, dict) and not raw.get("id"):
        taken = {e.get("id") for e in entries}
        n = len(entries) + 1
        while f"e{n}" in taken:
            n += 1
        raw["id"] = f"e{n}"
    cleaned = lore.clean_entries(entries + [raw])
    _write_entries(book["id"], cleaned)
    return cleaned[-1]


def update_lorebook_entry(name: str, entry_id: str, changes: Any) -> Optional[Dict[str, Any]]:
    """Change fields of one entry. Returns the stored entry, or None when the lorebook or entry does not exist."""
    book = get_lorebook(name)
    if not book or not isinstance(changes, dict):
        if book is not None:
            raise lore.LoreError("The entry changes must be an object")
        return None
    entries = book["entries"]
    for i, e in enumerate(entries):
        if e.get("id") == entry_id:
            merged = {**e, **{k: v for k, v in changes.items() if k != "id"}}
            entries[i] = merged
            cleaned = lore.clean_entries(entries)
            _write_entries(book["id"], cleaned)
            return cleaned[i]
    return None


def delete_lorebook_entry(name: str, entry_id: str) -> bool:
    book = get_lorebook(name)
    if not book:
        return False
    kept = [e for e in book["entries"] if e.get("id") != entry_id]
    if len(kept) == len(book["entries"]):
        return False
    _write_entries(book["id"], kept)
    return True


# ==============================================================================
# S-Connect Card Vault & Proxy Intercept Storage
# ==============================================================================

def save_connect_card(card: Dict[str, Any]) -> None:
    """Insert or update a character card in the S-Connect vault."""
    bot_id = str(card.get("id") or card.get("bot_id") or "").strip()
    if not bot_id:
        return
    now = time.time()
    greetings = card.get("greetings") or []
    tags = card.get("tags") or []
    
    with closing(get_db_connection()) as conn:
        conn.execute("""
            INSERT INTO connect_cards (
                bot_id, name, avatar, creator_id, creator_name, creator_avatar,
                category, description, personality, scenario, first_message,
                greetings_json, tags_json, tokens, chats, messages,
                is_unmasked, definition_private, source, raw_payload_json,
                created_at, updated_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?
            )
            ON CONFLICT(bot_id) DO UPDATE SET
                name = excluded.name,
                avatar = excluded.avatar,
                creator_id = excluded.creator_id,
                creator_name = excluded.creator_name,
                creator_avatar = excluded.creator_avatar,
                category = excluded.category,
                description = CASE WHEN length(excluded.description) >= length(connect_cards.description) THEN excluded.description ELSE connect_cards.description END,
                personality = CASE WHEN length(excluded.personality) > 0 THEN excluded.personality ELSE connect_cards.personality END,
                scenario = CASE WHEN length(excluded.scenario) > 0 THEN excluded.scenario ELSE connect_cards.scenario END,
                first_message = CASE WHEN length(excluded.first_message) > 0 THEN excluded.first_message ELSE connect_cards.first_message END,
                greetings_json = excluded.greetings_json,
                tags_json = excluded.tags_json,
                tokens = excluded.tokens,
                chats = excluded.chats,
                messages = excluded.messages,
                is_unmasked = CASE WHEN excluded.is_unmasked = 1 THEN 1 ELSE connect_cards.is_unmasked END,
                definition_private = CASE WHEN excluded.is_unmasked = 1 THEN 0 ELSE excluded.definition_private END,
                raw_payload_json = excluded.raw_payload_json,
                updated_at = excluded.updated_at
        """, (
            bot_id,
            str(card.get("name") or "Character"),
            str(card.get("avatar") or ""),
            str(card.get("creator_id") or card.get("creatorId") or ""),
            str(card.get("creator_name") or card.get("creatorName") or "Creator"),
            str(card.get("creator_avatar") or card.get("creatorAvatar") or ""),
            str(card.get("category") or ""),
            str(card.get("description") or ""),
            str(card.get("personality") or ""),
            str(card.get("scenario") or ""),
            str(card.get("first_message") or card.get("firstMessage") or ""),
            json.dumps(greetings),
            json.dumps(tags),
            int(card.get("tokens") or 0),
            int(card.get("chats") or 0),
            int(card.get("messages") or 0),
            1 if (card.get("is_unmasked") or card.get("isUnmasked") or (card.get("personality") and len(str(card.get("personality")).strip()) > 0 and not card.get("definition_private") and not card.get("definitionPrivate"))) else 0,
            1 if (card.get("definition_private") or card.get("definitionPrivate")) and not (card.get("is_unmasked") or card.get("isUnmasked")) else 0,
            str(card.get("source") or "janitorai"),
            json.dumps(card),
            float(card.get("created_at")) if isinstance(card.get("created_at"), (int, float)) else now,
            now
        ))
        conn.commit()


def get_connect_card(bot_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a single character card from SQLite vault."""
    clean_id = str(bot_id or "").strip()
    if not clean_id:
        return None
    with closing(get_db_connection()) as conn:
        row = conn.execute("SELECT * FROM connect_cards WHERE bot_id = ?", (clean_id,)).fetchone()
        if not row:
            return None
        return _format_connect_card_row(dict(row))


def list_connect_cards(
    q: str = "",
    unmasked_only: bool = False,
    limit: int = 60,
    sort: str = "trending",
    exclude_saved: bool = False
) -> List[Dict[str, Any]]:
    """List character cards matching search filters with proper popularity ordering."""
    query_parts = ["SELECT * FROM connect_cards WHERE 1=1"]
    params = []
    
    clean_q = str(q or "").strip().lower()
    if clean_q:
        query_parts.append("AND (lower(name) LIKE ? OR lower(creator_name) LIKE ? OR lower(description) LIKE ? OR lower(tags_json) LIKE ?)")
        wild = f"%{clean_q}%"
        params.extend([wild, wild, wild, wild])
    
    if unmasked_only:
        query_parts.append("AND is_unmasked = 1")

    if exclude_saved:
        query_parts.append("AND bot_id NOT IN (SELECT bot_id FROM connect_saved_cards)")
    
    clean_sort = str(sort or "trending").strip().lower()
    if clean_sort in ("trending", "popular", "chats"):
        query_parts.append("ORDER BY chats DESC, messages DESC LIMIT ?")
    elif clean_sort == "latest":
        query_parts.append("ORDER BY created_at DESC, updated_at DESC LIMIT ?")
    else:
        query_parts.append("ORDER BY updated_at DESC LIMIT ?")
        
    params.append(limit)
    
    with closing(get_db_connection()) as conn:
        rows = conn.execute(" ".join(query_parts), tuple(params)).fetchall()
        return [_format_connect_card_row(dict(r)) for r in rows]


def get_connect_cards_by_creators(creator_ids: List[str], limit: int = 60) -> List[Dict[str, Any]]:
    """Retrieve character cards authored by a list of creator IDs."""
    if not creator_ids:
        return []
    clean_ids = [str(c).strip() for c in creator_ids if str(c).strip()]
    if not clean_ids:
        return []
    placeholders = ",".join(["?"] * len(clean_ids))
    with closing(get_db_connection()) as conn:
        rows = conn.execute(
            f"SELECT * FROM connect_cards WHERE creator_id IN ({placeholders}) ORDER BY created_at DESC, updated_at DESC LIMIT ?",
            (*clean_ids, limit)
        ).fetchall()
        return [_format_connect_card_row(dict(r)) for r in rows]


def delete_connect_card(bot_id: str) -> bool:
    """Delete a stored card from vault."""
    clean_id = str(bot_id or "").strip()
    if not clean_id:
        return False
    with closing(get_db_connection()) as conn:
        cur = conn.execute("DELETE FROM connect_cards WHERE bot_id = ?", (clean_id,))
        conn.execute("DELETE FROM connect_saved_cards WHERE bot_id = ?", (clean_id,))
        conn.commit()
        return cur.rowcount > 0


def save_connect_bookmark(bot_id: str, card: Optional[Dict[str, Any]] = None) -> None:
    """Explicitly save/bookmark a character card in the user's library."""
    clean_id = str(bot_id or "").strip()
    if not clean_id:
        return
    if card:
        save_connect_card(card)
    now = time.time()
    with closing(get_db_connection()) as conn:
        conn.execute("""
            INSERT INTO connect_saved_cards (bot_id, saved_at)
            VALUES (?, ?)
            ON CONFLICT(bot_id) DO UPDATE SET saved_at = excluded.saved_at
        """, (clean_id, now))
        conn.commit()


def delete_connect_bookmark(bot_id: str) -> bool:
    """Remove a character bookmark from the user's library."""
    clean_id = str(bot_id or "").strip()
    if not clean_id:
        return False
    with closing(get_db_connection()) as conn:
        cur = conn.execute("DELETE FROM connect_saved_cards WHERE bot_id = ?", (clean_id,))
        conn.commit()
        return cur.rowcount > 0


def list_saved_connect_cards(q: str = "", limit: int = 60) -> List[Dict[str, Any]]:
    """List character cards explicitly saved by the user, ordered newly saved to oldest saved."""
    query_parts = [
        "SELECT c.*, s.saved_at FROM connect_saved_cards s",
        "JOIN connect_cards c ON s.bot_id = c.bot_id",
        "WHERE 1=1"
    ]
    params = []
    
    clean_q = str(q or "").strip().lower()
    if clean_q:
        query_parts.append("AND (lower(c.name) LIKE ? OR lower(c.creator_name) LIKE ? OR lower(c.description) LIKE ? OR lower(c.tags_json) LIKE ?)")
        wild = f"%{clean_q}%"
        params.extend([wild, wild, wild, wild])
    
    query_parts.append("ORDER BY s.saved_at DESC LIMIT ?")
    params.append(limit)
    
    with closing(get_db_connection()) as conn:
        rows = conn.execute(" ".join(query_parts), tuple(params)).fetchall()
        return [_format_connect_card_row(dict(r)) for r in rows]



def _format_connect_card_row(r: Dict[str, Any]) -> Dict[str, Any]:
    try:
        greetings = json.loads(r.get("greetings_json") or "[]")
    except Exception:
        greetings = []
    try:
        tags = json.loads(r.get("tags_json") or "[]")
    except Exception:
        tags = []
    
    return {
        "id": r["bot_id"],
        "name": r["name"],
        "avatar": r["avatar"],
        "creator_id": r["creator_id"],
        "creator_name": r["creator_name"],
        "creator_avatar": r["creator_avatar"],
        "category": r["category"],
        "description": r["description"],
        "personality": r["personality"],
        "scenario": r["scenario"],
        "first_message": r["first_message"],
        "firstMessage": r["first_message"],
        "greetings": greetings,
        "tags": tags,
        "tokens": r["tokens"],
        "chats": r["chats"],
        "messages": r["messages"],
        "is_unmasked": bool(r["is_unmasked"]),
        "isUnmasked": bool(r["is_unmasked"]),
        "definition_private": bool(r["definition_private"]),
        "definitionPrivate": bool(r["definition_private"]),
        "source": r["source"],
        "created_at": r["created_at"],
        "updated_at": r["updated_at"]
    }


def save_creator_profile(creator: Dict[str, Any]) -> None:
    """Insert or update a creator profile in the S-Connect vault."""
    if not creator or not isinstance(creator, dict):
        return
    cid = str(creator.get("id") or creator.get("creator_id") or "").strip()
    if not cid:
        return
    username = str(creator.get("username") or creator.get("user_name") or creator.get("displayName") or creator.get("name") or "").strip()
    display_name = str(creator.get("displayName") or creator.get("display_name") or creator.get("user_name") or creator.get("username") or creator.get("name") or "").strip()
    avatar_url = str(creator.get("avatar") or creator.get("avatar_url") or creator.get("creator_avatar") or "").strip()
    if "/bot-avatars/" in avatar_url:
        avatar_url = avatar_url.replace("/bot-avatars/", "/avatars/")
    bio = str(creator.get("bio") or creator.get("about_me") or "").strip()
    try:
        followers = int(creator.get("followers") or creator.get("followers_count") or 0)
    except Exception:
        followers = 0
    try:
        total_bots = int(creator.get("totalBots") or creator.get("total_bots") or len(creator.get("bots") or []) or 0)
    except Exception:
        total_bots = 0

    badges = creator.get("badges") or []
    style = creator.get("style") or {}
    now = time.time()

    with closing(get_db_connection()) as conn:
        conn.execute("""
            INSERT INTO connect_creators (
                creator_id, username, display_name, avatar_url, bio,
                followers, total_bots, badges_json, style_json,
                raw_payload_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(creator_id) DO UPDATE SET
                username = CASE WHEN length(excluded.username) > 0 AND excluded.username != excluded.creator_id THEN excluded.username ELSE connect_creators.username END,
                display_name = CASE WHEN length(excluded.display_name) > 0 AND excluded.display_name != excluded.creator_id THEN excluded.display_name ELSE connect_creators.display_name END,
                avatar_url = CASE WHEN length(excluded.avatar_url) > 0 THEN excluded.avatar_url ELSE connect_creators.avatar_url END,
                bio = CASE 
                    WHEN (excluded.bio LIKE 'Creator of %' OR excluded.bio LIKE 'JanitorAI author of %' OR length(excluded.bio) = 0) AND length(connect_creators.bio) > 0 AND connect_creators.bio NOT LIKE 'Creator of %' AND connect_creators.bio NOT LIKE 'JanitorAI author of %' THEN connect_creators.bio
                    WHEN length(excluded.bio) > 0 THEN excluded.bio 
                    ELSE connect_creators.bio 
                END,
                followers = CASE WHEN excluded.followers > 0 THEN excluded.followers ELSE connect_creators.followers END,
                total_bots = CASE WHEN excluded.total_bots > 0 THEN excluded.total_bots ELSE connect_creators.total_bots END,
                badges_json = CASE WHEN length(excluded.badges_json) > 2 THEN excluded.badges_json ELSE connect_creators.badges_json END,
                style_json = CASE WHEN length(excluded.style_json) > 2 THEN excluded.style_json ELSE connect_creators.style_json END,
                raw_payload_json = CASE WHEN length(excluded.raw_payload_json) > 2 THEN excluded.raw_payload_json ELSE connect_creators.raw_payload_json END,
                updated_at = excluded.updated_at
        """, (
            cid,
            username or cid,
            display_name or cid,
            avatar_url,
            bio,
            followers,
            total_bots,
            json.dumps(badges) if isinstance(badges, list) else "[]",
            json.dumps(style) if isinstance(style, dict) else "{}",
            json.dumps(creator),
            now
        ))
        conn.commit()


def get_creator_profile(creator_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve creator profile from vault, or synthesize from authored cards if available."""
    cid = str(creator_id or "").strip()
    if not cid:
        return None
    with closing(get_db_connection()) as conn:
        r = conn.execute("SELECT * FROM connect_creators WHERE creator_id = ?", (cid,)).fetchone()
        if r:
            row = dict(r)
            badges = []
            try:
                badges = json.loads(row.get("badges_json") or "[]")
            except Exception:
                pass
            style = {}
            try:
                style = json.loads(row.get("style_json") or "{}")
            except Exception:
                pass
            av = str(row["avatar_url"] or "")
            if "/bot-avatars/" in av:
                av = av.replace("/bot-avatars/", "/avatars/")
            return {
                "id": row["creator_id"],
                "username": row["username"] or cid,
                "displayName": row["display_name"] or row["username"] or cid,
                "avatar": av,
                "bio": row["bio"],
                "followers": row["followers"],
                "totalBots": row["total_bots"],
                "badges": badges,
                "style": style,
                "raw_payload_json": row.get("raw_payload_json") or "{}",
                "updated_at": row["updated_at"]
            }

        # Fallback: synthesize in-memory from connect_cards without polluting vault
        card_row = conn.execute("""
            SELECT creator_name, creator_avatar, count(*) as bot_cnt 
            FROM connect_cards 
            WHERE creator_id = ? 
            GROUP BY creator_id
        """, (cid,)).fetchone()
        if card_row and (card_row["creator_name"] or card_row["creator_avatar"]):
            syn_av = str(card_row["creator_avatar"] or "")
            if "/bot-avatars/" in syn_av:
                syn_av = syn_av.replace("/bot-avatars/", "/avatars/")
            return {
                "id": cid,
                "username": card_row["creator_name"] or cid,
                "displayName": card_row["creator_name"] or cid,
                "avatar": syn_av,
                "bio": f"JanitorAI creator with {card_row['bot_cnt']} authored cards",
                "followers": 0,
                "totalBots": card_row["bot_cnt"],
                "badges": [],
                "style": {},
                "updated_at": time.time()
            }
    return None


def get_creator_profiles_batch(creator_ids: List[str]) -> List[Dict[str, Any]]:
    """Batch fetch creator profiles."""
    results = []
    seen = set()
    for cid in creator_ids:
        clean = str(cid or "").strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        p = get_creator_profile(clean)
        if p:
            results.append(p)
    return results


def save_connect_intercept(intercept: Dict[str, Any]) -> int:
    """Save an intercepted system prompt / character persona capture."""
    now = time.time()
    with closing(get_db_connection()) as conn:
        cur = conn.execute("""
            INSERT INTO connect_intercepts (
                bot_id, bot_name, model, system_prompt, user_prompt,
                detected_persona, intercepted_at, raw_body_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(intercept.get("bot_id") or ""),
            str(intercept.get("bot_name") or "Captured Character"),
            str(intercept.get("model") or "s-connect-proxy"),
            str(intercept.get("system_prompt") or ""),
            str(intercept.get("user_prompt") or ""),
            str(intercept.get("detected_persona") or ""),
            float(intercept.get("intercepted_at") or now),
            json.dumps(intercept.get("raw_body") or {})
        ))
        conn.commit()
        return cur.lastrowid or 0


def get_latest_connect_intercept() -> Optional[Dict[str, Any]]:
    """Return the most recent intercepted character prompt."""
    with closing(get_db_connection()) as conn:
        row = conn.execute("SELECT * FROM connect_intercepts ORDER BY id DESC LIMIT 1").fetchone()
        if not row:
            return None
        return dict(row)


def list_connect_intercepts(limit: int = 30) -> List[Dict[str, Any]]:
    """Return recent intercepted prompts for live inspection."""
    with closing(get_db_connection()) as conn:
        rows = conn.execute("SELECT * FROM connect_intercepts ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]


def clear_connect_intercepts() -> None:
    """Clear captured intercepts log."""
    with closing(get_db_connection()) as conn:
        conn.execute("DELETE FROM connect_intercepts")
        conn.commit()


# ==============================================================================
# S-Connect Chat Sessions & Cross-Device Cloud Sync
# ==============================================================================

def save_connect_session(session: Dict[str, Any]) -> None:
    """Insert or update an S-Connect chat session in SQLite."""
    session_id = str(session.get("id") or session.get("session_id") or "").strip()
    if not session_id:
        return
    bot_id = str(session.get("botId") or session.get("bot_id") or "").strip()
    bot_name = str(session.get("botName") or session.get("bot_name") or "")
    bot_avatar = str(session.get("botAvatar") or session.get("bot_avatar") or "")
    bot_desc = str(session.get("botDescription") or session.get("bot_description") or "")
    created_at = float(session.get("createdAt") or session.get("created_at") or time.time() * 1000)
    updated_at = float(session.get("updatedAt") or session.get("updated_at") or time.time() * 1000)
    summary = str(session.get("summary") or "no summary :(")
    msg_count = int(session.get("messageCount") or session.get("message_count") or 0)
    greeting_idx = int(session.get("greetingIdx") or session.get("greeting_idx") or 0)
    persona_id = str(session.get("personaId") or session.get("persona_id") or "")
    persona_name = str(session.get("personaName") or session.get("persona_name") or "")
    persona_avatar = str(session.get("personaAvatar") or session.get("persona_avatar") or "")
    is_pub = 1 if session.get("isPublished") or session.get("is_published") else 0

    msgs = session.get("messages")
    msgs_json = json.dumps(msgs) if isinstance(msgs, list) else str(session.get("messages_json") or "[]")

    settings = session.get("settings")
    settings_json = json.dumps(settings) if isinstance(settings, dict) else str(session.get("settings_json") or "{}")

    with closing(get_db_connection()) as conn:
        conn.execute("""
            INSERT INTO connect_chat_sessions (
                session_id, bot_id, bot_name, bot_avatar, bot_description,
                created_at, updated_at, summary, message_count, greeting_idx,
                persona_id, persona_name, persona_avatar, is_published,
                messages_json, settings_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                bot_id = excluded.bot_id,
                bot_name = excluded.bot_name,
                bot_avatar = excluded.bot_avatar,
                bot_description = excluded.bot_description,
                updated_at = excluded.updated_at,
                summary = excluded.summary,
                message_count = excluded.message_count,
                greeting_idx = excluded.greeting_idx,
                persona_id = excluded.persona_id,
                persona_name = excluded.persona_name,
                persona_avatar = excluded.persona_avatar,
                is_published = excluded.is_published,
                messages_json = CASE WHEN excluded.messages_json != '[]' THEN excluded.messages_json ELSE connect_chat_sessions.messages_json END,
                settings_json = CASE WHEN excluded.settings_json != '{}' THEN excluded.settings_json ELSE connect_chat_sessions.settings_json END
        """, (
            session_id, bot_id, bot_name, bot_avatar, bot_desc,
            created_at, updated_at, summary, msg_count, greeting_idx,
            persona_id, persona_name, persona_avatar, is_pub,
            msgs_json, settings_json
        ))
        conn.commit()


def get_connect_sessions(bot_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return all stored S-Connect chat sessions, optionally filtered by bot_id."""
    query = "SELECT * FROM connect_chat_sessions"
    params: List[Any] = []
    if bot_id:
        query += " WHERE bot_id = ?"
        params.append(str(bot_id).strip())
    query += " ORDER BY updated_at DESC"

    with closing(get_db_connection()) as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                msgs = json.loads(d.get("messages_json") or "[]")
            except Exception:
                msgs = []
            try:
                sett = json.loads(d.get("settings_json") or "{}")
            except Exception:
                sett = {}
            result.append({
                "id": d["session_id"],
                "session_id": d["session_id"],
                "botId": d["bot_id"],
                "botName": d["bot_name"],
                "botAvatar": d["bot_avatar"],
                "botDescription": d["bot_description"],
                "createdAt": d["created_at"],
                "updatedAt": d["updated_at"],
                "summary": d["summary"],
                "messageCount": d["message_count"],
                "greetingIdx": d["greeting_idx"],
                "personaId": d["persona_id"],
                "personaName": d["persona_name"],
                "personaAvatar": d["persona_avatar"],
                "isPublished": bool(d["is_published"]),
                "messages": msgs,
                "settings": sett
            })
        return result


def get_connect_session_by_id(session_id: str) -> Optional[Dict[str, Any]]:
    """Return single session by ID with its messages and settings."""
    clean_id = str(session_id or "").strip()
    if not clean_id:
        return None
    with closing(get_db_connection()) as conn:
        row = conn.execute("SELECT * FROM connect_chat_sessions WHERE session_id = ?", (clean_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            msgs = json.loads(d.get("messages_json") or "[]")
        except Exception:
            msgs = []
        try:
            sett = json.loads(d.get("settings_json") or "{}")
        except Exception:
            sett = {}
        return {
            "id": d["session_id"],
            "session_id": d["session_id"],
            "botId": d["bot_id"],
            "botName": d["bot_name"],
            "botAvatar": d["bot_avatar"],
            "botDescription": d["bot_description"],
            "createdAt": d["created_at"],
            "updatedAt": d["updated_at"],
            "summary": d["summary"],
            "messageCount": d["message_count"],
            "greetingIdx": d["greeting_idx"],
            "personaId": d["persona_id"],
            "personaName": d["persona_name"],
            "personaAvatar": d["persona_avatar"],
            "isPublished": bool(d["is_published"]),
            "messages": msgs,
            "settings": sett
        }


def delete_connect_session(session_id: str) -> bool:
    """Delete a chat session from SQLite."""
    clean_id = str(session_id or "").strip()
    if not clean_id:
        return False
    with closing(get_db_connection()) as conn:
        cur = conn.execute("DELETE FROM connect_chat_sessions WHERE session_id = ?", (clean_id,))
        conn.commit()
        return cur.rowcount > 0


def get_connect_vault_val(key: str, default: Any = None) -> Any:
    """Get a stored preference/vault value (e.g. personas, saved bots)."""
    with closing(get_db_connection()) as conn:
        row = conn.execute("SELECT value FROM connect_user_vault WHERE key = ?", (key,)).fetchone()
        if not row:
            return default
        try:
            return json.loads(row["value"])
        except Exception:
            return row["value"]


def set_connect_vault_val(key: str, value: Any) -> None:
    """Set a stored preference/vault value."""
    val_str = json.dumps(value) if not isinstance(value, str) else value
    with closing(get_db_connection()) as conn:
        conn.execute("""
            INSERT INTO connect_user_vault (key, value, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """, (key, val_str, time.time()))
        conn.commit()


def get_full_connect_sync_payload() -> Dict[str, Any]:
    """Assemble complete portable sync bundle of sessions, personas, and preferences."""
    sessions = get_connect_sessions()
    personas = get_connect_vault_val("personas", [])
    active_persona_id = get_connect_vault_val("active_persona_id", "persona_default")
    saved_bots = get_connect_vault_val("saved_bots", [])
    following = get_connect_vault_val("following", [])
    active_chats = get_connect_vault_val("active_chats", {})
    creator_profiles = get_creator_profiles_batch(following)

    return {
        "version": 2,
        "synced_at": time.time(),
        "sessions": sessions,
        "personas": personas,
        "active_persona_id": active_persona_id,
        "saved_bots": saved_bots,
        "following": following,
        "creator_profiles": creator_profiles,
        "active_chats": active_chats
    }


def merge_connect_sync_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Merge an incoming bundle with the local SQLite vault (newest updatedAt wins)."""
    incoming_sessions = payload.get("sessions") or []
    for s in incoming_sessions:
        if isinstance(s, dict) and (s.get("id") or s.get("session_id")):
            save_connect_session(s)

    if "personas" in payload and isinstance(payload["personas"], list) and payload["personas"]:
        local_personas = get_connect_vault_val("personas", [])
        p_map = {p.get("id"): p for p in local_personas if isinstance(p, dict) and p.get("id")}
        for p in payload["personas"]:
            if isinstance(p, dict) and p.get("id"):
                p_map[p["id"]] = p
        set_connect_vault_val("personas", list(p_map.values()))

    if "active_persona_id" in payload and payload["active_persona_id"]:
        set_connect_vault_val("active_persona_id", payload["active_persona_id"])

    if "saved_bots" in payload and isinstance(payload["saved_bots"], list):
        local_saved = set(get_connect_vault_val("saved_bots", []))
        local_saved.update(payload["saved_bots"])
        set_connect_vault_val("saved_bots", list(local_saved))

    if "following" in payload and isinstance(payload["following"], list):
        local_following = set(get_connect_vault_val("following", []))
        local_following.update(payload["following"])
        set_connect_vault_val("following", list(local_following))

    if "creator_profiles" in payload and isinstance(payload["creator_profiles"], list):
        for cp in payload["creator_profiles"]:
            if isinstance(cp, dict) and (cp.get("id") or cp.get("creator_id")):
                save_creator_profile(cp)

    if "active_chats" in payload and isinstance(payload["active_chats"], dict):
        local_active = get_connect_vault_val("active_chats", {})
        local_active.update(payload["active_chats"])
        set_connect_vault_val("active_chats", local_active)

    return get_full_connect_sync_payload()


# -----------------------------------------------------------------------------
# Custom Voices Vault (Google Gemini 3.8 Flash TTS Voice Design)
# -----------------------------------------------------------------------------

def save_custom_voice(
    voice_id: str,
    name: str,
    description: str = "",
    prompt: str = "",
    voice_type: str = "prompted",
    sample_audio: str = "",
) -> Dict[str, Any]:
    """Save or update a custom-designed voice persona."""
    init_db()
    now = time.time()
    with closing(get_db_connection()) as conn:
        conn.execute("""
            INSERT INTO custom_voices (voice_id, name, description, prompt, voice_type, sample_audio, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(voice_id) DO UPDATE SET
                name = excluded.name,
                description = excluded.description,
                prompt = excluded.prompt,
                voice_type = excluded.voice_type,
                sample_audio = CASE WHEN excluded.sample_audio != '' THEN excluded.sample_audio ELSE custom_voices.sample_audio END
        """, (voice_id, name, description, prompt, voice_type, sample_audio, now))
        conn.commit()
    return {
        "voice_id": voice_id,
        "name": name,
        "description": description,
        "prompt": prompt,
        "voice_type": voice_type,
        "sample_audio": sample_audio,
        "created_at": now,
    }


def get_custom_voices() -> List[Dict[str, Any]]:
    """Retrieve all saved custom-designed voice personas."""
    init_db()
    with closing(get_db_connection()) as conn:
        rows = conn.execute("""
            SELECT voice_id, name, description, prompt, voice_type, sample_audio, created_at
            FROM custom_voices
            ORDER BY created_at DESC
        """).fetchall()
    return [dict(r) for r in rows]


def get_custom_voice(voice_id: str) -> Optional[Dict[str, Any]]:
    """Get a single custom voice by voice_id."""
    init_db()
    with closing(get_db_connection()) as conn:
        row = conn.execute("""
            SELECT voice_id, name, description, prompt, voice_type, sample_audio, created_at
            FROM custom_voices WHERE voice_id = ?
        """, (voice_id,)).fetchone()
    return dict(row) if row else None


def delete_custom_voice(voice_id: str) -> bool:
    """Delete a custom voice persona from the vault."""
    init_db()
    with closing(get_db_connection()) as conn:
        cursor = conn.execute("DELETE FROM custom_voices WHERE voice_id = ?", (voice_id,))
        conn.commit()
        return cursor.rowcount > 0


