import base64, hashlib, hmac, logging, os, secrets, aiosqlite

from dotenv import load_dotenv
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "utils", "database.db")

load_dotenv()

_ENC_PREFIX = "enc:v1:"
_crypto_keys: Optional[tuple[bytes, bytes]] = None


def safe_int(value: Optional[str | int]) -> Optional[int]:
    if value is None:
        return None
    val_str = str(value).strip().lower()
    if val_str in ("none", "null", ""):
        return None
    try:
        return int(val_str)
    except ValueError:
        return None

def _get_keys() -> tuple[bytes, bytes]:
    global _crypto_keys
    if _crypto_keys is None:
        secret = os.getenv("BAN_REASON_KEY", "").strip()
        if len(secret) < 32:
            raise RuntimeError(
                "BAN_REASON_KEY is missing or too short (need 32+ characters) in .env. Generate one with:\n"
                "  python -c \"import secrets; print(secrets.token_urlsafe(48))\"\n"
                "Back it up somewhere that is NOT next to the database; without it, stored reasons "
                "can never be read again."
            )
        master = hashlib.sha256(secret.encode("utf-8")).digest()
        _crypto_keys = (
            hmac.new(master, b"osavs-enc", hashlib.sha256).digest(),
            hmac.new(master, b"osavs-mac", hashlib.sha256).digest(),
        )
    return _crypto_keys

def check_key() -> None:
    _get_keys()

def _keystream(enc_key: bytes, nonce: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        out += hmac.new(enc_key, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest()
        counter += 1
    return bytes(out[:length])

def encrypt_text(value: Optional[str]) -> Optional[str]:
    if value is None or value.startswith(_ENC_PREFIX):
        return value
    enc_key, mac_key = _get_keys()
    nonce = secrets.token_bytes(16)
    data = value.encode("utf-8")
    ct = bytes(a ^ b for a, b in zip(data, _keystream(enc_key, nonce, len(data))))
    tag = hmac.new(mac_key, nonce + ct, hashlib.sha256).digest()
    return _ENC_PREFIX + base64.urlsafe_b64encode(nonce + ct + tag).decode("ascii")

def decrypt_text(value: Optional[str]) -> Optional[str]:
    if value is None or not value.startswith(_ENC_PREFIX):
        return value
    enc_key, mac_key = _get_keys()
    try:
        raw = base64.urlsafe_b64decode(value[len(_ENC_PREFIX):].encode("ascii"))
        nonce, ct, tag = raw[:16], raw[16:-32], raw[-32:]
        if not hmac.compare_digest(tag, hmac.new(mac_key, nonce + ct, hashlib.sha256).digest()):
            raise ValueError("bad tag")
        return bytes(a ^ b for a, b in zip(ct, _keystream(enc_key, nonce, len(ct)))).decode("utf-8")
    except Exception:
        logging.error("[Crypto] Could not decrypt a stored reason (wrong BAN_REASON_KEY or corrupted data).")
        return "[unreadable: wrong key or corrupted]"

_settings_cache: dict[str, dict] = {}

async def _backfill_ban_groups(conn):
    async with conn.execute(
        "SELECT target_id, reason, moderator_id, timestamp FROM banned_users WHERE ban_group IS NULL"
    ) as cursor:
        rows = await cursor.fetchall()

    buckets: dict[tuple, list[str]] = {}
    for target_id, reason, moderator_id, timestamp in rows:
        buckets.setdefault((reason, moderator_id, timestamp), []).append(target_id)

    for members in buckets.values():
        discord_side = [t for t in members if t.isdigit()]
        vrchat_side = [t for t in members if not t.isdigit()]
        if len(discord_side) == 1 and len(vrchat_side) == 1:
            await conn.execute(
                "UPDATE banned_users SET ban_group = ? WHERE target_id IN (?, ?)",
                (secrets.token_hex(8), discord_side[0], vrchat_side[0]),
            )

async def _encrypt_existing_reasons(conn):
    for table, key_col in (("banned_users", "target_id"), ("banned_servers", "server_id")):
        async with conn.execute(f"SELECT {key_col}, reason FROM {table}") as cursor:
            rows = await cursor.fetchall()
        for key, reason in rows:
            enc = encrypt_text(reason)
            if enc != reason:
                await conn.execute(f"UPDATE {table} SET reason = ? WHERE {key_col} = ?", (enc, key))

async def init_db():
    check_key()
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA synchronous=NORMAL")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS server_settings (
                server_id TEXT PRIMARY KEY,
                verified_role TEXT NOT NULL,
                verify_channel TEXT NOT NULL,
                verification_logs TEXT NOT NULL,
                av_start_code TEXT DEFAULT 'AVS-',
                required_role TEXT,
                language TEXT DEFAULT 'en'
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS verified_users (
                discord_id TEXT PRIMARY KEY,
                vrchat_id TEXT UNIQUE
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS banned_users (
                target_id TEXT PRIMARY KEY,
                reason TEXT NOT NULL,
                moderator_id TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS banned_servers (
                server_id TEXT PRIMARY KEY,
                reason TEXT NOT NULL,
                moderator_id TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        async with conn.execute("PRAGMA table_info(banned_users)") as cursor:
            ban_columns = {row[1] for row in await cursor.fetchall()}
        if "ban_group" not in ban_columns:
            await conn.execute("ALTER TABLE banned_users ADD COLUMN ban_group TEXT")

        async with conn.execute("PRAGMA table_info(banned_servers)") as cursor:
            server_ban_columns = {row[1] for row in await cursor.fetchall()}
        if "evidence_thread_id" not in ban_columns:
            await conn.execute("ALTER TABLE banned_users ADD COLUMN evidence_thread_id TEXT")
        if "evidence_thread_id" not in server_ban_columns:
            await conn.execute("ALTER TABLE banned_servers ADD COLUMN evidence_thread_id TEXT")

        async with conn.execute("SELECT value FROM bot_state WHERE key = 'ban_groups_backfilled'") as cursor:
            backfilled = await cursor.fetchone()
        if not backfilled:
            await _backfill_ban_groups(conn)
            await conn.execute("INSERT OR REPLACE INTO bot_state (key, value) VALUES ('ban_groups_backfilled', '1')")

        async with conn.execute("SELECT value FROM bot_state WHERE key = 'ban_reasons_encrypted'") as cursor:
            reasons_done = await cursor.fetchone()
        if not reasons_done:
            await _encrypt_existing_reasons(conn)
            await conn.execute("INSERT OR REPLACE INTO bot_state (key, value) VALUES ('ban_reasons_encrypted', '1')")

        async with conn.execute("SELECT value FROM bot_state WHERE key = 'vrchat_ids_lowercased'") as cursor:
            migrated = await cursor.fetchone()
        if not migrated:
            await conn.execute(
                "UPDATE OR IGNORE verified_users SET vrchat_id = lower(vrchat_id) WHERE vrchat_id != lower(vrchat_id)"
            )
            await conn.execute("INSERT OR REPLACE INTO bot_state (key, value) VALUES ('vrchat_ids_lowercased', '1')")
        await conn.commit()

async def get_server_settings(guild_id: int | str) -> dict:
    cached = _settings_cache.get(str(guild_id))
    if cached is not None:
        return dict(cached)
    result = await _load_server_settings(guild_id)
    _settings_cache[str(guild_id)] = result
    return dict(result)

async def _load_server_settings(guild_id: int | str) -> dict:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT * FROM server_settings WHERE server_id = ?", (str(guild_id),)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                data = dict(row)
                return {
                    "server_id": safe_int(data["server_id"]),
                    "verified_role": safe_int(data["verified_role"]),
                    "verify_channel": safe_int(data["verify_channel"]),
                    "verification_logs": safe_int(data["verification_logs"]),
                    "av_start_code": data["av_start_code"] or "AVS-",
                    "required_role": safe_int(data["required_role"]),
                    "language": data.get("language") or "en"
                }
            return {
                "server_id": safe_int(guild_id),
                "verified_role": None,
                "verify_channel": None,
                "verification_logs": None,
                "av_start_code": "AVS-",
                "required_role": None,
                "language": "en"
            }

async def save_server_settings(
    guild_id: int | str, 
    verified_role: int | str,
    verify_channel: int | str, 
    verification_logs: int | str, 
    av_start_code: str,
    required_role: Optional[int | str] = None,
    language: str = "en"
):
    formatted_prefix = av_start_code.strip() if av_start_code else "AVS-"
    if formatted_prefix and not formatted_prefix.endswith("-"):
        formatted_prefix += "-"

    clean_guild_id = safe_int(guild_id)
    clean_verified_role = safe_int(verified_role)
    clean_verify_channel = safe_int(verify_channel)
    clean_verification_logs = safe_int(verification_logs)
    clean_required_role = safe_int(required_role)

    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("""
            INSERT OR REPLACE INTO server_settings (
                server_id, 
                verified_role, 
                verify_channel, 
                verification_logs, 
                av_start_code,
                required_role,
                language
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            str(clean_guild_id) if clean_guild_id is not None else str(guild_id), 
            str(clean_verified_role) if clean_verified_role is not None else str(verified_role), 
            str(clean_verify_channel) if clean_verify_channel is not None else str(verify_channel), 
            str(clean_verification_logs) if clean_verification_logs is not None else str(verification_logs), 
            formatted_prefix,
            str(clean_required_role) if clean_required_role is not None else None,
            language or "en"
        ))
        await conn.commit()
    _settings_cache.pop(str(guild_id), None)
    if clean_guild_id is not None:
        _settings_cache.pop(str(clean_guild_id), None)

async def delete_server_settings(guild_id: int | str) -> bool:
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute(
            "DELETE FROM server_settings WHERE server_id = ?", (str(guild_id),)
        ) as cursor:
            await conn.commit()
            _settings_cache.pop(str(guild_id), None)
            return cursor.rowcount > 0

async def get_vrchat_id_from_discord(discord_id: int | str) -> Optional[str]:
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute(
            "SELECT vrchat_id FROM verified_users WHERE discord_id = ?", (str(discord_id),)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

async def is_vrchat_id_verified(vrchat_id: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute(
            "SELECT 1 FROM verified_users WHERE vrchat_id = ?", (vrchat_id.strip().lower(),)
        ) as cursor:
            row = await cursor.fetchone()
            return row is not None

async def get_discord_id_from_vrchat(vrchat_id: str) -> Optional[int]:
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute(
            "SELECT discord_id FROM verified_users WHERE vrchat_id = ?", (vrchat_id.strip().lower(),)
        ) as cursor:
            row = await cursor.fetchone()
            return safe_int(row[0]) if row else None

async def get_verified_among(ids: list[int | str]) -> dict[int, str]:
    out: dict[int, str] = {}
    if not ids:
        return out
    async with aiosqlite.connect(DB_PATH) as conn:
        for i in range(0, len(ids), 500):
            chunk = [str(x) for x in ids[i:i + 500]]
            marks = ",".join("?" * len(chunk))
            async with conn.execute(
                f"SELECT discord_id, vrchat_id FROM verified_users WHERE discord_id IN ({marks})", chunk
            ) as cursor:
                for d, v in await cursor.fetchall():
                    parsed = safe_int(d)
                    if parsed is not None:
                        out[parsed] = v
    return out

async def get_verified_users_page(limit: int = 100, offset: int = 0) -> tuple[list[tuple[int, str]], int]:
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute(
            "SELECT discord_id, vrchat_id FROM verified_users ORDER BY rowid LIMIT ? OFFSET ?", (limit, offset)
        ) as cursor:
            rows = await cursor.fetchall()
        async with conn.execute("SELECT COUNT(*) FROM verified_users") as cursor:
            total = (await cursor.fetchone())[0]
    results = []
    for d, v in rows:
        parsed = safe_int(d)
        if parsed is not None:
            results.append((parsed, v))
    return results, total

async def get_verified_users_after(after: int = 0, limit: int = 100) -> tuple[list[tuple[int, str]], int, Optional[int]]:
    limit = max(1, min(int(limit), 500))
    after = max(0, int(after))
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute(
            "SELECT rowid, discord_id, vrchat_id FROM verified_users WHERE rowid > ? ORDER BY rowid LIMIT ?",
            (after, limit),
        ) as cursor:
            rows = await cursor.fetchall()
        async with conn.execute("SELECT COUNT(*) FROM verified_users") as cursor:
            total = (await cursor.fetchone())[0]
    results = []
    for _, d, v in rows:
        parsed = safe_int(d)
        if parsed is not None:
            results.append((parsed, v))
    next_after = rows[-1][0] if len(rows) == limit else None
    return results, total, next_after

async def get_all_verified_users() -> list[tuple[int, str]]:
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute("SELECT discord_id, vrchat_id FROM verified_users") as cursor:
            rows = await cursor.fetchall()
            results = []
            for row in rows:
                parsed_id = safe_int(row[0])
                if parsed_id is not None:
                    results.append((parsed_id, row[1]))
            return results

async def add_verified_user(discord_id: int | str, vrchat_id: str, overwrite: bool = False) -> bool:
    clean_id = safe_int(discord_id)
    target_id = str(clean_id) if clean_id is not None else str(discord_id)
    vrc = vrchat_id.strip().lower()

    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("BEGIN IMMEDIATE")
        async with conn.execute(
            "SELECT discord_id, vrchat_id FROM verified_users WHERE discord_id = ? OR vrchat_id = ?",
            (target_id, vrc)
        ) as cursor:
            existing = await cursor.fetchall()
        if existing and all(d == target_id and v == vrc for d, v in existing):
            await conn.rollback()
            return True
        if existing and not overwrite:
            await conn.rollback()
            return False
        if existing:
            await conn.execute(
                "DELETE FROM verified_users WHERE discord_id = ? OR vrchat_id = ?", (target_id, vrc)
            )
        await conn.execute(
            "INSERT INTO verified_users (discord_id, vrchat_id) VALUES (?, ?)", (target_id, vrc)
        )
        await conn.commit()
        return True

async def remove_verified_user(discord_id: int | str) -> bool:
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute(
            "DELETE FROM verified_users WHERE discord_id = ?", (str(discord_id),)
        ) as cursor:
            await conn.commit()
            return cursor.rowcount > 0

async def get_total_verified_users(exclude_ids: Optional[list[int | str]] = None) -> int:
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute("SELECT COUNT(*) FROM verified_users") as cursor:
            row = await cursor.fetchone()
            total = row[0] if row else 0
        if exclude_ids:
            marks = ",".join("?" for _ in exclude_ids)
            async with conn.execute(
                f"SELECT COUNT(*) FROM verified_users WHERE discord_id IN ({marks})",
                tuple(str(x) for x in exclude_ids)
            ) as cursor:
                row = await cursor.fetchone()
                total -= row[0] if row else 0
        return total

async def is_banned(target_id: int | str) -> bool:
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute(
            "SELECT 1 FROM banned_users WHERE target_id = ?", (str(target_id).strip(),)
        ) as cursor:
            row = await cursor.fetchone()
            return row is not None

async def get_banned_user(target_id: int | str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT * FROM banned_users WHERE target_id = ?", (str(target_id).strip(),)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                data = dict(row)
                raw_target = data["target_id"]
                return {
                    "target_id": safe_int(raw_target) if raw_target.isdigit() else raw_target,
                    "reason": decrypt_text(data["reason"]),
                    "moderator_id": safe_int(data["moderator_id"]),
                    "timestamp": data["timestamp"]
                }
            return None

async def add_banned_user(target_id: int | str, reason: str, moderator_id: int | str, ban_group: Optional[str] = None):
    clean_mod = safe_int(moderator_id)
    
    target_key = str(target_id).strip()
    target_mod = str(clean_mod) if clean_mod is not None else str(moderator_id)

    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "INSERT OR REPLACE INTO banned_users (target_id, reason, moderator_id, ban_group) VALUES (?, ?, ?, ?)",
            (target_key, encrypt_text(reason), target_mod, ban_group)
        )
        await conn.commit()

async def set_ban_thread_id(target_ids: list, thread_id: int | str) -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        for t in target_ids:
            await conn.execute(
                "UPDATE banned_users SET evidence_thread_id = ? WHERE target_id = ?",
                (str(thread_id), str(t).strip()),
            )
        await conn.commit()

async def get_ban_thread_id(target_id: int | str) -> Optional[str]:
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute(
            "SELECT evidence_thread_id FROM banned_users WHERE target_id = ?", (str(target_id).strip(),)
        ) as cursor:
            row = await cursor.fetchone()
    return row[0] if row and row[0] else None

async def set_server_ban_thread_id(server_id: int | str, thread_id: int | str) -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE banned_servers SET evidence_thread_id = ? WHERE server_id = ?",
            (str(thread_id), str(server_id).strip()),
        )
        await conn.commit()

async def get_server_ban_thread_id(server_id: int | str) -> Optional[str]:
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute(
            "SELECT evidence_thread_id FROM banned_servers WHERE server_id = ?", (str(server_id).strip(),)
        ) as cursor:
            row = await cursor.fetchone()
    return row[0] if row and row[0] else None

async def remove_banned_user(target_id: int | str) -> bool:
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute(
            "DELETE FROM banned_users WHERE target_id = ?", (str(target_id).strip(),)
        ) as cursor:
            await conn.commit()
            return cursor.rowcount > 0

async def remove_banned_user_and_group(target_id: int | str) -> list[str]:
    key = str(target_id).strip()
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("BEGIN IMMEDIATE")
        async with conn.execute("SELECT ban_group FROM banned_users WHERE target_id = ?", (key,)) as cursor:
            row = await cursor.fetchone()
        if not row:
            await conn.rollback()
            return []
        group = row[0]
        if group:
            async with conn.execute("SELECT target_id FROM banned_users WHERE ban_group = ?", (group,)) as cursor:
                removed = [r[0] for r in await cursor.fetchall()]
            await conn.execute("DELETE FROM banned_users WHERE ban_group = ?", (group,))
        else:
            removed = [key]
            await conn.execute("DELETE FROM banned_users WHERE target_id = ?", (key,))
        await conn.commit()
        return removed

async def is_server_banned(server_id: int | str) -> bool:
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute(
            "SELECT 1 FROM banned_servers WHERE server_id = ?", (str(server_id).strip(),)
        ) as cursor:
            row = await cursor.fetchone()
            return row is not None

async def add_banned_server(server_id: int | str, reason: str, moderator_id: Optional[int | str] = None):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "INSERT OR REPLACE INTO banned_servers (server_id, reason, moderator_id) VALUES (?, ?, ?)",
            (str(server_id).strip(), encrypt_text(reason), str(moderator_id) if moderator_id is not None else None)
        )
        await conn.commit()

async def remove_banned_server(server_id: int | str) -> bool:
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute(
            "DELETE FROM banned_servers WHERE server_id = ?", (str(server_id).strip(),)
        ) as cursor:
            await conn.commit()
            return cursor.rowcount > 0

async def get_all_banned_users() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT target_id, reason, moderator_id, timestamp FROM banned_users ORDER BY timestamp DESC"
        ) as cursor:
            rows = await cursor.fetchall()
    out = [dict(r) for r in rows]
    for r in out:
        r["reason"] = decrypt_text(r["reason"])
    return out

async def get_all_banned_servers() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT server_id, reason, moderator_id, timestamp FROM banned_servers ORDER BY timestamp DESC"
        ) as cursor:
            rows = await cursor.fetchall()
    out = [dict(r) for r in rows]
    for r in out:
        r["reason"] = decrypt_text(r["reason"])
    return out

async def get_maintenance_mode() -> bool:
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute(
            "SELECT value FROM bot_state WHERE key = 'maintenance_mode'"
        ) as cursor:
            row = await cursor.fetchone()
            return bool(row and row[0] == "1")

async def set_maintenance_mode(enabled: bool):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "INSERT OR REPLACE INTO bot_state (key, value) VALUES ('maintenance_mode', ?)",
            ("1" if enabled else "0",),
        )
        await conn.commit()
