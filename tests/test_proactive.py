# -*- coding: utf-8 -*-
"""test_proactive.py - ทดสอบระบบสุ่มชวนคุยของไอริ
กันน่ารำคาญ: งดช่วงนอน / เว้นห่างขั้นต่ำ / เพดานต่อวัน / ต้องมีคนคุยในช่องอื่น
"""

import asyncio
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ให้ import จาก root โปรเจกต์
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.proactive import (
    DAILY_CAP,
    FOLLOWUP_CHANCE,
    FOLLOWUP_MAX_DELAY,
    FOLLOWUP_MIN_DELAY,
    MIN_GAP_SECONDS,
    can_proactive,
    counters_for,
    dump_state,
    followup_delay_seconds,
    is_quiet_hour,
    maybe_followup,
    parse_state,
    pending_count,
    record_proactive,
    should_followup,
    spawn,
)

ICT = timezone(timedelta(hours=7))


def _dt(hour: int, minute: int = 0, day: int = 16) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=ICT)


def _ok_state(now: datetime) -> dict:
    """สถานะที่ผ่านทุกเงื่อนไข (ยกเว้น chance)"""
    ts = int(now.timestamp())
    return {
        "last_proactive_ts": ts - 7200,   # เธอทักครั้งล่าสุด 2 ชม. ก่อน
        "count_today": 0,
        "other_activity_ts": ts - 60,     # มีคนคุยในช่องอื่นเมื่อ 1 นาทีก่อน
        "own_channel_ts": None,           # ช่องของเธอเงียบ
    }


def test_is_quiet_hour_blocks_sleep_time():
    # 00:00 - 06:59 = ช่วงนอน ห้ามโพสต์
    assert is_quiet_hour(_dt(0, 0)) is True
    assert is_quiet_hour(_dt(3, 30)) is True
    assert is_quiet_hour(_dt(6, 59)) is True


def test_is_quiet_hour_allows_waking_time():
    assert is_quiet_hour(_dt(7, 0)) is False
    assert is_quiet_hour(_dt(12, 0)) is False
    assert is_quiet_hour(_dt(23, 59)) is False


def test_quiet_hour_blocks_proactive():
    now = _dt(3, 0)
    ok, reason = can_proactive(now, chance=1.0, **_ok_state(now))
    assert ok is False
    assert reason == "quiet_hour"


def test_waking_hour_allowed_when_everything_ok():
    now = _dt(10, 0)
    ok, reason = can_proactive(now, chance=1.0, **_ok_state(now))
    assert ok is True
    assert reason == "ok"


def test_min_gap_blocks_when_too_soon():
    now = _dt(10, 0)
    state = _ok_state(now)
    state["last_proactive_ts"] = int(now.timestamp()) - 30 * 60  # เพิ่งทักไป 30 นาทีก่อน
    ok, reason = can_proactive(now, chance=1.0, **state)
    assert ok is False
    assert reason == "cooldown"


def test_min_gap_boundary_exactly_allowed():
    now = _dt(10, 0)
    state = _ok_state(now)
    state["last_proactive_ts"] = int(now.timestamp()) - MIN_GAP_SECONDS
    ok, reason = can_proactive(now, chance=1.0, **state)
    assert ok is True
    assert reason == "ok"


def test_daily_cap_blocks():
    now = _dt(10, 0)
    state = _ok_state(now)
    state["count_today"] = DAILY_CAP
    ok, reason = can_proactive(now, chance=1.0, **state)
    assert ok is False
    assert reason == "daily_cap"


def test_no_recent_activity_in_other_channels_blocks():
    now = _dt(10, 0)
    state = _ok_state(now)
    state["other_activity_ts"] = int(now.timestamp()) - 30 * 60  # เซิร์ฟเงียบไป 30 นาที
    ok, reason = can_proactive(now, chance=1.0, **state)
    assert ok is False
    assert reason == "no_recent_activity"


def test_missing_activity_state_blocks():
    now = _dt(10, 0)
    state = _ok_state(now)
    state["other_activity_ts"] = None
    ok, reason = can_proactive(now, chance=1.0, **state)
    assert ok is False
    assert reason == "no_recent_activity"


def test_own_channel_just_talked_blocks():
    # มีคนเพิ่งพูดในช่องของเธอ → ไม่แทรก ปล่อยให้เป็นบทสนทนาปกติ
    now = _dt(10, 0)
    state = _ok_state(now)
    state["own_channel_ts"] = int(now.timestamp()) - 2 * 60
    ok, reason = can_proactive(now, chance=1.0, **state)
    assert ok is False
    assert reason == "own_channel_active"


def test_chance_zero_never_fires():
    now = _dt(10, 0)
    ok, reason = can_proactive(now, chance=0.0, **_ok_state(now))
    assert ok is False
    assert reason == "chance"


def test_chance_one_always_fires():
    now = _dt(10, 0)
    ok, reason = can_proactive(now, chance=1.0, **_ok_state(now))
    assert ok is True
    assert reason == "ok"


def test_followup_always_when_chance_one():
    assert should_followup(chance=1.0) is True


def test_followup_never_when_chance_zero():
    assert should_followup(chance=0.0) is False


def test_followup_default_rate_is_15_percent():
    # ค่าเริ่มต้นต้องเป็น 15% — ทดสอบด้วยสถิติ (n=2000 → เอ่อแคบมาก)
    trials = 2000
    hits = sum(1 for _ in range(trials) if should_followup())
    rate = hits / trials
    assert FOLLOWUP_CHANCE == 0.15
    assert 0.10 <= rate <= 0.20, f"อัตรา follow-up อยู่ที่ {rate:.3f} ไม่ใกล้ 0.15"


def test_followup_delay_within_one_minute():
    for _ in range(200):
        delay = followup_delay_seconds()
        assert FOLLOWUP_MIN_DELAY <= delay <= FOLLOWUP_MAX_DELAY
        assert delay <= 60


# ==========================================
# state: ตัวนับรายวัน + เวลาล่าสุด (ต้องจำข้าม restart ของ Render)
# ==========================================

def test_parse_state_empty_returns_defaults():
    state = parse_state(None)
    assert state["last_ts"] is None
    assert state["day"] is None
    assert state["count"] == 0


def test_parse_state_invalid_json_returns_defaults():
    # ค่าเสียหายใน DB ห้ามทำให้บอทล้ม
    state = parse_state("not json {{{")
    assert state["last_ts"] is None
    assert state["count"] == 0


def test_dump_state_roundtrip():
    now = _dt(10, 0)
    raw = dump_state(record_proactive(parse_state(None), now))
    last_ts, count = counters_for(parse_state(raw), now)
    assert last_ts == int(now.timestamp())
    assert count == 1


def test_record_then_counters_roundtrip():
    now = _dt(10, 0)
    state = record_proactive(parse_state(None), now)
    last_ts, count = counters_for(state, now)
    assert last_ts == int(now.timestamp())
    assert count == 1


def test_record_same_day_increments():
    state = record_proactive(parse_state(None), _dt(10, 0, day=16))
    state = record_proactive(state, _dt(11, 0, day=16))
    _, count = counters_for(state, _dt(12, 0, day=16))
    assert count == 2


def test_counters_reset_on_new_day():
    # โพสต์ไป 2 ครั้งเมื่อวาน → วันนี้นับใหม่เป็น 0 (ไม่งั้นบอทหยุดทักถาวร)
    state = record_proactive(parse_state(None), _dt(10, 0, day=15))
    state = record_proactive(state, _dt(11, 0, day=15))
    last_ts, count = counters_for(state, _dt(9, 0, day=16))
    assert count == 0
    # แต่เวลาล่าสุดยังอยู่ เพื่อให้กฎเว้นห่างยังทำงานข้ามวันได้
    assert last_ts == int(_dt(11, 0, day=15).timestamp())


def test_record_new_day_starts_at_one():
    state = record_proactive(parse_state(None), _dt(22, 0, day=15))
    state = record_proactive(state, _dt(8, 0, day=16))
    _, count = counters_for(state, _dt(9, 0, day=16))
    assert count == 1


# ==========================================
# maybe_followup: 15% คุยต่อภายใน 1 นาที
# ==========================================

def _harness(build_text):
    sent = []

    async def send(text):
        sent.append(text)

    return send, sent


def test_maybe_followup_sends_when_chance_one():
    async def build():
        return "อ้อ ลืมบอกไปอีกอย่างนึง~"

    send, sent = _harness(build)
    out = asyncio.run(maybe_followup(send, build, delay=0, chance=1.0))
    assert out == "อ้อ ลืมบอกไปอีกอย่างนึง~"
    assert sent == ["อ้อ ลืมบอกไปอีกอย่างนึง~"]


def test_maybe_followup_skips_when_chance_zero():
    async def build():
        return "ไม่ควรส่งข้อความนี้"

    send, sent = _harness(build)
    out = asyncio.run(maybe_followup(send, build, delay=0, chance=0.0))
    assert out is None
    assert sent == []


def test_maybe_followup_skips_when_no_text():
    # AI คืนว่าง → ห้ามส่งข้อความเปล่า
    async def build():
        return ""

    send, sent = _harness(build)
    out = asyncio.run(maybe_followup(send, build, delay=0, chance=1.0))
    assert out is None
    assert sent == []


def test_spawn_keeps_task_reference_until_done():
    # task ที่ไม่มีใครถือ reference ถูก asyncio เก็บทิ้งได้ระหว่างรัน (เงียบมาก)
    async def main():
        done = []

        async def work():
            done.append(1)

        task = spawn(work())
        assert pending_count() >= 1
        await task
        assert done == [1]
        assert pending_count() == 0

    asyncio.run(main())


if __name__ == "__main__":
    test_is_quiet_hour_blocks_sleep_time()
    test_is_quiet_hour_allows_waking_time()
    test_quiet_hour_blocks_proactive()
    test_waking_hour_allowed_when_everything_ok()
    test_min_gap_blocks_when_too_soon()
    test_min_gap_boundary_exactly_allowed()
    test_daily_cap_blocks()
    test_no_recent_activity_in_other_channels_blocks()
    test_missing_activity_state_blocks()
    test_own_channel_just_talked_blocks()
    test_chance_zero_never_fires()
    test_chance_one_always_fires()
    test_followup_always_when_chance_one()
    test_followup_never_when_chance_zero()
    test_followup_default_rate_is_15_percent()
    test_followup_delay_within_one_minute()
    test_parse_state_empty_returns_defaults()
    test_parse_state_invalid_json_returns_defaults()
    test_dump_state_roundtrip()
    test_record_then_counters_roundtrip()
    test_record_same_day_increments()
    test_counters_reset_on_new_day()
    test_record_new_day_starts_at_one()
    test_maybe_followup_sends_when_chance_one()
    test_maybe_followup_skips_when_chance_zero()
    test_maybe_followup_skips_when_no_text()
    test_spawn_keeps_task_reference_until_done()
    print("✅ test_proactive: all passed")
