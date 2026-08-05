import asyncio
import random
import time
from datetime import datetime

import discord
from discord.ext import commands
from discord import app_commands

from database import get_session, ChallengeSetting, Challenge, ChallengeStarterCode as ChallengeStarterCodeModel, ChallengeTestCase, UserChallengeProgress, UserXP, ChallengeAchievement
from utils.embeds import primary, success, error
from utils.judge import run_code, outputs_match

LANGUAGES = ["C++", "Python", "JavaScript", "Java", "C#", "Go", "Rust"]
DIFFICULTIES = ["Easy", "Medium", "Hard", "Expert"]

DIFF_ICONS = {"Easy": "🟢", "Medium": "🟡", "Hard": "🔴", "Expert": "💀"}
DIFF_STYLES = {
    "Easy": discord.ButtonStyle.success,
    "Medium": discord.ButtonStyle.primary,
    "Hard": discord.ButtonStyle.danger,
    "Expert": discord.ButtonStyle.danger,
}


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


def build_challenge_embed(ch: Challenge, settings: ChallengeSetting, bot):
    try:
        color = int((settings.embed_color or "#5865F2").lstrip("#"), 16)
    except ValueError:
        color = 0x5865F2
    embed = discord.Embed(title=ch.title, description=(ch.description or "")[:4090], color=color)
    if settings.thumbnail:
        embed.set_thumbnail(url=settings.thumbnail)
    embed.add_field(name="Difficulty", value=f"{DIFF_ICONS.get(ch.difficulty, '')} {ch.difficulty}", inline=True)
    embed.add_field(name="Language", value=ch.language or "Any", inline=True)
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


def build_master_embed(settings: ChallengeSetting, counts: dict, bot):
    try:
        color = int((settings.embed_color or "#5865F2").lstrip("#"), 16)
    except ValueError:
        color = 0x5865F2
    embed = discord.Embed(
        title="⚡ Programming Challenges",
        description=(
            "Pick a **difficulty** below and you'll be given a **random challenge** to solve.\n\n"
            "Solve it to earn **XP** and **coins** and climb the leaderboard! 🏆"
        ),
        color=color,
    )
    if settings.thumbnail:
        embed.set_thumbnail(url=settings.thumbnail)
    for d in DIFFICULTIES:
        n = counts.get(d, 0)
        icon = DIFF_ICONS.get(d, "")
        embed.add_field(
            name=f"{icon} {d}",
            value=f"{n} challenge{'s' if n != 1 else ''}" if n else "None yet",
            inline=True,
        )
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


class GlobalLeaderboardButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="View Leaderboard", style=discord.ButtonStyle.secondary, emoji="🏆", custom_id="dt_chal_lb_global")

    async def callback(self, interaction: discord.Interaction):
        sess = get_session()
        try:
            rows = sess.query(UserXP).filter_by(guild_id=interaction.guild_id).order_by(UserXP.xp.desc()).limit(10).all()
            lines = []
            medals = ["🥇", "🥈", "🥉"]
            for i, row in enumerate(rows):
                member = interaction.guild.get_member(row.user_id) if interaction.guild else None
                name = member.display_name if member else f"`{row.user_id}`"
                medal = medals[i] if i < 3 else f"`#{i + 1}`"
                lines.append(f"{medal} **{name}** — **{row.xp} XP** • {row.challenges_solved} solved")
            embed = primary("🏆 Challenge Leaderboard", "\n".join(lines) if lines else "No solvers yet — be the first!", footer="D&T Programming Challenges")
            await interaction.response.send_message(embed=embed, ephemeral=True)
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


class ChallengeMasterView(discord.ui.View):
    """Persistent panel: pick a difficulty -> get a random challenge."""

    def __init__(self, difficulties: list, bot=None, show_leaderboard: bool = True):
        super().__init__(timeout=None)
        self.bot = bot
        for d in difficulties:
            self.add_item(DifficultyButton(d))
        if show_leaderboard:
            self.add_item(GlobalLeaderboardButton())

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
            embed = build_challenge_embed(ch, settings, self.bot or interaction.client)
            view = ChallengeSessionView(ch.id, languages, ch, interaction.user.id)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        finally:
            sess.close()


class ChallengeSessionView(discord.ui.View):
    def __init__(self, challenge_id: int, languages: list, challenge: Challenge, user_id: int):
        super().__init__(timeout=900)
        self.challenge_id = challenge_id
        self.challenge = challenge
        self.languages = languages
        self.user_id = user_id
        self.selected_language = languages[0] if languages else "Python"
        self.start_time = time.time()

        options = [discord.SelectOption(label=lang, value=lang) for lang in languages]
        select = discord.ui.Select(placeholder="Select language", options=options, custom_id=f"dt_chal_lang:{challenge_id}")
        select.callback = self._on_language
        self.add_item(select)

        button = discord.ui.Button(label="Submit Code", style=discord.ButtonStyle.success, emoji="📤", custom_id=f"dt_chal_submit:{challenge_id}")
        button.callback = self._on_submit
        self.add_item(button)

    async def _on_language(self, interaction: discord.Interaction):
        self.selected_language = interaction.data["values"][0]
        await interaction.response.defer(ephemeral=True)

    async def _on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This session belongs to someone else.", ephemeral=True)
            return
        starter = ""
        sess = get_session()
        try:
            row = sess.query(ChallengeStarterCodeModel).filter_by(challenge_id=self.challenge.id, language=self.selected_language).first()
            starter = row.code if row else ""
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
    bot.add_view(ChallengeMasterView(DIFFICULTIES, bot=bot, show_leaderboard=True))


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
            rows = sess.query(Challenge).filter_by(enabled=True).all()
        finally:
            sess.close()

        counts = {}
        for ch in rows:
            counts[ch.difficulty] = counts.get(ch.difficulty, 0) + 1
        difficulties = [d for d in DIFFICULTIES if counts.get(d)]
        if not difficulties:
            return {"error": "No enabled challenges found — create and enable at least one challenge first"}

        embed = build_master_embed(settings, counts, self.bot)
        view = ChallengeMasterView(difficulties, bot=self.bot, show_leaderboard=settings.leaderboard_enabled)
        await channel.send(embed=embed, view=view)
        return {"success": True, "sent": len(difficulties)}

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
