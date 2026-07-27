import time
import collections

import discord
from discord.ext import commands
from discord import app_commands

from database import get_session, GuildSettings, SecurityLimit, SecurityWhitelist
from utils.embeds import error, warning


ACTION_TYPES = {
    "ban": "Ban",
    "kick": "Kick",
    "mute": "Timeout",
    "channel_create": "Channel Created",
    "channel_delete": "Channel Deleted",
    "role_create": "Role Created",
    "role_delete": "Role Deleted",
}

PUNISHMENTS = {
    "ban": "Ban Actor",
    "kick": "Kick Actor",
    "remove_roles": "Remove All Roles",
    "timeout_1h": "Timeout Actor (1h)",
    "lockdown": "Server Lockdown",
}


class Security(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._action_log = collections.defaultdict(lambda: collections.deque())
        self._triggered = set()

    def _is_whitelisted(self, member: discord.Member) -> bool:
        sess = get_session()
        try:
            wl = sess.query(SecurityWhitelist).filter_by(guild_id=member.guild.id).all()
            for entry in wl:
                if entry.entity_type == "user" and entry.entity_id == member.id:
                    return True
                if entry.entity_type == "role":
                    if any(r.id == entry.entity_id for r in member.roles):
                        return True
        finally:
            sess.close()
        return False

    def _log_action(self, guild_id: int, actor_id: int, action_type: str):
        key = (guild_id, actor_id, action_type)
        now = time.time()
        self._action_log[key].append(now)

    def _get_count(self, guild_id: int, actor_id: int, action_type: str, window_seconds: int) -> int:
        key = (guild_id, actor_id, action_type)
        now = time.time()
        self._action_log[key] = collections.deque(
            t for t in self._action_log[key] if now - t < window_seconds
        )
        return len(self._action_log[key])

    def _get_limits(self, guild_id: int) -> list:
        sess = get_session()
        try:
            return sess.query(SecurityLimit).filter_by(guild_id=guild_id).all()
        finally:
            sess.close()

    async def _execute_punishment(self, member: discord.Member, punishment: str):
        try:
            if punishment == "ban":
                await member.ban(reason="Security limit exceeded")
            elif punishment == "kick":
                await member.kick(reason="Security limit exceeded")
            elif punishment == "remove_roles":
                from discord import utils
                below = [r for r in member.roles[1:] if r < member.guild.me.top_role]
                if below:
                    await member.remove_roles(*below, reason="Security limit exceeded")
            elif punishment == "timeout_1h":
                from datetime import timedelta
                await member.timeout(timedelta(hours=1), reason="Security limit exceeded")
            elif punishment == "lockdown":
                for ch in member.guild.text_channels:
                    try:
                        await ch.set_permissions(member.guild.default_role, send_messages=False)
                    except Exception:
                        pass
        except discord.Forbidden:
            pass

    async def _check_limit(self, member: discord.Member, action_type: str):
        if self._is_whitelisted(member):
            return

        limits = self._get_limits(member.guild.id)
        for limit in limits:
            if not limit.enabled or limit.action_type != action_type:
                continue
            window = limit.time_window * 60
            count = self._get_count(member.guild.id, member.id, action_type, window)
            trigger_key = (member.guild.id, member.id, action_type, limit.id)
            if count >= limit.max_count:
                if trigger_key not in self._triggered:
                    self._triggered.add(trigger_key)
                    print(f"[Security] {member} exceeded {action_type} limit ({count}/{limit.max_count} in {limit.time_window}m). Punishment: {limit.punishment}")
                    await self._execute_punishment(member, limit.punishment)
                    try:
                        await member.guild.system_channel.send(
                            embed=warning(
                                "Security Triggered",
                                f"{member.mention} exceeded the **{ACTION_TYPES.get(action_type, action_type)}** limit "
                                f"({count} actions in {limit.time_window} min).\n"
                                f"Punishment: **{PUNISHMENTS.get(limit.punishment, limit.punishment)}**",
                            )
                        )
                    except Exception:
                        pass
                return

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.ban):
            if entry.target.id == user.id and entry.user.id != self.bot.user.id:
                self._log_action(guild.id, entry.user.id, "ban")
                member = guild.get_member(entry.user.id)
                if member:
                    await self._check_limit(member, "ban")
                break

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        try:
            entry = await member.guild.audit_logs(limit=1, action=discord.AuditLogAction.kick).flatten()
            if entry and entry[0].target.id == member.id and entry[0].user.id != self.bot.user.id:
                actor = member.guild.get_member(entry[0].user.id)
                if actor:
                    self._log_action(member.guild.id, actor.id, "kick")
                    await self._check_limit(actor, "kick")
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        try:
            async for entry in channel.guild.audit_logs(limit=5, action=discord.AuditLogAction.channel_delete):
                if entry.target.id == channel.id and entry.user.id != self.bot.user.id:
                    self._log_action(channel.guild.id, entry.user.id, "channel_delete")
                    member = channel.guild.get_member(entry.user.id)
                    if member:
                        await self._check_limit(member, "channel_delete")
                    break
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        try:
            async for entry in channel.guild.audit_logs(limit=5, action=discord.AuditLogAction.channel_create):
                if entry.target.id == channel.id and entry.user.id != self.bot.user.id:
                    self._log_action(channel.guild.id, entry.user.id, "channel_create")
                    member = channel.guild.get_member(entry.user.id)
                    if member:
                        await self._check_limit(member, "channel_create")
                    break
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        try:
            async for entry in role.guild.audit_logs(limit=5, action=discord.AuditLogAction.role_delete):
                if entry.target.id == role.id and entry.user.id != self.bot.user.id:
                    self._log_action(role.guild.id, entry.user.id, "role_delete")
                    member = role.guild.get_member(entry.user.id)
                    if member:
                        await self._check_limit(member, "role_delete")
                    break
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        try:
            async for entry in role.guild.audit_logs(limit=5, action=discord.AuditLogAction.role_create):
                if entry.target.id == role.id and entry.user.id != self.bot.user.id:
                    self._log_action(role.guild.id, entry.user.id, "role_create")
                    member = role.guild.get_member(entry.user.id)
                    if member:
                        await self._check_limit(member, "role_create")
                    break
        except Exception:
            pass

    @app_commands.command(name="security-status", description="Show security limits status")
    @app_commands.checks.has_permissions(administrator=True)
    async def security_status(self, interaction: discord.Interaction):
        limits = self._get_limits(interaction.guild_id)
        if not limits:
            await interaction.response.send_message("No security limits configured.", ephemeral=True)
            return
        lines = []
        for l in limits:
            status = "ON" if l.enabled else "OFF"
            lines.append(
                f"**{ACTION_TYPES.get(l.action_type, l.action_type)}** [{status}]\n"
                f"→ Max {l.max_count} actions in {l.time_window} min → **{PUNISHMENTS.get(l.punishment, l.punishment)}**"
            )
        from utils.embeds import info
        await interaction.response.send_message(embed=info("Security Limits", "\n\n".join(lines)), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Security(bot))
