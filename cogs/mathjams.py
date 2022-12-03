import schedule
from discord.ext import commands
import sqlite3

from cogs import config as cfg

Cog = commands.Cog


class Mathjams(Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        cursor = cfg.db.cursor()
        cursor.execute('''INSERT OR IGNORE INTO settings VALUES
            ('mathjams_ping', 'True')
            ''')
        cfg.db.commit()
        cursor.execute("SELECT value FROM settings WHERE setting = 'mathjams_ping'")
        self.ping = (cursor.fetchone()[0] == 'True')
        schedule.every().friday.at("11:55").do(self.schedule_ping, timeslot="a").tag('cogs.mathjams')
        schedule.every().friday.at("19:55").do(self.schedule_ping, timeslot="b").tag('cogs.mathjams')
        schedule.every().saturday.at("02:55").do(self.schedule_ping, timeslot="c").tag('cogs.mathjams')

    def schedule_ping(self, timeslot):
        self.bot.loop.create_task(self.ping_mathjams(timeslot))

    async def ping_mathjams(self, timeslot):
        if self.ping:
            role_id = cfg.Config.config[f'mathjams_timeslot_{timeslot}']
            mathjams_channel = await self.bot.fetch_channel(cfg.Config.config['mathjams_channel'])
            r = self.bot.get_guild(cfg.Config.config['mods_guild']).get_role(role_id)
            await r.edit(mentionable=True)
            await mathjams_channel.send('Mathjams in 5 minutes XD! <@&{}>'.format(role_id))
            await r.edit(mentionable=False)

    @commands.command()
    @commands.check(cfg.is_staff)
    async def mathjams(self, ctx, status: bool=None):
        if status == None:
            self.ping = not self.ping
        else:
            self.ping = status
        cursor = cfg.db.cursor()
        cursor.execute(f"UPDATE settings SET value = '{str(self.ping)}' WHERE setting = 'mathjams_ping'")
        cfg.db.commit()
        await ctx.guild.get_channel(cfg.Config.config['log_channel']).send(
            f'**Mathjams auto ping set to `{self.ping}` by {ctx.author.mention}**')



async def setup(bot):
    await bot.add_cog(Mathjams(bot))
