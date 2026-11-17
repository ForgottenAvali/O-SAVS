import asyncio, getpass, os

from admin_app_db import (
    init_db, create_account, account_exists, reset_auth_code,
    set_password, set_disabled, MIN_PASSWORD_LENGTH,
)


def _prompt_password() -> str:
    while True:
        pw = getpass.getpass(f"Dashboard password (min {MIN_PASSWORD_LENGTH} characters): ")
        if len(pw) < MIN_PASSWORD_LENGTH:
            print(f"Too short -- use at least {MIN_PASSWORD_LENGTH} characters.")
            continue
        if pw != getpass.getpass("Confirm password: "):
            print("Passwords didn't match, try again.")
            continue
        return pw

def _show_code_once(username: str, code: str):
    print("\n" + "=" * 60)
    print(f"  AUTHORIZATION CODE for '{username}'")
    print(f"\n        {code}\n")
    print("  Save it in a password manager NOW. It is stored only as a")
    print("  hash and can never be shown again -- if it's lost, use")
    print("  option 2 to generate a new one.")
    print("=" * 60)
    input("\nPress Enter once it's saved (the screen will be cleared)... ")
    os.system("cls" if os.name == "nt" else "clear")

async def create_flow():
    username = input("Dashboard username: ").strip()
    if not username:
        print("Username can't be empty.")
        return
    if await account_exists(username):
        print(f"Account '{username}' already exists. Use option 2 to generate a new authorization code.")
        return

    password = _prompt_password()
    discord_id_raw = input(
        "Their Discord user ID (recommended - used for @mentions in log embeds "
        "and reuses your existing admin allow-list; press Enter to skip): "
    ).strip()
    if discord_id_raw and not discord_id_raw.isdigit():
        print("Discord IDs are numbers only.")
        return
    discord_id = int(discord_id_raw) if discord_id_raw else None

    auth_code = await create_account(username, password, discord_id)
    print(f"Account '{username}' created.")
    _show_code_once(username, auth_code)

async def reset_code_flow():
    username = input("Existing dashboard username: ").strip()
    if not await account_exists(username):
        print(f"No account named '{username}'.")
        return

    auth_code = await reset_auth_code(username)
    print(f"New authorization code generated for '{username}'. The old one no longer works.")
    _show_code_once(username, auth_code)

async def reset_password_flow():
    username = input("Existing dashboard username: ").strip()
    if not await account_exists(username):
        print(f"No account named '{username}'.")
        return

    await set_password(username, _prompt_password())
    print(f"Password changed for '{username}'. Their existing dashboard sessions are now invalid.")

async def disable_flow(disabled: bool):
    username = input("Existing dashboard username: ").strip()
    if not await set_disabled(username, disabled):
        print(f"No account named '{username}'.")
        return

    if disabled:
        print(f"'{username}' is disabled: they can't log in and their sessions are invalid.")
    else:
        print(f"'{username}' is enabled again and can log in.")

async def main():
    await init_db()
    print("1) Create a new dashboard account")
    print("2) Generate a new authorization code for an existing account")
    print("3) Reset an account's password")
    print("4) Disable an account")
    print("5) Re-enable an account")
    choice = input("Choose 1-5: ").strip()

    if choice == "1":
        await create_flow()
    elif choice == "2":
        await reset_code_flow()
    elif choice == "3":
        await reset_password_flow()
    elif choice == "4":
        await disable_flow(True)
    elif choice == "5":
        await disable_flow(False)
    else:
        print("Invalid choice.")

if __name__ == "__main__":
    asyncio.run(main())
