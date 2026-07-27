import json

import discord
from discord.ext import commands

from database import get_session, GuildSettings, LogEntry
from utils.embeds import info, warning

LOG_TYPES = {
    "member_join": {"label": "Member Joined", "default_color": "#22c55e"},
    "member_leave": {"label": "Member Left", "default_color": "#ef4444"},
    "nickname_change": {"label": "Nickname Changed", "default_color": "#5865f2"},
    "role_add": {"label": "Role Added", "default_color": "#22c55e"},
    "role_remove": {"label": "Role Removed", "default_color": "#ef4444"},
    "message_delete": {"label": "Message Deleted", "default_color": "#ef4444"},
    "message_edit": {"label": "Message Edited", "default_color": "#eab308"},
    "voice_join": {"label": "Voice Joined", "default_color": "#22c55e"},
    "voice_leave": {"label": "Voice Left", "default_color": "#ef4444"},
    "invite_create": {"label": "Invite Created", "default_color": "#5865f2"},
}


class Logging(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _get_settings(self, guild_id: int):
        sess = get_session()
        try:
            return sess.get(GuildSettings, guild_id)
        finally:
            sess.close()

    def _get_log_settings(self, guild_id: int) -> dict:
        settings = self._get_settings(guild_id)
        if not settings or not settings.log_settings:
            return {}
        try:
            return json.loads(settings.log_settings)
        except Exception:
            return {}

    def _is_enabled(self, guild_id: int, log_type: str) -> bool:
        ls = self._get_log_settings(guild_id)
        if log_type not in ls:
            return True
        return ls[log_type].get("enabled", True)

    def _get_color(self, guild_id: int, log_type: str) -> int:
        ls = self._get_log_settings(guild_id)
        default_hex = LOG_TYPES.get(log_type, {}).get("default_color", "#5865f2")
        hex_str = ls.get(log_type, {}).get("color", default_hex)
        try:
            return int(hex_str.lstrip("#"), 16)
        except ValueError:
            return 0x5865f2

    def _add_log_entry(self, guild_id: int, event_type: str, description: str = None, user_id: int = None):
        sess = get_session()
        try:
            entry = LogEntry(guild_id=guild_id, event_type=event_type, description=description, user_id=user_id)
            sess.add(entry)
            sess.commit()
        finally:
            sess.close()

    async def _get_log_channel(self, guild: discord.Guild):
        settings = self._get_settings(guild.id)
        if settings and settings.log_channel_id:
            channel = guild.get_channel(settings.log_channel_id)
            if channel and channel.permissions_for(guild.me).send_messages:
                return channel
        return None

    def _make_embed(self, title: str, description: str, guild_id: int, log_type: str, footer: str = None):
        color = self._get_color(guild_id, log_type)
        embed = discord.Embed(title=title, description=description, color=color)
        if footer:
            embed.set_footer(text=footer)
        return embed

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        self._add_log_entry(member.guild.id, "member_join", f"{member} joined the server", member.id)
        if not self._is_enabled(member.guild.id, "member_join"):
            return
        channel = await self._get_log_channel(member.guild)
        if not channel:
            return
        embed = self._make_embed(
            "Member Joined",
            f"{member.mention} **{member}**\nAccount: <t:{int(member.created_at.timestamp())}:R>",
            member.guild.id, "member_join",
            footer=f"ID: {member.id}",
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        self._add_log_entry(member.guild.id, "member_leave", f"{member} left the server", member.id)
        if not self._is_enabled(member.guild.id, "member_leave"):
            return
        channel = await self._get_log_channel(member.guild)
        if not channel:
            return
        roles = ", ".join(r.mention for r in member.roles if r != member.guild.default_role) or "None"
        embed = self._make_embed(
            "Member Left",
            f"**{member}** ({member.mention})\nRoles: {roles}",
            member.guild.id, "member_leave",
            footer=f"ID: {member.id}",
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        channel = await self._get_log_channel(before.guild)
        if not channel:
            return
        if before.nick != after.nick:
            if self._is_enabled(before.guild.id, "nickname_change"):
                desc = f"**{before}**\nBefore: `{before.nick or before.name}`\nAfter: `{after.nick or after.name}`"
                self._add_log_entry(before.guild.id, "nickname_change", desc, before.id)
                embed = self._make_embed("Nickname Changed", desc, before.guild.id, "nickname_change")
                await channel.send(embed=embed)
        before_roles = set(before.roles)
        after_roles = set(after.roles)
        for role in after_roles - before_roles:
            if role != before.guild.default_role:
                self._add_log_entry(before.guild.id, "role_add", f"{after} was given {role.name}", before.id)
                if self._is_enabled(before.guild.id, "role_add"):
                    embed = self._make_embed("Role Added", f"{after.mention} was given {role.mention}", before.guild.id, "role_add")
                    await channel.send(embed=embed)
        for role in before_roles - after_roles:
            if role != before.guild.default_role:
                self._add_log_entry(before.guild.id, "role_remove", f"{after} lost {role.name}", before.id)
                if self._is_enabled(before.guild.id, "role_remove"):
                    embed = self._make_embed("Role Removed", f"{after.mention} lost {role.mention}", before.guild.id, "role_remove")
                    await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        desc = f"Author: {message.author}\nChannel: #{message.channel.name}"
        if message.content:
            desc += f"\nContent: {message.content[:500]}"
        self._add_log_entry(message.guild.id, "message_delete", desc, message.author.id)
        if not self._is_enabled(message.guild.id, "message_delete"):
            return
        channel = await self._get_log_channel(message.guild)
        if not channel:
            return
        embed = self._make_embed(
            "Message Deleted",
            f"**Author:** {message.author.mention}\n**Channel:** {message.channel.mention}",
            message.guild.id, "message_delete",
            footer=f"ID: {message.id}",
        )
        if message.content:
            embed.description += f"\n**Content:**\n{message.content[:1000]}"
        if message.attachments:
            embed.description += f"\n**Attachments:** `{len(message.attachments)} file(s)`"
        await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot or not before.guild or before.content == after.content:
            return
        desc = f"Author: {before.author}\nChannel: #{before.channel.name}\nBefore: {before.content[:300]}\nAfter: {after.content[:300]}"
        self._add_log_entry(before.guild.id, "message_edit", desc, before.author.id)
        if not self._is_enabled(before.guild.id, "message_edit"):
            return
        channel = await self._get_log_channel(before.guild)
        if not channel:
            return
        embed = self._make_embed(
            "Message Edited",
            f"**Author:** {before.author.mention}\n**Channel:** {before.channel.mention}\n**Before:**\n{before.content[:900]}\n**After:**\n{after.content[:900]}",
            before.guild.id, "message_edit",
            footer=f"ID: {before.id}",
        )
        await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if before.channel == after.channel:
            return
        if after.channel:
            self._add_log_entry(member.guild.id, "voice_join", f"{member} joined voice channel {after.channel.name}", member.id)
            if self._is_enabled(member.guild.id, "voice_join"):
                channel = await self._get_log_channel(member.guild)
                if channel:
                    embed = self._make_embed("Voice Joined", f"{member.mention} joined **{after.channel.name}**", member.guild.id, "voice_join")
                    await channel.send(embed=embed)
        elif before.channel:
            self._add_log_entry(member.guild.id, "voice_leave", f"{member} left voice channel {before.channel.name}", member.id)
            if self._is_enabled(member.guild.id, "voice_leave"):
                channel = await self._get_log_channel(member.guild)
                if channel:
                    embed = self._make_embed("Voice Left", f"{member.mention} left **{before.channel.name}**", member.guild.id, "voice_leave")
                    await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        inviter = invite.inviter.mention if invite.inviter else "Unknown"
        desc = f"Invite {invite.code} created by {inviter}"
        self._add_log_entry(invite.guild.id, "invite_create", desc, invite.inviter.id if invite.inviter else None)
        if not self._is_enabled(invite.guild.id, "invite_create"):
            return
        channel = await self._get_log_channel(invite.guild)
        if not channel:
            return
        embed = self._make_embed(
            "Invite Created",
            f"**Code:** {invite.code}\n**Created by:** {inviter}\n**Max uses:** {invite.max_uses or 'Unlimited'}",
            invite.guild.id, "invite_create",
        )
        await channel.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Logging(bot))
