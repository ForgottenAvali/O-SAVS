<div align="center">
  <img src="https://github.com/ForgottenAvali/O-SAVS_Assets/blob/main/Banners/OSAVSBanner.png?raw=true" alt="O-SAVS Banner" width="100%" />

  <br />
  <br />

  [![Invite Bot](https://img.shields.io/badge/Invite-O--SAVS-24292F?style=for-the-badge&logo=discord&logoColor=white)](https://discord.com/oauth2/authorize?client_id=1516450694109073439)
  [![Discord](https://img.shields.io/badge/Join-Noodle's%20Nexus-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/PeXzxBeUcB)
  [![Ko-fi](https://img.shields.io/badge/Ko--fi-Support%20Me-F16061?style=for-the-badge&logo=ko-fi&logoColor=white)](https://ko-fi.com/forgottenavali)

  ![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)
  ![discord.py](https://img.shields.io/badge/discord.py-2.7.1-5865F2?style=flat-square)
  ![vrchatapi](https://img.shields.io/pypi/v/vrchatapi?style=flat-square&label=vrchatapi&color=1F9D8B)
</div>

<br />

<div align="center">

O-SAVS is a global Discord age-verification bot designed to integrate seamlessly with VRChat profiles. It allows server administrators to restrict adult spaces by ensuring members have verified their 18+ status on VRChat. Once a user is verified in one server running O-SAVS, their status automatically syncs across all mutual servers operating the bot.

**Quick Links**<br />
[Features](#features) · [Admin Dashboard](#admin-dashboard) · [Database](#database-architecture) · [Installation](#installation--host-setup) · [Team](#community--team) · [Legal](#legal--policies)

</div>

---

## Table of Contents

1. [How It Works](#how-it-works)
2. [Features](#features)
3. [Admin Dashboard](#admin-dashboard)
4. [Database Architecture](#database-architecture)
5. [Installation & Host Setup](#installation--host-setup)
6. [Community & Team](#community--team)
7. [Legal & Policies](#legal--policies)

---

## How It Works

| Step | Description |
| :--: | :---------- |
| **1** | A member requests a verification code from the bot. |
| **2** | The member places the generated code in their VRChat bio or status. |
| **3** | The bot confirms account ownership and links their Discord and VRChat accounts. |
| **4** | The verified role is assigned and synced across every participating server. |

---

## Features

| Feature | Description |
| :------ | :---------- |
| **Global Verification Sync** | Verify once, get synced automatically across all participating Discord servers. |
| **VRChat Profile Integration** | Generates custom verification codes for users to place in their VRChat bio or status to verify account ownership. |
| **Automated Guild Setup** | `/setup` slash command to configure roles, log channels, and code prefixes. |
| **Role Hierarchy Safety** | Built-in checks to prevent configuration failures when managing role assignments. |
| **Auto-Syncing** | Automatically assigns verified roles to existing or joining members who are already in the global database. |
| **Auto-Cleanup** | Automatically purges server configuration settings from the O-SAVS database upon bot removal (leaves all Discord roles, channels, and member verifications intact). |
| **Admin Dashboard** | A standalone desktop application used by O-SAVS Administration to manage the bot (see [below](#admin-dashboard)). |

---

## Admin Dashboard

O-SAVS Administration manages the bot through a standalone desktop application rather than in-server commands. It communicates with the bot over an authenticated internal HTTP API.

| Area | Description |
| :--- | :---------- |
| **Account Management** | Link and unlink Discord-VRChat accounts, and globally ban or unban Discord and VRChat IDs. |
| **Server Management** | Ban or unban entire servers (the bot automatically leaves banned servers, and leaves again if re-added) and request temporary, single-use support invites for auditing purposes. |
| **Audit Logging** | Every administrative action taken through the dashboard is recorded and searchable. |
| **Restricted Access** | Access is limited to authorized administrators through a credentialed login, cross-checked against an internal allow-list of authorized Discord IDs. |

> **Not running the dashboard app?** The Admin Dashboard is only used by O-SAVS Administration. If you're self-hosting and don't have the desktop app, you can delete the admin files in the `cogs` folder (such as `admin_api.py`) and the bot will start and run normally without them.

---

## Database Architecture

| Table | Purpose | Fields |
| :---- | :------ | :----- |
| `server_settings` | Guild configuration | `server_id`, `verified_role`, `verify_channel`, `verification_logs`, `av_start_code`, `required_role` |
| `verified_users` | Discord-to-VRChat account mapping | `discord_id`, `vrchat_id` |
| `banned_users` | Global user ban records | `target_id` (Discord ID or VRChat User ID), `reason`, `moderator_id`, `timestamp` |
| `banned_servers` | Banned server records. The bot automatically leaves any server listed here. | `server_id`, `reason`, `moderator_id`, `timestamp` |

---

## Installation & Host Setup

### Prerequisites

- Python 3.10 or higher
- Required Python libraries:

```bash
pip install -r requirements.txt
```

---

## Community & Team

| Resource | Description |
| :------- | :---------- |
| [Meet the O-SAVS Team](TEAM.md) | Contact info and roles for development, administration, and support staff. |
| [O-SAVS Partners](PARTNERS.md) | View affiliated communities, VRChat groups, and partner organizations. |

---

## Legal & Policies

| Document | Description |
| :------- | :---------- |
| [Privacy Policy](PRIVACY.md) | Details on data collection, storage, and retention. |
| [Terms of Service](TERMS.md) | Usage rules, server admin responsibilities, and guidelines. |
| [License](LICENSE.md) | PolyForm Noncommercial License 1.0.0 |

- You are free to use, modify, and host this bot for non-commercial community use. Commercial hosting, selling, or monetization of this software is strictly prohibited.
- The bot is hosted 24/7 by ForgottenAvali and can be added to your server for free in [Noodle's Nexus](https://discord.gg/PeXzxBeUcB) or through the `INVITE O-SAVS` button above.

---

<div align="center">
  <sub>© O-SAVS · Maintained by <a href="https://ko-fi.com/forgottenavali">ForgottenAvali</a> · Licensed under PolyForm Noncommercial 1.0.0</sub>
</div>
