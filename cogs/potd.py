import ast
import math
import random
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
        self.update_ratings()
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
        self.update_ratings()
        self.prepare_dms(potd_row)
        self.to_send = self.generate_source(potd_row)
        self.listening_in_channel = cfg.Config.config['potd_channel']
        self.ping_daily = True
        self.late = False
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

    @commands.command(aliases=['fetch'], brief='Fetch a potd by id.')
    async def potd_fetch(self, ctx, number: int):
        # Read from the spreadsheet
        reply = cfg.Config.service.spreadsheets().values().get(spreadsheetId=cfg.Config.config['potd_sheet'],
                                                               range=POTD_RANGE).execute()
        values = reply.get('values', [])
        current_potd = int(values[0][0])  # this will be the top left cell which indicates the latest added potd

        if number > current_potd:
            await ctx.send(f"There is no potd for day {number}. ")
            return

        potd_row = values[current_potd - number]  # this gets the row requested

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

    @commands.command(aliases=['search'], brief='Search a potd by genre and difficulty.')
    async def potd_search(self, ctx, diff_lower_bound:int, diff_upper_bound:int, genre:str='ACGN'):
        if diff_lower_bound > diff_upper_bound:
            await ctx.send(f"Difficulty lower bound cannot be higher than upper bound.")
            return

        # Set up the genre filter
        genre_filter = ""
        if "A" in genre.upper():
            genre_filter += "A"
        if "C" in genre.upper():
            genre_filter += "C"
        if "G" in genre.upper():
            genre_filter += "G"
        if "N" in genre.upper():
            genre_filter += "N"
        if len(genre_filter) == 0: # If not filled, search all genre
            genre_filter = "ACGN"

        # set up the difficulty filter
        diff_lower_bound_filter = max(0,diff_lower_bound)
        diff_upper_bound_filter = max(min(99, diff_upper_bound), diff_lower_bound_filter)
        
        picked_potd = self.pick_potd(diff_lower_bound_filter, diff_upper_bound_filter, genre_filter)
        if picked_potd is not None:
            # fetch the picked POTD
            await self.potd_fetch(ctx, int(picked_potd))
        else:
            await ctx.send(f"No POTD found!")

    @commands.command(aliases=['mock'], brief='Create a mock paper using past POTDs.')
    async def potd_mock(self, ctx, template:str="IMO"):
        template = template.upper()
        template_list = ["IMO", "AMO", "APMO", "BMO1", "BMO2", "SMO2"]
        if template not in template_list:
            await ctx.send(f"Template not found. Possible templates: {', '.join(template_list)}")
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
            elif template == "SMO2":
                difficulty_bounds = [[4,5],[5,6],[6,7],[7,8],[8,9]]

        genres=[]
        genre_pool = ["A","C","G","N"] * math.ceil(len(difficulty_bounds)/4)
        while not self.is_genre_legit(genres, template, difficulty_bounds):
            genres = random.sample(genre_pool, len(difficulty_bounds))
        
        problems_tex = []
        # render the mock paper
        for i in range(0,len(difficulty_bounds)):
            picked_potd = self.pick_potd(difficulty_bounds[i][0], difficulty_bounds[i][1], genres[i])
            potd_statement = self.get_potd_statement(int(picked_potd))
            problems_tex.append(f'\\textbf{{Problem {i+1}. (POTD {str(picked_potd)})}}\\\\ ' + potd_statement)
        
        if template in ["IMO","AMO"] : 
            if template in ["IMO"]:
                index_day1 = [0,1,2]
                index_day2 = [3,4,5]
            elif template in ["AMO"]:
                index_day1 = [0,1,2,3]
                index_day2 = [4,5,6,7]
            title_day1 = r'\begin{center}\textbf{\textsf{MODSBot Mock ' + template + r' (Day 1)}}\end{center}'
            problems_day1 = r'\\ \\'.join([problems_tex[index] for index in index_day1])
            to_tex_day1 = f'<@419356082981568522>\n```tex\n {title_day1} {problems_day1}```'
            await ctx.send(to_tex_day1, delete_after=5)
            title_day2 = r'\begin{center}\textbf{\textsf{MODSBot Mock ' + template + r' (Day 2)}}\end{center}'
            problems_day2 = r'\\ \\'.join([problems_tex[index] for index in index_day2])
            to_tex_day2 = f'<@419356082981568522>\n```tex\n {title_day2} {problems_day2}```'
            await ctx.send(to_tex_day2, delete_after=5)
        else:
            title = r'\begin{center}\textbf{\textsf{MODSBot Mock ' + template + r'}}\end{center}'
            problems = r'\\ \\'.join(problems_tex)
            to_tex = f'<@419356082981568522>\n```tex\n {title} {problems}```'
            await ctx.send(to_tex, delete_after=5) 


    def is_genre_legit(genres, template, difficulty_bounds):
        if len(genres) != len(difficulty_bounds):
            return False
        
        # the paper need to contain all ACGN
        if not ("A" in genres and "C" in genres and "G" in genres and "N" in genres): 
            return False

        if template == "IMO":
            # P3 and P6 should be different genre
            if genres[2] == genres[5]: 
                return False

            # Geoff Smith Rule
            genres_geoff_smith = [genres[index] for index in [0,1,3,4]]
            if not ("A" in genres_geoff_smith and "C" in genres_geoff_smith and "G" in genres_geoff_smith and "N" in genres_geoff_smith):
                return False

        return True

    def pick_potd(diff_lower_bound_filter, diff_upper_bound_filter, genre_filter):
        # get data from spreadsheet
        potds = cfg.Config.service.spreadsheets().values().get(spreadsheetId=cfg.Config.config['potd_sheet'],
                                                               range=POTD_RANGE).execute().get('values', [])

        # filter and pick a POTD
        filtered_potds = [x for x in potds if len(x) >= max(cfg.Config.config['potd_sheet_difficulty_col'], cfg.Config.config['potd_sheet_genre_col'])
                        and x[cfg.Config.config['potd_sheet_difficulty_col']].isnumeric()
                        and int(x[cfg.Config.config['potd_sheet_difficulty_col']]) >= diff_lower_bound_filter
                        and int(x[cfg.Config.config['potd_sheet_difficulty_col']]) <= diff_upper_bound_filter
                        and len(set(x[cfg.Config.config['potd_sheet_genre_col']]).intersection(genre_filter)) > 0]                        

        if len(filtered_potds) > 0:
            filtered_potds_id = list(map(lambda x: x[cfg.Config.config['potd_sheet_id_col']], filtered_potds))
            picked_potd = int(random.choice(filtered_potds_id))
            return picked_potd
        else:
            return None        

    def get_potd_statement(number:int):
        # Read from the spreadsheet
        reply = cfg.Config.service.spreadsheets().values().get(spreadsheetId=cfg.Config.config['potd_sheet'],
                                                               range=POTD_RANGE).execute()
        values = reply.get('values', [])
        current_potd = int(values[0][0])  # this will be the top left cell which indicates the latest added potd

        if number > current_potd:
            return None

        potd_row = values[current_potd - number]  # this gets the row requested

        # Create the tex
        potd_statement = ''
        try:
            potd_statement = potd_row[cfg.Config.config['potd_sheet_statement_col']]
            return potd_statement
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


def setup(bot):
    bot.add_cog(Potd(bot))
