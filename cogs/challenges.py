import asyncio
import random
import re
import time
from datetime import datetime

import aiohttp
import discord
from discord.ext import commands
from discord import app_commands

from database import get_session, ChallengeSetting, Challenge, ChallengeStarterCode as ChallengeStarterCodeModel, ChallengeTestCase, UserChallengeProgress, UserXP, ChallengeAchievement
from utils.embeds import primary, success, error
from utils.judge import run_code, outputs_match

LANGUAGES = ["C++", "Python", "JavaScript", "Java", "C#", "Go"]
DIFFICULTIES = ["Easy", "Medium", "Hard", "Expert"]

DIFF_ICONS = {"Easy": "🟢", "Medium": "🟡", "Hard": "🔴", "Expert": "💀"}
DIFF_STYLES = {
    "Easy": discord.ButtonStyle.success,
    "Medium": discord.ButtonStyle.primary,
    "Hard": discord.ButtonStyle.danger,
    "Expert": discord.ButtonStyle.danger,
}

LANGUAGE_DESCRIPTIONS = {
    "C++": "High-performance compiled language",
    "Python": "Readable, beginner-friendly language",
    "JavaScript": "Versatile web & scripting language",
    "Java": "Object-oriented JVM language",
    "C#": "Microsoft's .NET language",
    "Go": "Simple, concurrent language",
}

LANGUAGE_EMOJI_URLS = {
    "C++": "https://cdn.discordapp.com/attachments/1520569661538828308/1520571483938623488/c_plus_plus_satr.png",
    "Python": "https://cdn.discordapp.com/attachments/1520567681001066616/1520571271329611786/python_satr.png",
    "Java": "https://cdn.discordapp.com/attachments/1520570909386215534/1520570909696721008/c8e36fa1-c3e6-41c9-bb38-d1b1c36f3267.png",
    "JavaScript": "https://upload.wikimedia.org/wikipedia/commons/thumb/9/99/Unofficial_JavaScript_logo_2.svg/1200px-Unofficial_JavaScript_logo_2.svg.png",
    "C#": "https://cdn.discordapp.com/attachments/1520718782195171459/1520718782325325914/c_sharp_satr.png",
    "Go": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/05/Go_Logo_Blue.svg/1200px-Go_Logo_Blue.svg.png",
}

LANGUAGE_EMOJI_NAMES = {
    "C++": "dt_cpp",
    "Python": "dt_python",
    "Java": "dt_java",
    "JavaScript": "dt_js",
    "C#": "dt_csharp",
    "Go": "dt_go",
}

# Languages whose solutions require boilerplate (main/class wrapper) — these get
# a starter code. Scripting languages (Python, JavaScript) need none.
NEEDS_STARTER = {"C++", "Java", "C#", "Go"}

STARTER_TEMPLATES = {
    "C++": '#include <iostream>\nusing namespace std;\n\nint main() {\n    int n;\n    cin >> n;\n    cout << n << endl;\n    return 0;\n}\n',
    "Java": 'import java.util.*;\n\npublic class Main {\n    public static void main(String[] args) {\n        Scanner sc = new Scanner(System.in);\n        // write your solution here\n    }\n}\n',
    "C#": 'using System;\n\nclass Program {\n    static void Main() {\n        // write your solution here\n    }\n}\n',
    "Go": 'package main\n\nfunc main() {\n    // write your solution here\n}\n',
}

_emoji_cache = {}


async def _fetch_bytes(url: str):
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=12)) as resp:
            resp.raise_for_status()
            return await resp.read()


def _can_manage_emojis(guild: discord.Guild) -> bool:
    if not guild.me:
        return False
    perms = guild.me.guild_permissions
    return bool(getattr(perms, "manage_expressions", None) or getattr(perms, "manage_emojis", None))


async def resolve_language_emojis(guild: discord.Guild) -> dict:
    """Return {language: emoji_or_None}. Uses guild custom emojis when present,
    otherwise tries to upload the official language logos as custom emojis.
    Falls back to plain text (None) when unavailable."""
    if guild.id in _emoji_cache:
        return _emoji_cache[guild.id]
    result = {}
    can_create = _can_manage_emojis(guild)
    for lang in LANGUAGES:
        name = LANGUAGE_EMOJI_NAMES.get(lang)
        emoji = discord.utils.get(guild.emojis, name=name) if name else None
        if not emoji and can_create and lang in LANGUAGE_EMOJI_URLS:
            try:
                data = await _fetch_bytes(LANGUAGE_EMOJI_URLS[lang])
            except Exception:
                data = None
            if data:
                try:
                    emoji = await guild.create_custom_emoji(
                        name=name, image=data, reason="Programming Challenges language logo"
                    )
                except discord.HTTPException:
                    emoji = None
        result[lang] = emoji
    _emoji_cache[guild.id] = result
    return result


def get_challenge_setting(guild_id: int) -> ChallengeSetting:
    sess = get_session()
    try:
        s = sess.get(ChallengeSetting, guild_id)
        if not s:
            s = ChallengeSetting(guild_id=guild_id)
            sess.add(s)
            sess.commit()
        return s
    finally:
        sess.close()


_STARTER_SECTION_RE = re.compile(r"\*\*كود البداية[^\n]*\*\*\s*\n+```(?:cpp)?\s*\n.*?```\s*\n*", re.DOTALL)


def _strip_starter_section(text):
    """Remove the embedded 'كود البداية (C++):' code block from a description,
    since the per-language starter is already provided in the submit modal."""
    if not text:
        return text
    return _STARTER_SECTION_RE.sub("", text, count=1)


def build_challenge_embed(ch: Challenge, settings: ChallengeSetting, bot, language: str = None):
    try:
        color = int((settings.embed_color or "#5865F2").lstrip("#"), 16)
    except ValueError:
        color = 0x5865F2
    embed = discord.Embed(title=ch.title, description=_strip_starter_section((ch.description or "")[:4090]), color=color)
    if settings.thumbnail:
        embed.set_thumbnail(url=settings.thumbnail)
    embed.add_field(name="Difficulty", value=f"{DIFF_ICONS.get(ch.difficulty, '')} {ch.difficulty}", inline=True)
    embed.add_field(name="Language", value=language or ch.language or "Any", inline=True)
    embed.add_field(name="Category", value=ch.category or "—", inline=True)
    embed.add_field(name="XP Reward", value=f"**{ch.xp_reward} XP**", inline=True)
    embed.add_field(name="Estimated Time", value=ch.estimated_time or "—", inline=True)
    rate = round(ch.successful_attempts / ch.total_attempts * 100) if ch.total_attempts else 0
    embed.add_field(
        name="Statistics",
        value=f"⚡ {ch.total_attempts} attempts • ✅ {ch.successful_attempts} solved • {rate}% rate",
        inline=True,
    )
    embed.set_footer(text=settings.footer or "D&T Programming Challenges")
    if bot and bot.user:
        embed.set_author(name="Programming Challenges", icon_url=bot.user.display_avatar.url)
    return embed


def build_master_embed(settings: ChallengeSetting, bot):
    try:
        color = int((settings.embed_color or "#5865F2").lstrip("#"), 16)
    except ValueError:
        color = 0x5865F2
    embed = discord.Embed(
        title="💻 Programming Challenges",
        description=(
            "Pick a **programming language**, then choose a **difficulty** "
            "and you'll be given a **random challenge** to solve.\n\n"
            "Solve it to earn **XP** and **coins** and climb the leaderboard! 🏆"
        ),
        color=color,
    )
    if settings.thumbnail:
        embed.set_thumbnail(url=settings.thumbnail)
    embed.set_footer(text=settings.footer or "D&T Programming Challenges")
    if bot and bot.user:
        embed.set_author(name="Programming Challenges", icon_url=bot.user.display_avatar.url)
    return embed


def build_language_embed(language: str, settings: ChallengeSetting, bot, emoji=None):
    try:
        color = int((settings.embed_color or "#5865F2").lstrip("#"), 16)
    except ValueError:
        color = 0x5865F2
    emoji_str = f"{emoji} " if emoji else ""
    embed = discord.Embed(
        title=f"🎯 {emoji_str}{language} Challenges",
        description="Now select a **difficulty** and you'll get a random challenge in your language.",
        color=color,
    )
    if settings.thumbnail:
        embed.set_thumbnail(url=settings.thumbnail)
    embed.set_footer(text=settings.footer or "D&T Programming Challenges")
    if bot and bot.user:
        embed.set_author(name="Programming Challenges", icon_url=bot.user.display_avatar.url)
    return embed


def _pick_random_challenge(sess, guild_id: int, user_id: int, difficulty: str) -> Challenge:
    challenges = (
        sess.query(Challenge)
        .filter(Challenge.enabled.is_(True), Challenge.difficulty == difficulty)
        .order_by(Challenge.id.asc())
        .all()
    )
    if not challenges:
        return None
    solved_ids = {
        r.challenge_id
        for r in sess.query(UserChallengeProgress)
        .filter_by(guild_id=guild_id, user_id=user_id, solved=True)
        .all()
    }
    pool = [c for c in challenges if c.id not in solved_ids]
    return random.choice(pool or challenges)


def _get_challenge_languages(sess, challenge: Challenge) -> list:
    starter = {
        sc.language: sc.code
        for sc in sess.query(ChallengeStarterCodeModel).filter_by(challenge_id=challenge.id).all()
    }
    if starter:
        available = [l for l in LANGUAGES if l in starter]
        if available:
            return available
    if challenge.language in LANGUAGES:
        return [challenge.language]
    return LANGUAGES


def build_leaderboard_embed(guild, guild_id: int):
    sess = get_session()
    try:
        rows = sess.query(UserXP).filter_by(guild_id=guild_id).order_by(UserXP.xp.desc()).limit(10).all()
        lines = []
        medals = ["🥇", "🥈", "🥉"]
        for i, row in enumerate(rows):
            member = guild.get_member(row.user_id) if guild else None
            name = member.display_name if member else f"`{row.user_id}`"
            medal = medals[i] if i < 3 else f"`#{i + 1}`"
            lines.append(f"{medal} **{name}** — **{row.xp} XP** • 🪙 {row.coins} • {row.challenges_solved} solved")
        embed = primary("🏆 Challenge Leaderboard", "\n".join(lines) if lines else "No solvers yet — be the first!", footer="D&T Programming Challenges")
        embed.timestamp = datetime.utcnow()
        return embed
    finally:
        sess.close()


class DifficultyButton(discord.ui.Button):
    def __init__(self, difficulty: str):
        kwargs = {
            "label": difficulty,
            "style": DIFF_STYLES.get(difficulty, discord.ButtonStyle.primary),
            "custom_id": f"dt_chal_diff:{difficulty.lower()}",
        }
        if DIFF_ICONS.get(difficulty):
            kwargs["emoji"] = DIFF_ICONS[difficulty]
        super().__init__(**kwargs)

    async def callback(self, interaction: discord.Interaction):
        await self.view._on_difficulty(interaction, self.label)


class LanguageSelect(discord.ui.Select):
    def __init__(self, emoji_map: dict):
        options = []
        for lang in LANGUAGES:
            kwargs = {
                "label": lang,
                "value": lang,
                "description": LANGUAGE_DESCRIPTIONS.get(lang),
            }
            emoji = emoji_map.get(lang) if emoji_map else None
            if emoji:
                kwargs["emoji"] = emoji
            options.append(discord.SelectOption(**kwargs))
        super().__init__(
            placeholder="Select a programming language...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="dt_chal_lang",
        )

    async def callback(self, interaction: discord.Interaction):
        await self.view._on_language(interaction, self.values[0])


class ChallengeMasterView(discord.ui.View):
    """Persistent panel: pick a language -> difficulty -> random challenge."""

    def __init__(self, bot=None, emoji_map: dict = None):
        super().__init__(timeout=None)
        self.bot = bot
        self.add_item(LanguageSelect(emoji_map or {}))

    async def _on_language(self, interaction: discord.Interaction, language: str):
        sess = get_session()
        try:
            settings = sess.get(ChallengeSetting, interaction.guild_id)
            if not settings or not settings.enabled:
                await interaction.response.send_message("❌ Programming Challenges are currently disabled.", ephemeral=True)
                return
            total = sess.query(Challenge).filter_by(enabled=True).count()
        finally:
            sess.close()
        if not total:
            await interaction.response.send_message("❌ No enabled challenges found — create and enable at least one challenge first.", ephemeral=True)
            return
        emoji_map = await resolve_language_emojis(interaction.guild)
        embed = build_language_embed(language, settings, interaction.client, emoji_map.get(language))
        view = DifficultyButtonsView(interaction.user.id, language, bot=interaction.client)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class DifficultyButtonsView(discord.ui.View):
    """Per-user difficulty buttons shown after a language is picked."""

    def __init__(self, user_id: int, language: str, bot=None):
        super().__init__(timeout=900)
        self.user_id = user_id
        self.language = language
        self.bot = bot
        for d in ("Easy", "Medium", "Hard"):
            self.add_item(DifficultyButton(d))

    async def _on_difficulty(self, interaction: discord.Interaction, difficulty: str):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This challenge session belongs to another user.", ephemeral=True)
            return
        sess = get_session()
        try:
            settings = sess.get(ChallengeSetting, interaction.guild_id)
            if not settings or not settings.enabled:
                await interaction.response.send_message("❌ Programming Challenges are currently disabled.", ephemeral=True)
                return
            ch = _pick_random_challenge(sess, interaction.guild_id, interaction.user.id, difficulty)
            if not ch:
                await interaction.response.send_message(f"❌ No enabled challenges found for **{difficulty}**.", ephemeral=True)
                return
            embed = build_challenge_embed(ch, settings, self.bot or interaction.client, language=self.language)
            view = ChallengeSessionView(ch.id, self.language, ch, interaction.user.id)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        finally:
            sess.close()


class LegacyChallengeMasterView(discord.ui.View):
    """Backward-compatible persistent panel for messages sent before the
    language-select redesign (difficulty buttons only)."""

    def __init__(self, difficulties: list, bot=None):
        super().__init__(timeout=None)
        self.bot = bot
        for d in difficulties:
            self.add_item(DifficultyButton(d))

    async def _on_difficulty(self, interaction: discord.Interaction, difficulty: str):
        sess = get_session()
        try:
            settings = sess.get(ChallengeSetting, interaction.guild_id)
            if not settings or not settings.enabled:
                await interaction.response.send_message("❌ Programming Challenges are currently disabled.", ephemeral=True)
                return
            ch = _pick_random_challenge(sess, interaction.guild_id, interaction.user.id, difficulty)
            if not ch:
                await interaction.response.send_message(f"❌ No enabled challenges found for **{difficulty}**.", ephemeral=True)
                return
            languages = _get_challenge_languages(sess, ch)
            embed = build_challenge_embed(ch, settings, self.bot or interaction.client, language=languages[0])
            view = ChallengeSessionView(ch.id, languages[0], ch, interaction.user.id)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        finally:
            sess.close()


class ChallengeSessionView(discord.ui.View):
    def __init__(self, challenge_id: int, language: str, challenge: Challenge, user_id: int):
        super().__init__(timeout=900)
        self.challenge_id = challenge_id
        self.challenge = challenge
        self.language = language
        self.user_id = user_id
        self.selected_language = language
        self.start_time = time.time()

        button = discord.ui.Button(label="Submit Code", style=discord.ButtonStyle.success, emoji="📤", custom_id=f"dt_chal_submit:{challenge_id}")
        button.callback = self._on_submit
        self.add_item(button)

    async def _on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This session belongs to someone else.", ephemeral=True)
            return
        starter = ""
        if self.language in NEEDS_STARTER:
            starter = STARTER_TEMPLATES.get(self.language, "")
            sess = get_session()
            try:
                row = sess.query(ChallengeStarterCodeModel).filter_by(challenge_id=self.challenge.id, language=self.selected_language).first()
                if row and row.code:
                    starter = row.code
            finally:
                sess.close()
        modal = CodeSubmitModal(self.challenge, self.selected_language, starter, self.start_time, interaction.user.id, interaction.guild_id)
        await interaction.response.send_modal(modal)


class CodeSubmitModal(discord.ui.Modal, title="Submit your solution"):
    def __init__(self, challenge: Challenge, language: str, starter_code: str, start_time: float, user_id: int, guild_id: int):
        super().__init__(title=f"Submit — {challenge.challenge_key}")
        self.challenge = challenge
        self.language = language
        self.start_time = start_time
        self.user_id = user_id
        self.guild_id = guild_id
        self.code_input = discord.ui.TextInput(
            label="Your code",
            style=discord.TextStyle.paragraph,
            placeholder=f"Write your {language} solution here...",
            default=starter_code or "",
            required=True,
        )
        self.add_item(self.code_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        started = time.time()
        code = self.code_input.value

        result = await evaluate_challenge(self.challenge, code, self.language, self.user_id, self.guild_id, self.start_time)
        result["elapsed"] = round(time.time() - started, 1)

        embed = build_result_embed(result, self.challenge, interaction)
        try:
            await interaction.edit_original_response(embed=embed, view=None)
        except Exception:
            await interaction.followup.send(embed=embed, ephemeral=True)


async def evaluate_challenge(challenge: Challenge, code: str, language: str, user_id: int, guild_id: int, start_time: float):
    sess = get_session()
    try:
        test_cases = sess.query(ChallengeTestCase).filter_by(challenge_id=challenge.id).all()
        settings = {
            "ignore_trailing_spaces": challenge.ignore_trailing_spaces,
            "ignore_empty_lines": challenge.ignore_empty_lines,
            "case_sensitive": challenge.case_sensitive,
        }

        passed = 0
        total = len(test_cases)
        failure = None

        for i, tc in enumerate(test_cases):
            res = await asyncio.to_thread(
                run_code,
                language, code, tc.input or "",
                challenge.time_limit or 2, challenge.memory_limit or 256, challenge.max_code_size or 100000,
            )
            if not res.get("ok"):
                failure = {
                    "type": res.get("kind", "runtime"),
                    "hidden": tc.hidden,
                    "input": tc.input or "",
                    "expected": tc.expected_output or "",
                    "got": res.get("error") or res.get("stderr") or "",
                }
                break
            if outputs_match(res.get("output", ""), tc.expected_output or "", settings):
                passed += 1
            else:
                failure = {
                    "type": "wrong_answer",
                    "hidden": tc.hidden,
                    "input": tc.input or "",
                    "expected": tc.expected_output or "",
                    "got": res.get("output", ""),
                }
                break
            await asyncio.sleep(0.2)

        solved = total > 0 and passed == total
        elapsed = max(0.0, time.time() - start_time)

        challenge.total_attempts = (challenge.total_attempts or 0) + 1
        if solved:
            challenge.successful_attempts = (challenge.successful_attempts or 0) + 1
            prev = challenge.avg_solve_time or 0.0
            n = challenge.successful_attempts
            challenge.avg_solve_time = ((prev * (n - 1)) + elapsed) / n

        progress = sess.query(UserChallengeProgress).filter_by(guild_id=guild_id, user_id=user_id, challenge_id=challenge.id).first()
        was_solved = progress.solved if progress else False
        if not progress:
            progress = UserChallengeProgress(guild_id=guild_id, user_id=user_id, challenge_id=challenge.id)
            sess.add(progress)
        progress.attempts = (progress.attempts or 0) + 1
        if solved and not was_solved:
            progress.solved = True
            progress.solved_at = datetime.utcnow()
            progress.best_time = elapsed if progress.best_time is None else min(progress.best_time, elapsed)
        sess.commit()

        first_solve = solved and not was_solved
        xp_awarded = 0
        coins_awarded = 0
        achievement_unlocked = ""

        if first_solve:
            if challenge.xp_reward:
                up = sess.query(UserXP).filter_by(guild_id=guild_id, user_id=user_id).first()
                if not up:
                    up = UserXP(guild_id=guild_id, user_id=user_id)
                    sess.add(up)
                up.xp = (up.xp or 0) + challenge.xp_reward
                up.coins = (up.coins or 0) + challenge.coins_reward
                up.challenges_solved = (up.challenges_solved or 0) + 1
                xp_awarded = challenge.xp_reward
                coins_awarded = challenge.coins_reward

            if challenge.unlock_achievement:
                exists = sess.query(ChallengeAchievement).filter_by(guild_id=guild_id, user_id=user_id, name=challenge.unlock_achievement).first()
                if not exists:
                    sess.add(ChallengeAchievement(guild_id=guild_id, user_id=user_id, name=challenge.unlock_achievement))
                    achievement_unlocked = challenge.unlock_achievement
            sess.commit()

        return {
            "solved": solved,
            "passed": passed,
            "total": total,
            "failure": failure,
            "xp_awarded": xp_awarded,
            "coins_awarded": coins_awarded,
            "achievement": achievement_unlocked,
            "first_solve": first_solve,
            "unlock_next": challenge.unlock_next_challenge and first_solve,
            "best_time": progress.best_time if progress else None,
        }
    finally:
        sess.close()


def build_result_embed(result, challenge: Challenge, interaction: discord.Interaction):
    if result["solved"]:
        lines = []
        if result["total"]:
            lines.append(f"**{result['passed']}/{result['total']}** test cases passed")
        lines.append(f"⏱️ Solved in **{_fmt_time(result.get('elapsed') or 0)}**")
        if result["xp_awarded"]:
            lines.append(f"✨ **+{result['xp_awarded']} XP** • 🪙 **+{result['coins_awarded']} coins**")
        elif not result.get("first_solve"):
            lines.append("(Already solved — no additional XP)")
        if result.get("achievement"):
            lines.append(f"🏅 Achievement unlocked: **{result['achievement']}**")
        if result.get("unlock_next"):
            lines.append("🔓 You unlocked the **next challenge**!")
        embed = success("✅ Accepted", "\n".join(lines), footer=f"{challenge.challenge_key} • {challenge.title}")
        if interaction.client and interaction.client.user:
            embed.set_thumbnail(url=interaction.client.user.display_avatar.url)
        return embed

    f = result.get("failure") or {}
    if f.get("hidden"):
        embed = error("❌ Wrong Answer", "A **hidden** test case failed. Your code passes the visible cases but fails an edge case. Keep trying!")
    elif f.get("type") == "compile":
        embed = error("❌ Compilation Error", f"```\n{_clip(f.get('got') or '', 1800)}\n```")
    elif f.get("type") == "timeout":
        embed = error("❌ Time Limit Exceeded", f"Your solution exceeded the **{challenge.time_limit}s** time limit on a test case.")
    elif f.get("type") == "runtime":
        embed = error("❌ Runtime Error", f"```\n{_clip(f.get('got') or '', 1800)}\n```")
    else:
        embed = error("❌ Wrong Answer", "Your output does not match the expected output on this test case.")
        embed.add_field(name="Input", value=f"```{_clip(f.get('input', ''), 900)}```", inline=False)
        embed.add_field(name="Expected", value=f"```{_clip(f.get('expected', ''), 450)}```", inline=True)
        embed.add_field(name="Got", value=f"```{_clip(f.get('got', ''), 450)}```", inline=True)
    embed.add_field(name="Passed", value=f"{result['passed']}/{result['total']}", inline=True)
    embed.add_field(name="Time", value=f"{_fmt_time(result.get('elapsed') or 0)}", inline=True)
    embed.set_footer(text=f"{challenge.challenge_key} • {challenge.title}")
    return embed


def _fmt_time(seconds: float):
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    return f"{seconds // 60}m {seconds % 60}s"


def _clip(text, n=1000):
    text = text or ""
    return text[:n] + ("..." if len(text) > n else "")


def register_persistent_views(bot: commands.Bot):
    bot.add_view(ChallengeMasterView(bot=bot))
    bot.add_view(LegacyChallengeMasterView(DIFFICULTIES, bot=bot))


class Challenges(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def send_panels(self, channel_id: int):
        settings = None
        for g in self.bot.guilds:
            settings = get_challenge_setting(g.id)
            break
        if not settings:
            return {"error": "Programming Challenges are not configured yet"}
        if not settings.enabled:
            return {"error": "Programming Challenges are disabled — enable them in the dashboard first"}

        channel = self.bot.get_channel(channel_id)
        if not channel:
            return {"error": f"Channel {channel_id} not found — make sure the bot can see it"}

        sess = get_session()
        try:
            total = sess.query(Challenge).filter_by(enabled=True).count()
        finally:
            sess.close()

        if not total:
            return {"error": "No enabled challenges found — create and enable at least one challenge first"}

        emoji_map = await resolve_language_emojis(channel.guild)
        embed = build_master_embed(settings, self.bot)
        view = ChallengeMasterView(bot=self.bot, emoji_map=emoji_map)
        await channel.send(embed=embed, view=view)
        return {"success": True, "sent": len(LANGUAGES)}

    @app_commands.command(name="challenge-panel", description="Send the programming challenges panel to a channel")
    @app_commands.checks.has_permissions(administrator=True)
    async def challenge_panel(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        target = channel or interaction.channel
        settings = get_challenge_setting(interaction.guild_id)
        if not settings.enabled:
            await interaction.response.send_message("⚠️ Enable Programming Challenges in the dashboard first.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        result = await self.send_panels(target.id)
        if result.get("error"):
            await interaction.edit_original_response(content=f"❌ {result['error']}")
        else:
            await interaction.edit_original_response(content=f"✅ Sent the challenge panel to {target.mention}!")


async def setup(bot: commands.Bot):
    await bot.add_cog(Challenges(bot))
