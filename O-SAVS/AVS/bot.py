import os, discord, asyncio, logging, itertools, importlib.util, aiohttp

from dotenv import load_dotenv
from discord.ext import commands, tasks

from cogs import verification
from settings import PRIMARY_SERVER, BOT_ID
from data.vrchat import login_vrc
from data.database import init_db, get_total_verified_users, get_maintenance_mode
from data.lock import ensure_single_instance, cleanup_instance

admin_cog = None
for _name in ("admin_api", "admin_commands"):
    if importlib.util.find_spec(f"cogs.{_name}") is not None:
        admin_cog = importlib.import_module(f"cogs.{_name}")
        break

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s"
)

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

status_index = 0
last_verified_count = None


@bot.event
async def on_ready():
    if not hasattr(bot, "initialized"):
        await init_db()
        await verification.setup(bot)

        if admin_cog is not None:
            await admin_cog.setup(bot)

        await bot.tree.sync()

        bot.initialized = True

    if await get_maintenance_mode():
        await bot.change_presence(status=discord.Status.invisible, activity=None)
        print("[System] Maintenance mode is ON, appearing offline.")

    print(f"[Discord] Logged in as {bot.user}")

    if not update_status.is_running():
        update_status.start()

@tasks.loop(seconds=30)
async def update_status():
    global status_index, last_verified_count

    if await get_maintenance_mode():
        return

    active_guilds = [g for g in bot.guilds if g.id != PRIMARY_SERVER]
    server_count = len(active_guilds)

    try:
        last_verified_count = await get_total_verified_users(exclude_ids=[BOT_ID])
    except Exception as e:
        logging.warning("Could not refresh verified count, using last known value: %s", e)

    statuses = [f"Verifying people in {server_count} servers!"]
    if last_verified_count is not None:
        statuses.append(f"{last_verified_count:,} users are already verified!")

    current_status = statuses[status_index % len(statuses)]

    try:
        await bot.change_presence(
            activity=discord.CustomActivity(name=current_status)
        )
    except (aiohttp.ClientError, ConnectionResetError):
        return

    status_index += 1

bot.status_task = update_status

@update_status.before_loop
async def before_update_status():
    await bot.wait_until_ready()

@update_status.error
async def update_status_error(exc):
    logging.exception("update_status failed: %s", exc)

async def start_bot():
    ensure_single_instance()
    try:
        await login_vrc()
        await bot.start(TOKEN)
    except KeyboardInterrupt:
        print("\n[System] Manual shutdown triggered.")

    except Exception as e:
        logging.exception("Bot crashed: %s", e)

    finally:
        cleanup_instance()
        
        if not bot.is_closed():
            await bot.close()
        print("[System] Bot has been shut down.")

if __name__ == "__main__":
    try:
        asyncio.run(start_bot())
    except RuntimeError as e:
        logging.exception("RuntimeError at root level: %s", e)
