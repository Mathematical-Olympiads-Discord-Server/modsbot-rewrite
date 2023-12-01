import ast
import contextlib
import datetime as dt
import logging
import math
import pickle
from datetime import datetime

import discord
import matplotlib
import matplotlib.pyplot as plt
import schedule
from discord.ext import commands
from discord.ext.commands import BucketType

from cogs import config as cfg

Cog = commands.Cog

today_messages = {}


def sigmoid(x):
    return 1 / (1 + math.exp(-x))


def weight(chars, m_date, last_m, now_ts):
    interval = 100 if last_m is None else m_date - last_m
    interval = abs(interval)
    chars = chars if chars != 0 else 1
    # print(interval)
    try:
        return (
            10
            * math.log10(chars)
            * (sigmoid(interval / 30))
            * math.exp((now_ts - m_date) * math.log(0.9, math.e) / 86400)
        )
    except Exception:
        print(chars, interval, m_date, last_m, now_ts)


def moving_avg(data, interval):
    # Initialize the rolling sum
    rolling_sum = sum(data[:interval])
    moving_averages = [rolling_sum / interval]
    # Loop over the remaining elements in the array
    for i in range(interval, len(data)):
        # Add the current element to the rolling sum
        # and subtract the element interval
        # positions earlier
        rolling_sum += data[i] - data[i - interval]

        # Calculate the moving average for the current interval
        # and append it to the list of moving averages
        moving_averages.append(rolling_sum / interval)

    # Return the list of moving averages
    return moving_averages


class Activity(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("cogs.activity")
        self.new_message = False

        schedule.every().day.at("10:00").do(self.schedule_ua).tag("cogs.activity")

    @Cog.listener()
    async def on_message(self, message):
        if (
            not message.author.bot and message.guild is not None
        ):  # Ignore messages from bots and DMs
            cursor = cfg.db.cursor()
            cursor.execute(
                "INSERT INTO messages (discord_message_id, "
                "discord_channel_id, discord_user_id, message_length, "
                "message_date) VALUES (?, ?, ?, ?, ?)",
                (
                    message.id,
                    message.channel.id,
                    message.author.id,
                    len(message.content),
                    datetime.now(),
                ),
            )
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
            await ctx.send(f"Done!: New activity: ```{today_messages}```")
        except Exception:
            await ctx.send("Something went wrong! ")

    @commands.command()
    @commands.is_owner()
    async def f_dump_activity(self, ctx):
        pickle.dump(today_messages, open("data/activity_dump.p", "wb+"))
        await ctx.send("Dumped")

    def f_dump(self):
        if self.new_message:
            pickle.dump(today_messages, open("data/activity_dump.p", "wb+"))
            self.logger.info(f"Dumped activity: {str(today_messages)}")
        else:
            self.logger.info("No new messages. ")
        self.new_message = False

    @commands.command()
    @commands.is_owner()
    async def f_load_activity(self, ctx):
        x = pickle.load(open("data/activity_dump.p", "rb"))
        today_messages.clear()
        for i in x:
            today_messages[i] = x[i]
        await ctx.send(f"Loaded: ```{today_messages}```")

    @commands.command(aliases=["ad", "as"], brief="Show my activity score.")
    async def activity_score(self, ctx, other: discord.User = None):
        interval = 30
        to_check = ctx.author if other is None else other
        cursor = cfg.db.cursor()
        cursor.execute(
            f"""SELECT message_date, message_length
        FROM messages
        WHERE message_date BETWEEN
        "{str(dt.date.today() - dt.timedelta(interval - 1))}"
        AND "{str(dt.date.today() + dt.timedelta(1))}"
        AND discord_channel_id != {cfg.Config.config['bot_spam_channel']}
        and discord_channel_id != {cfg.Config.config['muted_channel']}
        and discord_channel_id !=
        {cfg.Config.config['staff_bot_spam_channel']}
        and discord_user_id = {to_check.id}
        LIMIT 1000000;"""
        )
        messages = cursor.fetchall()
        tss = [(datetime.fromisoformat(x[0]).timestamp(), x[1]) for x in messages]
        last_message_time = -1
        score = 0

        now = datetime.now(dt.timezone.utc).timestamp()
        for message in tss:
            if last_message_time != -1:
                score += weight(message[1], message[0], last_message_time, now)
            else:
                score = weight(message[1], message[0], None, now)
            last_message_time = message[0]

        await ctx.send(f"Activity score is {int(score)}. ")

    @commands.command(aliases=["ua"])
    @commands.check(cfg.is_staff)
    async def update_actives(
        self, ctx, threshold: int = cfg.Config.config["active_threshold"]
    ):
        cursor = cfg.db.cursor()
        cursor.execute(
            f"""SELECT discord_user_id, message_date, message_length
        FROM messages
        WHERE message_date BETWEEN "{str(dt.date.today() - dt.timedelta(30 - 1))}"
        AND "{str(dt.date.today() + dt.timedelta(1))}"
        AND discord_channel_id != {cfg.Config.config['bot_spam_channel']}
        and discord_channel_id != {cfg.Config.config['muted_channel']}
        and discord_channel_id != {cfg.Config.config['staff_bot_spam_channel']}
        LIMIT 1000000;"""
        )
        messages = cursor.fetchall()
        tss = [(x[0], datetime.fromisoformat(x[1]).timestamp(), x[2]) for x in messages]
        last_message = {}
        activity = {}

        now = datetime.now(dt.timezone.utc).timestamp()
        for message in tss:
            if message[0] in activity:
                activity[message[0]] += weight(
                    message[2], message[1], last_message[message[0]], now
                )
            else:
                activity[message[0]] = weight(message[2], message[1], None, now)
            last_message[message[0]] = message[1]
        actives_today = {i for i in activity if activity[i] >= threshold}
        print([i for i in activity if activity[i] >= threshold])
        print(len([i for i in activity if activity[i] >= threshold]))

        active_role = ctx.guild.get_role(cfg.Config.config["active_role"])
        continued_actives = set()
        removed_actives = set()
        new_actives = set()
        for member in active_role.members:
            if member.id in actives_today:
                continued_actives.add(member.id)
            else:
                with contextlib.suppress(Exception):
                    await member.remove_roles(active_role)
                removed_actives.add(member.id)

        for id in actives_today:
            if id not in continued_actives:
                with contextlib.suppress(Exception):
                    await ctx.guild.get_member(id).add_roles(active_role)
                new_actives.add(id)

        ca = (
            ", ".join([str(x) for x in continued_actives])
            if continued_actives
            else "None"
        )
        ra = ", ".join([str(x) for x in removed_actives]) if removed_actives else "None"
        na = ", ".join([str(x) for x in new_actives]) if new_actives else "None"
        print(f"Continued: ```{ca}```\nRemoved: ```{ra}```\nNew: ```{na}```")
        await ctx.guild.get_channel(cfg.Config.config["log_channel"]).send(
            f"Continued: ```{ca}```\nRemoved: ```{ra}```\nNew: ```{na}```"
        )

    class ActtopFlags(commands.FlagConverter, delimiter=" ", prefix="--"):
        interval: int = commands.flag(name="interval", aliases=["i"], default=30)

    @commands.command(
        aliases=["acttop"],
        brief="Show user activity leaderboard.",
        help="`-acttop`: show user activity leaderboard\n"
        "`-acttop --interval 15`: show leaderboard for the last 15 days",
        cooldown_after_parsing=True,
    )
    @commands.cooldown(1, 10, BucketType.user)
    async def activity_top(self, ctx, *, flags: ActtopFlags):
        interval = min(flags.interval, 30)
        cursor = cfg.db.cursor()
        cursor.execute(
            f"""SELECT discord_user_id, message_date, message_length
        FROM messages
        WHERE message_date BETWEEN "{str(dt.date.today() - dt.timedelta(interval - 1))}"
        AND "{str(dt.date.today() + dt.timedelta(1))}"
        AND discord_channel_id != {cfg.Config.config['bot_spam_channel']}
        and discord_channel_id != {cfg.Config.config['muted_channel']}
        and discord_channel_id != {cfg.Config.config['staff_bot_spam_channel']}
        LIMIT 1000000;"""
        )
        messages = cursor.fetchall()
        tss = [(x[0], datetime.fromisoformat(x[1]).timestamp(), x[2]) for x in messages]
        last_message = {}
        score = {}

        now = datetime.now(dt.timezone.utc).timestamp()
        for message in tss:
            if message[0] in score:
                score[message[0]] += weight(
                    message[2], message[1], last_message[message[0]], now
                )
            else:
                score[message[0]] = weight(message[2], message[1], None, now)
            last_message[message[0]] = message[1]
        scores = [(x, int(score[x])) for x in score]
        scores.sort(key=lambda x: -x[1])

        if len(scores) <= 20:
            embed = discord.Embed()
            length = len(scores)
            embed.add_field(
                name=f"Top users by activity score ({interval} day)",
                value="\n".join(
                    [
                        f"`{i + 1}.` <@!{scores[i][0]}>: `{scores[i][1]}`"
                        for i in range(length)
                    ]
                ),
            )
            await ctx.send(embed=embed)
        else:
            pages = []
            for j in range(math.ceil(len(scores) / 20)):
                print(j)
                pageMin = 20 * j
                pageMax = min(20 * j + 20, len(scores))
                page = discord.Embed(
                    title=f"Top users by activity score ({interval} day) - Page {j + 1}"
                )
                lines = "\n".join(
                    [
                        f"`{i + 1}.` <@!{scores[i][0]}>: `{scores[i][1]}`"
                        for i in range(pageMin, pageMax)
                    ]
                )
                page.description = lines
                pages.append(page)
            await self.bot.get_cog("MenuManager").new_menu(ctx, pages)

    class ChtopFlags(commands.FlagConverter, delimiter=" ", prefix="--"):
        interval: int = commands.flag(name="interval", aliases=["i"], default=30)

    @commands.command(
        aliases=["chtop"],
        brief="Show channel activity leaderboard.",
        help="`-chtop`: show channel activity leaderboard (by activity points)\n"
        "`-chtop --interval 15`: show leaderboard for the last 15 days",
        cooldown_after_parsing=True,
    )
    @commands.cooldown(1, 10, BucketType.user)
    async def channel_top(self, ctx, *, flags: ChtopFlags):
        interval = min(flags.interval, 30)
        cursor = cfg.db.cursor()
        cursor.execute(
            f"""SELECT discord_channel_id, message_date, message_length
        FROM messages
        WHERE message_date BETWEEN "{str(dt.date.today() - dt.timedelta(interval - 1))}"
        AND "{str(dt.date.today() + dt.timedelta(1))}"
        LIMIT 1000000;"""
        )
        messages = cursor.fetchall()
        tss = [(x[0], datetime.fromisoformat(x[1]).timestamp(), x[2]) for x in messages]
        last_message = {}
        score = {}

        now = datetime.now(dt.timezone.utc).timestamp()
        for message in tss:
            if message[0] in score:
                score[message[0]] += weight(
                    message[2], message[1], last_message[message[0]], now
                )
            else:
                score[message[0]] = weight(message[2], message[1], None, now)
            last_message[message[0]] = message[1]
        scores = [(x, int(score[x])) for x in score]
        scores.sort(key=lambda x: -x[1])

        if len(scores) <= 20:
            embed = discord.Embed()
            length = len(scores)
            embed.add_field(
                name=f"Top channels by activity score ({interval} day)",
                value="\n".join(
                    [
                        f"`{i + 1}.` <#{scores[i][0]}>: `{scores[i][1]}`"
                        for i in range(length)
                    ]
                ),
            )
            await ctx.send(embed=embed)
        else:
            pages = []
            for j in range(math.ceil(len(scores) / 20)):
                print(j)
                pageMin = 20 * j
                pageMax = min(20 * j + 20, len(scores))
                title = (
                    f"Top channels by activity score ({interval} day)"
                    f" - Page {j + 1}"
                )
                page = discord.Embed(title=title)
                lines = "\n".join(
                    [
                        f"`{i + 1}.` <#{scores[i][0]}>: `{scores[i][1]}`"
                        for i in range(pageMin, pageMax)
                    ]
                )
                page.description = lines
                pages.append(page)
            await self.bot.get_cog("MenuManager").new_menu(ctx, pages)

    class ActivityFlags(commands.FlagConverter, delimiter=" ", prefix="--"):
        interval: int = commands.flag(name="interval", aliases=["i"], default=30)
        user: discord.User = commands.flag(name="user", aliases=["u"], default=None)

    @commands.cooldown(1, 10, BucketType.user)
    @commands.command(
        aliases=["act"],
        brief="Show user's activity graph.",
        help="`-activity`: show my activity graph\n"
        "`-activity --interval 60`: show my activity graph for past 60 days\n"
        "`-activity --user @user`: show activity graph for @user\n"
        "`-activity --interval 60 --user @user`: combine commands",
        cooldown_after_parsing=True,
    )
    async def activity(self, ctx, *, flags: ActivityFlags):
        matplotlib.use("agg")

        messages = []
        ticks = []
        delta = dt.timedelta(days=1)
        index = 0
        end = datetime.now().date()
        interval = flags.interval
        user = flags.user

        epoch = dt.date(2019, 1, 11)  # This is when the server was created
        if interval is None:
            interval = (end - epoch) / delta
        interval = min(interval, (end - epoch) / delta)
        if interval < 1:
            await ctx.send("Interval must be at least 1.")
            return

        if user is None:
            user = ctx.author

        cursor = cfg.db.cursor()
        cursor.execute(
            f"""
        SELECT date(message_date) as date, COUNT(*) AS number
        FROM messages
        WHERE date(message_date)
        BETWEEN "{str(dt.date.today() - dt.timedelta(interval - 1))}"
        AND "{str(dt.date.today() + dt.timedelta(1))}"
        and discord_user_id = {user.id}
        GROUP BY discord_user_id, DATE(message_date)
        ORDER BY DATE(message_date), discord_user_id;
        """
        )
        result = cursor.fetchall()

        plt.style.use("ggplot")

        start = end - (interval - 1) * delta
        while start <= end:
            if len(result) > index and result[index][0] == str(start):
                messages.append(result[index][1])
                index += 1
            else:
                messages.append(0)
            if interval > 600:
                ticks.append(
                    str(start)[:7] if start.day == 1 and start.month % 3 == 1 else None
                )
            elif interval > 70:
                ticks.append(str(start)[:7] if start.day == 1 else None)
            else:
                ticks.append(str(start)[5:] if start.weekday() == 0 else None)
            start += delta
        x_pos = [i for i, _ in enumerate(messages)]
        print(x_pos)
        print(messages)
        if (
            interval > 50
        ):  # With a lot of data to display cool formatting is less necessary
            plt.figure(figsize=(24, 13.5))
            plt.xkcd(scale=0, randomness=0, length=0)
        else:
            plt.xkcd(scale=0.5, randomness=0.5)
            plt.figure(figsize=(8, 6))
        plt.bar(x_pos, messages, color="green")
        plt.xlabel("Date")
        plt.ylabel("Messages")
        plt.title(f"{user.display_name}'s Activity")
        plt.axhline(y=10, linewidth=1, color="r")
        plt.subplots_adjust(bottom=0.15)

        plt.xticks(x_pos, ticks)
        fname = f"data/{datetime.now().isoformat()}.png"
        plt.savefig(fname)
        await ctx.send(file=discord.File(open(fname, "rb")))
        plt.clf()
        plt.close("all")

    class ServerActivityFlags(commands.FlagConverter, delimiter=" ", prefix="--"):
        interval: int = commands.flag(name="interval", aliases=["i"], default=30)
        channel: discord.TextChannel = commands.flag(
            name="channel", aliases=["c"], default=None
        )

    @commands.cooldown(1, 10, BucketType.user)
    @commands.command(
        aliases=["sa"],
        brief="Show server/channel's activity graph.",
        help="`-server_activity`: show server's activity graph\n"
        "`-server_activity --interval 60`: show server's "
        "activity graph for past 60 days\n"
        "`-server_activity --channel #lounge`: show lounge's activity graph\n"
        "`-server_activity --interval 60 --channel #lounge`: combine commands",
        cooldown_after_parsing=True,
    )
    async def server_activity(self, ctx, *, flags: ServerActivityFlags):
        matplotlib.use("agg")

        messages = []
        ticks = []
        delta = dt.timedelta(days=1)
        index = 0
        end = datetime.now().date()
        interval = flags.interval
        channel = flags.channel

        epoch = dt.date(2019, 1, 11)  # This is when the server was created
        if interval is None:
            interval = (end - epoch) / delta
        interval = min(interval, (end - epoch) / delta)
        if interval < 1:
            await ctx.send("Interval must be at least 1.")
            return

        cursor = cfg.db.cursor()
        if channel is None:
            cursor.execute(
                f"""
            SELECT date(message_date) as date, COUNT(*) AS number
            FROM messages
            WHERE date(message_date)
            BETWEEN "{str(dt.date.today() - dt.timedelta(interval - 1))}"
            AND "{str(dt.date.today() + dt.timedelta(1))}"
            GROUP BY DATE(message_date)
            ORDER BY DATE(message_date);
            """
            )
        else:
            cursor.execute(
                f"""
            SELECT date(message_date) as date, COUNT(*) AS number
            FROM messages
            WHERE date(message_date)
            BETWEEN "{str(dt.date.today() - dt.timedelta(interval - 1))}"
            AND "{str(dt.date.today() + dt.timedelta(1))}"
            AND discord_channel_id = {channel.id}
            GROUP BY DATE(message_date)
            ORDER BY DATE(message_date);
            """
            )
        result = cursor.fetchall()
        plt.style.use("ggplot")

        start = end - (interval - 1) * delta
        while start <= end:
            if len(result) > index and result[index][0] == str(start):
                messages.append(result[index][1])
                index += 1
            else:
                messages.append(0)
            if interval > 600:
                ticks.append(
                    str(start)[:7] if start.day == 1 and start.month % 3 == 1 else None
                )
            elif interval > 70:
                ticks.append(str(start)[:7] if start.day == 1 else None)
            else:
                ticks.append(str(start)[5:] if start.weekday() == 0 else None)
            start += delta
        x_pos = [i for i, _ in enumerate(messages)]
        if (
            interval > 50
        ):  # With a lot of data to display cool formatting is less necessary
            plt.figure(figsize=(24, 13.5))
            plt.xkcd(scale=0, randomness=0, length=0)
        else:
            plt.xkcd(scale=0.5, randomness=0.5)
            plt.figure(figsize=(8, 6))
        plt.bar(x_pos, messages, color="green")

        # Plot 30 DMA
        if interval > 30:
            plt.plot(x_pos[29:], moving_avg(messages, 30))
        # Plot 90 DMA
        if interval > 90:
            plt.plot(x_pos[89:], moving_avg(messages, 90))

        plt.xlabel("Date")
        plt.ylabel("Messages")
        if channel is None:
            plt.title("MODS's Activity")
        else:
            plt.title(f"{channel.name}'s Activity")
        plt.axhline(y=10, linewidth=1, color="r")
        plt.subplots_adjust(bottom=0.15)

        plt.xticks(x_pos, ticks)
        fname = f"data/{datetime.now().isoformat()}.png"
        plt.savefig(fname)
        await ctx.send(file=discord.File(open(fname, "rb")))
        plt.clf()
        plt.close("all")

    def schedule_ua(self, mode=None):
        self.bot.loop.create_task(self.call_ua())

    async def call_ua(self):
        channel = self.bot.get_channel(cfg.Config.config["bot_spam_channel"])

        # post something so we know it is working
        await channel.send("-ua")

        # do the update active
        message = await channel.fetch_message(channel.last_message_id)
        ctx = await self.bot.get_context(message)
        await self.update_actives(ctx)


async def setup(bot):
    await bot.add_cog(Activity(bot))
