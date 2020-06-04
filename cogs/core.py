from discord.ext import commands

Cog = commands.Cog


class Core(Cog):

    @commands.command(hidden=True)
    @commands.is_owner()
    async def reload(self, ctx, *, cog=''):
        """Reloads an extension"""
        try:
            ctx.bot.reload_extension(cog)
        except Exception as e:
            await ctx.send('Failed to load: `{}`\n```py\n{}\n```'.format(cog, e))
        else:
            await ctx.send('Reloaded cog {} successfully'.format(cog))


def setup(bot):
    bot.add_cog(Core(bot))
