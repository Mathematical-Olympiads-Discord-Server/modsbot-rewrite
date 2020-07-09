import ast
import asyncio
import logging
import pickle
from datetime import datetime

import discord
import schedule
from discord.ext import commands

from cogs import config as cfg

Cog = commands.Cog

today_messages = {}


class Activity(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger('cogs.activity')
        self.new_message = False
        schedule.every().day.at("09:30").do(asyncio.run_coroutine_threadsafe, self.process_today(), bot.loop).tag(
            'cogs.activity')
        schedule.every(5).minutes.do(self.f_dump).tag('cogs.activity')

        # Start
        try:
            x = pickle.load(open('data/activity_dump.p', 'rb'))
            for i in x: today_messages[i] = x[i]
        except FileNotFoundError:
            today_messages.clear()

    async def process_today(self):
        today_date = datetime.now().strftime("%d %b %Y")
        self.logger.info(today_messages)

        # Figure out which users were active today.
        active_users_today = str(today_messages)

        await self.bot.get_channel(cfg.Config.config['log_channel']).send(
            "Logged active users for {}: ```{}```".format(today_date, active_users_today))

        # Log that information.
        r_body = {'values': [[today_date, str(active_users_today)]]}
        cfg.Config.service.spreadsheets().values().append(spreadsheetId=cfg.Config.config['activity_sheet'],
                                                          range='Log!A1', valueInputOption='RAW',
                                                          insertDataOption='INSERT_ROWS', body=r_body).execute()

        '''
        # Get the values of the previous x days.
        activity = cfg.Config.service.spreadsheets().values().get(spreadsheetId=cfg.Config.config['potd_sheet'],
                                                                  range='Log!A2:B').execute().get('values', [])
        active_days = {}
        for i in range(-1, -cfg.Config.config['period_length'] - 1, -1):
            activity_that_day = ast.literal_eval(activity[i][1])
            for user in activity_that_day:
                active_days = active_days.get(user, 0) + 1

        active_users = set()
        for user in active_days:
            if active_days[user] >= cfg.Config.config['days_active_threshold']:
                active_days.add(user)

        for user in active_users:
        '''
        # Clear today's
        today_messages.clear()
        self.f_dump()

    @Cog.listener()
    async def on_message(self, message):
        if not message.author.bot and message.guild is not None:  # Ignore messages from bots and DMs
            if message.author.id in today_messages:
                today_messages[message.author.id] += 1
            else:
                today_messages[message.author.id] = 1
            cursor = cfg.db.cursor()
            cursor.execute(
                'INSERT INTO messages (discord_message_id, discord_channel_id, discord_user_id, message_length, message_date) VALUES (%s, %s, %s, %s, %s)',
                (message.id, message.channel.id, message.author.id, len(message.content), datetime.now()))
            cfg.db.commit()
        self.new_message = True

    @commands.command()
    @commands.is_owner()
    async def dump_activity(self, ctx):
        await ctx.send(today_messages)

    @commands.command()
    @commands.is_owner()
    async def add_activity(self, ctx, *, activity):
        try:
            activity_dict = ast.literal_eval(activity)
            for user in activity_dict:
                if user in today_messages:
                    today_messages[user] += activity_dict[user]
                else:
                    today_messages[user] = activity_dict[user]
            await ctx.send('Done!: New activity: ```{}```'.format(today_messages))
        except:
            await ctx.send("Something went wrong! ")

    @commands.command()
    @commands.is_owner()
    async def f_dump_activity(self, ctx):
        pickle.dump(today_messages, open('data/activity_dump.p', 'wb+'))
        await ctx.send("Dumped")

    def f_dump(self):
        if self.new_message:
            pickle.dump(today_messages, open('data/activity_dump.p', 'wb+'))
            self.logger.info('Dumped activity: {}'.format(str(today_messages)))
        else:
            self.logger.info('No new messages. ')
        self.new_message = False

    @commands.command()
    @commands.is_owner()
    async def f_load_activity(self, ctx):
        x = pickle.load(open('data/activity_dump.p', 'rb'))
        today_messages.clear()
        for i in x:
            today_messages[i] = x[i]
        await ctx.send("Loaded: ```{}```".format(today_messages))

    @commands.command()
    async def active_days(self, ctx):
        cursor = cfg.db.cursor()
        cursor.execute(f'''SELECT discord_user_id as userid, date(message_date) as date, COUNT(*) AS number
            FROM messages
            WHERE date(message_date) > date_sub(curdate(), interval 14 day)
            GROUP BY discord_user_id, DATE(message_date)
            HAVING number >= 10 and userid = {ctx.author.id}
            ORDER BY DATE(message_date), discord_user_id;''')
        l = len(cursor.fetchall())
        await ctx.author.send(f'You have {l} active days!')

    @commands.command()
    async def active_days_o(self, ctx, other: discord.User):
        cursor = cfg.db.cursor()
        cursor.execute(f'''SELECT discord_user_id as userid, date(message_date) as date, COUNT(*) AS number
            FROM messages
            WHERE date(message_date) > date_sub(curdate(), interval 14 day)
            GROUP BY discord_user_id, DATE(message_date)
            HAVING number >= 10 and userid = {other.id}
            ORDER BY DATE(message_date), discord_user_id;''')
        l = len(cursor.fetchall())
        await ctx.author.send(f'{other.display_name} has {l} active days!')


def setup(bot):
    bot.add_cog(Activity(bot))
