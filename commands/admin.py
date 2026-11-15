# -*- coding: utf-8 -*-
"""admin.py - คำสั่งระบบ: !airihelp, !airistatus, !setmode, !allow, !disallow, !set_welcome, !set_announcement, !airireload"""

import time
import discord
from discord.ext import commands

import config

START_TIME = time.time()


def _is_admin(ctx: commands.Context) -> bool:
    return ctx.author.guild_permissions.manage_guild


class AdminCmd(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="airihelp")
    async def airihelp(self, ctx: commands.Context):
        """แสดงรายการคำสั่งทั้งหมด"""
        p = config.COMMAND_PREFIX
        embed = discord.Embed(title="🌸 คำสั่งของไอริ", color=0xFFB6C1)

        embed.add_field(
            name="💬 สนทนา & ความจำ",
            value=(
                f"`{p}nickname @user [ชื่อ]` — ตั้งชื่อเรียก\n"
                f"`{p}nickname @user reset` — ลบชื่อเรียก\n"
                f"`{p}whois [@user]` — ดูข้อมูล/ชื่อเรียก\n"
                f"`{p}nicknames` — รายการชื่อเรียกทั้งหมด\n"
                f"`{p}forgetcontext` — ล้างบริบทห้องนี้\n"
                f"`{p}forgetme` — ลืมเรื่องของคุณ\n"
                f"`{p}memory` — สถานะ Memory"
            ),
            inline=False,
        )
        embed.add_field(
            name="⚙️ ระบบ (Admin)",
            value=(
                f"`{p}airistatus` — สถานะบอท\n"
                f"`{p}setmode <mention|active|selective>` — โหมดตอบ\n"
                f"`{p}allow #ch` / `{p}disallow #ch` — จัดการห้อง\n"
                f"`{p}set_welcome #ch` — ห้องต้อนรับ\n"
                f"`{p}set_announcement #ch` — ห้องแจ้งเตือนเวลา\n"
                f"`{p}airireload` — โหลดคำสั่งใหม่"
            ),
            inline=False,
        )
        embed.add_field(
            name="💰 เศรษฐกิจ & 🎮 เกม",
            value=(
                f"`{p}work` `{p}balance` `{p}shop` `{p}buy` `{p}sell` `{p}inventory` `{p}history`\n"
                f"`{p}send_gift` `{p}trade` `{p}profile`\n"
                f"`{p}rps` `{p}guess` `{p}lotto` `{p}match_images` `{p}weather [เมือง]`"
            ),
            inline=False,
        )
        embed.set_footer(text="พิมพ์ @ไอริ หรือ Reply หาเค้าเพื่อคุยได้ทุกห้องเลยนะ 😉")
        await ctx.send(embed=embed)

    @commands.command(name="airistatus")
    async def airistatus(self, ctx: commands.Context):
        """ตรวจสอบสถานะบอท"""
        uptime = int(time.time() - START_TIME)
        h, rem = divmod(uptime, 3600)
        m, s = divmod(rem, 60)
        latency = round(self.bot.latency * 1000)

        embed = discord.Embed(title="📊 สถานะไอริ", color=0x00FFCC)
        embed.add_field(name="📶 Ping", value=f"`{latency} ms`", inline=True)
        embed.add_field(name="⏱️ Uptime", value=f"`{h}h {m}m {s}s`", inline=True)
        embed.add_field(name="🤖 โหมดตอบ", value=f"`{config.RESPOND_MODE}`", inline=True)
        embed.add_field(name="🧠 โมเดล AI", value=f"`{config.MODEL_NAME}`", inline=True)
        embed.add_field(name="🏠 เซิร์ฟเวอร์", value=f"`{len(self.bot.guilds)}`", inline=True)
        embed.add_field(name="📡 Latency (Gateway)", value=f"`{latency} ms`", inline=True)
        embed.set_footer(text="ทำงานบน Termux/Android ปกติค่า ⚡")
        await ctx.send(embed=embed)

    @commands.command(name="setmode")
    @commands.guild_only()
    async def setmode(self, ctx: commands.Context, mode: str = None):
        """เปลี่ยนโหมดตอบ: !setmode mention|active|selective (Admin)"""
        if not _is_admin(ctx):
            await ctx.send("คำสั่งนี้สำหรับผู้ดูแลเท่านั้นนะคะ 😤")
            return
        mode = (mode or "").lower()
        if mode not in ("mention", "active", "selective"):
            await ctx.send(f"โหมดที่ใช้ได้: `mention`, `active`, `selective` ค่ะ (ตอนนี้: `{config.RESPOND_MODE}`)")
            return
        config.RESPOND_MODE = mode
        desc = {
            "mention": "ตอบเมื่อ Mention/Reply ถึงไอริ",
            "active": "ตอบทุกข้อความในห้องที่อนุญาต",
            "selective": "ตอบเฉพาะห้องที่อนุญาตเท่านั้น",
        }
        await ctx.send(f"เปลี่ยนโหมดตอบเป็น **{mode}** แล้วค่า ({desc[mode]}) ✅")

    @commands.command(name="allow")
    @commands.guild_only()
    async def allow(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """เพิ่มห้องที่อนุญาตให้ตอบ (Admin)"""
        if not _is_admin(ctx):
            await ctx.send("คำสั่งนี้สำหรับผู้ดูแลเท่านั้นนะคะ 😤")
            return
        if channel is None:
            channel = ctx.channel
        if channel.id not in config.ALLOWED_CHANNELS:
            config.ALLOWED_CHANNELS.append(channel.id)
        await ctx.send(f"เพิ่ม {channel.mention} เข้ารายการห้องที่อนุญาตแล้วค่า ✅")

    @commands.command(name="disallow")
    @commands.guild_only()
    async def disallow(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """ลบห้องออกจากรายการที่อนุญาต (Admin)"""
        if not _is_admin(ctx):
            await ctx.send("คำสั่งนี้สำหรับผู้ดูแลเท่านั้นนะคะ 😤")
            return
        if channel is None:
            channel = ctx.channel
        if channel.id in config.ALLOWED_CHANNELS:
            config.ALLOWED_CHANNELS.remove(channel.id)
        await ctx.send(f"ลบ {channel.mention} ออกจากรายการแล้วค่า ✅")
        await ctx.send(f"รายการตอนนี้: {config.ALLOWED_CHANNELS or '(ว่าง)'}")

    @commands.command(name="set_welcome")
    @commands.guild_only()
    async def set_welcome(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """ตั้งห้องต้อนรับสมาชิกใหม่ (Admin)"""
        if not _is_admin(ctx):
            await ctx.send("คำสั่งนี้สำหรับผู้ดูแลเท่านั้นนะคะ 😤")
            return
        if channel is None:
            await ctx.send("ระบุห้องด้วยนะคะ เช่น `!set_welcome #general`")
            return
        config.WELCOME_CHANNEL_ID = channel.id
        await ctx.send(f"ตั้งห้องต้อนรับเป็น {channel.mention} เรียบร้อยแล้วค่า ✨")

    @commands.command(name="set_announcement")
    @commands.guild_only()
    async def set_announcement(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """ตั้งห้องแจ้งเตือนเวลา (Admin)"""
        if not _is_admin(ctx):
            await ctx.send("คำสั่งนี้สำหรับผู้ดูแลเท่านั้นนะคะ 😤")
            return
        if channel is None:
            await ctx.send("ระบุห้องด้วยนะคะ เช่น `!set_announcement #announcements`")
            return
        config.ANNOUNCEMENT_CHANNEL_ID = channel.id
        await ctx.send(f"ตั้งห้องแจ้งเตือนเวลา (อรุณสวัสดิ์/ฝันดี/ไล่นอน) เป็น {channel.mention} เรียบร้อยแล้วค่า ⏰")

    @commands.command(name="airireload")
    @commands.is_owner()
    async def airireload(self, ctx: commands.Context):
        """โหลด extensions ทั้งหมดใหม่ (เจ้าของบอท)"""
        try:
            for ext in list(self.bot.extensions.keys()):
                await self.bot.reload_extension(ext)
            await ctx.send("โหลดคำสั่งใหม่เรียบร้อยแล้วค่า 🔄")
        except Exception as e:
            await ctx.send(f"โหลดไม่สำเร็จ: `{e}`")


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCmd(bot))
