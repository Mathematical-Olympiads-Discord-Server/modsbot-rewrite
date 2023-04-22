import ast
from functools import reduce
import math
import random
import statistics
from datetime import datetime, timedelta

import discord
import schedule
import threading
from discord.ext import commands
from discord.ext.commands import BucketType

from cogs import config as cfg

Cog = commands.Cog

POTD_RANGE = 'POTD!A2:M'
CURATOR_RANGE = 'Curators!A3:E'

days = [None, 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']


def is_pc(ctx):
    if ctx.guild is None:
        return False
    return cfg.Config.config['problem_curator_role'] in [x.id for x in ctx.author.roles]

async def dm_or_channel(user: discord.User, channel: discord.abc.Messageable, content='', *args, **kargs):
    try:
        if user is not None and not user.bot:
            await user.send(*args, content=content, **kargs)
    except Exception:
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
        schedule.every().day.at("09:00").do(lambda: self.schedule_potd(1)).tag('cogs.potd')
        schedule.every().day.at("07:00").do(lambda: self.schedule_potd(3)).tag('cogs.potd')
        schedule.every().day.at("04:00").do(lambda: self.schedule_potd(6)).tag('cogs.potd')
        schedule.every().day.at("22:00").do(lambda: self.schedule_potd(12)).tag('cogs.potd')


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
            self.bot.loop.create_task(self.reset_potd())

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

    def curator_id(self, curators, value):
        value = str(value)
        if value == '':
            return None
        for i in curators:
            for j in range(min(len(i), 4)):
                if value == str(i[j]):
                    return i[0]
        return None

    def generate_source(self, potd_row):
        # Figure out whose potd it is
        curators = cfg.Config.service.spreadsheets().values().get(spreadsheetId=cfg.Config.config['potd_sheet'],
                                                               range=CURATOR_RANGE).execute().get('values', [])
        curator_id = self.curator_id(curators, potd_row[3])
        if curator_id is None:
            curator = 'Unknown Curator'
        else:
            curator = f'<@!{curator_id}>'
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

    def schedule_potd(self, mode=None):
        self.bot.loop.create_task(self.check_potd(mode))

    def responsible(self, potd_id:int, urgent:bool=False):     # Mentions of responsible curators

        # Get stuff from the sheet (API call)
        potds = cfg.Config.service.spreadsheets().values().get(spreadsheetId=cfg.Config.config['potd_sheet'],
                                                               range=POTD_RANGE).execute().get('values', [])
        curators = cfg.Config.service.spreadsheets().values().get(spreadsheetId=cfg.Config.config['potd_sheet'],
                                                               range=CURATOR_RANGE).execute().get('values', [])
        try:
            i = int(potds[0][0]) - int(potd_id)
        except Exception:
            return 'Invalid entry (A2) in spreadsheet! '
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
                if (curator[4] == day):
                    mentions += f'<@{curator[0]}> '
                    r_list.append(curator)
            except Exception:
                pass
        if urgent:
            return mentions + f'<@&{cfg.Config.config["problem_curator_role"]}> '
        if mentions == '':
            return f'No responsible curators found for the potd on {potd_row[1]}!'

        # Searches for curator whose last curation on this day of the week was longest ago.
        i += 7
        while (i < len(potds)) and (len(r_list) > 1):
            try:
                for curator in r_list:
                    if curator[0] == self.curator_id(curators, potds[i][3]):
                        r_list.remove(curator)
            except Exception:
                pass
            i += 7
        return f'<@{r_list[0][0]}> '

    async def potd_embedded(self, ctx, *, number: int):
        # It can only handle one at a time!
        if self.listening_in_channel != -1:
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
            to_tex = '<@419356082981568522>\n```tex\n \\textbf{Day ' + str(number) + '} --- ' + str(potd_row[2]) + ' ' + str(
                potd_row[1]) + '\\vspace{11pt}\\\\\\setlength\\parindent{1.5em}' + str(potd_row[8]) + '```'
        except IndexError:
            await ctx.send("There is no potd for day {}. ".format(number))
            return
        print(to_tex)

        # Finish up
        self.requested_number = int(potd_row[0])
        self.latest_potd = int(potd_row[0])
        self.to_send = self.generate_source(potd_row)
        self.listening_in_channel = ctx.channel.id
        self.late = True
        await ctx.send(to_tex, delete_after=20)

    async def check_potd(self, mode=None):

        # Get the potds from the sheet (API call)
        potds = cfg.Config.service.spreadsheets().values().get(spreadsheetId=cfg.Config.config['potd_sheet'],
                                                               range=POTD_RANGE).execute().get('values', [])

        # Check today's potd
        if mode is None:
            next = datetime.now()
            date = next.strftime("%d %b %Y")
            soon = [(next + timedelta(days = i)).strftime("%d %b %Y") for i in range(1, 4)]
        else:
            next = datetime.now() + timedelta(hours = mode)
            date = next.strftime("%d %b %Y")
            soon = [date]
        if date[0] == '0':
            date = date[1:]
        for i in range(len(soon)):
            if soon[i][0] == '0':
                soon[i] = soon[i][1:]
        passed_current = False
        potd_row = None
        fail = False
        remind = []
        curator_role = (await self.bot.fetch_guild(cfg.Config.config['mods_guild'])).get_role(cfg.Config.config['problem_curator_role'])
        j = 1                   # TESTING
        for potd in potds:
            j += 1              # TESTING
            if len(potd) < 2:   # TESTING
                await self.bot.get_channel(cfg.Config.config['log_channel']).send(
                        f"Invalid entry at row {j}, potd = {potd}")
                pass
            if passed_current:
                if len(potd) < 8:  # Then there has not been a potd on that day.
                    fail = True
                    await curator_role.edit(mentionable = True)
                    await self.bot.get_channel(cfg.Config.config['helper_lounge']).send(
                        f"There was no potd on {potd[1]}! {self.responsible(int(potd[0]), True)}")
                    await curator_role.edit(mentionable = False)
            if potd[1] == date:
                passed_current = True
                potd_row = potd
                if len(potd) < 8 and (mode is None):  # There is no potd.
                    fail = True
                    await curator_role.edit(mentionable = True)
                    await self.bot.get_channel(cfg.Config.config['helper_lounge']).send(
                        f"There is no potd today! {self.responsible(int(potd[0]), True)}")
                    await curator_role.edit(mentionable = False)
            if potd[1] in soon:
                if len(potd) < 8:  # Then there is no potd on that day.
                    remind.append(int(potd[0]))
                soon.remove(potd[1])
        if soon != []:
            await self.bot.get_channel(cfg.Config.config['helper_lounge']).send(
                f"Insufficient rows in the potd sheet! ")
        if remind != []:
            mentions = ''
            for i in remind:
                mentions += self.responsible(i, mode == 1)
            await curator_role.edit(mentionable = True)
            await self.bot.get_channel(cfg.Config.config['helper_lounge']).send(
                f"Remember to fill in your POTDs! {mentions}")
            await curator_role.edit(mentionable = False)
        if fail or not (mode is None):
            return

        print('l123')
        # Otherwise, everything has passed and we are good to go.
        # Create the message to send
        to_tex = '<@419356082981568522>\n```tex\n\\textbf{Day ' + str(potd_row[0]) + '} --- ' + str(potd_row[2]) + ' ' + str(
            potd_row[1]) + '\\vspace{11pt}\\\\\\setlength\\parindent{1.5em}' + str(potd_row[8]) + '```'
        print(to_tex)

        # Finish up
        self.requested_number = int(potd_row[0])
        self.latest_potd = int(potd_row[0])
        self.prepare_dms(potd_row)
        self.to_send = self.generate_source(potd_row)
        self.listening_in_channel = cfg.Config.config['potd_channel']
        self.ping_daily = True
        self.late = False
        await self.bot.get_channel(cfg.Config.config['potd_channel']).send(to_tex, delete_after=20)
        await self.create_potd_forum_post(self.requested_number)
        print('l149')
        # In case Paradox unresponsive
        self.timer = threading.Timer(20, self.reset_if_necessary)
        self.timer.start()

    async def create_potd_forum_post(self, number):
        forum = self.bot.get_channel(cfg.Config.config['potd_forum'])
        await forum.create_thread(name=f"POTD {number}", content="potd")

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
            bot_log = self.bot.get_channel(cfg.Config.config['log_channel'])

            ping_msg = None
            if self.ping_daily:
                r = self.bot.get_guild(cfg.Config.config['mods_guild']).get_role(cfg.Config.config['potd_role'])
                await r.edit(mentionable=True)
                ping_msg = await message.channel.send('<@&{}>'.format(cfg.Config.config['potd_role']))
                await r.edit(mentionable=False)

                if self.enable_dm:

                    bot_spam = self.bot.get_channel(cfg.Config.config['bot_spam_channel'])
                    potd_discussion_channel = self.bot.get_channel(cfg.Config.config['potd_discussion_channel'])

                    ping_embed = discord.Embed(title=f'POTD {self.latest_potd} has been posted: ',
                        description=f'{potd_discussion_channel.mention}\n{message.jump_url}', colour=0xDCDCDC)
                    for field in self.to_send.to_dict()['fields']:
                        ping_embed.add_field(name=field['name'], value=field['value'])
                    if message.attachments == []:
                        await bot_log.send('No attachments found! ')
                    else:
                        ping_embed.set_image(url=message.attachments[0].url)
                        dm_failed = []
                        for id in self.dm_list:
                            user = self.bot.get_user(int(id))
                            try:
                                await user.send(embed=ping_embed)
                            except Exception:
                                dm_failed.append(id)
                        if dm_failed != []:
                            msg = 'Remember to turn on DMs from this server to get private notifications! '
                            for id in dm_failed: msg += f'<@{id}> '
                            await bot_spam.send(msg, embed=ping_embed)

            if message.channel.id == cfg.Config.config['potd_channel']:
                try:
                    await message.publish()
                    await source_msg.publish()
                except Exception:
                    await bot_log.send('Failed to publish!')

            cursor = cfg.db.cursor()
            if ping_msg is None:
                cursor.execute(f'''INSERT INTO potd_info (potd_id, problem_msg_id, source_msg_id, ping_msg_id) VALUES
                    ('{self.latest_potd}', '{message.id}', '{source_msg.id}', '')''')
            else:
                cursor.execute(f'''INSERT INTO potd_info (potd_id, problem_msg_id, source_msg_id, ping_msg_id) VALUES
                    ('{self.latest_potd}', '{message.id}', '{source_msg.id}', '{ping_msg.id}')''')
            cfg.db.commit()

            await self.reset_potd()
            await bot_log.send('POTD execution successful.')

    @commands.command(aliases=['potd'], brief='Displays the potd with the provided number. ')
    @commands.check(is_pc)
    async def potd_display(self, ctx, number: int):

        # It can only handle one at a time!
        if self.listening_in_channel != -1:
            await dm_or_channel(ctx.author, self.bot.get_channel(cfg.Config.config['helper_lounge']),
                "Please wait until the previous call has finished!")
            return

        # Read from the spreadsheet
        reply = cfg.Config.service.spreadsheets().values().get(spreadsheetId=cfg.Config.config['potd_sheet'],
                                                               range=POTD_RANGE).execute()
        values = reply.get('values', [])
        current_potd = int(values[0][0])  # this will be the top left cell which indicates the latest added potd
        potd_row = values[current_potd - number]  # this gets the row requested

        # Create the message to send
        to_tex = ''
        try:
            to_tex = '<@419356082981568522>\n```tex\n\\textbf{Day ' + str(potd_row[0]) + '} --- ' + str(potd_row[2]) + ' ' + str(
                potd_row[1]) + '\\vspace{11pt}\\\\\\setlength\\parindent{1.5em}' + str(potd_row[8]) + '```'
        except IndexError:
            await dm_or_channel(ctx.author, self.bot.get_channel(cfg.Config.config['helper_lounge']),
                f"There is no potd for day {number}. ")
            return
        print(to_tex)

        # Finish up
        self.requested_number = int(potd_row[0])
        self.latest_potd = int(potd_row[0])
        self.prepare_dms(potd_row)
        self.to_send = self.generate_source(potd_row)
        self.listening_in_channel = ctx.channel.id
        self.late = True
        self.ping_daily = False
        await ctx.send(to_tex, delete_after=20)
        # In case Paradox unresponsive
        self.timer = threading.Timer(20, self.reset_if_necessary)
        self.timer.start()

    @commands.command(aliases=['fetch'], brief='Fetch a potd by id.')
    @commands.cooldown(1, 10, BucketType.user)
    async def potd_fetch(self, ctx, number: int):
        sheet = self.get_potd_sheet()
        potd_row = self.get_potd_row(number, sheet)

        if potd_row == None:
            await ctx.send(f"There is no potd for day {number}. ")
            return
        else:
            # Create the message to send
            to_tex = ''
            try:
                to_tex = '<@' + str(cfg.Config.config['paradox_id']) + '>\n```tex\n\\textbf{Day ' + str(
                    potd_row[cfg.Config.config['potd_sheet_id_col']]) + '} --- ' + str(
                    potd_row[cfg.Config.config['potd_sheet_day_col']]) + ' ' + str(
                    potd_row[cfg.Config.config['potd_sheet_date_col']]) + '\\vspace{11pt}\\\\\\setlength\\parindent{1.5em}' + str(
                    potd_row[cfg.Config.config['potd_sheet_statement_col']]) + '```'
            except IndexError:
                await ctx.send(f"There is no potd for day {number}. ")
                return
            print(to_tex)
            
            # Send the problem tex
            await ctx.send(to_tex, delete_after=5)

    @commands.command(aliases=['source'], brief='Get the source of a potd by id.')
    @commands.cooldown(1, 10, BucketType.user)
    async def potd_source(self, ctx, number: int):
        sheet = self.get_potd_sheet()
        potd_row = self.get_potd_row(number, sheet)

        if potd_row == None:
            await ctx.send(f"There is no potd for day {number}. ")
            return
        else:
            source = self.generate_source(potd_row)
            await ctx.send(embed=source)

    @commands.command(aliases=['search'], brief='Search for a POTD by genre and difficulty.',
        help='`-search 4 6`: Search for a POTD with difficulty d4 to d6 (inclusive).\n'
            '`-search 4 6 C`: Search for a POTD with difficulty d4 to d6 and genres including combinatorics.\n'
            '`-search 4 6 CG`: Search for a POTD with difficulty d4 to d6 and genres including combinatorics or geometry.\n'
            '`-search 4 6 \'CG\'`: Search for a POTD with difficulty d4 to d6 and genres including (combinatorics AND geometry).\n'
            '`-search 4 6 A\'CG\'N`: Search for a POTD with difficulty d4 to d6 and genres including (algebra OR (combinatorics AND geometry) OR number theory).\n'
            '`-search 4 6 ACGN false`: Search for a POTD with difficulty d4 to d6. Allow getting problems marked in the `-solved` list.')
    @commands.cooldown(1, 10, BucketType.user)
    async def potd_search(self, ctx, diff_lower_bound:int, diff_upper_bound:int, genre:str='ACGN', search_unsolved:bool=True):
        if diff_lower_bound > diff_upper_bound:
            await ctx.send(f"Difficulty lower bound cannot be higher than upper bound.")
            return

        # Set up the genre filter
        genre_filter = self.parse_genre_input(genre)

        # set up the difficulty filter
        diff_lower_bound_filter = max(0,diff_lower_bound)
        diff_upper_bound_filter = max(min(99, diff_upper_bound), diff_lower_bound_filter)
        
        potds = cfg.Config.service.spreadsheets().values().get(spreadsheetId=cfg.Config.config['potd_sheet'],
                                                               range=POTD_RANGE).execute().get('values', [])
        picked_potd = self.pick_potd(diff_lower_bound_filter, diff_upper_bound_filter, genre_filter, potds, [], ctx, search_unsolved)
        if picked_potd is not None:
            # fetch the picked POTD
            await self.potd_fetch(ctx, int(picked_potd))
        else:
            await ctx.send(f"No POTD found!")

    def parse_genre_input(self, genre):
        complex_genres = genre.split("'")[1::2]
        simple_genres = "".join(genre.split("'")[0::2])

        genre_filter = []
        for character in simple_genres:
            if character.upper() == "A":
                genre_filter.append("A")
            if character.upper() == "C":
                genre_filter.append("C")
            if character.upper() == "G":
                genre_filter.append("G")
            if character.upper() == "N":
                genre_filter.append("N")

        for item in complex_genres:
            parsed_complex_genre = set()
            for character in item:
                if character.upper() == "A":
                    parsed_complex_genre.add("A")
                if character.upper() == "C":
                    parsed_complex_genre.add("C")
                if character.upper() == "G":
                    parsed_complex_genre.add("G")
                if character.upper() == "N":
                    parsed_complex_genre.add("N")
            parsed_complex_genre = "".join(parsed_complex_genre)
            genre_filter.append(parsed_complex_genre)

        return set(genre_filter)

    @commands.command(aliases=['mock'], brief='Create a mock paper using past POTDs.',
        help='`-mock IMO`: create mock IMO paper\n'
            '\n'
            'See below for a list of available templates and respective difficulty ranges\n'
            '(e.g. [5,7],[7,9],[9,11],[5,7],[7,9],[9,11] means problem 1 is d5-7, problem 2 is d7-9, etc.) \n'
            '\n'
            'IMO (International Mathematical Olympiad):\n'
            '[5,7],[7,9],[9,11],[5,7],[7,9],[9,11]\n'
            'AMO (Australian Mathematical Olympiad):\n'
            '[2,3],[3,4],[4,5],[5,6],[2,3],[3,4],[4,5],[5,6]\n'
            'APMO (Asian Pacific Mathematics Olympiad):\n'
            '[4,5],[5,6],[6,7],[7,8],[8,10]\n'
            'BMO1 (British Mathematical Olympiad Round 1):\n'
            '[1,2],[1,2],[2,3],[2,3],[3,4],[3,4]\n'
            'BMO2 (British Mathematical Olympiad Round 2):\n'
            '[3,4],[4,5],[5,6],[6,7]\n'
            'IGO (Iranian Geometry Olympiad):\n'
            '[5,6],[6,7],[7,8],[8,9],[9,10]\n'
            'NZMO2 (New Zealand Mathematical Olympiad Round 2):\n'
            '[1,2],[2,3],[3,4],[4,5],[5,6]\n'
            'SMO2 (Singapore Mathematical Olympiad Open Round 2):\n'
            '[4,5],[5,6],[6,7],[7,8],[8,9]\n'
            'USAMO (United States of America Mathematical Olympiad):\n'
            '[5,7],[7,9],[9,11],[5,7],[7,9],[9,11]\n'
            'USAJMO (United States of America Junior Mathematical Olympiad):\n'
            '[3,5],[5,7],[7,8],[3,5],[5,7],[7,8]\n'
            'CHINA (Crushingly Hard Imbalanced Nightmarish Assessment):\n'
            '[7,8],[8,10],[10,12],[7,8],[8,10],[10,12]')
    @commands.cooldown(1, 30, BucketType.user)
    async def potd_mock(self, ctx, template:str="IMO", search_unsolved:bool=True):
        template = template.upper()
        template_list = ["IMO", "AMO", "APMO", "BMO1", "BMO2", "IGO", "NZMO2", "SMO2", "USAMO", "USAJMO", "CHINA"]
        if template not in template_list and template != "AFMO":
            await ctx.send(f"Template not found. Possible templates: {', '.join(template_list)}. Use `-help potd_mock` for more details.")
            return
        else:
            if template == "IMO":
                difficulty_bounds = [[5,7],[7,9],[9,11],[5,7],[7,9],[9,11]]
            elif template == "AMO":
                difficulty_bounds = [[2,3],[3,4],[4,5],[5,6],[2,3],[3,4],[4,5],[5,6]]
            elif template == "APMO":
                difficulty_bounds = [[4,5],[5,6],[6,7],[7,8],[8,10]]
            elif template == "BMO1":
                difficulty_bounds = [[1,2],[1,2],[2,3],[2,3],[3,4],[3,4]]
            elif template == "BMO2":
                difficulty_bounds = [[3,4],[4,5],[5,6],[6,7]]         
            elif template == "IGO":
                difficulty_bounds = [[5,6],[6,7],[7,8],[8,9],[9,10]]
            elif template == "NZMO2":
                difficulty_bounds = [[1,2],[2,3],[3,4],[4,5],[5,6]]
            elif template == "SMO2":
                difficulty_bounds = [[4,5],[5,6],[6,7],[7,8],[8,9]]
            elif template == "USAMO":
                difficulty_bounds = [[5,7],[7,9],[9,11],[5,7],[7,9],[9,11]]
            elif template == "USAJMO":
                difficulty_bounds = [[3,5],[5,7],[7,8],[3,5],[5,7],[7,8]]
            elif template == "CHINA":
                difficulty_bounds = [[7,8],[8,10],[10,12],[7,8],[8,10],[10,12]]
            elif template == "AFMO": # easter egg
                difficulty_bounds = [[12,"T"],[12,"T"],[12,"T"],[13,"T"]]

        # SMO2 seems to have an unspoken rule to start with geometry at P1 and nowhere else
        if template == "SMO2":
            genre_rule = ["G","ACN","ACN","ACN","ACN"]
        elif template == "IGO":
            genre_rule = ["G","G","G","G","G"]
        else:
            genre_rule = ["ACGN"] * len(difficulty_bounds)

        genres=[]
        while not self.is_genre_legit(genres, template, difficulty_bounds, genre_rule):
            genres=list(map(lambda x: random.choice(x),genre_rule))

        problems_tex = []
        potds = cfg.Config.service.spreadsheets().values().get(spreadsheetId=cfg.Config.config['potd_sheet'],
                                                               range=POTD_RANGE).execute().get('values', [])
        already_picked = []

        # render the mock paper
        for i in range(0,len(difficulty_bounds)):
            picked_potd = self.pick_potd(difficulty_bounds[i][0], difficulty_bounds[i][1], genres[i], potds, already_picked, ctx, search_unsolved)
            already_picked.append(picked_potd)
            potd_statement = self.get_potd_statement(int(picked_potd), potds)
            problems_tex.append(f'\\textbf{{Problem {i+1}. (POTD {str(picked_potd)})}}\\\\ ' + potd_statement)
        
        if template in ["IMO","AMO","USAMO","USAJMO","CHINA"] : # 2-day contests
            if template in ["IMO","CHINA","USAMO","USAJMO"]:
                index_day1 = [0,1,2]
                index_day2 = [3,4,5]
            elif template in ["AMO"]:
                index_day1 = [0,1,2,3]
                index_day2 = [4,5,6,7]

            name_day1 = template + ' (Day 1)'
            problems_tex_day1 = [problems_tex[index] for index in index_day1]
            await self.send_out_mock(ctx, name_day1, problems_tex_day1)

            name_day2 = template + ' (Day 2)'
            problems_tex_day2 = [problems_tex[index] for index in index_day2]
            await self.send_out_mock(ctx, name_day2, problems_tex_day2)
        else: # 1-day contests
            await self.send_out_mock(ctx, template, problems_tex)

    async def send_out_mock(self, ctx, name, problems_tex):
        while len(problems_tex) > 0: # still has problems to send out
            title = r'\begin{center}\textbf{\textsf{MODSBot Mock ' + name + r'}}\end{center}'
            problems = ''
            while len(problems_tex) > 0 and len(problems + problems_tex[0]) < 1800 : # add problems one-by-one until no problems left or it's too long
                problems = problems + problems_tex.pop(0) + r'\\ \\'
            problems = problems[0:-5]
            to_tex = f'<@419356082981568522>\n```tex\n {title} {problems}```'
            await ctx.send(to_tex, delete_after=5) 

    def is_genre_legit(self, genres, template, difficulty_bounds, genre_rule):
        if len(genres) != len(difficulty_bounds):
            return False
        
        # the paper need to contain all genres listed in genre_rule
        for genre in set(reduce(lambda x, y: x+y, genre_rule)):
            if not genre in genres:
                return False

        # the selected genres need to match the genre_rule
        for i in range(0,len(genres)):
            if genres[i] not in genre_rule[i]:
                return False

        if template == "IMO":
            # P3 and P6 should be different genre
            if genres[2] == genres[5]: 
                return False
            
            # The three problems on each day should be different genre
            if len({genres[0],genres[1],genres[2]}) < 3:
                return False
            if len({genres[3],genres[4],genres[5]}) < 3:
                return False

            # Geoff Smith Rule
            genres_geoff_smith = [genres[index] for index in [0,1,3,4]]
            if not ("A" in genres_geoff_smith and "C" in genres_geoff_smith and "G" in genres_geoff_smith and "N" in genres_geoff_smith):
                return False

        return True

    def pick_potd(self, diff_lower_bound_filter, diff_upper_bound_filter, genre_filter, potds, already_picked, ctx, search_unsolved:bool):
        solved_potd = []
        if search_unsolved == True:
            solved_potd = self.get_potd_solved(ctx)

        def match_genre(x,genre_filter):
            for genre in genre_filter:
                if (len(set(x[cfg.Config.config['potd_sheet_genre_col']]).intersection(genre)) == len(genre)):
                    return True
            return False

        # filter by genre and difficulty
        if type(diff_upper_bound_filter) == int:
            filtered_potds = [x for x in potds if len(x) >= max(cfg.Config.config['potd_sheet_difficulty_col'], cfg.Config.config['potd_sheet_genre_col'])
                            and x[cfg.Config.config['potd_sheet_difficulty_col']].isnumeric()
                            and int(x[cfg.Config.config['potd_sheet_difficulty_col']]) >= diff_lower_bound_filter
                            and int(x[cfg.Config.config['potd_sheet_difficulty_col']]) <= diff_upper_bound_filter
                            and match_genre(x,genre_filter)]
        else: # if diff bound is "T"
            filtered_potds = [x for x in potds if len(x) >= max(cfg.Config.config['potd_sheet_difficulty_col'], cfg.Config.config['potd_sheet_genre_col'])
                            and ((x[cfg.Config.config['potd_sheet_difficulty_col']].isnumeric()
                                and int(x[cfg.Config.config['potd_sheet_difficulty_col']]) >= diff_lower_bound_filter)
                                or not x[cfg.Config.config['potd_sheet_difficulty_col']].isnumeric())
                            and match_genre(x,genre_filter)]


        # pick a POTD
        if len(filtered_potds) > 0:
            filtered_potds_id = list(map(lambda x: int(x[cfg.Config.config['potd_sheet_id_col']]), filtered_potds))
            unsolved_potds_id = [x for x in filtered_potds_id if x not in solved_potd if x not in already_picked]
            if len(unsolved_potds_id) > 0:
                picked_potd = int(random.choice(unsolved_potds_id))
            else:
                not_repeated_potds_id = [x for x in filtered_potds_id if x not in already_picked]
                if len(not_repeated_potds_id) > 0:
                    picked_potd = int(random.choice(not_repeated_potds_id))
                else:
                    picked_potd = int(random.choice(filtered_potds_id))
            return picked_potd
        else:
            return None

    def get_potd_statement(self, number:int, potds):
        current_potd = int(potds[0][0])  # this will be the top left cell which indicates the latest added potd

        if number > current_potd:
            return None

        potd_row = potds[current_potd - number]  # this gets the row requested

        # Create the tex
        potd_statement = ''
        try:
            potd_statement = potd_row[cfg.Config.config['potd_sheet_statement_col']]
            return potd_statement
        except IndexError:
            return None

    @commands.command(aliases=['mark'], brief='Mark the POTD you have solved')
    @commands.cooldown(1, 5, BucketType.user)
    async def potd_mark(self, ctx, *, user_input:str):
        # parse input
        try:
            potd_numbers = [int(i) for i in user_input.split(",")]
        except ValueError:
            await ctx.send("Error: The input contains non-integer values.")
            return

        if len(potd_numbers) > 30:
            await ctx.send("Please don't send more than 30 POTDs in each call.")
            return

        # insert to DB
        added = []
        already_solved = []
        no_potd = []
        no_hint = []
        sheet = self.get_potd_sheet()
        for potd_number in potd_numbers:
            cursor = cfg.db.cursor()
            cursor.execute(f'''SELECT discord_user_id, potd_id, create_date FROM potd_solves 
                                WHERE discord_user_id = {ctx.author.id} 
                                AND potd_id = {potd_number}''')
            result = cursor.fetchall()
            if len(result) > 0:
                already_solved.append(str(potd_number))
            else:
                cursor.execute(f'''INSERT INTO potd_solves (discord_user_id, potd_id, create_date) VALUES
                    ('{ctx.author.id}', '{potd_number}', '{datetime.now()}')''')
                added.append(str(potd_number))
            
            potd_row = self.get_potd_row(potd_number, sheet)
            if potd_row == None:
                no_potd.append(str(potd_number))
            else:
                if potd_row != None and random.random() <  0.25:
                    if len(potd_row) <= cfg.Config.config['potd_sheet_hint1_col'] or potd_row[cfg.Config.config['potd_sheet_hint1_col']] == None:
                        no_hint.append(str(potd_number))

        # send confirm message
        messages = []
        if len(added) != 0:
            if len(added) == 1:
                messages.append(f'POTD {added[0]} is added to your solved list.')
            else:
                messages.append(f'POTD {",".join(added)} are added to your solved list.')
        if len(already_solved) != 0:
            if len(already_solved) == 1:
                messages.append(f'POTD {already_solved[0]} is already in your solved list.')
            else:
                messages.append(f'POTD {",".join(already_solved)} are already in your solved list.')
        if len(no_potd) != 0:
            if len(no_potd) == 1:
                messages.append(f'There is no POTD {no_potd[0]}. Are you sure you have inputted the correct number?')
            else:
                messages.append(f'There are no POTD  {",".join(no_potd)}. Are you sure you have inputted the correct number?')
        if len(no_hint) != 0:
            if len(no_hint) == 1:
                messages.append(f"There is no hint for POTD {no_hint[0]}. Would you like to contribute one? Contact <@{cfg.Config.config['staffmail_id']}> to submit a hint!")
            else:
                messages.append(f"There are no hint for POTD {','.join(no_hint)}. Would you like to contribute one? Contact <@{cfg.Config.config['staffmail_id']}> to submit a hint!")
        message = "\n".join(messages)
        await ctx.send(message)

    @commands.command(aliases=['unmark'], brief='Unmark the POTD you have solved')
    @commands.cooldown(1, 5, BucketType.user)
    async def potd_unmark(self, ctx, *, user_input:str):
        # parse input
        try:
            potd_numbers = [int(i) for i in user_input.split(",")]
        except ValueError:
            await ctx.send("Error: The input contains non-integer values.")
            return

        if len(potd_numbers) > 30:
            await ctx.send("Please don't send more than 30 POTDs in each call.")
            return

        # delete from DB
        for potd_number in potd_numbers:
            cursor = cfg.db.cursor()
            cursor.execute(f'''DELETE FROM potd_solves 
                                WHERE discord_user_id = {ctx.author.id} AND potd_id = {potd_number}''')
        
        # send confirm message
        if len(potd_numbers) == 1:
            await ctx.send(f'POTD {potd_numbers[0]} is removed from your solved list. ')
        else:
            await ctx.send(f'POTD {",".join(list(map(str,potd_numbers)))} are removed from your solved list. ')

    @commands.command(aliases=['solved'], brief='Show the POTDs you have solved',
        help='`-solved`: Show the POTDs you have solved.\n'
            '`-solved d`: Show the POTDs you have solved, ordered by difficulties.\n'
            '`-solved s`: Show the POTDs you have solved, divided into the four subjects.\n')
    @commands.cooldown(1, 5, BucketType.user)
    async def potd_solved(self, ctx, flag=None):
        solved = self.get_potd_solved(ctx)
        
        potds = cfg.Config.service.spreadsheets().values().get(spreadsheetId=cfg.Config.config['potd_sheet'],
                                                               range=POTD_RANGE).execute().get('values', [])
        current_potd = int(potds[0][0])
        
        if flag == "d":
            solved_by_difficulty = {}
            for number in solved:
                if number > current_potd or number <= 0:
                    difficulty = "(Unknown)"
                else:
                    potd_row = potds[current_potd - number]
                    if len(potd_row) > cfg.Config.config['potd_sheet_difficulty_col']:
                        difficulty = potd_row[cfg.Config.config['potd_sheet_difficulty_col']]
                    else:
                        difficulty = "(Unknown)"

                if difficulty not in solved_by_difficulty:
                    solved_by_difficulty[difficulty] = []
                solved_by_difficulty[difficulty].append(number)            
            
            sorted_keys = sorted(solved_by_difficulty.keys(), key=lambda x: (x.isnumeric(),int(x) if x.isnumeric() else x), reverse=True)
            solved_by_difficulty = {key:solved_by_difficulty[key] for key in sorted_keys}

            output_string = f'Your solved POTD: \n'
            for key in solved_by_difficulty:
                total = len([potd for potd in potds if len(potd) > cfg.Config.config['potd_sheet_difficulty_col']
                              and potd[cfg.Config.config['potd_sheet_difficulty_col']] == key])
                output_string += "D" + key + ": " + f"{solved_by_difficulty[key]} ({len(solved_by_difficulty[key])}/{total})" + "\n"
            await self.send_potd_solved(ctx, output_string)
        elif flag == "s":
            solved_by_genre = {'A':[], 'C':[], 'G':[], 'N':[]}
            for number in solved:
                if number > current_potd or number <= 0:
                    genre = "(Unknown)"
                else:
                    potd_row = potds[current_potd - number]
                    if len(potd_row) > cfg.Config.config['potd_sheet_genre_col']:
                        genre = potd_row[cfg.Config.config['potd_sheet_genre_col']]
                    else:
                        genre = "(Unknown)"

                if 'A' in genre:
                    solved_by_genre['A'].append(number)
                if 'C' in genre:
                    solved_by_genre['C'].append(number)
                if 'G' in genre:
                    solved_by_genre['G'].append(number)
                if 'N' in genre:
                    solved_by_genre['N'].append(number)

            output_string = f'Your solved POTD: \n'
            for key in solved_by_genre:
                total = len([potd for potd in potds if len(potd) > cfg.Config.config['potd_sheet_difficulty_col']
                              and key in potd[cfg.Config.config['potd_sheet_genre_col']]])
                output_string += key + ": " + f"{solved_by_genre[key]} ({len(solved_by_genre[key])}/{total})" + "\n"
            await self.send_potd_solved(ctx, output_string)
        else:
            output_string = f'Your solved POTD: \n{solved} ({len(solved)}/{len(potds)})'
            await self.send_potd_solved(ctx, output_string)
        
    
    def get_potd_solved(self, ctx):
        cursor = cfg.db.cursor()
        cursor.execute(f'''SELECT discord_user_id, potd_id, create_date FROM potd_solves 
                            WHERE discord_user_id = {ctx.author.id} 
                            ORDER BY potd_id DESC''')
        return [x[1] for x in cursor.fetchall()]

    # send message in batches of 1900+e characters because of 2k character limit
    async def send_potd_solved(self, ctx, output_string):
        i = 0
        output_batch = ""
        while i < len(output_string):
            if output_batch == "":
                jump = min(1900, len(output_string)-i)
                output_batch += output_string[i:i+jump]
                i += jump
            else:
                output_batch += output_string[i]
                i += 1
            if output_batch[-1] == "," or output_batch[-1] == "]" or len(output_batch) == 2000 or i==len(output_string): # we end a batch at "," or "]"
                await ctx.send(output_batch)
                output_batch = ""


    @commands.command(aliases=['hint'], brief='Get hint for the POTD.')
    @commands.cooldown(1, 10, BucketType.user)
    async def potd_hint(self, ctx, number: int, hint_number: int = 1):
        sheet = self.get_potd_sheet()
        potd_row = self.get_potd_row(number, sheet)
        if potd_row == None:
            await ctx.send(f"There is no potd for day {number}. ")
            return
        else:  
            if hint_number == 1:
                if len(potd_row) <= cfg.Config.config['potd_sheet_hint1_col'] or potd_row[cfg.Config.config['potd_sheet_hint1_col']] == None:
                    await ctx.send(f"There is no hint for POTD {number}. Would you like to contribute one? Contact <@{cfg.Config.config['staffmail_id']}> to submit a hint!")
                    return
                else:
                    await ctx.send(f"Hint for POTD {number}:\n")
                    await ctx.send(f"<@{cfg.Config.config['paradox_id']}> texsp ||{potd_row[cfg.Config.config['potd_sheet_hint1_col']]}||")
                    if len(potd_row) > cfg.Config.config['potd_sheet_hint2_col'] and potd_row[cfg.Config.config['potd_sheet_hint2_col']] != None:
                        await ctx.send(f"There is another hint for this POTD. Use `-hint {number} 2` to get the hint.")
            elif hint_number == 2:
                if len(potd_row) <= cfg.Config.config['potd_sheet_hint2_col'] or potd_row[cfg.Config.config['potd_sheet_hint2_col']] == None:
                    await ctx.send(f"There is no hint 2 for POTD {number}. Would you like to contribute one? Contact <@{cfg.Config.config['staffmail_id']}> to submit a hint!")
                    return
                else:
                    await ctx.send(f"Hint 2 for POTD {number}:\n")
                    await ctx.send(f"<@{cfg.Config.config['paradox_id']}> texsp ||{potd_row[cfg.Config.config['potd_sheet_hint2_col']]}||")
                    if len(potd_row) > cfg.Config.config['potd_sheet_hint3_col'] and potd_row[cfg.Config.config['potd_sheet_hint3_col']] != None:
                        await ctx.send(f"There is another hint for this POTD. Use `-hint {number} 3` to get the hint.")
            elif hint_number == 3:
                if len(potd_row) <= cfg.Config.config['potd_sheet_hint3_col'] or potd_row[cfg.Config.config['potd_sheet_hint3_col']] == None:
                    await ctx.send(f"There is no hint 3 for POTD {number}. Would you like to contribute one? Contact <@{cfg.Config.config['staffmail_id']}> to submit a hint!")
                    return
                else:
                    await ctx.send(f"Hint 3 for POTD {number}:\n")
                    await ctx.send(f"<@{cfg.Config.config['paradox_id']}> texsp ||{potd_row[cfg.Config.config['potd_sheet_hint3_col']]}||")
            else:
                await ctx.send("Hint number should be from 1 to 3.")


    def get_potd_sheet(self):
        sheet = cfg.Config.service.spreadsheets().values().get(spreadsheetId=cfg.Config.config['potd_sheet'],
                                                               range=POTD_RANGE).execute()
        return sheet

    def get_potd_row(self, number, sheet):
        values = sheet.get('values', [])
        current_potd = int(values[0][0])  # this will be the top left cell which indicates the latest added potd

        if number > current_potd or number < 1:
            return None

        try:
            potd_row = values[current_potd - number]  # this gets the row requested
            return potd_row
        except IndexError:
            return None

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
        if result is None:
            return None
        embed = discord.Embed(colour=colour)
        try:
            if ctx.author.nick is None:
                embed.add_field(name='Username', value=ctx.author.name)
            else:
                embed.add_field(name='Nickname', value=ctx.author.nick)
        except Exception:
            embed.add_field(name='Username', value=ctx.author.name)
        for i in range(4):
            embed.add_field(name=['Algebra', 'Combinatorics', 'Geometry', 'Number Theory'][i], value=subcriteria(4*i))
        embed.set_footer(text='Use `-help pn` for help. ')
        return embed

    @commands.command(aliases=['pn'], brief='Customizes potd pings. ', help='`-pn`: enable POTD notifications or show settings\n'
                                                                            '`-pn a1-7`: set difficulty range for category\n'
                                                                            '`-pn c`: toggle notifications for category\n'
                                                                            '`-pn a1-7 c`: combine commands\n'
                                                                            '`-pn off`: disable notifications')
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
        if status is None:
            self.enable_dm = not self.enable_dm
        else:
            self.enable_dm = status
        cursor = cfg.db.cursor()
        cursor.execute(f"UPDATE settings SET value = '{str(self.enable_dm)}' WHERE setting = 'potd_dm'")
        cfg.db.commit()
        await self.bot.get_channel(cfg.Config.config['log_channel']).send(
            f'**POTD notifications set to `{self.enable_dm}` by {ctx.author.nick} ({ctx.author.id})**')


async def setup(bot):
    await bot.add_cog(Potd(bot))
