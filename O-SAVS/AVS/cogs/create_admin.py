import asyncio, getpass

from admin_app_db import init_db, create_account, account_exists, set_auth_code


def _prompt_auth_code() -> str:
    while True:
        code = getpass.getpass("4-digit authorization code (used to confirm sensitive actions like Leave Server): ")
        if not (len(code) == 4 and code.isdigit()):
            print("The code must be exactly 4 digits.")
            continue
        if code != getpass.getpass("Confirm authorization code: "):
            print("Codes didn't match, try again.")
            continue
        return code

async def create_flow():
    username = input("Dashboard username: ").strip()
    if await account_exists(username):
        print(f"Account '{username}' already exists. Use option 2 to set its authorization code.")
        return

    password = getpass.getpass("Dashboard password: ")
    discord_id_raw = input(
        "Their Discord user ID (recommended - used for @mentions in log embeds "
        "and reuses your existing admin allow-list; press Enter to skip): "
    ).strip()
    discord_id = int(discord_id_raw) if discord_id_raw else None
    auth_code = _prompt_auth_code()

    await create_account(username, password, discord_id, auth_code)
    print(f"Account '{username}' created.")

async def set_code_flow():
    username = input("Existing dashboard username: ").strip()
    if not await account_exists(username):
        print(f"No account named '{username}'.")
        return

    await set_auth_code(username, _prompt_auth_code())
    print(f"Authorization code updated for '{username}'.")

async def main():
    await init_db()
    print("1) Create a new dashboard account")
    print("2) Set or reset an existing account's authorization code")
    choice = input("Choose 1 or 2: ").strip()

    if choice == "1":
        await create_flow()
    elif choice == "2":
        await set_code_flow()
    else:
        print("Invalid choice.")

if __name__ == "__main__":
    asyncio.run(main())
