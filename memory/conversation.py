# -*- coding: utf-8 -*-
"""conversation.py - ระบบความจำบทสนทนา
Short-term: in-memory deque แยกตาม (guild_id, channel_id) + TTL
Persistent: SQLite (สำหรับข้อมูลข้ามรีสตาร์ท)
"""

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field, asdict

import config
from memory import storage


@dataclass
class MessageEntry:
    speaker_id: int
    speaker_name: str
    content: str
    role: str = "user"          # user | assistant
    reply_to: str = ""          # ข้อความที่กำลัง reply (ถ้ามี)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)

    def format_for_ai(self) -> str:
        name = self.speaker_name or "ไม่ทราบชื่อ"
        prefix = "ไอริ" if self.role == "assistant" else f"{name}"
        return f"{prefix}: {self.content}"


class ContextManager:
    """จัดการ Short-term memory แยกตามห้อง พร้อม TTL และจำนวนจำกัด"""

    def __init__(self, max_messages: int = None, ttl_seconds: int = None):
        self.max_messages = max_messages or config.CONTEXT_MESSAGES
        self.ttl_seconds = ttl_seconds or config.CONTEXT_TTL_SECONDS
        # key: (guild_id, channel_id) -> deque ของ MessageEntry
        self._store: dict = defaultdict(deque)
        self._last_touch: dict = {}

    def _key(self, guild_id: int, channel_id: int):
        return (guild_id, channel_id)

    def _expire(self, key):
        """ลบข้อความที่หมดอายุแล้ว"""
        now = time.time()
        dq = self._store.get(key)
        if not dq:
            return
        cutoff = now - self.ttl_seconds
        # deque บันทึกแบบ FIFO เก่าสุดอยู่ซ้ายมือ
        while dq and dq[0].timestamp < cutoff:
            dq.popleft()

    def add(self, guild_id: int, channel_id: int, entry: MessageEntry):
        key = self._key(guild_id, channel_id)
        self._expire(key)
        dq = self._store[key]
        dq.append(entry)
        while len(dq) > self.max_messages:
            dq.popleft()
        self._last_touch[key] = time.time()

    def get_history(self, guild_id: int, channel_id: int) -> list:
        key = self._key(guild_id, channel_id)
        self._expire(key)
        return list(self._store.get(key, []))

    def clear_channel(self, guild_id: int, channel_id: int):
        key = self._key(guild_id, channel_id)
        self._store.pop(key, None)
        self._last_touch.pop(key, None)

    def clear_all(self):
        self._store.clear()
        self._last_touch.clear()

    def stats(self, guild_id: int, channel_id: int) -> dict:
        key = self._key(guild_id, channel_id)
        self._expire(key)
        dq = self._store.get(key, deque())
        oldest = min((m.timestamp for m in dq), default=None)
        return {
            "messages": len(dq),
            "max_messages": self.max_messages,
            "ttl_seconds": self.ttl_seconds,
            "oldest_age_seconds": (time.time() - oldest) if oldest else None,
        }

    # --- Persistent memory (SQLite) ---
    def persist(self, guild_id: int, channel_id: int, entry: MessageEntry):
        """บันทึกลง SQLite สำหรับข้อมูลข้ามรีสตาร์ท (เก็บสูงสุด 200 ล่าสุดต่อห้อง)"""
        conn = storage.get_conn()
        try:
            conn.execute(
                """
                INSERT INTO conversation_persist (guild_id, channel_id, speaker_id, speaker_name, content, role)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (guild_id, channel_id, entry.speaker_id, entry.speaker_name, entry.content, entry.role),
            )
            # ตัดข้อมูลเก่าให้เหลือ 200 ต่อห้อง
            conn.execute(
                """
                DELETE FROM conversation_persist
                WHERE guild_id = ? AND channel_id = ?
                  AND id NOT IN (
                    SELECT id FROM conversation_persist
                    WHERE guild_id = ? AND channel_id = ?
                    ORDER BY id DESC LIMIT 200
                  )
                """,
                (guild_id, channel_id, guild_id, channel_id),
            )
            conn.commit()
        except Exception:
            pass

    def load_persistent(self, guild_id: int, channel_id: int) -> list:
        """โหลดประวัติ persistent กลับเข้า short-term (ตอนบอทเริ่มต้น/เปิดห้อง)"""
        conn = storage.get_conn()
        rows = conn.execute(
            """
            SELECT speaker_id, speaker_name, content, role, created_at
            FROM conversation_persist
            WHERE guild_id = ? AND channel_id = ?
            ORDER BY id ASC
            """,
            (guild_id, channel_id),
        ).fetchall()
        entries = []
        for r in rows:
            entries.append(
                MessageEntry(
                    speaker_id=r["speaker_id"] or 0,
                    speaker_name=r["speaker_name"] or "",
                    content=r["content"] or "",
                    role=r["role"] or "user",
                )
            )
        return entries


# singleton ใช้ร่วมกันทั้งบอท
context_manager = ContextManager()
