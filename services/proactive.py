# -*- coding: utf-8 -*-
"""proactive.py - ระบบสุ่มชวนคุยของไอริ

ไอริโพสต์ขึ้นมาเองในช่องของเธอ เมื่อมีคนคุยกันอยู่ในช่องอื่นของเซิร์ฟเวอร์
กันน่ารำคาญด้วยเงื่อนไข:
  - งดช่วงนอน (00:00-07:00 ตามเวลาของบอท)
  - เว้นห่างจากครั้งล่าสุดอย่างน้อย 1 ชั่วโมง
  - เพดาน 4 ข้อความ/วัน
  - ต้องมีคนเพิ่งคุยในช่องอื่นภายใน 10 นาที
  - ไม่แทรกบทสนทนาที่กำลังดำเนินอยู่ในช่องของเธอเอง
  - มีโอกาสสุ่ม 2% ต่อนาที (ค่าเหล่านี้คือ my call — ปรับได้ที่นี่)

หลังไอริส่งข้อความเสร็จ มีโอกาส 15% ที่เธอจะส่งข้อความเสริมอีก 1 ครั้ง
ภายใน 1 นาที ให้รู้สึกเหมือนเธอนึกอะไรขึ้นมาได้
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from datetime import datetime

logger = logging.getLogger("airi.proactive")

# --- ค่าตั้งระบบสุ่มชวนคุย ---
QUIET_START_HOUR = 0        # งดโพสต์ตั้งแต่...
QUIET_END_HOUR = 7          # ...จนถึง (เวลา .hour ของ config.now())
MIN_GAP_SECONDS = 60 * 60   # เว้นห่างจากครั้งล่าสุด 1 ชั่วโมง
DAILY_CAP = 4               # เพดานต่อวัน
TRIGGER_CHANCE = 0.02       # โอกาสต่อนาที เมื่อผ่านทุกเงื่อนไขแล้ว
ACTIVITY_WINDOW_SECONDS = 10 * 60  # ต้องมีคนคุยในช่องอื่นภายใน 10 นาที

# --- ค่าตั้งข้อความเสริม (follow-up) ---
FOLLOWUP_CHANCE = 0.15      # 15% หลังข้อความของเธอเอง
FOLLOWUP_MIN_DELAY = 5      # รออย่างน้อย 5 วินาที
FOLLOWUP_MAX_DELAY = 60     # และไม่เกิน 1 นาที


def is_quiet_hour(now: datetime) -> bool:
    """True = อยู่ในช่วงห้ามโพสต์ (ช่วงนอน)"""
    return QUIET_START_HOUR <= now.hour < QUIET_END_HOUR


def can_proactive(
    now: datetime,
    *,
    last_proactive_ts: int | None = None,
    count_today: int = 0,
    other_activity_ts: int | None = None,
    own_channel_ts: int | None = None,
    chance: float = TRIGGER_CHANCE,
) -> tuple[bool, str]:
    """ตัดสินว่ารอบนี้ไอริควรโพสต์ขึ้นมาเองไหม

    คืน (ควรโพสต์, เหตุผล) — เหตุผลไว้ใช้ log/debug:
    "ok" | "quiet_hour" | "no_recent_activity" | "own_channel_active"
    | "cooldown" | "daily_cap" | "chance"
    """
    if is_quiet_hour(now):
        return False, "quiet_hour"

    ts = int(now.timestamp())

    if other_activity_ts is None or (ts - other_activity_ts) > ACTIVITY_WINDOW_SECONDS:
        return False, "no_recent_activity"

    if own_channel_ts is not None and (ts - own_channel_ts) <= ACTIVITY_WINDOW_SECONDS:
        return False, "own_channel_active"

    if last_proactive_ts is not None and (ts - last_proactive_ts) < MIN_GAP_SECONDS:
        return False, "cooldown"

    if count_today >= DAILY_CAP:
        return False, "daily_cap"

    if not (random.random() < chance):
        return False, "chance"

    return True, "ok"


def should_followup(chance: float = FOLLOWUP_CHANCE) -> bool:
    """True = ครั้งนี้ไอริส่งข้อความเสริมต่อ (ค่าเริ่มต้น 15%)"""
    return random.random() < chance


def followup_delay_seconds() -> int:
    """เวลาที่จะรอส่งข้อความเสริม (สุ่มภายใน 1 นาที)"""
    return random.randint(FOLLOWUP_MIN_DELAY, FOLLOWUP_MAX_DELAY)


async def maybe_followup(
    send,
    build_text,
    *,
    delay: float | None = None,
    chance: float = FOLLOWUP_CHANCE,
) -> str | None:
    """รอสุ่มภายใน 1 นาที แล้วส่งข้อความเสริมด้วยโอกาส 15%

    send:      async callable(text) — ส่งข้อความออกไป
    build_text: async callable() -> str — แต่งข้อความเสริม (คืนว่าง = ไม่ส่ง)

    คืนข้อความที่ส่ง หรือ None ถ้ารอบนี้ไม่ส่ง
    """
    seconds = followup_delay_seconds() if delay is None else delay
    if seconds > 0:
        await asyncio.sleep(seconds)

    if not should_followup(chance):
        return None

    text = await build_text()
    if not text or not str(text).strip():
        return None

    await send(text)
    return text


async def send_followup(channel, previous_text: str) -> str | None:
    """รอสุ่มภายใน 1 นาที แล้วให้ไอริคุยต่อเองด้วยโอกาส 15%

    ใช้ brain แต่งข้อความ (และตัด指令 ให้) — คืนข้อความที่ส่ง หรือ None
    error ทั้งหมด log ไว้ ห้ามทำให้ task ล้ม
    """
    from core import brain

    async def build() -> str:
        return await brain.get_followup(previous_text)

    try:
        sent = await maybe_followup(channel.send, build)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.warning("followup error: %s", e)
        return None

    if sent:
        logger.info("Follow-up sent: %s", sent[:60])
    return sent


# ==========================================
# task tracking: ถือ reference ไว้จนงานเสร็จ
# task ที่ไม่มีใครถือถูก asyncio เก็บทิ้งได้ระหว่างรัน — เงียบมาก ไม่มี error
# ==========================================

_pending: set[asyncio.Task] = set()


def spawn(coro) -> asyncio.Task:
    """สร้าง task โดยถือ reference ไว้จนเสร็จ กันงานหายเงียบๆ"""
    task = asyncio.create_task(coro)
    _pending.add(task)
    task.add_done_callback(_pending.discard)
    return task


def pending_count() -> int:
    """จำนวนงานที่ยังค้าง (ไว้ตรวจในเทสต์/log)"""
    return len(_pending)


def cancel_all() -> None:
    """ยกเลิกงานค้างทั้งหมด — เรียกตอนปิดบอท"""
    for t in list(_pending):
        t.cancel()
    _pending.clear()


# ==========================================
# state: ตัวนับรายวัน + เวลาล่าสุด
# เก็บเป็น JSON ใน bot_settings — Render ดิสก์หายทุก redeploy อยู่แล้ว
# แต่ระหว่างรันต้องจำข้าม restart ให้ได้
# ==========================================

def _empty_state() -> dict:
    return {"last_ts": None, "day": None, "count": 0}


def parse_state(raw: str | None) -> dict:
    """อ่าน state จาก JSON — ค่าเสียหาย/ว่าง → ค่าเริ่มต้น ห้ามทำให้บอทล้ม"""
    if not raw:
        return _empty_state()
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            return _empty_state()
        return {
            "last_ts": int(data["last_ts"]) if data.get("last_ts") else None,
            "day": str(data["day"]) if data.get("day") else None,
            "count": int(data.get("count", 0)),
        }
    except (TypeError, ValueError):
        return _empty_state()


def dump_state(state: dict) -> str:
    """แปลง state เป็น JSON สำหรับบันทึกลง DB"""
    return json.dumps(state, ensure_ascii=False)


def counters_for(state: dict, now: datetime) -> tuple[int | None, int]:
    """คืน (last_proactive_ts, count_today)

    ข้ามวันแล้ว count ต้องเป็น 0 — ไม่งั้นหลังโพสต์ครบ DAILY_CAP วันแรก
    บอทจะหยุดทักถาวร
    """
    day = now.strftime("%Y-%m-%d")
    count = state["count"] if state.get("day") == day else 0
    return state.get("last_ts"), count


def record_proactive(state: dict, now: datetime) -> dict:
    """คืน state ใหม่หลังไอริโพสต์สำเร็จรอบนี้ (นับ +1 / ตั้งเวลาล่าสุด)"""
    day = now.strftime("%Y-%m-%d")
    count = state["count"] if state.get("day") == day else 0
    return {"last_ts": int(now.timestamp()), "day": day, "count": count + 1}
