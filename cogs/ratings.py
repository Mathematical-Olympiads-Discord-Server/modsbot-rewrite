import statistics
from datetime import datetime

import discord
from discord.ext import commands

from cogs import config as cfg
from utils import potd_utils

Cog = commands.Cog


class Ratings(Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def format(self, rating):
        return f"d||`{rating}`||" if rating >= 10 else f"d||`{rating} `||"

    @commands.command(aliases=["rate"], brief="Rates a potd based on difficulty. ")
    async def potd_rate(self, ctx, potd: int, rating: int, overwrite: bool = False):
        if rating < 0 or rating > 14:
            await ctx.send(
                f"<@{ctx.author.id}> POTD rating is only allowed from 0 to 14."
            )
            return

        # Delete messages if it's in a guild
        if ctx.guild is not None:
            await ctx.message.delete()

        cursor = cfg.db.cursor()
        cursor.execute(
            f"SELECT * FROM ratings where prob = {potd} and userid = {ctx.author.id} "
            "LIMIT 1"
        )
        result = cursor.fetchone()
        # print(result)
        if result is None:
            sql = "INSERT INTO ratings (prob, userid, rating) VALUES (?, ?, ?)"
            cursor.execute(sql, (potd, ctx.author.id, rating))
            cfg.db.commit()
            await ctx.send(
                f"<@{ctx.author.id}> You have rated POTD {potd} {self.format(rating)}."
            )
        elif overwrite:
            cursor.execute(
                f"UPDATE ratings SET rating = {rating} WHERE idratings = {result[0]}"
            )
            cfg.db.commit()
            await ctx.send(
                f"<@{ctx.author.id}> You have rated POTD {potd} {self.format(rating)}."
            )
        else:
            await ctx.send(
                f"<@{ctx.author.id}> You already rated this POTD "
                f"{self.format(result[3])}. "
                f"If you wish to overwrite append `True` to your previous message, "
                f"like `-rate {potd} <rating> True` "
            )
        await potd_utils.edit_source(self.bot, potd)

    @commands.command(aliases=["rating"], brief="Finds the median of a POTD's ratings")
    async def potd_rating(self, ctx, potd: int, full: bool = True):
        cursor = cfg.db.cursor()

        cursor.execute(
            f"""SELECT blacklisted_user_id
        FROM potd_rater_blacklist
        WHERE discord_user_id = {ctx.author.id}
        LIMIT 1000000;"""
        )
        blacklisted_users = list(map(lambda x: x[0], cursor.fetchall()))
        blacklisted_users_string = "('" + "','".join(map(str, blacklisted_users)) + "')"

        sql = (
            f"SELECT * FROM ratings WHERE prob = {potd} "
            f"AND userid not in {blacklisted_users_string} ORDER BY rating"
        )
        cursor.execute(sql)
        if result := list(map(lambda x: list(x), cursor.fetchall())):
            median = float(statistics.median([row[3] for row in result]))

            await ctx.send(
                f"Median community rating for POTD {potd} is {self.format(median)}. "
            )
            if full:
                result_chunks = [result[i : i + 25] for i in range(0, len(result), 25)]
                for chunk in result_chunks:
                    embed = discord.Embed()
                    embed.add_field(
                        name=f"Full list of community rating for POTD {potd}",
                        value="\n".join(
                            f"<@!{row[2]}>: {self.format(row[3])}" for row in chunk
                        ),
                    )
                    await ctx.send(embed=embed)

        else:
            await ctx.send(f"No ratings for POTD {potd} yet. ")

    @commands.command(aliases=["myrating"], brief="Checks your rating of a potd. ")
    async def potd_rating_self(self, ctx, potd: int):
        cursor = cfg.db.cursor()
        cursor.execute(
            f"SELECT * FROM ratings WHERE prob = {potd} AND userid = {ctx.author.id}"
        )
        result = cursor.fetchone()
        if result is None:
            await ctx.author.send(f"You have not rated potd {potd}. ")
        else:
            await ctx.author.send(
                f"You have rated potd {potd} as difficulty level {result[3]}"
            )

    @commands.command(aliases=["myratings"], brief="Checks all your ratings. ")
    async def potd_rating_all(self, ctx):
        cursor = cfg.db.cursor()
        cursor.execute(f"SELECT * FROM ratings WHERE userid = {ctx.author.id}")
        result = cursor.fetchall()
        if len(result) == 0:
            await ctx.author.send("You have not rated any problems!")
        else:
            ratings = [f"{i[1]:<6}{i[3]}" for i in result]

            # Ensure that sent messages do not exceed character length
            rating_msgs = []
            rating_msg = []
            for rating in ratings:
                rating_msg.append(rating)
                if sum(len(rating_str) + 1 for rating_str in rating_msg) >= 1900:
                    rating_msgs.append("\n".join(rating_msg))
                    rating_msg = []
            if len(rating_msg) != 0:
                rating_msgs.append("\n".join(rating_msg))
            await ctx.author.send("Your ratings:")
            for msg in rating_msgs:
                await ctx.author.send(f"```Potd  Rating\n{msg}\n```")
            await ctx.author.send(f"You have rated {len(result)} potds.")

    @commands.command(
        aliases=["rmrating", "unrate"], brief="Removes your rating for a potd. "
    )
    async def potd_rating_remove(self, ctx, potd: int):
        cursor = cfg.db.cursor()
        cursor.execute(
            f"SELECT * FROM ratings WHERE prob = {potd} AND userid = {ctx.author.id}"
        )
        result = cursor.fetchone()
        if result is None:
            await ctx.author.send(f"You have not rated potd {potd}. ")
        else:
            cursor.execute(
                f"DELETE FROM ratings WHERE prob = {potd} AND userid = {ctx.author.id}"
            )
            await ctx.author.send(
                f"Removed your rating of difficulty level {result[3]} for potd {potd}. "
            )
            await potd_utils.edit_source(self.bot, potd)

    @commands.command(
        aliases=["blacklist", "rater_blacklist"],
        brief="Blacklist a user from community rating. ",
    )
    async def potd_rater_blacklist(self, ctx, user_id: int):
        user = self.bot.get_user(user_id)
        if user is None:
            await ctx.send(f"User with ID {user_id} is not found on this server!")
            display_name = f"<@{user_id}>"
        else:
            display_name = user.display_name

        cursor = cfg.db.cursor()
        cursor.execute(
            f"""SELECT blacklisted_user_id
            FROM potd_rater_blacklist
            WHERE discord_user_id = {ctx.author.id}
            LIMIT 1000000;"""
        )
        blacklisted_users = cursor.fetchall()
        if str(user_id) not in list(map(lambda x: x[0], blacklisted_users)):
            sql = (
                "INSERT INTO potd_rater_blacklist "
                "(discord_user_id, blacklisted_user_id, create_date)"
                "VALUES (?, ?, ?)"
            )
            cursor.execute(sql, (str(ctx.author.id), str(user_id), datetime.now()))
            cfg.db.commit()
            await ctx.send(f"User `{display_name}` is added to your blacklist.")
        else:
            await ctx.send(
                f"User `{display_name}` is already in your blacklist."
            )

    @commands.command(
        aliases=["unblacklist", "rater_unblacklist"],
        brief="Unblacklist a user from community rating. ",
    )
    async def potd_rater_unblacklist(self, ctx, user_id: int):
        user = self.bot.get_user(user_id)
        if user is None:
            await ctx.send(f"User with ID {user_id} is not found on this server!")        
            display_name = f"<@{user_id}>"
        else:
            display_name = user.display_name

        cursor = cfg.db.cursor()
        sql = (
            f"DELETE FROM potd_rater_blacklist "
            f"WHERE blacklisted_user_id = {user_id} "
            f"AND discord_user_id = {ctx.author.id}"
        )
        cursor.execute(sql)
        cfg.db.commit()
        await ctx.send(f"User `{display_name}` is removed from your blacklist.")

    @commands.command(aliases=["myblacklist"], brief="Get your potd rating blacklist.")
    async def potd_myblacklist(self, ctx):
        cursor = cfg.db.cursor()
        cursor.execute(
            f"""SELECT blacklisted_user_id
        FROM potd_rater_blacklist
        WHERE discord_user_id = {ctx.author.id}
        LIMIT 1000000;"""
        )
        blacklisted_users = cursor.fetchall()

        embed = discord.Embed()
        embed.add_field(
            name=f"{ctx.author.display_name}'s POTD rating blacklist",
            value="\n".join(
                [
                    f"<@!{blacklisted_users[i][0]}>"
                    for i in range(len(blacklisted_users))
                ]
            ),
        )
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Ratings(bot))
