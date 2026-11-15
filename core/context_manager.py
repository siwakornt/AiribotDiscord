# -*- coding: utf-8 -*-
"""context_manager.py - ตัวเชื่อมระหว่าง conversation memory กับการสร้าง prompt"""

from memory.conversation import context_manager, MessageEntry


def add_user_message(guild_id: int, channel_id: int, speaker_id: int, speaker_name: str, content: str, reply_to: str = "") -> MessageEntry:
    entry = MessageEntry(
        speaker_id=speaker_id,
        speaker_name=speaker_name,
        content=content,
        role="user",
        reply_to=reply_to,
    )
    context_manager.add(guild_id, channel_id, entry)
    context_manager.persist(guild_id, channel_id, entry)
    return entry


def add_assistant_message(guild_id: int, channel_id: int, content: str) -> MessageEntry:
    entry = MessageEntry(
        speaker_id=0,
        speaker_name="ไอริ",
        content=content,
        role="assistant",
    )
    context_manager.add(guild_id, channel_id, entry)
    context_manager.persist(guild_id, channel_id, entry)
    return entry


def get_history(guild_id: int, channel_id: int) -> list:
    return context_manager.get_history(guild_id, channel_id)


def clear_channel(guild_id: int, channel_id: int):
    context_manager.clear_channel(guild_id, channel_id)


def get_stats(guild_id: int, channel_id: int) -> dict:
    return context_manager.stats(guild_id, channel_id)


def build_context_block(guild_id: int, channel_id: int, max_chars: int = 8000) -> str:
    """แปลง history เป็นข้อความสำหรับใส่ใน prompt"""
    history = get_history(guild_id, channel_id)
    if not history:
        return "ยังไม่มีบทสนทนาในห้องนี้"
    lines = []
    total = 0
    for m in history:
        line = m.format_for_ai()
        total += len(line)
        if total > max_chars:
            break
        lines.append(line)
    return "\n".join(lines)
