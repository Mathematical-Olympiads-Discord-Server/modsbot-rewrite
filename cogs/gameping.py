import time

from discord.ext import commands

from cogs import config as cfg


class Games(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cooldown_until = (
            None  # stores expiration timestamp (time.time() + seconds)
        )

    @commands.command(name="games", aliases=["g"])
    @commands.guild_only()
    @commands.check(cfg.is_active)
    async def games(self, ctx):

        role_id = self.bot.config.get("games_role")
        if not role_id:
            await ctx.send("Game role not configured.")
            return

        role = ctx.guild.get_role(role_id)
        if role is None:
            await ctx.send("Game role not found in this server.")
            return

        # Cooldown duration in seconds
        cooldown_minutes = self.bot.config.get("minutes_games_cooldown", 5)
        cooldown_seconds = cooldown_minutes * 60

        # Check cooldown
        now = time.time()
        if self.cooldown_until and now < self.cooldown_until:
            remaining = self.cooldown_until - now
            await ctx.send(
                f"Game role ping is on cooldown. Try again in {remaining} seconds."
            )
            return

        # Send the ping
        await ctx.send(f"{role.mention}")

        # Set cooldown expiration
        self.cooldown_until = now + cooldown_seconds


async def setup(bot):
    await bot.add_cog(Games(bot))
