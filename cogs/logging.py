import discord
from discord.ext import commands

from database import get_session, GuildSettings, LogEntry
from utils.embeds import info, warning


class Logging(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _get_settings(self, guild_id: int):
        sess = get_session()
        try:
            return sess.get(GuildSettings, guild_id)
        finally:
            sess.close()

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

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        self._add_log_entry(member.guild.id, "member_join", f"{member} joined the server", member.id)
        channel = await self._get_log_channel(member.guild)
        if not channel:
            return
        embed = info("Member Joined", f"{member.mention} **{member}**\nAccount: <t:{int(member.created_at.timestamp())}:R>", footer=f"ID: {member.id}")
        embed.set_thumbnail(url=member.display_avatar.url)
        await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        self._add_log_entry(member.guild.id, "member_leave", f"{member} left the server", member.id)
        channel = await self._get_log_channel(member.guild)
        if not channel:
            return
        roles = ", ".join(r.mention for r in member.roles if r != member.guild.default_role) or "None"
        embed = warning("Member Left", f"**{member}** ({member.mention})\nRoles: {roles}", footer=f"ID: {member.id}")
        embed.set_thumbnail(url=member.display_avatar.url)
        await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        channel = await self._get_log_channel(before.guild)
        if not channel:
            return
        if before.nick != after.nick:
            desc = f"**{before}**\nBefore: `{before.nick or before.name}`\nAfter: `{after.nick or after.name}`"
            self._add_log_entry(before.guild.id, "nickname_change", desc, before.id)
            await channel.send(embed=info("Nickname Changed", desc))
        before_roles = set(before.roles)
        after_roles = set(after.roles)
        for role in after_roles - before_roles:
            if role != before.guild.default_role:
                self._add_log_entry(before.guild.id, "role_add", f"{after} was given {role.name}", before.id)
                await channel.send(embed=info("Role Added", f"{after.mention} was given {role.mention}"))
        for role in before_roles - after_roles:
            if role != before.guild.default_role:
                self._add_log_entry(before.guild.id, "role_remove", f"{after} lost {role.name}", before.id)
                await channel.send(embed=warning("Role Removed", f"{after.mention} lost {role.mention}"))

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        desc = f"Author: {message.author}\nChannel: #{message.channel.name}"
        if message.content:
            desc += f"\nContent: {message.content[:500]}"
        self._add_log_entry(message.guild.id, "message_delete", desc, message.author.id)
        channel = await self._get_log_channel(message.guild)
        if not channel:
            return
        embed = warning("Message Deleted", f"**Author:** {message.author.mention}\n**Channel:** {message.channel.mention}", footer=f"ID: {message.id}")
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
        channel = await self._get_log_channel(before.guild)
        if not channel:
            return
        embed = info("Message Edited", f"**Author:** {before.author.mention}\n**Channel:** {before.channel.mention}\n**Before:**\n{before.content[:900]}\n**After:**\n{after.content[:900]}", footer=f"ID: {before.id}")
        await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if before.channel == after.channel:
            return
        channel = await self._get_log_channel(member.guild)
        if after.channel:
            desc = f"{member} joined voice channel {after.channel.name}"
            self._add_log_entry(member.guild.id, "voice_join", desc, member.id)
            if channel:
                await channel.send(embed=info("Voice Joined", f"{member.mention} joined **{after.channel.name}**"))
        elif before.channel:
            desc = f"{member} left voice channel {before.channel.name}"
            self._add_log_entry(member.guild.id, "voice_leave", desc, member.id)
            if channel:
                await channel.send(embed=info("Voice Left", f"{member.mention} left **{before.channel.name}**"))

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        inviter = invite.inviter.mention if invite.inviter else "Unknown"
        desc = f"Invite {invite.code} created by {inviter}"
        self._add_log_entry(invite.guild.id, "invite_create", desc, invite.inviter.id if invite.inviter else None)
        channel = await self._get_log_channel(invite.guild)
        if not channel:
            return
        embed = info("Invite Created", f"**Code:** {invite.code}\n**Created by:** {inviter}\n**Max uses:** {invite.max_uses or 'Unlimited'}")
        await channel.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Logging(bot))
