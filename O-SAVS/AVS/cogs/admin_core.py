import asyncio, logging, discord, os, json

from typing import Optional
from discord import Embed
from discord.ext import commands

from data.vrchat import get_vrchat_user
from data.database import (
    get_all_verified_users,
    add_verified_user,
    remove_verified_user,
    get_vrchat_id_from_discord,
    get_server_settings,
    is_banned,
    add_banned_user,
    remove_banned_user,
    get_banned_user,
)

ADMIN_USERS = os.path.join(os.path.dirname(__file__), "..", "utils", "administrator_user_ids.json")


def is_user_allowed(user_id) -> bool:
    try:
        with open(ADMIN_USERS, "r", encoding="utf-8") as f:
            data = json.load(f)
            allowed_ids = {str(uid) for uid in data.get("allowed_user_ids", [])}
            return str(user_id) in allowed_ids
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logging.error(f"[AdminCore] Error reading {ADMIN_USERS}: {e}")
        return False

async def resolve_target(target_input: str) -> tuple[Optional[int], Optional[str]]:
    target_input = target_input.strip()

    if target_input.isdigit() and 16 <= len(target_input) <= 22:
        discord_id = int(target_input)
        vrchat_id = await get_vrchat_id_from_discord(discord_id)
        return discord_id, vrchat_id

    vrchat_id = target_input
    all_verified = await get_all_verified_users()
    discord_id = next((d_id for d_id, v_id in all_verified if v_id.lower() == vrchat_id.lower()), None)

    if not discord_id:
        vrc_user = await get_vrchat_user(vrchat_id)
        if vrc_user:
            vrchat_id = vrc_user.get("id", vrchat_id)

    return discord_id, vrchat_id

async def get_or_fetch_user(bot: commands.Bot, user_id: int) -> Optional[discord.User]:
    user = bot.get_user(user_id)
    if user:
        return user
    try:
        return await bot.fetch_user(user_id)
    except (discord.NotFound, discord.HTTPException):
        return None

async def get_bot_servers(bot: commands.Bot) -> list[dict]:
    return [
        {"id": guild.id, "name": guild.name, "member_count": guild.member_count}
        for guild in bot.guilds
    ]

async def generate_and_send_invite(bot: commands.Bot, guild_id: int, admin_discord_id: Optional[int]) -> dict:
    guild = bot.get_guild(guild_id)
    if not guild:
        return {"success": False, "error": f"Bot is not in a server with ID `{guild_id}`."}

    if not admin_discord_id:
        return {
            "success": False,
            "error": "Your dashboard account isn't linked to a Discord ID, so an invite can't be DMed to you.",
        }

    channel = next(
        (c for c in guild.text_channels if c.permissions_for(guild.me).create_instant_invite),
        None,
    )
    if not channel:
        return {"success": False, "error": f"Bot doesn't have permission to create an invite in `{guild.name}`."}

    try:
        invite = await channel.create_invite(max_uses=1, max_age=300, reason="Admin dashboard server invite request")
    except discord.Forbidden:
        return {"success": False, "error": f"Missing permissions to create an invite in `{guild.name}`."}
    except discord.HTTPException as e:
        return {"success": False, "error": f"Discord API error creating invite: {e}"}

    user = await get_or_fetch_user(bot, admin_discord_id)
    if not user:
        return {"success": False, "error": "Could not find your Discord account to send the invite."}

    try:
        await user.send(f"Here's your invite to **{guild.name}**: {invite.url}\n(This invite expires in 5 minutes, and is single use.)")
    except discord.Forbidden:
        return {"success": False, "error": "Could not DM you the invite -- check your Discord privacy settings."}

    return {"success": True, "message": f"Invite to {guild.name} sent to your Discord DMs!"}

async def send_verify_log(bot, guild, action, member, vrchat_id, operator_id, operator_name, reason=None):
    settings = await get_server_settings(guild.id)
    log_channel_id = settings.get("verification_logs")
    if not log_channel_id:
        return

    channel = guild.get_channel(log_channel_id)
    if not channel or not isinstance(channel, discord.TextChannel):
        return

    vrc_user = await get_vrchat_user(vrchat_id)
    username = vrc_user.get("username", "Unknown User") if vrc_user else "Unknown User"

    embed = Embed(title=f"🛡️ {action}", color=discord.Color.red(), timestamp=discord.utils.utcnow())
    if member:
        embed.add_field(name="User", value=f"{member.mention} (`{member.id}`)", inline=False)
    embed.add_field(
        name="VRChat Account",
        value=f"[{username}](https://vrchat.com/home/user/{vrchat_id}) (`{vrchat_id}`)",
        inline=True,
    )
    operator_display = f"<@{operator_id}> (`{operator_id}`)" if operator_id else f"{operator_name} (dashboard)"
    embed.add_field(name="Operator", value=operator_display, inline=True)

    if reason:
        embed.add_field(name="Reason", value=reason, inline=False)

    try:
        await channel.send(embed=embed)
    except (discord.Forbidden, discord.HTTPException) as e:
        logging.error(f"[AdminCore] Failed to send log in {guild.name} ({guild.id}): {e}")

async def perform_link(bot, operator_id, operator_name, target_user_id: int, vrchat_id: str, reason: Optional[str] = None) -> dict:
    vrc_user = await get_vrchat_user(vrchat_id)
    if not vrc_user:
        return {"success": False, "error": f"Invalid VRChat User ID or unable to fetch profile for `{vrchat_id}`."}

    username = vrc_user.get("username", "Unknown User")
    await add_verified_user(target_user_id, vrchat_id)

    added_count = 0
    already_had_count = 0
    error_summary = []

    for guild in bot.guilds:
        member = guild.get_member(target_user_id)
        if not member:
            continue

        settings = await get_server_settings(guild.id)
        role_id = settings.get("verified_role")
        if not role_id:
            continue

        role = guild.get_role(role_id)
        if role:
            if role not in member.roles:
                try:
                    await member.add_roles(
                        role, reason=f"Global Admin Link by {operator_name}" + (f": {reason}" if reason else "")
                    )
                    added_count += 1
                except discord.Forbidden:
                    error_summary.append(f"• **{guild.name}:** Missing permissions to add role")
                except discord.HTTPException as e:
                    error_summary.append(f"• **{guild.name}:** API error (`{e.status}`): `{e.text}`")
            else:
                already_had_count += 1

        await send_verify_log(bot, guild, "Admin Global Link", member, vrchat_id, operator_id, operator_name, reason)
        await asyncio.sleep(0.5)

    return {
        "success": True,
        "vrchat_username": username,
        "vrchat_id": vrchat_id,
        "target_user_id": target_user_id,
        "added_count": added_count,
        "already_had_count": already_had_count,
        "errors": error_summary,
    }

async def perform_unlink(bot, operator_id, operator_name, target_user_id: int, reason: Optional[str] = None) -> dict:
    vrchat_id = await get_vrchat_id_from_discord(target_user_id)
    if not vrchat_id:
        return {"success": False, "error": f"No linked VRChat account found for Discord ID `{target_user_id}`."}

    vrc_user = await get_vrchat_user(vrchat_id)
    username = vrc_user.get("username", "Unknown User") if vrc_user else "Unknown User"

    removed = await remove_verified_user(target_user_id)
    if not removed:
        return {"success": False, "error": f"Failed to remove database record for `{target_user_id}`."}

    removed_count = 0
    did_not_have_count = 0
    error_summary = []

    for guild in bot.guilds:
        member = guild.get_member(target_user_id)
        if not member:
            continue

        settings = await get_server_settings(guild.id)
        role_id = settings.get("verified_role")
        if not role_id:
            continue

        role = guild.get_role(role_id)
        if role:
            if role in member.roles:
                try:
                    await member.remove_roles(
                        role, reason=f"Global Admin Unlink by {operator_name}" + (f": {reason}" if reason else "")
                    )
                    removed_count += 1
                except discord.Forbidden:
                    error_summary.append(f"• **{guild.name}:** Missing permissions to remove role")
                except discord.HTTPException as e:
                    error_summary.append(f"• **{guild.name}:** API error (`{e.status}`): `{e.text}`")
            else:
                did_not_have_count += 1

        await send_verify_log(bot, guild, "Admin Global Unlink", member, vrchat_id, operator_id, operator_name, reason)
        await asyncio.sleep(0.5)

    return {
        "success": True,
        "vrchat_username": username,
        "vrchat_id": vrchat_id,
        "target_user_id": target_user_id,
        "removed_count": removed_count,
        "did_not_have_count": did_not_have_count,
        "errors": error_summary,
    }

async def perform_ban(bot, operator_id, operator_name, target_input: str, reason: str) -> dict:
    discord_id, vrchat_id = await resolve_target(target_input)

    if not discord_id and not vrchat_id:
        return {"success": False, "error": "Target could not be resolved to a valid Discord User ID or VRChat User ID."}

    target_key = discord_id or vrchat_id
    if await is_banned(target_key) or (vrchat_id and await is_banned(vrchat_id)):
        return {"success": False, "error": f"Target `{target_input}` is already globally banned."}

    await add_banned_user(target_id=target_key, reason=reason, moderator_id=operator_id)

    removed_count = 0
    did_not_have_count = 0
    error_summary = []

    if discord_id:
        await remove_verified_user(discord_id)

        for guild in bot.guilds:
            member = guild.get_member(discord_id)
            if not member:
                continue

            settings = await get_server_settings(guild.id)
            role_id = settings.get("verified_role")
            if not role_id:
                continue

            role = guild.get_role(role_id)
            if role:
                if role in member.roles:
                    try:
                        await member.remove_roles(role, reason="Global Ban Enforced")
                        removed_count += 1
                    except discord.Forbidden:
                        error_summary.append(f"• **{guild.name}:** Missing permissions to remove role")
                    except discord.HTTPException as e:
                        error_summary.append(f"• **{guild.name}:** API error (`{e.status}`): `{e.text}`")
                else:
                    did_not_have_count += 1

            if vrchat_id:
                await send_verify_log(
                    bot, guild, "Global User Ban", member, vrchat_id, operator_id, operator_name, "Global Ban Enforced"
                )

            await asyncio.sleep(0.5)

    return {
        "success": True,
        "discord_id": discord_id,
        "vrchat_id": vrchat_id,
        "removed_count": removed_count,
        "did_not_have_count": did_not_have_count,
        "errors": error_summary,
    }

async def perform_unban(bot, operator_id, operator_name, target_input: str, reason: str) -> dict:
    discord_id, vrchat_id = await resolve_target(target_input)

    unbanned = False
    for key in [discord_id, vrchat_id, target_input]:
        if key and await remove_banned_user(key):
            unbanned = True
            break

    if not unbanned:
        return {"success": False, "error": f"Target `{target_input}` is not currently globally banned."}

    return {"success": True, "discord_id": discord_id, "vrchat_id": vrchat_id}

async def perform_get_ban(bot, target_input: str) -> dict:
    discord_id, vrchat_id = await resolve_target(target_input)

    ban_info = None
    for key in [discord_id, vrchat_id, target_input]:
        if key:
            ban_info = await get_banned_user(key)
            if ban_info:
                break

    if not ban_info:
        return {"success": True, "banned": False, "discord_id": discord_id, "vrchat_id": vrchat_id}

    return {
        "success": True,
        "banned": True,
        "discord_id": discord_id,
        "vrchat_id": vrchat_id,
        "reason": ban_info.get("reason", "No reason provided"),
        "moderator_id": ban_info.get("moderator_id"),
        "timestamp": ban_info.get("timestamp"),
    }
