import os, discord, asyncio, logging


from dotenv import load_dotenv
from discord.ext import commands


from cogs import verification, administration
from data.vrchat import login_vrc
from data.database import init_db
from data.lock import ensure_single_instance, cleanup_instance


logging.basicConfig(
    level=logging.INFO,
    format="%(message)s"
)


intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents)


load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")


@bot.event
async def on_ready():
    if not hasattr(bot, "initialized"):
        await init_db()
        await verification.setup(bot)
        await administration.setup(bot)
        await bot.tree.sync()

        bot.initialized = True

    print(f"[Discord] Logged in as {bot.user}")


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
