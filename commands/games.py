# -*- coding: utf-8 -*-
"""games.py - มินิเกมแบบปุ่มกด: rps, guess, lotto, match_images + weather"""

import random
import asyncio
import discord
from discord.ext import commands

from commands.economy import _get_stats, _save_stats


class RPSView(discord.ui.View):
    def __init__(self, user_id: int, guild_id: int):
        super().__init__(timeout=30)
        self.user_id = user_id
        self.guild_id = guild_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("เกมของคนอื่นน้า~ 🥺", ephemeral=True)
            return False
        return True

    async def play(self, interaction: discord.Interaction, player: str):
        bot_choice = random.choice(["rock", "paper", "scissors"])
        th = {"rock": "ค้อน", "paper": "กระดาษ", "scissors": "กรรไกร"}
        if player == bot_choice:
            result = f"เค้าเลือก {th[bot_choice]} เหมือนกันเลย! เสมอกันน้า~ 🤝"
        elif (player == "rock" and bot_choice == "scissors") or \
             (player == "paper" and bot_choice == "rock") or \
             (player == "scissors" and bot_choice == "paper"):
            result = f"เค้าเลือก {th[bot_choice]}... คุณชนะเค้าแล้ว! เก่งจัง~ 🎉 (ได้ 10 บาท)"
            stats = _get_stats(self.user_id, self.guild_id)
            stats["money"] += 10
            _save_stats(self.user_id, self.guild_id, stats)
        else:
            result = f"เค้าเลือก {th[bot_choice]}... คุณแพ้เค้าแล้ว! ฮิฮิ~ 😏 ลองใหม่น้า!"
        for c in self.children:
            c.disabled = True
        await interaction.response.edit_message(content=result, view=self)

    @discord.ui.button(label="ค้อน ✊", style=discord.ButtonStyle.secondary)
    async def rock(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.play(interaction, "rock")

    @discord.ui.button(label="กระดาษ 🖐️", style=discord.ButtonStyle.secondary)
    async def paper(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.play(interaction, "paper")

    @discord.ui.button(label="กรรไกร ✌️", style=discord.ButtonStyle.secondary)
    async def scissors(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.play(interaction, "scissors")


class GuessView(discord.ui.View):
    def __init__(self, correct: int, user_id: int, guild_id: int):
        super().__init__(timeout=30)
        self.correct = correct
        self.user_id = user_id
        self.guild_id = guild_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("เกมของคนอื่นน้า~ 🥺", ephemeral=True)
            return False
        return True

    async def callback(self, interaction: discord.Interaction):
        guess = int(interaction.data["custom_id"])
        if guess == self.correct:
            for c in self.children:
                c.disabled = True
            await interaction.response.edit_message(
                content=f"ถูกต้อง! เลขคือ {self.correct} ค่า~ 🎉 (ได้ 20 บาท)", view=self
            )
            stats = _get_stats(self.user_id, self.guild_id)
            stats["money"] += 20
            _save_stats(self.user_id, self.guild_id, stats)
        else:
            await interaction.response.send_message(f"เลข {guess} ไม่ถูกน้า~ ลองใหม่ค่า! 😆", ephemeral=True)


class GuessViewButtons(GuessView):
    def __init__(self, correct: int, user_id: int, guild_id: int):
        super().__init__(correct, user_id, guild_id)
        # สร้างปุ่ม 1-10
        for i in range(1, 11):
            btn = discord.ui.Button(label=str(i), style=discord.ButtonStyle.secondary, custom_id=str(i))
            btn.callback = self._make_cb(i)
            self.add_item(btn)

    def _make_cb(self, val: int):
        async def _cb(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("เกมของคนอื่นน้า~ 🥺", ephemeral=True)
                return
            if val == self.correct:
                for c in self.children:
                    c.disabled = True
                await interaction.response.edit_message(
                    content=f"ถูกต้อง! เลขคือ {self.correct} ค่า~ 🎉 (ได้ 20 บาท)", view=self
                )
                stats = _get_stats(self.user_id, self.guild_id)
                stats["money"] += 20
                _save_stats(self.user_id, self.guild_id, stats)
            else:
                await interaction.response.send_message(f"เลข {val} ไม่ถูกน้า~ ลองใหม่ค่า! 😆", ephemeral=True)
        return _cb


class MatchView(discord.ui.View):
    def __init__(self, images: list, user_id: int, guild_id: int):
        super().__init__(timeout=60)
        self.images = images
        self.user_id = user_id
        self.guild_id = guild_id
        self.selected: list = []
        for i in range(len(images)):
            btn = discord.ui.Button(label="?", style=discord.ButtonStyle.secondary, custom_id=str(i))
            btn.callback = self._make_cb(i)
            self.add_item(btn)

    def _make_cb(self, idx: int):
        async def _cb(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("เกมของคนอื่นน้า~ 🥺", ephemeral=True)
                return
            if idx in self.selected:
                return
            self.selected.append(idx)
            self.children[idx].label = self.images[idx]
            self.children[idx].style = discord.ButtonStyle.primary
            self.children[idx].disabled = True

            if len(self.selected) == 2:
                a, b = self.selected
                if self.images[a] == self.images[b]:
                    for c in self.children:
                        c.disabled = True
                    await interaction.response.edit_message(content="จับคู่ถูกต้อง! 🎉 (ได้ 20 บาท)", view=self)
                    stats = _get_stats(self.user_id, self.guild_id)
                    stats["money"] += 20
                    _save_stats(self.user_id, self.guild_id, stats)
                else:
                    await interaction.response.edit_message(content="ไม่เหมือนกันนะ~ ปิดใหม่น้า", view=self)
                    await asyncio.sleep(1.2)
                    for i in self.selected:
                        self.children[i].label = "?"
                        self.children[i].style = discord.ButtonStyle.secondary
                        self.children[i].disabled = False
                    self.selected = []
                    try:
                        await interaction.edit_original_response(content="จับคู่ผลไม้ให้เหมือนกันนะ~ 🍎🍌🍒", view=self)
                    except Exception:
                        pass
            else:
                await interaction.response.edit_message(view=self)
        return _cb


class Games(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="rps")
    async def rps(self, ctx: commands.Context):
        """เป่ายิ้งฉุบกับไอริ ✊🖐️✌️"""
        view = RPSView(user_id=ctx.author.id, guild_id=ctx.guild.id)
        await ctx.send("เป่ายิ้งฉุบกัน! เลือกมาเลยค่า~", view=view)

    @commands.command(name="guess")
    async def guess(self, ctx: commands.Context):
        """เกมทายเลข 1-10 🎯"""
        view = GuessViewButtons(correct=random.randint(1, 10), user_id=ctx.author.id, guild_id=ctx.guild.id)
        await ctx.send("ทายเลข 1-10 มาเลยค่า~", view=view)

    @commands.command(name="lotto")
    async def lotto(self, ctx: commands.Context):
        """ซื้อลอตเตอรี่ 10 บาท 🎰"""
        stats = _get_stats(ctx.author.id, ctx.guild.id)
        if stats["money"] < 10:
            await ctx.send("เงินไม่พอซื้อลอตเตอรี่เลยน้า~ 😢 (ลอง `!work` ก่อนนะ)")
            return
        stats["money"] -= 10
        win = random.randint(0, 99)
        mine = random.randint(0, 99)
        result = f"เลขที่ออก: **{win:02d}**\nเลขของคุณ: **{mine:02d}**\n"
        if mine == win:
            stats["money"] += 100
            result += "🎉 ถูกรางวัลใหญ่! รับ 100 บาทค่า~"
        elif mine % 10 == win % 10 or mine // 10 == win // 10:
            stats["money"] += 20
            result += "✨ ถูกรางวัลเลขหลักเดียว~ รับ 20 บาทค่า~"
        else:
            result += "😭 ไม่ถูกเลย ไว้ลองใหม่น้า~"
        _save_stats(ctx.author.id, ctx.guild.id, stats)
        await ctx.send(result)

    @commands.command(name="match_images")
    async def match_images(self, ctx: commands.Context):
        """จับคู่ผลไม้ 🍎🍌🍒"""
        images = ["🍎", "🍌", "🍒", "🍎", "🍌", "🍒"]
        random.shuffle(images)
        view = MatchView(images=images, user_id=ctx.author.id, guild_id=ctx.guild.id)
        await ctx.send("จับคู่ผลไม้ที่เหมือนกันให้ได้นะ~", view=view)

    @commands.command(name="weather")
    async def weather(self, ctx: commands.Context, *, location: str = "Bangkok"):
        """เช็คอากาศ: !weather Bangkok"""
        import requests
        try:
            url = f"https://wttr.in/{location.replace(' ', '+')}?format=3&lang=th"
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                await ctx.send(f"🌤️ `{r.text.strip()}`")
            else:
                await ctx.send("หาข้อมูลอากาศไม่เจอเลยน้า~ 😢")
        except Exception:
            await ctx.send("เช็คอากาศไม่ได้ตอนนี้ค่า~ 🌧️")


async def setup(bot: commands.Bot):
    await bot.add_cog(Games(bot))
