from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_from_directory, send_file
import os
from functools import wraps
from dotenv import load_dotenv
import requests

from config import GUILD_ID, ADMIN_IDS, DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET, DISCORD_REDIRECT_URI
from database import (
    get_session, get_settings, GuildSettings,
    AutoResponder, ActiveTicket, LogEntry,
)

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
    discord_auth_url = f"https://discord.com/api/oauth2/authorize?client_id={DISCORD_CLIENT_ID}&redirect_uri={DISCORD_REDIRECT_URI}&response_type=code&scope=identify"
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
    return render_template("index.html")


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
    guild = bot_state["bot"].guild if bot_state["bot"] else None
    if guild:
        bot_state["member_count"] = guild.member_count or 0
        bot_state["guild_name"] = guild.name
    s = _settings()
    return jsonify({
        "status": bot_state["status"],
        "member_count": bot_state["member_count"],
        "guild_name": bot_state["guild_name"],
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


# ---- Non-API settings routes (for toggles/simple updates) ----

@app.route("/api/uploads/<filename>")
@login_required
def api_uploads(filename):
    return send_from_directory(UPLOAD_DIR, filename)


@app.route("/update", methods=["POST"])
@login_required
def update():
    _update_settings(
        welcome_channel_id=int(request.form.get("welcome_channel")) if request.form.get("welcome_channel") else None,
        log_channel_id=int(request.form.get("log_channel")) if request.form.get("log_channel") else None,
        auto_role_id=int(request.form.get("auto_role")) if request.form.get("auto_role") else None,
    )
    return jsonify({"ok": True})


def run_dashboard(host="127.0.0.1", port=5000, debug=False):
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    run_dashboard(debug=True)
