# -*- coding: utf-8 -*-
"""people.py - ระบบจดจำบุคคล (People Memory)
Primary Identity คือ Discord User ID (ห้ามใช้ Display Name เป็นตัวระบุหลัก)
ชื่อเรียก (nickname) แยกตามเซิร์ฟเวอร์ (guild_id)
"""

import json
from datetime import datetime

from memory import storage


def upsert_person(user_id: int, guild_id: int, username: str = "", display_name: str = ""):
    """สร้าง/อัปเดตข้อมูลบุคคล"""
    conn = storage.get_conn()
    now = datetime.utcnow().isoformat()
    conn.execute(
        """
        INSERT INTO people (user_id, guild_id, username, display_name, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id, guild_id) DO UPDATE SET
            username = excluded.username,
            display_name = excluded.display_name,
            updated_at = excluded.updated_at
        """,
        (user_id, guild_id, username, display_name, now),
    )
    conn.commit()


def get_person(user_id: int, guild_id: int) -> dict | None:
    conn = storage.get_conn()
    row = conn.execute(
        "SELECT * FROM people WHERE user_id = ? AND guild_id = ?",
        (user_id, guild_id),
    ).fetchone()
    if row is None:
        return None
    d = dict(row)
    try:
        d["facts"] = json.loads(d.get("facts") or "[]")
    except Exception:
        d["facts"] = []
    return d


def set_nickname(user_id: int, guild_id: int, nickname: str) -> bool:
    """ตั้งชื่อเรียกให้สมาชิก (แยกตามเซิร์ฟเวอร์)"""
    conn = storage.get_conn()
    cur = conn.execute(
        """
        INSERT INTO people (user_id, guild_id, nickname, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id, guild_id) DO UPDATE SET
            nickname = excluded.nickname,
            updated_at = excluded.updated_at
        """,
        (user_id, guild_id, nickname, datetime.utcnow().isoformat()),
    )
    conn.commit()
    return cur.rowcount > 0


def reset_nickname(user_id: int, guild_id: int) -> bool:
    """ลบชื่อเรียก (รีเซ็ตเป็นค่าว่าง)"""
    conn = storage.get_conn()
    cur = conn.execute(
        "UPDATE people SET nickname = '', updated_at = ? WHERE user_id = ? AND guild_id = ?",
        (datetime.utcnow().isoformat(), user_id, guild_id),
    )
    conn.commit()
    return cur.rowcount > 0


def get_nickname(user_id: int, guild_id: int) -> str:
    """ดึงชื่อเรียก ถ้าไม่มีคืนค่า '' (ระบบจะใช้สรรพนามทั่วไปแทน)"""
    person = get_person(user_id, guild_id)
    if person and person.get("nickname"):
        return person["nickname"]
    return ""


def add_fact(user_id: int, guild_id: int, fact: str) -> bool:
    """เพิ่มข้อเท็จจริงเกี่ยวกับบุคคล (ป้องกันซ้ำ)"""
    person = get_person(user_id, guild_id)
    if person is None:
        upsert_person(user_id, guild_id)
        person = get_person(user_id, guild_id) or {"facts": []}
    facts = person.get("facts", [])
    if fact in facts:
        return False
    facts.append(fact)
    conn = storage.get_conn()
    conn.execute(
        "UPDATE people SET facts = ?, updated_at = ? WHERE user_id = ? AND guild_id = ?",
        (json.dumps(facts, ensure_ascii=False), datetime.utcnow().isoformat(), user_id, guild_id),
    )
    conn.commit()
    return True


def get_facts(user_id: int, guild_id: int) -> list:
    person = get_person(user_id, guild_id)
    return person.get("facts", []) if person else []


def list_people(guild_id: int) -> list:
    """รายชื่อสมาชิกที่มีข้อมูลในเซิร์ฟเวอร์นี้"""
    conn = storage.get_conn()
    rows = conn.execute(
        "SELECT user_id, username, display_name, nickname, facts FROM people WHERE guild_id = ?",
        (guild_id,),
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["facts"] = json.loads(d.get("facts") or "[]")
        except Exception:
            d["facts"] = []
        out.append(d)
    return out


def find_by_display_name(guild_id: int, display_name: str) -> dict | None:
    """ค้นหาบุคคลจาก Display Name (ใช้เมื่อ AI ระบุชื่อ ไม่ใช่ตัวระบุหลัก)"""
    conn = storage.get_conn()
    row = conn.execute(
        "SELECT * FROM people WHERE guild_id = ? AND lower(display_name) = lower(?)",
        (guild_id, display_name),
    ).fetchone()
    if row:
        d = dict(row)
        try:
            d["facts"] = json.loads(d.get("facts") or "[]")
        except Exception:
            d["facts"] = []
        return d
    return None


def build_memory_summary(guild_id: int) -> str:
    """สร้างสรุปความจำเกี่ยวกับทุกคนในเซิร์ฟเวอร์ ส่งให้ AI อ่าน"""
    people = list_people(guild_id)
    if not people:
        return "ยังไม่มีข้อมูลความจำบุคคลในเซิร์ฟเวอร์นี้"
    lines = ["=== สมุดบันทึกความจำเกี่ยวกับสมาชิกในเซิร์ฟเวอร์นี้ ==="]
    for p in people:
        name = p.get("nickname") or p.get("display_name") or p.get("username") or "ไม่ทราบชื่อ"
        facts = p.get("facts") or []
        facts_str = ", ".join(facts) if facts else "ยังไม่มีข้อมูลเพิ่มเติม"
        lines.append(f"- {name} (User ID: {p['user_id']}): {facts_str}")
    return "\n".join(lines)
