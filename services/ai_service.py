# -*- coding: utf-8 -*-
"""ai_service.py - AI Service (Google Gemini ผ่าน google-genai)
แยกออกจาก Bot Core, มี Timeout, Retry, Rate Limit handling, ไม่เปิดเผย API Key
interface: chat(system_prompt, messages) / generate(system_prompt, user_prompt)
"""

import asyncio
import logging
import time

from google import genai
from google.genai import types as genai_types
from google.genai import errors as genai_errors

import config

logger = logging.getLogger("airi.ai")

# จำกัดความยาว context ที่ส่งไปยัง AI (characters)
MAX_CONTEXT_CHARS = 12000
MAX_RETRIES = 3                 # retry ต่อโมเดล (มี fallback โมเดลช่วยด้วย ไม่ต้อง retry นาน)
UNAVAILABLE_RETRIES = 1         # 503/500/502/504 = โมเดลล่ม → รอแค่ 1 ครั้งแล้วสลโมเดลสำรองเลย
RETRY_BASE_DELAY = 2.0          # วินาที → backoff 2, 4, ... (ไม่เกิน 15)
REQUEST_TIMEOUT = 30.0          # วินาทีต่อครั้ง
TOTAL_REQUEST_BUDGET = 60.0     # เพดานเวลารวมต่อ 1 ข้อความ (กันตอบช้าเกินไป)
FALLBACK_RETRY_SECONDS = 600.0  # ทุก 10 นาที จะลองโมเดลหลักใหม่อีกครั้ง


class AIService:
    def __init__(self):
        self._client: genai.Client | None = None
        self._model = config.MODEL_NAME
        self._fallback_until = 0.0      # เมื่อไรจะกลับไปลองโมเดลหลักใหม่ (monotonic)
        self._last_request_ts = 0.0
        self._min_interval = 0.5  # กันยิงถี่เกินไป (rate limit ฝั่งเรา)

    def _ensure_client(self) -> genai.Client:
        if self._client is None:
            # ไม่ log หรือส่ง API key ออกที่ไหนทั้งสิ้น
            self._client = genai.Client(api_key=config.GOOGLE_API_KEY)
        return self._client

    def _message_parts(self, m: dict) -> list:
        """แปลง content ของข้อความเดียวเป็น Gemini parts

        รองรับ 2 แบบ:
        - str            → [{"text": ...}]
        - list (multimodal) → [{"text": ...}, {"inline_data": {"mime_type","data"}}, ...]
        """
        content = m.get("content", "")
        parts: list = []
        if isinstance(content, list):
            for p in content:
                if not isinstance(p, dict):
                    continue
                if "inline_data" in p:
                    blob = p.get("inline_data") or {}
                    data = blob.get("data")
                    mime = blob.get("mime_type") or "image/png"
                    if data:
                        parts.append(genai_types.Part.from_bytes(data=data, mime_type=mime))
                elif p.get("text"):
                    parts.append({"text": str(p["text"])})
        else:
            text = str(content)
            if text:
                parts.append({"text": text})
        return parts

    def _to_gemini_contents(self, messages: list) -> list:
        """แปลงข้อความสไตล์ OpenAI (role: user/assistant) เป็น Gemini contents (role: user/model)
        content อาจเป็น str หรือ list ของ parts (รูปภาพ/GIF) ก็ได้
        """
        contents = []
        for m in messages:
            role = "model" if m.get("role") == "assistant" else "user"
            parts = self._message_parts(m)
            if not parts:
                continue
            # Gemini ไม่ชอบ role เดียวกันติดกันหลายรอบ → รวมข้อความ
            if contents and contents[-1]["role"] == role:
                contents[-1]["parts"].extend(parts)
            else:
                contents.append({"role": role, "parts": list(parts)})
        return contents

    async def chat(
        self,
        system_prompt: str,
        messages: list,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> str:
        """
        ส่งสนทนาไปยัง Gemini และคืนคำตอบเป็นข้อความ
        messages: [{"role": "user"|"assistant", "content": str}, ...]
        พร้อม Retry + Rate limit + ตัด context ให้ไม่ยาวเกินไป
        """
        client = self._ensure_client()

        # จำกัดความยาว context รวม
        trimmed = self._trim_messages(messages)
        contents = self._to_gemini_contents(trimmed)
        if not contents:
            return "อุ้ย~ เค้าไม่เห็นข้อความเลยน้า~ 😢"

        # min-interval กัน rate limit ฝั่งเรา
        now = time.monotonic()
        wait = self._last_request_ts + self._min_interval - now
        if wait > 0:
            await asyncio.sleep(wait)

        gen_config = genai_types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=temperature,
            max_output_tokens=max_tokens,
        )

        last_err = None
        deadline = time.monotonic() + TOTAL_REQUEST_BUDGET
        chain = self._model_chain()
        stop_chain = False  # rate limit = คนละโควตาไม่ใช่คนละโมเดล → ไม่ต้องสลับโมเดล

        # ลองทีละโมเดล: โมเดลที่ใช้อยู่ → โมเดลหลัก → โมเดลสำรอง (กัน 503 high demand)
        for model in chain:
            for attempt in range(MAX_RETRIES):
                if time.monotonic() > deadline:
                    logger.warning("หมดเวลาตอบ (budget %.0fs) — หยุดลองโมเดล", TOTAL_REQUEST_BUDGET)
                    break
                self._last_request_ts = time.monotonic()
                try:
                    response = await asyncio.wait_for(
                        client.aio.models.generate_content(
                            model=model,
                            contents=contents,
                            config=gen_config,
                        ),
                        timeout=REQUEST_TIMEOUT,
                    )
                    text = getattr(response, "text", None)
                    result = (text or "").strip() or "อุ้ย~ เค้าตอบไม่ได้เลยน้า~ 😢"
                    if model != config.MODEL_NAME:
                        self._use_fallback(model)
                    return result
                except asyncio.TimeoutError as e:
                    last_err = e
                    logger.warning("Gemini timeout [%s] retry (attempt %d/%d)",
                                   model, attempt + 1, MAX_RETRIES)
                except genai_errors.ClientError as e:
                    code = getattr(e, "code", None)
                    # แสดง error จริงจาก Google (code + message) แต่ไม่แตะ API key
                    logger.error("Gemini client error [%s]: code=%s message=%s",
                                 model, code, getattr(e, "message", str(e)))
                    last_err = e
                    if code == 404:
                        break  # โมเดลนี้ไม่มีจริง → ลองโมเดลถัดไป
                    # 4xx อื่น (auth/bad request) เปลี่ยนโมเดลก็ไม่ช่วย
                    return self._error_reply(last_err)
                except genai_errors.ServerError as e:
                    last_err = e
                    srv_code = getattr(e, "code", None)
                    # error ที่แท้จริงจากฝั่ง Google (ไม่ใช่แค่ชื่อ class)
                    logger.warning(
                        "Gemini server error [%s] retry (attempt %d/%d): code=%s message=%s",
                        model, attempt + 1, MAX_RETRIES,
                        srv_code, getattr(e, "message", str(e)),
                    )
                    # rate limit = โควตาของ API key เดียวกัน → สลับโมเดลก็ไม่ช่วย
                    if srv_code == 429:
                        stop_chain = True
                    # โมเดลล่ม (500/502/503/504) → ไม่รอนาน รีบสลับไปโมเดลสำรอง
                    elif isinstance(srv_code, int) and 500 <= srv_code < 600 and attempt >= UNAVAILABLE_RETRIES:
                        break
                except Exception as e:
                    last_err = e
                    logger.warning("Gemini error [%s] retry (attempt %d/%d): %s: %s",
                                   model, attempt + 1, MAX_RETRIES, type(e).__name__, e)

                if attempt < MAX_RETRIES - 1:
                    # backoff แบบ exponential แต่จำกัดไม่ให้รอนานเกิน 15 วิ
                    delay = min(RETRY_BASE_DELAY * (2 ** attempt), 15.0)
                    # 429 rate limit → รอเพิ่มอีก 3 เท่า ไม่งั้นโดนซ้ำ
                    if getattr(last_err, "code", None) == 429:
                        delay = min(delay * 3, 20.0)
                    await asyncio.sleep(delay)

            if stop_chain:
                break

        # ครบทุกโมเดลแล้วยังล้มเหลว — log error จริงเต็มๆ เพื่อ debug
        real_code = getattr(last_err, "code", None)
        real_msg = getattr(last_err, "message", None) or (str(last_err) if last_err else "unknown")
        logger.error(
            "AI request failed after retries models=%s: %s (code=%s) message=%s",
            ",".join(chain), type(last_err).__name__ if last_err else "unknown", real_code, real_msg,
        )
        return self._error_reply(last_err)

    def _model_chain(self) -> list[str]:
        """ลำดับโมเดลที่จะลอง: โมเดลที่ใช้อยู่ → โมเดลหลัก → โมเดลสำรอง"""
        primary = config.MODEL_NAME
        # หมดเวลาใช้โมเดลสำรอง → กลับไปลองโมเดลหลักใหม่
        if self._model != primary and self._fallback_until and time.monotonic() >= self._fallback_until:
            logger.info("หมดเวลาใช้โมเดลสำรอง → กลับไปใช้โมเดลหลัก %s", primary)
            self._model = primary
            self._fallback_until = 0.0
        chain: list[str] = []
        for m in (self._model, primary, *config.FALLBACK_MODELS):
            if m and m not in chain:
                chain.append(m)
        return chain

    def _use_fallback(self, model: str) -> None:
        """จำไว้ว่ากำลังใช้โมเดลสำรอง + ตั้งเวลาเพื่อคอยกลับไปลองโมเดลหลัก"""
        if model != self._model:
            logger.warning(
                "สลับไปใช้โมเดลสำรอง: %s (โมเดลหลัก %s ตอบไม่ได้ชั่วคราว)",
                model, config.MODEL_NAME,
            )
            self._model = model
        if not self._fallback_until:
            self._fallback_until = time.monotonic() + FALLBACK_RETRY_SECONDS

    @staticmethod
    def _error_reply(last_err) -> str:
        """แปลง error จริงเป็นข้อความบอกผู้ใช้ (บอกสาเหตุจริง แต่ไม่เปิด API key)"""
        real_code = getattr(last_err, "code", None)
        real_msg = getattr(last_err, "message", None) or (str(last_err) if last_err else "unknown")
        err_name = type(last_err).__name__ if last_err else "unknown"
        if real_code == 429:
            hint = "ระบบ AI ติด rate limit (429) ชั่วคราว"
        elif isinstance(real_code, int) and 500 <= real_code < 600:
            hint = f"เซิร์ฟเวอร์ Google ล่มชั่วคราว (HTTP {real_code})"
        elif real_code == 400:
            hint = "คำขอถูกปฏิเสธ (400) — อาจเป็นที่รูป/ข้อความ"
        elif real_code in (401, 403):
            hint = f"API key ใช้ไม่ได้ (HTTP {real_code})"
        elif real_code == 404:
            hint = "ไม่พบโมเดล AI (404) — ตรวจค่า MODEL_NAME ใน /sdcard/.env"
        elif "Timeout" in err_name:
            hint = "หมดเวลาเชื่อมต่อ (Timeout) — เน็ตช้าหรือ AI ตอบช้า"
        else:
            hint = f"{err_name}: {str(real_msg)[:80]}"
        return f"ขอโทษน้าา~ เค้าฟังไม่ออกเลยค่ะ 😢 ({hint})"

    @staticmethod
    def _content_chars(m: dict) -> int:
        """นับจำนวนตัวอักษร (เฉพาะส่วนข้อความ — น้ำหนักรูปไม่นับ เพื่อไม่ให้ context ถูกตัดทิ้ง)"""
        content = m.get("content", "")
        if isinstance(content, list):
            return sum(len(str(p.get("text", ""))) for p in content if isinstance(p, dict))
        return len(str(content))

    def _trim_messages(self, messages: list) -> list:
        """ตัดข้อความเก่าออกจนกว่าจะไม่เกิน MAX_CONTEXT_CHARS (เก็บข้อความปัจจุบันไว้เสมอ)"""
        result = list(messages)
        total = sum(self._content_chars(m) for m in result)
        while len(result) > 1 and total > MAX_CONTEXT_CHARS:
            removed = result.pop(0)
            total -= self._content_chars(removed)
        return result

    async def generate(self, system_prompt: str, user_prompt: str, temperature: float = 0.8) -> str:
        """เรียกแบบครั้งเดียว (ไม่ต้องมี history) - ใช้สำหรับข้อความแจ้งเตือน"""
        return await self.chat(
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            temperature=temperature,
        )


# singleton
ai_service = AIService()
