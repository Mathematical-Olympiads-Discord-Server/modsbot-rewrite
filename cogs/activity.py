import asyncio
from datetime import datetime

import schedule
from discord.ext import commands

from cogs import config as cfg

Cog = commands.Cog

today_messages = {}


class Activity(Cog):
    def __init__(self, bot):
        self.bot = bot
        schedule.every().day.at("12:00").do(asyncio.run_coroutine_threadsafe, self.process_today(), bot.loop)

    async def process_today(self):
        today_date = datetime.now().strftime("%d %b %Y")
        print(today_messages)

        # Figure out which users were active today.
        active_users_today = ''
        for user in today_messages:
            if today_messages[user] > cfg.Config.config['daily_active_threshold']:
                active_users_today += user
                active_users_today += ' '
        print(active_users_today)

        await self.bot.get_channel(cfg.Config.config['log_channel']).send(
            "Logged active users for {}: ```{}```".format(today_date, active_users_today))

        # Log that information.
        r_body = {'values': [[today_date, str(active_users_today)]]}
        cfg.Config.service.spreadsheets().values().append(spreadsheetId=cfg.Config.config['activity_sheet'],
                                                          range='Sheet1!A1', valueInputOption='RAW',
                                                          insertDataOption='INSERT_ROWS', body=r_body).execute()

        # Get the values of the previous 7 days.

    @Cog.listener()
    async def on_message(self, message):
        if not message.author.bot:  # Ignore messages from bots
            if message.author.id in today_messages:
                today_messages[message.author.id] += 1
            else:
                today_messages[message.author.id] = 1


def setup(bot):
    bot.add_cog(Activity(bot))
