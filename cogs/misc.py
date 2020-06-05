from discord.ext import commands
from discord.ext.commands import BucketType

from cogs import config as cfg

Cog = commands.Cog

waiting_for = set()


class Misc(Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def record(self):
        g = self.bot.get_guild(cfg.Config.config['mods_guild'])

    @commands.command()
    @commands.cooldown(1, 600, BucketType.user)
    async def suggest(self, ctx, *, suggestion):
        await self.bot.get_channel(cfg.Config.config['suggestion_channel']).send(
            '**Suggestion by <@!{}>**: \n{}'.format(ctx.author.id, suggestion))


def setup(bot):
    bot.add_cog(Misc(bot))
