import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
GUILD_ID = int(os.getenv("GUILD_ID", 0))
ADMIN_IDS = [
    int(uid.strip())
    for uid in os.getenv("ADMIN_IDS", "").split(",")
    if uid.strip().isdigit()
]
