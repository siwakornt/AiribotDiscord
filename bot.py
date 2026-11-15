# -*- coding: utf-8 -*-
"""
bot.py - จุดเริ่มต้น Airi Discord Bot
รันด้วย: python bot.py
"""

import os
import sys
import asyncio
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import aiohttp
import discord
from aiohttp import web
from discord.ext import commands, tasks

import config
from memory import storage
from core import message_handler
from services.ai_service import ai_service, TOTAL_REQUEST_BUDGET

# ==========================================
# Logging (ไม่บันทึก Token/API Key ลง log)
# ==========================================
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

def setup_logging():
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # console
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(logging.Formatter(LOG_FORMAT, datefmt="%H:%M:%S"))
    root.addHandler(ch)

    # file (หมุนเวียน 1MB x 3)
    try:
        log_file = config.LOG_DIR / "airi.log"
        fh = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        fh.setFormatter(logging.Formatter(LOG_FORMAT))
        root.addHandler(fh)
    except Exception:
        pass

    # ปิด log จาก library ที่ noise เกินไป
    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.getLogger("google").setLevel(logging.WARNING)

setup_logging()
logger = logging.getLogger("airi.bot")

# ==========================================
# Bot Setup
# ==========================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.messages = True
intents.reactions = True

# ==========================================
# Extensions (คำสั่งทั้งหมด)
# ==========================================
EXTENSIONS = [
    "commands.slash",
    "commands.nickname",
    "commands.memory",
    "commands.admin",
    "commands.economy",
    "commands.games",
]


# ==========================================
# Health Server + Keep-alive (สำหรับ Render Web Service)
# ==========================================
# Render จะสแกนหาพอร์ตที่เปิดอยู่เพื่อเช็คว่า deploy ผ่านไหม
# ถ้าไม่เปิดพอร์ตเลยจะขึ้น "No open ports detected" แล้ว deploy timeout
# บอท Discord ไม่ต้องรับทราฟฟิกจริง จึงเปิด HTTP server เล็กๆ ไว้ตอบ /health เท่านั้น
_health_started = False  # กัน start ซ้ำ (on_ready ถูกเรียกซ้ำได้ทุกครั้งที่ reconnect)
_health_runner = None    # web.AppRunner ไว้ cleanup ตอนปิดบอท
_keepalive_task = None   # background task ยิง ping ตัวเองทุก 10 นาที

KEEPALIVE_INTERVAL = 600  # วินาที (10 นาที)
KEEPALIVE_TIMEOUT = 10    # วินาที


def _health_port() -> int:
    """อ่านพอร์ตจาก env PORT (Render ตั้งให้เอง) default 10000"""
    try:
        return int((os.getenv("PORT", "") or "10000").strip())
    except ValueError:
        return 10000


async def _health_ok(request: web.Request) -> web.Response:
    """ตอบ OK status 200 ให้ Render health check"""
    return web.Response(text="OK", status=200)


async def _keepalive_loop(base_url: str) -> None:
    """ยิง GET /health ไปที่ตัวเองทุก 10 นาที กัน Render แพลนฟรี spin down
    ห้ามให้ task ตาย: จับ exception ไว้ใน loop แล้วทำงานต่อ"""
    while True:
        await asyncio.sleep(KEEPALIVE_INTERVAL)
        try:
            timeout = aiohttp.ClientTimeout(total=KEEPALIVE_TIMEOUT)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"{base_url}/health") as resp:
                    logger.info(
                        "Keep-alive ping OK: %s/health (status=%s)", base_url, resp.status
                    )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(
                "Keep-alive ping failed: %s/health - %s: %s", base_url, type(e).__name__, e
            )


def _start_keepalive() -> None:
    """เริ่ม task keep-alive (ข้ามถ้าไม่ได้ตั้ง RENDER_EXTERNAL_URL)"""
    global _keepalive_task
    base_url = (os.getenv("RENDER_EXTERNAL_URL", "") or "").strip().rstrip("/")
    if not base_url:
        logger.info("Keep-alive skipped (RENDER_EXTERNAL_URL not set)")
        return
    if _keepalive_task is not None and not _keepalive_task.done():
        return
    _keepalive_task = asyncio.create_task(_keepalive_loop(base_url))
    logger.info(
        "Keep-alive started: GET %s/health ทุก %s วินาที", base_url, KEEPALIVE_INTERVAL
    )


async def _start_health_server() -> None:
    """เปิด HTTP server ที่ 0.0.0.0:PORT ตอบ / และ /health
    รันใน event loop เดียวกับบอท — กัน start ซ้ำด้วย _health_started"""
    global _health_started, _health_runner
    if _health_started:
        return
    _health_started = True

    port = _health_port()
    app = web.Application()
    app.router.add_get("/", _health_ok)
    app.router.add_get("/health", _health_ok)

    runner = web.AppRunner(app)
    try:
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
    except Exception as e:
        # bind พอร์ตไม่ได้ -> log error แต่ห้ามให้บอทล้ม
        logger.error(
            "Health server failed to bind 0.0.0.0:%s - %s: %s",
            port, type(e).__name__, e, exc_info=True,
        )
        try:
            await runner.cleanup()
        except Exception:
            pass
        return

    _health_runner = runner
    logger.info("Health server started on 0.0.0.0:%s (GET / , GET /health)", port)
    _start_keepalive()


async def _stop_health_server() -> None:
    """ยกเลิก keep-alive task + ปิด health server อย่างถูกต้องตอนบอทปิด"""
    global _keepalive_task, _health_runner

    if _keepalive_task is not None:
        _keepalive_task.cancel()
        try:
            await _keepalive_task
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("Keep-alive stop error: %s", e)
        _keepalive_task = None
        logger.info("Keep-alive stopped")

    if _health_runner is not None:
        try:
            await _health_runner.cleanup()
        except Exception as e:
            logger.warning("Health server cleanup error: %s", e)
        _health_runner = None
        logger.info("Health server stopped")


class AiriBot(commands.Bot):
    """Bot subclass เพื่อ override setup_hook (โหลด extensions ก่อน sync)"""

    async def setup_hook(self):
        # เปิด health server ใน event loop เดียวกับบอท
        # setup_hook ถูกเรียกครั้งเดียว + _health_started กันซ้ำ
        # แม้ on_ready ถูกเรียกหลายครั้งตอน reconnect ก็จะไม่ start ซ้ำ
        await _start_health_server()

        for ext in EXTENSIONS:
            try:
                await self.load_extension(ext)
                logger.info("Loaded extension: %s", ext)
            except Exception as e:
                logger.error("Failed to load %s: %s", ext, e, exc_info=True)

    async def close(self) -> None:
        """ยกเลิก keep-alive task + ปิด health server ตอนบอทปิด"""
        try:
            await _stop_health_server()
        except Exception as e:
            logger.warning("Health shutdown error: %s", e)
        await super().close()


bot = AiriBot(
    command_prefix=config.COMMAND_PREFIX,
    intents=intents,
    help_command=None,  # ใช้ /airihelp แทน
)


# ==========================================
# Tasks: แจ้งเตือนเวลา + Auto save
# ==========================================
_announced = set()  # กันส่งซ้ำในนาทีเดียว


@tasks.loop(minutes=1)
async def announcement_task():
    """แจ้งเตือนเวลา: อรุณสวัสดิ์ 07:00 / ฝันดี 22:00 / ไล่นอน 23:00, 23:30"""
    channel_id = config.ANNOUNCEMENT_CHANNEL_ID
    if not channel_id:
        return

    from datetime import datetime
    now = config.now()
    minute_key = (now.strftime("%Y-%m-%d"), now.hour, now.minute)
    if minute_key in _announced:
        return

    channel = bot.get_channel(channel_id)
    if channel is None:
        return

    from services.ai_service import ai_service
    from core.brain import PERSONA

    try:
        # 07:00 อรุณสวัสดิ์ + อากาศ
        if now.hour == 7 and now.minute == 0:
            _announced.add(minute_key)
            weather = ""
            try:
                import requests
                r = requests.get("https://wttr.in/Bangkok?format=3&lang=th", timeout=5)
                if r.status_code == 200:
                    weather = r.text.strip()
            except Exception:
                pass
            prompt = f"ตอนนี้เวลา {now.strftime('%H:%M')} ยามเช้า สภาพอากาศ: {weather or 'ไม่ทราบ'} เขียนข้อความอรุณสวัสดิ์พี่ๆ แบบสดใส น่ารักสไตล์ไอริ"
            text = await ai_service.generate(PERSONA, prompt, temperature=0.9)
            await channel.send(text or f"อรุณสวัสดิ์ค่า~ ☀️ {weather}")

        # 22:00 ฝันดี
        elif now.hour == 22 and now.minute == 0:
            _announced.add(minute_key)
            prompt = "ตอนนี้ 4 ทุ่มแล้ว เขียนข้อความบอกฝันดีพี่ๆ แบบน่ารักๆ สไตล์ไอริ"
            text = await ai_service.generate(PERSONA, prompt, temperature=0.9)
            await channel.send(text or "ดึกแล้วน้า~ ฝันดีค่า 💤✨")

        # 23:00 ไล่นอน (เพิ่มงอน +1)
        elif now.hour == 23 and now.minute == 0:
            _announced.add(minute_key)
            await _sleep_nudge(channel, grudge_add=1, gentle=False)

        # 23:30 ไล่นอน (เพิ่มงอน +2)
        elif now.hour == 23 and now.minute == 30:
            _announced.add(minute_key)
            await _sleep_nudge(channel, grudge_add=2, gentle=True)

    except Exception as e:
        logger.error("announcement error: %s", e, exc_info=True)


async def _sleep_nudge(channel, grudge_add: int, gentle: bool):
    """สร้างข้อความไล่นอน + เพิ่มงอนให้สมาชิกออนไลน์"""
    from memory import storage as st
    targets = []
    for member in channel.guild.members:
        if member.bot or member.status == discord.Status.offline:
            continue
        # กรองตามยศถ้ากำหนดไว้
        if config.SLEEP_ROLE_NAMES:
            if not any(
                any(role_name in (r.name or "").lower() for role_name in config.SLEEP_ROLE_NAMES)
                for r in member.roles
            ):
                continue
        targets.append(member)
        # เพิ่มงอน
        conn = st.get_conn()
        row = conn.execute(
            "SELECT grudge FROM user_stats WHERE user_id = ? AND guild_id = ?",
            (member.id, channel.guild.id),
        ).fetchone()
        current = row["grudge"] if row else 0
        new_grudge = min(4, current + grudge_add)
        conn.execute(
            """
            INSERT INTO user_stats (user_id, guild_id, grudge)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, guild_id) DO UPDATE SET grudge = excluded.grudge
            """,
            (member.id, channel.guild.id, new_grudge),
        )
        conn.commit()

    if not targets:
        return

    mentions = " ".join(t.mention for t in targets)
    from services.ai_service import ai_service
    from core.brain import PERSONA
    now_str = config.now().strftime("%H:%M")
    style = "ดุเบาๆ ด้วยความห่วงใย" if gentle else "เป็นห่วงเป็นใยมากๆ"
    prompt = f"ตอนนี้ {now_str} แล้ว เขียนข้อความไล่คนไม่ยอมนอน {mentions} แบบ{style} สไตล์ไอริ (ห้ามพูดเรื่องงอน)"
    try:
        text = await ai_service.generate(PERSONA, prompt, temperature=0.9)
    except Exception:
        text = None
    fallback = f"⏰ {now_str} แล้วนะ! ไปนอนได้แล้วค่า~ 🛌💤" if not gentle else f"⏰ {now_str} ดึกมากแล้ว! ยังไม่นอนอีกเหรอคะ~ 💤"
    await channel.send(f"{mentions}\n{text or fallback}")


# ==========================================
# Events
# ==========================================
async def _ai_warmup():
    """ยิงเรียก AI ครั้งเดียวตอนเปิดบอท เพื่อ warm DNS/TLS ของ Google
    กันข้อความแรกของผู้ใช้ต้องรอค้างจน timeout (ตอบช้า ~60 วิ)
    timeout ต้องมากกว่า TOTAL_REQUEST_BUDGET เพราะมี retry + fallback โมเดล"""
    try:
        await asyncio.wait_for(
            ai_service.chat(
                system_prompt="ping",
                messages=[{"role": "user", "content": "hi"}],
                temperature=0.0,
                max_tokens=8,
            ),
            timeout=TOTAL_REQUEST_BUDGET + 15,
        )
        logger.info("AI warmup OK (โมเดลที่ใช้: %s)", ai_service._model)
    except Exception as e:
        logger.info("AI warmup ข้ามไป (%s: %s)", type(e).__name__, e)


@bot.event
async def on_ready():
    logger.info("Logged in as %s (ID: %s)", bot.user, bot.user.id)

    # Init database
    try:
        storage.init_db()
        logger.info("Database initialized: %s", config.DB_PATH)
    except Exception as e:
        logger.error("DB init failed: %s", e)

    # โหลดค่าห้องที่ล็อก (legacy latest_channel_id) + ห้องตั้งค่าต่างๆ จาก DB
    try:
        saved = storage.get_setting("latest_channel_id")
        if saved is not None:
            config.latest_channel_id = int(saved)
            logger.info("Locked channel restored: %s", config.latest_channel_id)
        saved_wel = storage.get_setting("welcome_channel_id")
        if saved_wel:
            config.WELCOME_CHANNEL_ID = int(saved_wel)
        saved_ann = storage.get_setting("announcement_channel_id")
        if saved_ann:
            config.ANNOUNCEMENT_CHANNEL_ID = int(saved_ann)
    except Exception as e:
        logger.warning("Restore settings failed: %s", e)

    # Sync slash commands (หลังโหลด extensions แล้ว)
    try:
        synced = await bot.tree.sync()
        logger.info("Synced %d slash commands", len(synced))
        for cmd in synced:
            logger.info("  /%s - %s", cmd.name, cmd.description or "")
    except Exception as e:
        logger.warning("Slash sync failed: %s", e)

    if not announcement_task.is_running():
        announcement_task.start()
        logger.info("Announcement task started")

    # แสดงโหมดตอบ
    logger.info("Respond mode: %s | Model: %s", config.RESPOND_MODE, config.MODEL_NAME)
    logger.info("Locked channel: %s", config.latest_channel_id or "(not set - mention only)")
    logger.info("✨ Airi is ready!")

    # Warm-up AI แบบไม่บล็อก (แก้ข้อความแรกตอบช้า)
    asyncio.create_task(_ai_warmup())


@bot.event
async def on_message(message: discord.Message):
    # ตอบข้อความสนทนา (AI)
    await message_handler.handle_message(message, bot)

    # ประมวลผลคำสั่ง prefix ด้วย
    await bot.process_commands(message)


@bot.event
async def on_member_join(member: discord.Member):
    if not config.WELCOME_CHANNEL_ID:
        return
    channel = bot.get_channel(config.WELCOME_CHANNEL_ID)
    if channel is None:
        return
    embed = discord.Embed(
        title="✨ ยินดีต้อนรับสู่เซิร์ฟเวอร์ค่า! 🎉",
        description=f"ยินดีต้อนรับ {member.mention} นะคะ~ ขอให้สนุกน้า! 💕",
        color=0xFFB6C1,
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text=f"สมาชิกลำดับที่ {member.guild.member_count}")
    await channel.send(embed=embed)


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("ไม่มีสิทธิ์ใช้คำสั่งนี้นะคะ 😤")
        return
    if isinstance(error, commands.BadArgument):
        await ctx.send("ข้อมูลที่ใส่ไม่ถูกต้องน้า~ ลองใหม่นะคะ")
        return
    logger.error("Command error: %s", error, exc_info=True)
    try:
        await ctx.send("มีข้อผิดพลาดบางอย่างน้า~ 😢 ลองใหม่อีกทีนะคะ")
    except Exception:
        pass


# ==========================================
# Main
# ==========================================
def main():
    # ตรวจค่าที่จำเป็น
    errors = config.validate()
    if errors:
        print("❌ ไม่สามารถเริ่มบอทได้:")
        for e in errors:
            print(f"   - {e}")
        print("\nตั้งค่า DISCORD_TOKEN / GOOGLE_API_KEY ใน .bashrc (export ...) หรือ .env แล้วรันใหม่นะคะ")
        sys.exit(1)

    # สร้างโฟลเดอร์ data
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)

    print("🌸 เริ่มต้น Airi Discord Bot...")
    print(f"   Mode: {config.RESPOND_MODE} | Model: {config.MODEL_NAME}")
    print(f"   DB: {config.DB_PATH}")

    try:
        bot.run(config.DISCORD_TOKEN, log_handler=None)
    except KeyboardInterrupt:
        print("\nปิดบอทเรียบร้อยแล้วค่า 👋")
    except discord.LoginFailure:
        print("❌ DISCORD_TOKEN ไม่ถูกต้องนะคะ ตรวจสอบ .bashrc หรือ .env อีกทีค่ะ")
        sys.exit(1)
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาด: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
