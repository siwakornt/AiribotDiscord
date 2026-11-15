# -*- coding: utf-8 -*-
"""test_memory.py - ทดสอบระบบ Conversation Memory / Context Manager"""

import sys
import time
from pathlib import Path

# ให้ import จาก root โปรเจกต์
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from memory.conversation import ContextManager, MessageEntry


def test_add_and_get_history():
    cm = ContextManager(max_messages=5, ttl_seconds=3600)
    for i in range(3):
        cm.add(1, 100, MessageEntry(speaker_id=i, speaker_name=f"u{i}", content=f"msg{i}"))
    hist = cm.get_history(1, 100)
    assert len(hist) == 3
    assert hist[0].content == "msg0"
    assert hist[-1].content == "msg2"


def test_max_messages_limit():
    cm = ContextManager(max_messages=5, ttl_seconds=3600)
    for i in range(10):
        cm.add(1, 100, MessageEntry(speaker_id=1, speaker_name="u", content=f"m{i}"))
    hist = cm.get_history(1, 100)
    assert len(hist) == 5
    # เก็บใหม่สุดไว้
    assert hist[-1].content == "m9"


def test_separate_by_channel():
    cm = ContextManager(max_messages=10, ttl_seconds=3600)
    cm.add(1, 100, MessageEntry(speaker_id=1, speaker_name="u", content="ห้องA"))
    cm.add(1, 200, MessageEntry(speaker_id=1, speaker_name="u", content="ห้องB"))
    assert len(cm.get_history(1, 100)) == 1
    assert len(cm.get_history(1, 200)) == 1
    # ล้างห้องA ต้องไม่กระทบห้องB
    cm.clear_channel(1, 100)
    assert len(cm.get_history(1, 100)) == 0
    assert len(cm.get_history(1, 200)) == 1


def test_ttl_expiry():
    cm = ContextManager(max_messages=10, ttl_seconds=1)
    cm.add(1, 100, MessageEntry(speaker_id=1, speaker_name="u", content="เก่า", timestamp=time.time() - 10))
    cm.add(1, 100, MessageEntry(speaker_id=1, speaker_name="u", content="ใหม่"))
    hist = cm.get_history(1, 100)
    assert len(hist) == 1
    assert hist[0].content == "ใหม่"


def test_clear_all():
    cm = ContextManager()
    cm.add(1, 100, MessageEntry(speaker_id=1, speaker_name="u", content="x"))
    cm.clear_all()
    assert cm.get_history(1, 100) == []


if __name__ == "__main__":
    test_add_and_get_history()
    test_max_messages_limit()
    test_separate_by_channel()
    test_ttl_expiry()
    test_clear_all()
    print("✅ test_memory: all passed")
