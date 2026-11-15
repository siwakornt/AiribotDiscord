# -*- coding: utf-8 -*-
"""test_dm.py - ทดสอบการตอบข้อความ DM (กล่องข้อความส่วนตัว)

บั๊กเดิม: เมื่อมีการล็อกห้องด้วย /jump (latest_channel_id != 0)
_should_respond คืน `channel.id == latest_channel_id` ซึ่งใน DM ไม่มีทางเท่ากัน
→ บอทไม่ตอบ DM เลย
"""

import sys
from contextlib import contextmanager
from pathlib import Path

# ให้ import จาก root โปรเจกต์
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from core.message_handler import _should_respond

BOT_ID = 9999


# ---- stub เบาๆ พอให้ _should_respond ทำงานได้ (ไม่แตะ logic ของ discord.py) ----

class _User:
    def __init__(self, user_id: int, is_bot: bool = False):
        self.id = user_id
        self.bot = is_bot

    def mentioned_in(self, message) -> bool:
        return False


class _Channel:
    def __init__(self, channel_id: int):
        self.id = channel_id


class _Message:
    def __init__(self, *, author_id: int, channel_id: int, guild=None, is_bot: bool = False):
        self.author = _User(author_id, is_bot)
        self.channel = _Channel(channel_id)
        self.guild = guild          # None = DM
        self.reference = None
        self.mention_everyone = False
        self.mentions = []


class _Bot:
    def __init__(self, user_id: int = BOT_ID):
        self.user = _User(user_id)


@contextmanager
def _locked_channel(channel_id: int):
    """ตั้งห้องที่ล็อกไว้ชั่วคราว แล้วคืนค่าเดิมเสมอ"""
    old = config.latest_channel_id
    config.latest_channel_id = channel_id
    try:
        yield
    finally:
        config.latest_channel_id = old


def test_dm_responds_even_when_channel_locked():
    # หัวใจของฟีเจอร์: DM ต้องตอบได้แม้มีการล็อกห้องอยู่
    with _locked_channel(12345):
        msg = _Message(author_id=1, channel_id=777, guild=None)
        assert _should_respond(msg, _Bot()) is True


def test_dm_responds_in_mention_mode():
    old_mode, old_lock = config.RESPOND_MODE, config.latest_channel_id
    try:
        config.latest_channel_id = 0
        config.RESPOND_MODE = "mention"     # โหมดปกติ: ตอบเฉพาะตอนถูก mention
        msg = _Message(author_id=1, channel_id=777, guild=None)
        assert _should_respond(msg, _Bot()) is True
    finally:
        config.RESPOND_MODE, config.latest_channel_id = old_mode, old_lock


def test_locked_channel_still_rejects_other_guild_channels():
    # regression: DM ต้องไม่ทำให้การล็อกห้องในเซิร์ฟเวอร์หลุด
    with _locked_channel(12345):
        msg = _Message(author_id=1, channel_id=999, guild=object())
        assert _should_respond(msg, _Bot()) is False


def test_locked_channel_still_accepts_its_own_channel():
    with _locked_channel(12345):
        msg = _Message(author_id=1, channel_id=12345, guild=object())
        assert _should_respond(msg, _Bot()) is True


def test_bot_ignores_itself_in_dm():
    with _locked_channel(12345):
        msg = _Message(author_id=BOT_ID, channel_id=777, guild=None)
        assert _should_respond(msg, _Bot()) is False


def test_other_bot_in_dm_is_ignored():
    with _locked_channel(12345):
        msg = _Message(author_id=555, channel_id=777, guild=None, is_bot=True)
        assert _should_respond(msg, _Bot()) is False


if __name__ == "__main__":
    test_dm_responds_even_when_channel_locked()
    test_dm_responds_in_mention_mode()
    test_locked_channel_still_rejects_other_guild_channels()
    test_locked_channel_still_accepts_its_own_channel()
    test_bot_ignores_itself_in_dm()
    test_other_bot_in_dm_is_ignored()
    print("✅ test_dm: all passed")
