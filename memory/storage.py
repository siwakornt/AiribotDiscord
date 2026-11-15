# -*- coding: utf-8 -*-
"""storage.py - SQLite wrapper สำหรับจัดการฐานข้อมูล"""

import sqlite3
import threading
from pathlib import Path

import config

_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS people (
    user_id INTEGER NOT NULL,
    guild_id INTEGER NOT NULL,
    username TEXT DEFAULT '',
    display_name TEXT DEFAULT '',
    nickname TEXT DEFAULT '',
    facts TEXT DEFAULT '[]',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, guild_id)
);

CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id INTEGER PRIMARY KEY,
    welcome_channel_id INTEGER DEFAULT 0,
    announcement_channel_id INTEGER DEFAULT 0,
    respond_mode TEXT DEFAULT 'mention',
    allowed_channels TEXT DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS user_stats (
    user_id INTEGER NOT NULL,
    guild_id INTEGER NOT NULL,
    money INTEGER DEFAULT 0,
    impression INTEGER DEFAULT 0,
    grudge INTEGER DEFAULT 0,
    inventory TEXT DEFAULT '{}',
    PRIMARY KEY (user_id, guild_id)
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT DEFAULT (datetime('now')),
    user_id INTEGER,
    guild_id INTEGER,
    user_name TEXT,
    action TEXT,
    item TEXT,
    amount INTEGER,
    total_price INTEGER,
    target_name TEXT
);

CREATE TABLE IF NOT EXISTS bot_settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS conversation_persist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    speaker_id INTEGER,
    speaker_name TEXT,
    content TEXT,
    role TEXT DEFAULT 'user',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_persist_channel
    ON conversation_persist (guild_id, channel_id, id);
"""


def get_conn() -> sqlite3.Connection:
    """คืนค่า connection แบบ thread-local (กันชนกันหลาย thread)"""
    conn = getattr(_local, "conn", None)
    if conn is None:
        config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(config.DB_PATH), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        _local.conn = conn
    return conn


def init_db():
    """สร้างตารางทั้งหมดหากยังไม่มี"""
    conn = get_conn()
    conn.executescript(SCHEMA)
    conn.commit()


def get_setting(key: str, default: str | None = None) -> str | None:
    """อ่านค่าตั้งค่าทั่วไปของบอท (bot_settings)"""
    conn = get_conn()
    row = conn.execute("SELECT value FROM bot_settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str):
    """บันทึกค่าตั้งค่าทั่วไปของบอท"""
    conn = get_conn()
    conn.execute(
        "INSERT INTO bot_settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value)),
    )
    conn.commit()


def close():
    conn = getattr(_local, "conn", None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
        _local.conn = None
