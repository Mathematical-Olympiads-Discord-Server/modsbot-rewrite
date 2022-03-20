import ast
import statistics
from datetime import datetime, timedelta

import discord
import schedule
import threading
from discord.ext import commands

from cogs import config as cfg

Cog = commands.Cog

POTD_RANGE = 'History!A2:M'
CURATOR_RANGE = 'Curators!A3:E'

days = [None, 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']


def is_pc(ctx):
    return cfg.Config.config['problem_curator_role'] in [x.id for x in ctx.author.roles]

async def dm_or_channel(user: discord.User, channel: discord.abc.Messageable, content='', *args, **kargs):
    try:
        if user is not None and not user.bot:
            await user.send(*args, content=content, **kargs)
    except discord.Forbidden:
        await channel.send(*args, content=user.mention+'\n'+content, **kargs)


class Potd(Cog):

    def __init__(self, bot: commands.Bot):

        self.listening_in_channel = -1
        self.to_send = ''
        self.bot = bot
        self.ping_daily = False
        self.late = False
        self.requested_number = -1
        self.dm_list = []
        self.timer = None
        
        cursor = cfg.db.cursor()
        cursor.execute('''INSERT OR IGNORE INTO settings (setting, value) VALUES
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

    @commands.command()
    @commands.check(is_pc)
    async def reset_potd(self, ctx=None):
        self.requested_number = -1
        self.listening_in_channel = -1
        self.to_send = ''
        self.late = False
        self.ping_daily = False
        self.dm_list = []
        try:
            self.timer.cancel()
        except Exception:
            pass
        self.timer = None

    def reset_if_necessary(self):
        if self.listening_in_channel != -1:
            self.reset_potd()

    def prepare_dms(self, potd_row):
        def should_dm(x):
            for i in range(4):
                if (['a', 'c', 'g', 'n'][i] in potd_row[5].lower()) and not (x[1][4*i] == 'x'):
                    if int(x[1][4*i:4*i+2]) <= d <= int(x[1][4*i+2:4*i+4]):
                        return True
            return False

        try:
            d = int(potd_row[6])
        except Exception:
            return

        cursor = cfg.db.cursor()
        cursor.execute("SELECT * FROM potd_ping2")
        result = cursor.fetchall()
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
        source.add_field(name='Subscribed', value=f'`{str(len(self.dm_list)).ljust(5)}`')
        source.set_footer(text=f'Use -rating {potd_row[0]} to check the community difficulty rating of this problem '
                            f'or -rate {potd_row[0]} rating to rate it yourself. React with a 👍 if you liked '
                            f'the problem. ')

        return source

    def schedule_potd(self):
        self.bot.loop.create_task(self.check_potd())

    def responsible(self, potd_id:int, urgent:bool=False):     # Mentions of responsible curators

        # Get stuff from the sheet (API call)
        potds = cfg.Config.service.spreadsheets().values().get(spreadsheetId=cfg.Config.config['potd_sheet'],
                                                               range=POTD_RANGE).execute().get('values', [])
        curators = cfg.Config.service.spreadsheets().values().get(spreadsheetId=cfg.Config.config['potd_sheet'],
                                                               range=CURATOR_RANGE).execute().get('values', [])
        try:
            i = int(potds[0][0]) - int(potd_id)
        except Exception:
            return 'Invalid entry (A2) in spreadsheet. '
        potd_row = potds[i]

        # Searches for relevant curators
        mentions = ''
        r_list = []
        try:
            day = str(days.index(str(potd_row[2])))
        except Exception:
            return 'Day not recognized. '
        for curator in curators:
            try:
                if (curator[4] == day) or (curator[4] == 'back-up'):
                    mentions += f'<@{curator[0]}> '
                    if curator[4] != 'back-up':
                        r_list.append(curator)
            except Exception:
                pass
        if urgent or (len(r_list) == 0):
            return mentions

        # Searches for curator whose last curation on this day of the week was longest ago.
        i += 7
        while (i < len(potds)) and (len(r_list) > 1):
            try:
                for curator in r_list:
                    if curator[2] == potds[i][3]:
                        r_list.remove(curator)
            except Exception:
                pass
            i += 7
        return f'<@{r_list[0][0]}> '

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
        current_potd = int(values[0][0])  # this will be the top left cell which indicates the latest added potd
        potd_row = values[current_potd - number]  # this gets the row requested

        # Create the message to send
        to_tex = ''
        try:
            to_tex = '```tex\n \\textbf{Day ' + str(number) + '} --- ' + str(potd_row[2]) + ' ' + str(
                potd_row[1]) + '\\vspace{11pt}\\\\' + str(potd_row[8]) + '```'
        except IndexError:
            await ctx.send("There is no potd for day {}. ".format(number))
            return
        print(to_tex)

        # Finish up
        self.requested_number = int(potd_row[0])
        self.latest_potd = int(potd_row[0])
        self.update_ratings()
        self.to_send = self.generate_source(potd_row)
        self.listening_in_channel = ctx.channel.id
        self.late = True
        await ctx.send(to_tex, delete_after=20)

    async def check_potd(self):

        # Get the potds from the sheet (API call)
        potds = cfg.Config.service.spreadsheets().values().get(spreadsheetId=cfg.Config.config['potd_sheet'],
                                                               range=POTD_RANGE).execute().get('values', [])

        # Check today's potd
        date = datetime.now().strftime("%d %b %Y")
        soon = [(datetime.now() + timedelta(days = i)).strftime("%d %b %Y") for i in range(1, 4)]
        if date[0] == '0':
            date = date[1:]
        for i in range(3):
            if soon[i][0] == '0':
                soon[i] = soon[i][1:]
        passed_current = False
        potd_row = None
        fail = False
        remind = []
        for potd in potds:
            if passed_current:
                if len(potd) < 8:  # Then there has not been a potd on that day.
                    fail = True
                    await self.bot.get_channel(cfg.Config.config['helper_lounge']).send(
                        f"There was no potd on {potd[1]}! {self.responsible(int(potd[0]), True)}")
            if potd[1] == date:
                passed_current = True
                potd_row = potd
                if len(potd) < 8:  # There is no potd.
                    fail = True
                    await self.bot.get_channel(cfg.Config.config['helper_lounge']).send(
                        f"There is no potd today! {self.responsible(int(potd[0]), True)}")
            if potd[1] in soon:
                if len(potd) < 8:  # Then there is no potd on that day.
                    remind.append(int(potd[0]))
                soon.remove(potd[1])
        if soon != []:
            await self.bot.get_channel(cfg.Config.config['helper_lounge']).send(
                f"Insufficient rows in the potd sheet! {self.responsible(int(potd_row[0]))}")
        if remind != []:
            mentions = ''
            for i in remind:
                mentions += self.responsible(i)
            await self.bot.get_channel(cfg.Config.config['helper_lounge']).send(
                f"Remember to fill in your POTDs! {mentions}")
        if fail:
            return

        print('l123')
        # Otherwise, everything has passed and we are good to go.
        # Create the message to send
        to_tex = '```tex\n\\textbf{Day ' + str(potd_row[0]) + '} --- ' + str(potd_row[2]) + ' ' + str(
            potd_row[1]) + '\\vspace{11pt}\\\\' + str(potd_row[8]) + '```'
        print(to_tex)

        # Finish up
        self.requested_number = int(potd_row[0])
        self.latest_potd = int(potd_row[0])
        self.update_ratings()
        self.prepare_dms(potd_row)
        self.to_send = self.generate_source(potd_row)
        self.listening_in_channel = cfg.Config.config['potd_channel']
        self.ping_daily = True
        await self.bot.get_channel(cfg.Config.config['potd_channel']).send(to_tex, delete_after=20)
        print('l149')
        # In case Paradox unresponsive
        self.timer = threading.Timer(20, self.reset_if_necessary)
        self.timer.start()

    @Cog.listener()
    async def on_message(self, message: discord.Message):
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

            ping_msg = None
            if self.ping_daily:
                r = self.bot.get_guild(cfg.Config.config['mods_guild']).get_role(cfg.Config.config['potd_role'])
                await r.edit(mentionable=True)
                ping_msg = await message.channel.send('<@&{}>'.format(cfg.Config.config['potd_role']))
                await r.edit(mentionable=False)

                if self.enable_dm:

                    bot_spam = self.bot.get_channel(cfg.Config.config['bot_spam_channel'])
                    potd_discussion_channel = self.bot.get_channel(cfg.Config.config['potd_discussion_channel'])
                    helper_lounge = self.bot.get_channel(cfg.Config.config['helper_lounge'])

                    ping_embed = discord.Embed(title=f'POTD {self.latest_potd} has been posted: ',
                        description=f'{potd_discussion_channel.mention}\n{message.jump_url}', colour=0xDCDCDC)
                    for field in self.to_send.to_dict()['fields']:
                        ping_embed.add_field(name=field['name'], value=field['value'])
                    if message.attachments == []:
                        await helper_lounge.send('No attachments found! ')
                    else:
                        ping_embed.set_image(url=message.attachments[0].url)
                        dm_failed = []
                        for id in self.dm_list:
                            member = self.bot.get_guild(cfg.Config.config['mods_guild']).get_member(int(id))
                            try:
                                await member.send(embed=ping_embed)
                            except discord.Forbidden:
                                dm_failed.append(id)
                        if dm_failed != []:
                            msg = 'Remember to turn on DMs from this server to get private notifications! '
                            for id in dm_failed: msg += f'<@{id}> '
                            await bot_spam.send(msg, embed=ping_embed)

            try:
                await message.publish()
                await source_msg.publish()
            except Exception:
                pass

            cursor = cfg.db.cursor()
            if ping_msg == None:
                cursor.execute(f'''INSERT INTO potd_info (potd_id, problem_msg_id, source_msg_id, ping_msg_id) VALUES
                    ('{self.latest_potd}', '{message.id}', '{source_msg.id}', '')''')
            else:
                cursor.execute(f'''INSERT INTO potd_info (potd_id, problem_msg_id, source_msg_id, ping_msg_id) VALUES
                    ('{self.latest_potd}', '{message.id}', '{source_msg.id}', '{ping_msg.id}')''')
            cfg.db.commit()

            await self.reset_potd()

    @commands.command(aliases=['potd'], brief='Displays the potd with the provided number. ')
    @commands.check(is_pc)
    async def potd_display(self, ctx, number: int):

        # It can only handle one at a time!
        if not self.listening_in_channel == -1:
            await dm_or_channel(ctx.author, self.bot.get_channel(cfg.Config.config['helper_lounge']),
                "Please wait until the previous call has finished!")
            return

        reply = cfg.Config.service.spreadsheets().values().get(spreadsheetId=cfg.Config.config['potd_sheet'],
                                                               range=POTD_RANGE).execute()
        values = reply.get('values', [])
        current_potd = int(values[0][0])  # this will be the top left cell which indicates the latest added potd
        potd_row = values[current_potd - number]  # this gets the row requested

        # Create the message to send
        to_tex = ''
        try:
            to_tex = '```tex\n\\textbf{Day ' + str(potd_row[0]) + '} --- ' + str(potd_row[2]) + ' ' + str(
                potd_row[1]) + '\\vspace{11pt}\\\\' + str(potd_row[8]) + '```'
        except IndexError:
            await dm_or_channel(ctx.author, self.bot.get_channel(cfg.Config.config['helper_lounge']),
                f"There is no potd for day {number}. ")
            return
        print(to_tex)

        # Finish up
        self.requested_number = int(potd_row[0])
        self.latest_potd = int(potd_row[0])
        self.update_ratings()
        self.prepare_dms(potd_row)
        self.to_send = self.generate_source(potd_row)
        self.listening_in_channel = ctx.channel.id
        self.late = True
        self.ping_daily = False
        await ctx.send(to_tex, delete_after=20)
        # In case Paradox unresponsive
        self.timer = threading.Timer(20, self.reset_if_necessary)
        self.timer.start()

    @commands.command(aliases=['remove_potd'], brief='Deletes the potd with the provided number. ')
    @commands.check(is_pc)
    async def delete_potd(self, ctx, number: int):
        
        # It can only handle one at a time!
        if not self.listening_in_channel in [-1, -2]:
            await dm_or_channel(ctx.author, self.bot.get_channel(cfg.Config.config['helper_lounge']),
                "Please wait until the previous call has finished!")
            return
        self.listening_in_channel = 0
        
        # Delete old POTD
        cursor = cfg.db.cursor()
        cursor.execute(f"SELECT problem_msg_id, source_msg_id, ping_msg_id FROM potd_info WHERE potd_id = '{number}'")
        result = cursor.fetchall()
        cursor.execute(f"DELETE FROM potd_info WHERE potd_id = '{number}'")
        cfg.db.commit()
        for i in result:
            for j in i:
                try:
                    await self.bot.get_channel(cfg.Config.config['potd_channel']).get_partial_message(int(j)).delete()
                except Exception:
                    pass
        self.listening_in_channel = -1

    @commands.command(aliases=['update_potd'], brief='Replaces the potd with the provided number. ')
    @commands.check(is_pc)
    async def replace_potd(self, ctx, number: int):
        
        # It can only handle one at a time!
        if not self.listening_in_channel == -1:
            await dm_or_channel(ctx.author, self.bot.get_channel(cfg.Config.config['helper_lounge']),
                "Please wait until the previous call has finished!")
            return

        await self.delete_potd(ctx, number)
        await self.potd_display(ctx, number)

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

    def potd_notif_embed(self, ctx, colour):

        result = None
        def subcriteria(a):
            if result[1][a] == 'x':
                return 'Off'
            else:
                return f'D{int(result[1][a:a+2])}-{int(result[1][a+2:a+4])}'

        cursor = cfg.db.cursor()
        cursor.execute(f'SELECT * FROM potd_ping2 WHERE user_id = {ctx.author.id}')
        result = cursor.fetchone()
        if result == None:
            return None
        embed = discord.Embed(colour=colour)
        try:
            if ctx.author.nick == None:
                embed.add_field(name='Username', value=ctx.author.name)
            else:
                embed.add_field(name='Nickname', value=ctx.author.nick)
        except Exception:
            embed.add_field(name='Username', value=ctx.author.name)
        for i in range(4):
            embed.add_field(name=['Algebra', 'Combinatorics', 'Geometry', 'Number Theory'][i], value=subcriteria(4*i))
        embed.set_footer(text='Use `-pn off` to turn this off. ')
        return embed

    @commands.command(aliases=['pn'], brief='Customizes potd pings. ')
    async def potd_notif(self, ctx, *criteria:str):

        # Empty criteria
        cursor = cfg.db.cursor()
        criteria = list(criteria)
        if len(criteria) == 0:
            cursor.execute(f"SELECT * FROM potd_ping2 WHERE user_id = '{ctx.author.id}'")
            result = cursor.fetchone()
            if result == None:
                cursor.execute(f'''INSERT INTO potd_ping2 (user_id, criteria)
                    VALUES('{ctx.author.id}', '0 120 120 120 12')''')
                cfg.db.commit()
                await ctx.send('Your POTD notification settings have been updated: ', embed=self.potd_notif_embed(ctx, 0x5FE36A))
            else:
                await ctx.send('Here are your POTD notification settings: ', embed=self.potd_notif_embed(ctx, 0xDCDCDC))
            return

        # Turn off ping
        if criteria[0].lower() == 'off':
            cursor.execute(f"DELETE FROM potd_ping2 WHERE user_id = '{ctx.author.id}'")
            cfg.db.commit()
            await ctx.send('Your POTD notifications have been turned off. ')
            return

        # Run criteria
        cursor.execute(f"SELECT * FROM potd_ping2 WHERE user_id = '{ctx.author.id}'")
        result = cursor.fetchone()
        if result == None:
            cursor.execute(f'''INSERT INTO potd_ping2 (user_id, criteria)
                VALUES('{ctx.author.id}', 'xxxxxxxxxxxxxxxx')''')
            cursor.execute(f"SELECT * FROM potd_ping2 WHERE user_id = '{ctx.author.id}'")
            result = cursor.fetchone()
        result = list(result)

        temp = "".join(criteria).lower()
        criteria = [temp[0]]
        for i in temp[1:]:
            if i in ['a', 'c', 'g', 'n']:
                criteria.append(i)
            else:
                criteria[len(criteria)-1] += i
        
        # Difficulty only
        if len(criteria) == 1:
            temp = criteria[0].split('-')
            if len(temp) == 2:
                try:
                    min = int(temp[0])
                    max = int(temp[1])
                    if (0 <= min <= max <= 12):
                        if result[1] == 'xxxxxxxxxxxxxxxx':
                            result[1] = '                '
                        temp = ''
                        for i in range(4):
                            if result[1][4*i] == 'x':
                                temp += 'xxxx'
                            else:
                                temp += str(min).ljust(2) + str(max).ljust(2)
                        cursor.execute(f"UPDATE potd_ping2 SET criteria = '{temp}' WHERE user_id = '{ctx.author.id}'")
                        cfg.db.commit()
                        await ctx.send('Your POTD notification settings have been updated: ', embed=self.potd_notif_embed(ctx, 0x5FE36A))
                        return
                    else:
                        cfg.db.rollback()
                        await ctx.send(f'`{criteria[0]}` Invalid difficulty range! ')
                        return
                except ValueError:
                    pass

        remaining = ['a', 'c', 'g', 'n']
        for i in criteria:
            if i in remaining:
                # Category without difficulty
                remaining.remove(i)
                index = ['a', 'c', 'g', 'n'].index(i[0])
                if result[1][4*index] == 'x':
                    result[1] = result[1][:4*index] + '0 12' + result[1][4*index+4:]
                else:
                    result[1] = result[1][:4*index] + 'xxxx' + result[1][4*index+4:]
            else:
                # Category with difficulty
                criterion = i[1:].split('-')
                if (i[0] not in remaining) or (len(criterion) != 2):
                    cfg.db.rollback()
                    await ctx.send(f'`{i}` Invalid input format! ')
                    return
                try:
                    min = int(criterion[0])
                    max = int(criterion[1])
                    if not (0 <= min <= max <= 12):
                        cfg.db.rollback()
                        await ctx.send(f'`{i}` Invalid difficulty range! ')
                        return
                except ValueError:
                    cfg.db.rollback()
                    await ctx.send(f'`{i}` Invalid input format! ')
                    return
                remaining.remove(i[0])
                index = ['a', 'c', 'g', 'n'].index(i[0])
                result[1] = f'{result[1][:4*index]}{str(min).ljust(2)}{str(max).ljust(2)}{result[1][4*index+4:]}'

        cursor.execute(f"UPDATE potd_ping2 SET criteria = '{result[1]}' WHERE user_id = '{ctx.author.id}'")
        cfg.db.commit()
        await ctx.send('Your POTD notification settings have been updated: ', embed=self.potd_notif_embed(ctx, 0x5FE36A))

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
        await self.bot.get_channel(cfg.Config.config['log_channel']).send(
            f'**POTD notifications set to `{self.enable_dm}` by {ctx.author.nick} ({ctx.author.id})**')


def setup(bot):
    bot.add_cog(Potd(bot))
