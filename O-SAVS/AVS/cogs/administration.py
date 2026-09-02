import logging, discord, asyncio, os, json


from typing import Optional
from datetime import datetime, timezone
from discord import Embed
from discord.ext import commands


from data.vrchat import get_vrchat_user
from data.database import (
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
SUPPORT_SERVER_ID = 1543888548296392775
ADMIN_CONTROL_CHANNEL_ID = 1544214237524525066


def is_admin_control_channel():
    async def predicate(ctx: commands.Context):
        if not ctx.guild or ctx.guild.id != SUPPORT_SERVER_ID:
            return False

        if ctx.channel.id != ADMIN_CONTROL_CHANNEL_ID:
            await ctx.send(
                f"❌ This command can only be used in <#{ADMIN_CONTROL_CHANNEL_ID}>.",
                delete_after=10
            )
            return False
        return True
    return commands.check(predicate)


class ServerPaginatorView(discord.ui.View):
    def __init__(self, author_id: int, guilds: list[discord.Guild], per_page: int = 10):
        super().__init__(timeout=180)
        self.author_id = author_id
        self.guilds = guilds
        self.per_page = per_page
        self.current_page = 0
        self.total_pages = max(1, (len(guilds) + per_page - 1) // per_page)
        
        self.update_button_states()

    def update_button_states(self):
        self.prev_button.disabled = (self.current_page == 0)
        self.next_button.disabled = (self.current_page >= self.total_pages - 1)

    def create_embed(self) -> discord.Embed:
        start_idx = self.current_page * self.per_page
        end_idx = start_idx + self.per_page
        page_guilds = self.guilds[start_idx:end_idx]

        embed = discord.Embed(
            title=f"📊 O-SAVS Server List ({len(self.guilds)} Total)",
            color=discord.Color.blue()
        )

        lines = [
            f"• **{g.name}** (`{g.id}`) - {g.member_count} members"
            for g in page_guilds
        ]
        
        embed.description = "\n".join(lines) if lines else "No servers found."
        embed.set_footer(text=f"Page {self.current_page + 1} of {self.total_pages}")
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Only the command invoker can use these controls.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_button_states()
            await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.update_button_states()
            await interaction.response.edit_message(embed=self.create_embed(), view=self)


class Administration(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot


    async def cog_command_error(self, ctx: commands.Context, error: Exception):
        if isinstance(original_error, commands.CheckFailure):
            return


    def is_user_allowed(self, user_id: int) -> bool:
        try:
            with open(ADMIN_USERS, "r", encoding="utf-8") as f:
                data = json.load(f)
                allowed_ids = data.get("allowed_user_ids", [])
                return user_id in allowed_ids
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logging.error(f"[Administration] Error reading {ADMIN_USERS}: {e}")
            return False


    async def cog_check(self, ctx: commands.Context) -> bool:
        return self.is_user_allowed(ctx.author.id)


    async def get_or_fetch_user(self, user_id: int) -> Optional[discord.User]:
        user = self.bot.get_user(user_id)
        if user:
            return user
        try:
            return await self.bot.fetch_user(user_id)
        except (discord.NotFound, discord.HTTPException):
            return None


    async def send_verify_log(self, guild: discord.Guild, action: str, member: discord.Member, vrchat_id: str, operator: discord.User, reason: Optional[str] = None):
        settings = await get_server_settings(guild.id)
        log_channel_id = settings.get("log_channel")
        if not log_channel_id:
            return

        channel = guild.get_channel(log_channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return

        vrc_user = await get_vrchat_user(vrchat_id)
        username = vrc_user.get("username", "Unknown User") if vrc_user else "Unknown User"

        embed = Embed(
            title=f"🛡️ {action}",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="User", value=f"{member.mention} (`{member.id}`)", inline=False)
        embed.add_field(name="VRChat Account", value=f"[{username}](https://vrchat.com/home/user/{vrchat_id}) (`{vrchat_id}`)", inline=True)
        embed.add_field(name="Operator", value=f"{operator.mention} (`{operator.id}`)", inline=True)

        if reason:
            embed.add_field(name="Reason", value=reason, inline=False)

        try:
            await channel.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException) as e:
            logging.error(f"[Audit Log Error] Failed to send log in {guild.name} ({guild.id}): {e}")


    @commands.command(name="link", help="Admin only: Force link a Discord user to a VRChat ID across all servers")
    @is_admin_control_channel()
    async def link_cmd(self, ctx: commands.Context, target_user_id: int, vrchat_id: str, *, reason: Optional[str] = None):
        if not self.is_user_allowed(ctx.author.id):
            return

        vrc_user = await get_vrchat_user(vrchat_id)
        if not vrc_user:
            embed = Embed(
                title="❌ VRChat User Not Found",
                description=f"Invalid VRChat User ID or unable to fetch user profile for `{vrchat_id}`.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        username = vrc_user.get("username", "Unknown User")
        await add_verified_user(target_user_id, vrchat_id)

        added_count = 0
        already_had_count = 0
        error_summary = []

        for guild in self.bot.guilds:
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
                        await member.add_roles(role, reason=f"Global Admin Link by {ctx.author.name}" + (f": {reason}" if reason else ""))
                        added_count += 1
                    except discord.Forbidden:
                        error_summary.append(f"• **{guild.name}:** Missing permissions to add role")
                    except discord.HTTPException as e:
                        error_summary.append(f"• **{guild.name}:** API error (`{e.status}`): `{e.text}`")
                else:
                    already_had_count += 1

            await self.send_verify_log(
                guild=guild,
                action="Admin Global Link",
                member=member,
                vrchat_id=vrchat_id,
                operator=ctx.author,
                reason=reason
            )

            await asyncio.sleep(0.5)

        summary_parts = []
        if added_count > 0:
            summary_parts.append(f"• Added verified role in **{added_count}** server(s).")
        if already_had_count > 0:
            summary_parts.append(f"• User already had the verified role in **{already_had_count}** server(s).")
        if not summary_parts and not error_summary:
            summary_parts.append("• *User was not found in any mutual servers with configured roles.*")

        if error_summary:
            summary_parts.extend(error_summary)

        target_user = await self.get_or_fetch_user(target_user_id)
        user_tag = f"{target_user.name} (`{target_user_id}`)" if target_user else f"`{target_user_id}`"

        embed = Embed(
            title="🔗 Account Link Enforced",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="Target User", value=user_tag, inline=False)
        embed.add_field(name="VRChat Profile", value=f"**[{username}](https://vrchat.com/home/user/{vrchat_id})** (`{vrchat_id}`)", inline=False)
        embed.add_field(name="Operator", value=f"{ctx.author.name} (`{ctx.author.id}`)", inline=True)
        embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
        embed.add_field(name="Role Addition Summary", value="\n".join(summary_parts), inline=False)

        await ctx.send(embed=embed)

    @link_cmd.error
    async def link_cmd_error(self, ctx: commands.Context, error: Exception):
        if not self.is_user_allowed(ctx.author.id):
            return

        original_error = getattr(error, "original", error)

        if isinstance(original_error, commands.MissingRequiredArgument):
            embed = Embed(title="⚠️ Invalid Command Usage", description="Usage: `.link <discord_user_id> <vrchat_user_id> [reason]`", color=discord.Color.gold())
            await ctx.send(embed=embed)
        elif isinstance(original_error, commands.BadArgument):
            embed = Embed(title="❌ Invalid Argument", description="Target User ID must be a numeric Discord integer ID.", color=discord.Color.red())
            await ctx.send(embed=embed)
        else:
            logging.error(f"[Link Error] {original_error}", exc_info=original_error)
            embed = Embed(title="⚠️ Internal Error", description=f"`{original_error}`", color=discord.Color.red())
            await ctx.send(embed=embed)


    @commands.command(name="unlink", help="Admin only: Unlink a Discord user from their VRChat account across all servers")
    @is_admin_control_channel()
    async def unlink_cmd(self, ctx: commands.Context, target_user_id: int, *, reason: Optional[str] = None):
        if not self.is_user_allowed(ctx.author.id):
            return

        vrchat_id = await get_vrchat_id_from_discord(target_user_id)

        if not vrchat_id:
            embed = Embed(
                title="❌ User Not Linked",
                description=f"No linked VRChat account found for Discord ID `{target_user_id}`.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        vrc_user = await get_vrchat_user(vrchat_id)
        username = vrc_user.get("username", "Unknown User") if vrc_user else "Unknown User"

        removed = await remove_verified_user(target_user_id)

        if not removed:
            embed = Embed(
                title="❌ Database Error",
                description=f"Failed to remove database record for `<@{target_user_id}>`.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        removed_count = 0
        did_not_have_count = 0
        error_summary = []

        for guild in self.bot.guilds:
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
                        await member.remove_roles(role, reason=f"Global Admin Unlink by {ctx.author.name}" + (f": {reason}" if reason else ""))
                        removed_count += 1
                    except discord.Forbidden:
                        error_summary.append(f"• **{guild.name}:** Missing permissions to remove role")
                    except discord.HTTPException as e:
                        error_summary.append(f"• **{guild.name}:** API error (`{e.status}`): `{e.text}`")
                else:
                    did_not_have_count += 1

            await self.send_verify_log(
                guild=guild,
                action="Admin Global Unlink",
                member=member,
                vrchat_id=vrchat_id,
                operator=ctx.author,
                reason=reason
            )

            await asyncio.sleep(0.5)

        summary_parts = []
        if removed_count > 0:
            summary_parts.append(f"• Removed verified role in **{removed_count}** server(s).")
        if did_not_have_count > 0:
            summary_parts.append(f"• User did not have the verified role in **{did_not_have_count}** server(s).")
        if not summary_parts and not error_summary:
            summary_parts.append("• *User was not found in any mutual servers with configured roles.*")

        if error_summary:
            summary_parts.extend(error_summary)

        target_user = await self.get_or_fetch_user(target_user_id)
        user_tag = f"{target_user.name} (`{target_user_id}`)" if target_user else f"`{target_user_id}`"

        embed = Embed(
            title="🔓 Account Unlink Enforced",
            color=discord.Color.orange(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="Target User", value=user_tag, inline=False)
        embed.add_field(name="Unlinked VRChat Profile", value=f"**[{username}](https://vrchat.com/home/user/{vrchat_id})** (`{vrchat_id}`)", inline=False)
        embed.add_field(name="Operator", value=f"{ctx.author.name} (`{ctx.author.id}`)", inline=True)
        embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
        embed.add_field(name="Role Removal Summary", value="\n".join(summary_parts), inline=False)

        await ctx.send(embed=embed)

    @unlink_cmd.error
    async def unlink_cmd_error(self, ctx: commands.Context, error: Exception):
        if not self.is_user_allowed(ctx.author.id):
            return

        original_error = getattr(error, "original", error)

        if isinstance(original_error, commands.MissingRequiredArgument):
            embed = Embed(title="⚠️ Invalid Command Usage", description="Usage: `.unlink <discord_user_id> [reason]`", color=discord.Color.gold())
            await ctx.send(embed=embed)
        elif isinstance(original_error, commands.BadArgument):
            embed = Embed(title="❌ Invalid Argument", description="Target User ID must be a numeric Discord integer ID.", color=discord.Color.red())
            await ctx.send(embed=embed)
        else:
            logging.error(f"[Unlink Error] {original_error}", exc_info=original_error)
            embed = Embed(title="⚠️ Internal Error", description=f"`{original_error}`", color=discord.Color.red())
            await ctx.send(embed=embed)


    @commands.command(name="ban_user", help="Admin only: Globally ban a user ID, unlink their VRChat ID, and strip roles")
    @is_admin_control_channel()
    async def ban_user_cmd(self, ctx: commands.Context, target_user_id: int, *, reason: str):
        if not self.is_user_allowed(ctx.author.id):
            return

        if await is_banned(target_user_id):
            embed = Embed(
                title="❌ Already Banned",
                description=f"User ID `{target_user_id}` is already globally banned.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        target_user = await self.get_or_fetch_user(target_user_id)
        vrchat_id = await get_vrchat_id_from_discord(target_user_id)

        await add_banned_user(
            discord_id=target_user_id,
            reason=reason,
            moderator_id=ctx.author.id
        )
        await remove_verified_user(target_user_id)

        removed_count = 0
        did_not_have_count = 0
        error_summary = []

        for guild in self.bot.guilds:
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
                        await member.remove_roles(role, reason="Global Ban Enforced")
                        removed_count += 1
                    except discord.Forbidden:
                        error_summary.append(f"• **{guild.name}:** Missing permissions to remove role")
                    except discord.HTTPException as e:
                        error_summary.append(f"• **{guild.name}:** API error (`{e.status}`): `{e.text}`")
                else:
                    did_not_have_count += 1

            if vrchat_id:
                await self.send_verify_log(
                    guild=guild,
                    action="Global User Ban",
                    member=member,
                    vrchat_id=vrchat_id,
                    operator=ctx.author,
                    reason="Global Ban Enforced"
                )

            await asyncio.sleep(0.5)

        summary_parts = []
        if removed_count > 0:
            summary_parts.append(f"• Stripped verified role in **{removed_count}** server(s).")
        if did_not_have_count > 0:
            summary_parts.append(f"• User did not have the verified role in **{did_not_have_count}** server(s).")
        if not summary_parts and not error_summary:
            summary_parts.append("• *User was not found as a member in any mutual servers.*")

        if error_summary:
            summary_parts.extend(error_summary)

        user_tag = f"{target_user.name} (`{target_user_id}`)" if target_user else f"`{target_user_id}`"

        embed = Embed(
            title="🚫 Global Ban Enforced",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="Target User", value=user_tag, inline=False)
        embed.add_field(name="Moderator", value=f"{ctx.author.name} (`{ctx.author.id}`)", inline=True)
        embed.add_field(name="Unlinked VRChat ID", value=f"`{vrchat_id or 'None'}`", inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Role Removal Summary", value="\n".join(summary_parts), inline=False)

        await ctx.send(embed=embed)

    @ban_user_cmd.error
    async def ban_user_cmd_error(self, ctx: commands.Context, error: Exception):
        if not self.is_user_allowed(ctx.author.id):
            return

        original_error = getattr(error, "original", error)

        if isinstance(original_error, commands.MissingRequiredArgument):
            embed = Embed(title="⚠️ Invalid Command Usage", description="Usage: `.ban_user <discord_user_id> <reason>`", color=discord.Color.gold())
            await ctx.send(embed=embed)
        elif isinstance(original_error, commands.BadArgument):
            embed = Embed(title="❌ Invalid Argument", description="Target User ID must be a numeric Discord integer ID.", color=discord.Color.red())
            await ctx.send(embed=embed)
        else:
            logging.error(f"[Ban Error] {original_error}", exc_info=original_error)
            embed = Embed(title="⚠️ Internal Error", description=f"`{original_error}`", color=discord.Color.red())
            await ctx.send(embed=embed)


    @commands.command(name="unban_user", help="Admin only: Remove a user from the global ban list")
    @is_admin_control_channel()
    async def unban_user_cmd(self, ctx: commands.Context, target_user_id: int, *, reason: str):
        if not self.is_user_allowed(ctx.author.id):
            return

        if not await remove_banned_user(target_user_id):
            embed = Embed(
                title="❌ Not Blacklisted",
                description=f"User ID `{target_user_id}` is not currently globally banned.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        target_user = await self.get_or_fetch_user(target_user_id)
        user_tag = f"{target_user.name} (`{target_user_id}`)" if target_user else f"`{target_user_id}`"

        embed = Embed(
            title="✅ Global Ban Removed",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="Target User", value=user_tag, inline=False)
        embed.add_field(name="Moderator", value=f"{ctx.author.name} (`{ctx.author.id}`)", inline=True)
        embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)

        await ctx.send(embed=embed)

    @unban_user_cmd.error
    async def unban_user_cmd_error(self, ctx: commands.Context, error: Exception):
        if not self.is_user_allowed(ctx.author.id):
            return

        original_error = getattr(error, "original", error)

        if isinstance(original_error, commands.MissingRequiredArgument):
            embed = Embed(title="⚠️ Invalid Command Usage", description="Usage: `.unban_user <discord_user_id> <reason>`", color=discord.Color.gold())
            await ctx.send(embed=embed)
        elif isinstance(original_error, commands.BadArgument):
            embed = Embed(title="❌ Invalid Argument", description="Target User ID must be a numeric Discord integer ID.", color=discord.Color.red())
            await ctx.send(embed=embed)
        else:
            logging.error(f"[Unban Error] {original_error}", exc_info=original_error)
            embed = Embed(title="⚠️ Internal Error", description=f"`{original_error}`", color=discord.Color.red())
            await ctx.send(embed=embed)


    @commands.command(name="get_user_ban", help="Admin only: Check if a Discord user is globally banned and view ban details")
    @is_admin_control_channel()
    async def get_user_ban_cmd(self, ctx: commands.Context, target_user_id: int):
        if not self.is_user_allowed(ctx.author.id):
            return

        ban_info = await get_banned_user(target_user_id)

        if not ban_info:
            embed = Embed(
                title="✅ No Ban Record Found",
                description=f"User ID `{target_user_id}` is **not** globally banned.",
                color=discord.Color.green()
            )
            return await ctx.send(embed=embed)

        reason = ban_info.get("reason", "No reason provided")
        moderator_id = ban_info.get("moderator_id")
        created_at = ban_info.get("timestamp")
        if isinstance(created_at, str):
            try:
                cleaned_ts = created_at.replace("Z", "+00:00")
                dt = datetime.fromisoformat(cleaned_ts)

                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)

                created_at = dt
            except ValueError:
                pass

        target_user = await self.get_or_fetch_user(target_user_id)
        mod_user = await self.get_or_fetch_user(moderator_id) if moderator_id else None

        user_tag = f"{target_user.name} (`{target_user_id}`)" if target_user else f"`{target_user_id}`"
        mod_tag = f"{mod_user.name} (`{moderator_id}`)" if mod_user else (f"`{moderator_id}`" if moderator_id else "Unknown")

        embed = Embed(
            title="🚫 Global Ban Record Found",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="Target User", value=user_tag, inline=False)
        embed.add_field(name="Moderator", value=mod_tag, inline=True)

        if created_at:
            embed.add_field(name="Ban Date", value=f"<t:{int(created_at.timestamp())}:F>" if isinstance(created_at, datetime) else f"`{created_at}`", inline=True)

        embed.add_field(name="Reason", value=reason, inline=False)

        await ctx.send(embed=embed)

    @get_user_ban_cmd.error
    async def get_user_ban_cmd_error(self, ctx: commands.Context, error: Exception):
        if not self.is_user_allowed(ctx.author.id):
            return

        original_error = getattr(error, "original", error)

        if isinstance(original_error, commands.MissingRequiredArgument):
            embed = Embed(title="⚠️ Invalid Command Usage", description="Usage: `.get_user_ban <discord_user_id>`", color=discord.Color.gold())
            await ctx.send(embed=embed)
        elif isinstance(original_error, commands.BadArgument):
            embed = Embed(title="❌ Invalid Argument", description="Target User ID must be a numeric Discord integer ID.", color=discord.Color.red())
            await ctx.send(embed=embed)
        else:
            logging.error(f"[Get Ban Error] {original_error}", exc_info=original_error)
            embed = Embed(title="⚠️ Internal Error", description=f"`{original_error}`", color=discord.Color.red())
            await ctx.send(embed=embed)


    @commands.command(name="get_osavs_servers", help="Admin only: View paginated server list where O-SAVS is present")
    @is_admin_control_channel()
    async def get_osavs_servers(self, ctx: commands.Context):
        if not self.bot.guilds:
            return await ctx.send("❌ O-SAVS is not currently in any servers.")

        view = ServerPaginatorView(author_id=ctx.author.id, guilds=list(self.bot.guilds))
        await ctx.send(embed=view.create_embed(), view=view)

    @get_osavs_servers.error
    async def get_osavs_servers_error(self, ctx: commands.Context, error: Exception):
        original_error = getattr(error, "original", error)

        if not isinstance(original_error, commands.CheckFailure):
            logging.error(f"[Get Servers Error] {original_error}", exc_info=original_error)
            embed = Embed(title="⚠️ Internal Error", description=f"`{original_error}`", color=discord.Color.red())
            await ctx.send(embed=embed)


    @commands.command(name="invite_me_osavs", help="Admin only: Generate single-use invite for specified guild ID")
    @is_admin_control_channel()
    async def invite_me_osavs(self, ctx: commands.Context, server_id: int):
        guild = self.bot.get_guild(server_id)
        
        if not guild:
            return await ctx.send(f"❌ Server with ID `{server_id}` was not found or O-SAVS is not in that server.")

        target_channel = None
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).create_instant_invite:
                target_channel = channel
                break

        if not target_channel:
            return await ctx.send(
                f"❌ Unable to create an invite for **{guild.name}** (`{guild.id}`). "
                "The bot lacks `Create Instant Invite` permissions in all available text channels."
            )

        try:
            invite = await target_channel.create_invite(
                max_age=300,
                max_uses=1,
                reason=f"O-SAVS Admin invite generated by {ctx.author}"
            )
            await ctx.send(
                f"🔑 **Invite generated for {guild.name}:**\n"
                f"{invite.url}\n"
                "*Note: This link will expire in 5 minutes and can only be used once.*"
            )
        except discord.Forbidden:
            await ctx.send(f"❌ Permission error while generating invite for **{guild.name}**.")
        except discord.HTTPException as e:
            logging.error(f"[Invite Admin Error] {e}")
            await ctx.send(f"❌ Failed to generate invite due to an HTTP exception: `{e}`")

    @invite_me_osavs.error
    async def invite_me_osavs_error(self, ctx: commands.Context, error: Exception):
        original_error = getattr(error, "original", error)

        if isinstance(original_error, commands.MissingRequiredArgument):
            embed = Embed(title="⚠️ Invalid Command Usage", description="Usage: `.invite_me_osavs <discord_server_id>`", color=discord.Color.gold())
            await ctx.send(embed=embed)
        elif isinstance(original_error, commands.BadArgument):
            embed = Embed(title="❌ Invalid Argument", description="Target Server ID must be a numeric Discord integer ID.", color=discord.Color.red())
            await ctx.send(embed=embed)
        elif not isinstance(original_error, commands.CheckFailure):
            logging.error(f"[Invite Error] {original_error}", exc_info=original_error)
            embed = Embed(title="⚠️ Internal Error", description=f"`{original_error}`", color=discord.Color.red())
            await ctx.send(embed=embed)


    @commands.command(name="commands", help="Admin only: See what all the admin commands are")
    async def commands_cmd(self, ctx: commands.Context):
        if not self.is_user_allowed(ctx.author.id):
            return

        embed = Embed(
            title="O-SAVS Administrator Commands",
            description=(
                ".link (Usage: `.link <discord_user_id> <vrchat_user_id> [reason]`)\n"
                ".unlink (Usage: `.unlink <discord_user_id> [reason]`)\n"
                ".ban_user (Usage: `.ban_user <discord_user_id> <reason>`)\n"
                ".unban_user (Usage: `.unban_user <discord_user_id> <reason>`)\n"
                ".get_user_ban (Usage: `.get_user_ban <discord_user_id>`)\n"
                ".get_osavs_servers (Usage: `.get_osavs_servers`)\n"
                ".invite_me_osavs (Usage: `.invite_me_osavs <discord_server_id>`)"
            ),
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow()
        )

        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Administration(bot))
