import re
import asyncio
from datetime import timedelta

import discord
from discord.ext import commands
from discord import app_commands

from database import get_session, GuildSettings, Warning
from utils.embeds import success, warning, error, info

SPAM_LIMIT = 5
SPAM_WINDOW = 5


def parse_duration(text: str) -> timedelta | None:
    match = re.match(r"^(\d+)([smhd])$", text.strip().lower())
    if not match:
        return None
    val = int(match.group(1))
    unit = match.group(2)
    if unit == "s":
        return timedelta(seconds=val)
    elif unit == "m":
        return timedelta(minutes=val)
    elif unit == "h":
        return timedelta(hours=val)
    elif unit == "d":
        return timedelta(days=val)
    return None


def format_duration(td: timedelta) -> str:
    total = int(td.total_seconds())
    if total < 60:
        return f"{total}s"
    if total < 3600:
        return f"{total // 60}m"
    if total < 86400:
        return f"{total // 3600}h"
    return f"{total // 86400}d"


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

    # ---- Moderation Commands ----

    @app_commands.command(name="clear", description="Delete a number of messages")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def clear(self, interaction: discord.Interaction, amount: int):
        if amount < 1 or amount > 200:
            await interaction.response.send_message("Amount must be between 1 and 200.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount)
        await interaction.followup.send(
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

    @app_commands.command(name="timeout", description="Timeout a member (duration: 10m, 2h, 1d)")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def timeout(self, interaction: discord.Interaction, member: discord.Member, duration: str, reason: str = "No reason"):
        if not self._can_moderate(interaction.user, member):
            await interaction.response.send_message(embed=error("Error", "Cannot timeout that member."), ephemeral=True)
            return
        td = parse_duration(duration)
        if not td or td.total_seconds() < 1:
            await interaction.response.send_message("Invalid duration. Use format: `10s`, `10m`, `2h`, `1d`", ephemeral=True)
            return
        if td > timedelta(days=28):
            await interaction.response.send_message("Maximum timeout duration is 28 days.", ephemeral=True)
            return
        await member.timeout(td, reason=reason)
        await interaction.response.send_message(
            embed=success("Timed Out", f"{member.mention} timed out for **{format_duration(td)}**.\nReason: {reason}")
        )

    @app_commands.command(name="untimeout", description="Remove timeout from a member")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def untimeout(self, interaction: discord.Interaction, member: discord.Member):
        await member.timeout(None, reason="Manual untimeout")
        await interaction.response.send_message(embed=success("Untimed Out", f"Timeout removed from {member.mention}."))

    @app_commands.command(name="warn", description="Issue a warning to a member")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason"):
        if not self._can_moderate(interaction.user, member):
            await interaction.response.send_message(embed=error("Error", "Cannot warn that member."), ephemeral=True)
            return
        sess = get_session()
        try:
            w = Warning(
                guild_id=interaction.guild_id,
                user_id=member.id,
                moderator_id=interaction.user.id,
                reason=reason,
            )
            sess.add(w)
            sess.commit()
            count = sess.query(Warning).filter_by(guild_id=interaction.guild_id, user_id=member.id).count()
        finally:
            sess.close()
        await interaction.response.send_message(
            embed=success("Warned", f"{member.mention} has been warned.\nReason: {reason}\nTotal warnings: **{count}**")
        )

    @app_commands.command(name="warnings", description="View warnings for a member")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warnings(self, interaction: discord.Interaction, member: discord.Member):
        sess = get_session()
        try:
            warns = (
                sess.query(Warning)
                .filter_by(guild_id=interaction.guild_id, user_id=member.id)
                .order_by(Warning.created_at.desc())
                .all()
            )
        finally:
            sess.close()
        if not warns:
            await interaction.response.send_message(embed=info("Warnings", f"{member.mention} has no warnings."), ephemeral=True)
            return
        lines = []
        for i, w in enumerate(warns, 1):
            mod = interaction.guild.get_member(w.moderator_id)
            mod_name = mod.display_name if mod else f"ID: {w.moderator_id}"
            date = w.created_at.strftime("%Y-%m-%d %H:%M") if w.created_at else "Unknown"
            lines.append(f"**#{i}** — {w.reason}\n> Moderator: {mod_name} | {date}")
        embed = warning(
            f"Warnings for {member.display_name}",
            "\n\n".join(lines),
            footer=f"Total: {len(warns)} warning(s)",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="clear-warns", description="Clear all warnings for a member")
    @app_commands.checks.has_permissions(administrator=True)
    async def clear_warns(self, interaction: discord.Interaction, member: discord.Member):
        sess = get_session()
        try:
            count = sess.query(Warning).filter_by(guild_id=interaction.guild_id, user_id=member.id).delete()
            sess.commit()
        finally:
            sess.close()
        await interaction.response.send_message(
            embed=success("Warnings Cleared", f"Cleared **{count}** warning(s) for {member.mention}.")
        )

    @app_commands.command(name="lock", description="Lock a channel to prevent members from writing")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def lock(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        channel = channel or interaction.channel
        await channel.set_permissions(interaction.guild.default_role, send_messages=False)
        await interaction.response.send_message(
            embed=success("Locked", f"{channel.mention} has been locked.")
        )

    @app_commands.command(name="unlock", description="Unlock a channel")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def unlock(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        channel = channel or interaction.channel
        await channel.set_permissions(interaction.guild.default_role, send_messages=None)
        await interaction.response.send_message(
            embed=success("Unlocked", f"{channel.mention} has been unlocked.")
        )

    @app_commands.command(name="slowmode", description="Set slowmode delay for the current channel")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def slowmode(self, interaction: discord.Interaction, seconds: int):
        if seconds < 0 or seconds > 21600:
            await interaction.response.send_message("Slowmode must be between 0 and 21600 seconds (6 hours).", ephemeral=True)
            return
        await interaction.channel.edit(slowmode_delay=seconds)
        if seconds == 0:
            await interaction.response.send_message(embed=success("Slowmode", "Slowmode disabled."))
        else:
            await interaction.response.send_message(
                embed=success("Slowmode", f"Slowmode set to **{seconds}** second(s).")
            )

    @app_commands.command(name="nick", description="Change a member's nickname")
    @app_commands.checks.has_permissions(manage_nicknames=True)
    async def nick(self, interaction: discord.Interaction, member: discord.Member, nickname: str):
        if not self._can_moderate(interaction.user, member):
            await interaction.response.send_message(embed=error("Error", "Cannot change that member's nickname."), ephemeral=True)
            return
        old_nick = member.display_name
        await member.edit(nick=nickname)
        await interaction.response.send_message(
            embed=success("Nickname Changed", f"{member.mention}: **{old_nick}** → **{nickname}**")
        )

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
