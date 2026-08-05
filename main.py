import threading
import sys
import os

from bot import Bot
from dashboard.app import run_dashboard, set_bot
from config import BOT_TOKEN
from database import init_db
from voice_bots import start_voice_bots
from challenges_bot import start_challenges_bot


def start_dashboard():
    run_dashboard()


def main():
    if not BOT_TOKEN:
        print("ERROR: DISCORD_BOT_TOKEN is not set. Check your .env file.")
        sys.exit(1)

    init_db()
    start_voice_bots()
    start_challenges_bot()

    bot = Bot()
    set_bot(bot)

    port = int(os.getenv("PORT", 5000))
    host = "0.0.0.0"
    dash_thread = threading.Thread(target=start_dashboard, daemon=True)
    dash_thread.start()
    print(f"[Dashboard] Web dashboard started on http://{host}:{port}")

    try:
        bot.run(BOT_TOKEN)
    except discord.LoginFailure:
        print("ERROR: Invalid bot token.")
        sys.exit(1)


if __name__ == "__main__":
    import discord
    main()
