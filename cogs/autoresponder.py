import discord
from discord.ext import commands

from database import get_session, AutoResponder as AutoResponderModel


class AutoResponder(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        sess = get_session()
        try:
            triggers = sess.query(AutoResponderModel).filter_by(guild_id=message.guild.id).all()
        finally:
            sess.close()

        content_lower = message.content.lower()
        for tr in triggers:
            if tr.trigger.lower() in content_lower:
                await message.channel.send(tr.response)
                return


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoResponder(bot))
