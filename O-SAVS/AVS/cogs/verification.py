import random, discord, string, asyncio, re, logging, os, json, hashlib, importlib

from typing import Optional
from datetime import datetime, timezone
from discord import app_commands, Interaction, ui, ButtonStyle
from discord.ext import commands

from settings import PRIMARY_SERVER, GLOBAL_LOG_CHANNEL_ID
import data.languages as _languages_module
from data.vrchat import get_vrchat_user
from data.database import (
    get_server_settings,
    get_vrchat_id_from_discord,
    is_vrchat_id_verified,
    add_verified_user,
    save_server_settings,
    get_all_verified_users,
    delete_server_settings,
    is_banned,
    get_maintenance_mode,
)
from data.languages import (
    LANGUAGES,
    SITE,
    DEFAULT_LANGUAGE,
    get_language,
    get_start_text,
    get_buttons,
    localize,
    get_bio_panel_text,
    get_panel_subtitle,
    get_text,
    get_notice_titles,
    describe_language,
    get_wizard_text,
    get_vrc_modal_text,
    codes_for_verify_label
)

importlib.reload(_languages_module)

PANEL_STATE_FILE = os.path.join(os.path.dirname(__file__), "..", "utils", "panel_state.json")


def generate_code(prefix: str = "AVS-") -> str:
    clean_prefix = prefix.strip() if prefix else "AVS-"
    return clean_prefix + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

def sep() -> ui.Separator:
    return ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small)

def static_layout(*items) -> ui.LayoutView:
    view = ui.LayoutView(timeout=None)
    for item in items:
        view.add_item(item)
    return view

def notice(text: str, language=None) -> ui.LayoutView:
    icon, _, body = text.partition(" ")
    body = body.strip()
    kind = {"❌": "error", "✅": "success", "⚠": "warning"}.get(icon.rstrip("️"))
    colour = {
        "error": discord.Color.red(),
        "success": discord.Color.green(),
        "warning": discord.Color.orange(),
    }.get(kind, discord.Color.blurple())
    title = get_notice_titles(language).get(kind, "Notice")

    first, _, rest = body.partition("\n")
    bold = re.fullmatch(r"\*\*(.+)\*\*", first.strip())
    if bold:
        title, body = bold.group(1), rest.strip()

    items = [ui.TextDisplay(f"# {icon} {title}")]
    if body:
        items += [sep(), ui.TextDisplay(body)]
    return static_layout(ui.Container(*items, accent_colour=colour))

def log_layout(title: str, colour: discord.Colour, fields: list) -> ui.LayoutView:
    details = "\n".join(f"**{name}:** {value}" for name, value in fields)
    return static_layout(
        ui.Container(
            ui.TextDisplay(f"# {title}"),
            ui.TextDisplay(f"-# <t:{int(discord.utils.utcnow().timestamp())}:F>"),
            sep(),
            ui.TextDisplay(details),
            accent_colour=colour
        )
    )

MAINTENANCE_NOTICE = get_text("maintenance", DEFAULT_LANGUAGE)

async def maintenance_blocked(interaction: Interaction, language: Optional[str] = None) -> bool:
    if not await get_maintenance_mode():
        return False
    if language is None and interaction.guild_id:
        language = (await get_server_settings(interaction.guild_id)).get("language")
    view = notice(get_text("maintenance", language), language)
    if interaction.response.is_done():
        await interaction.followup.send(view=view, ephemeral=True)
    else:
        await interaction.response.send_message(view=view, ephemeral=True)
    return True

def has_age_button(components) -> bool:
    for comp in components:
        if getattr(comp, "custom_id", None) == "ageverify_start":
            return True

        children = getattr(comp, "children", None)
        if children and has_age_button(children):
            return True

        accessory = getattr(comp, "accessory", None)
        if accessory is not None and has_age_button([accessory]):
            return True

    return False

class BioCheckButton(ui.Button):
    def __init__(self, bio_view: "BioCheckView", language: str = DEFAULT_LANGUAGE):
        super().__init__(label=get_buttons(language)[1], style=ButtonStyle.success)
        self.bio_view = bio_view

    async def callback(self, interaction: Interaction):
        if await maintenance_blocked(interaction, self.bio_view.language):
            return
        await self.bio_view.run_check(interaction)

class BioCheckView(ui.LayoutView):
    def __init__(self, bot: commands.Bot, cog: commands.Cog, user_id: str, code: str, settings: dict, username: str = "Unknown User"):
        super().__init__(timeout=300)
        self.bot = bot
        self.cog = cog
        self.user_id = user_id
        self.code = code
        self.settings = settings
        self.username = username
        self.language = settings.get("language") or DEFAULT_LANGUAGE

        self.build()

    def build(self):
        self.clear_items()

        title, subtitle, instruction, after = get_bio_panel_text(self.language, self.username)

        self.add_item(ui.Container(
            ui.TextDisplay(f"# 🔐 {title}"),
            ui.TextDisplay(f"-# {subtitle}"),
            sep(),
            ui.Section(
                ui.TextDisplay(instruction),
                ui.TextDisplay(f"# `{self.code}`"),
                ui.TextDisplay(after),
                accessory=BioCheckButton(self, self.language)
            ),
        ))

    async def run_check(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)

        language = self.language

        if await is_banned(interaction.user.id):
            self.stop()
            return await interaction.followup.send(view=notice(get_text("banned_discord", language), language), ephemeral=True)

        if await is_banned(self.user_id):
            self.stop()
            return await interaction.followup.send(view=notice(get_text("banned_vrchat", language), language), ephemeral=True)

        existing_vrc_id = await get_vrchat_id_from_discord(interaction.user.id)
        if existing_vrc_id:
            self.stop()
            return await interaction.followup.send(view=notice(get_text("linked_discord", language, vrc_id=existing_vrc_id), language), ephemeral=True)

        if await is_vrchat_id_verified(self.user_id):
            self.stop()
            return await interaction.followup.send(view=notice(get_text("linked_vrchat", language, vrc_id=self.user_id), language), ephemeral=True)

        user_data = await get_vrchat_user(self.user_id)

        if not user_data:
            return await interaction.followup.send(view=notice(get_text("fetch_failed", language), language), ephemeral=True)

        bio = user_data.get("bio", "") or ""

        if self.code not in bio:
            return await interaction.followup.send(view=notice(get_text("code_missing", language), language), ephemeral=True)

        if not user_data.get("verification"):
            return await interaction.followup.send(view=notice(get_text("not_age_verified", language), language), ephemeral=True)

        await add_verified_user(interaction.user.id, self.user_id)

        origin_role_added = False

        for guild in self.bot.guilds:
            member = guild.get_member(interaction.user.id)
            if not member:
                continue

            settings = await get_server_settings(guild.id)
            role_id = settings.get("verified_role")
            required_role_id = settings.get("required_role")

            if not role_id:
                continue

            if required_role_id:
                req_role = guild.get_role(required_role_id)
                if req_role and req_role not in member.roles:
                    continue

            role = guild.get_role(role_id)
            if role and role not in member.roles:
                is_origin = (guild.id == interaction.guild_id)
                
                audit_reason = (
                    "O-SAVS Automated Verification" if is_origin 
                    else "O-SAVS Auto-Role: Global Verification Sync"
                )
                
                log_reason = (
                    "Initial profile verification via code" if is_origin 
                    else "Global Verification Sync"
                )

                try:
                    await member.add_roles(role, reason=audit_reason)
                    if is_origin:
                        origin_role_added = True
                except (discord.Forbidden, discord.HTTPException) as e:
                    logging.error(f"[Verify Log Error - {guild.id}] {e}")

                try:
                    await self.cog.send_verify_log(
                        guild=guild,
                        action="User Verified",
                        member=member,
                        vrchat_id=self.user_id,
                        operator=interaction.user if is_origin else self.bot.user,
                        reason=log_reason
                    )
                except Exception as e:
                    logging.error(f"[Verify Log Error - {guild.id}] {e}")

        await self.cog.send_global_log(
            action="User Verified",
            user=interaction.user,
            vrchat_id=self.user_id,
            origin_guild=interaction.guild
        )

        self.stop()

        success_msg = get_text("verified" if origin_role_added else "linked", language, guild=interaction.guild.name)

        await interaction.followup.send(view=notice(success_msg, language), ephemeral=True)

def _iter_components(components):
    for comp in components or []:
        yield comp
        for attr in ("children", "components"):
            yield from _iter_components(getattr(comp, attr, None))
        accessory = getattr(comp, "accessory", None)
        if accessory is not None:
            yield accessory

def panel_language_from_message(interaction: Interaction, server_language: Optional[str] = None) -> Optional[str]:
    message = interaction.message
    if message is None:
        return None
    for comp in _iter_components(getattr(message, "components", None)):
        if getattr(comp, "custom_id", None) != "ageverify_start":
            continue
        matches = codes_for_verify_label(getattr(comp, "label", None))
        if not matches:
            return None
        return server_language if server_language in matches else matches[0]
    return None

class AgeVerifyButton(ui.Button):
    def __init__(self, language: str = DEFAULT_LANGUAGE, ephemeral: bool = False):
        super().__init__(label=get_buttons(language)[0], style=ButtonStyle.primary, custom_id="ageverify_start")
        self.language = language if ephemeral else None

    async def callback(self, interaction: Interaction):
        language = self.language
        if language is None:
            settings = await get_server_settings(interaction.guild_id)
            server_language = settings.get("language")
            language = panel_language_from_message(interaction, server_language) or server_language

        if await maintenance_blocked(interaction, language):
            return

        await interaction.response.send_modal(VRChatUsername(language))

def render_steps(lang) -> str:
    lines = []
    for i, step in enumerate(lang.steps, 1):
        lines.append(f"{i}. " + localize(step.replace("{site}", SITE), lang.code))
    return "\n".join(lines) + "\n\n" + lang.done

class LanguageSelect(ui.Select):
    def __init__(self, bot: commands.Bot, cog: commands.Cog, default_language: str = DEFAULT_LANGUAGE):
        super().__init__(
            placeholder="🌐 Language / Idioma / Sprache / 言語...",
            min_values=1,
            max_values=1,
            custom_id="ageverify_language",
            options=[
                discord.SelectOption(
                    label=lang.native, value=lang.code, description=describe_language(lang, default_language), emoji=lang.emoji
                )
                for lang in LANGUAGES.values()
            ],
        )
        self.bot = bot
        self.cog = cog

    async def callback(self, interaction: Interaction):
        code = self.values[0]

        # Inside a user's private copy: switch the language in place.
        if interaction.message is not None and interaction.message.flags.ephemeral:
            await interaction.response.edit_message(
                view=ConfirmCheck(self.bot, self.cog, code, ephemeral=True)
            )
            return

        settings = await get_server_settings(interaction.guild_id)
        await interaction.response.edit_message(
            view=ConfirmCheck(self.bot, self.cog, settings.get("language"))
        )
        if code in LANGUAGES:
            await interaction.followup.send(
                view=ConfirmCheck(self.bot, self.cog, code, ephemeral=True), ephemeral=True
            )

class ConfirmCheck(ui.LayoutView):
    def __init__(self, bot: commands.Bot, cog: commands.Cog, language: str = DEFAULT_LANGUAGE, ephemeral: bool = False):
        super().__init__(timeout=900 if ephemeral else None)
        self.bot = bot
        self.cog = cog

        lang = get_language(language)
        start_heading, start_text = get_start_text(lang.code)

        self.add_item(ui.Container(
            ui.TextDisplay(f"# {lang.title}"),
            ui.TextDisplay(f"-# {get_panel_subtitle(lang.code)}"),
            sep(),
            ui.TextDisplay(f"## {lang.about_heading}"),
            ui.TextDisplay(lang.about),
        ))

        items = [
            ui.Section(
                ui.TextDisplay(f"## {start_heading}"),
                ui.TextDisplay(start_text),
                accessory=AgeVerifyButton(lang.code, ephemeral)
            ),
            sep(),
            ui.TextDisplay(f"## {lang.how_heading}"),
            ui.TextDisplay(render_steps(lang)),
        ]

        if not ephemeral:
            items += [sep(), ui.ActionRow(LanguageSelect(bot, cog, lang.code))]

        self.add_item(ui.Container(*items))

class VRChatUsername(ui.Modal):
    def __init__(self, language: Optional[str] = None):
        title, label = get_vrc_modal_text(language)
        super().__init__(title=title, timeout=None)
        self.language = language
        self.userID = ui.TextInput(
            label=label,
            style=discord.TextStyle.short,
            placeholder="usr_...",
            required=True,
            max_length=128
        )
        self.add_item(self.userID)

    async def on_submit(self, modal_interaction: Interaction):
        if await maintenance_blocked(modal_interaction, self.language):
            return

        await modal_interaction.response.defer(ephemeral=True)

        settings = await get_server_settings(modal_interaction.guild_id)
        language = self.language or settings.get("language")

        required_role_id = settings.get("required_role")
        if required_role_id:
            req_role = modal_interaction.guild.get_role(required_role_id)
            if req_role and req_role not in modal_interaction.user.roles:
                return await modal_interaction.followup.send(view=notice(get_text("required_role", language, role=req_role.mention), language), ephemeral=True)

        existing_vrc_id = await get_vrchat_id_from_discord(modal_interaction.user.id)
        if existing_vrc_id:
            return await modal_interaction.followup.send(view=notice(get_text("linked_discord", language, vrc_id=existing_vrc_id), language), ephemeral=True)

        if await is_banned(modal_interaction.user.id):
            return await modal_interaction.followup.send(view=notice(get_text("banned_discord", language), language), ephemeral=True)

        user_input = self.userID.value.strip()
        match = re.search(r"usr_[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}", user_input, re.IGNORECASE)

        if not match:
            invalid_layout = static_layout(
                ui.Container(
                    ui.TextDisplay(f"# {get_text('invalid_title', language)}"),
                    sep(),
                    ui.TextDisplay(get_text("invalid_body", language, input=user_input)),
                    accent_colour=discord.Color.red()
                )
            )
            return await modal_interaction.followup.send(view=invalid_layout, ephemeral=True)

        clean_id = match.group(0)

        if await is_banned(clean_id):
            return await modal_interaction.followup.send(view=notice(get_text("banned_vrchat", language), language), ephemeral=True)

        if await is_vrchat_id_verified(clean_id):
            return await modal_interaction.followup.send(view=notice(get_text("linked_vrchat", language, vrc_id=clean_id), language), ephemeral=True)

        prefix = settings.get("av_start_code") or "AVS-"
        code = generate_code(prefix)

        user_data = await get_vrchat_user(clean_id)
        username = user_data.get("username", "Unknown User") if user_data else "Unknown User"

        cog = modal_interaction.client.get_cog("Verification")
        view_settings = {**settings, "language": self.language or settings.get("language")}
        view = BioCheckView(modal_interaction.client, cog, clean_id, code, view_settings, username)

        await modal_interaction.followup.send(view=view, ephemeral=True)

class PrefixModal(ui.Modal, title="Custom Verification Prefix"):
    prefix_input = ui.TextInput(
        label="Verification Code Prefix",
        placeholder="AVS-",
        default="AVS-",
        max_length=7,
        required=True
    )

    def __init__(self, wizard_view: "SetupWizardView"):
        super().__init__()
        self.wizard_view = wizard_view

    async def on_submit(self, interaction: Interaction):
        val = self.prefix_input.value.strip() or "AVS-"
        if not val.endswith("-"):
            val += "-"
        self.wizard_view.selected_prefix = val
        await self.wizard_view.update_wizard(interaction)

class WizardRoleSelect(ui.RoleSelect):
    def __init__(self, wizard: "SetupWizardView", step: str):
        t = get_wizard_text(wizard.selected_language)
        placeholder = (
            f"2. {t['ph_verified']}" if step == "verified"
            else f"3. {t['ph_required']}"
        )
        current = wizard.selected_role if step == "verified" else wizard.required_role
        super().__init__(
            placeholder=placeholder,
            min_values=1,
            max_values=1,
            default_values=[current] if current else []
        )
        self.wizard = wizard
        self.step = step

    async def callback(self, interaction: Interaction):
        role = self.values[0]

        if self.step == "verified":
            bot_top_role = interaction.guild.me.top_role
            if role >= bot_top_role:
                return await interaction.response.send_message(view=notice(f"❌ I cannot assign {role.mention} because it is higher than or equal to my highest role ({bot_top_role.mention})."), ephemeral=True)
            self.wizard.selected_role = role
        else:
            self.wizard.required_role = role

        await self.wizard.update_wizard(interaction)

class WizardChannelSelect(ui.ChannelSelect):
    def __init__(self, wizard: "SetupWizardView"):
        super().__init__(
            placeholder=f"4. {get_wizard_text(wizard.selected_language)['ph_channel']}",
            channel_types=[discord.ChannelType.text],
            min_values=1,
            max_values=1,
            default_values=[wizard.selected_channel] if wizard.selected_channel else []
        )
        self.wizard = wizard

    async def callback(self, interaction: Interaction):
        text_channel = interaction.guild.get_channel(self.values[0].id)

        if not isinstance(text_channel, discord.TextChannel):
            return await interaction.response.send_message(view=notice("❌ Could not resolve that text channel. Please try again."), ephemeral=True)

        self.wizard.selected_channel = text_channel
        await self.wizard.update_wizard(interaction)

class WizardLanguageSelect(ui.Select):
    def __init__(self, wizard: "SetupWizardView"):
        super().__init__(
            placeholder=f"1. {get_wizard_text(wizard.selected_language)['ph_language']}",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label=lang.native,
                    value=lang.code,
                    description=describe_language(lang, wizard.selected_language),
                    emoji=lang.emoji,
                    default=(lang.code == wizard.selected_language),
                )
                for lang in LANGUAGES.values()
            ],
        )
        self.wizard = wizard

    async def callback(self, interaction: Interaction):
        self.wizard.selected_language = self.values[0]
        await self.wizard.update_wizard(interaction)

class ClearPreRoleButton(ui.Button):
    def __init__(self, wizard: "SetupWizardView"):
        super().__init__(label=get_wizard_text(wizard.selected_language)["btn_clear"], style=ButtonStyle.secondary)
        self.wizard = wizard

    async def callback(self, interaction: Interaction):
        self.wizard.required_role = None
        await self.wizard.update_wizard(interaction)

class SetPrefixButton(ui.Button):
    def __init__(self, wizard: "SetupWizardView"):
        super().__init__(label=get_wizard_text(wizard.selected_language)["btn_prefix"], style=ButtonStyle.secondary)
        self.wizard = wizard

    async def callback(self, interaction: Interaction):
        await interaction.response.send_modal(PrefixModal(self.wizard))

class FinishSetupButton(ui.Button):
    def __init__(self, wizard: "SetupWizardView"):
        super().__init__(label=get_wizard_text(wizard.selected_language)["btn_finish"], style=ButtonStyle.success, disabled=not wizard.is_ready())
        self.wizard = wizard

    async def callback(self, interaction: Interaction):
        await self.wizard.finish_setup(interaction)

class SetupWizardView(ui.LayoutView):
    def __init__(self, bot: commands.Bot, cog: commands.Cog, author: discord.Member, log_channel: discord.TextChannel, language: str = DEFAULT_LANGUAGE):
        super().__init__(timeout=300)
        self.bot = bot
        self.cog = cog
        self.author = author
        self.log_channel = log_channel

        self.selected_role: Optional[discord.Role] = None
        self.required_role: Optional[discord.Role] = None
        self.selected_channel: Optional[discord.TextChannel] = None
        self.selected_prefix: str = "AVS-"
        self.selected_language: str = language if language in LANGUAGES else DEFAULT_LANGUAGE

        self.build()

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(view=notice("❌ Only the command invoker can control this wizard."), ephemeral=True)
            return False
        return True

    def is_ready(self) -> bool:
        return bool(self.selected_role and self.selected_channel)

    def build(self):
        self.clear_items()

        t = get_wizard_text(self.selected_language)
        role_str = self.selected_role.mention if self.selected_role else f"❌ *{t['not_selected']}*"
        req_role_str = self.required_role.mention if self.required_role else f"🔹 *{t['none_optional']}*"
        channel_str = self.selected_channel.mention if self.selected_channel else f"❌ *{t['not_selected']}*"
        language_obj = get_language(self.selected_language)
        language_str = f"{language_obj.emoji} {language_obj.native}"

        footer = t["footer_ready"] if self.is_ready() else t["footer_not_ready"]

        self.add_item(ui.Container(
            ui.TextDisplay(f"# ⚙️ O-SAVS {t['title']}"),
            ui.TextDisplay(f"-# {t['subtitle']}"),
            sep(),
            ui.TextDisplay(
                f"{t['intro']}\n\n"
                f"**{t['log_created']}:** {self.log_channel.mention}"
            ),
        ))

        self.add_item(ui.Container(
            ui.TextDisplay(f"### 1. {t['h_language']}\n{language_str}"),
            ui.ActionRow(WizardLanguageSelect(self)),
            sep(),
            ui.TextDisplay(f"### 2. {t['h_verified']}\n{role_str}"),
            ui.ActionRow(WizardRoleSelect(self, "verified")),
            sep(),
            ui.Section(
                ui.TextDisplay(f"### 3. {t['h_required']}\n{req_role_str}"),
                accessory=ClearPreRoleButton(self)
            ),
            ui.ActionRow(WizardRoleSelect(self, "required")),
            sep(),
            ui.TextDisplay(f"### 4. {t['h_channel']}\n{channel_str}"),
            ui.ActionRow(WizardChannelSelect(self)),
            sep(),
            ui.Section(
                ui.TextDisplay(f"### 5. {t['h_prefix']}\n`{self.selected_prefix}`"),
                accessory=SetPrefixButton(self)
            ),
        ))

        self.add_item(ui.Container(
            ui.Section(
                ui.TextDisplay(f"### {t['finish']}\n{footer}"),
                accessory=FinishSetupButton(self)
            ),
        ))

    async def update_wizard(self, interaction: Interaction):
        self.build()
        await interaction.response.edit_message(view=self, allowed_mentions=discord.AllowedMentions.none())

    async def finish_setup(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        verified_role = self.selected_role
        required_role = self.required_role
        verify_channel = self.selected_channel
        prefix = self.selected_prefix
        language = self.selected_language
        language_obj = get_language(language)
        language_label = f"{language_obj.emoji} {language_obj.native}"
        target_log_channel = self.log_channel

        await save_server_settings(
            guild_id=guild.id,
            verified_role=verified_role.id,
            verify_channel=verify_channel.id,
            verification_logs=target_log_channel.id,
            av_start_code=prefix,
            required_role=required_role.id if required_role else None,
            language=language
        )

        thank_you_layout = static_layout(
            ui.Container(
                ui.TextDisplay("# Thank you for using O-SAVS!"),
                ui.TextDisplay("-# CONFIGURATION UPDATED"),
                sep(),
                ui.TextDisplay(
                    "O-SAVS (Open-Source Age Verification System) configuration has been updated for this server."
                ),
                ui.TextDisplay(
                    f"**Verified Role:** {verified_role.mention}\n"
                    f"**Required Pre-Role:** {required_role.mention if required_role else 'None'}\n"
                    f"**Verify Channel:** {verify_channel.mention}\n"
                    f"**Verification Logs:** {target_log_channel.mention}\n"
                    f"**Code Prefix:** `{prefix}`\n"
                    f"**Server Language:** {language_label}"
                ),
                sep(),
                ui.TextDisplay(
                    "Noodle would personally like to thank you for using O-SAVS, we hope you enjoy the system and if you have any issues and or suggestions feel free to reach out in [Noodle's Nexus](https://discord.gg/PeXzxBeUcB)!"
                ),
                ui.TextDisplay(f"-# <t:{int(datetime.now(timezone.utc).timestamp())}:F>"),
            )
        )
        try:
            await target_log_channel.send(view=thank_you_layout, allowed_mentions=discord.AllowedMentions.none())
        except discord.Forbidden as e:
            logging.error(f"[Setup Log Error - {guild.id}] {e}")

        try:
            await verify_channel.send(view=ConfirmCheck(self.bot, self.cog, language))
        except discord.Forbidden:
            return await interaction.followup.send(view=notice(f"⚠️ Settings saved, but lacked permissions to send panel in {verify_channel.mention}."), ephemeral=True)

        all_verified = await get_all_verified_users()
        synced_count = 0

        for discord_id, vrchat_id in all_verified:
            member = guild.get_member(discord_id)
            if member and verified_role not in member.roles:
                if required_role and required_role not in member.roles:
                    continue

                try:
                    await member.add_roles(verified_role, reason="O-SAVS setup: Syncing global verification")
                    synced_count += 1
                    await self.cog.send_verify_log(
                        guild=guild,
                        action="User Verified",
                        member=member,
                        vrchat_id=vrchat_id,
                        operator=interaction.user,
                        reason="O-SAVS setup: Syncing existing global verification"
                    )
                    await asyncio.sleep(0.5)
                except discord.Forbidden as e:
                    logging.error(f"[Setup Log Error - {guild.id}] {e}")

        self.stop()

        final_layout = static_layout(
            ui.Container(
                ui.TextDisplay("# ✅ Setup Complete!"),
                ui.TextDisplay("-# O-SAVS CONFIGURATION"),
                sep(),
                ui.TextDisplay(f"O-SAVS is now active in **{guild.name}**!"),
                ui.TextDisplay(
                    f"- **Log Channel:** {target_log_channel.mention}\n"
                    f"- **Panel Channel:** {verify_channel.mention}\n"
                    f"- **Verified Role:** {verified_role.mention}\n"
                    f"- **Required Pre-Role:** {required_role.mention if required_role else 'None'}\n"
                    f"- **Code Prefix:** `{prefix}`\n"
                    f"- **Server Language:** {language_label}\n"
                    f"- **Synced Users:** `{synced_count}`"
                ),
                accent_colour=discord.Colour.green()
            )
        )

        await interaction.message.edit(view=final_layout, allowed_mentions=discord.AllowedMentions.none())
        await interaction.followup.send(view=notice("✅ Server setup completed successfully!"), ephemeral=True)

class Verification(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._has_synced = False
        self._panel_view = ConfirmCheck(bot, self)
        self.bot.add_view(self._panel_view)

    async def send_global_log(self, action: str, user: discord.User | discord.Member, vrchat_id: str, origin_guild: Optional[discord.Guild] = None, reason: Optional[str] = None):
        if not GLOBAL_LOG_CHANNEL_ID or self.bot.get_guild(PRIMARY_SERVER) is None:
            return

        channel = self.bot.get_channel(GLOBAL_LOG_CHANNEL_ID)
        if not channel:
            try:
                channel = await self.bot.fetch_channel(GLOBAL_LOG_CHANNEL_ID)
            except (discord.NotFound, discord.HTTPException) as e:
                logging.error(f"[Global Log Error] {e}")
                return

        if not isinstance(channel, discord.TextChannel) or channel.guild.id != PRIMARY_SERVER:
            return

        vrc_user = await get_vrchat_user(vrchat_id)
        username = vrc_user.get("username", "Unknown User") if vrc_user else "Unknown User"

        fields = [
            ("Discord User", f"{user.mention} (`{user.id}`)"),
            ("VRChat Profile", f"[{username}](https://vrchat.com/home/user/{vrchat_id}) (`{vrchat_id}`)"),
        ]

        if origin_guild:
            fields.append(("Origin Server", f"**{origin_guild.name}** (`{origin_guild.id}`)"))
        else:
            fields.append(("Origin Server", "*Global Event / System Sync*"))

        if reason:
            fields.append(("Reason", reason))

        try:
            await channel.send(
                view=log_layout(f"🌐 Global Audit: {action}", discord.Color.purple(), fields),
                allowed_mentions=discord.AllowedMentions.none()
            )
        except (discord.Forbidden, discord.HTTPException) as e:
            logging.error(f"[Global Log Error] {e}")

    async def cog_load(self):
        if self.bot.is_ready() and not self._has_synced:
            self._has_synced = True

            if not getattr(self.bot, "_startup_sync_done", False):
                self.bot._startup_sync_done = True
                self.bot.loop.create_task(self.sync_offline_verifications())

            self.bot.loop.create_task(self.refresh_panels())

    def cog_unload(self):
        try:
            self.bot.remove_view(self._panel_view)
        except Exception as e:
            logging.warning(f"[Verification] Could not remove persistent panel view on unload: {e}")

        try:
            store = self.bot._connection._view_store
            seen = set()
            for entry in list(store._views.values()):
                view = entry[0] if isinstance(entry, tuple) else entry
                if id(view) in seen:
                    continue
                seen.add(id(view))
                if type(view).__module__ == __name__:
                    view.stop()
        except Exception as e:
            logging.warning(f"[Verification] Could not stop old message views on unload: {e}")

    def load_panel_hash(self) -> Optional[str]:
        try:
            with open(PANEL_STATE_FILE, "r") as f:
                return json.load(f).get("panel_hash")
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def save_panel_hash(self, value: str):
        try:
            with open(PANEL_STATE_FILE, "w") as f:
                json.dump({"panel_hash": value}, f)
        except OSError as e:
            logging.error(f"[Panel Refresh Error] Could not save panel state: {e}")

    async def find_panel_message(self, channel: discord.TextChannel) -> Optional[discord.Message]:
        async for message in channel.history(limit=100):
            if message.author.id == self.bot.user.id and has_age_button(message.components):
                return message
        return None

    async def refresh_panels(self):
        await self.bot.wait_until_ready()

        new_hash = hashlib.sha256(
            json.dumps(
                {code: ConfirmCheck(self.bot, self, code).to_components() for code in LANGUAGES},
                sort_keys=True,
            ).encode()
        ).hexdigest()

        if self.load_panel_hash() == new_hash:
            logging.info("[Panel Refresh Log] Panel layout unchanged, nothing to update")
            return

        logging.info("[Panel Refresh Log] Panel layout changed, updating verification panels")

        updated_count = 0
        error_count = 0

        for guild in self.bot.guilds:
            settings = await get_server_settings(guild.id)
            channel_id = settings.get("verify_channel")
            if not channel_id:
                continue

            channel = guild.get_channel(channel_id)
            if not isinstance(channel, discord.TextChannel):
                continue

            try:
                message = await self.find_panel_message(channel)
                if message is None:
                    continue

                if getattr(message.flags, "components_v2", False):
                    try:
                        await message.edit(view=ConfirmCheck(self.bot, self, settings.get("language")))
                    except (discord.HTTPException, TypeError):
                        await channel.send(view=ConfirmCheck(self.bot, self, settings.get("language")))
                        await message.delete()
                else:
                    await channel.send(view=ConfirmCheck(self.bot, self, settings.get("language")))
                    await message.delete()

                updated_count += 1
                await asyncio.sleep(1)
            except (discord.Forbidden, discord.HTTPException) as e:
                logging.error(f"[Panel Refresh Error - {guild.id}] {e}")
                error_count += 1

        if error_count == 0:
            self.save_panel_hash(new_hash)

        logging.info(f"[Panel Refresh Log] Complete! Updated {updated_count} panel(s). Errors: {error_count}")

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

        fields = [
            ("User", f"{member.mention} (`{member.id}`)"),
            ("VRChat Account", f"[{username}](https://vrchat.com/home/user/{vrchat_id}) (`{vrchat_id}`)"),
            ("Operator", f"{active_operator.mention} (`{active_operator.id}`)"),
        ]

        if reason:
            fields.append(("Reason", reason))

        log_colour = discord.Color.blue() if "Link" in action or "Verified" in action else discord.Color.orange()

        max_retries = 3
        for attempt in range(max_retries):
            try:
                await log_channel.send(
                    view=log_layout(f"🛡️ {action}", log_colour, fields),
                    allowed_mentions=discord.AllowedMentions.none()
                )
                await asyncio.sleep(0.5)
                break
            except discord.Forbidden as e:
                logging.error(f"[Dispatch Log Error - {guild.id}] {e}")
                break
            except discord.HTTPException as e:
                if e.status == 429:
                    retry_after = getattr(e, "retry_after", 1)
                    logging.warning(f"[Dispatch Log Rate Limited - {guild.id}] Retrying in {retry_after}s: {e}")
                    await asyncio.sleep(retry_after)
                else:
                    logging.error(f"[Dispatch Log Error - {guild.id}] {e}")
                    break
            except Exception as e:
                logging.error(f"[Dispatch Log Error - {guild.id}] {e}")
                break

    @app_commands.command(name="setup", description="Interactive setup wizard for configuring O-SAVS in your server")
    @app_commands.default_permissions(administrator=True)
    async def setup_cmd(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild

        if not guild.me.guild_permissions.manage_roles or not guild.me.guild_permissions.manage_channels:
            return await interaction.followup.send(view=notice("❌ I do not have the **Manage Roles** or **Manage Channels** permissions in this server."), ephemeral=True)

        log_overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False, send_messages=False, view_channel=False),
            guild.me: discord.PermissionOverwrite(
                read_messages=True,
                send_messages=True,
                embed_links=True,
                attach_files=True,
                view_channel=True
            )
        }

        existing_settings = await get_server_settings(guild.id)
        saved_log_id = existing_settings.get("verification_logs")
        target_log_channel = guild.get_channel(saved_log_id) if saved_log_id else None

        if not isinstance(target_log_channel, discord.TextChannel):
            target_log_channel = discord.utils.get(guild.text_channels, name="verification-logs")

        if target_log_channel:
            try:
                updated_overwrites = target_log_channel.overwrites
                updated_overwrites.update(log_overwrites)
                
                await target_log_channel.edit(
                    overwrites=updated_overwrites,
                    reason="O-SAVS setup: Enforcing strict admin log access"
                )
            except discord.Forbidden:
                return await interaction.followup.send(view=notice(f"⚠️ Found existing {target_log_channel.mention}, but lacked permissions to update access overrides."), ephemeral=True)
        else:
            try:
                target_log_channel = await guild.create_text_channel(
                    name="verification-logs",
                    overwrites=log_overwrites,
                    reason="O-SAVS setup: Dedicated verification log channel created"
                )
            except discord.Forbidden:
                return await interaction.followup.send(view=notice("❌ Missing permissions to create `#verification-logs`. Check my role permissions and try again."), ephemeral=True)

        wizard_view = SetupWizardView(
            self.bot, self, interaction.user, target_log_channel,
            language=existing_settings.get("language") or DEFAULT_LANGUAGE
        )

        try:
            wizard_msg = await target_log_channel.send(view=wizard_view, allowed_mentions=discord.AllowedMentions.none())
            await interaction.followup.send(view=notice(f"✅ {target_log_channel.mention} configured! Please continue setup in {target_log_channel.mention}: {wizard_msg.jump_url}"), ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send(view=notice(f"❌ Configured {target_log_channel.mention}, but lacked permission to send messages in it."), ephemeral=True)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        try:
            removed = await delete_server_settings(guild.id)
            if removed:
                logging.info(f"[Guild Remove Log - {guild.id}] Removed settings for {guild.name}")
            else:
                logging.info(f"[Guild Remove Log - {guild.id}] No settings record found to delete for {guild.name}")
        except Exception as e:
            logging.error(f"[Guild Remove Log Error - {guild.id}] {e}")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return

        vrchat_id = await get_vrchat_id_from_discord(member.id)
        if not vrchat_id:
            return

        settings = await get_server_settings(member.guild.id)
        role_id = settings.get("verified_role")
        required_role_id = settings.get("required_role")

        if not role_id:
            return

        if required_role_id:
            req_role = member.guild.get_role(required_role_id)
            if req_role and req_role not in member.roles:
                return

        role = member.guild.get_role(role_id)
        if not role or role in member.roles:
            return

        try:
            await member.add_roles(role, reason="O-SAVS Auto-Role: Existing global verification")
        except (discord.Forbidden, discord.HTTPException) as e:
            logging.error(f"[Member Join Log Error - {member.guild.id}] {e}")
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

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if after.bot:
            return

        added_roles = set(after.roles) - set(before.roles)
        if not added_roles:
            return

        settings = await get_server_settings(after.guild.id)
        required_role_id = settings.get("required_role")
        verified_role_id = settings.get("verified_role")

        if not required_role_id or not verified_role_id:
            return

        if any(r.id == required_role_id for r in added_roles):
            vrchat_id = await get_vrchat_id_from_discord(after.id)
            if not vrchat_id or await is_banned(after.id):
                return

            verified_role = after.guild.get_role(verified_role_id)
            if not verified_role or verified_role in after.roles:
                return

            try:
                await after.add_roles(verified_role, reason="O-SAVS Auto-Role: Required role acquired")

                await self.send_verify_log(
                    guild=after.guild,
                    action="User Verified",
                    member=after,
                    vrchat_id=vrchat_id,
                    operator=self.bot.user,
                    reason="Acquired Required Role (Global Verification)"
                )
            except (discord.Forbidden, discord.HTTPException) as e:
                logging.error(f"[Member Update Log Error - {after.guild.id}] {e}")

    async def sync_offline_verifications(self):
        await self.bot.wait_until_ready()
        logging.info("[Startup Sync Log] Starting startup verification role sync")

        all_verified = await get_all_verified_users()
        if not all_verified:
            logging.info("[Startup Sync Log] No verified users found in database")
            return

        verified_map = {discord_id: vrchat_id for discord_id, vrchat_id in all_verified}
        synced_count = 0
        error_count = 0

        for guild in self.bot.guilds:
            settings = await get_server_settings(guild.id)
            role_id = settings.get("verified_role")
            required_role_id = settings.get("required_role")

            if not role_id:
                continue

            role = guild.get_role(role_id)
            req_role = guild.get_role(required_role_id) if required_role_id else None
            bot_member = guild.me
            
            if not role or not bot_member.guild_permissions.manage_roles or role >= bot_member.top_role:
                continue

            for member in guild.members:
                if req_role and req_role not in member.roles:
                    continue

                if member.id in verified_map and role not in member.roles:
                    if await is_banned(member.id):
                        continue

                    try:
                        await member.add_roles(role, reason="O-SAVS Startup Sync: Granting role to verified user")
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
                    except (discord.Forbidden, discord.HTTPException) as e:
                        logging.warning(f"[Startup Sync Log Error - {guild.id}] {e}")
                        error_count += 1

        logging.info(f"[Startup Sync Log] Complete! Granted roles to {synced_count} member(s). Errors: {error_count}")

async def setup(bot: commands.Bot):
    await bot.add_cog(Verification(bot))
