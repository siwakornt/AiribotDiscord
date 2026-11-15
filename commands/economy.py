# -*- coding: utf-8 -*-
"""economy.py - ระบบเศรษฐกิจ: work, balance, shop, buy, sell, inventory, history, send_gift, trade, profile"""

import json
import random
import discord
from discord.ext import commands

from memory import storage

SHOP_ITEMS = {
    "ดอกไม้": {"price": 10, "desc": "ดอกไม้สดสวยงาม (ลดงอน 1)", "type": "gift", "val": 1},
    "ขนม": {"price": 20, "desc": "ขนมหวานแสนอร่อย (ลดงอน 2)", "type": "gift", "val": 2},
    "ช็อคโกแลต": {"price": 30, "desc": "ช็อคโกแลตเข้มข้น (ลดงอน 3)", "type": "gift", "val": 3},
    "การ์ด": {"price": 5, "desc": "การ์ดน่ารักๆ (ลดงอน 1)", "type": "gift", "val": 1},
    "เค้ก": {"price": 50, "desc": "เค้กปอนด์ใหญ่ (เพิ่มประทับใจ +5)", "type": "gift_impression", "val": 5},
    "ตุ๊กตาหมี": {"price": 100, "desc": "ตุ๊กตาหมีนุ่มฟู (เพิ่มประทับใจ +10)", "type": "gift_impression", "val": 10},
    "แหวนหมั้น": {"price": 500, "desc": "แหวนสุดหรู (เพิ่มประทับใจ +30)", "type": "gift_impression", "val": 30},
}


def _get_stats(user_id: int, guild_id: int) -> dict:
    conn = storage.get_conn()
    row = conn.execute(
        "SELECT * FROM user_stats WHERE user_id = ? AND guild_id = ?",
        (user_id, guild_id),
    ).fetchone()
    if row:
        d = dict(row)
        try:
            d["inventory"] = json.loads(d.get("inventory") or "{}")
        except Exception:
            d["inventory"] = {}
        return d
    return {"money": 0, "impression": 0, "grudge": 0, "inventory": {}}


def _save_stats(user_id: int, guild_id: int, stats: dict):
    conn = storage.get_conn()
    conn.execute(
        """
        INSERT INTO user_stats (user_id, guild_id, money, impression, grudge, inventory)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, guild_id) DO UPDATE SET
            money = excluded.money,
            impression = excluded.impression,
            grudge = excluded.grudge,
            inventory = excluded.inventory
        """,
        (user_id, guild_id, stats["money"], stats["impression"], stats["grudge"],
         json.dumps(stats["inventory"], ensure_ascii=False)),
    )
    conn.commit()


def _log_tx(user_id: int, guild_id: int, user_name: str, action: str, item: str, amount: int, total_price: int, target_name: str = None):
    conn = storage.get_conn()
    conn.execute(
        """
        INSERT INTO transactions (user_id, guild_id, user_name, action, item, amount, total_price, target_name)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, guild_id, user_name, action, item, amount, total_price, target_name),
    )
    conn.commit()


class Economy(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="work")
    async def work(self, ctx: commands.Context):
        """ทำงานแลกเงิน 💼"""
        jobs = [
            ("ขายขนมครก", 10, 25), ("ล้างจานในร้านอาหาร", 15, 30),
            ("วาดรูปขาย", 20, 35), ("ช่วยคุณยายถือของ", 5, 15),
            ("สตรีมเกม", 10, 50), ("แจกใบปลิว", 5, 20),
            ("ร้องเพลงข้างถนน", 8, 40), ("เลี้ยงเด็กแสบ", 15, 35),
        ]
        job, lo, hi = random.choice(jobs)
        pay = random.randint(lo, hi)
        stats = _get_stats(ctx.author.id, ctx.guild.id)
        stats["money"] += pay
        _save_stats(ctx.author.id, ctx.guild.id, stats)
        await ctx.send(f"ไปทำงานเป็น **{job}** แล้วได้เงินมา **{pay} บาท** น้า~ 💵 ขยันสุดๆ ไปเลย~!")

    @commands.command(name="balance")
    async def balance(self, ctx: commands.Context):
        """ดูเงินที่มี 💰"""
        stats = _get_stats(ctx.author.id, ctx.guild.id)
        await ctx.send(f"คุณมีเงินอยู่ **{stats['money']} บาท** แล้วน้า~ 💖")

    @commands.command(name="shop")
    async def shop(self, ctx: commands.Context):
        """ดูสินค้าในร้าน 🛍️"""
        embed = discord.Embed(title="🛍️ ร้านค้าของไอริ", description="ซื้อด้วย `!buy <ชื่อ> [จำนวน]`", color=0xFFB6C1)
        for name, item in SHOP_ITEMS.items():
            embed.add_field(name=f"🎁 {name} — {item['price']} บาท", value=f"*{item['desc']}*", inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="buy")
    async def buy(self, ctx: commands.Context, item_name: str = None, amount: int = 1):
        """ซื้อไอเทม: !buy ดอกไม้ 2"""
        if item_name is None:
            await ctx.send("ระบุชื่อไอเทมด้วยนะคะ เช่น `!buy ดอกไม้`")
            return
        if amount <= 0:
            await ctx.send("จำนวนต้องมากกว่า 0 น้า~")
            return
        # ค้นหาชื่อไอเทม (case-insensitive + ตรงบางส่วน)
        matched = None
        for k in SHOP_ITEMS:
            if k.lower() == item_name.lower() or item_name.lower() in k.lower():
                matched = k
                break
        if matched is None:
            await ctx.send(f"ไม่มีไอเทม `{item_name}` ในร้านนะคะ พิมพ์ `!shop` ดูสินค้าได้เลยค่า")
            return
        price = SHOP_ITEMS[matched]["price"] * amount
        stats = _get_stats(ctx.author.id, ctx.guild.id)
        if stats["money"] < price:
            await ctx.send(f"เงินไม่พอค่า~ ต้องใช้ {price} บาท แต่มีแค่ {stats['money']} บาทน้า 😢")
            return
        stats["money"] -= price
        inv = stats["inventory"]
        inv[matched] = inv.get(matched, 0) + amount
        stats["inventory"] = inv
        _save_stats(ctx.author.id, ctx.guild.id, stats)
        _log_tx(ctx.author.id, ctx.guild.id, ctx.author.display_name, "BUY", matched, amount, price)
        await ctx.send(f"ซื้อ **{matched}** x{amount} เรียบร้อย (จ่าย {price} บาท) 🎉")

    @commands.command(name="sell")
    async def sell(self, ctx: commands.Context, item_name: str = None, amount: int = 1):
        """ขายไอเทมคืน (70%): !sell ดอกไม้ 1"""
        if item_name is None:
            await ctx.send("ระบุชื่อไอเทมที่จะขายด้วยนะคะ")
            return
        if amount <= 0:
            await ctx.send("จำนวนต้องมากกว่า 0 น้า~")
            return
        matched = None
        for k in SHOP_ITEMS:
            if k.lower() == item_name.lower() or item_name.lower() in k.lower():
                matched = k
                break
        if matched is None:
            await ctx.send(f"ไม่มีไอเทม `{item_name}` ขายคืนไม่ได้น้า~")
            return
        stats = _get_stats(ctx.author.id, ctx.guild.id)
        has = stats["inventory"].get(matched, 0)
        if has < amount:
            await ctx.send(f"มี `{matched}` แค่ {has} ชิ้นเอง ขายไม่ได้ค่า~")
            return
        refund = int(SHOP_ITEMS[matched]["price"] * 0.7) * amount
        stats["inventory"][matched] = has - amount
        stats["money"] += refund
        _save_stats(ctx.author.id, ctx.guild.id, stats)
        _log_tx(ctx.author.id, ctx.guild.id, ctx.author.display_name, "SELL", matched, amount, refund)
        await ctx.send(f"ขาย **{matched}** x{amount} ได้เงินคืน **{refund} บาท** เรียบร้อย~ 💵")

    @commands.command(name="inventory")
    async def inventory(self, ctx: commands.Context):
        """ดูไอเทมในกระเป๋า 🎒"""
        stats = _get_stats(ctx.author.id, ctx.guild.id)
        inv = stats["inventory"]
        items = [f"🎁 **{k}**: {v} ชิ้น" for k, v in inv.items() if v > 0]
        embed = discord.Embed(title=f"🎒 กระเป๋าของ {ctx.author.display_name}", color=0x98FB98)
        embed.description = "\n".join(items) if items else "กระเป๋าว่างเปล่าเลย~ ลอง `!shop` ดูสิคะ!"
        await ctx.send(embed=embed)

    @commands.command(name="history")
    async def history(self, ctx: commands.Context):
        """ดูประวัติธุรกรรมล่าสุด 📜"""
        conn = storage.get_conn()
        rows = conn.execute(
            "SELECT * FROM transactions WHERE guild_id = ? ORDER BY id DESC LIMIT 10",
            (ctx.guild.id,),
        ).fetchall()
        if not rows:
            await ctx.send("ยังไม่มีประวัติการทำธุรกรรมเลยน้า~")
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
        await ctx.send(embed=embed)

    @commands.command(name="send_gift")
    async def send_gift(self, ctx: commands.Context, gift: str = None):
        """ส่งของขวัญให้ไอริ 🎁 (ลดงอน/เพิ่มประทับใจ)"""
        if gift is None:
            await ctx.send("ระบุของขวัญด้วยนะคะ เช่น `!send_gift ดอกไม้` (ดูของที่ `!shop`)")
            return
        matched = None
        for k in SHOP_ITEMS:
            if k.lower() == gift.lower() or gift.lower() in k.lower():
                matched = k
                break
        if matched is None:
            await ctx.send(f"ไม่มีของขวัญชื่อ `{gift}` นะคะ~")
            return
        stats = _get_stats(ctx.author.id, ctx.guild.id)
        if stats["inventory"].get(matched, 0) > 0:
            stats["inventory"][matched] -= 1
            price = 0
        else:
            price = SHOP_ITEMS[matched]["price"]
            if stats["money"] < price:
                await ctx.send("เงินไม่พอและไม่มีไอเทมในกระเป๋าด้วย~ ลอง `!work` ก่อนนะคะ 💼")
                return
            stats["money"] -= price

        info = SHOP_ITEMS[matched]
        if info["type"] == "gift_impression":
            stats["impression"] = min(100, stats["impression"] + info["val"])
            msg = f"ได้รับ **{matched}** แล้ว~ ชอบมากๆ เลยค่า~! 💖 (ประทับใจ +{info['val']})"
        else:
            stats["grudge"] = max(0, stats["grudge"] - info["val"])
            msg = f"ได้รับ **{matched}** แล้ว~ ขอบคุณมากค่ะ~ (งอน -{info['val']})"

        _save_stats(ctx.author.id, ctx.guild.id, stats)
        _log_tx(ctx.author.id, ctx.guild.id, ctx.author.display_name, "GIFT", matched, 1, price)
        await ctx.send(msg)

    @commands.command(name="trade")
    async def trade(self, ctx: commands.Context, target: discord.Member = None, item_name: str = None, amount: int = 1):
        """มอบไอเทมให้เพื่อน: !trade @user ดอกไม้ 1"""
        if target is None or item_name is None:
            await ctx.send("วิธีใช้: `!trade @user ชื่อไอเทม [จำนวน]`")
            return
        if target.bot or target.id == ctx.author.id:
            await ctx.send("ระบุเป้าหมายไม่ถูกต้องน้า~")
            return
        if amount <= 0:
            await ctx.send("จำนวนต้องมากกว่า 0 น้า~")
            return
        matched = None
        for k in SHOP_ITEMS:
            if k.lower() == item_name.lower() or item_name.lower() in k.lower():
                matched = k
                break
        if matched is None:
            await ctx.send(f"ไม่มีไอเทม `{item_name}` ค่า~")
            return
        stats = _get_stats(ctx.author.id, ctx.guild.id)
        if stats["inventory"].get(matched, 0) < amount:
            await ctx.send(f"ไม่มี `{matched}` พอจะมอบให้เพื่อนนะค้า~")
            return
        stats["inventory"][matched] -= amount
        _save_stats(ctx.author.id, ctx.guild.id, stats)

        tstats = _get_stats(target.id, ctx.guild.id)
        tstats["inventory"][matched] = tstats["inventory"].get(matched, 0) + amount
        _save_stats(target.id, ctx.guild.id, tstats)

        _log_tx(ctx.author.id, ctx.guild.id, ctx.author.display_name, "TRADE", matched, amount, 0, target_name=target.display_name)
        await ctx.send(f"🤝 **{ctx.author.display_name}** มอบ **{matched}** x{amount} ให้ **{target.display_name}** เรียบร้อยแล้วค่า~")

    @commands.command(name="profile")
    async def profile(self, ctx: commands.Context, member: discord.Member = None):
        """ดูโปรไฟล์ 📝"""
        member = member or ctx.author
        stats = _get_stats(member.id, ctx.guild.id)
        from memory import people as ps
        person = ps.get_person(member.id, ctx.guild.id) or {}
        facts = person.get("facts", [])

        embed = discord.Embed(title=f"โปรไฟล์ของ {member.display_name}", color=0xADD8E6)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="💰 เงิน", value=f"{stats['money']} บาท", inline=True)
        embed.add_field(name="💗 ประทับใจ", value=f"{stats['impression']} / 100", inline=True)
        embed.add_field(name="😠 งอน", value=f"{stats['grudge']} / 4", inline=True)
        facts_text = "\n".join(f"• {f}" for f in facts) if facts else "ยังไม่มีบันทึก"
        embed.add_field(name="🧠 ที่ไอริจำได้", value=facts_text, inline=False)
        inv = stats["inventory"]
        inv_text = "\n".join(f"• {k}: {v}" for k, v in inv.items() if v > 0) or "ไม่มีไอเทม"
        embed.add_field(name="🎒 ไอเทม", value=inv_text, inline=False)
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Economy(bot))
