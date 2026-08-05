import asyncio
import threading

import discord

from config import VOICE_BOT_TOKENS
from database import get_session, VoiceBotSetting

voice_bots: dict = {}


def _get_setting(bot_index: int) -> VoiceBotSetting:
    sess = get_session()
    try:
        row = sess.get(VoiceBotSetting, bot_index)
        if not row:
            row = VoiceBotSetting(bot_index=bot_index, label=f"Voice Bot {bot_index + 1}")
            sess.add(row)
            sess.commit()
        return row
    finally:
        sess.close()


def _save_setting(bot_index: int, label: str, voice_channel_id, enabled: bool):
    sess = get_session()
    try:
        row = sess.get(VoiceBotSetting, bot_index)
        if not row:
            row = VoiceBotSetting(bot_index=bot_index)
            sess.add(row)
        row.label = label
        row.voice_channel_id = int(voice_channel_id) if voice_channel_id else None
        row.enabled = enabled
        sess.commit()
    finally:
        sess.close()


class VoicePresenceBot(discord.Client):
    def __init__(self, bot_index: int, token: str):
        intents = discord.Intents.default()
        intents.voice_states = True
        super().__init__(intents=intents)
        self.bot_index = bot_index
        self.token = token
        self.current_vc = None
        self.last_error = ""

    async def on_ready(self):
        print(f"[VoiceBot {self.bot_index}] Online as {self.user}")
        await self.sync_target()
        self.bg_task = asyncio.ensure_future(self._keep_alive())

    async def _keep_alive(self):
        while True:
            await asyncio.sleep(30)
            try:
                await self.sync_target()
            except Exception:
                pass

    async def on_voice_state_update(self, member, before, after):
        if member.id != self.user.id:
            return
        if after.channel is None and self.current_vc is not None:
            self.current_vc = None
            await asyncio.sleep(2)
            await self.sync_target()

    async def sync_target(self):
        import traceback
        try:
            row = _get_setting(self.bot_index)
            target = row.voice_channel_id if row.enabled and row.voice_channel_id else None

            if target is None:
                self.last_error = ""
                for vc in list(self.voice_clients):
                    try:
                        await vc.disconnect()
                    except Exception:
                        pass
                self.current_vc = None
                return

            channel = self.get_channel(target)
            if channel is None:
                for g in self.guilds:
                    ch = discord.utils.get(g.voice_channels, id=target)
                    if ch:
                        channel = ch
                        break
            if channel is None:
                self.last_error = f"Channel {target} not found (is the bot in the server?)"
                print(f"[VoiceBot {self.bot_index}] {self.last_error}")
                return

            # Prefer the library's actual connection state over the cached one.
            vc = None
            for client in self.voice_clients:
                if client.channel and client.channel.id == target:
                    vc = client
                    break
            if vc is None:
                for client in self.voice_clients:
                    if client.guild and client.guild == channel.guild:
                        vc = client
                        break

            if vc:
                self.current_vc = vc
                if vc.channel and vc.channel.id == target:
                    self.last_error = ""
                    return
                try:
                    await vc.move_to(channel)
                    self.last_error = ""
                    print(f"[VoiceBot {self.bot_index}] Moved to {channel.name}")
                    return
                except Exception as e:
                    print(f"[VoiceBot {self.bot_index}] Move error: {e}")
                    try:
                        await vc.disconnect()
                    except Exception:
                        pass
                    self.current_vc = None
                    vc = None

            self.current_vc = await channel.connect(timeout=30)
            self.last_error = ""
            print(f"[VoiceBot {self.bot_index}] Joined #{channel.name}")
        except discord.Forbidden as e:
            self.last_error = "No permission to connect (check Connect permission)"
            print(f"[VoiceBot {self.bot_index}] Forbidden: {e}")
        except Exception as e:
            self.last_error = str(e)
            traceback.print_exc()
            print(f"[VoiceBot {self.bot_index}] sync error: {e}")

    async def rename_bot(self, new_name: str):
        try:
            if not self.user:
                return "Bot not ready yet"
            if self.user.name == new_name:
                return ""
            await self.user.edit(username=new_name)
            self.last_error = ""
            return ""
        except discord.HTTPException as e:
            msg = f"Rename failed (HTTP {e.status}): {e.text}"
            self.last_error = msg
            return msg
        except Exception as e:
            msg = f"Rename failed: {e}"
            self.last_error = msg
            return msg

    def trigger_sync(self):
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self.sync_target(), self.loop)


def start_voice_bots():
    for i, token in enumerate(VOICE_BOT_TOKENS):
        if i in voice_bots:
            continue
        bot = VoicePresenceBot(i, token)
        voice_bots[i] = bot
        thread = threading.Thread(target=bot.run, args=(token,), daemon=True)
        thread.start()
        print(f"[VoiceBot] Started bot {i + 1}")


def get_voice_bot_user_id(bot_index: int):
    bot = voice_bots.get(bot_index)
    if bot and bot.user:
        return bot.user.id
    return None


def get_voice_bot_list():
    result = []
    for i in range(len(VOICE_BOT_TOKENS)):
        bot = voice_bots.get(i)
        row = _get_setting(i)
        status = "offline"
        channel_name = ""
        if bot and bot.is_ready():
            status = "online"
            vc = bot.current_vc
            if vc is None and bot.voice_clients:
                vc = bot.voice_clients[0]
            if vc and vc.channel:
                channel_name = vc.channel.name
        result.append({
            "bot_index": i,
            "label": row.label,
            "voice_channel_id": str(row.voice_channel_id) if row.voice_channel_id else None,
            "enabled": bool(row.enabled),
            "status": status,
            "channel_name": channel_name,
            "error": getattr(bot, "last_error", "") if bot else "",
        })
    return result
