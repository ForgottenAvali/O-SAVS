import os, aiosqlite


from typing import Optional


DB_PATH = os.path.join(os.path.dirname(__file__), "..", "utils", "database.db")


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


async def init_db():
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS server_settings (
                server_id TEXT PRIMARY KEY,
                verified_role TEXT NOT NULL,
                verify_channel TEXT NOT NULL,
                verification_logs TEXT NOT NULL,
                av_start_code TEXT DEFAULT 'AVS-',
                required_role TEXT
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
                discord_id TEXT PRIMARY KEY,
                reason TEXT NOT NULL,
                moderator_id TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await conn.commit()


async def get_server_settings(guild_id: int | str) -> dict:
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
                    "required_role": safe_int(data["required_role"])
                }
            return {
                "server_id": safe_int(guild_id),
                "verified_role": None,
                "verify_channel": None,
                "verification_logs": None,
                "av_start_code": "AVS-",
                "required_role": None
            }


async def save_server_settings(
    guild_id: int | str, 
    verified_role: int | str,
    verify_channel: int | str, 
    verification_logs: int | str, 
    av_start_code: str,
    required_role: Optional[int | str] = None
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
                required_role
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            str(clean_guild_id) if clean_guild_id is not None else str(guild_id), 
            str(clean_verified_role) if clean_verified_role is not None else str(verified_role), 
            str(clean_verify_channel) if clean_verify_channel is not None else str(verify_channel), 
            str(clean_verification_logs) if clean_verification_logs is not None else str(verification_logs), 
            formatted_prefix,
            str(clean_required_role) if clean_required_role is not None else None
        ))
        await conn.commit()


async def delete_server_settings(guild_id: int | str) -> bool:
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute(
            "DELETE FROM server_settings WHERE server_id = ?", (str(guild_id),)
        ) as cursor:
            await conn.commit()
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
            "SELECT 1 FROM verified_users WHERE vrchat_id = ?", (vrchat_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row is not None


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


async def add_verified_user(discord_id: int | str, vrchat_id: str):
    clean_id = safe_int(discord_id)
    target_id = str(clean_id) if clean_id is not None else str(discord_id)
    
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "INSERT OR REPLACE INTO verified_users (discord_id, vrchat_id) VALUES (?, ?)",
            (target_id, vrchat_id)
        )
        await conn.commit()


async def remove_verified_user(discord_id: int | str) -> bool:
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute(
            "DELETE FROM verified_users WHERE discord_id = ?", (str(discord_id),)
        ) as cursor:
            await conn.commit()
            return cursor.rowcount > 0


async def is_banned(discord_id: int | str) -> bool:
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute(
            "SELECT 1 FROM banned_users WHERE discord_id = ?", (str(discord_id),)
        ) as cursor:
            row = await cursor.fetchone()
            return row is not None


async def get_banned_user(discord_id: int | str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT * FROM banned_users WHERE discord_id = ?", (str(discord_id),)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                data = dict(row)
                return {
                    "discord_id": safe_int(data["discord_id"]),
                    "reason": data["reason"],
                    "moderator_id": safe_int(data["moderator_id"]),
                    "timestamp": data["timestamp"]
                }
            return None


async def add_banned_user(discord_id: int | str, reason: str, moderator_id: int | str):
    clean_user = safe_int(discord_id)
    clean_mod = safe_int(moderator_id)
    
    target_user = str(clean_user) if clean_user is not None else str(discord_id)
    target_mod = str(clean_mod) if clean_mod is not None else str(moderator_id)

    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "INSERT OR REPLACE INTO banned_users (discord_id, reason, moderator_id) VALUES (?, ?, ?)",
            (target_user, reason, target_mod)
        )
        await conn.commit()


async def remove_banned_user(discord_id: int | str) -> bool:
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute(
            "DELETE FROM banned_users WHERE discord_id = ?", (str(discord_id),)
        ) as cursor:
            await conn.commit()
            return cursor.rowcount > 0
