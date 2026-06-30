import discord

COLOR_PRIMARY = 0x5865F2    # Discord blurple
COLOR_SUCCESS = 0x57F287   # green
COLOR_WARNING = 0xFEE75C   # yellow
COLOR_ERROR   = 0xED4245   # red
COLOR_INFO    = 0x00A8FF   # blue


def primary(title, description="", fields=None, footer=None):
    embed = discord.Embed(title=title, description=description, color=COLOR_PRIMARY)
    _add_fields(embed, fields)
    if footer:
        embed.set_footer(text=footer)
    return embed


def success(title, description="", fields=None, footer=None):
    embed = discord.Embed(title=title, description=description, color=COLOR_SUCCESS)
    _add_fields(embed, fields)
    if footer:
        embed.set_footer(text=footer)
    return embed


def warning(title, description="", fields=None, footer=None):
    embed = discord.Embed(title=title, description=description, color=COLOR_WARNING)
    _add_fields(embed, fields)
    if footer:
        embed.set_footer(text=footer)
    return embed


def error(title, description="", fields=None, footer=None):
    embed = discord.Embed(title=title, description=description, color=COLOR_ERROR)
    _add_fields(embed, fields)
    if footer:
        embed.set_footer(text=footer)
    return embed


def info(title, description="", fields=None, footer=None):
    embed = discord.Embed(title=title, description=description, color=COLOR_INFO)
    _add_fields(embed, fields)
    if footer:
        embed.set_footer(text=footer)
    return embed


def _add_fields(embed, fields):
    if fields:
        for name, value, inline in fields:
            embed.add_field(name=name, value=value, inline=inline)
