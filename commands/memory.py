# -*- coding: utf-8 -*-
"""memory.py - คำสั่งจัดการความจำ: !forgetcontext, !memory"""

import discord
from discord.ext import commands

import config
from core import context_manager as ctx
from memory import people as people_store
from memory import storage


class MemoryCmd(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="forgetcontext")
    @commands.guild_only()
    async def forgetcontext(self, ctx: commands.Context):
        """ล้างบริบทสนทนาของห้องปัจจุบัน"""
        ctx.clear_channel(ctx.guild.id, ctx.channel.id)
        # ลบจาก persistent ด้วย
        conn = storage.get_conn()
        try:
            conn.execute(
                "DELETE FROM conversation_persist WHERE guild_id = ? AND channel_id = ?",
                (ctx.guild.id, ctx.channel.id),
            )
            conn.commit()
        except Exception:
            pass
        await ctx.send("เค้าลืมบทสนทนาในห้องนี้แล้วนะคะ เริ่มคุยใหม่ได้เลย~ 🧹")

    @commands.command(name="memory")
    @commands.guild_only()
    async def memory(self, ctx: commands.Context):
        """ตรวจสอบสถานะ Memory ของห้องนี้"""
        stats = ctx_module_stats = __import__("core.context_manager", fromlist=["get_stats"]).get_stats(
            ctx.guild.id, ctx.channel.id
        )
        people_count = len(people_store.list_people(ctx.guild.id))

        embed = discord.Embed(title="🧠 สถานะ Memory", color=0x9B59B6)
        embed.add_field(name="ห้องนี้", value=f"ข้อความใน context: **{stats['messages']}/{stats['max_messages']}**", inline=False)
        oldest = stats.get("oldest_age_seconds")
        if oldest is not None:
            embed.add_field(name="ข้อความเก่าสุด", value=f"{int(oldest)} วินาทีที่แล้ว (TTL: {stats['ttl_seconds']}s)", inline=False)
        else:
            embed.add_field(name="ข้อความเก่าสุด", value="ยังไม่มี", inline=False)
        embed.add_field(name="สมาชิกที่มีข้อมูล", value=f"**{people_count}** คน", inline=False)
        embed.add_field(name="โหมดตอบ", value=f"`{config.RESPOND_MODE}`", inline=True)
        await ctx.send(embed=embed)

    @commands.command(name="forgetme")
    @commands.guild_only()
    async def forgetme(self, ctx: commands.Context):
        """ล้างความจำที่เค้าจำเกี่ยวกับคุณ"""
        people_store.reset_nickname(ctx.author.id, ctx.guild.id)
        # ลบ facts
        from memory import people as ps
        person = ps.get_person(ctx.author.id, ctx.guild.id)
        if person:
            import json
            conn = storage.get_conn()
            conn.execute(
                "UPDATE people SET facts = '[]' WHERE user_id = ? AND guild_id = ?",
                (ctx.author.id, ctx.guild.id),
            )
            conn.commit()
        await ctx.send("เค้าลืมเรื่องของคุณแล้วนะคะ... แต่ยังจำได้ว่าคุณเป็นคนน่ารักอยู่ดี 😉")


async def setup(bot: commands.Bot):
    await bot.add_cog(MemoryCmd(bot))
