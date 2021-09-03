import schedule
from discord.ext import commands

from cogs import config as cfg

Cog = commands.Cog


class Mathjams(Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        schedule.every().friday.at("11:55").do(self.schedule_ping).tag('cogs.mathjams')
        schedule.every().friday.at("19:55").do(self.schedule_ping).tag('cogs.mathjams')
        schedule.every().saturday.at("02:55").do(self.schedule_ping).tag('cogs.mathjams')
        self.mathjams_role = cfg.Config.config['mathjams_role']

    def schedule_ping(self):
        self.bot.loop.create_task(self.ping_mathjams())

    async def ping_mathjams(self):
        mathjams_channel = await self.bot.fetch_channel(cfg.Config.config['mathjams_channel'])
        r = self.bot.get_guild(cfg.Config.config['mods_guild']).get_role(cfg.Config.config['mathjams_role'])
        await r.edit(mentionable=True)
        await mathjams_channel.send('Mathjams in 5 minutes XD! <@&{}>'.format(cfg.Config.config['mathjams_role']))
        await r.edit(mentionable=False)


def setup(bot):
    bot.add_cog(Mathjams(bot))
