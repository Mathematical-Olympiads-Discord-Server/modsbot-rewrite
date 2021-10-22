import ast
import asyncio
import statistics
from datetime import datetime, timedelta

import discord
import schedule
import threading
from discord.ext import commands

from cogs import config as cfg

Cog = commands.Cog

POTD_RANGE = 'History!A2:M'


def is_pc(ctx):
    return ctx.author.id in cfg.Config.config['pc_codes']

class Potd(Cog):

    def __init__(self, bot: commands.Bot):

        self.listening_in_channel = -1
        self.to_send = ''
        self.bot = bot
        self.ping_daily = False
        self.late = False
        self.requested_number = -1
        self.dm_no = 0
        self.dm_list = []
        self.timer = None
        
        cursor = cfg.db.cursor()
        cursor.execute('''INSERT OR IGNORE INTO settings VALUES
            ('potd_dm', 'True')
            ''')
        cfg.db.commit()
        cursor.execute("SELECT value FROM settings WHERE setting = 'potd_dm'")
        self.enable_dm = (cursor.fetchone()[0] == 'True')

        schedule.every().day.at("10:00").do(self.schedule_potd).tag('cogs.potd')

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

    def reset(self):
        if self.listening_in_channel != -1: # Prevent reset during execution
            self.requested_number = -1
            self.listening_in_channel = -1
            self.to_send = ''
            self.late = False
            self.ping_daily = False
            self.dm_no = 0
            self.dm_list = []
            try:
                self.timer.cancel()
            except Exception:
                pass
            self.timer = None

    def prepare_dms(self, potd_row):
        def should_dm(x):
            return (d >= x[2]) and (d <= x[3]) and (len(set(x[1]).intersection(potd_row[5])) != 0)

        try:
            d = int(potd_row[6])
        except Exception:
            return

        cursor = cfg.db.cursor()
        cursor.execute("SELECT * FROM potd_ping")
        result = cursor.fetchall()
        self.dm_no = len(result)
        self.dm_list = [i[0] for i in filter(should_dm, result)]

    def generate_source(self, potd_row):
        # Figure out whose potd it is
        curator = 'Unknown Curator'
        if potd_row[3] in cfg.Config.config['pc_codes'].inverse:
            curator = '<@!{}>'.format(cfg.Config.config['pc_codes'].inverse[potd_row[3]])
        difficulty_length = len(potd_row[5]) + len(potd_row[6])
        padding = (' ' * (max(35 - len(potd_row[4]), 1)))

        source = discord.Embed()
        source.add_field(name='Curator', value=curator)
        source.add_field(name='Source', value=f'||`{potd_row[4]}{padding}`||')
        source.add_field(name='Difficulty', value=f'||`{str(potd_row[6]).ljust(5)}`||')
        source.add_field(name='Genre', value=f'||`{str(potd_row[5]).ljust(5)}`||')
        source.add_field(name='Subscribed', value=f'||`{self.dm_no}`||')
        source.set_footer(text=f'Use -rating {potd_row[0]} to check the community difficulty rating of this problem '
                            f'or -rate {potd_row[0]} rating to rate it yourself. React with a 👍 if you liked '
                            f'the problem. ')

        return source

    def schedule_potd(self):
        self.bot.loop.create_task(self.check_potd())

    def update_ratings(self):
        with open('data/potd_ratings.txt', 'r+') as f:
            # Clear
            f.truncate()

            # Re-write
            f.write(str(self.latest_potd))
            f.write('\n')
            f.write(str(self.potd_ratings))

    async def potd_embedded(self, ctx, *, number: int):
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
            to_tex = '```tex\n \\textbf{Day ' + str(number) + '} --- ' + str(potd_row[2]) + ' ' + str(
                potd_row[1]) + '\n \\begin{flushleft} \n' + str(potd_row[8]) + '\n \\end{flushleft}```'
        except IndexError:
            await ctx.send("There is no potd for day {}. ".format(number))
            return
        print(to_tex)

        # Finish up
        await ctx.send(to_tex, delete_after=20)
        self.requested_number = int(potd_row[0])
        self.latest_potd = int(potd_row[0])
        self.update_ratings()
        self.to_send = self.generate_source(potd_row)
        self.listening_in_channel = ctx.channel.id
        self.late = True

    @commands.command() # TESTING
    @commands.check(cfg.is_staff) # TESTING
    async def check_potd(self, ctx): # TESTING
    # async def check_potd(self):

        # Get the potds from the sheet (API call)
        potds = cfg.Config.service.spreadsheets().values().get(spreadsheetId=cfg.Config.config['potd_sheet'],
                                                               range=POTD_RANGE).execute().get('values', [])

        # Check today's potd
        date = datetime.now().strftime("%d %b %Y")
        tmr = (datetime.now() + timedelta(days = 1)).strftime("%d %b %Y")
        if date[0] == '0':
            date = date[1:]
        if tmr[0] == '0':
            tmr = tmr[1:]
        passed_current = False
        potd_row = None
        fail = False
        has_tmr = False
        for potd in potds:
            if potd[1] == date:
                if len(potd) >= 8:  # Then there is a potd.
                    passed_current = True
                    potd_row = potd
                else:  # There is no potd.
                    fail = True
                    await self.bot.get_channel(cfg.Config.config['helper_lounge']).send("There is no potd today!")
            if passed_current:
                if len(potd) < 8:  # Then there has not been a potd on that day.
                    if fail:
                        await self.bot.get_channel(cfg.Config.config['helper_lounge']).send(
                            "There was no potd on {}. ".format(potd[1]))
                    else:
                        await self.bot.get_channel(cfg.Config.config['helper_lounge']).send(
                            "There is a potd today, but there wasn't one on {}. ".format(potd[1]))
                    fail = True
            if potd[1] == tmr:
                if len(potd) >= 8:  # Then there is a potd tomorrow.
                    has_tmr = True
        if not has_tmr:
            await self.bot.get_channel(cfg.Config.config['helper_lounge']).send("There is no potd tomorrow!")
        if fail:
            return

        print('l123')
        # Otherwise, everything has passed and we are good to go.
        # Create the message to send
        to_tex = '```tex\n \\textbf{Day ' + str(potd_row[0]) + '} --- ' + str(potd_row[2]) + ' ' + str(
            potd_row[1]) + '\n \\begin{flushleft} \n' + str(potd_row[8]) + '\n \\end{flushleft}```'
        print(to_tex)

        # Finish up
        await self.bot.get_channel(cfg.Config.config['potd_channel']).send(to_tex, delete_after=20)
        self.requested_number = int(potd_row[0])
        self.latest_potd = int(potd_row[0])
        self.update_ratings()
        self.prepare_dms(potd_row)
        self.to_send = self.generate_source(potd_row)
        self.listening_in_channel = cfg.Config.config['potd_channel']
        self.ping_daily = True
        print('l149')
        # In case Paradox unresponsive
        self.timer = threading.Timer(20, self.reset)
        self.timer.start()

    @Cog.listener()
    async def on_message(self, message: discord.message):
        if message.channel.id == self.listening_in_channel and int(message.author.id) == cfg.Config.config[
            'paradox_id']:
            # m = await message.channel.send(
            #     '{} \nRate this problem with `-rate {} <rating>` and check its user difficulty rating with `-rating {}`'.format(
            #         self.to_send, self.requested_number, self.requested_number))
            self.listening_in_channel = -1 # Prevent reset
            source_msg = await message.channel.send(embed=self.to_send)
            await source_msg.add_reaction("👍")
            if self.late:
                await source_msg.add_reaction('⏰')

            if self.ping_daily:
                r = self.bot.get_guild(cfg.Config.config['mods_guild']).get_role(cfg.Config.config['potd_role'])
                await r.edit(mentionable=True)
                await message.channel.send('<@&{}>'.format(cfg.Config.config['potd_role']))
                await r.edit(mentionable=False)

                if self.enable_dm:
                    bot_spam = message.guild.get_channel(cfg.Config.config['bot_spam_channel'])
                    ping_embed = discord.Embed()
                    ping_embed.add_field(name=f'POTD {self.latest_potd} has been posted: ', value=message.channel.mention)
                    for id in self.dm_list:
                        member = message.guild.get_member(int(id))
                        try:
                            if member is not None and not member.bot:
                                await member.send(embed=ping_embed)
                        except discord.Forbidden:
                            await bot_spam.send(member.mention, embed=ping_embed)

            try:
                await message.publish()
                await source_msg.publish()
            except Exception:
                pass

            self.reset()

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
            to_tex = '```tex\n \\textbf{Day ' + str(number) + '} --- ' + str(potd_row[2]) + ' ' + str(
                potd_row[1]) + '\n \\begin{flushleft} \n' + str(potd_row[8]) + '\n \\end{flushleft}```'
        except IndexError:
            await ctx.send("There is no potd for day {}. ".format(number))
            return
        print(to_tex)

        # Finish up
        await ctx.send(to_tex, delete_after=20)
        self.requested_number = int(potd_row[0])
        self.latest_potd = int(potd_row[0])
        self.update_ratings()
        self.to_send = self.generate_source(potd_row)
        self.listening_in_channel = ctx.channel.id
        self.late = True
        # In case Paradox unresponsive
        self.timer = threading.Timer(20, self.reset)
        self.timer.start()

    @commands.command(aliases=['rate'], brief='Rates a potd based on difficulty. ')
    async def potd_rate(self, ctx, potd: int, rating: int, overwrite: bool = False):
        if potd > self.latest_potd:  # Sanitise potd number
            await ctx.author.send('You cannot rate an un-released potd!')
            return

        # Delete messages if it's in a guild
        if ctx.guild is not None:
            await ctx.message.delete()

        cursor = cfg.db.cursor()
        cursor.execute(f'SELECT * FROM ratings where prob = {potd} and userid = {ctx.author.id} LIMIT 1')
        result = cursor.fetchone()
        # print(result)
        if result is None:
            sql = 'INSERT INTO ratings (prob, userid, rating) VALUES (?, ?, ?)'
            cursor.execute(sql, (potd, ctx.author.id, rating))
            cfg.db.commit()
            await ctx.author.send(f'You just rated potd {potd} {rating}. Thank you! ')
        else:
            if not overwrite:
                await ctx.author.send(
                    f'You already rated this potd {result[3]}. '
                    f'If you wish to overwrite append `True` to your previous message, like `-rate {potd} {rating} True` ')
            else:
                cursor.execute(f'UPDATE ratings SET rating = {rating} WHERE idratings = {result[0]}')
                cfg.db.commit()
                await ctx.author.send(f'Changed your rating for potd {potd} from {result[3]} to {rating}')

    @commands.command(aliases=['rating'], brief='Finds the median of a potd\'s ratings')
    async def potd_rating(self, ctx, potd: int, full: bool = False):
        cursor = cfg.db.cursor()
        cursor.execute(f'SELECT * FROM ratings WHERE prob = {potd}')
        result = cursor.fetchall()
        if len(result) == 0:
            await ctx.author.send(f'No ratings for potd {potd} yet. ')
        else:
            median = statistics.median([row[3] for row in result])
            await ctx.author.send(f'Rating for potd {potd} is `{median}`. ')
            if full:
                await ctx.author.send(f'Full list: {[row[3] for row in result]}')
        await ctx.message.delete()

    @commands.command(aliases=['myrating'], brief='Checks your rating of a potd. ')
    async def potd_rating_self(self, ctx, potd: int):
        cursor = cfg.db.cursor()
        cursor.execute(f'SELECT * FROM ratings WHERE prob = {potd} AND userid = {ctx.author.id}')
        result = cursor.fetchone()
        if result is None:
            await ctx.author.send(f'You have not rated potd {potd}. ')
        else:
            await ctx.author.send(f'You have rated potd {potd} as difficulty level {result[3]}')

    @commands.command(aliases=['myratings'], brief='Checks all your ratings. ')
    async def potd_rating_all(self, ctx):
        cursor = cfg.db.cursor()
        cursor.execute(f'SELECT * FROM ratings WHERE userid = {ctx.author.id}')
        result = cursor.fetchall()
        if len(result) == 0:
            await ctx.author.send('You have not rated any problems!')
        else:
            ratings = '\n'.join([f'{i[1]:<6}{i[3]}' for i in result])
            await ctx.author.send(f'Your ratings: ```Potd  Rating\n{ratings}```You have rated {len(result)} potds. ')

    @commands.command(aliases=['rmrating', 'unrate'], brief='Removes your rating for a potd. ')
    async def potd_rating_remove(self, ctx, potd: int):
        cursor = cfg.db.cursor()
        cursor.execute(f'SELECT * FROM ratings WHERE prob = {potd} AND userid = {ctx.author.id}')
        result = cursor.fetchone()
        if result is None:
            await ctx.author.send(f'You have not rated potd {potd}. ')
        else:
            cursor.execute(f'DELETE FROM ratings WHERE prob = {potd} AND userid = {ctx.author.id}')
            await ctx.author.send(f'Removed your rating of difficulty level {result[3]} for potd {potd}. ')

    def potd_notif_embed(self, ctx):
        cursor = cfg.db.cursor()
        cursor.execute(f'SELECT * FROM potd_ping WHERE user_id = {ctx.author.id}')
        result = cursor.fetchone()
        if result == None:
            return None
        msg = discord.Embed()
        if ctx.author.nick == None:
            msg.add_field(name='Username', value=ctx.author.name)
        else:
            msg.add_field(name='Nickname', value=ctx.author.nick)
        msg.add_field(name='Categories', value=result[1])
        msg.add_field(name='Difficulty', value=f'{str(result[2])}-{str(result[3])}')
        return msg

    @commands.command(aliases=['pn'], brief='Customizes potd pings. ')
    async def potd_notif(self, ctx, *criteria:str):

        # Empty criteria
        cursor = cfg.db.cursor()
        criteria = list(criteria)
        if len(criteria) == 0:
            cursor.execute(f"SELECT * FROM potd_ping WHERE user_id = '{ctx.author.id}'")
            result = cursor.fetchone()
            if result == None:
                cursor.execute(f'''INSERT INTO potd_ping (user_id, categories, min, max)
                    VALUES('{ctx.author.id}', 'ACGN', 1, 12)''')
                cfg.db.commit()
                await ctx.send('You will now receive POTD notifications. Use `-pn off` to turn this off. ', embed=self.potd_notif_embed(ctx))
            else:
                await ctx.send('Here are your POTD notification settings: ', embed=self.potd_notif_embed(ctx))
            return

        # Turn off ping
        if criteria[0].lower() in {'clear', 'delete', 'remove', 'off', 'false', 'reset'}:
            cursor.execute(f"DELETE FROM potd_ping WHERE user_id = '{ctx.author.id}'")
            cfg.db.commit()
            await ctx.send('Your POTD notifications have been turned off. ')
            return

        # Run criteria
        cursor.execute(f"SELECT * FROM potd_ping WHERE user_id = '{ctx.author.id}'")
        result = cursor.fetchone()
        if result == None:
            cursor.execute(f'''INSERT INTO potd_ping (user_id, categories, min, max)
                VALUES('{ctx.author.id}', 'ACGN', 0, 12)''')

        categories = ''
        for category in 'ACGN':
            if category in criteria[0].upper():
                categories += category
        if categories != '':
            cursor.execute(f"UPDATE potd_ping SET categories = '{categories}'")
            criteria.pop(0)

        if len(criteria) > 0:
            try:
                max = int(criteria.pop())
                min = int(criteria.pop())
            except Exception:
                cfg.db.rollback()
                await ctx.send('Check your input! ')
                return
            if (min < 0) or (min > 12) or (max < 0) or (max > 12) or (min > max):
                cfg.db.rollback()
                await ctx.send('Check your input! ')
                return
            cursor.execute(f"UPDATE potd_ping SET min = {min}, max = {max}")

        if len(criteria) > 0:
            cfg.db.rollback()
            await ctx.send('Check your input! ')
            return

        cfg.db.commit()
        await ctx.send('Your POTD notification settings have been updated: ', embed=self.potd_notif_embed(ctx))

    @commands.command()
    @commands.check(cfg.is_staff)
    async def enable_potd_dm(self, ctx, status:bool=None):
        if status == None:
            self.enable_dm = not self.enable_dm
        else:
            self.enable_dm = status
        cursor = cfg.db.cursor()
        cursor.execute(f"UPDATE settings SET value = '{str(self.enable_dm)}' WHERE setting = 'potd_dm'")
        cfg.db.commit()
        await ctx.guild.get_channel(cfg.Config.config['log_channel']).send(
            f'**POTD notifications set to `{self.enable_dm}` by {ctx.author.mention}**')


def setup(bot):
    bot.add_cog(Potd(bot))
