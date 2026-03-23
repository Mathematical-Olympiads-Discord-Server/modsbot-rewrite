from datetime import datetime, timezone
from random import choice

from discord.ext import commands

from cogs import config as cfg

import asyncio

Cog = commands.Cog

class Games(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.lock = False
    
    async def release_lock(self):
        minutes_cooldown = cfg.Config.config.get("minutes_games_cooldown", 10)
        await asyncio.sleep(minutes_cooldown * 60)
        self.lock = False  
      
    @commands.command()
    @commands.guild_only()
    @commands.check(cfg.is_active)
    async def games(self, ctx):
        role_id = cfg.Config.config["games_role"]
        role = ctx.guild.get_role(role_id)
        if not role:
            await ctx.send("Incorrect or missing game role")
            return

        if self.lock:
            await ctx.send("Games role ping is on cooldown.")
            return

        self.lock = True
        try:
            await ctx.send(f"{role.mention}")
        finally:
            asyncio.create_task(self.release_lock())
        

async def setup(bot):
    await bot.add_cog(Games(bot))


        

    
