# O-SAVS (Open-Source Age Verification System)

[![Discord](https://img.shields.io/badge/Discord-Join%20Community-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/PeXzxBeUcB)
[![Ko-fi](https://img.shields.io/badge/Ko--fi-Support%20Me-F16061?style=for-the-badge&logo=ko-fi&logoColor=white)](https://ko-fi.com/forgottenavali)

[🔒 Privacy Policy](PRIVACY.md) | [📜 Terms of Service](TERMS.md)

O-SAVS is a global Discord age-verification bot designed to integrate seamlessly with VRChat profiles. It allows server administrators to restrict adult spaces by ensuring members have verified their 18+ status on VRChat. Once a user is verified in one server running O-SAVS, their status automatically syncs across all mutual servers operating the bot.

---

## Features

- **Global Verification Sync:** Verify once, get synced automatically across all participating Discord servers.
- **VRChat Profile Integration:** Generates custom verification codes for users to place in their VRChat bio or status to verify the account is theirs.
- **Automated Guild Setup:** Interactive `/setup` slash command to configure roles, log channels, and code prefixes (Refer to `VRChat Profile Integration` for this).
- **Role Hierarchy Safety:** Built-in checks to prevent configuration failures when managing role assignments.
- **Management Commands:** Administrative prefix commands (`.link` / `.unlink`) to manually control database links across servers with audit logging. (Only usable by ForgottenAvali and a few others.)
- **Auto-Syncing:** Automatically assigns verified roles to existing or joining members who are already in the global database.
- **Auto-Cleanup:** Cleans up server configuration data upon bot departure (`on_guild_remove`).

---

## Database Architecture

O-SAVS utilizes **SQLite (`aiosqlite`)** with text-based Snowflake column schemas to prevent precision loss across 64-bit Discord IDs.

- **`server_settings`**: Stores guild configuration (`server_id`, `verified_role`, `verify_channel`, `verification_logs`, `av_start_code`).
- **`verified_users`**: Maps Discord IDs (`discord_id`) to VRChat User IDs (`vrchat_id`).

---

## Installation & Host Setup

### Prerequisites

- Python 3.10 or higher
- Required Python libraries:

```bash
pip install discord.py aiosqlite aiohttp vrchatapi
```

---
## License

This project is licensed under the **PolyForm Noncommercial License 1.0.0**. 

You are free to use, modify, and host this bot for non-commercial community use. Commercial hosting, selling, or monetization of this software is strictly prohibited. 

See the full [LICENSE](LICENSE) file for details.
