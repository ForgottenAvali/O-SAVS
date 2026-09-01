import os, aiosqlite


from typing import Optional


DB_PATH = os.path.join(os.path.dirname(__file__), "..", "utils", "database.db")


async def init_db():
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS server_settings (
                server_id TEXT PRIMARY KEY,
                verified_role TEXT NOT NULL,
                verify_channel TEXT NOT NULL,
                verification_logs TEXT NOT NULL,
                av_start_code TEXT DEFAULT 'AVS-'
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
                    "server_id": int(data["server_id"]),
                    "verified_role": int(data["verified_role"]) if data["verified_role"] else None,
                    "verify_channel": int(data["verify_channel"]) if data["verify_channel"] else None,
                    "verification_logs": int(data["verification_logs"]) if data["verification_logs"] else None,
                    "av_start_code": data["av_start_code"]
                }
            return {
                "server_id": int(guild_id),
                "verified_role": None,
                "verify_channel": None,
                "verification_logs": None,
                "av_start_code": "AVS-"
            }


async def save_server_settings(
    guild_id: int | str, 
    verified_role: int | str, 
    verify_channel: int | str, 
    verification_logs: int | str, 
    av_start_code: str
):
    formatted_prefix = av_start_code.strip()
    if formatted_prefix and not formatted_prefix.endswith("-"):
        formatted_prefix += "-"

    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("""
            INSERT OR REPLACE INTO server_settings (
                server_id, 
                verified_role, 
                verify_channel, 
                verification_logs, 
                av_start_code
            ) VALUES (?, ?, ?, ?, ?)
        """, (
            str(guild_id), 
            str(verified_role), 
            str(verify_channel), 
            str(verification_logs), 
            formatted_prefix
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
            return [(int(row[0]), row[1]) for row in rows]


async def add_verified_user(discord_id: int | str, vrchat_id: str):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "INSERT OR REPLACE INTO verified_users (discord_id, vrchat_id) VALUES (?, ?)",
            (str(discord_id), vrchat_id)
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
                    "discord_id": int(data["discord_id"]),
                    "reason": data["reason"],
                    "moderator_id": int(data["moderator_id"]),
                    "timestamp": data["timestamp"]
                }
            return None


async def add_banned_user(discord_id: int | str, reason: str, moderator_id: int | str):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "INSERT OR REPLACE INTO banned_users (discord_id, reason, moderator_id) VALUES (?, ?, ?)",
            (str(discord_id), reason, str(moderator_id))
        )
        await conn.commit()


async def remove_banned_user(discord_id: int | str) -> bool:
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute(
            "DELETE FROM banned_users WHERE discord_id = ?", (str(discord_id),)
        ) as cursor:
            await conn.commit()
            return cursor.rowcount > 0
