import asyncio

import discord
from discord.ext import commands
from discord import app_commands

from database import get_session, GuildSettings, ActiveTicket as ActiveTicketModel
from utils.embeds import info, success, warning


class OpenTicketButton(discord.ui.Button):
    def __init__(self, label: str = "Open Ticket"):
        super().__init__(label=label, style=discord.ButtonStyle.primary, emoji="🎫", custom_id="dt_open_ticket")

    async def _get_settings(self, guild_id: int):
        sess = get_session()
        try:
            return sess.get(GuildSettings, guild_id) or GuildSettings(guild_id=guild_id)
        finally:
            sess.close()

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        settings = await self._get_settings(guild.id)

        sess = get_session()
        try:
            existing = sess.query(ActiveTicketModel).filter_by(user_id=interaction.user.id, guild_id=guild.id).first()
            if existing:
                await interaction.response.send_message(
                    embed=warning("Already Open", "You already have an open ticket."), ephemeral=True,
                )
                return

            category = guild.get_channel(settings.ticket_category_id) if settings.ticket_category_id else None
            if not category:
                category = discord.utils.get(guild.categories, name="Tickets")
            if not category:
                category = await guild.create_category("Tickets")

            support_role = guild.get_role(settings.ticket_support_role_id) if settings.ticket_support_role_id else None
            if not support_role:
                support_role = discord.utils.get(guild.roles, name="Support Team")
            if not support_role:
                support_role = await guild.create_role(name="Support Team", colour=discord.Colour.blue())

            if not settings.ticket_support_role_id:
                settings.ticket_support_role_id = support_role.id
                sess.commit()

            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
                support_role: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_messages=True),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True),
            }
            channel = await category.create_text_channel(
                f"ticket-{interaction.user.name.lower()}",
                overwrites=overwrites,
                topic=f"Support ticket for {interaction.user} (ID: {interaction.user.id})",
            )

            ticket = ActiveTicketModel(guild_id=guild.id, channel_id=channel.id, user_id=interaction.user.id)
            sess.add(ticket)
            sess.commit()

            await interaction.response.send_message(
                embed=success("Ticket Created", f"Your ticket has been opened in {channel.mention}."), ephemeral=True,
            )

            greet = info(
                f"Ticket — {interaction.user.display_name}",
                "Welcome! Please describe your issue.\nClick the 🔒 button to close this ticket when resolved.",
            )
            close_view = TicketCloseView()
            await channel.send(interaction.user.mention, embed=greet, view=close_view)
        finally:
            sess.close()


class TicketView(discord.ui.View):
    def __init__(self, button_text: str = "Open Ticket"):
        super().__init__(timeout=None)
        self.add_item(OpenTicketButton(button_text))


class TicketCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="dt_close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Closing this ticket in 5 seconds...", ephemeral=True)

        sess = get_session()
        try:
            ticket = sess.query(ActiveTicketModel).filter_by(channel_id=interaction.channel_id).first()
            if ticket:
                sess.delete(ticket)
                sess.commit()
        finally:
            sess.close()

        await asyncio.sleep(5)
        await interaction.channel.delete(reason="Ticket closed by user")


class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="setup-tickets", description="Create the ticket panel in this channel")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_tickets(self, interaction: discord.Interaction):
        sess = get_session()
        try:
            settings = sess.get(GuildSettings, interaction.guild_id)
            if not settings:
                settings = GuildSettings(guild_id=interaction.guild_id)
                sess.add(settings)
                sess.commit()
        finally:
            sess.close()

        embed = info(
            "🎫 Support Tickets",
            "Click the button below to open a support ticket.\nOur support team will assist you as soon as possible.",
            footer="D&T Server Support",
        )
        view = TicketView()
        await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message("✅ Ticket panel created! Click the button to test it.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
