<div align="center">
  <img src="https://github.com/ForgottenAvali/O-SAVS_Assets/blob/main/Banners/OSAVSBanner.png" alt="O-SAVS Banner" width="100%" />

  <br />

  [![Invite Bot](https://img.shields.io/badge/Invite-O--SAVS-24292F?style=for-the-badge&logo=discord&logoColor=white)](https://discord.com/oauth2/authorize?client_id=1516450694109073439)
  [![Discord](https://img.shields.io/badge/Join-Noodle's%20Nexus-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/PeXzxBeUcB)
  [![Ko-fi](https://img.shields.io/badge/Ko--fi-Support%20Me-F16061?style=for-the-badge&logo=ko-fi&logoColor=white)](https://ko-fi.com/forgottenavali)
</div>

<br />

O-SAVS is a global Discord age-verification bot designed to integrate seamlessly with VRChat profiles. It allows server administrators to restrict adult spaces by ensuring members have verified their 18+ status on VRChat. Once a user is verified in one server running O-SAVS, their status automatically syncs across all mutual servers operating the bot.

---

## Features

- **Global Verification Sync:** Verify once, get synced automatically across all participating Discord servers.
- **VRChat Profile Integration:** Generates custom verification codes for users to place in their VRChat bio or status to verify account ownership.
- **Automated Guild Setup:** `/setup` slash command to configure roles, log channels, and code prefixes.
- **Role Hierarchy Safety:** Built-in checks to prevent configuration failures when managing role assignments.
- **Admin Dashboard:** A standalone desktop application for O-SAVS Administration to manually manage account links, global user exclusions, server listings, and temporary support invite links. Access is restricted to authorized administrators via credentialed login, cross-checked against an internal allow-list of authorized Discord IDs.
- **Auto-Syncing:** Automatically assigns verified roles to existing or joining members who are already in the global database.
- **Auto-Cleanup:** Automatically purges server configuration settings from the O-SAVS database upon bot removal (leaves all Discord roles, channels, and member verifications intact).

---

## Admin Dashboard

O-SAVS Administration manages the bot through a standalone desktop application rather than in-server commands, communicating with the bot over an authenticated internal HTTP API.

- **Actions:** Link/unlink Discord-VRChat accounts, globally ban/unban a Discord or VRChat ID, and look up a target's ban status.
- **Servers:** View every server the bot is currently in, with live member counts, and request a temporary, single-use invite for support/auditing purposes.
- **Logs:** Search and review a full audit trail of every administrative action taken through the dashboard.

Dashboard access requires a dashboard account **and** a linked Discord User ID present on O-SAVS Administration's internal allow-list; accounts without a linked, allow-listed ID cannot log in.

---

## Database Architecture

- **`server_settings`**: Stores guild configuration (`server_id`, `verified_role`, `verify_channel`, `verification_logs`, `av_start_code`, `required_role`).
- **`verified_users`**: Maps Discord IDs (`discord_id`) to VRChat User IDs (`vrchat_id`).
- **`banned_users`**: Stores global user ban records (`target_id` (Discord ID or VRChat User ID), `reason`, `moderator_id`, `timestamp`).

---

## Installation & Host Setup

### Prerequisites

- Python 3.10 or higher
- Required Python libraries:

```bash
pip install discord.py aiosqlite aiohttp vrchatapi
```

---

## Community & Team

- [Meet the O-SAVS Team](TEAM.md) - Contact info and roles for development, administration, and support staff.
- [O-SAVS Partners](PARTNERS.md) - View affiliated communities, VRChat groups, and partner organizations.

---

## Legal & Policies

- [Privacy Policy](PRIVACY.md) - Details on data collection, storage, and retention.
- [Terms of Service](TERMS.md) - Usage rules, server admin responsibilities, and guidelines.
- [License](LICENSE) - PolyForm Noncommercial License 1.0.0
   - You are free to use, modify, and host this bot for non-commercial community use. Commercial hosting, selling, or monetization of this software is strictly prohibited.
   - The bot is hosted 24/7 by ForgottenAvali and can be added to your server for free in [Noodle's Nexus](https://discord.gg/PeXzxBeUcB) or through the `INVITE O-SAVS` button above.
