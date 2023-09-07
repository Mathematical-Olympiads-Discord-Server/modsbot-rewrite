import schedule
from discord.ext import commands

Cog = commands.Cog


class Core(Cog):
    @commands.command(hidden=True)
    @commands.is_owner()
    async def reload(self, ctx, *, cog=""):
        """Reloads an extension"""
        schedule.clear(tag=cog)
        try:
            await ctx.bot.reload_extension(cog)
        except Exception as e:
            await ctx.send(f"Failed to load: `{cog}`\n```py\n{e}\n```")
        else:
            await ctx.send(f"Reloaded cog {cog} successfully")

    @commands.command(brief="Gets the schedule")
    @commands.is_owner()
    async def schedule(self, ctx):
        if len(schedule.jobs) == 0:
            await ctx.send("No jobs listed!")
        else:
            await ctx.send(schedule.jobs, delete_after=10)


async def setup(bot):
    await bot.add_cog(Core(bot))
