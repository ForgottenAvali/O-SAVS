import getpass

from admin_app_db import init_db, create_account


def main():
    init_db()
    username = input("Dashboard username: ").strip()
    password = getpass.getpass("Dashboard password: ")
    discord_id_raw = input(
        "Their Discord user ID (recommended -- used for @mentions in log embeds "
        "and reuses your existing admin allow-list; press Enter to skip): "
    ).strip()
    discord_id = int(discord_id_raw) if discord_id_raw else None

    create_account(username, password, discord_id)
    print(f"Account '{username}' created.")

if __name__ == "__main__":
    main()
