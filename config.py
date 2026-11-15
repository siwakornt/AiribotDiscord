# ==========================================
# config.py - โหลดค่า configuration
# อ่านจาก Environment Variables ก่อน (.bashrc / export) แล้วค่อย fallback ไปที่ .env
# ชื่อตัวแปรตรงกับ airi.py เดิม: DISCORD_TOKEN, GOOGLE_API_KEY, MODEL_NAME
# ==========================================

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

# ลำดับการอ่านค่า (load_dotenv ไม่ทับค่าที่มีอยู่แล้ว → ไฟล์แรกที่เจอค่าจะชนะ):
# 1) Environment Variables (.bashrc / export) ชนะเสมอ
# 2) /sdcard/.env — ไฟล์ตั้งค่าหลัก (DISCORD_TOKEN, GOOGLE_API_KEY, MODEL_NAME)
# 3) .env ในโปรเจกต์ — fallback สำหรับค่าตั้งเพิ่มเติม
load_dotenv(Path("/storage/emulated/0/.env"))
load_dotenv(BASE_DIR / ".env")


def _int_env(key: str, default: int = 0) -> int:
    try:
        return int(os.getenv(key, str(default)).strip() or default)
    except ValueError:
        return default


def _int_list_env(key: str) -> list:
    raw = os.getenv(key, "0") or "0"
    out = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            val = int(part)
            if val != 0:
                out.append(val)
        except ValueError:
            continue
    return out


# --- Discord ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "!").strip() or "!"

# --- Legacy channel lock (ตาม airi.py) ---
# CHANNEL_ID = ห้องที่ล็อกให้ไอริตอบ (0 = ยังไม่ล็อก → Mention ยังตอบได้ทุกห้อง)
# ค่า runtime จะถูกอัปเดตโดยคำสั่ง /jump และบันทึกลง bot_settings
CHANNEL_ID = _int_env("CHANNEL_ID", 0)
latest_channel_id = CHANNEL_ID

# --- AI Provider (Google Gemini) ---
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "").strip()
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-3.1-flash-lite").strip()

# โมเดลสำรอง — ใช้เมื่อโมเดลหลักตอบ 503/404 (เช่น "model is experiencing high demand")
# ตั้งค่าผ่าน env ได้: MODEL_FALLBACK=gemini-3.5-flash-lite,gemini-2.5-flash-lite
FALLBACK_MODELS = [
    m.strip()
    for m in (os.getenv("MODEL_FALLBACK", "gemini-3.5-flash-lite,gemini-2.5-flash-lite") or "").split(",")
    if m.strip() and m.strip() != MODEL_NAME
]

# --- Timezone ---
# ค่าเริ่มต้น = เวลาไทย (UTC+7)
# กันปัญหา server ที่รัน UTC (เช่น Render) ทำให้ไอริบอกเวลาผิด เช่น บอก 11 โมง ตอน 18:37
# ตั้งผ่าน env ได้: TIMEZONE=Asia/Bangkok | Asia/Tokyo | Europe/London ...
TIMEZONE = (os.getenv("TIMEZONE", "") or "Asia/Bangkok").strip()


def _load_tz():
    """โหลด tz database ถ้าหาไม่เจอ → fallback เป็น UTC+7 (เวลาไทย)"""
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(TIMEZONE)
    except Exception:
        # ไม่มี tz database ในเครื่อง → ใช้ offset ไทยเป็นค่าสำรอง
        return timezone(timedelta(hours=7))


TZ = _load_tz()


def now():
    """เวลาปัจจุบันตาม TIMEZONE ที่ตั้งไว้ — ใช้แทน datetime.now() ทุกจุด
    (datetime.now() จะคืนเวลา server/UTC ทำให้บอกเวลาผิดบน Render)"""
    return datetime.now(TZ)


# --- Respond Mode ---
RESPOND_MODE = (os.getenv("RESPOND_MODE", "mention") or "mention").strip().lower()
if RESPOND_MODE not in ("mention", "active", "selective"):
    RESPOND_MODE = "mention"

# --- Context ---
CONTEXT_MESSAGES = max(1, _int_env("CONTEXT_MESSAGES", 20))
CONTEXT_TTL_SECONDS = max(60, _int_env("CONTEXT_TTL_SECONDS", 7200))
ALLOWED_CHANNELS = _int_list_env("ALLOWED_CHANNELS")

# --- Channels ---
WELCOME_CHANNEL_ID = _int_env("WELCOME_CHANNEL_ID", 0)
ANNOUNCEMENT_CHANNEL_ID = _int_env("ANNOUNCEMENT_CHANNEL_ID", 0)

# --- Roles ---
SLEEP_ROLE_NAMES = [
    r.strip().lower()
    for r in (os.getenv("SLEEP_ROLE_NAMES", "member") or "").split(",")
    if r.strip()
]

# --- Paths ---
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "airi.db"
LOG_DIR = DATA_DIR / "logs"

# สร้างโฟลเดอร์ข้อมูล
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)


def validate() -> list:
    """ตรวจสอบค่าที่จำเป็น คืนค่าเป็นรายการข้อผิดพลาด"""
    errors = []
    if not DISCORD_TOKEN:
        errors.append("DISCORD_TOKEN ยังไม่ได้ตั้งค่า (export ใน .bashrc หรือใส่ใน .env)")
    if not GOOGLE_API_KEY:
        errors.append("GOOGLE_API_KEY ยังไม่ได้ตั้งค่า (export ใน .bashrc หรือใส่ใน .env)")
    return errors
