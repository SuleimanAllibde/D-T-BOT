import asyncio
import datetime
import io
import os
import time
from collections import deque

import discord
from discord.ext import commands

from config import GUILD_ID


class Bot(commands.Bot):
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
                name="over D&T Server",
            ),
        )
        self._message_timestamps: deque = deque()

    async def setup_hook(self):
        await self.load_extension("cogs.welcome")
        await self.load_extension("cogs.moderation")
        await self.load_extension("cogs.autorole")
        await self.load_extension("cogs.tickets")
        await self.load_extension("cogs.logging")
        await self.load_extension("cogs.autoresponder")
        await self.load_extension("cogs.utility")
        await self.load_extension("cogs.security")

        guild = discord.Object(id=GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)

        # Register persistent views for ticket system and reaction roles
        from cogs.tickets import TicketView, TicketCloseView
        self.add_view(TicketView())
        self.add_view(TicketCloseView())
        try:
            from cogs.autorole import _register_persistent_view
            _register_persistent_view(self)
            print("[Setup] Registered persistent ReactionRole view")
        except Exception as e:
            print(f"[Setup] Could not register ReactionRoleView: {e}")

    async def start(self, *args, **kwargs):
        # Fix: capture the actual running event loop (asyncio.run() creates a new one)
        self.loop = asyncio.get_running_loop()
        await super().start(*args, **kwargs)

    async def on_ready(self):
        # Ensure self.loop points to the correct running loop
        self.loop = asyncio.get_running_loop()
        print(f"[Bot] Logged in as {self.user} (ID: {self.user.id})")
        from dashboard.app import set_bot
        set_bot(self)

    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild or message.guild.id != GUILD_ID:
            return
        self._message_timestamps.append(time.time())

    @property
    def message_count_24h(self):
        cutoff = time.time() - 86400
        while self._message_timestamps and self._message_timestamps[0] < cutoff:
            self._message_timestamps.popleft()
        return len(self._message_timestamps)

    @property
    def guild(self):
        return self.get_guild(GUILD_ID)

    def send_embed_to_channel(
        self, channel_id: int, title: str, description: str,
        color: str = "#5865F2", thumbnail_url: str = "", footer: str = "",
        file_path: str = ""
    ):
        async def _send():
            try:
                guild = self.guild
                if not guild:
                    print("[Embed] ERROR: Guild not found")
                    return
                channel = discord.utils.get(guild.text_channels, id=channel_id)
                if not channel:
                    cached_ids = [c.id for c in guild.text_channels]
                    print(f"[Embed] ERROR: Channel {channel_id} not found. Cached text channel IDs: {cached_ids}")
                    return
                try:
                    hex_color = int(color.lstrip("#"), 16)
                except ValueError:
                    hex_color = 0x5865F2
                embed = discord.Embed(title=title, description=description, color=hex_color)
                if thumbnail_url:
                    embed.set_thumbnail(url=thumbnail_url)
                if footer:
                    embed.set_footer(text=footer)
                kwargs = {"embed": embed}
                if file_path:
                    if os.path.exists(file_path):
                        with open(file_path, 'rb') as fh:
                            data = fh.read()
                        kwargs["file"] = discord.File(io.BytesIO(data), filename=os.path.basename(file_path))
                        print(f"[Embed] Attaching file: {file_path}")
                    else:
                        print(f"[Embed] File not found: {file_path}")
                await channel.send(**kwargs)
                print(f"[Embed] Sent to #{channel.name}")
            except Exception as e:
                print(f"[Embed] ERROR: {e}")
        try:
            asyncio.run_coroutine_threadsafe(_send(), self.loop)
        except Exception as e:
            print(f"[Embed] run_coroutine_threadsafe error: {e}")

    def send_message_to_channel(self, channel_id: int, content: str, file_path: str = ""):
        async def _send():
            try:
                channel = self.get_channel(channel_id)
                if not channel:
                    print(f"[Message] ERROR: Channel {channel_id} not found")
                    return
                kwargs = {"content": content}
                if file_path:
                    if os.path.exists(file_path):
                        with open(file_path, 'rb') as fh:
                            data = fh.read()
                        kwargs["file"] = discord.File(io.BytesIO(data), filename=os.path.basename(file_path))
                        print(f"[Message] Attaching file: {file_path}")
                    else:
                        print(f"[Message] File not found: {file_path}")
                await channel.send(**kwargs)
                print(f"[Message] Sent to #{channel.name}")
            except Exception as e:
                print(f"[Message] ERROR: {e}")
        try:
            asyncio.run_coroutine_threadsafe(_send(), self.loop)
        except Exception as e:
            print(f"[Message] run_coroutine_threadsafe error: {e}")

    def send_poll_to_channel(self, channel_id: int, question: str, options: list, duration: int = 1, allow_multiple: bool = False):
        async def _send():
            try:
                channel = self.get_channel(channel_id)
                if not channel:
                    print(f"[Poll] ERROR: Channel {channel_id} not found")
                    return

                poll = discord.Poll(
                    question=question,
                    duration=datetime.timedelta(hours=duration),
                    multiple=allow_multiple,
                )
                for opt in options:
                    poll.add_answer(text=opt)

                msg = await channel.send(poll=poll)
                print(f"[Poll] Sent native poll to #{channel.name} with {len(options)} options, {duration}h")

            except Exception as e:
                import traceback
                traceback.print_exc()
                print(f"[Poll] ERROR: {e}")
        try:
            asyncio.run_coroutine_threadsafe(_send(), self.loop)
        except Exception as e:
            print(f"[Poll] run_coroutine_threadsafe error: {e}")

    def close_ticket_channel(self, channel_id: int):
        async def _close():
            try:
                channel = self.get_channel(channel_id)
                if channel:
                    from database import get_session, ActiveTicket
                    print(f"[Tickets] Closing ticket channel #{channel.name}")
                    await channel.delete(reason="Ticket closed from dashboard")
                    sess = get_session()
                    try:
                        sess.query(ActiveTicket).filter_by(channel_id=channel_id).delete()
                        sess.commit()
                        print(f"[Tickets] Ticket closed, DB cleaned")
                    finally:
                        sess.close()
            except Exception as e:
                print(f"[Tickets] close ERROR: {e}")
        try:
            asyncio.run_coroutine_threadsafe(_close(), self.loop)
        except Exception as e:
            print(f"[Tickets] run_coroutine_threadsafe error: {e}")

    def send_ticket_panel(self, channel_id: int):
        async def _send():
            try:
                guild = self.guild
                if not guild:
                    print("[TicketPanel] ERROR: Guild not found")
                    return
                channel = discord.utils.get(guild.text_channels, id=channel_id)
                if not channel:
                    cached_ids = [c.id for c in guild.text_channels]
                    print(f"[TicketPanel] ERROR: Channel {channel_id} not found. Cached text channel IDs: {cached_ids}")
                    return
                from database import get_session, GuildSettings
                sess = get_session()
                try:
                    settings = sess.get(GuildSettings, GUILD_ID)
                    if not settings:
                        settings = GuildSettings(guild_id=GUILD_ID)
                        sess.add(settings)
                        sess.commit()

                    panel_title = settings.ticket_panel_title or "🎫 Support Tickets"
                    panel_desc = settings.ticket_panel_desc or "Click the button below to open a ticket."
                    button_text = settings.ticket_button_text or "Open Ticket"
                    embed_color = settings.ticket_embed_color or "#5865F2"
                    old_msg_id = settings.ticket_panel_message_id
                finally:
                    sess.close()

                from cogs.tickets import TicketView
                try:
                    hex_color = int(embed_color.lstrip("#"), 16)
                except ValueError:
                    hex_color = 0x5865F2
                embed = discord.Embed(
                    title=panel_title,
                    description=panel_desc,
                    color=hex_color,
                )
                embed.set_footer(text="D&T Server Support")

                # Delete old panel message if it exists
                if old_msg_id:
                    try:
                        old_msg = await channel.fetch_message(old_msg_id)
                        await old_msg.delete()
                        print(f"[TicketPanel] Deleted old panel message {old_msg_id}")
                    except (discord.NotFound, discord.Forbidden):
                        pass

                view = TicketView(button_text=button_text)
                msg = await channel.send(embed=embed, view=view)
                print(f"[TicketPanel] Sent to #{channel.name} (msg ID: {msg.id})")

                # Save new message ID and channel ID
                sess = get_session()
                try:
                    s = sess.get(GuildSettings, GUILD_ID)
                    if s:
                        s.ticket_panel_channel_id = channel_id
                        s.ticket_panel_message_id = msg.id
                        sess.commit()
                        print(f"[TicketPanel] Saved panel message ID {msg.id}")
                finally:
                    sess.close()
            except Exception as e:
                print(f"[TicketPanel] ERROR: {e}")

        try:
            asyncio.run_coroutine_threadsafe(_send(), self.loop)
        except Exception as e:
            print(f"[TicketPanel] run_coroutine_threadsafe error: {e}")

    def get_active_tickets(self):
        from database import get_session, ActiveTicket
        sess = get_session()
        try:
            tickets = sess.query(ActiveTicket).filter_by(guild_id=GUILD_ID).all()
            return [
                {
                    "id": t.id,
                    "channel_id": t.channel_id,
                    "user_id": t.user_id,
                    "opened_at": t.opened_at.isoformat() if t.opened_at else "",
                }
                for t in tickets
            ]
        finally:
            sess.close()

    def send_role_panel(self, channel_id: int, role_ids: list):
        async def _send():
            try:
                guild = self.guild
                if not guild:
                    print("[RolePanel] ERROR: Guild not found")
                    return
                channel = discord.utils.get(guild.text_channels, id=channel_id)
                if not channel:
                    print(f"[RolePanel] ERROR: Channel {channel_id} not found")
                    return
                role_map = {}
                for rid in role_ids:
                    role = guild.get_role(int(rid))
                    if role:
                        role_map[role.name] = role
                if not role_map:
                    print("[RolePanel] ERROR: No valid roles found")
                    return
                from cogs.autorole import ReactionRoleView
                embed = discord.Embed(
                    title="Self Roles",
                    description="Select a role from the dropdown below.\n\n" + "\n".join(f"• {r.mention}" for r in role_map.values()),
                    color=0x5865F2,
                )
                view = ReactionRoleView(role_map)
                await channel.send(embed=embed, view=view)
                print(f"[RolePanel] Sent to #{channel.name} with {len(role_map)} roles")
            except Exception as e:
                print(f"[RolePanel] ERROR: {e}")
        try:
            asyncio.run_coroutine_threadsafe(_send(), self.loop)
        except Exception as e:
            print(f"[RolePanel] run_coroutine_threadsafe error: {e}")
