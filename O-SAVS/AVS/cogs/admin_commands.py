import logging, os, discord

from typing import Optional
from discord import app_commands, Interaction
from discord.ext import commands

from cogs import admin_core
from cogs.verification import notice
from settings import PRIMARY_SERVER


def admin_only():
    return app_commands.check(lambda i: admin_core.is_user_allowed(i.user.id))

def parse_id(value: str) -> Optional[int]:
    value = value.strip()
    return int(value) if value.isdigit() else None

async def respond(interaction: Interaction, result: dict, title: str, details: str = ""):
    if result.get("success"):
        extra = "\n".join(result.get("errors", []))
        text = f"✅ **{title}**\n{details}\n{extra}".strip()
    else:
        text = f"❌ {result.get('error', 'Unknown error.')}"
    await interaction.followup.send(view=notice(text), ephemeral=True)

class AdminCommands(commands.Cog):
    admin = app_commands.Group(
        name="admin", description="O-SAVS global administration", guild_ids=[PRIMARY_SERVER]
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.loop.create_task(self._enforce_bans())

    async def _enforce_bans(self):
        await self.bot.wait_until_ready()
        await admin_core.enforce_server_bans(self.bot)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        if await admin_core.is_server_banned(guild.id):
            await guild.leave()

    async def cog_app_command_error(self, interaction: Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            text = "❌ You are not authorized to use O-SAVS admin commands."
        else:
            logging.error(f"[AdminCommands] {error}", exc_info=error)
            text = "❌ Something went wrong running that command."
        send = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message
        await send(view=notice(text), ephemeral=True)

    @admin.command(name="link", description="Globally link a Discord user to a VRChat account")
    @admin_only()
    async def link(self, interaction: Interaction, user: discord.User, vrchat_id: str, reason: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        r = await admin_core.perform_link(self.bot, interaction.user.id, str(interaction.user), user.id, vrchat_id.strip(), reason)
        await respond(interaction, r, "Linked",
                      f"{user} (`{user.id}`) → `{r.get('vrchat_username')}`\nRole added in {r.get('added_count')} server(s).")

    @admin.command(name="unlink", description="Globally unlink a Discord user")
    @admin_only()
    async def unlink(self, interaction: Interaction, user: discord.User, reason: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        r = await admin_core.perform_unlink(self.bot, interaction.user.id, str(interaction.user), user.id, reason)
        await respond(interaction, r, "Unlinked", f"Role removed in {r.get('removed_count')} server(s).")

    @admin.command(name="ban", description="Globally ban a Discord ID or VRChat ID from verifying")
    @admin_only()
    async def ban(self, interaction: Interaction, target: str, reason: str):
        await interaction.response.defer(ephemeral=True)
        r = await admin_core.perform_ban(self.bot, interaction.user.id, str(interaction.user), target, reason)
        await respond(interaction, r, "Banned",
                      f"Discord `{r.get('discord_id')}` · VRChat `{r.get('vrchat_id')}`\nRole removed in {r.get('removed_count')} server(s).")

    @admin.command(name="unban", description="Remove a global ban")
    @admin_only()
    async def unban(self, interaction: Interaction, target: str, reason: str):
        await interaction.response.defer(ephemeral=True)
        r = await admin_core.perform_unban(self.bot, interaction.user.id, str(interaction.user), target, reason)
        await respond(interaction, r, "Unbanned", f"Discord `{r.get('discord_id')}` · VRChat `{r.get('vrchat_id')}`")

    @admin.command(name="bancheck", description="Check whether a Discord ID or VRChat ID is banned")
    @admin_only()
    async def bancheck(self, interaction: Interaction, target: str):
        await interaction.response.defer(ephemeral=True)
        r = await admin_core.perform_get_ban(self.bot, target)
        if r.get("banned"):
            details = f"Reason: {r['reason']}\nModerator: `{r['moderator_id']}`\nSince: {r['timestamp']}"
            await respond(interaction, r, "Banned", details)
        else:
            await respond(interaction, r, "Not banned", f"Discord `{r.get('discord_id')}` · VRChat `{r.get('vrchat_id')}`")

    @admin.command(name="servers", description="List servers the bot is in")
    @admin_only()
    async def servers(self, interaction: Interaction):
        servers = await admin_core.get_bot_servers(self.bot)
        lines = [f"`{s['id']}` **{s['name']}** ({s['member_count']:,} members)" for s in servers]
        body = "\n".join(lines)[:3500]
        await interaction.response.send_message(view=notice(f"ℹ️ **Servers ({len(servers)})**\n{body}"), ephemeral=True)

    @admin.command(name="invite", description="DM yourself a one-hour, single-use invite to a server")
    @admin_only()
    async def invite(self, interaction: Interaction, server_id: str):
        await interaction.response.defer(ephemeral=True)
        gid = parse_id(server_id)
        if gid is None:
            return await respond(interaction, {"success": False, "error": "Invalid server ID."}, "")
        r = await admin_core.generate_and_send_invite(self.bot, gid, interaction.user.id)
        await respond(interaction, r, "Invite sent", r.get("message", ""))

    @admin.command(name="leave", description="Make the bot leave a server")
    @admin_only()
    async def leave(self, interaction: Interaction, server_id: str, reason: str):
        await interaction.response.defer(ephemeral=True)
        gid = parse_id(server_id)
        if gid is None:
            return await respond(interaction, {"success": False, "error": "Invalid server ID."}, "")
        r = await admin_core.perform_leave_server(self.bot, gid)
        await respond(interaction, r, "Left server", f"{r.get('server_name')} (`{gid}`)")

    @admin.command(name="maintenance", description="Turn maintenance mode on or off")
    @app_commands.describe(mode="Turn maintenance mode on or off")
    @app_commands.choices(mode=[
        app_commands.Choice(name="on", value="on"),
        app_commands.Choice(name="off", value="off"),
    ])
    @admin_only()
    async def maintenance(self, interaction: Interaction, mode: app_commands.Choice[str]):
        await interaction.response.defer(ephemeral=True)
        enabled = mode.value == "on"
        r = await admin_core.perform_set_maintenance(self.bot, enabled)
        await respond(interaction, r, f"Maintenance mode {'on' if enabled else 'off'}", r.get("message", ""))

    @admin.command(name="serverban", description="Ban a server and leave it")
    @admin_only()
    async def serverban(self, interaction: Interaction, server_id: str, reason: str):
        await interaction.response.defer(ephemeral=True)
        gid = parse_id(server_id)
        if gid is None:
            return await respond(interaction, {"success": False, "error": "Invalid server ID."}, "")
        r = await admin_core.perform_ban_server(self.bot, interaction.user.id, gid, reason)
        await respond(interaction, r, "Server banned", f"`{gid}` — bot left: {r.get('left_server')}")

    @admin.command(name="serverunban", description="Unban a server")
    @admin_only()
    async def serverunban(self, interaction: Interaction, server_id: str, reason: str):
        await interaction.response.defer(ephemeral=True)
        gid = parse_id(server_id)
        if gid is None:
            return await respond(interaction, {"success": False, "error": "Invalid server ID."}, "")
        r = await admin_core.perform_unban_server(gid)
        await respond(interaction, r, "Server unbanned", f"`{gid}`")

async def setup(bot: commands.Bot):
    if not PRIMARY_SERVER:
        print("[System] PRIMARY_SERVER not set, admin slash commands disabled.")
        return
    await bot.add_cog(AdminCommands(bot))
    await bot.tree.sync(guild=discord.Object(id=PRIMARY_SERVER))
