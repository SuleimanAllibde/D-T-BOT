import discord
from discord.ext import commands
from discord import app_commands

from database import get_session, GuildSettings
from utils.embeds import success, info


class ReactionRoleDropdown(discord.ui.Select):
    def __init__(self, role_map: dict):
        options = [
            discord.SelectOption(label=r.name, value=str(r.id))
            for r in role_map.values() if r
        ]
        super().__init__(placeholder="Choose a role...", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        role_id = int(self.values[0])
        role = interaction.guild.get_role(role_id)
        if not role:
            await interaction.response.send_message("Role not found.", ephemeral=True)
            return
        if role in interaction.user.roles:
            await interaction.user.remove_roles(role, reason="Reaction role removed")
            await interaction.response.send_message(f"Removed {role.mention}.", ephemeral=True)
        else:
            await interaction.user.add_roles(role, reason="Reaction role added")
            await interaction.response.send_message(f"Added {role.mention}.", ephemeral=True)


class AutoRole(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="set-autorole", description="Set the default role for new members")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_autorole(self, interaction: discord.Interaction, role: discord.Role):
        sess = get_session()
        try:
            s = sess.get(GuildSettings, interaction.guild_id)
            if not s:
                s = GuildSettings(guild_id=interaction.guild_id)
                sess.add(s)
            s.auto_role_id = role.id
            sess.commit()
        finally:
            sess.close()
        await interaction.response.send_message(embed=success("Auto-Role Set", f"New members will get {role.mention}."))

    @app_commands.command(name="remove-autorole", description="Remove auto-role")
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_autorole(self, interaction: discord.Interaction):
        sess = get_session()
        try:
            s = sess.get(GuildSettings, interaction.guild_id)
            if s:
                s.auto_role_id = None
                sess.commit()
        finally:
            sess.close()
        await interaction.response.send_message(embed=success("Auto-Role Removed", "Auto-role disabled."))

    @app_commands.command(name="reaction-role", description="Create a reaction role panel")
    @app_commands.checks.has_permissions(administrator=True)
    async def reaction_role(self, interaction: discord.Interaction, role1: discord.Role, role2: discord.Role = None, role3: discord.Role = None, role4: discord.Role = None, role5: discord.Role = None):
        roles = {r.name: r for r in [role1, role2, role3, role4, role5] if r is not None}
        embed = info("Reaction Roles", "Select a role from the dropdown below.\n\n" + "\n".join(f"• {r.mention}" for r in roles.values()))
        view = discord.ui.View(timeout=None)
        view.add_item(ReactionRoleDropdown(roles))
        await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message("Reaction role panel created!", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoRole(bot))
