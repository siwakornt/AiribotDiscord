# -*- coding: utf-8 -*-
"""test_brain.py - ทดสอบการประกอบ System Prompt ของไอริ

จุดที่คุม: ค่าความประทับใจ/ความงอน ต้องถูกส่งเข้า prompt
พร้อม "คำสั่งปรับนิสัย" ตามค่า (ไม่ใช่แค่บอกตัวเลข)
และฟีเจอร์指令 เดิมห้ามหายไป
"""

import sys
from pathlib import Path

# ให้ import จาก root โปรเจกต์
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.brain import build_status_block


def test_status_block_contains_current_values():
    text = build_status_block(75, 2)
    assert "75 / 100" in text
    assert "เต็ม 100" in text
    assert "2 / 4" in text
    assert "เต็ม 4" in text


def test_status_block_zero_values():
    # ผู้ใช้ใหม่ (ค่า 0) ต้องเห็นค่าถูกต้อง ไม่ใช่ค้างจากคนก่อนหน้า
    text = build_status_block(0, 0)
    assert "0 / 100" in text
    assert "0 / 4" in text


def test_status_block_maps_impression_to_behavior():
    text = build_status_block(75, 0)
    # ต้องมีขั้นพฤติกรรมครบทุกช่วง — ไม่ใช่แค่บอกตัวเลขแล้วปล่อย AI เดา
    for marker in ("0-30", "31-70", "71-90", "91-100"):
        assert marker in text, f"ไม่มีขั้นพฤติกรรม {marker}"
    assert "คลั่งรัก" in text
    assert "ตอบกลับแบบรักผู้ใช้ขึ้นเรื่อยๆ" in text


def test_status_block_maps_grudge_to_behavior():
    text = build_status_block(50, 3)
    for marker in ("1-2", "3-4"):
        assert marker in text, f"ไม่มีขั้นความงอน {marker}"
    assert "งอนจริง" in text


def test_status_block_keeps_directive_instructions():
    # ฟีเจอร์指令 เดิม (ปรับค่าอัตโนมัติ) ห้ามหายไปจากการ refactor
    text = build_status_block(50, 1)
    assert "指令" in text
    assert "ผู้ใช้จะไม่เห็น" in text


def test_status_block_forbids_revealing_values():
    # ผู้ใช้ห้ามเห็นตัวเลขค่าความรู้สึก — ต้องสั่งไว้ใน prompt
    text = build_status_block(80, 2)
    assert "ห้ามพูดถึงตัวเลข" in text


if __name__ == "__main__":
    test_status_block_contains_current_values()
    test_status_block_zero_values()
    test_status_block_maps_impression_to_behavior()
    test_status_block_maps_grudge_to_behavior()
    test_status_block_keeps_directive_instructions()
    test_status_block_forbids_revealing_values()
    print("✅ test_brain: all passed")
