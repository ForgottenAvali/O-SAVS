import random, string, asyncio, re, logging, discord


from typing import Optional
from datetime import datetime, timezone
from discord import app_commands, Interaction, ui, ButtonStyle, Embed
from discord.ext import commands


from data.vrchat import get_vrchat_user
from data.database import (
    get_server_settings,
    get_vrchat_id_from_discord,
    is_vrchat_id_verified,
    add_verified_user,
    remove_verified_user,
    save_server_settings,
    get_all_verified_users,
    delete_server_settings,
    is_banned,
    add_banned_user,
    remove_banned_user,
    get_banned_user
)


ALLOWED_USER_IDS = {1112115547589578904, 604433120045039617, 554334137306185747}


def generate_code(prefix: str = "AVS-") -> str:
    clean_prefix = prefix.strip() if prefix else "AVS-"
    return clean_prefix + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


class BioCheckView(ui.View):
    def __init__(self, bot: commands.Bot, cog: commands.Cog, user_id: str, code: str, settings: dict):
        super().__init__(timeout=300)
        self.bot = bot
        self.cog = cog
        self.user_id = user_id
        self.code = code
        self.settings = settings


    @ui.button(label="I've updated my profile", style=ButtonStyle.success)
    async def check_bio(self, interaction: Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)

        user_data = await get_vrchat_user(self.user_id)

        if not user_data:
            return await interaction.followup.send(
                "❌ Failed to fetch VRChat profile data. Please verify your User ID or try again later.",
                ephemeral=True
            )

        bio = user_data.get("bio", "") or ""
        status = user_data.get("status", "") or ""

        if self.code not in bio and self.code not in status:
            return await interaction.followup.send(
                "❌ Verification code was **not found** in your VRChat status or bio. Make sure you entered it correctly.",
                ephemeral=True
            )

        if not user_data.get("verification"):
            return await interaction.followup.send(
                "❌ Your VRChat account is **not age verified**. Official VRChat 18+ verification is required.",
                ephemeral=True
            )

        await add_verified_user(interaction.user.id, self.user_id)

        role_added = False

        for guild in self.bot.guilds:
            member = guild.get_member(interaction.user.id)
            if not member:
                continue

            settings = await get_server_settings(guild.id)
            role_id = settings.get("verified_role")
            if not role_id:
                continue

            role = guild.get_role(role_id)
            if role and role not in member.roles:
                try:
                    await member.add_roles(role, reason="O-SAVS Automated Verification")
                    role_added = True
                except discord.Forbidden:
                    logging.error(f"[Verify] Missing permissions to assign role in guild {guild.id}")
                except discord.HTTPException as e:
                    logging.error(f"[Verify] HTTP error assigning role in guild {guild.id}: {e}")

            try:
                await self.cog.send_verify_log(
                    guild=guild,
                    action="User Verified",
                    member=member,
                    vrchat_id=self.user_id,
                    operator=interaction.user
                )
            except Exception as e:
                logging.error(f"[Verify Log Error - {guild.id}] {e}")

        self.stop()

        await interaction.followup.send(
            "✅ **Verification complete!**\n"
            f"You have been age verified in all servers using O-SAVS including **{interaction.guild.name}**.\n"
            "You may now remove the verification code from your VRChat profile.",
            ephemeral=True
        )


class ConfirmCheck(ui.View):
    def __init__(self, bot: commands.Bot, cog: commands.Cog):
        super().__init__(timeout=None)
        self.bot = bot
        self.cog = cog


    @ui.button(label="Age Verify", style=ButtonStyle.primary, custom_id="ageverify_start")
    async def verify_button(self, interaction: Interaction, button: ui.Button):
        modal = VRChatUsername(self.bot, self.cog, interaction)
        await interaction.response.send_modal(modal)


class VRChatUsername(ui.Modal, title="VRChat Verification"):
    userID = ui.TextInput(
        label="What is your VRChat user id?",
        style=discord.TextStyle.short,
        placeholder="usr_...",
        required=True,
        max_length=128
    )


    def __init__(self, bot: commands.Bot, cog: commands.Cog, interaction: Interaction):
        super().__init__(timeout=None)
        self.bot = bot
        self.cog = cog
        self.interaction = interaction


    async def on_submit(self, modal_interaction: Interaction):
        await modal_interaction.response.defer(ephemeral=True)

        existing_vrc_id = await get_vrchat_id_from_discord(modal_interaction.user.id)
        if existing_vrc_id:
            return await modal_interaction.followup.send(
                f"❌ Your Discord account is already linked to VRChat ID (`{existing_vrc_id}`).\n"
                "If you need to unlink this account, you may join the [Noodle's Nexus](https://discord.gg/PeXzxBeUcB) support server.",
                ephemeral=True
            )

        banned_user = await is_banned(modal_interaction.user.id)
        if banned_user:
            return await modal_interaction.followup.send(
                f"❌ Your Discord account was banned by the administration team for O-SAVS.\n"
                "If you believe this ban was issued in error you may appeal by joining the [Noodle's Nexus](https://discord.gg/PeXzxBeUcB) support server.",
                ephemeral=True
            )

        user_input = self.userID.value.strip()

        id_pattern = r"usr_[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}"
        match = re.search(id_pattern, user_input, re.IGNORECASE) or re.search(r"usr_[a-fA-F0-9\-]{20,}", user_input)

        if not match:
            invalid_embed = Embed(
                title="Invalid Input!",
                description=(
                    "Could not detect a valid VRChat User ID.\n"
                    "Please paste your **profile link** (e.g. `https://vrchat.com/home/user/usr_...`) or raw **User ID** (`usr_...`).\n"
                    "If you believe this is an error you may get assistance in the [Noodle's Nexus](https://discord.gg/PeXzxBeUcB) support server.\n\n"
                    f"You entered: `{user_input}`"
                ),
                color=discord.Color.red()
            )
            return await modal_interaction.followup.send(embed=invalid_embed, ephemeral=True)

        clean_id = match.group(0)

        if await is_vrchat_id_verified(clean_id):
            return await modal_interaction.followup.send(
                f"❌ The VRChat account (`{clean_id}`) is already linked to another Discord user.",
                ephemeral=True
            )

        settings = await get_server_settings(modal_interaction.guild_id)
        prefix = settings.get("av_start_code") or "AVS-"
        code = generate_code(prefix)

        user_data = await get_vrchat_user(clean_id)
        username = user_data.get("username", "Unknown User") if user_data else "Unknown User"

        view = BioCheckView(self.bot, self.cog, clean_id, code, settings)

        start_embed = Embed(
            title=f"🔐 Verification for `{username}`",
            description=(
                f"Add the following code to your VRChat status or bio: **`{code}`**\n\n"
                "Once updated, click the button below to complete verification."
            ),
            color=discord.Color.blue()
        )

        await modal_interaction.followup.send(embed=start_embed, view=view, ephemeral=True)


class AgeVerify(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._has_synced = False
        self.bot.add_view(ConfirmCheck(bot, self))


    async def cog_load(self):
        if self.bot.is_ready() and not self._has_synced:
            self._has_synced = True
            self.bot.loop.create_task(self.sync_offline_verifications())


    async def send_verify_log(self, guild: discord.Guild, action: str, member: discord.Member, vrchat_id: str, operator: Optional[discord.User | discord.Member] = None, reason: Optional[str] = None):
        settings = await get_server_settings(guild.id)
        log_channel_id = settings.get("verification_logs") or settings.get("log_channel")
        if not log_channel_id:
            return

        log_channel = guild.get_channel(log_channel_id)
        if not isinstance(log_channel, discord.TextChannel):
            return

        vrc_user = await get_vrchat_user(vrchat_id)
        username = vrc_user.get("username", "Unknown User") if vrc_user else "Unknown User"

        active_operator = operator or self.bot.user

        embed = discord.Embed(
            title=f"🛡️ {action}",
            color=discord.Color.blue() if "Link" in action or "Verified" in action else discord.Color.orange(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="User", value=f"{member.mention} (`{member.id}`)", inline=True)
        embed.add_field(name="VRChat Account", value=f"[{username}](https://vrchat.com/home/user/{vrchat_id})\n`{vrchat_id}`", inline=True)
        embed.add_field(name="Operator", value=f"{active_operator.mention} (`{active_operator.id}`)", inline=False)

        if reason:
            embed.add_field(name="Reason", value=reason, inline=False)

        max_retries = 3
        for attempt in range(max_retries):
            try:
                await log_channel.send(embed=embed)
                await asyncio.sleep(0.5)
                break
            except discord.Forbidden:
                logging.error(f"[Log Dispatch Failed - {guild.id}] Missing permissions to send messages in channel {log_channel_id}.")
                break
            except discord.HTTPException as e:
                if e.status == 429:
                    retry_after = getattr(e, "retry_after", 1)
                    logging.warning(f"[Log Dispatch Rate Limited] Retrying in {retry_after}s for guild {guild.id}")
                    await asyncio.sleep(retry_after)
                else:
                    logging.error(f"[Log Dispatch Error - {guild.id}] HTTP {e.status}: {e.text}")
                    break
            except Exception as e:
                logging.error(f"[Log Dispatch Failed - {guild.id}] {e}")
                break


    async def get_or_fetch_user(self, user_id: int) -> Optional[discord.User]:
        user = self.bot.get_user(user_id)
        if user:
            return user
        try:
            return await self.bot.fetch_user(user_id)
        except (discord.NotFound, discord.HTTPException):
            return None


    @app_commands.command(name="setup", description="Configure O-SAVS server settings, send the panel, and sync existing members")
    @app_commands.describe(
        verified_role="The role assigned to age verified members",
        verify_channel="The channel where the verification panel will be posted",
        av_start_code="Custom prefix for verification codes (default: AVS-)"
    )
    @app_commands.default_permissions(administrator=True)
    async def setup_cmd(
        self,
        interaction: Interaction,
        verified_role: discord.Role,
        verify_channel: discord.TextChannel,
        av_start_code: str = None
    ):
        await interaction.response.defer(ephemeral=True)

        bot_top_role = interaction.guild.me.top_role
        if verified_role >= bot_top_role:
            embed = discord.Embed(
                title="❌ Role Hierarchy Error",
                description=(
                    f"I cannot assign the {verified_role.mention} role because it is **higher than or equal to** my highest role ({bot_top_role.mention}).\n\n"
                    "**How to fix:**\n"
                    "1. Open **Server Settings** > **Roles**.\n"
                    "- Drag my role above the verified role in the role list.\n"
                    "- Run `/setup` again."
                ),
                color=discord.Color.red()
            )
            return await interaction.followup.send(embed=embed, ephemeral=True)

        if not interaction.guild.me.guild_permissions.manage_roles:
            return await interaction.followup.send(
                "❌ I do not have the **Manage Roles** permission in this server.",
                ephemeral=True
            )

        log_overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False, send_messages=False),
            interaction.guild.me: discord.PermissionOverwrite(
                read_messages=True,
                send_messages=True,
                embed_links=True,
                attach_files=True,
                view_channel=True
            )
        }

        for role in interaction.guild.roles:
            if role.permissions.administrator:
                log_overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, view_channel=True)

        target_log_channel = discord.utils.get(interaction.guild.text_channels, name="verification-logs")

        if target_log_channel:
            try:
                for target, overwrite in log_overwrites.items():
                    await target_log_channel.set_permissions(target, overwrite=overwrite, reason="O-SAVS setup: Enforcing strict admin log access")
            except discord.Forbidden:
                return await interaction.followup.send(
                    f"⚠️ Found existing {target_log_channel.mention}, but lacked permissions to update its channel access overrides. Update or remove the channel then run `/setup` again.",
                    ephemeral=True
                )
        else:
            try:
                target_log_channel = await interaction.guild.create_text_channel(
                    name="verification-logs",
                    overwrites=log_overwrites,
                    reason="O-SAVS setup: Dedicated verification log channel created"
                )
            except discord.Forbidden:
                return await interaction.followup.send(
                    "❌ Missing permissions to create `#verification-logs`. Please check my role hierarchy then run `/setup` again.",
                    ephemeral=True
                )

        prefix = av_start_code.strip() if av_start_code else "AVS-"

        await save_server_settings(
            guild_id=interaction.guild_id,
            verified_role=verified_role.id,
            verify_channel=verify_channel.id,
            verification_logs=target_log_channel.id,
            av_start_code=prefix
        )

        thank_you_embed = Embed(
            title="Thank you for using O-SAVS!",
            description=(
                "O-SAVS (Open-Source Age Verification System) configuration has been updated for this server.\n\n"
                f"**Verified Role:** {verified_role.mention}\n"
                f"**Verify Channel:** {verify_channel.mention}\n"
                f"**Verification Logs:** {target_log_channel.mention}\n"
                f"**Code Prefix:** `{prefix}`\n\n"
                "Noodle would personally like to thank you for using O-SAVS, we hope you enjoy the system and if you have any issues and or suggestions feel free to reach out in [Noodle's Nexus](https://discord.gg/PeXzxBeUcB)!"
            ),
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        try:
            await target_log_channel.send(embed=thank_you_embed)
        except discord.Forbidden:
            logging.error(f"[Setup] Lacking permissions to send thank you embed in {target_log_channel.id}")

        panel_embed = Embed(
            title="VRChat 18+ Verification",
            description=(
                "To age verify yourself, you must verify that your VRChat account is **age verified**.\n\n"
                "Click the **Age Verify** button below to begin."
            ),
            color=discord.Color.dark_grey()
        )
        panel_embed.add_field(
            name="Instructions",
            value=(
                "1. Sign into [vrchat.com](https://vrchat.com/home)\n"
                "- Go to your profile and copy the link to it\n"
                "- Click the Age Verify button below and input the link you copied\n"
                "- After clicking submit, we will give you a code; Input that code into your VRChat status or bio\n"
                "- After inputting the code into your status or bio click the `I've updated my profile` button.\n"
                "- If you did it all correctly you will now be age verified in the server and any other server using O-SAVS"
            )
        )

        try:
            await verify_channel.send(embed=panel_embed, view=ConfirmCheck(self.bot, self))
        except discord.Forbidden:
            return await interaction.followup.send(
                f"⚠️ Server settings saved, but I lacked permissions to send the verification panel in {verify_channel.mention}.",
                ephemeral=True
            )

        all_verified = await get_all_verified_users()
        synced_count = 0

        for discord_id, vrchat_id in all_verified:
            member = interaction.guild.get_member(discord_id)
            if member:
                if verified_role not in member.roles:
                    try:
                        await member.add_roles(verified_role, reason="O-SAVS setup: Syncing existing global verification")
                        synced_count += 1
                        await self.send_verify_log(
                            guild=interaction.guild,
                            action="User Verified",
                            member=member,
                            vrchat_id=vrchat_id,
                            operator=interaction.user,
                            reason="O-SAVS setup: Syncing existing global verification"
                        )
                        await asyncio.sleep(0.5)
                    except discord.Forbidden:
                        logging.error(f"[Setup] Failed to grant role to {member.id} due to permissions.")

        await interaction.followup.send(
            f"✅ **Setup complete!**\n"
            f"- Created/Secured log channel {target_log_channel.mention}.\n"
            f"- Verification panel dispatched to {verify_channel.mention}.\n"
            f"- Synced **{synced_count}** previously verified user(s) currently in this server.",
            ephemeral=True
        )

    
    @commands.command(name="link", help="Admin only: Force link a Discord user to a VRChat ID across all servers")
    async def link_cmd(self, ctx: commands.Context, target_user_id: int, vrchat_id: str, *, reason: Optional[str] = None):
        if ctx.author.id not in ALLOWED_USER_IDS:
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
        if ctx.author.id not in ALLOWED_USER_IDS:
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
    async def unlink_cmd(self, ctx: commands.Context, target_user_id: int, *, reason: Optional[str] = None):
        if ctx.author.id not in ALLOWED_USER_IDS:
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
        if ctx.author.id not in ALLOWED_USER_IDS:
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
    async def ban_user_cmd(self, ctx: commands.Context, target_user_id: int, *, reason: str):
        if ctx.author.id not in ALLOWED_USER_IDS:
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
        if ctx.author.id not in ALLOWED_USER_IDS:
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
    async def unban_user_cmd(self, ctx: commands.Context, target_user_id: int, *, reason: str):
        if ctx.author.id not in ALLOWED_USER_IDS:
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
        if ctx.author.id not in ALLOWED_USER_IDS:
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
    async def get_user_ban_cmd(self, ctx: commands.Context, target_user_id: int):
        if ctx.author.id not in ALLOWED_USER_IDS:
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
        if ctx.author.id not in ALLOWED_USER_IDS:
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


    @commands.command(name="commands", help="Admin only: See what all the admin commands are")
    async def commands_cmd(self, ctx: commands.Context):
        if ctx.author.id not in ALLOWED_USER_IDS:
            return

        embed = Embed(
            title="O-SAVS Administrator Commands",
            description=
                ".link (Usage: `.link <discord_user_id> <vrchat_user_id> [reason]`)\n"
                ".unlink (Usage: `.unlink <discord_user_id> [reason]`)\n"
                ".ban_user (Usage: `.ban_user <discord_user_id> <reason>`)\n"
                ".unban_user (Usage: `.unban_user <discord_user_id> <reason>`)\n"
                ".get_user_ban (Usage: `.get_user_ban <discord_user_id>`)",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow()
        )

        await ctx.send(embed=embed)


    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        try:
            removed = await delete_server_settings(guild.id)
            if removed:
                logging.info(f"[Guild Remove] Removed settings for guild: {guild.name} ({guild.id})")
            else:
                logging.info(f"[Guild Remove] No settings record found to delete for guild: {guild.name} ({guild.id})")
        except Exception as e:
            logging.error(f"[Guild Remove Error - {guild.id}] Failed to delete settings: {e}")


    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return

        vrchat_id = await get_vrchat_id_from_discord(member.id)
        if not vrchat_id:
            return

        settings = await get_server_settings(member.guild.id)
        role_id = settings.get("verified_role")
        if not role_id:
            return

        role = member.guild.get_role(role_id)
        if not role or role in member.roles:
            return

        try:
            await member.add_roles(role, reason="O-SAVS Auto-Role: Existing global verification")
            logging.info(f"[Member Join] Automatically verified {member} ({member.id}) in {member.guild.name}")
        except discord.Forbidden:
            logging.error(f"[Member Join] Missing permissions to assign role in {member.guild.name} ({member.guild.id})")
            return
        except discord.HTTPException as e:
            logging.error(f"[Member Join] HTTP error assigning role in {member.guild.name} ({member.guild.id}): {e}")
            return

        try:
            await self.send_verify_log(
                guild=member.guild,
                action="User Verified",
                member=member,
                vrchat_id=vrchat_id,
                operator=self.bot.user,
                reason="Auto-assigned role on server join (Global Verification)"
            )
        except Exception as e:
            logging.error(f"[Member Join Log Error - {member.guild.id}] {e}")

            
    async def sync_offline_verifications(self):
        await self.bot.wait_until_ready()
        logging.info("[Startup Sync] Starting startup verification role sync")

        all_verified = await get_all_verified_users()
        if not all_verified:
            logging.info("[Startup Sync] No verified users found in database")
            return

        verified_map = {discord_id: vrchat_id for discord_id, vrchat_id in all_verified}
        synced_count = 0
        error_count = 0

        for guild in self.bot.guilds:
            settings = await get_server_settings(guild.id)
            role_id = settings.get("verified_role")
            if not role_id:
                continue

            role = guild.get_role(role_id)
            bot_member = guild.me
            
            if not role or not bot_member.guild_permissions.manage_roles or role >= bot_member.top_role:
                continue

            for member in guild.members:
                if member.id in verified_map and role not in member.roles:
                    if await is_banned(member.id):
                        continue

                    try:
                        await member.add_roles(role, reason="O-SAVS Startup Sync: Granting role to offline verified user")
                        synced_count += 1
                        
                        await self.send_verify_log(
                            guild=guild,
                            action="User Verified",
                            member=member,
                            vrchat_id=verified_map[member.id],
                            operator=self.bot.user,
                            reason="O-SAVS Startup Sync"
                        )
                        
                        await asyncio.sleep(0.5)
                    except discord.Forbidden:
                        logging.warning(f"[Startup Sync Error - {guild.id}] Missing permissions in {guild.name} for {member}")
                        error_count += 1
                    except discord.HTTPException as e:
                        logging.error(f"[Startup Sync Error - {guild.id}] HTTP Error in {guild.name} for {member}: {e}")
                        error_count += 1

        logging.info(f"[Startup Sync] Complete! Granted roles to {synced_count} member(s). Errors: {error_count}")


async def setup(bot: commands.Bot):
    await bot.add_cog(AgeVerify(bot))
