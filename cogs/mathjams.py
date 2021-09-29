import schedule
from discord.ext import commands

from cogs import config as cfg

Cog = commands.Cog


class Mathjams(Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        schedule.every().friday.at("11:55").do(self.schedule_ping, timeslot="a").tag('cogs.mathjams')
        schedule.every().friday.at("19:55").do(self.schedule_ping, timeslot="b").tag('cogs.mathjams')
        schedule.every().saturday.at("02:55").do(self.schedule_ping, timeslot="c").tag('cogs.mathjams')

    def schedule_ping(self, timeslot):
        self.bot.loop.create_task(self.ping_mathjams(timeslot))

    async def ping_mathjams(self, timeslot):
        role_id = cfg.Config.config[f'mathjams_timeslot_{timeslot}']
        mathjams_channel = await self.bot.fetch_channel(cfg.Config.config['mathjams_channel'])
        r = self.bot.get_guild(cfg.Config.config['mods_guild']).get_role(role_id)
        await r.edit(mentionable=True)
        await mathjams_channel.send('Mathjams in 5 minutes XD! <@&{}>'.format(role_id))
        await r.edit(mentionable=False)


def setup(bot):
    bot.add_cog(Mathjams(bot))
