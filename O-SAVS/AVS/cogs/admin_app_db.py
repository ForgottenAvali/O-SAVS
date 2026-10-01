import asyncio, aiosqlite, hashlib, hmac, os, secrets

from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), "admin_app.db")


async def init_db():
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS admin_accounts (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                discord_id TEXT
            )
            """)
        async with conn.execute("PRAGMA table_info(admin_accounts)") as cursor:
            existing_columns = {row[1] for row in await cursor.fetchall()}
        if "auth_code_hash" not in existing_columns:
            await conn.execute("ALTER TABLE admin_accounts ADD COLUMN auth_code_hash TEXT")
        if "auth_code_salt" not in existing_columns:
            await conn.execute("ALTER TABLE admin_accounts ADD COLUMN auth_code_salt TEXT")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS action_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                actor_username TEXT NOT NULL,
                action TEXT NOT NULL,
                target TEXT,
                reason TEXT,
                result_summary TEXT
            )
        """)
        await conn.commit()

def _hash_password_sync(password: str, salt_hex: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 200_000).hex()

async def _hash_password(password: str, salt_hex: str) -> str:
    return await asyncio.to_thread(_hash_password_sync, password, salt_hex)

async def create_account(username: str, password: str, discord_id: int = None, auth_code: str = None):
    salt = secrets.token_hex(16)
    pw_hash = await _hash_password(password, salt)
    discord_id_str = str(discord_id) if discord_id is not None else None

    code_hash = code_salt = None
    if auth_code:
        code_salt = secrets.token_hex(16)
        code_hash = await _hash_password(auth_code, code_salt)

    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """INSERT INTO admin_accounts
               (username, password_hash, salt, discord_id, auth_code_hash, auth_code_salt)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (username, pw_hash, salt, discord_id_str, code_hash, code_salt),
        )
        await conn.commit()

async def account_exists(username: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute(
            "SELECT 1 FROM admin_accounts WHERE username = ?", (username,)
        ) as cursor:
            return await cursor.fetchone() is not None

async def set_auth_code(username: str, auth_code: str) -> bool:
    """Sets or replaces an existing account's authorization code. Returns False if no such account."""
    salt = secrets.token_hex(16)
    code_hash = await _hash_password(auth_code, salt)
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            "UPDATE admin_accounts SET auth_code_hash = ?, auth_code_salt = ? WHERE username = ?",
            (code_hash, salt, username),
        )
        await conn.commit()
        return cursor.rowcount > 0

async def has_auth_code(username: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute(
            "SELECT auth_code_hash FROM admin_accounts WHERE username = ?", (username,)
        ) as cursor:
            row = await cursor.fetchone()
            return bool(row and row[0])

async def verify_auth_code(username: str, auth_code: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute(
            "SELECT auth_code_hash, auth_code_salt FROM admin_accounts WHERE username = ?", (username,)
        ) as cursor:
            row = await cursor.fetchone()

    if not row or not row[0] or not row[1]:
        return False
    candidate = await _hash_password(auth_code, row[1])
    return hmac.compare_digest(candidate, row[0])

async def verify_login(username: str, password: str):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT * FROM admin_accounts WHERE username = ?", (username,)
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            return None
        if await _hash_password(password, row["salt"]) != row["password_hash"]:
            return None

        raw_discord_id = row["discord_id"]
        discord_id = int(raw_discord_id) if raw_discord_id is not None else None
        return {"username": row["username"], "discord_id": discord_id}

async def log_action(actor_username: str, action: str, target: str, reason: str, result_summary: str):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """INSERT INTO action_log
               (timestamp, actor_username, action, target, reason, result_summary)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (datetime.now(timezone.utc).isoformat(), actor_username, action, target, reason, result_summary),
        )
        await conn.commit()

async def search_logs(query: str = "", limit: int = 300):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row

        if query:
            like = f"%{query}%"
            async with conn.execute(
                """SELECT * FROM action_log
                   WHERE actor_username LIKE ? OR action LIKE ? OR target LIKE ?
                      OR reason LIKE ? OR result_summary LIKE ?
                   ORDER BY id DESC LIMIT ?""",
                (like, like, like, like, like, limit),
            ) as cursor:
                rows = await cursor.fetchall()
        else:
            async with conn.execute(
                "SELECT * FROM action_log ORDER BY id DESC LIMIT ?", (limit,)
            ) as cursor:
                rows = await cursor.fetchall()

        return [dict(r) for r in rows]
