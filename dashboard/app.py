from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_from_directory, send_file
import os
import json
import asyncio
import urllib.parse
from concurrent import futures as concurrent_futures
from functools import wraps
from dotenv import load_dotenv
import requests
import psutil

from config import GUILD_ID, ADMIN_IDS, DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET, DISCORD_REDIRECT_URI
from database import (
    get_session, get_settings, GuildSettings,
    AutoResponder, ActiveTicket, LogEntry,
    SecurityLimit, SecurityWhitelist,
    ChallengeSetting, Challenge, ChallengeExample,
    ChallengeStarterCode, ChallengeTestCase,
    UserChallengeProgress, UserXP, ChallengeAchievement,
)
from voice_bots import get_voice_bot_list, get_voice_bot_user_id, _save_setting, voice_bots
from challenges_bot import get_challenges_bot, get_challenges_bot_status

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("DASHBOARD_SECRET_KEY", "dev-secret-change-me")

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

bot_state = {"bot": None, "status": "Offline", "member_count": 0, "guild_name": "Unknown"}


def set_bot(bot_instance):
    bot_state["bot"] = bot_instance
    bot_state["status"] = "Online"
    guild = bot_instance.guild
    if guild:
        bot_state["member_count"] = guild.member_count or 0
        bot_state["guild_name"] = guild.name


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


@app.route("/login")
def login():
    if session.get("logged_in"):
        return redirect(url_for("index"))
    discord_auth_url = f"https://discord.com/api/oauth2/authorize?client_id={DISCORD_CLIENT_ID}&redirect_uri={urllib.parse.quote(DISCORD_REDIRECT_URI, safe='')}&response_type=code&scope=identify"
    return render_template("login.html", discord_auth_url=discord_auth_url)


@app.route("/callback")
def oauth2_callback():
    code = request.args.get("code")
    if not code:
        return redirect(url_for("login"))
    data = {
        "client_id": DISCORD_CLIENT_ID,
        "client_secret": DISCORD_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": DISCORD_REDIRECT_URI,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    r = requests.post("https://discord.com/api/oauth2/token", data=data, headers=headers)
    if not r.ok:
        return render_template("login.html", error="Failed to authenticate with Discord")
    token_data = r.json()
    access_token = token_data.get("access_token")
    if not access_token:
        return render_template("login.html", error="No access token received")
    user_r = requests.get("https://discord.com/api/users/@me", headers={"Authorization": f"Bearer {access_token}"})
    if not user_r.ok:
        return render_template("login.html", error="Failed to fetch user info")
    user_data = user_r.json()
    user_id = int(user_data["id"])
    if user_id not in ADMIN_IDS:
        return render_template("login.html", error="You are not authorized to access this dashboard")
    session["logged_in"] = True
    session["user_id"] = user_id
    session["username"] = user_data.get("username", "Unknown")
    return redirect(url_for("index"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    return render_template("overview.html", active_page="overview")


@app.route("/logs")
@login_required
def logs_page():
    return render_template("logs.html", active_page="logs")


@app.route("/welcomer")
@login_required
def welcomer_page():
    return render_template("welcomer.html", active_page="welcomer")


@app.route("/autoresponder")
@login_required
def autoresponder_page():
    return render_template("autoresponder.html", active_page="autoresponder")


@app.route("/roles")
@login_required
def roles_page():
    return render_template("roles.html", active_page="roles")


@app.route("/automod")
@login_required
def automod_page():
    return render_template("automod.html", active_page="automod")


@app.route("/moderation")
@login_required
def moderation_page():
    return render_template("moderation.html", active_page="moderation")


@app.route("/security")
@login_required
def security_page():
    return render_template("security.html", active_page="security")


@app.route("/sender")
@login_required
def sender_page():
    return render_template("sender.html", active_page="sender")


@app.route("/tickets")
@login_required
def tickets_page():
    return render_template("tickets.html", active_page="tickets")


@app.route("/challenges")
@login_required
def challenges_page():
    return render_template("challenges.html", active_page="challenges")


@app.route("/challenges/edit/<int:challenge_id>")
@login_required
def challenge_editor_page(challenge_id):
    return render_template(
        "challenge_editor.html",
        active_page="challenge-editor",
        challenge_id=challenge_id,
        preview=request.args.get("preview") == "1",
    )


@app.route("/challenges/new")
@login_required
def challenge_new_page():
    return render_template(
        "challenge_editor.html",
        active_page="challenge-editor",
        challenge_id=None,
        preview=False,
    )


@app.route("/voice-bots")
@login_required
def voice_bots_page():
    return render_template("voice_bots.html", active_page="voicebots")


# ---- Helpers ----

def _settings():
    return get_settings(GUILD_ID)


def _update_settings(**kwargs):
    sess = get_session()
    try:
        s = sess.get(GuildSettings, GUILD_ID)
        if not s:
            s = GuildSettings(guild_id=GUILD_ID)
            sess.add(s)
        for k, v in kwargs.items():
            setattr(s, k, v)
        sess.commit()
        return s
    finally:
        sess.close()


# ---- API: Guild Data (channels, roles, categories for dropdowns) ----

@app.route("/api/guild/channels")
@login_required
def api_guild_channels():
    bot = bot_state["bot"]
    if not bot:
        return jsonify({"error": "Bot not initialized", "bot_state": str(bot_state["status"])}), 200
    g = bot.guild
    if not g:
        return jsonify({"error": f"Guild not found for GUILD_ID. Bot is in {len(bot.guilds)} guilds"}), 200
    channels = []
    for ch in g.text_channels:
        channels.append({"id": str(ch.id), "name": ch.name})
    return jsonify(channels)


@app.route("/api/guild/roles")
@login_required
def api_guild_roles():
    bot = bot_state["bot"]
    if not bot:
        return jsonify([])
    g = bot.guild
    if not g:
        return jsonify([])
    roles = []
    for r in g.roles:
        if r.name != "@everyone":
            roles.append({"id": str(r.id), "name": r.name})
    return jsonify(roles)


@app.route("/api/guild/categories")
@login_required
def api_guild_categories():
    bot = bot_state["bot"]
    if not bot:
        return jsonify([])
    g = bot.guild
    if not g:
        return jsonify([])
    cats = []
    for c in g.categories:
        cats.append({"id": str(c.id), "name": c.name})
    return jsonify(cats)


@app.route("/api/guild/voice_channels")
@login_required
def api_guild_voice_channels():
    bot = bot_state["bot"]
    if not bot:
        return jsonify([])
    g = bot.guild
    if not g:
        return jsonify([])
    vcs = []
    for ch in g.voice_channels:
        vcs.append({"id": str(ch.id), "name": ch.name})
    return jsonify(vcs)


@app.route("/api/voicebots")
@login_required
def api_voicebots():
    return jsonify(get_voice_bot_list())


@app.route("/api/voicebots/update", methods=["POST"])
@login_required
def api_voicebots_update():
    bot_index = request.form.get("bot_index")
    if bot_index is None or not bot_index.isdigit():
        return jsonify({"error": "Invalid bot index"}), 400
    index = int(bot_index)
    channel_id = request.form.get("voice_channel_id", "").strip()
    enabled = request.form.get("enabled") == "on"
    label = request.form.get("label", f"Voice Bot {index + 1}").strip()
    _save_setting(index, label, channel_id if channel_id else None, enabled)

    errors = []
    vb = voice_bots.get(index)
    username_ok = False
    if vb and vb.is_ready():
        if label and (not vb.user or label != vb.user.name):
            try:
                future = asyncio.run_coroutine_threadsafe(vb.rename_bot(label), vb.loop)
                err = future.result(timeout=10)
                if err:
                    errors.append(err)
                else:
                    username_ok = True
            except Exception as e:
                errors.append(f"Rename failed: {e}")
    else:
        errors.append("Voice bot not ready")

    main_bot = bot_state.get("bot")
    vb_user_id = get_voice_bot_user_id(index)
    if not username_ok and main_bot and vb_user_id and label:
        try:
            future = main_bot.set_voice_bot_nickname(vb_user_id, label)
            err = future.result(timeout=10)
            if err:
                errors.append(err)
        except Exception as e:
            errors.append(f"Nickname failed: {e}")

    if vb:
        vb.trigger_sync()
    return jsonify({"success": True, "rename_error": " | ".join(errors)})


# ---- Programming Challenges ----

def _challenge_summary(ch):
    rate = round(ch.successful_attempts / ch.total_attempts * 100) if ch.total_attempts else 0
    return {
        "id": ch.id,
        "challenge_key": ch.challenge_key,
        "title": ch.title,
        "language": ch.language,
        "category": ch.category,
        "difficulty": ch.difficulty,
        "enabled": bool(ch.enabled),
        "xp_reward": ch.xp_reward,
        "total_attempts": ch.total_attempts,
        "successful_attempts": ch.successful_attempts,
        "success_rate": rate,
        "created_at": ch.created_at.isoformat() if ch.created_at else None,
    }


def _challenge_full(ch):
    sess = get_session()
    try:
        examples = sess.query(ChallengeExample).filter_by(challenge_id=ch.id).order_by(ChallengeExample.id.asc()).all()
        tests = sess.query(ChallengeTestCase).filter_by(challenge_id=ch.id).order_by(ChallengeTestCase.id.asc()).all()
        starter = sess.query(ChallengeStarterCode).filter_by(challenge_id=ch.id).all()
        rate = round(ch.successful_attempts / ch.total_attempts * 100) if ch.total_attempts else 0
        return {
            "id": ch.id,
            "challenge_key": ch.challenge_key,
            "title": ch.title,
            "description": ch.description,
            "language": ch.language,
            "category": ch.category,
            "difficulty": ch.difficulty,
            "enabled": bool(ch.enabled),
            "time_limit": ch.time_limit,
            "memory_limit": ch.memory_limit,
            "max_code_size": ch.max_code_size,
            "ignore_trailing_spaces": bool(ch.ignore_trailing_spaces),
            "ignore_empty_lines": bool(ch.ignore_empty_lines),
            "case_sensitive": ch.case_sensitive if ch.case_sensitive is not None else True,
            "xp_reward": ch.xp_reward,
            "coins_reward": ch.coins_reward,
            "unlock_achievement": ch.unlock_achievement,
            "unlock_next_challenge": bool(ch.unlock_next_challenge),
            "estimated_time": ch.estimated_time,
            "stats": {
                "total_attempts": ch.total_attempts,
                "successful_attempts": ch.successful_attempts,
                "success_rate": rate,
                "avg_solve_time": round(ch.avg_solve_time or 0, 1),
            },
            "starter_codes": {sc.language: sc.code for sc in starter},
            "examples": [
                {"id": e.id, "input": e.input, "output": e.output, "explanation": e.explanation}
                for e in examples
            ],
            "test_cases": [
                {"id": t.id, "input": t.input, "expected_output": t.expected_output, "hidden": bool(t.hidden)}
                for t in tests
            ],
        }
    finally:
        sess.close()


def _save_challenge_children(sess, challenge_id, data):
    starter = data.get("starter_codes")
    if isinstance(starter, dict):
        sess.query(ChallengeStarterCode).filter_by(challenge_id=challenge_id).delete()
        for lang, code in starter.items():
            if code is not None:
                sess.add(ChallengeStarterCode(challenge_id=challenge_id, language=lang, code=code))
    examples = data.get("examples")
    if isinstance(examples, list):
        sess.query(ChallengeExample).filter_by(challenge_id=challenge_id).delete()
        for e in examples:
            sess.add(ChallengeExample(
                challenge_id=challenge_id,
                input=e.get("input", ""),
                output=e.get("output", ""),
                explanation=e.get("explanation", ""),
            ))
    tests = data.get("test_cases")
    if isinstance(tests, list):
        sess.query(ChallengeTestCase).filter_by(challenge_id=challenge_id).delete()
        for t in tests:
            sess.add(ChallengeTestCase(
                challenge_id=challenge_id,
                input=t.get("input", ""),
                expected_output=t.get("expected_output", ""),
                hidden=bool(t.get("hidden", True)),
            ))


@app.route("/api/challenges/settings", methods=["GET", "POST"])
@login_required
def api_challenge_settings():
    sess = get_session()
    try:
        s = sess.get(ChallengeSetting, GUILD_ID)
        if not s:
            s = ChallengeSetting(guild_id=GUILD_ID)
            sess.add(s)
            sess.commit()
        if request.method == "POST":
            s.enabled = request.form.get("enabled") == "on"
            ch = request.form.get("channel_id", "").strip()
            s.channel_id = int(ch) if ch else None
            s.embed_color = request.form.get("embed_color") or "#5865F2"
            s.thumbnail = request.form.get("thumbnail") or None
            s.footer = request.form.get("footer") or "D&T Programming Challenges"
            s.leaderboard_enabled = request.form.get("leaderboard_enabled") == "on"
            s.xp_enabled = request.form.get("xp_enabled") == "on"
            lb_ch = request.form.get("leaderboard_channel_id", "").strip()
            new_lb = int(lb_ch) if lb_ch else None
            if new_lb != s.leaderboard_channel_id:
                s.leaderboard_channel_id = new_lb
                s.leaderboard_message_id = None
            sess.commit()
            return jsonify({"ok": True})
        return jsonify({
            "enabled": bool(s.enabled),
            "channel_id": str(s.channel_id) if s.channel_id else None,
            "embed_color": s.embed_color or "#5865F2",
            "thumbnail": s.thumbnail,
            "footer": s.footer,
            "leaderboard_enabled": bool(s.leaderboard_enabled),
            "xp_enabled": bool(s.xp_enabled),
            "leaderboard_channel_id": str(s.leaderboard_channel_id) if s.leaderboard_channel_id else None,
        })
    finally:
        sess.close()


@app.route("/api/challenges/bot-status")
@login_required
def api_challenge_bot_status():
    return jsonify(get_challenges_bot_status())


@app.route("/api/challenges/send-panel", methods=["POST"])
@login_required
def api_challenge_send_panel():
    bot = get_challenges_bot() or bot_state.get("bot")
    if not bot:
        return jsonify({"error": "Bot is offline — start it with `python main.py`"}), 503
    if not getattr(bot, "loop", None):
        return jsonify({"error": "Bot is still connecting — try again in a moment"}), 503
    sess = get_session()
    try:
        s = sess.get(ChallengeSetting, GUILD_ID)
        if request.form.get("channel_id"):
            channel_id = int(request.form["channel_id"])
        elif s and s.channel_id:
            channel_id = s.channel_id
        else:
            return jsonify({"error": "No channel selected"}), 400
    finally:
        sess.close()

    target = bot
    if not target.get_cog("Challenges"):
        other = bot_state.get("bot")
        if other and other is not target and other.get_cog("Challenges"):
            target = other
    if not target.get_cog("Challenges"):
        return jsonify({"error": "Challenges cog not loaded"}), 500
    if not getattr(target, "loop", None):
        return jsonify({"error": "Bot is still connecting — try again in a moment"}), 503

    async def _do():
        return await target.get_cog("Challenges").send_panels(channel_id)

    try:
        future = asyncio.run_coroutine_threadsafe(_do(), target.loop)
        result = future.result(timeout=60)
    except concurrent_futures.TimeoutError:
        return jsonify({"error": "Timed out sending the panel — try again"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    if result.get("error"):
        return jsonify({"error": result["error"]}), 400
    return jsonify({"success": True, "sent": result.get("sent", 0)})


@app.route("/api/challenges")
@login_required
def api_challenges_list():
    q = request.args.get("search", "").strip().lower()
    language = request.args.get("language", "").strip()
    difficulty = request.args.get("difficulty", "").strip()
    status = request.args.get("status", "").strip()
    sort = request.args.get("sort", "").strip()
    try:
        page = max(1, int(request.args.get("page", 1) or 1))
    except ValueError:
        page = 1
    try:
        per_page = max(5, min(50, int(request.args.get("per_page", 10) or 10)))
    except ValueError:
        per_page = 10

    sess = get_session()
    try:
        query = sess.query(Challenge)
        if q:
            query = query.filter(
                Challenge.title.ilike(f"%{q}%") | Challenge.challenge_key.ilike(f"%{q}%")
            )
        if language:
            query = query.filter(Challenge.language == language)
        if difficulty:
            query = query.filter(Challenge.difficulty == difficulty)
        if status == "enabled":
            query = query.filter(Challenge.enabled.is_(True))
        elif status == "disabled":
            query = query.filter(Challenge.enabled.is_(False))

        from sqlalchemy import case
        diff_order = case(
            (Challenge.difficulty == "Easy", 0),
            (Challenge.difficulty == "Medium", 1),
            (Challenge.difficulty == "Hard", 2),
            (Challenge.difficulty == "Expert", 3),
            else_=4,
        )
        if sort == "difficulty":
            query = query.order_by(diff_order.asc(), Challenge.id.asc())
        elif sort == "difficulty_desc":
            query = query.order_by(diff_order.desc(), Challenge.id.asc())
        elif sort == "language":
            query = query.order_by(Challenge.language.asc(), Challenge.id.asc())
        elif sort == "newest":
            query = query.order_by(Challenge.id.desc())
        else:
            query = query.order_by(Challenge.id.asc())

        total = query.count()
        rows = query.offset((page - 1) * per_page).limit(per_page).all()
        return jsonify({
            "items": [_challenge_summary(c) for c in rows],
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": max(1, (total + per_page - 1) // per_page),
        })
    finally:
        sess.close()


@app.route("/api/challenges/leaderboard")
@login_required
def api_challenge_leaderboard():
    sess = get_session()
    try:
        rows = sess.query(UserXP).filter_by(guild_id=GUILD_ID).order_by(UserXP.xp.desc()).limit(10).all()
        guild = bot_state["bot"].guild if bot_state.get("bot") else None
        out = []
        for i, r in enumerate(rows):
            member = guild.get_member(r.user_id) if guild else None
            out.append({
                "rank": i + 1,
                "user_id": str(r.user_id),
                "username": member.display_name if member else f"User {r.user_id}",
                "xp": r.xp,
                "coins": r.coins,
                "solved": r.challenges_solved,
            })
        return jsonify(out)
    finally:
        sess.close()


@app.route("/api/challenges/<int:challenge_id>")
@login_required
def api_challenge_get(challenge_id):
    sess = get_session()
    try:
        ch = sess.get(Challenge, challenge_id)
        if not ch:
            return jsonify({"error": "Challenge not found"}), 404
        return jsonify(_challenge_full(ch))
    finally:
        sess.close()


@app.route("/api/challenges", methods=["POST"])
@login_required
def api_challenge_create():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "Title is required"}), 400
    sess = get_session()
    try:
        ch = Challenge(
            challenge_key="CH-000",
            title=title,
            description=data.get("description", "") or "",
            language=data.get("language") or "Python",
            category=data.get("category") or "Algorithms",
            difficulty=data.get("difficulty") or "Easy",
            time_limit=int(data.get("time_limit") or 2),
            memory_limit=int(data.get("memory_limit") or 256),
            max_code_size=int(data.get("max_code_size") or 100000),
            ignore_trailing_spaces=bool(data.get("ignore_trailing_spaces")),
            ignore_empty_lines=bool(data.get("ignore_empty_lines")),
            case_sensitive=data.get("case_sensitive", True) if data.get("case_sensitive") is not None else True,
            xp_reward=int(data.get("xp_reward") or 0),
            coins_reward=int(data.get("coins_reward") or 0),
            unlock_achievement=(data.get("unlock_achievement") or "").strip() or None,
            unlock_next_challenge=bool(data.get("unlock_next_challenge")),
            estimated_time=data.get("estimated_time") or "~30 min",
        )
        sess.add(ch)
        sess.flush()
        ch.challenge_key = f"CH-{ch.id:03d}"
        _save_challenge_children(sess, ch.id, data)
        sess.commit()
        return jsonify({"id": ch.id, "challenge_key": ch.challenge_key})
    finally:
        sess.close()


@app.route("/api/challenges/<int:challenge_id>", methods=["POST"])
@login_required
def api_challenge_update(challenge_id):
    data = request.get_json(silent=True) or {}
    sess = get_session()
    try:
        ch = sess.get(Challenge, challenge_id)
        if not ch:
            return jsonify({"error": "Challenge not found"}), 404
        if "title" in data:
            ch.title = (data.get("title") or "").strip() or ch.title
        if "description" in data:
            ch.description = data.get("description") or ""
        if "language" in data:
            ch.language = data.get("language") or "Python"
        if "category" in data:
            ch.category = data.get("category") or "Algorithms"
        if "difficulty" in data:
            ch.difficulty = data.get("difficulty") or "Easy"
        if "enabled" in data:
            ch.enabled = bool(data.get("enabled"))
        if "time_limit" in data:
            ch.time_limit = int(data.get("time_limit") or 2)
        if "memory_limit" in data:
            ch.memory_limit = int(data.get("memory_limit") or 256)
        if "max_code_size" in data:
            ch.max_code_size = int(data.get("max_code_size") or 100000)
        if "ignore_trailing_spaces" in data:
            ch.ignore_trailing_spaces = bool(data.get("ignore_trailing_spaces"))
        if "ignore_empty_lines" in data:
            ch.ignore_empty_lines = bool(data.get("ignore_empty_lines"))
        if "case_sensitive" in data:
            ch.case_sensitive = bool(data.get("case_sensitive"))
        if "xp_reward" in data:
            ch.xp_reward = int(data.get("xp_reward") or 0)
        if "coins_reward" in data:
            ch.coins_reward = int(data.get("coins_reward") or 0)
        if "unlock_achievement" in data:
            ch.unlock_achievement = (data.get("unlock_achievement") or "").strip() or None
        if "unlock_next_challenge" in data:
            ch.unlock_next_challenge = bool(data.get("unlock_next_challenge"))
        if "estimated_time" in data:
            ch.estimated_time = data.get("estimated_time") or "~30 min"
        _save_challenge_children(sess, ch.id, data)
        sess.commit()
        return jsonify({"id": ch.id, "challenge_key": ch.challenge_key})
    finally:
        sess.close()


@app.route("/api/challenges/<int:challenge_id>/duplicate", methods=["POST"])
@login_required
def api_challenge_duplicate(challenge_id):
    sess = get_session()
    try:
        ch = sess.get(Challenge, challenge_id)
        if not ch:
            return jsonify({"error": "Challenge not found"}), 404
        new = Challenge(
            challenge_key="CH-000",
            title=f"{ch.title} (Copy)",
            description=ch.description,
            language=ch.language,
            category=ch.category,
            difficulty=ch.difficulty,
            enabled=False,
            time_limit=ch.time_limit,
            memory_limit=ch.memory_limit,
            max_code_size=ch.max_code_size,
            ignore_trailing_spaces=ch.ignore_trailing_spaces,
            ignore_empty_lines=ch.ignore_empty_lines,
            case_sensitive=ch.case_sensitive,
            xp_reward=ch.xp_reward,
            coins_reward=ch.coins_reward,
            unlock_achievement=ch.unlock_achievement,
            unlock_next_challenge=ch.unlock_next_challenge,
            estimated_time=ch.estimated_time,
        )
        sess.add(new)
        sess.flush()
        new.challenge_key = f"CH-{new.id:03d}"
        for sc in sess.query(ChallengeStarterCode).filter_by(challenge_id=ch.id).all():
            sess.add(ChallengeStarterCode(challenge_id=new.id, language=sc.language, code=sc.code))
        for e in sess.query(ChallengeExample).filter_by(challenge_id=ch.id).all():
            sess.add(ChallengeExample(challenge_id=new.id, input=e.input, output=e.output, explanation=e.explanation))
        for t in sess.query(ChallengeTestCase).filter_by(challenge_id=ch.id).all():
            sess.add(ChallengeTestCase(challenge_id=new.id, input=t.input, expected_output=t.expected_output, hidden=t.hidden))
        sess.commit()
        return jsonify({"id": new.id, "challenge_key": new.challenge_key})
    finally:
        sess.close()


@app.route("/api/challenges/<int:challenge_id>/toggle", methods=["POST"])
@login_required
def api_challenge_toggle(challenge_id):
    sess = get_session()
    try:
        ch = sess.get(Challenge, challenge_id)
        if not ch:
            return jsonify({"error": "Challenge not found"}), 404
        ch.enabled = not ch.enabled
        sess.commit()
        return jsonify({"enabled": bool(ch.enabled)})
    finally:
        sess.close()


@app.route("/api/challenges/<int:challenge_id>", methods=["DELETE"])
@login_required
def api_challenge_delete(challenge_id):
    sess = get_session()
    try:
        ch = sess.get(Challenge, challenge_id)
        if not ch:
            return jsonify({"error": "Challenge not found"}), 404
        for model in (ChallengeStarterCode, ChallengeExample, ChallengeTestCase, UserChallengeProgress):
            sess.query(model).filter_by(challenge_id=challenge_id).delete()
        sess.delete(ch)
        sess.commit()
        return jsonify({"ok": True})
    finally:
        sess.close()


# ---- Debug ----

@app.route("/api/debug")
@login_required
def api_debug():
    bot = bot_state["bot"]
    info = {
        "bot_status": bot_state["status"],
        "guild_name": bot_state["guild_name"],
        "member_count": bot_state["member_count"],
        "bot_instance": bot is not None,
        "guilds_count": len(bot.guilds) if bot else 0,
        "guild_ids": [g.id for g in bot.guilds] if bot else [],
        "config_guild_id": int(os.getenv("GUILD_ID", 0)),
    }
    if bot and bot.guild:
        info["found_guild"] = True
        info["text_channels"] = [{"id": str(ch.id), "name": ch.name} for ch in bot.guild.text_channels]
        info["roles"] = [{"id": str(r.id), "name": r.name} for r in bot.guild.roles if r.name != "@everyone"]
        info["categories"] = [{"id": str(c.id), "name": c.name} for c in bot.guild.categories]
    else:
        info["found_guild"] = False
    return jsonify(info)


@app.route("/api/debug/db")
@login_required
def api_debug_db():
    try:
        from database import get_session, GuildSettings, DB_PATH, DATABASE_URL
        info = {"db_path": DB_PATH, "db_exists": os.path.exists(DB_PATH), "DATABASE_URL": DATABASE_URL}
        sess = get_session()
        try:
            s = sess.get(GuildSettings, GUILD_ID)
            if s:
                info["settings_found"] = True
                info["settings"] = {c.name: getattr(s, c.name) for c in GuildSettings.__table__.columns}
            else:
                info["settings_found"] = False
        finally:
            sess.close()
        return jsonify(info)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---- API: Stats ----

@app.route("/api/stats")
@login_required
def api_stats():
    bot = bot_state["bot"]
    guild = bot.guild if bot else None
    if guild:
        bot_state["member_count"] = guild.member_count or 0
        bot_state["guild_name"] = guild.name
    s = _settings()

    ping_ms = round(bot.latency * 1000) if bot else 0
    new_members = 0
    if guild:
        from datetime import datetime, timedelta
        cutoff = datetime.utcnow() - timedelta(hours=24)
        new_members = sum(1 for m in guild.members if m.joined_at and m.joined_at.replace(tzinfo=None) > cutoff)

    return jsonify({
        "status": bot_state["status"],
        "member_count": bot_state["member_count"],
        "guild_name": bot_state["guild_name"],
        "ping_ms": ping_ms,
        "new_members_24h": new_members,
        "messages_24h": bot.message_count_24h if bot else 0,
        "ram_pct": round(psutil.virtual_memory().percent),
        "cpu_pct": round(psutil.cpu_percent(interval=0)),
        "welcome_enabled": s.welcome_enabled,
        "welcome_channel_id": str(s.welcome_channel_id) if s.welcome_channel_id else None,
        "leave_enabled": s.leave_enabled,
        "leave_channel_id": str(s.leave_channel_id) if s.leave_channel_id else None,
        "anti_bad_words": s.anti_bad_words,
        "anti_links": s.anti_links,
        "anti_spam": s.anti_spam,
        "automod_penalty": s.automod_penalty,
        "automod_bypass_roles": s.automod_bypass_roles,
        "ticket_enabled": s.ticket_enabled,
        "ticket_panel_channel_id": str(s.ticket_panel_channel_id) if s.ticket_panel_channel_id else None,
        "ticket_panel_message_id": str(s.ticket_panel_message_id) if s.ticket_panel_message_id else None,
        "log_channel_id": str(s.log_channel_id) if s.log_channel_id else None,
        "auto_role_id": str(s.auto_role_id) if s.auto_role_id else None,
    })


# ---- Module 1: Welcomer ----

@app.route("/api/welcomer", methods=["GET", "POST"])
@login_required
def api_welcomer():
    if request.method == "POST":
        _update_settings(
            welcome_enabled=request.form.get("welcome_enabled") == "on",
            welcome_channel_id=int(request.form["welcome_channel_id"]) if request.form.get("welcome_channel_id") else None,
            welcome_message=request.form.get("welcome_message", ""),
            leave_enabled=request.form.get("leave_enabled") == "on",
            leave_channel_id=int(request.form["leave_channel_id"]) if request.form.get("leave_channel_id") else None,
            leave_message=request.form.get("leave_message", ""),
            avatar_x=int(request.form["avatar_x"]) if request.form.get("avatar_x") else None,
            avatar_y=int(request.form["avatar_y"]) if request.form.get("avatar_y") else None,
            avatar_size=int(request.form["avatar_size"]) if request.form.get("avatar_size") else None,
        )
        return jsonify({"ok": True})
    s = _settings()
    return jsonify({
        "welcome_enabled": s.welcome_enabled,
        "welcome_channel_id": str(s.welcome_channel_id) if s.welcome_channel_id else None,
        "welcome_message": s.welcome_message,
        "leave_enabled": s.leave_enabled,
        "leave_channel_id": str(s.leave_channel_id) if s.leave_channel_id else None,
        "leave_message": s.leave_message,
        "avatar_x": s.avatar_x or 80,
        "avatar_y": s.avatar_y or 86,
        "avatar_size": s.avatar_size or 128,
    })



@app.route("/api/welcomer/preview")
@login_required
def api_welcomer_preview():
    bot = bot_state["bot"]
    if not bot:
        return jsonify({"error": "Bot offline"}), 503
    guild = bot.guild
    if not guild:
        return jsonify({"error": "No guild"}), 503

    import asyncio

    async def _build():
        member = guild.me
        data = await member.display_avatar.replace(size=256, format="png").read()
        s = _settings()
        from utils.card_renderer import generate_card
        return await generate_card(
            data,
            avatar_x=s.avatar_x or 80, avatar_y=s.avatar_y or 86,
            avatar_size=s.avatar_size or 128,
        )

    future = asyncio.run_coroutine_threadsafe(_build(), bot.loop)
    try:
        buf = future.result(timeout=15)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return send_file(buf, mimetype="image/png")


@app.route("/api/bg")
def api_bg():
    bg_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "pics", "welcome.png")
    if os.path.exists(bg_path):
        return send_file(bg_path, mimetype="image/jpeg")
    return jsonify({"error": "Not found"}), 404


PICS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "pics")

@app.route("/pics/<path:filename>")
def api_pics(filename):
    return send_from_directory(PICS_DIR, filename)


# ---- Module 2: Auto-Responder ----

@app.route("/api/autoresponder", methods=["GET"])
@login_required
def api_autoresponder_list():
    sess = get_session()
    try:
        items = sess.query(AutoResponder).filter_by(guild_id=GUILD_ID).all()
        return jsonify([{"id": r.id, "trigger": r.trigger, "response": r.response} for r in items])
    finally:
        sess.close()


@app.route("/api/autoresponder/add", methods=["POST"])
@login_required
def api_autoresponder_add():
    trigger = request.form.get("trigger", "").strip()
    response = request.form.get("response", "").strip()
    if trigger and response:
        sess = get_session()
        try:
            ar = AutoResponder(guild_id=GUILD_ID, trigger=trigger, response=response)
            sess.add(ar)
            sess.commit()
        finally:
            sess.close()
    return jsonify({"ok": True})


@app.route("/api/autoresponder/delete/<int:rid>", methods=["POST"])
@login_required
def api_autoresponder_delete(rid):
    sess = get_session()
    try:
        sess.query(AutoResponder).filter_by(id=rid, guild_id=GUILD_ID).delete()
        sess.commit()
    finally:
        sess.close()
    return jsonify({"ok": True})


# ---- Module 3: AutoMod ----

@app.route("/api/automod", methods=["POST"])
@login_required
def api_automod():
    bypass_raw = request.form.get("automod_bypass_roles", "")
    bypass_ids = ",".join(r.strip() for r in bypass_raw.split(",") if r.strip().isdigit())
    _update_settings(
        anti_bad_words=request.form.get("anti_bad_words") == "on",
        anti_links=request.form.get("anti_links") == "on",
        anti_spam=request.form.get("anti_spam") == "on",
        automod_penalty=request.form.get("automod_penalty", "mute"),
        automod_bypass_roles=bypass_ids,
    )
    return jsonify({"ok": True})


# ---- Module 4: Embed Sender ----

@app.route("/api/embed/send", methods=["POST"])
@login_required
def api_embed_send():
    bot = bot_state["bot"]
    if not bot:
        return jsonify({"error": "Bot offline"}), 503
    channel_id = request.form.get("channel_id", "").strip()
    title = request.form.get("title", "")
    description = request.form.get("description", "")
    color = request.form.get("color", "#5865F2")
    thumbnail = request.form.get("thumbnail", "")
    footer = request.form.get("footer", "")
    if not channel_id or not channel_id.isdigit():
        return jsonify({"error": "Invalid channel ID"}), 400
    file_path = ""
    if "file" in request.files:
        f = request.files["file"]
        if f and f.filename:
            import time, re
            name = re.sub(r'[^\w\.\-]', '_', f.filename)
            name = f"{int(time.time())}_{name}"
            file_path = os.path.join(UPLOAD_DIR, name)
            f.save(file_path)
    bot.send_embed_to_channel(
        int(channel_id), title, description, color, thumbnail, footer, file_path
    )
    return jsonify({"success": True})


@app.route("/api/message/send", methods=["POST"])
@login_required
def api_message_send():
    bot = bot_state["bot"]
    if not bot:
        return jsonify({"error": "Bot offline"}), 503
    channel_id = request.form.get("channel_id", "").strip()
    content = request.form.get("content", "").strip()
    if not channel_id or not channel_id.isdigit():
        return jsonify({"error": "Invalid channel ID"}), 400
    has_file = "file" in request.files and request.files["file"] and request.files["file"].filename
    if not content and not has_file:
        return jsonify({"error": "Message content is empty"}), 400
    file_path = ""
    if "file" in request.files:
        f = request.files["file"]
        if f and f.filename:
            import time, re
            name = re.sub(r'[^\w\.\-]', '_', f.filename)
            name = f"{int(time.time())}_{name}"
            file_path = os.path.join(UPLOAD_DIR, name)
            f.save(file_path)
    bot.send_message_to_channel(int(channel_id), content, file_path)
    return jsonify({"success": True})


@app.route("/api/poll/send", methods=["POST"])
@login_required
def api_poll_send():
    bot = bot_state["bot"]
    if not bot:
        return jsonify({"error": "Bot offline"}), 503
    channel_id = request.form.get("channel_id", "").strip()
    question = request.form.get("question", "").strip()
    options_raw = request.form.get("options", "[]")
    duration = request.form.get("duration", "24")
    allow_multiple = request.form.get("allow_multiple") == "on"

    if not channel_id or not channel_id.isdigit():
        return jsonify({"error": "Invalid channel ID"}), 400
    if not question:
        return jsonify({"error": "Question is required"}), 400
    try:
        options = [o.strip() for o in json.loads(options_raw) if o.strip()]
    except Exception:
        options = []
    # remove duplicates, truncate to Discord limits (55 chars per answer, 300 for question)
    options = list(dict.fromkeys(o[:55] for o in options))
    question = question[:300]
    if len(options) < 2 or len(options) > 9:
        return jsonify({"error": "Poll needs 2-9 unique options"}), 400

    try:
        dur = max(1, min(168, int(duration)))
    except ValueError:
        dur = 24

    bot.send_poll_to_channel(int(channel_id), question, options, dur, allow_multiple)
    return jsonify({"success": True})


# ---- Module 5: Tickets ----

@app.route("/api/tickets/settings", methods=["GET", "POST"])
@login_required
def api_tickets_settings():
    if request.method == "POST":
        _update_settings(
            ticket_enabled=request.form.get("ticket_enabled") == "on",
            ticket_panel_title=request.form.get("ticket_panel_title", "🎫 Support Tickets"),
            ticket_panel_desc=request.form.get("ticket_panel_desc", ""),
            ticket_button_text=request.form.get("ticket_button_text", "Open Ticket"),
            ticket_embed_color=request.form.get("ticket_embed_color", "#5865F2"),
            ticket_category_id=int(request.form["ticket_category_id"]) if request.form.get("ticket_category_id") else None,
            ticket_support_role_id=int(request.form["ticket_support_role_id"]) if request.form.get("ticket_support_role_id") else None,
        )
        return jsonify({"ok": True})
    s = _settings()
    return jsonify({
        "ticket_enabled": s.ticket_enabled,
        "ticket_panel_title": s.ticket_panel_title,
        "ticket_panel_desc": s.ticket_panel_desc,
        "ticket_button_text": s.ticket_button_text,
        "ticket_embed_color": s.ticket_embed_color,
        "ticket_category_id": str(s.ticket_category_id) if s.ticket_category_id else None,
        "ticket_support_role_id": str(s.ticket_support_role_id) if s.ticket_support_role_id else None,
        "ticket_panel_channel_id": str(s.ticket_panel_channel_id) if s.ticket_panel_channel_id else None,
        "ticket_panel_message_id": str(s.ticket_panel_message_id) if s.ticket_panel_message_id else None,
    })


@app.route("/api/tickets/send-panel", methods=["POST"])
@login_required
def api_tickets_send_panel():
    bot = bot_state["bot"]
    if not bot:
        return jsonify({"error": "Bot offline"}), 503
    channel_id = request.form.get("channel_id", "").strip()
    if not channel_id or not channel_id.isdigit():
        return jsonify({"error": "Invalid channel ID"}), 400
    bot.send_ticket_panel(int(channel_id))
    return jsonify({"success": True})


@app.route("/api/tickets/active")
@login_required
def api_tickets_active():
    bot = bot_state["bot"]
    if not bot:
        return jsonify([])
    tickets = bot.get_active_tickets()
    for t in tickets:
        t["channel_name"] = f"ticket-{t['user_id']}"
        ch = bot.get_channel(t["channel_id"])
        if ch:
            t["channel_name"] = ch.name
        user = bot.get_user(t["user_id"])
        t["user_name"] = user.name if user else f"Unknown ({t['user_id']})"
    return jsonify(tickets)


@app.route("/api/tickets/close/<int:channel_id>", methods=["POST"])
@login_required
def api_tickets_close(channel_id):
    bot = bot_state["bot"]
    if not bot:
        return jsonify({"error": "Bot offline"}), 503
    bot.close_ticket_channel(channel_id)
    return jsonify({"success": True})


# ---- Module 6: Roles ----

@app.route("/api/roles/send-panel", methods=["POST"])
@login_required
def api_roles_send_panel():
    bot = bot_state["bot"]
    if not bot:
        return jsonify({"error": "Bot offline"}), 503
    channel_id = request.form.get("channel_id", "").strip()
    role_ids = request.form.getlist("role_ids")
    if not channel_id or not channel_id.isdigit():
        return jsonify({"error": "Invalid channel ID"}), 400
    valid_ids = [r for r in role_ids if r.isdigit()]
    if not valid_ids:
        return jsonify({"error": "No valid roles selected"}), 400
    bot.send_role_panel(int(channel_id), valid_ids)
    return jsonify({"success": True})


# ---- Logs ----

@app.route("/api/logs/recent")
@login_required
def api_logs_recent():
    sess = get_session()
    try:
        entries = sess.query(LogEntry).filter_by(guild_id=GUILD_ID).order_by(LogEntry.timestamp.desc()).limit(50).all()
        return jsonify([
            {
                "id": e.id,
                "event_type": e.event_type,
                "description": e.description,
                "user_id": e.user_id,
                "timestamp": e.timestamp.isoformat() if e.timestamp else "",
            }
            for e in entries
        ])
    finally:
        sess.close()


@app.route("/api/logging/settings", methods=["GET"])
@login_required
def api_logging_settings():
    import json as _json
    s = _settings()
    try:
        ls = _json.loads(s.log_settings) if s.log_settings else {}
    except Exception:
        ls = {}
    return jsonify({"log_settings": ls})


@app.route("/api/logging/settings", methods=["POST"])
@login_required
def api_logging_settings_save():
    import json as _json
    data = request.get_json(silent=True) or {}
    settings_dict = data.get("log_settings", {})
    _update_settings(log_settings=_json.dumps(settings_dict))
    return jsonify({"ok": True})


@app.route("/api/logging/channel", methods=["POST"])
@login_required
def api_logging_channel():
    val = request.form.get("log_channel", "").strip()
    _update_settings(log_channel_id=int(val) if val else None)
    return jsonify({"ok": True})


# ---- Non-API settings routes (for toggles/simple updates) ----

@app.route("/api/uploads/<filename>")
@login_required
def api_uploads(filename):
    return send_from_directory(UPLOAD_DIR, filename)


@app.route("/update", methods=["POST"])
@login_required
def update():
    updates = {}
    if "auto_role" in request.form:
        val = request.form.get("auto_role")
        updates["auto_role_id"] = int(val) if val else None
    if "welcome_channel" in request.form:
        val = request.form.get("welcome_channel")
        updates["welcome_channel_id"] = int(val) if val else None
    if "log_channel" in request.form:
        val = request.form.get("log_channel")
        updates["log_channel_id"] = int(val) if val else None
    if updates:
        _update_settings(**updates)
    return jsonify({"ok": True})


# ---- Security ----

@app.route("/api/security/limits", methods=["GET"])
@login_required
def api_security_limits():
    sess = get_session()
    try:
        limits = sess.query(SecurityLimit).filter_by(guild_id=GUILD_ID).all()
        return jsonify([
            {
                "id": l.id,
                "action_type": l.action_type,
                "max_count": l.max_count,
                "time_window": l.time_window,
                "punishment": l.punishment,
                "enabled": l.enabled,
            }
            for l in limits
        ])
    finally:
        sess.close()


@app.route("/api/security/limits", methods=["POST"])
@login_required
def api_security_limits_add():
    sess = get_session()
    try:
        l = SecurityLimit(
            guild_id=GUILD_ID,
            action_type=request.form.get("action_type", "ban"),
            max_count=int(request.form.get("max_count", 5)),
            time_window=int(request.form.get("time_window", 60)),
            punishment=request.form.get("punishment", "ban"),
            enabled=request.form.get("enabled") == "on",
        )
        sess.add(l)
        sess.commit()
        return jsonify({"ok": True, "id": l.id})
    finally:
        sess.close()


@app.route("/api/security/limits/<int:limit_id>", methods=["POST"])
@login_required
def api_security_limit_update(limit_id):
    sess = get_session()
    try:
        l = sess.get(SecurityLimit, limit_id)
        if not l or l.guild_id != GUILD_ID:
            return jsonify({"error": "Not found"}), 404
        if "action_type" in request.form:
            l.action_type = request.form["action_type"]
        if "max_count" in request.form:
            l.max_count = int(request.form["max_count"])
        if "time_window" in request.form:
            l.time_window = int(request.form["time_window"])
        if "punishment" in request.form:
            l.punishment = request.form["punishment"]
        if "enabled" in request.form:
            l.enabled = request.form["enabled"] == "on"
        sess.commit()
        return jsonify({"ok": True})
    finally:
        sess.close()


@app.route("/api/security/limits/<int:limit_id>", methods=["DELETE"])
@login_required
def api_security_limit_delete(limit_id):
    sess = get_session()
    try:
        l = sess.get(SecurityLimit, limit_id)
        if l and l.guild_id == GUILD_ID:
            sess.delete(l)
            sess.commit()
        return jsonify({"ok": True})
    finally:
        sess.close()


@app.route("/api/security/whitelist", methods=["GET"])
@login_required
def api_security_whitelist():
    sess = get_session()
    try:
        entries = sess.query(SecurityWhitelist).filter_by(guild_id=GUILD_ID).all()
        return jsonify([
            {"id": e.id, "entity_type": e.entity_type, "entity_id": str(e.entity_id)}
            for e in entries
        ])
    finally:
        sess.close()


@app.route("/api/security/whitelist", methods=["POST"])
@login_required
def api_security_whitelist_add():
    sess = get_session()
    try:
        entity_type = request.form.get("entity_type", "user")
        entity_id = request.form.get("entity_id", "").strip()
        if not entity_id or not entity_id.isdigit():
            return jsonify({"error": "Invalid ID"}), 400
        existing = sess.query(SecurityWhitelist).filter_by(
            guild_id=GUILD_ID, entity_type=entity_type, entity_id=int(entity_id)
        ).first()
        if existing:
            return jsonify({"error": "Already whitelisted"}), 400
        e = SecurityWhitelist(guild_id=GUILD_ID, entity_type=entity_type, entity_id=int(entity_id))
        sess.add(e)
        sess.commit()
        return jsonify({"ok": True, "id": e.id})
    finally:
        sess.close()


@app.route("/api/security/whitelist/<int:entry_id>", methods=["DELETE"])
@login_required
def api_security_whitelist_delete(entry_id):
    sess = get_session()
    try:
        e = sess.get(SecurityWhitelist, entry_id)
        if e and e.guild_id == GUILD_ID:
            sess.delete(e)
            sess.commit()
        return jsonify({"ok": True})
    finally:
        sess.close()


def run_dashboard(host="0.0.0.0", port=None, debug=False):
    if port is None:
        port = int(os.getenv("PORT", 5000))
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    run_dashboard(debug=True)
