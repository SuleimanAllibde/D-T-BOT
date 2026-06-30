import re
import asyncio
from datetime import timedelta

import discord
from discord.ext import commands
from discord import app_commands

from database import get_session, GuildSettings
from utils.embeds import success, warning, error

SPAM_LIMIT = 5
SPAM_WINDOW = 5


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._recent = {}

    def _get_settings(self, guild_id: int):
        sess = get_session()
        try:
            return sess.get(GuildSettings, guild_id)
        finally:
            sess.close()

    def _can_moderate(self, member: discord.Member, target: discord.Member) -> bool:
        if target.top_role >= member.top_role and member != member.guild.owner:
            return False
        return True

    def _bypasses_automod(self, member: discord.Member, settings: GuildSettings) -> bool:
        if not settings.automod_bypass_roles:
            return False
        bypass_ids = [int(r.strip()) for r in settings.automod_bypass_roles.split(",") if r.strip().isdigit()]
        return any(role.id in bypass_ids for role in member.roles)

    async def _apply_penalty(self, member: discord.Member, reason: str, settings: GuildSettings):
        penalty = settings.automod_penalty or "mute"
        try:
            if penalty == "kick":
                await member.kick(reason=reason)
            elif penalty == "ban":
                await member.ban(reason=reason)
            else:
                await member.timeout(timedelta(minutes=10), reason=reason)
        except discord.Forbidden:
            pass

    async def _has_link(self, content: str) -> bool:
        pattern = r"(https?://[^\s]+)"
        return bool(re.search(pattern, content))

    # ---- Slash Commands ----

    @app_commands.command(name="clear", description="Delete a number of messages")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def clear(self, interaction: discord.Interaction, amount: int):
        if amount < 1 or amount > 200:
            await interaction.response.send_message("Amount must be between 1 and 200.", ephemeral=True)
            return
        deleted = await interaction.channel.purge(limit=amount)
        await interaction.response.send_message(
            embed=success("Cleared", f"Deleted {len(deleted)} messages."), ephemeral=True,
        )

    @app_commands.command(name="kick", description="Kick a member")
    @app_commands.checks.has_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason"):
        if not self._can_moderate(interaction.user, member):
            await interaction.response.send_message(embed=error("Error", "Cannot kick that member."), ephemeral=True)
            return
        await member.kick(reason=reason)
        await interaction.response.send_message(embed=success("Kicked", f"{member.mention} has been kicked.\nReason: {reason}"))

    @app_commands.command(name="ban", description="Ban a member")
    @app_commands.checks.has_permissions(ban_members=True)
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason"):
        if not self._can_moderate(interaction.user, member):
            await interaction.response.send_message(embed=error("Error", "Cannot ban that member."), ephemeral=True)
            return
        await member.ban(reason=reason)
        await interaction.response.send_message(embed=success("Banned", f"{member.mention} has been banned.\nReason: {reason}"))

    @app_commands.command(name="mute", description="Timeout a member")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def mute(self, interaction: discord.Interaction, member: discord.Member, minutes: int = 10, reason: str = "No reason"):
        if not self._can_moderate(interaction.user, member):
            await interaction.response.send_message(embed=error("Error", "Cannot mute that member."), ephemeral=True)
            return
        await member.timeout(timedelta(minutes=minutes), reason=reason)
        await interaction.response.send_message(embed=success("Muted", f"{member.mention} muted for {minutes}m.\nReason: {reason}"))

    @app_commands.command(name="unmute", description="Remove timeout")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def unmute(self, interaction: discord.Interaction, member: discord.Member):
        await member.timeout(None, reason="Manual unmute")
        await interaction.response.send_message(embed=success("Unmuted", f"{member.mention} unmuted."))

    # ---- Chat Filter (on_message) ----

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        settings = self._get_settings(message.guild.id)
        if not settings:
            return

        if self._bypasses_automod(message.author, settings):
            return

        # Anti bad words
        if settings.anti_bad_words:
            bad_words = ["fuck", "shit", "ass", "damn", "bitch", "crap", "dick", "piss", "slut", "whore"]
            content_lower = message.content.lower()
            for word in bad_words:
                if re.search(rf"\b{re.escape(word)}\b", content_lower):
                    await message.delete()
                    await message.channel.send(
                        embed=warning("Filtered", f"{message.author.mention} inappropriate language is not allowed."),
                        delete_after=5,
                    )
                    await self._apply_penalty(message.author, "Bad word detected", settings)
                    return

        # Anti links
        if settings.anti_links and await self._has_link(message.content):
            await message.delete()
            await message.channel.send(
                embed=warning("Filtered", f"{message.author.mention} links are not allowed in this server."),
                delete_after=5,
            )
            await self._apply_penalty(message.author, "Link detected", settings)
            return

        # Anti spam
        if settings.anti_spam:
            now = message.created_at.timestamp()
            user_msgs = self._recent.setdefault(message.author.id, [])
            user_msgs.append(now)
            self._recent[message.author.id] = [t for t in user_msgs if now - t < SPAM_WINDOW]
            if len(self._recent[message.author.id]) > SPAM_LIMIT:
                await self._apply_penalty(message.author, "Spam detected", settings)
                await message.channel.send(
                    embed=warning("Spam", f"{message.author.mention} has been penalized for spamming."),
                )
                return


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
