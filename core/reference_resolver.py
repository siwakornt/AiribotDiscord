# -*- coding: utf-8 -*-
"""reference_resolver.py - ระบบเข้าใจบุคคลจากบริบท (Reference Resolution)
วิเคราะห์ว่าคำสรรพนาม/ชื่อในข้อความหมายถึงใคร โดยใช้:
  - ข้อความก่อนหน้า + ผู้พูดแต่ละข้อความ
  - ชื่อเรียกที่ตั้งไว้
  - Discord Reply Reference
  - ความต่อเนื่องของหัวข้อ
ถ้าไม่มั่นใจ ให้ถามกลับแทนการเดา (ส่งสัญญาณ uncertainty ไปให้ AI ตัดสินใจ)
"""

import re

from memory import people as people_store

# คำสรรพนามที่มักอ้างถึงบุคคลที่สาม
PRONOUNS_TH = ["เขา", "เค้า", "เค้าเอง", "เธอ", "หมอนั่น", "หมอนี่", "ไอ้นั่น", "ไอ้นี่", "นาง", "นายคนนั้น"]
PRONOUNS_EN = ["he", "him", "his", "she", "her", "hers", "they", "them"]

# คำชี้ว่ากำลังถามถึงบุคคล
REFERENCE_CUES = ["คนนั้น", "คนนี้", "คนไหน", "ใคร", "ของเขา", "ของเธอ", "ของเค้า", "เล่นกับ", "คุยกับ", "ไปกับ"]


def _normalize(text: str) -> str:
    return (text or "").strip().lower()


def extract_mentioned_ids(message) -> set:
    """ดึง User ID ที่ถูก Mention ในข้อความ"""
    return {u.id for u in message.mentions}


def extract_reply_target_id(message) -> int | None:
    """ดึง User ID ของข้อความที่กำลัง Reply ถึง (ถ้า reply หาผู้พูดเดิมไม่ได้)"""
    ref = message.reference
    if ref is None:
        return None
    try:
        if ref.resolved and hasattr(ref.resolved, "author"):
            return ref.resolved.author.id
    except Exception:
        pass
    return None


def find_named_targets(text: str, guild_id: int) -> list:
    """
    ค้นหาชื่อบุคคลที่ปรากฏในข้อความ โดยเทียบกับ display_name/nickname
    ที่ระบบจำไว้ คืนค่าเป็น list ของ (user_id, matched_name)
    """
    found = []
    norm = _normalize(text)
    # ดึงรายชื่อทั้งหมดในเซิร์ฟเวอร์
    for p in people_store.list_people(guild_id):
        uid = p["user_id"]
        candidates = []
        if p.get("nickname"):
            candidates.append(p["nickname"])
        if p.get("display_name"):
            candidates.append(p["display_name"])
        if p.get("username"):
            candidates.append(p["username"])
        for name in candidates:
            n = _normalize(name)
            if n and n in norm:
                found.append((uid, name))
                break
    return found


def has_pronoun_reference(text: str) -> bool:
    """ตรวจว่าข้อความมีสรรพนาม/คำชี้บุคคลหรือไม่"""
    norm = _normalize(text)
    for p in PRONOUNS_TH:
        if p in norm:
            return True
    words = re.findall(r"[a-zA-Z]+", norm)
    for w in words:
        if w in PRONOUNS_EN:
            return True
    for cue in REFERENCE_CUES:
        if cue in norm:
            return True
    return False


def build_reference_hint(guild_id: int, channel_history: list, current_text: str, reply_target_id: int | None) -> str:
    """
    สร้างข้อความแนะนำ (hint) ส่งให้ AI ช่วยระบุบุคคล
    channel_history: list[MessageEntry] ของห้องนี้ (ใหม่สุดท้าย)
    คืนค่าเป็น string ว่างได้ถ้าไม่มีอะไรน่าสนใจ
    """
    hints = []

    # 1) Mention / Reply ในข้อความปัจจุบัน
    # (ส่วนนี้จะถูกส่งแยกโดย message_handler ผ่านข้อความจริง)

    # 2) Reply target
    if reply_target_id:
        person = people_store.get_person(reply_target_id, guild_id)
        if person:
            name = person.get("nickname") or person.get("display_name") or person.get("username") or str(reply_target_id)
            hints.append(f"ข้อความนี้กำลัง Reply ถึงข้อความของ: {name} (User ID: {reply_target_id})")

    # 3) ผู้พูด 3 ข้อความล่าสุด (เพื่อให้ AI เห็นว่าใครพูดอะไร)
    recent = channel_history[-6:]
    if recent:
        lines = ["บริบทสนทนาล่าสุดในห้องนี้:"]
        for m in recent:
            name = m.speaker_name or "ไม่ทราบชื่อ"
            who = "ไอริ" if m.role == "assistant" else name
            lines.append(f"- {who}: {m.content[:120]}")
        hints.append("\n".join(lines))

    # 4) ถ้ามีสรรพนาม ให้แนบรายชื่อผู้ที่อาจถูกอ้างถึง
    if has_pronoun_reference(current_text):
        known = people_store.list_people(guild_id)
        if known:
            names = []
            for p in known:
                label = p.get("nickname") or p.get("display_name") or p.get("username")
                if label:
                    names.append(f"{label} (ID: {p['user_id']})")
            if names:
                hints.append(
                    "สมาชิกที่จำไว้ (อาจเป็นบุคคลที่ถูกกล่าวถึง): " + ", ".join(names)
                    + "\nหากไม่แน่ใจว่าสรรพนามหมายถึงใคร ให้ถามกลับ ไม่เดา"
                )

    return "\n".join(hints)
