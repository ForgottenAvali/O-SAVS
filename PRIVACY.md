# O-SAVS Privacy Policy

Last Updated: September 2, 2026

O-SAVS ("the Bot") is committed to protecting user privacy and maintaining transparency regarding data collection, storage, and usage.

## 1. Information We Collect
To provide global age-verification functionality, O-SAVS stores the following minimal data in an encrypted database:
- **Discord User ID:** Stored as text to uniquely identify users across participating servers.
- **VRChat User ID:** Stored as text to map verified status between Discord and VRChat accounts.
- **Server Settings & Metadata:** Guild IDs, role IDs, log channel IDs, server names, member counts, and custom verification prefix codes configured by server administrators.
- **Global Sanction Records:** Discord User IDs, internal reason codes, timestamps, and moderator IDs for globally banned accounts to enforce system-wide exclusions.

## 2. Information We DO NOT Collect
- **Personal Identification Documents:** We do not request, collect, or store real names, IDs, passports, driver's licenses, or facial images.
- **Message Content:** We do not read, log, or store chat messages in any Discord server.
- **VRChat Account Credentials:** Authentication tokens and login details are restricted to the bot's host environment and are never stored alongside user records.

## 3. How We Use Data
Collected data is used solely to:
- Verify that a Discord account is linked to a VRChat profile containing a valid verification code.
- Automatically assign verified 18+ roles across mutual Discord servers operating O-SAVS.
- Maintain global ban lists and audit administrative actions (`.link`, `.unlink`, `.ban_user`, `.unban_user`, `.get_user_ban`, `.get_osavs_servers`, `.invite_me_osavs`) to protect participating communities from unauthorized or unsafe access.
- Perform system health audits, verify server setup permissions, and enable authorized bot administration through restricted administrative channels.

## 4. Data Retention & Deletion
- **User Unlinking:** If a user is unlinked, their record is permanently deleted from the active verification database.
- **Data Removal Requests:** Users may request complete removal of their linked account data at any time by opening a ticket in the [Noodle's Nexus](https://discord.gg/PeXzxBeUcB) support server.
- **Moderation & Sanction Exception:** Global sanction records (Discord User IDs, reason codes, timestamps, and moderator IDs for globally banned accounts) are retained indefinitely to enforce system-wide security, prevent ban evasion, and protect participating communities. Data removal requests will not erase active global sanction records.
- **Server Removal:** When O-SAVS leaves a server, server configuration settings are scheduled for automatic purge.

## 5. Third-Party Services
O-SAVS interacts directly with:
- **Discord API:** Subject to Discord's Terms of Service and Privacy Policy.
- **VRChat API:** Subject to VRChat's Terms of Service and Privacy Policy.
