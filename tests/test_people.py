# -*- coding: utf-8 -*-
"""test_people.py - ทดสอบระบบ People Memory / Nickname (ใช้ SQLite ชั่วคราว)"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ตั้ง DB path ชั่วคราวก่อน import config
import config as _config
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_config.DB_PATH = Path(_tmp.name)

from memory import storage, people

storage.init_db()


def test_upsert_and_get():
    people.upsert_person(111, 999, username="user1", display_name="User One")
    p = people.get_person(111, 999)
    assert p is not None
    assert p["display_name"] == "User One"
    assert p["username"] == "user1"


def test_nickname_per_guild():
    # ตั้งชื่อเรียกในเซิร์ฟ 999
    people.set_nickname(111, 999, "ไอริ")
    assert people.get_nickname(111, 999) == "ไอริ"
    # เซิร์ฟอื่น (888) ต้องไม่เห็นชื่อเรียกนี้ (แยกตามเซิร์ฟเวอร์)
    people.upsert_person(111, 888, username="user1", display_name="User One")
    assert people.get_nickname(111, 888) == ""


def test_reset_nickname():
    people.set_nickname(222, 999, "bob")
    assert people.get_nickname(222, 999) == "bob"
    people.reset_nickname(222, 999)
    assert people.get_nickname(222, 999) == ""


def test_add_fact_dedup():
    people.upsert_person(333, 999, username="u3", display_name="U3")
    assert people.add_fact(333, 999, "ชอบวาดรูป") is True
    assert people.add_fact(333, 999, "ชอบวาดรูป") is False  # ซ้ำ
    facts = people.get_facts(333, 999)
    assert facts == ["ชอบวาดรูป"]


def test_memory_summary_contains_nickname():
    people.upsert_person(444, 999, username="u4", display_name="U4")
    people.set_nickname(444, 999, "น้องมะลิ")
    people.add_fact(444, 999, "ชอบกินขนม")
    summary = people.build_memory_summary(999)
    assert "น้องมะลิ" in summary
    assert "ชอบกินขนม" in summary
    assert "444" in summary


if __name__ == "__main__":
    test_upsert_and_get()
    test_nickname_per_guild()
    test_reset_nickname()
    test_add_fact_dedup()
    test_memory_summary_contains_nickname()
    print("✅ test_people: all passed")
