import asyncio, aiosqlite, hashlib, hmac, os, secrets, shutil

from datetime import datetime, timezone

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "utils", "admin_app.db"))

PBKDF2_ITERATIONS = 600_000
LEGACY_PBKDF2_ITERATIONS = 200_000

AUTH_CODE_LENGTH = 12
_UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_LOWER = "abcdefghijklmnopqrstuvwxyz"
_DIGITS = "0123456789"
_ALPHABET = _UPPER + _LOWER + _DIGITS
MIN_PASSWORD_LENGTH = 12


def generate_auth_code() -> str:
    while True:
        code = "".join(secrets.choice(_ALPHABET) for _ in range(AUTH_CODE_LENGTH))
        if (any(c in _UPPER for c in code)
                and any(c in _LOWER for c in code)
                and any(c in _DIGITS for c in code)):
            return code

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
        if "auth_code_strong" not in existing_columns:
            await conn.execute("ALTER TABLE admin_accounts ADD COLUMN auth_code_strong INTEGER NOT NULL DEFAULT 0")
        if "password_iters" not in existing_columns:
            await conn.execute(
                f"ALTER TABLE admin_accounts ADD COLUMN password_iters INTEGER NOT NULL DEFAULT {LEGACY_PBKDF2_ITERATIONS}"
            )
        if "auth_code_iters" not in existing_columns:
            await conn.execute(
                f"ALTER TABLE admin_accounts ADD COLUMN auth_code_iters INTEGER NOT NULL DEFAULT {LEGACY_PBKDF2_ITERATIONS}"
            )
        if "session_epoch" not in existing_columns:
            await conn.execute("ALTER TABLE admin_accounts ADD COLUMN session_epoch INTEGER NOT NULL DEFAULT 0")
        if "disabled" not in existing_columns:
            await conn.execute("ALTER TABLE admin_accounts ADD COLUMN disabled INTEGER NOT NULL DEFAULT 0")
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
    try:
        os.chmod(DB_PATH, 0o600)
    except OSError:
        pass

def _hash_password_sync(password: str, salt_hex: str, iterations: int) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), iterations).hex()

async def _hash_password(password: str, salt_hex: str, iterations: int = PBKDF2_ITERATIONS) -> str:
    return await asyncio.to_thread(_hash_password_sync, password, salt_hex, iterations)

async def create_account(username: str, password: str, discord_id: int = None) -> str:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")

    salt = secrets.token_hex(16)
    pw_hash = await _hash_password(password, salt)
    discord_id_str = str(discord_id) if discord_id is not None else None

    auth_code = generate_auth_code()
    code_salt = secrets.token_hex(16)
    code_hash = await _hash_password(auth_code, code_salt)

    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """INSERT INTO admin_accounts
               (username, password_hash, salt, discord_id, auth_code_hash, auth_code_salt, auth_code_strong,
                password_iters, auth_code_iters)
               VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)""",
            (username, pw_hash, salt, discord_id_str, code_hash, code_salt,
             PBKDF2_ITERATIONS, PBKDF2_ITERATIONS),
        )
        await conn.commit()
    return auth_code

async def account_exists(username: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute(
            "SELECT 1 FROM admin_accounts WHERE username = ?", (username,)
        ) as cursor:
            return await cursor.fetchone() is not None

async def reset_auth_code(username: str) -> str | None:
    auth_code = generate_auth_code()
    salt = secrets.token_hex(16)
    code_hash = await _hash_password(auth_code, salt)
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            """UPDATE admin_accounts
               SET auth_code_hash = ?, auth_code_salt = ?, auth_code_strong = 1,
                   auth_code_iters = ?, session_epoch = session_epoch + 1
               WHERE username = ?""",
            (code_hash, salt, PBKDF2_ITERATIONS, username),
        )
        await conn.commit()
        return auth_code if cursor.rowcount > 0 else None

async def set_password(username: str, password: str) -> bool:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    salt = secrets.token_hex(16)
    pw_hash = await _hash_password(password, salt)
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            """UPDATE admin_accounts
               SET password_hash = ?, salt = ?, password_iters = ?, session_epoch = session_epoch + 1
               WHERE username = ?""",
            (pw_hash, salt, PBKDF2_ITERATIONS, username),
        )
        await conn.commit()
        return cursor.rowcount > 0

async def set_disabled(username: str, disabled: bool) -> bool:
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            "UPDATE admin_accounts SET disabled = ?, session_epoch = session_epoch + 1 WHERE username = ?",
            (1 if disabled else 0, username),
        )
        await conn.commit()
        return cursor.rowcount > 0

async def get_session_state(username: str):
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute(
            "SELECT session_epoch, disabled FROM admin_accounts WHERE username = ?", (username,)
        ) as cursor:
            row = await cursor.fetchone()
    return (row[0], bool(row[1])) if row else None

async def has_auth_code(username: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute(
            "SELECT auth_code_hash, auth_code_strong FROM admin_accounts WHERE username = ?", (username,)
        ) as cursor:
            row = await cursor.fetchone()
            return bool(row and row[0] and row[1])

async def verify_auth_code(username: str, auth_code: str) -> bool:
    auth_code = (auth_code or "").strip()
    if len(auth_code) > 128:
        return False

    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute(
            "SELECT auth_code_hash, auth_code_salt, auth_code_strong, auth_code_iters FROM admin_accounts WHERE username = ?",
            (username,),
        ) as cursor:
            row = await cursor.fetchone()

    if not row or not row[0] or not row[1] or not row[2]:
        await _hash_password(auth_code, "00" * 16)
        return False
    candidate = await _hash_password(auth_code, row[1], row[3])
    if not hmac.compare_digest(candidate, row[0]):
        return False

    if row[3] < PBKDF2_ITERATIONS:
        new_salt = secrets.token_hex(16)
        new_hash = await _hash_password(auth_code, new_salt)
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute(
                "UPDATE admin_accounts SET auth_code_hash = ?, auth_code_salt = ?, auth_code_iters = ? WHERE username = ?",
                (new_hash, new_salt, PBKDF2_ITERATIONS, username),
            )
            await conn.commit()
    return True

async def verify_login(username: str, password: str):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT * FROM admin_accounts WHERE username = ?", (username,)
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            await _hash_password(password, "00" * 16)
            return None
        candidate = await _hash_password(password, row["salt"], row["password_iters"])
        if not hmac.compare_digest(candidate, row["password_hash"]):
            return None

        if row["password_iters"] < PBKDF2_ITERATIONS:
            new_salt = secrets.token_hex(16)
            new_hash = await _hash_password(password, new_salt)
            await conn.execute(
                "UPDATE admin_accounts SET password_hash = ?, salt = ?, password_iters = ? WHERE username = ?",
                (new_hash, new_salt, PBKDF2_ITERATIONS, username),
            )
            await conn.commit()

        raw_discord_id = row["discord_id"]
        discord_id = int(raw_discord_id) if raw_discord_id is not None else None
        return {
            "username": row["username"],
            "discord_id": discord_id,
            "session_epoch": row["session_epoch"],
            "disabled": bool(row["disabled"]),
        }

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
