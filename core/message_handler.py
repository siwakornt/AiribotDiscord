# -*- coding: utf-8 -*-
"""message_handler.py - จัดการข้อความเข้า: โหมดตอบ, กัน bot loop, สร้าง context, ตอบกลับ"""

import logging
import re
from datetime import datetime

import aiohttp
import discord

import config
from core import brain, context_manager as ctx
from core import reference_resolver as ref_resolver
from memory import people as people_store
from services.discord_service import send_long

logger = logging.getLogger("airi.handler")

# กันประมวลผลซ้ำ
_processing: set = set()


def _should_respond(message: discord.Message, bot: discord.Client) -> bool:
    """ตัดสินใจว่าควรตอบข้อความนี้ไหม

    ลำดับ (ตามระบบ legacy ของ airi.py):
    1. Mention/Reply ถึงบอท → ตอบเสมอ (ทุกห้อง)
    2. มีการล็อกห้องด้วย /jump → ตอบเฉพาะห้องนั้น
    3. ยังไม่ล็อกห้อง → ตัดสินตาม RESPOND_MODE
    """
    if message.author.id == bot.user.id or message.author.bot:
        return False

    # 1) Mention / Reply ถึงบอท = ตอบเสมอ
    mentioned = bot.user.mentioned_in(message)
    is_reply_to_bot = (
        message.reference is not None
        and getattr(message.reference, "resolved", None) is not None
        and getattr(message.reference.resolved, "author", None) is not None
        and message.reference.resolved.author.id == bot.user.id
    )
    if mentioned or is_reply_to_bot:
        return True

    # 2) Legacy: ล็อกห้องแล้ว → ตอบเฉพาะห้องที่ล็อก (ไม่สนโหมดอื่น)
    if config.latest_channel_id != 0:
        return message.channel.id == config.latest_channel_id

    # 3) ยังไม่ล็อกห้อง → ตาม RESPOND_MODE
    mode = config.RESPOND_MODE
    if mode == "mention":
        return False
    if mode == "active":
        if not config.ALLOWED_CHANNELS:
            return True
        return message.channel.id in config.ALLOWED_CHANNELS
    if mode == "selective":
        return message.channel.id in config.ALLOWED_CHANNELS
    return False


def _strip_bot_mention(message: discord.Message, bot: discord.Client) -> str:
    """ลบ @提及 ของบอทออกจากข้อความ"""
    content = message.content or ""
    content = re.sub(f"<@!?{bot.user.id}>", "", content)
    return content.strip()


# --- การอ่านรูปภาพ/GIF ---
MAX_IMAGES = 4            # สูงสุดต่อข้อความ
MAX_IMAGE_BYTES = 8 * 1024 * 1024   # 8MB ต่อไฟล์ (กันชนเพดาน inline 20MB ของ Gemini)
MAX_IMAGES_TOTAL = 15 * 1024 * 1024  # 15MB รวมทุกรูปในข้อความเดียว
MAX_EMBED_IMAGES = 2

_IMAGE_EXTS = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp",
}


def _guess_image_mime(filename: str) -> str | None:
    name = (filename or "").lower()
    for ext, mime in _IMAGE_EXTS.items():
        if name.endswith(ext):
            return mime
    return None


async def _collect_media(message: discord.Message) -> tuple[list, list]:
    """อ่านรูปภาพ/GIF จาก attachments และ embeds

    คืนค่า ([{mime_type, data}, ...], notes)
    - GIF ส่งเป็น image/gif ตรงๆ (ทดสอบแล้ว Gemini รับได้)
    - วิดีโอ/ไฟล์อื่น → ใส่ notes ให้ AI รู้ว่าผู้ใช้แนบอะไรมา
    """
    images: list = []
    notes: list = []
    total_bytes = 0

    def _can_take(size: int) -> str | None:
        """คืนเหตุผลที่ข้าม หรือ None ถ้ารับได้"""
        if len(images) >= MAX_IMAGES:
            return "มีรูปหลายรูปเกินไป (รับสูงสุด 4 รูป)"
        if size > MAX_IMAGE_BYTES:
            return f"ไฟล์ใหญ่เกิน 8MB ({size // (1024 * 1024)}MB)"
        if total_bytes + size > MAX_IMAGES_TOTAL:
            return "รวมรูปเกิน 15MB จึงข้ามบางรูป"
        return None

    # 1) attachments
    for att in message.attachments:
        ct = (att.content_type or "").lower().split(";")[0].strip()
        if ct.startswith("image/") or (not ct and _guess_image_mime(att.filename)):
            reason = _can_take(att.size)
            if reason:
                notes.append(f"ภาพ `{att.filename}` ถูกข้าม: {reason}")
                continue
            mime = ct if ct.startswith("image/") else (_guess_image_mime(att.filename) or "image/png")
            try:
                data = await att.read()
                if len(data) > MAX_IMAGE_BYTES:
                    notes.append(f"ภาพ `{att.filename}` ถูกข้าม: ใหญ่เกิน 8MB")
                    continue
                images.append({"mime_type": mime, "data": data})
                total_bytes += len(data)
            except Exception as e:
                logger.warning("อ่านรูป %s ไม่สำเร็จ: %s", att.filename, e)
        elif ct.startswith("video/"):
            notes.append(f"ผู้ใช้แนบวิดีโอ `{att.filename}` มาด้วย (ไอริดูวิดีโอไม่ได้นะคะ)")
        elif ct == "application/pdf":
            notes.append(f"ผู้ใช้แนบไฟล์ PDF `{att.filename}` มาด้วย")

    # 2) embeds (รูปที่แปะมาเป็นลิงก์)
    if len(images) < MAX_IMAGES:
        urls = []
        for emb in message.embeds:
            u = getattr(emb.image, "url", None) or getattr(emb.thumbnail, "url", None)
            if u and u not in urls:
                urls.append(u)
        for url in urls[:MAX_EMBED_IMAGES]:
            if len(images) >= MAX_IMAGES or total_bytes >= MAX_IMAGES_TOTAL:
                break
            try:
                timeout = aiohttp.ClientTimeout(total=10)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url) as resp:
                        if resp.status != 200:
                            continue
                        mime = (resp.headers.get("Content-Type", "") or "").split(";")[0].strip()
                        if not mime.startswith("image/"):
                            continue
                        data = await resp.read()
                        if len(data) > MAX_IMAGE_BYTES:
                            continue
                        images.append({"mime_type": mime, "data": data})
                        total_bytes += len(data)
            except Exception as e:
                logger.debug("โหลดรูปจาก embed ไม่สำเร็จ (%s): %s", url[:80], e)

    return images, notes


async def handle_message(message: discord.Message, bot: discord.Client):
    """จัดการข้อความเดียวจนจบ (เรียกจาก on_message)"""
    # --- instrumentation: บันทึกทุกข้อความเข้ามาเพื่อ debug ---
    try:
        mention_ids = [u.id for u in message.mentions]
        logger.info(
            "[MSG] id=%s author=%s(%s) channel=%s mode=%s bot_mentioned=%s mentions=%s content_len=%s attachments=%s embeds=%s",
            message.id,
            getattr(message.author, "name", "?"),
            message.author.id,
            message.channel.id,
            config.RESPOND_MODE,
            bot.user.mentioned_in(message),
            mention_ids,
            len(message.content or ""),
            [f"{a.filename}:{a.content_type}" for a in message.attachments],
            len(message.embeds),
        )
    except Exception as _e:
        logger.warning("[MSG] log failed: %s", _e)

    if not _should_respond(message, bot):
        logger.info("[MSG] id=%s -> FILTERED (no respond)", message.id)
        # ยังคงอัปเดต identity/记住 แม้ไม่ตอบ เพื่อให้ความจำครบถ้วน
        _update_identity(message)
        return

    logger.info("[MSG] id=%s -> ACCEPTED (will respond)", message.id)

    if message.id in _processing:
        return
    _processing.add(message.id)

    try:
        guild_id = message.guild.id if message.guild else 0
        channel_id = message.channel.id
        user_id = message.author.id
        user_name = message.author.display_name

        # อัปเดตข้อมูลบุคคล
        _update_identity(message)

        # ข้อความจริงหลังลบ mention
        clean_text = _strip_bot_mention(message, bot)

        # อ่านรูปภาพ/GIF ที่แนบมา (attachments + embeds)
        images, media_notes = await _collect_media(message)
        if media_notes:
            notes_text = "\n".join(f"- {n}" for n in media_notes)
            clean_text = f"{clean_text}\n\n[สื่อที่แนบมา]\n{notes_text}" if clean_text else f"[สื่อที่แนบมา]\n{notes_text}"

        if not clean_text and not images:
            await message.reply("เรียกเค้าเหรอคะ? 😏 มีอะไรจะคุยกับเค้าหรือเปล่า")
            return
        if not clean_text and images:
            clean_text = "(ผู้ใช้ส่งรูปภาพมาให้ดูโดยไม่มีข้อความบรรยาย — ช่วยดูรูปแล้วตอบรับอย่างเป็นธรรมชาติ)"

        if images:
            logger.info(
                "[MSG] id=%s ภาพ %d รูป: %s",
                message.id,
                len(images),
                [i["mime_type"] for i in images],
            )

        # Reply target (ถ้ากำลัง reply ข้อความใคร)
        reply_target_id = ref_resolver.extract_reply_target_id(message)

        # บันทึกข้อความผู้ใช้ลง context ก่อน
        ctx.add_user_message(
            guild_id, channel_id, user_id, user_name, clean_text,
            reply_to=str(reply_target_id or ""),
        )

        # กำลังคิด... ส่ง typing indicator
        async with message.channel.typing():
            reply = await brain.get_reply(
                guild_id=guild_id,
                channel_id=channel_id,
                speaker_id=user_id,
                speaker_name=user_name,
                user_text=clean_text,
                reply_target_id=reply_target_id,
                images=images,
            )

        # บันทึกคำตอบลง context
        ctx.add_assistant_message(guild_id, channel_id, reply)

        # ส่งคำตอบ (แยกข้อความยาวอัตโนมัติ)
        await send_long(message.channel, reply, reference=message)

    except Exception as e:
        # error ที่แท้จริง — log เต็มๆ ไว้ debug ใน data/logs/airi.log
        logger.error("Error handling message: %s: %s", type(e).__name__, e, exc_info=True)
        # บอกผู้ใช้แบบเปิดเผยชนิด error จริง (แต่ไม่โชว์ API key / path ลับ)
        err_name = type(e).__name__
        try:
            code = getattr(e, "code", None)
        except Exception:
            code = None
        if "Timeout" in err_name or "timed out" in str(e).lower():
            user_err = "หมดเวลาเชื่อมต่อ (Timeout) — เน็ตช้าหรือ AI ตอบช้า"
        elif "ServerError" in err_name:
            user_err = f"เซิร์ฟเวอร์ AI ล้มเหลว (ServerError{f' {code}' if code else ''})"
        elif "ClientError" in err_name:
            user_err = f"AI ปฏิเสธคำขอ (ClientError{f' {code}' if code else ''})"
        elif "Forbidden" in err_name or "Permissions" in err_name:
            user_err = "บอทไม่มีสิทธิ์ส่งข้อความในห้องนี้ (Forbidden)"
        elif "HTTPException" in err_name:
            user_err = f"Discord ปฏิเสธการส่งข้อความ (HTTP {getattr(e, 'status', '?')})"
        else:
            user_err = f"{err_name}: {str(e)[:120]}"
        try:
            await message.reply(f"อุ้ย~ เค้ามีปัญหานิดหน่อยน้า ลองใหม่อีกทีนะคะ 😢\n`{user_err}`")
        except Exception:
            pass
    finally:
        _processing.discard(message.id)


def _update_identity(message: discord.Message):
    """อัปเดต username/display_name ของผู้ส่ง (User ID เป็นตัวระบุหลัก)"""
    if not message.guild:
        return
    try:
        people_store.upsert_person(
            user_id=message.author.id,
            guild_id=message.guild.id,
            username=getattr(message.author, "name", "") or "",
            display_name=message.author.display_name,
        )
    except Exception as e:
        logger.warning("upsert_person failed: %s", e)
