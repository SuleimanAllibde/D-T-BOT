import asyncio
import threading

import discord
from discord.ext import commands

from config import CHALLENGES_BOT_TOKEN, GUILD_ID
from database import get_session, ChallengeSetting
from cogs.challenges import build_leaderboard_embed, register_persistent_views

challenges_bot: "ChallengesBot | None" = None

LEADERBOARD_REFRESH_SECONDS = 60


class ChallengesBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
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

        guild = discord.Object(id=GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)

        register_persistent_views(self)
        print("[ChallengesBot] Registered challenge panel views")

    async def on_ready(self):
        self.loop = asyncio.get_running_loop()
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


def start_challenges_bot():
    global challenges_bot
    if not CHALLENGES_BOT_TOKEN:
        return None
    if challenges_bot is not None:
        return challenges_bot
    bot = ChallengesBot()
    challenges_bot = bot
    thread = threading.Thread(target=bot.run, args=(CHALLENGES_BOT_TOKEN,), daemon=True)
    thread.start()
    print("[ChallengesBot] Started separate challenges bot")
    return bot


def get_challenges_bot():
    return challenges_bot if challenges_bot and challenges_bot.is_ready() else None
