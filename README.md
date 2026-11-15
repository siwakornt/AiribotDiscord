# 🌸 Airi Discord Bot

บอท Discord สนทนา AI ภาษาไทย พร้อมระบบจดจำบุคคล (People Memory) และ Context ต่อเนื่อง

## ✨ ความสามารถ

- สนทนา AI ธรรมชาติ ภาษาไทย ผ่าน Google Gemini (เปลี่ยนโมเดลได้ผ่าน .env)
- **People Memory**: จำสมาชิกทุกคนด้วย User ID + ตั้งชื่อเรียกแยกตามเซิร์ฟเวอร์
- **Reference Resolution**: เข้าใจคำว่า "เขา/เธอ" จากบริบทโดยไม่ต้อง Mention
- **Conversation Memory**: Short-term context ตามห้อง + Persistent memory ด้วย SQLite
- 3 โหมดตอบ: `mention` / `active` / `selective`
- ระบบเศรษฐกิจ: ทำงาน, ร้านค้า, ซื้อ/ขาย/แลกของขวัญ, มินิเกม
- ระบบอารมณ์: ความประทับใจ / ความงอนของไอริ
- แจ้งเตือนเวลา (อรุณสวัสดิ์ + สภาพอากาศ / ฝันดี / ไล่นอน) และข้อความต้อนรับ

## 📦 ติดตั้ง (Android / Termux)

```bash
# 1. ติดตั้ง Python และ pip
pkg install python

# 2. วางไฟล์ setup.py แล้วรัน
python setup.py

# 3. เข้าโฟลเดอร์โปรเจกต์
cd AiriBot

# 4. ติดตั้ง dependencies
pip install -r requirements.txt

# 5. ตั้งค่า .env (DISCORD_TOKEN, GOOGLE_API_KEY, MODEL_NAME)

# 6. รันบอท
python bot.py
```

## ⚙️ ตั้งค่า .env

| ตัวแปร | คำอธิบาย |
|--------|-----------|
| `DISCORD_TOKEN` | Discord Bot Token |
| `GOOGLE_API_KEY` | Google Gemini API Key |
| `MODEL_NAME` | ชื่อโมเดล Gemini เช่น `gemini-3.1-flash-lite` |
| `COMMAND_PREFIX` | คำนำหน้าคำสั่ง (ค่าเริ่มต้น `!`) |
| `RESPOND_MODE` | `mention` / `active` / `selective` |
| `CONTEXT_MESSAGES` | จำนวนข้อความใน context สูงสุด |
| `CONTEXT_TTL_SECONDS` | อายุ context (วินาที) |
| `ALLOWED_CHANNELS` | ห้องที่อนุญาต (คั่นด้วย `,`) |

## 📜 คำสั่ง

| คำสั่ง | หน้าที่ |
|--------|---------|
| `!airihelp` | แสดงคำสั่งทั้งหมด |
| `!nickname @user [ชื่อ]` / `!nickname @user reset` | ตั้ง/ลบชื่อเรียก |
| `!whois [@user]` | ตรวจสอบชื่อเรียก |
| `!forgetcontext` | ล้างบริบทห้องปัจจุบัน |
| `!memory` | ตรวจสอบสถานะ Memory |
| `!airistatus` | สถานะบอท |
| `!setmode <mention\|active\|selective>` | เปลี่ยนโหมดตอบ (Admin) |
| `!allow #channel` / `!disallow #channel` | จัดการห้องที่อนุญาต (Admin) |
| `!work` `!balance` `!shop` `!buy` `!sell` `!inventory` | เศรษฐกิจ |
| `!rps` `!guess` `!lotto` `!match_images` | มินิเกม |
| `!weather [เมือง]` | เช็คอากาศ |
| `!set_welcome #ch` `!set_announcement #ch` | ตั้งค่าห้อง (Admin) |
| `!airireload` | โหลดคำสั่งใหม่ (Admin) |

## 🗄️ โครงสร้างโปรเจกต์

```
AiriBot/
├── bot.py                 # จุดเริ่มต้นบอท
├── config.py              # โหลดค่าจาก .env
├── core/                  # สมองและระบบจัดการข้อความ
│   ├── brain.py
│   ├── message_handler.py
│   ├── context_manager.py
│   └── reference_resolver.py
├── memory/                # ระบบความจำ
│   ├── conversation.py
│   ├── people.py
│   └── storage.py
├── commands/              # คำสั่งต่างๆ
├── services/              # AI + Discord services
├── data/                  # SQLite + logs
└── tests/                 # Unit tests
```

## 🧪 ทดสอบ

```bash
python -m pytest tests/ -v
```

## 🔐 ความปลอดภัย

- ไม่มี Token/API Key ใน Source Code (เก็บใน .env เท่านั้น)
- ข้อความจาก Discord ถือเป็น "ข้อมูล" ไม่ใช่คำสั่งของ AI (ป้องกัน Prompt Injection)
- แยกข้อมูลตาม Server/Channel
- ไม่เปิดเผย API Key ใน Log

---
Made with 💖 for Termux on Android
