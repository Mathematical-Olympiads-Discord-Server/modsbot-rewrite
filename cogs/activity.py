import ast
import datetime as dt
import logging
import math
import pickle
from datetime import datetime

import discord
import matplotlib.pyplot as plt
from discord.ext import commands, flags
from discord.ext.commands import BucketType

from cogs import config as cfg

Cog = commands.Cog

today_messages = {}


def sigmoid(x):
    return 1 / (1 + math.exp(-x))


def weight(chars, m_date, last_m, now_ts):
    if last_m is None:
        interval = 100
    else:
        interval = (m_date - last_m)
    interval = abs(interval)
    chars = chars if not chars == 0 else 1
    # print(interval)
    try:
        x = math.log10(chars) * sigmoid(interval / 30) * math.exp(
            (m_date - now_ts) * math.log(0.9, math.e) / 86400)
        # print(x)
        return 10 * math.log10(chars) * sigmoid(interval / 30) * math.exp(
            (now_ts - m_date) * math.log(0.9, math.e) / 86400)
    except Exception:
        print(chars, interval, m_date, last_m, now_ts)


class Activity(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger('cogs.activity')
        self.new_message = False

    @Cog.listener()
    async def on_message(self, message):
        if not message.author.bot and message.guild is not None:  # Ignore messages from bots and DMs
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

    @commands.command(aliases=['ad', 'as'])
    async def activity_score(self, ctx, other: discord.User = None):
        interval = 30
        to_check = ctx.author if other is None else other
        cursor = cfg.db.cursor()
        cursor.execute(f'''SELECT message_date, message_length 
        FROM messages
        WHERE message_date > date_sub(curdate(), interval {interval} day) 
        and discord_user_id = {to_check.id}
        LIMIT 100000;''')
        messages = cursor.fetchall()
        tss = [(x[0].timestamp(), x[1]) for x in messages]
        last_message_time = -1
        score = 0

        now = datetime.utcnow().timestamp()
        for message in tss:
            if last_message_time != -1:
                score += weight(message[1], message[0], last_message_time, now)
            else:
                score = weight(message[1], message[0], None, now)
            last_message_time = message[0]

        await ctx.send(f'Activity score is {int(score)}. ')

    @commands.command(aliases=['ua'])
    @commands.check(cfg.is_staff)
    async def update_actives(self, ctx, threshold: int = 750):
        cursor = cfg.db.cursor()
        cursor.execute(f'''SELECT discord_user_id, message_date, message_length 
        FROM messages
        WHERE message_date > date_sub(curdate(), interval 30 day) LIMIT 100000;''')
        messages = cursor.fetchall()
        tss = [(x[0], x[1].timestamp(), x[2]) for x in messages]
        last_message = {}
        activity = {}

        now = datetime.utcnow().timestamp()
        for message in tss:
            if message[0] in activity:
                activity[message[0]] += weight(message[2], message[1], last_message[message[0]], now)
                last_message[message[0]] = message[1]
            else:
                activity[message[0]] = weight(message[2], message[1], None, now)
                last_message[message[0]] = message[1]

        actives_today = set([i for i in activity if activity[i] >= threshold])
        print([i for i in activity if activity[i] >= threshold])
        print(len([i for i in activity if activity[i] >= threshold]))

        active_role = ctx.guild.get_role(cfg.Config.config['active_role'])
        continued_actives = set()
        removed_actives = set()
        new_actives = set()
        for member in active_role.members:
            if member.id in actives_today:
                continued_actives.add(member.id)
            else:
                try:
                    await member.remove_roles(active_role)
                except:
                    pass
                removed_actives.add(member.id)

        for id in actives_today:
            if id not in continued_actives:
                try:
                    await ctx.guild.get_member(id).add_roles(active_role)
                except:
                    pass
                new_actives.add(id)

        ca = ', '.join([str(x) for x in continued_actives]) if len(continued_actives) > 0 else 'None'
        ra = ', '.join([str(x) for x in removed_actives]) if len(removed_actives) > 0 else 'None'
        na = ', '.join([str(x) for x in new_actives]) if len(new_actives) > 0 else 'None'
        print(f'Continued: ```{ca}```\nRemoved: ```{ra}```\nNew: ```{na}```')
        await ctx.guild.get_channel(cfg.Config.config['log_channel']).send(
            f'Continued: ```{ca}```\nRemoved: ```{ra}```\nNew: ```{na}```')

    @flags.add_flag('--interval', type=int, default=30)
    @flags.add_flag('--users', type=int, default=15)
    @flags.command(aliases=['acttop'])
    @commands.cooldown(1, 10, BucketType.user)
    async def activity_top(self, ctx, **flags):
        interval = flags['interval'] if flags['interval'] < 30 else 30
        users = flags['users'] if flags['users'] < 30 else 30
        cursor = cfg.db.cursor()
        cursor.execute(f'''SELECT discord_user_id, message_date, message_length 
        FROM messages
        WHERE message_date > date_sub(curdate(), interval {interval} day) LIMIT 100000;''')
        messages = cursor.fetchall()
        tss = [(x[0], x[1].timestamp(), x[2]) for x in messages]
        last_message = {}
        score = {}

        now = datetime.utcnow().timestamp()
        for message in tss:
            if message[0] in score:
                score[message[0]] += weight(message[2], message[1], last_message[message[0]], now)
                last_message[message[0]] = message[1]
            else:
                score[message[0]] = weight(message[2], message[1], None, now)
                last_message[message[0]] = message[1]

        scores = [(x, int(score[x])) for x in score]
        scores.sort(key=lambda x: -x[1])
        embed = discord.Embed()
        embed.add_field(name=f'Top 15 users by activity score ({interval} day)',
                        value='\n'.join([f'`{i + 1}.` <@!{scores[i][0]}>: `{scores[i][1]}`' for i in range(users)]))
        await ctx.send(embed=embed)

    @flags.add_flag('--interval', type=int, default=None)
    @flags.add_flag('--user', type=discord.User, default=None)
    @commands.cooldown(1, 10, BucketType.user)
    @flags.command()
    async def activity(self, ctx, **flags):
        messages = []
        ticks = []
        delta = dt.timedelta(days=1)
        index = 0
        end = datetime.now().date()
        interval = flags['interval']
        user = flags['user']

        if interval is None:
            interval = (end - (dt.date(2020, 7, 1))) / delta
        if interval > (end - dt.date(2020, 7, 1)) / delta:
            await ctx.send(f'Too big interval (max size: `{(end - (dt.date(2020, 7, 1))) // delta}`)')
            return

        if user is None:
            user = ctx.author

        cursor = cfg.db.cursor()
        cursor.execute(f'''
        SELECT date(message_date) as date, COUNT(*) AS number
        FROM messages
        WHERE date(message_date) > date_sub(curdate(), interval {interval} day) 
        and discord_user_id = {user.id}
        GROUP BY discord_user_id, DATE(message_date)
        ORDER BY DATE(message_date), discord_user_id;
        ''')
        result = cursor.fetchall()

        plt.style.use('ggplot')

        start = end - (interval - 1) * delta
        while start <= end:
            if len(result) > index and result[index][0] == start:
                messages.append(result[index][1])
                index += 1
            else:
                messages.append(0)
            ticks.append(str(start)[5:] if start.weekday() == 0 else None)
            start += delta
        x_pos = [i for i, _ in enumerate(messages)]
        print(x_pos)
        print(messages)
        plt.xkcd(scale=0.5, randomness=0.5)
        plt.bar(x_pos, messages, color='green')
        plt.xlabel("Date")
        plt.ylabel("Messages")
        plt.title(f"{user.display_name}'s Activity")
        plt.axhline(y=10, linewidth=1, color='r')
        plt.subplots_adjust(bottom=0.15)

        plt.xticks(x_pos, ticks)
        fname = f'data/{datetime.now().isoformat()}.png'
        plt.savefig(fname)
        await ctx.send(file=discord.File(open(fname, 'rb')))
        plt.clf()


def setup(bot):
    bot.add_cog(Activity(bot))
