# O-SAVS Privacy Policy

*Last Updated: October 7, 2026*

O-SAVS ("the Bot") is committed to protecting user privacy and maintaining transparency regarding data collection, storage, and usage.

## 1. Information We Collect
To provide global age-verification functionality, O-SAVS stores the following minimal data in an encrypted database:
- **Discord User ID:** Stored as text to uniquely identify users across participating servers.
- **VRChat User ID:** Stored as text to map verified status between Discord and VRChat accounts.
- **Server Settings & Metadata:** Guild IDs, role IDs, log channel IDs, server names, member counts, and custom verification prefix codes configured by server administrators.
- **Global User Sanction Records:** Discord User IDs or VRChat User IDs, internal reason codes, timestamps, and moderator IDs for globally banned accounts to enforce system-wide exclusions.
- **Global Server Sanction Records:** Server IDs, server names, internal reason codes, timestamps, and moderator IDs for globally banned servers, used to ensure the Bot leaves and does not rejoin those servers.
- **Ban Evidence:** When a global ban of a user or server is being reviewed or issued, O-SAVS Administration may store message content related to that ban, along with the associated message, author, channel, and server IDs and timestamps. This applies only to content relevant to the ban (see Section 2).
- **Admin Action Logs:** Timestamps, the acting administrator's dashboard username, the action taken, the target Discord/VRChat ID or server ID, and any reason provided, recorded for every action performed through the Admin Dashboard.

## 2. Information We DO NOT Collect
- **Personal Identification Documents:** We do not request, collect, or store real names, IDs, passports, driver's licenses, or facial images.
- **Message Content (with one exception):** We do not read, log, or store chat messages in any Discord server as part of normal operation. The only exception is Ban Evidence: if a message or its content relates to a global user ban or global server ban, that specific content may be stored as described in Sections 1, 3, and 4. We do not store messages unrelated to a ban.
- **VRChat Account Credentials:** O-SAVS never requests, accesses, or stores user VRChat account credentials, passwords, or login tokens. Verification relies strictly on publicly accessible profile details linked via your VRChat User ID.

## 3. How We Use Data
Collected data is used solely to:
- Verify that a Discord account is linked to a VRChat profile containing a valid verification code.
- Automatically assign verified 18+ roles across mutual Discord servers operating O-SAVS.
- Maintain global user and server ban lists and audit administrative actions (linking, unlinking, banning, unbanning, ban lookups, server bans, server audits, and temporary support invites) performed through the official O-SAVS Admin Dashboard to protect participating communities from unauthorized or unsafe access.
- Review, justify, and document global bans, including handling appeals and keeping a record of past cases, using Ban Evidence where it exists.
- Perform system health audits, verify server setup permissions, and enable authorized bot administration through the restricted, credentialed O-SAVS Admin Dashboard.

## 4. Data Retention & Deletion
- **User Unlinking:** If a user is unlinked, their record is permanently deleted from the active verification database.
- **Data Removal Requests:** Users may request complete removal of their linked account data at any time by opening a ticket in the [Noodle's Nexus](https://discord.gg/PeXzxBeUcB) support server.
- **Moderation & Sanction Exception:** Global user and server sanction records (IDs, server names, reason codes, timestamps, and moderator IDs) and any Ban Evidence attached to them are retained indefinitely to enforce system-wide security, prevent ban evasion, keep an accurate record of administrative decisions, and protect participating communities. Data removal requests will not erase global sanction records or the Ban Evidence supporting them.
- **Lifted or Overturned Bans:** If a global ban is lifted or overturned on appeal, the related sanction record and Ban Evidence are still kept as a historical record of the case.
- **Server Removal:** When O-SAVS leaves a server, server configuration settings are scheduled for automatic purge. Global server sanction records are not purged when the Bot leaves a banned server, so that the ban continues to be enforced.

## 5. Third-Party Services
O-SAVS interacts directly with:
- **Discord API:** Subject to Discord's Terms of Service and Privacy Policy.
- **VRChat API:** Subject to VRChat's Terms of Service and Privacy Policy.
