from discord.ext import commands

from cogs import config as cfg

Cog = commands.Cog


class Misc(Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def record(self):
        g = self.bot.get_guild(cfg.Config.config['mods_guild'])




def setup(bot):
    bot.add_cog(Misc(bot))
