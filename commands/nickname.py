# -*- coding: utf-8 -*-
"""nickname.py - คำสั่งตั้ง/ตรวจชื่อเรียก: !nickname, !whois"""

import discord
from discord.ext import commands

from memory import people as people_store


class Nickname(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="nickname")
    @commands.guild_only()
    @commands.has_permissions(manage_nicknames=True)
    async def nickname(self, ctx: commands.Context, member: discord.Member = None, *, new_nickname: str = None):
        """ตั้งชื่อเรียกให้สมาชิก: !nickname @user ไอริ  |  ลบ: !nickname @user reset"""
        if member is None:
            await ctx.send("ระบุสมาชิกที่ต้องการตั้งชื่อเรียกด้วยนะคะ เช่น `!nickname @user ไอริ`")
            return

        if new_nickname is None:
            current = people_store.get_nickname(member.id, ctx.guild.id)
            if current:
                await ctx.send(f"ตอนนี้ {member.mention} มีชื่อเรียกว่า **{current}** อยู่แล้วค่ะ")
            else:
                await ctx.send(f"{member.mention} ยังไม่มีชื่อเรียกพิเศษนะคะ")
            return

        nick = new_nickname.strip()

        if nick.lower() == "reset":
            people_store.reset_nickname(member.id, ctx.guild.id)
            await ctx.send(f"ลบชื่อเรียกของ {member.mention} เรียบร้อยแล้วค่ะ (จะใช้สรรพนามทั่วไปแทน)")
            return

        if len(nick) > 32:
            await ctx.send("ชื่อเรียกยาวเกินไปนะคะ (สูงสุด 32 ตัวอักษร)")
            return

        people_store.set_nickname(member.id, ctx.guild.id, nick)
        await ctx.send(f"ตั้งชื่อเรียกของ {member.mention} เป็น **{nick}** เรียบร้อยแล้วค่ะ ✨")

    @commands.command(name="whois")
    @commands.guild_only()
    async def whois(self, ctx: commands.Context, member: discord.Member = None):
        """ตรวจสอบชื่อเรียก: !whois [@user] (ไม่ระบุ = ดูของตัวเอง)"""
        member = member or ctx.author
        person = people_store.get_person(member.id, ctx.guild.id)
        nickname = (person or {}).get("nickname", "")
        facts = (person or {}).get("facts", [])

        embed = discord.Embed(title=f"ข้อมูลของ {member.display_name}", color=0x7289DA)
        embed.add_field(name="🆔 User ID", value=str(member.id), inline=False)
        embed.add_field(name="🏷️ ชื่อเรียก", value=nickname if nickname else "(ยังไม่มี)", inline=False)
        if facts:
            embed.add_field(name="🧠 ความจำ", value="\n".join(f"• {f}" for f in facts[:10]), inline=False)
        embed.set_thumbnail(url=member.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(name="nicknames")
    @commands.guild_only()
    async def nicknames(self, ctx: commands.Context):
        """ดูรายการชื่อเรียกทั้งหมดในเซิร์ฟเวอร์"""
        people = people_store.list_people(ctx.guild.id)
        with_nicks = [p for p in people if p.get("nickname")]
        if not with_nicks:
            await ctx.send("ยังไม่มีใครตั้งชื่อเรียกไว้เลยน้า~")
            return
        lines = [f"• **{p['nickname']}** — <@{p['user_id']}>" for p in with_nicks]
        await ctx.send("**รายการชื่อเรียกในเซิร์ฟเวอร์:**\n" + "\n".join(lines))


async def setup(bot: commands.Bot):
    await bot.add_cog(Nickname(bot))
