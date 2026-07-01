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

SessionLocal = sessionmaker(bind=engine)
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


def init_db():
    Base.metadata.create_all(engine)
    _migrate_legacy()


def _migrate_legacy():
    if DATABASE_URL:
        return
    import sqlite3
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
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
