<div align="center">
  <img src="https://github.com/ForgottenAvali/O-SAVS_Assets/blob/main/Banners/OSAVSBanner.png?raw=true" alt="O-SAVS Banner" width="100%" />

  <br />
  <br />

  [![Invite Bot](https://img.shields.io/badge/Invite-O--SAVS-24292F?style=for-the-badge&logo=discord&logoColor=white)](https://discord.com/oauth2/authorize?client_id=1516450694109073439)
  [![Discord](https://img.shields.io/badge/Join-Noodle's%20Nexus-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/PeXzxBeUcB)
  [![Ko-fi](https://img.shields.io/badge/Ko--fi-Support%20Me-F16061?style=for-the-badge&logo=ko-fi&logoColor=white)](https://ko-fi.com/forgottenavali)

  ![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)
  ![discord.py](https://img.shields.io/pypi/v/discord.py?style=flat-square&label=discord.py&color=5865F2)
  ![vrchatapi](https://img.shields.io/pypi/v/vrchatapi?style=flat-square&label=vrchatapi&color=1F9D8B)
</div>

<br />

<div align="center">

O-SAVS (Open-Source Age Verification System) is a global Discord age-verification bot designed to integrate seamlessly with VRChat profiles. It allows server administrators to restrict adult spaces by ensuring members have verified their 18+ status on VRChat. Once a user is verified in one server running O-SAVS, their status automatically syncs across all mutual servers operating the bot.

**Quick Links**<br />
[Features](#features) · [Admin Dashboard](#admin-dashboard) · [Maintenance Mode](#maintenance-mode) · [Self-Hosted Administration](#self-hosted-administration) · [Database](#database-architecture) · [Installation](#installation--host-setup) · [Team](#community--team) · [Legal](#legal--policies)

</div>

---

## Table of Contents

1. [How It Works](#how-it-works)
2. [Features](#features)
3. [Admin Dashboard](#admin-dashboard)
4. [Maintenance Mode](#maintenance-mode)
5. [Self-Hosted Administration](#self-hosted-administration)
6. [Database Architecture](#database-architecture)
7. [Installation & Host Setup](#installation--host-setup)
8. [Community & Team](#community--team)
9. [Legal & Policies](#legal--policies)

---

## How It Works

1. **Request.** A member selects **Age Verify** on a server's verification panel and submits their VRChat account profile link or raw User ID (`usr_...`). The bot issues a unique verification code.
2. **Placement.** The member places the generated verification code in their VRChat bio.
3. **Confirmation.** The bot checks the member's VRChat public profile to confirm account ownership and verifies that the account holds official VRChat 18+ age verification status.
4. **Assignment & Sync.** Upon verification, the verified role is assigned in the current server and automatically synced across all mutual servers running O-SAVS.
5. **Localization.** Users can select their preferred language from the dropdown menu on the verification panel to complete the process in any of the 40 supported languages.

---

## Features

- **Global Verification Sync.** Verify once and be synced automatically across all participating Discord servers.
- **VRChat Profile Integration.** Generates custom verification codes for users to place in their VRChat bio or status to prove account ownership.
- **Automated Guild Setup.** The `/setup` slash command configures roles, log channels, and code prefixes.
- **Role Hierarchy Safety.** Built-in checks prevent configuration failures when managing role assignments.
- **Auto-Syncing.** Automatically assigns verified roles to existing or joining members who are already in the global database.
- **Panel Updates.** On startup and after every maintenance exit, verification panels are checked and refreshed automatically if their layout has changed.
- **Maintenance Mode.** Pauses new verifications without taking the bot offline. See [Maintenance Mode](#maintenance-mode).
- **Auto-Cleanup.** Purges a server's configuration from the O-SAVS database upon bot removal. Discord roles, channels, and member verifications are left intact.
- **Admin Dashboard.** A standalone desktop application used by O-SAVS Administration to manage the bot. See [Admin Dashboard](#admin-dashboard).
- **Self-Hosted Admin Commands.** Slash-command administration for self-hosters, restricted to a configurable list of user IDs. See [Self-Hosted Administration](#self-hosted-administration).

---

## Admin Dashboard

O-SAVS Administration manages the bot through a standalone desktop application rather than in-server commands. It communicates with the bot over an authenticated internal HTTP API.

- **Account Management.** Link and unlink Discord–VRChat accounts, and globally ban or unban Discord and VRChat IDs. A dedicated list view separates linked users from banned users.
- **Server Management.** View every server the bot is in, ban or unban entire servers, and request temporary, single-use support invites for auditing purposes. Banned servers are left immediately, and the bot leaves again if re-added.
- **Server Removal.** Remove the bot from a server on demand. This action requires the administrator's personal authorization code and a stated reason.
- **Maintenance Control.** Enter or exit [Maintenance Mode](#maintenance-mode) from the sidebar. This action requires the administrator's personal authorization code.
- **Audit Logging.** Every administrative action taken through the dashboard is recorded and searchable.
- **Restricted Access.** Access is limited to authorized administrators through a credentialed login, cross-checked against an internal allow-list of authorized Discord IDs. Failed login attempts are rate-limited.
- **Session Security.** Saved sessions are stored in the operating system's secure credential store and expire automatically.
- **Updates.** The application checks for new releases and displays release notes for each version.

> **Authorization codes** are assigned per account by the owner and are required for the most sensitive actions: removing the bot from a server and toggling maintenance mode.

---

## Maintenance Mode

Maintenance Mode allows administrators to work on the bot remotely without shutting it down. Global verification data, bans, and links remain fully intact while it is active.

- **Entering.** The bot's presence changes to offline (invisible). The bot process, API, and database remain running.
- **While Active.** Selecting **Age Verify** displays an "Under Maintenance" notice instead of the verification form. Members who were already mid-verification are also stopped at submission.
- **Exiting.** The verification cog is reloaded without restarting the bot, so updated code is applied immediately. Verification panels are then checked and refreshed if they changed, and the bot's status returns to normal.
- **Failure Handling.** If the verification cog fails to reload (for example, because of a code error), maintenance mode remains active and the error is reported. The bot never returns to service on broken code.
- **Persistence.** The maintenance state is stored in the database and survives a bot restart.

Maintenance Mode can be toggled in two ways:

- **Admin Dashboard.** Available to O-SAVS Administration and protected by the administrator's personal authorization code.
- **`/admin maintenance`.** Available on self-hosted installations and restricted to the user IDs listed in `ADMIN_USER_IDS`.

---

## Self-Hosted Administration

The bot loads **one** administration cog at startup, in the following order of priority:

1. **`cogs/admin_api.py`** enables the authenticated HTTP API used by the Admin Dashboard.
2. **`cogs/admin_commands.py`** enables `/admin` slash commands, restricted to the user IDs listed in `ADMIN_USER_IDS`.
3. **Neither present.** The bot runs normally without administration tools.

> **Not running the dashboard app?** The Admin Dashboard is only used by O-SAVS Administration. If you are self-hosting, delete `admin_api.py`, `admin_app_db.py`, and `admin_update.py` from the `cogs` folder. The bot will automatically fall back to the slash commands below. Keep `admin_core.py`, which both options depend on. To run with no administration tools at all, also delete `admin_commands.py`.

### Slash Commands

Commands are registered under `/admin` in the server set as `PRIMARY_SERVER`, and may only be used by the user IDs listed in `ADMIN_USER_IDS` in `settings.py`.

- `/admin link <user> <vrchat_id> [reason]` globally links a Discord user to a VRChat account.
- `/admin unlink <user> [reason]` globally unlinks a Discord user.
- `/admin ban <target> <reason>` globally bans a Discord ID or VRChat ID from verifying.
- `/admin unban <target> <reason>` removes a global ban.
- `/admin bancheck <target>` checks whether a Discord ID or VRChat ID is banned.
- `/admin servers` lists the servers the bot is in.
- `/admin invite <server_id>` sends you a one-hour, single-use invite to a server.
- `/admin leave <server_id> <reason>` removes the bot from a server.
- `/admin serverban <server_id> <reason>` bans a server and leaves it.
- `/admin serverunban <server_id> <reason>` unbans a server.
- `/admin maintenance <on|off>` enables or disables [Maintenance Mode](#maintenance-mode).

> Access to these commands is controlled solely by `ADMIN_USER_IDS`. Keep the list limited to people you fully trust.

---

## Database Architecture

### Bot Database

- **`server_settings`** stores per-guild configuration. Primary key: `server_id`. Fields: `verified_role`, `verify_channel`, `verification_logs`, `av_start_code`, `required_role`.
- **`verified_users`** maps Discord accounts to VRChat accounts. Primary key: `discord_id`. Fields: `vrchat_id` (unique).
- **`banned_users`** holds global user ban records. Primary key: `target_id`, which may be either a Discord ID or a VRChat User ID. Fields: `reason`, `moderator_id`, `timestamp`.
- **`banned_servers`** holds banned server records. The bot automatically leaves any server listed here. Primary key: `server_id`. Fields: `reason`, `moderator_id`, `timestamp`.
- **`bot_state`** stores persistent runtime state, such as the maintenance mode flag. Primary key: `key`. Fields: `value`.

### Admin Database

Used only when the Admin Dashboard API (`admin_api.py`) is installed.

- **`admin_accounts`** stores dashboard administrator credentials. Passwords and authorization codes are stored as salted hashes. Primary key: `username`. Fields: `password_hash`, `salt`, `discord_id`, `auth_code_hash`, `auth_code_salt`.
- **`action_log`** is the audit trail of administrative actions. Primary key: `id`. Fields: `timestamp`, `actor_username`, `action`, `target`, `reason`, `result_summary`.

---

## Installation & Host Setup

### Prerequisites & Permissions

- **Python** 3.10 or higher.
- **Discord Application** with a bot token and the **Server Members Intent** (`GatewayIntent.members`) enabled in the [Discord Developer Portal](https://discord.com/developers/applications).
- **Bot Permissions** in each server the bot is added to:
  - **Manage Roles** (`manage_roles`): Required to assign and remove verified roles across members.
  - **Manage Channels** (`manage_channels`): Required during `/setup` to create and configure the `#verification-logs` channel with strict overrides.
  - **Send Messages & View Channels**: Required to send panels, interact with users, and post logs.
  - **Embed Links & Attach Files**: Required to render styled UI layouts and status notices.
- **VRChat Account** that the bot uses to read public profiles. A dedicated account is recommended.

> **Role Hierarchy Safety:** The bot's top role in your Discord server must be positioned **higher** than the verified role and required pre-roles it is configured to manage.

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Create a `.env` file in the project root.

Required:

- `BOT_TOKEN`: Discord bot token.
- `VRC_USER`: VRChat account username.
- `VRC_PASS`: VRChat account password.
- `CONTACT`: Contact information included in the user agent sent to the VRChat API.

Admin Dashboard only:

- `ADMIN_API_HOST`: Address the admin API listens on.
- `ADMIN_API_PORT`: Port the admin API listens on.
- `GITHUB_TOKEN`: Token used to check for and download dashboard updates.
- `GITHUB_REPO`: Repository the dashboard updates are published to.

### 3. Configure `settings.py`

- `PRIMARY_SERVER`: ID of your main server. The `/admin` commands are registered here, and it is excluded from the public server count.
- `GLOBAL_LOG_CHANNEL_ID`: ID of the channel in the primary server where global verification events are logged.
- `BOT_ID`: The bot's own user ID. It is excluded from the verified-user count.
- `ADMIN_USER_IDS`: List of Discord user IDs allowed to use the `/admin` slash commands.

### 4. Start the Bot

```bash
python bot.py
```

On first launch, VRChat may request a two-factor code in the console. Once entered, the session is saved and reused on later launches.

---

## Community & Team

- [Meet the O-SAVS Team](TEAM.md): contact info and roles for development, administration, and support staff.
- [O-SAVS Partners](PARTNERS.md): affiliated communities, VRChat groups, and partner organizations.

---

## Legal & Policies

- [Privacy Policy](PRIVACY.md): details on data collection, storage, and retention.
- [Terms of Service](TERMS.md): usage rules, server admin responsibilities, and guidelines.
- [License](LICENSE.md): PolyForm Noncommercial License 1.0.0.

You are free to use, modify, and host this bot for non-commercial community use. Commercial hosting, selling, or monetization of this software is strictly prohibited.

The bot is hosted 24/7 by ForgottenAvali and can be added to your server for free in [Noodle's Nexus](https://discord.gg/PeXzxBeUcB) or through the `INVITE O-SAVS` button above.

---

<div align="center">
  <sub>O-SAVS · Maintained by <a href="https://ko-fi.com/forgottenavali">ForgottenAvali</a> · Licensed under PolyForm Noncommercial 1.0.0</sub>
</div>
