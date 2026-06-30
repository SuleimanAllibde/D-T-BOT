import discord
from discord.ext import commands

from database import get_session, GuildSettings
from utils.embeds import warning
from utils.card_renderer import generate_card


class Welcome(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        settings = self._get_settings(member.guild.id)
        if not settings or not settings.welcome_enabled:
            return
        channel = member.guild.get_channel(settings.welcome_channel_id) if settings.welcome_channel_id else None
        if not channel:
            return

        asset = member.display_avatar.replace(size=256, format="png")
        data = await asset.read()
        
        # 🔥 التحقق الآمن من قيم قاعدة البيانات حتى لا تختلط قيمة 0 مع الـ None
        avatar_x = settings.avatar_x if settings.avatar_x is not None else 80
        avatar_y = settings.avatar_y if settings.avatar_y is not None else 86
        avatar_size = settings.avatar_size if settings.avatar_size is not None else 128

        image = await generate_card(
            data,
            avatar_x=avatar_x,
            avatar_y=avatar_y,
            avatar_size=avatar_size,
        )

        msg = settings.welcome_message or "Welcome {user} to **{server}**!"
        msg = self._format(msg, member)

        await channel.send(content=msg, file=discord.File(image, "welcome.jpg"))

        if settings.auto_role_id:
            role = member.guild.get_role(settings.auto_role_id)
            if role:
                try:
                    await member.add_roles(role, reason="Auto-role on join")
                except discord.Forbidden:
                    pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        settings = self._get_settings(member.guild.id)
        if not settings or not settings.leave_enabled:
            return
        channel = member.guild.get_channel(settings.leave_channel_id) if settings.leave_channel_id else None
        if not channel:
            return
        msg = settings.leave_message or "{user} has left {server}."
        msg = self._format(msg, member)
        embed = warning("Goodbye", msg, footer=f"Member #{len(member.guild.members)}")
        await channel.send(embed=embed)

    def _get_settings(self, guild_id: int):
        sess = get_session()
        try:
            return sess.get(GuildSettings, guild_id)
        finally:
            sess.close()

    def _format(self, text: str, member: discord.Member) -> str:
        return text.replace("{user}", member.mention)\
                   .replace("{server}", member.guild.name)\
                   .replace("{member_count}", str(len(member.guild.members)))\
                   .replace("{username}", member.name)\
                   .replace("{display_name}", member.display_name)


async def setup(bot: commands.Bot):
    await bot.add_cog(Welcome(bot))