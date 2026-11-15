# -*- coding: utf-8 -*-
"""slash.py - ระบบคำสั่ง Slash (/) ครบทุกตัว
รวมคำสั่ง legacy จาก airi.py + คำสั่งใหม่
Discord จะแสดงลิสคำสั่งให้กดเลือกง่ายๆ ตอนพิมพ์ /
"""

import random
import asyncio
import discord
from discord import app_commands
from discord.ext import commands

import config
from memory import storage, people as people_store
from core import context_manager as ctx
from commands.economy import _get_stats, _save_stats, _log_tx, SHOP_ITEMS
from commands.games import RPSView, GuessViewButtons, MatchView
from services.ai_service import ai_service
from core.brain import PERSONA


def _is_admin(interaction: discord.Interaction) -> bool:
    if interaction.guild is None:
        return False
    return interaction.user.guild_permissions.manage_guild


async def _require_admin(interaction: discord.Interaction) -> bool:
    if _is_admin(interaction):
        return True
    await interaction.response.send_message("คำสั่งนี้สำหรับผู้ดูแลเท่านั้นนะคะ 😤", ephemeral=True)
    return False


class SlashCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ========== 💬 ระบบห้อง / ความจำ (Legacy) ==========

    @app_commands.command(name="jump", description="ตั้งห้องหลักที่ไอริจะตอบ (ล็อกห้อง)")
    @app_commands.describe(channel="เลือกห้องที่จะล็อกให้ไอริตอบ")
    async def jump(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """ย้าย/ล็อกห้องที่ไอริตอบ — Mention ยังตอบได้ทุกห้องเสมอ"""
        config.latest_channel_id = channel.id
        storage.set_setting("latest_channel_id", channel.id)
        await interaction.response.send_message(
            f"ย้ายไปที่ {channel.mention} แล้วน้า~ ไอริจะตอบห้องนี้เป็นหลักเลยค่า ✅\n"
            f"(ยัง Mention หาไอริได้ทุกห้องนะ 😉)",
            ephemeral=True,
        )
        await channel.send("ไอริย้ายมาห้องนี้แล้วน้า~ ถามไอริมาได้เลยค่า~ 🌸")

    @app_commands.command(name="jump_clear", description="ยกเลิกการล็อกห้อง (ให้ตอบตามโหมดปกติ)")
    async def jump_clear(self, interaction: discord.Interaction):
        if not await _require_admin(interaction):
            return
        config.latest_channel_id = 0
        storage.set_setting("latest_channel_id", 0)
        await interaction.response.send_message(
            f"ยกเลิกการล็อกห้องแล้วค่า (ตอนนี้โหมดตอบ: `{config.RESPOND_MODE}`) ✅",
            ephemeral=True,
        )

    @app_commands.command(name="create", description="สร้างห้องคุยใหม่ในเซิร์ฟเวอร์")
    @app_commands.describe(name="ชื่อห้องที่จะสร้าง เช่น chill หรือ project-abc")
    async def create_channel(self, interaction: discord.Interaction, name: str):
        if not await _require_admin(interaction):
            return
        guild = interaction.guild
        existing = discord.utils.get(guild.text_channels, name=name)
        if existing:
            await interaction.response.send_message(f"ห้อง `{name}` มีอยู่แล้วน้า~", ephemeral=True)
            return
        try:
            await guild.create_text_channel(name)
            await interaction.response.send_message(f"สร้างห้อง `{name}` เรียบร้อยแล้วค่า~ ✅", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("ไอริไม่มีสิทธิ์สร้างห้องในที่นี่น้า~", ephemeral=True)

    @app_commands.command(name="reset", description="รีเซ็ต/ลืมบทสนทนาของไอริ")
    async def reset_memory(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id if interaction.guild else 0
        ctx.clear_channel(guild_id, interaction.channel_id)
        conn = storage.get_conn()
        try:
            conn.execute(
                "DELETE FROM conversation_persist WHERE guild_id = ? AND channel_id = ?",
                (guild_id, interaction.channel_id),
            )
            conn.commit()
        except Exception:
            pass
        await interaction.response.send_message("ไอริลืมเรื่องที่คุยกันแล้วน้า~ 🧹", ephemeral=True)

    @app_commands.command(name="forgetcontext", description="ล้างบริบทห้องปัจจุบัน")
    async def forgetcontext(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id if interaction.guild else 0
        ctx.clear_channel(guild_id, interaction.channel_id)
        await interaction.response.send_message("ล้างบริบทห้องนี้เรียบร้อยแล้วค่า~ 🧹", ephemeral=True)

    @app_commands.command(name="memory", description="ตรวจสอบสถานะ Memory ของห้องนี้")
    async def memory(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id if interaction.guild else 0
        stats = ctx.get_stats(guild_id, interaction.channel_id)
        people_count = len(people_store.list_people(guild_id))
        embed = discord.Embed(title="🧠 สถานะ Memory", color=0x9B59B6)
        embed.add_field(name="ห้องนี้", value=f"ข้อความใน context: **{stats['messages']}/{stats['max_messages']}**", inline=False)
        oldest = stats.get("oldest_age_seconds")
        embed.add_field(
            name="ข้อความเก่าสุด",
            value=(f"{int(oldest)} วินาทีที่แล้ว (TTL: {stats['ttl_seconds']}s)" if oldest is not None else "ยังไม่มี"),
            inline=False,
        )
        embed.add_field(name="สมาชิกที่มีข้อมูล", value=f"**{people_count}** คน", inline=False)
        embed.add_field(name="โหมดตอบ", value=f"`{config.RESPOND_MODE}`", inline=True)
        locked = config.latest_channel_id
        embed.add_field(name="ห้องที่ล็อก", value=(f"<#{locked}>" if locked else "ยังไม่ล็อก"), inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="forgetme", description="ให้ไอริลืมเรื่องของคุณ")
    async def forgetme(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("ใช้ได้ในเซิร์ฟเวอร์เท่านั้นนะคะ", ephemeral=True)
            return
        people_store.reset_nickname(interaction.user.id, interaction.guild.id)
        conn = storage.get_conn()
        conn.execute(
            "UPDATE people SET facts = '[]' WHERE user_id = ? AND guild_id = ?",
            (interaction.user.id, interaction.guild.id),
        )
        conn.commit()
        await interaction.response.send_message("ไอริลืมเรื่องของคุณแล้วนะคะ... แต่ยังจำได้ว่าเป็นคนน่ารักอยู่ดี 😉", ephemeral=True)

    # ========== 🏷️ ระบบชื่อเรียก ==========

    @app_commands.command(name="nickname", description="ตั้ง/ดู/ลบชื่อเรียกให้สมาชิก")
    @app_commands.describe(member="สมาชิกที่ต้องการตั้งชื่อเรียก", new_nickname="ชื่อเรียกใหม่ (พิมพ์ reset เพื่อลบ)")
    async def nickname(self, interaction: discord.Interaction, member: discord.Member, new_nickname: str = None):
        if interaction.guild is None:
            await interaction.response.send_message("ใช้ได้ในเซิร์ฟเวอร์เท่านั้นนะคะ", ephemeral=True)
            return
        # ตั้งชื่อเรียกให้คนอื่น ต้องเป็นผู้ดูแล (ป้องกันแก้ชื่อคนอื่นมั่ว)
        if member.id != interaction.user.id and not _is_admin(interaction):
            await interaction.response.send_message("ตั้งชื่อเรียกให้คนอื่นได้เฉพาะผู้ดูแลเท่านั้นนะคะ 😤", ephemeral=True)
            return

        if new_nickname is None:
            current = people_store.get_nickname(member.id, interaction.guild.id)
            await interaction.response.send_message(
                f"ชื่อเรียกของ {member.mention}: **{current}**" if current else f"{member.mention} ยังไม่มีชื่อเรียกพิเศษนะคะ",
                ephemeral=True,
            )
            return

        nick = new_nickname.strip()
        if nick.lower() == "reset":
            people_store.reset_nickname(member.id, interaction.guild.id)
            await interaction.response.send_message(f"ลบชื่อเรียกของ {member.mention} เรียบร้อยแล้วค่ะ ✅", ephemeral=True)
            return
        if len(nick) > 32:
            await interaction.response.send_message("ชื่อเรียกยาวเกินไปนะคะ (สูงสุด 32 ตัวอักษร)", ephemeral=True)
            return
        people_store.set_nickname(member.id, interaction.guild.id, nick)
        await interaction.response.send_message(f"ตั้งชื่อเรียกของ {member.mention} เป็น **{nick}** เรียบร้อยแล้วค่ะ ✨", ephemeral=True)

    @app_commands.command(name="whois", description="ตรวจสอบชื่อเรียกและความจำของสมาชิก")
    @app_commands.describe(member="สมาชิกที่ต้องการตรวจสอบ (เว้นว่าง = ดูของตัวเอง)")
    async def whois(self, interaction: discord.Interaction, member: discord.Member = None):
        if interaction.guild is None:
            await interaction.response.send_message("ใช้ได้ในเซิร์ฟเวอร์เท่านั้นนะคะ", ephemeral=True)
            return
        member = member or interaction.user
        person = people_store.get_person(member.id, interaction.guild.id) or {}
        nickname = person.get("nickname", "")
        facts = person.get("facts", [])
        embed = discord.Embed(title=f"ข้อมูลของ {member.display_name}", color=0x7289DA)
        embed.add_field(name="🆔 User ID", value=str(member.id), inline=False)
        embed.add_field(name="🏷️ ชื่อเรียก", value=nickname if nickname else "(ยังไม่มี)", inline=False)
        if facts:
            embed.add_field(name="🧠 ความจำ", value="\n".join(f"• {f}" for f in facts[:10]), inline=False)
        embed.set_thumbnail(url=member.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="nicknames", description="ดูรายการชื่อเรียกทั้งหมดในเซิร์ฟเวอร์")
    async def nicknames(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("ใช้ได้ในเซิร์ฟเวอร์เท่านั้นนะคะ", ephemeral=True)
            return
        people = [p for p in people_store.list_people(interaction.guild.id) if p.get("nickname")]
        if not people:
            await interaction.response.send_message("ยังไม่มีใครตั้งชื่อเรียกไว้เลยน้า~", ephemeral=True)
            return
        lines = [f"• **{p['nickname']}** — <@{p['user_id']}>" for p in people]
        await interaction.response.send_message("**รายการชื่อเรียก:**\n" + "\n".join(lines))

    # ========== 📜 คำสั่งทั่วไป ==========

    @app_commands.command(name="airihelp", description="แสดงรายการคำสั่งทั้งหมด")
    async def airihelp(self, interaction: discord.Interaction):
        embed = discord.Embed(title="🌸 คำสั่งของไอริ (พิมพ์ / เพื่อดูลิส)", color=0xFFB6C1)
        embed.add_field(
            name="💬 ห้อง & ความจำ",
            value=(
                "`/jump #ห้อง` — ล็อกห้องให้ไอริตอบ\n"
                "`/jump_clear` — ยกเลิกการล็อกห้อง\n"
                "`/create` `/reset` `/forgetcontext` `/memory` `/forgetme`\n"
                "`/nickname @user [ชื่อ]` `/whois` `/nicknames`"
            ),
            inline=False,
        )
        embed.add_field(
            name="⚙️ ระบบ (Admin)",
            value=(
                "`/airistatus` `/setmode` `/allow` `/disallow`\n"
                "`/set_welcome #ch` `/set_announcement #ch` `/airireload`"
            ),
            inline=False,
        )
        embed.add_field(
            name="💰 เศรษฐกิจ & 🎮 เกม",
            value=(
                "`/work` `/balance` `/shop` `/buy` `/sell` `/inventory` `/history`\n"
                "`/send_gift` `/trade` `/profile`\n"
                "`/rps` `/guess` `/lotto` `/match_images` `/weather`"
            ),
            inline=False,
        )
        embed.set_footer(text="Mention หาไอริได้ทุกห้อง หรืออยู่ในห้องที่ล็อกไว้ก็คุยได้เลย 😉")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="airistatus", description="ตรวจสอบสถานะบอท")
    async def airistatus(self, interaction: discord.Interaction):
        import time
        from datetime import datetime
        latency = round(self.bot.latency * 1000)
        embed = discord.Embed(title="📊 สถานะไอริ", color=0x00FFCC)
        embed.add_field(name="📶 Ping", value=f"`{latency} ms`", inline=True)
        embed.add_field(name="🤖 โหมดตอบ", value=f"`{config.RESPOND_MODE}`", inline=True)
        embed.add_field(name="🧠 โมเดล", value=f"`{config.MODEL_NAME}`", inline=True)
        embed.add_field(name="🔒 ห้องที่ล็อก", value=(f"<#{config.latest_channel_id}>" if config.latest_channel_id else "ยังไม่ล็อก"), inline=True)
        embed.add_field(name="🏠 เซิร์ฟเวอร์", value=f"`{len(self.bot.guilds)}`", inline=True)
        embed.set_footer(text="ทำงานบน Termux/Android ปกติค่า ⚡")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="setmode", description="เปลี่ยนโหมดตอบ (Admin)")
    @app_commands.describe(mode="โหมดตอบ: mention = เมื่อถูก Mention, active = ทุกข้อความในห้องที่อนุญาต, selective = เฉพาะห้องที่อนุญาต")
    @app_commands.choices(mode=[
        app_commands.Choice(name="mention (ค่าเริ่มต้น)", value="mention"),
        app_commands.Choice(name="active", value="active"),
        app_commands.Choice(name="selective", value="selective"),
    ])
    async def setmode(self, interaction: discord.Interaction, mode: app_commands.Choice[str]):
        if not await _require_admin(interaction):
            return
        config.RESPOND_MODE = mode.value
        await interaction.response.send_message(f"เปลี่ยนโหมดตอบเป็น **{mode.value}** แล้วค่า ✅", ephemeral=True)

    @app_commands.command(name="allow", description="เพิ่มห้องที่อนุญาตให้ไอริตอบ (Admin)")
    @app_commands.describe(channel="ห้องที่จะเพิ่ม (เว้นว่าง = ห้องปัจจุบัน)")
    async def allow(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        if not await _require_admin(interaction):
            return
        channel = channel or interaction.channel
        if channel.id not in config.ALLOWED_CHANNELS:
            config.ALLOWED_CHANNELS.append(channel.id)
        await interaction.response.send_message(f"เพิ่ม {channel.mention} แล้วค่า ✅", ephemeral=True)

    @app_commands.command(name="disallow", description="ลบห้องออกจากรายการที่อนุญาต (Admin)")
    @app_commands.describe(channel="ห้องที่จะลบ (เว้นว่าง = ห้องปัจจุบัน)")
    async def disallow(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        if not await _require_admin(interaction):
            return
        channel = channel or interaction.channel
        if channel.id in config.ALLOWED_CHANNELS:
            config.ALLOWED_CHANNELS.remove(channel.id)
        await interaction.response.send_message(
            f"ลบ {channel.mention} แล้วค่า ✅ (รายการ: {config.ALLOWED_CHANNELS or 'ว่าง'})",
            ephemeral=True,
        )

    @app_commands.command(name="set_welcome", description="ตั้งห้องต้อนรับสมาชิกใหม่ (Admin)")
    @app_commands.describe(channel="ห้องที่จะส่งข้อความต้อนรับ")
    async def set_welcome(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not await _require_admin(interaction):
            return
        config.WELCOME_CHANNEL_ID = channel.id
        storage.set_setting("welcome_channel_id", channel.id)
        await interaction.response.send_message(f"ตั้งห้องต้อนรับเป็น {channel.mention} เรียบร้อยแล้วค่า ✨", ephemeral=True)

    @app_commands.command(name="set_announcement", description="ตั้งห้องแจ้งเตือนเวลา (Admin)")
    @app_commands.describe(channel="ห้องที่จะส่งข้อความแจ้งเตือนเวลา")
    async def set_announcement(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not await _require_admin(interaction):
            return
        config.ANNOUNCEMENT_CHANNEL_ID = channel.id
        storage.set_setting("announcement_channel_id", channel.id)
        await interaction.response.send_message(
            f"ตั้งห้องแจ้งเตือนเวลา (อรุณสวัสดิ์/ฝันดี/ไล่นอน) เป็น {channel.mention} เรียบร้อยแล้วค่า ⏰",
            ephemeral=True,
        )

    @app_commands.command(name="p", description="ให้ไอริพูดข้อความแทน")
    @app_commands.describe(text="ข้อความที่ให้ไอริพูด")
    async def say(self, interaction: discord.Interaction, text: str):
        if not await _require_admin(interaction):
            return
        await interaction.response.send_message(text)

    # ========== 💰 เศรษฐกิจ ==========

    @app_commands.command(name="work", description="ทำงานแลกเงิน 💼")
    async def work(self, interaction: discord.Interaction):
        jobs = [
            ("ขายขนมครก", 10, 25), ("ล้างจานในร้านอาหาร", 15, 30),
            ("วาดรูปขาย", 20, 35), ("ช่วยคุณยายถือของ", 5, 15),
            ("สตรีมเกม", 10, 50), ("แจกใบปลิว", 5, 20),
            ("ร้องเพลงข้างถนน", 8, 40), ("เลี้ยงเด็กแสบ", 15, 35),
        ]
        job, lo, hi = random.choice(jobs)
        pay = random.randint(lo, hi)
        guild_id = interaction.guild.id if interaction.guild else 0
        stats = _get_stats(interaction.user.id, guild_id)
        stats["money"] += pay
        _save_stats(interaction.user.id, guild_id, stats)
        await interaction.response.send_message(f"ไปทำงานเป็น **{job}** แล้วได้เงินมา **{pay} บาท** น้า~ 💵")

    @app_commands.command(name="balance", description="ดูจำนวนเงินที่มีอยู่ 💰")
    async def balance(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id if interaction.guild else 0
        stats = _get_stats(interaction.user.id, guild_id)
        await interaction.response.send_message(f"พี่มีเงินอยู่ **{stats['money']} บาท** แล้วน้า~ 💖")

    @app_commands.command(name="shop", description="ดูรายการสินค้าในร้านค้า 🛍️")
    async def shop(self, interaction: discord.Interaction):
        embed = discord.Embed(title="🛍️ ร้านค้าของไอริ", description="ซื้อด้วย `/buy` ค่า", color=0xFFB6C1)
        for name, item in SHOP_ITEMS.items():
            embed.add_field(name=f"🎁 {name} — {item['price']} บาท", value=f"*{item['desc']}*", inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="buy", description="ซื้อไอเทมจากร้านค้า 🛒")
    @app_commands.describe(item_name="ชื่อไอเทม เช่น ดอกไม้, ขนม, เค้ก", amount="จำนวนที่ต้องการซื้อ")
    async def buy(self, interaction: discord.Interaction, item_name: str, amount: int = 1):
        if amount <= 0:
            await interaction.response.send_message("จำนวนต้องมากกว่า 0 น้า~", ephemeral=True)
            return
        matched = next((k for k in SHOP_ITEMS if k.lower() == item_name.lower() or item_name.lower() in k.lower()), None)
        if matched is None:
            await interaction.response.send_message(f"ไม่มีไอเทม `{item_name}` ในร้านค้าน้า~ พิมพ์ `/shop` ดูสินค้าได้เลยค่า", ephemeral=True)
            return
        price = SHOP_ITEMS[matched]["price"] * amount
        guild_id = interaction.guild.id if interaction.guild else 0
        stats = _get_stats(interaction.user.id, guild_id)
        if stats["money"] < price:
            await interaction.response.send_message(f"เงินไม่พอค่า~ ต้องใช้ {price} บาท แต่มีแค่ {stats['money']} บาทน้า 😢", ephemeral=True)
            return
        stats["money"] -= price
        stats["inventory"][matched] = stats["inventory"].get(matched, 0) + amount
        _save_stats(interaction.user.id, guild_id, stats)
        _log_tx(interaction.user.id, guild_id, interaction.user.display_name, "BUY", matched, amount, price)
        await interaction.response.send_message(f"🎉 ซื้อ **{matched}** x{amount} เรียบร้อย (จ่าย {price} บาท) 🛍️")

    @app_commands.command(name="sell", description="ขายไอเทมคืนร้านค้า (ได้เงินคืน 70%) 💰")
    @app_commands.describe(item_name="ชื่อไอเทมที่ต้องการขาย", amount="จำนวนที่ต้องการขาย")
    async def sell(self, interaction: discord.Interaction, item_name: str, amount: int = 1):
        if amount <= 0:
            await interaction.response.send_message("จำนวนต้องมากกว่า 0 น้า~", ephemeral=True)
            return
        matched = next((k for k in SHOP_ITEMS if k.lower() == item_name.lower() or item_name.lower() in k.lower()), None)
        if matched is None:
            await interaction.response.send_message(f"ไม่มีไอเทม `{item_name}` ค่า~", ephemeral=True)
            return
        guild_id = interaction.guild.id if interaction.guild else 0
        stats = _get_stats(interaction.user.id, guild_id)
        has = stats["inventory"].get(matched, 0)
        if has < amount:
            await interaction.response.send_message(f"พี่มี `{matched}` แค่ {has} ชิ้นเอง ขายไม่ได้ค่า~", ephemeral=True)
            return
        refund = int(SHOP_ITEMS[matched]["price"] * 0.7) * amount
        stats["inventory"][matched] = has - amount
        stats["money"] += refund
        _save_stats(interaction.user.id, guild_id, stats)
        _log_tx(interaction.user.id, guild_id, interaction.user.display_name, "SELL", matched, amount, refund)
        await interaction.response.send_message(f"💵 ขาย **{matched}** x{amount} ได้เงินคืน **{refund} บาท** เรียบร้อย~")

    @app_commands.command(name="inventory", description="ดูไอเทมในกระเป๋าของคุณ 🎒")
    async def inventory(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id if interaction.guild else 0
        stats = _get_stats(interaction.user.id, guild_id)
        items = [f"🎁 **{k}**: {v} ชิ้น" for k, v in stats["inventory"].items() if v > 0]
        embed = discord.Embed(title=f"🎒 กระเป๋าของ {interaction.user.display_name}", color=0x98FB98)
        embed.description = "\n".join(items) if items else "กระเป๋าว่างเปล่าเลยน้า~ ลอง `/shop` ดูสิคะ!"
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="history", description="ดูประวัติการซื้อขายล่าสุด 📜")
    async def history(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id if interaction.guild else 0
        conn = storage.get_conn()
        rows = conn.execute(
            "SELECT * FROM transactions WHERE guild_id = ? ORDER BY id DESC LIMIT 10",
            (guild_id,),
        ).fetchall()
        if not rows:
            await interaction.response.send_message("ยังไม่มีประวัติการทำธุรกรรมเลยน้า~", ephemeral=True)
            return
        embed = discord.Embed(title="📜 ประวัติธุรกรรมล่าสุด", color=0xFFD700)
        for r in rows:
            act = r["action"]
            if act == "BUY":
                text = f"🛒 **{r['user_name']}** ซื้อ `{r['item']}` x{r['amount']} ({r['total_price']} บาท)"
            elif act == "SELL":
                text = f"💵 **{r['user_name']}** ขาย `{r['item']}` x{r['amount']} (ได้ {r['total_price']} บาท)"
            elif act == "GIFT":
                text = f"🎁 **{r['user_name']}** ส่ง `{r['item']}` ให้ไอริ"
            elif act == "TRADE":
                text = f"🤝 **{r['user_name']}** มอบ `{r['item']}` x{r['amount']} ให้ {r['target_name'] or 'เพื่อน'}"
            else:
                text = f"{act}: {r['item']} x{r['amount']}"
            embed.add_field(name=f"🕒 {r['timestamp']}", value=text, inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="send_gift", description="ส่งของขวัญเพื่อลดความงอน/เพิ่มความประทับใจ 🎁")
    @app_commands.describe(gift="เลือกของขวัญ เช่น ดอกไม้, ขนม, เค้ก, ตุ๊กตาหมี, แหวนหมั้น")
    async def send_gift(self, interaction: discord.Interaction, gift: str):
        matched = next((k for k in SHOP_ITEMS if k.lower() == gift.lower() or gift.lower() in k.lower()), None)
        if matched is None:
            await interaction.response.send_message(f"ไม่มีของขวัญชื่อ `{gift}` นะคะ~ ดูของได้ที่ `/shop`", ephemeral=True)
            return
        guild_id = interaction.guild.id if interaction.guild else 0
        stats = _get_stats(interaction.user.id, guild_id)
        if stats["inventory"].get(matched, 0) > 0:
            stats["inventory"][matched] -= 1
            price = 0
        else:
            price = SHOP_ITEMS[matched]["price"]
            if stats["money"] < price:
                await interaction.response.send_message("เงินไม่พอและไม่มีไอเทมในกระเป๋า~ ลอง `/work` ก่อนนะคะ 💼", ephemeral=True)
                return
            stats["money"] -= price
        info = SHOP_ITEMS[matched]
        if info["type"] == "gift_impression":
            stats["impression"] = min(100, stats["impression"] + info["val"])
            msg = f"ไอริได้รับ **{matched}** จากพี่แล้วน้า~ ชอบมากๆ เลยค่า~! 💖 (ประทับใจ +{info['val']})"
        else:
            stats["grudge"] = max(0, stats["grudge"] - info["val"])
            msg = f"ไอริได้รับ **{matched}** จากพี่แล้วน้า~ ขอบคุณมากเลยค่ะ~ (งอน -{info['val']})"
        _save_stats(interaction.user.id, guild_id, stats)
        _log_tx(interaction.user.id, guild_id, interaction.user.display_name, "GIFT", matched, 1, price)
        await interaction.response.send_message(msg)

    @app_commands.command(name="trade", description="มอบไอเทมให้เพื่อนในเซิร์ฟเวอร์ 🤝")
    @app_commands.describe(target="เพื่อนที่จะมอบไอเทมให้", item_name="ชื่อไอเทม", amount="จำนวน")
    async def trade(self, interaction: discord.Interaction, target: discord.Member, item_name: str, amount: int = 1):
        if target.bot or target.id == interaction.user.id or amount <= 0:
            await interaction.response.send_message("ระบุเป้าหมายหรือจำนวนไม่ถูกต้องน้า~", ephemeral=True)
            return
        matched = next((k for k in SHOP_ITEMS if k.lower() == item_name.lower() or item_name.lower() in k.lower()), None)
        if matched is None:
            await interaction.response.send_message(f"ไม่มีไอเทม `{item_name}` ค่า~", ephemeral=True)
            return
        guild_id = interaction.guild.id if interaction.guild else 0
        stats = _get_stats(interaction.user.id, guild_id)
        if stats["inventory"].get(matched, 0) < amount:
            await interaction.response.send_message(f"พี่ไม่มี `{matched}` พอจะมอบให้เพื่อนนะค้า~", ephemeral=True)
            return
        stats["inventory"][matched] -= amount
        _save_stats(interaction.user.id, guild_id, stats)
        tstats = _get_stats(target.id, guild_id)
        tstats["inventory"][matched] = tstats["inventory"].get(matched, 0) + amount
        _save_stats(target.id, guild_id, tstats)
        _log_tx(interaction.user.id, guild_id, interaction.user.display_name, "TRADE", matched, amount, 0, target_name=target.display_name)
        await interaction.response.send_message(
            f"🤝 **{interaction.user.display_name}** ได้มอบ **{matched}** x{amount} ให้กับ **{target.display_name}** เรียบร้อยแล้วค่า~"
        )

    @app_commands.command(name="profile", description="ดูโปรไฟล์ของคุณ 📝")
    @app_commands.describe(member="สมาชิกที่ต้องการดู (เว้นว่าง = ดูของตัวเอง)")
    async def profile(self, interaction: discord.Interaction, member: discord.Member = None):
        member = member or interaction.user
        guild_id = interaction.guild.id if interaction.guild else 0
        stats = _get_stats(member.id, guild_id)
        person = people_store.get_person(member.id, guild_id) or {}
        facts = person.get("facts", [])
        embed = discord.Embed(title=f"โปรไฟล์ของ {member.display_name}", color=0xADD8E6)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="💰 เงิน", value=f"{stats['money']} บาท", inline=True)
        embed.add_field(name="💗 ประทับใจ", value=f"{stats['impression']} / 100", inline=True)
        embed.add_field(name="😠 งอน", value=f"{stats['grudge']} / 4", inline=True)
        embed.add_field(name="🧠 ที่ไอริจำได้", value=("\n".join(f"• {f}" for f in facts) if facts else "ยังไม่มีบันทึก"), inline=False)
        inv = stats["inventory"]
        embed.add_field(
            name="🎒 ไอเทม",
            value=("\n".join(f"• {k}: {v}" for k, v in inv.items() if v > 0) or "ไม่มีไอเทม"),
            inline=False,
        )
        await interaction.response.send_message(embed=embed)

    # ========== 🎮 เกม ==========

    @app_commands.command(name="rps", description="เป่ายิ้งฉุบกับไอริ ✊🖐️✌️")
    async def rps(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id if interaction.guild else 0
        view = RPSView(user_id=interaction.user.id, guild_id=guild_id)
        await interaction.response.send_message("เป่ายิ้งฉุบกัน! เลือกมาเลยค่า~", view=view)

    @app_commands.command(name="guess", description="เกมทายเลข 1-10 🎯")
    async def guess(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id if interaction.guild else 0
        view = GuessViewButtons(correct=random.randint(1, 10), user_id=interaction.user.id, guild_id=guild_id)
        await interaction.response.send_message("ทายเลข 1-10 มาเลยค่า~", view=view)

    @app_commands.command(name="lotto", description="ซื้อลอตเตอรี่ลุ้นรางวัล 🎰")
    async def lotto(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id if interaction.guild else 0
        stats = _get_stats(interaction.user.id, guild_id)
        if stats["money"] < 10:
            await interaction.response.send_message("พี่มีเงินไม่พอซื้อลอตเตอรี่เลยน้า~ 😢 (ลอง `/work` ก่อนนะ)", ephemeral=True)
            return
        stats["money"] -= 10
        win = random.randint(0, 99)
        mine = random.randint(0, 99)
        result = f"เลขที่ออก: **{win:02d}**\nเลขของพี่: **{mine:02d}**\n"
        if mine == win:
            stats["money"] += 100
            result += "🎉 ถูกรางวัลใหญ่เลย! รับไปเลย 100 บาทค่า~"
        elif mine % 10 == win % 10 or mine // 10 == win // 10:
            stats["money"] += 20
            result += "✨ ถูกรางวัลเลขหลักเดียว~ รับไป 20 บาทค่า~"
        else:
            result += "😭 ไม่ถูกเลย ไว้ลองใหม่น้า~"
        _save_stats(interaction.user.id, guild_id, stats)
        await interaction.response.send_message(result)

    @app_commands.command(name="match_images", description="จับคู่ผลไม้ที่เหมือนกัน 🍎🍌🍒")
    async def match_images(self, interaction: discord.Interaction):
        images = ["🍎", "🍌", "🍒", "🍎", "🍌", "🍒"]
        random.shuffle(images)
        guild_id = interaction.guild.id if interaction.guild else 0
        view = MatchView(images=images, user_id=interaction.user.id, guild_id=guild_id)
        await interaction.response.send_message("จับคู่ผลไม้ที่เหมือนกันให้ได้นะ~", view=view)

    @app_commands.command(name="weather", description="เช็คสภาพอากาศ 🌤️")
    @app_commands.describe(location="ชื่อเมือง (ค่าเริ่มต้น Bangkok)")
    async def weather(self, interaction: discord.Interaction, location: str = "Bangkok"):
        await interaction.response.defer()
        import requests
        try:
            url = f"https://wttr.in/{location.replace(' ', '+')}?format=3&lang=th"
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                await interaction.followup.send(f"🌤️ `{r.text.strip()}`")
            else:
                await interaction.followup.send("ไอริหาข้อมูลอากาศไม่เจอเลยน้า~ 😢")
        except Exception:
            await interaction.followup.send("ไอริเช็คอากาศไม่ได้ตอนนี้ค่า~ 🌧️")


async def setup(bot: commands.Bot):
    await bot.add_cog(SlashCommands(bot))
