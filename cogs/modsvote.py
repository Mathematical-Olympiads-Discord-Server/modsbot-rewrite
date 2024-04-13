from datetime import datetime, timedelta

import bidict
import schedule
from discord.ext import commands

from cogs import config as cfg

Cog = commands.Cog


class ModsVote(Cog):
    def __init__(self, bot):
        self.bot = bot
        schedule.every().day.at("01:00").do(self.ping_mods).tag("cogs.modsvote")

    status_aliases = bidict.bidict(
        {
            1: ("mod-vote", "modvote", "vote", "escalate", "escalated", "m", "v", "e"),
            2: ("passed", "approved", "approve", "accept", "accepted", "a"),
            3: ("denied", "deny", "reject", "rejected", "d"),
            4: ("revised", "revise", "r"),
            5: ("implemented", "implement", "i"),
            6: ("removed", "remove"),
        }
    )

    @commands.command(
        brief="Post a new mods vote",
        help="`-modsvote <content>`: Post a new mods vote with <content> in the mods "
        "announcement channel.",
    )
    @commands.check(cfg.is_staff)
    async def modsvote(self, ctx, *, content):
        # add the item to db
        cursor = cfg.db.cursor()
        insert_sql = (
            "INSERT INTO mods_vote (content, status, create_date, "
            "update_date, deadline) VALUES (?, ?, ?, ?, ?)"
        )
        cursor.execute(
            insert_sql,
            (
                content,
                1,
                datetime.now(),
                datetime.now(),
                datetime.now()
                + timedelta(days=cfg.Config.config["modsvote_default_days"]),
            ),
        )
        vote_item_id = cursor.lastrowid

        try:
            deadline = self.get_timestamp(
                datetime.now()
                + timedelta(days=cfg.Config.config["modsvote_default_days"])
            )
            # post the content to mods-announcement
            output = (
                f"⏳    **Mods Vote `#{vote_item_id}`    "
                f"(Deadline: {deadline})**\n"
                f"{content}"
            )
            m = await self.bot.get_channel(cfg.Config.config["mod_vote_chan"]).send(
                output
            )
            await m.add_reaction("👍")
            await m.add_reaction("🤷")
            await m.add_reaction("👎")
        except Exception as e:
            # delete the item in db if connection error
            delete_sql = "DELETE FROM mods_vote WHERE rowid = ?"
            cursor.execute(delete_sql, (vote_item_id,))
            await ctx.send("Error occured! Please try again.")
            self.bot.logger.exception(e)
        else:
            # add the post url to db
            edit_sql = "UPDATE mods_vote SET msg_id = ? WHERE rowid = ?"
            cursor.execute(edit_sql, (m.id, vote_item_id))
            await ctx.send(f"Mods Vote #{vote_item_id} is posted.")
        finally:
            cfg.db.commit()

    @commands.command(
        brief="Edit a mods vote and reset the vote",
        help="`-modsvote_edit <number> <content>`: Replace the content of mods vote"
        " #<number> with <content>, reset the votes.",
    )
    @commands.check(cfg.is_staff)
    async def modsvote_edit(self, ctx, number: int, *, content):
        cursor = cfg.db.cursor()
        try:
            # get the item from db
            sql = "SELECT * FROM mods_vote WHERE rowid = ?"
            cursor.execute(sql, (str(number),))
            vote_item = cursor.fetchall()[0]

            # edit the content to mods-announcement and reset the votes
            message = await self.bot.get_channel(
                cfg.Config.config["mod_vote_chan"]
            ).fetch_message(vote_item[2])
            output = (
                f"⏳    **Mods Vote `#{number}`    "
                f"(Deadline: {self.get_timestamp(vote_item[5])})**\n{content}"
            )
            await message.edit(content=output)
            await message.clear_reactions()
            await message.add_reaction("👍")
            await message.add_reaction("🤷")
            await message.add_reaction("👎")
        except Exception as e:
            await ctx.send("Error occured! Please try again.")
            self.bot.logger.exception(e)
        else:
            # edit the content in db
            edit_sql = (
                "UPDATE mods_vote SET content = ?, status = ?, "
                "update_date = ? WHERE rowid = ?"
            )
            cursor.execute(edit_sql, (content, 1, datetime.now(), number))
            await ctx.send(f"Mods Vote #{number} is edited and votes are reset.")
        finally:
            cfg.db.commit()

    @commands.command(
        brief="Mark a mods vote as pending",
        help="`-modsvote_pending <number>`: Mark the status of mods vote "
        "#<number> as pending",
    )
    @commands.check(cfg.is_staff)
    async def modsvote_pending(self, ctx, number: int):
        cursor = cfg.db.cursor()
        try:
            # get the item from db
            sql = "SELECT * FROM mods_vote WHERE rowid = ?"
            cursor.execute(sql, (str(number),))
            vote_item = cursor.fetchall()[0]
            content = vote_item[0]
            msg_id = vote_item[2]

            # edit the content to mods-announcement
            message = await self.bot.get_channel(
                cfg.Config.config["mod_vote_chan"]
            ).fetch_message(msg_id)
            output = (
                f"⏳    **Mods Vote `#{number}`    "
                f"(Deadline: {self.get_timestamp(vote_item[5])})**\n{content}"
            )
            await message.edit(content=output)
        except Exception as e:
            await ctx.send("Error occured! Please try again.")
            self.bot.logger.exception(e)
        else:
            # edit the content in db
            edit_sql = (
                "UPDATE mods_vote SET status = ?, update_date = ? WHERE rowid = ?"
            )
            cursor.execute(edit_sql, (1, datetime.now(), number))
            await ctx.send(f"Mods Vote #{number} marked as pending.")
        finally:
            cfg.db.commit()

    @commands.command(
        aliases=[
            "modsvote_passed",
            "modsvote_approve",
            "modsvote_approved",
            "modsvote_accept",
            "modsvote_accepted",
        ],
        brief="Mark a mods vote as passed",
        help="`-modsvote_pass <number>`: Mark the status of mods vote "
        "#<number> as passed",
    )
    @commands.check(cfg.is_staff)
    async def modsvote_pass(self, ctx, number: int):
        cursor = cfg.db.cursor()
        try:
            # get the item from db
            sql = "SELECT * FROM mods_vote WHERE rowid = ?"
            cursor.execute(sql, (str(number),))
            vote_item = cursor.fetchall()[0]
            content = vote_item[0]
            msg_id = vote_item[2]

            # edit the content to mods-announcement
            message = await self.bot.get_channel(
                cfg.Config.config["mod_vote_chan"]
            ).fetch_message(msg_id)
            mods_vote_result = await self.get_mods_vote_result(msg_id)
            deadline = datetime.now() + timedelta(
                days=cfg.Config.config["modsvote_default_days"]
            )
            output = (
                f"👍    **Passed `#{number}`    "
                f"{mods_vote_result.result_string}    "
                f"(Deadline: {self.get_timestamp(deadline)})**\n{content}"
            )
            await message.edit(content=output)
        except Exception as e:
            await ctx.send("Error occured! Please try again.")
            self.bot.logger.exception(e)
        else:
            # edit the content in db
            edit_sql = (
                "UPDATE mods_vote SET status = ?, update_date = ?, "
                "deadline = ? WHERE rowid = ?"
            )
            cursor.execute(edit_sql, (2, datetime.now(), deadline, number))
            await ctx.send(f"Mods Vote #{number} marked as passed.")
        finally:
            cfg.db.commit()

    @commands.command(
        aliases=["modsvote_denied", "modsvote_reject", "modsvote_rejected"],
        brief="Mark a mods vote as rejected",
        help="`-modsvote_deny <number>`: Mark the status of mods vote #<number> "
        "as rejected",
    )
    @commands.check(cfg.is_staff)
    async def modsvote_deny(self, ctx, number: int):
        cursor = cfg.db.cursor()
        try:
            # get the item from db
            sql = "SELECT * FROM mods_vote WHERE rowid = ?"
            cursor.execute(sql, (str(number),))
            vote_item = cursor.fetchall()[0]
            content = vote_item[0]
            msg_id = vote_item[2]

            # edit the content to mods-announcement
            message = await self.bot.get_channel(
                cfg.Config.config["mod_vote_chan"]
            ).fetch_message(msg_id)
            mods_vote_result = await self.get_mods_vote_result(msg_id)
            output = (
                f"🚫    **Rejected `#{number}`    "
                f"{mods_vote_result.result_string}**"
                f"\n{content}"
            )
            await message.edit(content=output)
        except Exception as e:
            await ctx.send("Error occured! Please try again.")
            self.bot.logger.exception(e)
        else:
            # edit the content in db
            edit_sql = (
                "UPDATE mods_vote SET status = ?, update_date = ? WHERE rowid = ?"
            )
            cursor.execute(edit_sql, (3, datetime.now(), number))
            await ctx.send(f"Mods Vote #{number} marked as denied.")
        finally:
            cfg.db.commit()

    @commands.command(
        aliases=["modsvote_implement"],
        brief="Mark a mods vote as implemented",
        help="`-modsvote_implemented <number>`: Mark the status of mods vote "
        "#<number> as implemented",
    )
    @commands.check(cfg.is_staff)
    async def modsvote_implemented(self, ctx, number: int):
        cursor = cfg.db.cursor()
        try:
            # get the item from db
            sql = "SELECT * FROM mods_vote WHERE rowid = ?"
            cursor.execute(sql, (str(number),))
            vote_item = cursor.fetchall()[0]
            content = vote_item[0]
            msg_id = vote_item[2]

            # edit the content to mods-announcement
            message = await self.bot.get_channel(
                cfg.Config.config["mod_vote_chan"]
            ).fetch_message(msg_id)
            mods_vote_result = await self.get_mods_vote_result(msg_id)
            output = (
                f"{cfg.Config.config['check_emoji']}    **Implemented `#{number}`    "
                f"{mods_vote_result.result_string}** "
                f"\n{content}"
            )
            await message.edit(content=output)
        except Exception as e:
            await ctx.send("Error occured! Please try again.")
            self.bot.logger.exception(e)
        else:
            # edit the content in db
            edit_sql = (
                "UPDATE mods_vote SET status = ?, update_date = ? WHERE rowid = ?"
            )
            cursor.execute(edit_sql, (5, datetime.now(), number))
            await ctx.send(f"Mods Vote #{number} marked as implemented.")
        finally:
            cfg.db.commit()

    @commands.command(
        aliases=["modsvote_remove"],
        brief="Mark a mods vote as removed",
        help="`-modsvote_remove <number>`: Mark the status of mods vote "
        "#<number> as removed",
    )
    @commands.check(cfg.is_staff)
    async def modsvote_removed(self, ctx, number: int):
        cursor = cfg.db.cursor()
        try:
            # get the item from db
            sql = "SELECT * FROM mods_vote WHERE rowid = ?"
            cursor.execute(sql, (str(number),))
            vote_item = cursor.fetchall()[0]
            content = vote_item[0]
            msg_id = vote_item[2]

            # edit the content to mods-announcement
            message = await self.bot.get_channel(
                cfg.Config.config["mod_vote_chan"]
            ).fetch_message(msg_id)
            output = (
                f":skull_crossbones:     **Removed `#{number}`    "
                f"(Deadline: {self.get_timestamp(vote_item[5])})**\n{content}"
            )
            await message.edit(content=output)
        except Exception as e:
            await ctx.send("Error occured! Please try again.")
            self.bot.logger.exception(e)
        else:
            # edit the content in db
            edit_sql = (
                "UPDATE mods_vote SET status = ?, update_date = ? WHERE rowid = ?"
            )
            cursor.execute(edit_sql, (6, datetime.now(), number))
            await ctx.send(f"Mods Vote #{number} marked as removed.")
        finally:
            cfg.db.commit()

    @commands.command(
        brief="Change the deadline of a mods vote",
        help="`-modsvote_deadline <number> <days>`: Change the deadline of mods "
        "vote #<number> to <days> days after now.",
    )
    @commands.check(cfg.is_staff)
    async def modsvote_deadline(self, ctx, number: int, days: int):
        cursor = cfg.db.cursor()
        try:
            # get the item from db
            sql = "SELECT * FROM mods_vote WHERE rowid = ?"
            cursor.execute(sql, (str(number),))
            vote_item = cursor.fetchall()[0]
            content = vote_item[0]
            msg_id = vote_item[2]

            # edit the content to mods-announcement
            message = await self.bot.get_channel(
                cfg.Config.config["mod_vote_chan"]
            ).fetch_message(msg_id)
            deadline = self.get_timestamp(datetime.now() + timedelta(days=days))
            output = (
                f"⏳    **Mods Vote `#{number}`    (Deadline: {deadline})**"
                f"\n{content}"
            )
            await message.edit(content=output)
        except Exception as e:
            await ctx.send("Error occured! Please try again.")
            self.bot.logger.exception(e)
        else:
            # edit the content in db
            edit_sql = "UPDATE mods_vote SET deadline = ? WHERE rowid = ?"
            cursor.execute(edit_sql, (datetime.now() + timedelta(days=days), number))
            await ctx.send(f"Mods Vote #{number} deadline set to {deadline}.")
        finally:
            cfg.db.commit()

    def ping_mods(self, mode=None):
        self.bot.loop.create_task(self.check_modsvote())

    async def check_modsvote(self):
        cursor = cfg.db.cursor()
        # get pending items from db
        sql = "SELECT *, rowid FROM mods_vote WHERE status = 1 AND deadline < ?"
        cursor.execute(sql, (datetime.now(),))
        deadline_pending_items = cursor.fetchall()

        # check votes for each pending item
        for pending_item in deadline_pending_items:
            try:
                msg_id = pending_item[2]
                mods_vote_result = await self.get_mods_vote_result(msg_id)

                # ping the jackers
                pings = ", ".join([f"<@!{j}>" for j in mods_vote_result.to_ping])
                url = (
                    f"https://discord.com/channels/{cfg.Config.config['mods_guild']}"
                    f"/{cfg.Config.config['mod_vote_chan']}/{msg_id}"
                )
                if pings != "":
                    await self.bot.get_channel(cfg.Config.config["mod_chan"]).send(
                        f"{pings} Please vote on Mods Vote #{pending_item[6]} {url} "
                        f"`{self.truncate_string(pending_item[0])}`"
                    )
                else:
                    await self.bot.get_channel(cfg.Config.config["mod_chan"]).send(
                        f"<@&{cfg.Config.config['mod_role']}> "
                        f"Please finalize on Mods Vote #{pending_item[6]} {url} "
                        f"`{self.truncate_string(pending_item[0])}`"
                    )

            except self.NotFoundException:
                # if the message is deleted, mark the status as removed
                sql = "UPDATE mods_vote SET status = ? WHERE rowid = ?"
                cursor.execute(sql, (6, pending_item[6]))
                await self.bot.get_channel(cfg.Config.config["mod_chan"]).send(
                    f"Mods Vote #{pending_item[6]} status set as removed."
                )

        sql = "SELECT *, rowid FROM mods_vote WHERE status = 1"
        cursor.execute(sql)
        pending_items = cursor.fetchall()
        for pending_item in pending_items:
            try:
                msg_id = pending_item[2]
                mods_vote_result = await self.get_mods_vote_result(msg_id)

                # update message if enough for/against votes
                if mods_vote_result.status in ["passed", "rejected"]:
                    emoji = "🚀" if mods_vote_result.status == "passed" else "🥀"
                    message = await self.bot.get_channel(
                        cfg.Config.config["mod_vote_chan"]
                    ).fetch_message(msg_id)
                    output = (
                        f"{emoji}    **Mods Vote `#{pending_item[6]}`    "
                        f"(Deadline: {self.get_timestamp(pending_item[5])})**\n"
                        f"{pending_item[0]}"
                    )
                    await message.edit(content=output)

            except self.NotFoundException:
                # if the message is deleted, mark the status as removed
                sql = "UPDATE mods_vote SET status = ? WHERE rowid = ?"
                cursor.execute(sql, (6, pending_item[6]))
                await self.bot.get_channel(cfg.Config.config["mod_chan"]).send(
                    f"Mods Vote #{pending_item[6]} status set as removed."
                )

        # get passed items from db
        sql = "SELECT *, rowid FROM mods_vote WHERE status = 2 AND deadline < ?"
        cursor.execute(sql, (datetime.now(),))
        passed_items = cursor.fetchall()

        # ping mods if after deadline
        for passed_item in passed_items:
            try:
                msg_id = passed_item[2]
                mods_vote_result = await self.get_mods_vote_result(msg_id)
                url = (
                    f"https://discord.com/channels/{cfg.Config.config['mods_guild']}"
                    f"/{cfg.Config.config['mod_vote_chan']}/{msg_id}"
                )
                await self.bot.get_channel(cfg.Config.config["mod_chan"]).send(
                    f"<@&{cfg.Config.config['mod_role']}> "
                    f"Item not yet implemented: Mods Vote #{passed_item[6]} {url} "
                    f"`{self.truncate_string(passed_item[0])}`"
                )
            except self.NotFoundException:
                # if the message is deleted, mark the status as removed
                sql = "UPDATE mods_vote SET status = ? WHERE rowid = ?"
                cursor.execute(sql, (6, passed_item[6]))
                await self.bot.get_channel(cfg.Config.config["mod_chan"]).send(
                    f"Mods Vote #{passed_item[6]} status set as removed."
                )

    def get_mod_list(self):
        guild = self.bot.get_guild(cfg.Config.config["mods_guild"])
        moderator_role = guild.get_role(cfg.Config.config["moderator_role"])
        mods = [x.id for x in moderator_role.members]
        mod_in_training_role = guild.get_role(cfg.Config.config["mod_in_training_role"])
        mods += [x.id for x in mod_in_training_role.members]
        admin_role = guild.get_role(cfg.Config.config["admin_role"])
        mods += [x.id for x in admin_role.members]
        return mods

    def get_advisor_list(self):
        guild = self.bot.get_guild(cfg.Config.config["mods_guild"])
        advisor_role = guild.get_role(cfg.Config.config["advisor_role"])
        return [x.id for x in advisor_role.members]

    async def get_mods_vote_result(self, msg_id):
        modsvote_result = self.ModsVoteResult()
        mods_list = self.get_mod_list()
        advisors_list = self.get_advisor_list()
        modsvote_result.mods_list = mods_list
        modsvote_result.advisors_list = advisors_list

        try:
            message = await self.bot.get_channel(
                cfg.Config.config["mod_vote_chan"]
            ).fetch_message(msg_id)
        except Exception as e:
            if e.code == 10008:
                raise self.NotFoundException() from e
        else:
            for reaction in message.reactions:
                if reaction.emoji in ["👍", "🤷", "👎"]:
                    async for reactor in reaction.users():
                        if reaction.emoji == "👍" and reactor.id in mods_list:
                            modsvote_result.mods_for.append(reactor.id)
                        elif reaction.emoji == "👍" and reactor.id in advisors_list:
                            modsvote_result.advisors_for.append(reactor.id)
                        elif reaction.emoji == "🤷" and reactor.id in mods_list:
                            modsvote_result.mods_abstain.append(reactor.id)
                        elif reaction.emoji == "🤷" and reactor.id in advisors_list:
                            modsvote_result.advisors_abstain.append(reactor.id)
                        elif reaction.emoji == "👎" and reactor.id in mods_list:
                            modsvote_result.mods_against.append(reactor.id)
                        elif reaction.emoji == "👎" and reactor.id in advisors_list:
                            modsvote_result.advisors_against.append(reactor.id)

            return modsvote_result

    def truncate_string(self, text):
        return f"{text[:200]}..." if len(text) > 200 else text

    class ModsVoteResult:
        def __init__(self):
            self.mods_list = []
            self.advisors_list = []
            self.mods_for = []
            self.mods_abstain = []
            self.mods_against = []
            self.advisors_for = []
            self.advisors_abstain = []
            self.advisors_against = []

        @property
        def for_count(self):
            return self.format_vote_count(
                len(self.mods_for) + len(self.advisors_for) * 0.5
            )

        @property
        def abstain_count(self):
            return self.format_vote_count(
                len(self.mods_abstain) + len(self.advisors_abstain) * 0.5
            )

        @property
        def against_count(self):
            return self.format_vote_count(
                len(self.mods_against) + len(self.advisors_against) * 0.5
            )

        @property
        def total(self):
            return len(self.mods_list) + len(self.advisors_list) * 0.5

        @property
        def status(self):
            if (self.for_count > self.total * 0.5) and (
                self.against_count < self.total * 0.5
            ):
                return "passed"
            elif (self.against_count > self.total * 0.5) and (
                self.for_count < self.total * 0.5
            ):
                return "rejected"
            else:
                return "pending"

        @property
        def result_string(self):
            return (
                f"({self.for_count}, {self.abstain_count}, {self.against_count} / "
                f"{len(self.mods_list)}+{len(self.advisors_list)})"
            )

        @property
        def to_ping(self):
            # if result not yet decided, ping all unvoted mods and advisors
            if self.status == "pending":
                exclusion_set = set(
                    self.mods_for
                    + self.mods_abstain
                    + self.mods_against
                    + self.advisors_for
                    + self.advisors_abstain
                    + self.advisors_against
                )
                return [
                    item
                    for item in self.mods_list + self.advisors_list
                    if item not in exclusion_set
                ]
            # if result already decided, ping all unvoted mods
            else:
                exclusion_set = set(
                    self.mods_for + self.mods_abstain + self.mods_against
                )
                return [item for item in self.mods_list if item not in exclusion_set]

        def format_vote_count(self, count):
            return int(count) if int(count) == count else count

    class NotFoundException(Exception):
        pass

    def get_timestamp(self, dt):
        if type(dt) is str:
            dt = datetime.strptime(dt, "%Y-%m-%d %H:%M:%S.%f")
        epoch = int(dt.timestamp())
        return f"<t:{epoch}:R>"


async def setup(bot):
    await bot.add_cog(ModsVote(bot))
