import asyncio

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

    async def setup_hook(self):
        await self.load_extension("cogs.welcome")
        await self.load_extension("cogs.moderation")
        await self.load_extension("cogs.autorole")
        await self.load_extension("cogs.tickets")
        await self.load_extension("cogs.logging")
        await self.load_extension("cogs.autoresponder")

        guild = discord.Object(id=GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)

        # Register persistent views for ticket system
        from cogs.tickets import TicketView, TicketCloseView
        self.add_view(TicketView())
        self.add_view(TicketCloseView())

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
                    kwargs["file"] = discord.File(file_path)
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
                    kwargs["file"] = discord.File(file_path)
                await channel.send(**kwargs)
                print(f"[Message] Sent to #{channel.name}")
            except Exception as e:
                print(f"[Message] ERROR: {e}")
        try:
            asyncio.run_coroutine_threadsafe(_send(), self.loop)
        except Exception as e:
            print(f"[Message] run_coroutine_threadsafe error: {e}")

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
                    old_msg_id = settings.ticket_panel_message_id
                finally:
                    sess.close()

                from cogs.tickets import TicketView
                embed = discord.Embed(
                    title=panel_title,
                    description=panel_desc,
                    color=0x5865F2,
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
