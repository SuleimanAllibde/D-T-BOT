import os
from datetime import datetime

from sqlalchemy import create_engine, Column, Integer, BigInteger, String, Text, Boolean, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL")
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "dt_bot.db")
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "data", "uploads")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

if DATABASE_URL:
    engine = create_engine(DATABASE_URL, echo=False)
else:
    engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
Base = declarative_base()


class GuildSettings(Base):
    __tablename__ = "guild_settings"

    guild_id = Column(BigInteger, primary_key=True)

    # Welcomer
    welcome_enabled = Column(Boolean, default=True)
    welcome_channel_id = Column(BigInteger, nullable=True)
    welcome_message = Column(Text, default="Welcome {user} to **{server}**!")
    leave_enabled = Column(Boolean, default=False)
    leave_channel_id = Column(BigInteger, nullable=True)
    leave_message = Column(Text, default="{user} has left {server}. We'll miss you!")
    welcome_card_bg = Column(Text, nullable=True)

    # Card layout coordinates
    avatar_x = Column(Integer, default=80)
    avatar_y = Column(Integer, default=86)
    avatar_size = Column(Integer, default=128)
    name_x = Column(Integer, default=248)
    name_y = Column(Integer, default=140)

    # Auto-role
    auto_role_id = Column(BigInteger, nullable=True)

    # Logging
    log_channel_id = Column(BigInteger, nullable=True)
    log_settings = Column(Text, default="{}")

    # AutoMod
    anti_bad_words = Column(Boolean, default=False)
    anti_links = Column(Boolean, default=False)
    anti_spam = Column(Boolean, default=False)
    automod_penalty = Column(String(20), default="mute")
    automod_bypass_roles = Column(Text, default="")

    # Ticket panel
    ticket_enabled = Column(Boolean, default=True)
    ticket_panel_title = Column(String(200), default="🎫 Support Tickets")
    ticket_panel_desc = Column(Text, default="Click the button below to open a ticket.")
    ticket_button_text = Column(String(80), default="Open Ticket")
    ticket_embed_color = Column(String(7), default="#5865F2")
    ticket_category_id = Column(BigInteger, nullable=True)
    ticket_support_role_id = Column(BigInteger, nullable=True)
    ticket_panel_channel_id = Column(BigInteger, nullable=True)
    ticket_panel_message_id = Column(BigInteger, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AutoResponder(Base):
    __tablename__ = "auto_responder"

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(BigInteger, nullable=False)
    trigger = Column(String(500), nullable=False)
    response = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class ActiveTicket(Base):
    __tablename__ = "active_tickets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(BigInteger, nullable=False)
    channel_id = Column(BigInteger, nullable=False, unique=True)
    user_id = Column(BigInteger, nullable=False)
    opened_at = Column(DateTime, default=datetime.utcnow)


class LogEntry(Base):
    __tablename__ = "log_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(BigInteger, nullable=False)
    event_type = Column(String(50), nullable=False)
    description = Column(Text, nullable=True)
    user_id = Column(BigInteger, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)


class Warning(Base):
    __tablename__ = "warnings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(BigInteger, nullable=False)
    user_id = Column(BigInteger, nullable=False)
    moderator_id = Column(BigInteger, nullable=False)
    reason = Column(Text, default="No reason")
    created_at = Column(DateTime, default=datetime.utcnow)


class SecurityLimit(Base):
    __tablename__ = "security_limits"

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(BigInteger, nullable=False)
    action_type = Column(String(50), nullable=False)
    max_count = Column(Integer, default=5)
    time_window = Column(Integer, default=60)
    punishment = Column(String(50), default="ban")
    enabled = Column(Boolean, default=False)


class SecurityWhitelist(Base):
    __tablename__ = "security_whitelist"

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(BigInteger, nullable=False)
    entity_type = Column(String(10), nullable=False)
    entity_id = Column(BigInteger, nullable=False)


class VoiceBotSetting(Base):
    __tablename__ = "voice_bot_settings"

    bot_index = Column(Integer, primary_key=True)
    label = Column(String(80), default="Voice Bot")
    voice_channel_id = Column(BigInteger, nullable=True)
    enabled = Column(Boolean, default=False)


def init_db():
    Base.metadata.create_all(engine)
    _migrate_legacy()


def _migrate_postgres():
    from sqlalchemy import text
    with engine.connect() as conn:
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS voice_bot_settings (
                    bot_index INTEGER PRIMARY KEY,
                    label VARCHAR(80) DEFAULT 'Voice Bot',
                    voice_channel_id BIGINT,
                    enabled BOOLEAN DEFAULT FALSE
                )
            """))
            conn.commit()
        except Exception:
            pass
    columns_to_add = [
        ("guild_settings", "log_settings", "TEXT DEFAULT '{}'"),
        ("guild_settings", "ticket_panel_channel_id", "BIGINT"),
        ("guild_settings", "ticket_panel_message_id", "BIGINT"),
        ("guild_settings", "avatar_x", "INTEGER DEFAULT 80"),
        ("guild_settings", "avatar_y", "INTEGER DEFAULT 86"),
        ("guild_settings", "avatar_size", "INTEGER DEFAULT 128"),
        ("guild_settings", "name_x", "INTEGER DEFAULT 248"),
        ("guild_settings", "name_y", "INTEGER DEFAULT 140"),
    ]
    with engine.connect() as conn:
        for table, col, typ in columns_to_add:
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {typ}"))
            except Exception:
                pass
        conn.commit()


def _migrate_legacy():
    if DATABASE_URL:
        _migrate_postgres()
        return
    import sqlite3
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS voice_bot_settings (
                bot_index INTEGER PRIMARY KEY,
                label VARCHAR(80) DEFAULT 'Voice Bot',
                voice_channel_id BIGINT,
                enabled BOOLEAN DEFAULT 0
            )
        """)
        cursor.execute("PRAGMA table_info(guild_settings)")
        existing = {row[1] for row in cursor.fetchall()}
        legacy = [
            ("ticket_panel_channel_id", "BIGINT"),
            ("ticket_panel_message_id", "BIGINT"),
            ("avatar_x", "INTEGER DEFAULT 80"),
            ("avatar_y", "INTEGER DEFAULT 86"),
            ("avatar_size", "INTEGER DEFAULT 128"),
            ("name_x", "INTEGER DEFAULT 248"),
            ("name_y", "INTEGER DEFAULT 140"),
            ("log_settings", "TEXT DEFAULT '{}'"),
        ]
        for col, typ in legacy:
            if col not in existing:
                cursor.execute(f"ALTER TABLE guild_settings ADD COLUMN {col} {typ}")
        conn.commit()
        conn.close()
    except Exception:
        pass


def get_session():
    return SessionLocal()


def get_settings(guild_id: int) -> GuildSettings:
    sess = get_session()
    try:
        settings = sess.get(GuildSettings, guild_id)
        if not settings:
            settings = GuildSettings(guild_id=guild_id)
            sess.add(settings)
            sess.commit()
        return settings
    finally:
        sess.close()
