import threading
import sys

from bot import Bot
from dashboard.app import run_dashboard, set_bot
from config import BOT_TOKEN
from database import init_db


def start_dashboard():
    run_dashboard()


def main():
    if not BOT_TOKEN:
        print("ERROR: DISCORD_BOT_TOKEN is not set. Check your .env file.")
        sys.exit(1)

    init_db()

    bot = Bot()
    set_bot(bot)

    dash_thread = threading.Thread(target=start_dashboard, daemon=True)
    dash_thread.start()
    print("[Dashboard] Web dashboard started on http://127.0.0.1:5000")

    try:
        bot.run(BOT_TOKEN)
    except discord.LoginFailure:
        print("ERROR: Invalid bot token.")
        sys.exit(1)


if __name__ == "__main__":
    import discord
    main()
