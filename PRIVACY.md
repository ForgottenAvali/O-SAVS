# O-SAVS Privacy Policy

[📖 README](README.md) | [⚖️ License](LICENSE) | [📜 Terms of Service](TERMS.md)

Last Updated: August 31, 2026

O-SAVS ("the Bot") is committed to protecting user privacy and maintaining transparency regarding data collection, storage, and usage.

## 1. Information We Collect
To provide global age-verification functionality, O-SAVS stores the following minimal data in an encrypted database:
- **Discord User ID:** Stored as text to uniquely identify users across participating servers.
- **VRChat User ID:** Stored as text to map verified status between Discord and VRChat accounts.
- **Server Settings:** Guild IDs, role IDs, log channel IDs, and custom verification prefix codes configured by server administrators.

## 2. Information We DO NOT Collect
- **Personal Identification Documents:** We do not request, collect, or store real-name IDs, passports, driver's licenses, or facial images.
- **Message Content:** We do not read, log, or store chat messages in any Discord server.
- **VRChat Account Credentials:** Authentication tokens and login details are restricted to the bot's host environment and are never stored alongside user records.

## 3. How We Use Data
Collected data is used solely to:
- Verify that a Discord account is linked to a VRChat profile containing a valid verification code.
- Automatically assign verified 18+ roles across mutual Discord servers operating O-SAVS.
- Audit administrative actions (`.link` / `.unlink`) to prevent system abuse.

## 4. Data Retention & Deletion
- **User Unlinking:** If a user is unlinked, their record is permanently deleted from the active verification database.
- **Data Removal Requests:** Users may request complete data removal at any time by opening a ticket in our Support Server (Noodle's Nexus) or contacting a Bot Administrator.
- **Server Removal:** When O-SAVS leaves a server, server configuration settings are scheduled for automatic purge.

## 5. Third-Party Services
O-SAVS interacts directly with:
- **Discord API:** Subject to Discord's Terms of Service and Privacy Policy.
- **VRChat API:** Subject to VRChat's Terms of Service and Privacy Policy.
