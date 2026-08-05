import asyncio
import threading
import traceback

import discord
from discord.ext import commands

from config import CHALLENGES_BOT_TOKEN, GUILD_ID
from database import get_session, ChallengeSetting
from cogs.challenges import build_leaderboard_embed, register_persistent_views

challenges_bot: "ChallengesBot | None" = None
challenges_bot_status = {
    "status": "not_configured",
    "error": "",
    "ready": False,
    "user": "",
}

LEADERBOARD_REFRESH_SECONDS = 60


def decode_bot_id(token: str):
    """Extract the bot user/app ID from a bot token (prefix before the first dot)."""
    try:
        return token.split(".", 1)[0]
    except Exception:
        return ""


def get_invite_url(token: str):
    bot_id = decode_bot_id(token)
    if bot_id and bot_id.isdigit():
        return (
            f"https://discord.com/oauth2/authorize?client_id={bot_id}"
            f"&scope=bot%20applications.commands&permissions=2147493408"
        )
    return ""


class ChallengesBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.guilds = True

        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="challenge leaderboard",
            ),
        )
        self.bg_task = None

    async def setup_hook(self):
        await self.load_extension("cogs.challenges")
        register_persistent_views(self)

        guild = discord.Object(id=GUILD_ID)
        try:
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        except Exception as e:
            print(f"[ChallengesBot] WARNING: could not sync slash commands: {e}")

        print("[ChallengesBot] Registered challenge panel views")

    async def on_ready(self):
        self.loop = asyncio.get_running_loop()
        challenges_bot_status["status"] = "online"
        challenges_bot_status["ready"] = True
        challenges_bot_status["error"] = ""
        challenges_bot_status["user"] = f"{self.user} (ID: {self.user.id})"
        print(f"[ChallengesBot] Logged in as {self.user} (ID: {self.user.id})")
        if not self.bg_task:
            self.bg_task = asyncio.ensure_future(self._leaderboard_loop())

    async def _leaderboard_loop(self):
        while True:
            try:
                await self.update_leaderboard()
            except Exception as e:
                print(f"[ChallengesBot] Leaderboard update error: {e}")
            await asyncio.sleep(LEADERBOARD_REFRESH_SECONDS)

    async def update_leaderboard(self):
        sess = get_session()
        try:
            s = sess.get(ChallengeSetting, GUILD_ID)
            if (
                not s
                or not s.enabled
                or not s.leaderboard_enabled
                or not s.leaderboard_channel_id
            ):
                return
            channel_id = s.leaderboard_channel_id
            message_id = s.leaderboard_message_id
        finally:
            sess.close()

        channel = self.get_channel(channel_id)
        if channel is None:
            for g in self.guilds:
                ch = discord.utils.get(g.text_channels, id=channel_id)
                if ch:
                    channel = ch
                    break
        if channel is None:
            return

        guild = self.get_guild(GUILD_ID)
        embed = build_leaderboard_embed(guild, GUILD_ID)

        if message_id:
            try:
                msg = await channel.fetch_message(message_id)
                await msg.edit(embed=embed)
                return
            except discord.NotFound:
                pass
            except (discord.Forbidden, discord.HTTPException) as e:
                print(f"[ChallengesBot] Could not edit leaderboard: {e}")
                return

        msg = await channel.send(embed=embed)
        sess = get_session()
        try:
            s = sess.get(ChallengeSetting, GUILD_ID)
            if s:
                s.leaderboard_message_id = msg.id
                sess.commit()
        finally:
            sess.close()
        print(f"[ChallengesBot] Posted leaderboard to #{channel.name} (msg {msg.id})")


def _run_challenges_bot(bot: ChallengesBot):
    try:
        bot.run(CHALLENGES_BOT_TOKEN)
    except discord.PrivilegedIntentsRequired:
        challenges_bot_status["status"] = "error"
        challenges_bot_status["error"] = "SERVER MEMBERS INTENT is not enabled for this bot in the Developer Portal."
        print("\n[ChallengesBot] ❌ FAILED to login — the app is missing the SERVER MEMBERS INTENT.")
        print("[ChallengesBot]    1. Open https://discord.com/developers/applications")
        print("[ChallengesBot]    2. Select the CHALLENGES bot application -> Bot tab (Privileged Gateway Intents)")
        print("[ChallengesBot]    3. Turn ON  SERVER MEMBERS INTENT  (MESSAGE CONTENT is NOT required for this bot)")
        print("[ChallengesBot]    4. Save, then restart the service on Render")
        print("[ChallengesBot]    Invite link if not added to the server yet:")
        print(f"[ChallengesBot]       {get_invite_url(CHALLENGES_BOT_TOKEN)}")
    except discord.LoginFailure:
        challenges_bot_status["status"] = "error"
        challenges_bot_status["error"] = "Invalid CHALLENGES_BOT_TOKEN."
        print("\n[ChallengesBot] ❌ FAILED to login — CHALLENGES_BOT_TOKEN is invalid.")
        print("[ChallengesBot]    Copy the exact token from the Discord Developer Portal (Bot -> Reset Token).")
    except discord.HTTPException as e:
        challenges_bot_status["status"] = "error"
        challenges_bot_status["error"] = f"Discord API error: {e}"
        print(f"\n[ChallengesBot] ❌ FAILED to connect — Discord API error: {e}")
    except Exception as e:
        challenges_bot_status["status"] = "error"
        challenges_bot_status["error"] = f"{e}"
        print(f"\n[ChallengesBot] ❌ FAILED to start: {e}")
        traceback.print_exc()


def start_challenges_bot():
    global challenges_bot
    if not CHALLENGES_BOT_TOKEN:
        challenges_bot_status["status"] = "not_configured"
        challenges_bot_status["error"] = "CHALLENGES_BOT_TOKEN is empty — set it in the dashboard env vars."
        return None
    if challenges_bot is not None:
        return challenges_bot
    bot = ChallengesBot()
    challenges_bot = bot
    challenges_bot_status["status"] = "starting"
    challenges_bot_status["error"] = ""
    thread = threading.Thread(target=_run_challenges_bot, args=(bot,), daemon=True)
    thread.start()
    print("[ChallengesBot] Starting separate challenges bot...")
    print(f"[ChallengesBot] Bot ID: {decode_bot_id(CHALLENGES_BOT_TOKEN)}")
    print(f"[ChallengesBot] Invite URL: {get_invite_url(CHALLENGES_BOT_TOKEN)}")
    return bot


def get_challenges_bot():
    return challenges_bot if challenges_bot and challenges_bot.is_ready() else None


def get_challenges_bot_status():
    return dict(challenges_bot_status)


def test_token(token: str):
    """Validate a bot token against the Discord API without logging in."""
    import urllib.request
    print("[ChallengesBot] Bot ID from token:", decode_bot_id(token) or "INVALID FORMAT")
    print("[ChallengesBot] Invite URL:", get_invite_url(token) or "cannot build (token malformed)")
    req = urllib.request.Request(
        "https://discord.com/api/v10/users/@me",
        headers={"Authorization": f"Bot {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            print(f"[ChallengesBot] ✅ Token VALID — bot application: {data.get('username')} (ID {data.get('id')})")
            return True
    except urllib.error.HTTPError as e:
        print(f"[ChallengesBot] ❌ Token REJECTED — HTTP {e.code}: {e.read().decode()[:200]}")
        return False
    except Exception as e:
        print(f"[ChallengesBot] ❌ Could not reach Discord API: {e}")
        return False


if __name__ == "__main__":
    import sys
    import json
    if "--test" in sys.argv:
        if not CHALLENGES_BOT_TOKEN:
            print("[ChallengesBot] CHALLENGES_BOT_TOKEN is empty — set it in .env first.")
            sys.exit(1)
        test_token(CHALLENGES_BOT_TOKEN)
        sys.exit(0)
