import asyncio, aiosqlite, hashlib, os, secrets

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

async def create_account(username: str, password: str, discord_id: int = None):
    salt = secrets.token_hex(16)
    pw_hash = await _hash_password(password, salt)
    discord_id_str = str(discord_id) if discord_id is not None else None
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "INSERT INTO admin_accounts (username, password_hash, salt, discord_id) VALUES (?, ?, ?, ?)",
            (username, pw_hash, salt, discord_id_str),
        )
        await conn.commit()

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
