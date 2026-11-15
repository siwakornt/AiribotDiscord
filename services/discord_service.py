# -*- coding: utf-8 -*-
"""discord_service.py - Helper สำหรับจัดการข้อความ Discord"""

MAX_MESSAGE_LEN = 2000  # ข้อความ Discord สูงสุด 2000 อักขระ


def split_message(text: str, limit: int = MAX_MESSAGE_LEN) -> list:
    """แยกข้อความยาวเป็นหลายก้อนไม่ให้เกิน limit (ตัดที่บรรทัด/เว้นวรรคก่อน)"""
    text = text or ""
    if len(text) <= limit:
        return [text] if text else []

    parts = []
    remaining = text
    while len(remaining) > limit:
        cut = remaining.rfind("\n", 0, limit)
        if cut <= 0:
            cut = remaining.rfind(" ", 0, limit)
        if cut <= 0:
            cut = limit
        parts.append(remaining[:cut])
        remaining = remaining[cut:].lstrip("\n ")
    if remaining:
        parts.append(remaining)
    return parts


async def send_long(channel, text: str, **kwargs):
    """ส่งข้อความยาวโดยแยกเป็นหลายข้อความอัตโนมัติ"""
    parts = split_message(text)
    if not parts:
        return None
    last = None
    for part in parts:
        last = await channel.send(part, **kwargs)
    return last
