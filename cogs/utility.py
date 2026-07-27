import datetime

import discord
from discord.ext import commands
from discord import app_commands

from utils.embeds import primary, info


class Utility(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ping", description="Show bot latency")
    async def ping(self, interaction: discord.Interaction):
        ws_ms = round(self.bot.latency * 1000)
        db_start = datetime.datetime.utcnow()
        from database import get_session
        sess = get_session()
        try:
            sess.execute("SELECT 1" if hasattr(sess, 'execute') else "")
        except Exception:
            pass
        finally:
            sess.close()
        db_ms = round((datetime.datetime.utcnow() - db_start).total_seconds() * 1000)

        embed = primary(
            "Pong! 🏓",
            fields=[
                ("WebSocket", f"**{ws_ms}ms**", True),
                ("Database", f"**{db_ms}ms**", True),
            ],
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="userinfo", description="Show information about a member")
    async def userinfo(self, interaction: discord.Interaction, member: discord.Member = None):
        member = member or interaction.user
        top_role = member.top_role if member.top_role != interaction.guild.default_role else None
        roles = [r.mention for r in reversed(member.roles[1:])]

        embed = info(
            member.display_name,
            f"**{member}** (ID: {member.id})",
            fields=[
                ("Joined Server", f"<t:{int(member.joined_at.timestamp())}:R>" if member.joined_at else "Unknown", True),
                ("Joined Discord", f"<t:{int(member.created_at.timestamp())}:R>" if member.created_at else "Unknown", True),
                ("Top Role", top_role.mention if top_role else "None", True),
                ("Roles", " ".join(roles[:20]) if roles else "None", False),
            ],
            footer=f"Member #{interaction.guild.member_count}",
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="avatar", description="Show a member's avatar")
    async def avatar(self, interaction: discord.Interaction, member: discord.Member = None):
        member = member or interaction.user
        url = member.display_avatar.replace(size=1024).url
        embed = info(
            f"{member.display_name}'s Avatar",
            f"[Download]({url})",
        )
        embed.set_image(url=url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="banner", description="Show a member's banner")
    async def banner(self, interaction: discord.Interaction, member: discord.Member = None):
        member = member or interaction.user
        user = await self.bot.fetch_user(member.id)
        if not user.banner:
            await interaction.response.send_message(f"{member.display_name} has no banner.", ephemeral=True)
            return
        url = user.banner.replace(size=1024).url
        embed = info(
            f"{member.display_name}'s Banner",
            f"[Download]({url})",
        )
        embed.set_image(url=url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="roleinfo", description="Show information about a role")
    async def roleinfo(self, interaction: discord.Interaction, role: discord.Role):
        members_with = len(role.members)
        perms = [perm[0].replace("_", " ").title() for perm in role.permissions if perm[1]]
        embed = info(
            role.name,
            f"ID: {role.id}",
            fields=[
                ("Members", f"**{members_with}**", True),
                ("Color", f"**{role.color}**", True),
                ("Mentionable", "Yes" if role.mentionable else "No", True),
                ("Hoisted", "Yes" if role.hoist else "No", True),
                ("Permissions", ", ".join(perms[:15]) if perms else "None", False),
            ],
        )
        embed.set_thumbnail(url=role.guild.icon.url if role.guild.icon else None)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Utility(bot))
