import ast
import asyncio
import statistics
from datetime import datetime

import discord
import schedule
from discord.ext import commands

from cogs import config as cfg

Cog = commands.Cog

POTD_RANGE = 'History!A2:M'


def is_pc(ctx):
    return ctx.author.id in cfg.Config.config['pc_codes']


class Potd(Cog):

    def __init__(self, bot):
        self.listening_in_channel = -1
        self.to_send = ''
        self.bot = bot
        self.ping_daily = False
        self.late = False
        schedule.every().day.at("12:00").do(asyncio.run_coroutine_threadsafe, self.check_potd(), bot.loop)

        # Initialise potd_ratings
        try:
            with open('data/potd_ratings.txt', 'r') as f:
                self.latest_potd = int(f.readline())
                self.potd_ratings = ast.literal_eval(f.read())
        except FileNotFoundError as e:
            self.latest_potd = 10000
            self.potd_ratings = {}
        except ValueError as e:
            print("Corrupted potd_ratings file!")
            self.latest_potd = 10000
            self.potd_ratings = {}

    def update_ratings(self):
        with open('data/potd_ratings.txt', 'r+') as f:
            # Clear
            f.truncate()

            # Re-write
            f.write(str(self.latest_potd))
            f.write('\n')
            f.write(str(self.potd_ratings))

    async def check_potd(self):
        # Get the potds from the sheet (API call)
        potds = cfg.Config.service.spreadsheets().values().get(spreadsheetId=cfg.Config.config['potd_sheet'],
                                                               range=POTD_RANGE).execute().get('values', [])

        # Check today's potd
        date = datetime.now().strftime("%d %b %Y")
        if date[0] == '0':
            date = date[1:]
        passed_current = False
        potd_row = None
        for potd in potds:
            if potd[1] == date:
                if len(potd) >= 8:  # Then there is a potd.
                    passed_current = True
                    potd_row = potd
                else:  # There is no potd.
                    await self.bot.get_channel(cfg.Config.config['helper_lounge']).send("There is no potd today!")
                    return
            if passed_current:
                if len(potd) < 8:  # Then there has not been a potd on the past day.
                    await self.bot.get_channel(cfg.Config.config['helper_lounge']).send(
                        "There is a potd today, however there was not one on {}. ".format(potd[1]))
                    return

        # Otherwise, everything has passed and we are good to go.
        # Create the message to send
        to_tex = '```\n \\textbf{Day ' + str(potd_row[0]) + '} --- ' + str(potd_row[2]) + ' ' + str(
            potd_row[1]) + '\n \\begin{flushleft} \n' + str(potd_row[8]) + '\n \\end{flushleft}```'
        print(to_tex)

        # Figure out whose potd it is
        curator = 'Unknown Curator'
        if potd_row[3] in cfg.Config.config['pc_codes'].inverse:
            curator = 'Problem chosen by <@!{}>'.format(cfg.Config.config['pc_codes'].inverse[potd_row[3]])
        difficulty_length = len(potd_row[5]) + len(potd_row[6])
        source = '{} Source: ||`{}{}{}`||'.format(curator, potd_row[4],
                                                  (' ' * (max(51 - len(potd_row[4]) - difficulty_length, 1))),
                                                  (potd_row[5] + potd_row[6]))

        # Finish up
        print(source)
        await self.bot.get_channel(cfg.Config.config['potd_channel']).send(to_tex, delete_after=1.5)
        self.latest_potd = potd_row[0]
        self.update_ratings()
        self.to_send = source
        self.listening_in_channel = cfg.Config.config['potd_channel']
        self.ping_daily = True

    @Cog.listener()
    async def on_message(self, message: discord.message):
        if message.channel.id == self.listening_in_channel and int(message.author.id) == cfg.Config.config[
            'paradox_id']:
            m = await message.channel.send(self.to_send)
            await m.add_reaction("👍")
            if self.late:
                await m.add_reaction('⏰')

            if self.ping_daily:
                r = self.bot.get_guild(cfg.Config.config['mods_guild']).get_role(cfg.Config.config['potd_role'])
                await r.edit(mentionable=True)
                await message.channel.send('<@&{}>'.format(cfg.Config.config['potd_role']))
                await r.edit(mentionable=False)

            self.listening_in_channel = -1
            self.to_send = ''
            self.late = False
            self.ping_daily = False

    @commands.command(aliases=['potd'], brief='Displays the potd from the provided number. ')
    @commands.check(is_pc)
    async def potd_display(self, ctx, number: int):
        # It can only handle one at a time!
        if not self.listening_in_channel == -1:
            await ctx.send("Please wait until the previous potd call has finished!")
            return

        reply = cfg.Config.service.spreadsheets().values().get(spreadsheetId=cfg.Config.config['potd_sheet'],
                                                               range=POTD_RANGE).execute()
        values = reply.get('values', [])
        current_potd = int(values[0][0])  # this will be the top left cell which indicates the current potd
        potd_row = values[current_potd - number]  # this gets the row requested

        # Create the message to send
        to_tex = ''
        try:
            to_tex = '```\n \\textbf{Day ' + str(number) + '} --- ' + str(potd_row[2]) + ' ' + str(
                potd_row[1]) + '\n \\begin{flushleft} \n' + str(potd_row[8]) + '\n \\end{flushleft}```'
        except IndexError:
            await ctx.send("There is no potd for day {}. ".format(number))
            return
        print(to_tex)

        # Figure out whose potd it is
        curator = 'Unknown Curator'
        if potd_row[3] in cfg.Config.config['pc_codes'].inverse:
            curator = 'Problem chosen by <@!{}>'.format(cfg.Config.config['pc_codes'].inverse[potd_row[3]])
        difficulty_length = len(potd_row[5]) + len(potd_row[6])
        source = '{} Source: ||`{}{}{}`||'.format(curator, potd_row[4],
                                                  (' ' * (max(51 - len(potd_row[4]) + difficulty_length, 1))),
                                                  (potd_row[5] + potd_row[6]))

        # Finish up
        print(source)
        await ctx.send(to_tex, delete_after=1.5)
        self.latest_potd = potd_row[0]
        self.update_ratings()
        self.to_send = source
        self.listening_in_channel = ctx.channel.id
        self.late = True

    @commands.command(aliases=['rate'], brief='Rates a potd based on difficulty. ')
    async def potd_rate(self, ctx, potd: int, rating: int):
        if potd > self.latest_potd:  # Sanitise potd number
            await ctx.author.send('You cannot rate an un-released potd!')
            return

        if potd not in self.potd_ratings:
            self.potd_ratings[potd] = {}
        self.potd_ratings[potd][ctx.author.id] = rating

        await ctx.message.delete()
        await ctx.author.send('Thanks! Your rating of {} for potd {} has been recorded. '.format(rating, potd))
        self.update_ratings()

    @commands.command(aliases=['rating'], brief='Finds the median of a potd\'s ratings')
    async def potd_rating(self, ctx, potd: int):
        if potd not in self.potd_ratings:
            await ctx.author.send('There have been no ratings for this potd yet. ')
        else:
            await ctx.author.send(
                'The median rating for potd {} is {}. '.format(potd, statistics.median(self.potd_ratings[potd].values())))


def setup(bot):
    bot.add_cog(Potd(bot))
