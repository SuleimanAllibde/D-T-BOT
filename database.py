import os
from datetime import datetime

from sqlalchemy import create_engine, Column, Integer, BigInteger, String, Text, Boolean, DateTime, JSON, Float
from sqlalchemy.orm import declarative_base, sessionmaker

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "dt_bot.db")
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "data", "uploads")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

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
    automod_penalty = Column(String(20), default="mute")  # mute, kick, ban
    automod_bypass_roles = Column(Text, default="")  # comma-separated role IDs

    # Ticket panel customization
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
    # Add missing columns for existing databases (schema migration)
    _migrate_add_column("guild_settings", "ticket_panel_channel_id", "BIGINT")
    _migrate_add_column("guild_settings", "ticket_panel_message_id", "BIGINT")
    _migrate_add_column("guild_settings", "avatar_x", "INTEGER DEFAULT 80")
    _migrate_add_column("guild_settings", "avatar_y", "INTEGER DEFAULT 86")
    _migrate_add_column("guild_settings", "avatar_size", "INTEGER DEFAULT 128")
    _migrate_add_column("guild_settings", "name_x", "INTEGER DEFAULT 248")
    _migrate_add_column("guild_settings", "name_y", "INTEGER DEFAULT 140")


def _migrate_add_column(table: str, column: str, col_type: str):
    import sqlite3
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(f"PRAGMA table_info({table})")
        existing = [row[1] for row in cursor.fetchall()]
        if column not in existing:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
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
