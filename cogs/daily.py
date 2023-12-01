import contextlib
import threading
from datetime import datetime, timedelta

import discord
import openpyxl
import schedule
from discord.ext import commands

from cogs import config as cfg
from utils import potd_utils

Cog = commands.Cog

POTD_RANGE = "POTD!A2:S"
CURATOR_RANGE = "Curators!A3:E"

days = [None, "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


class Daily(Cog):
    def __init__(self, bot: commands.Bot):
        self.listening_in_channel = -1
        self.to_send = ""
        self.bot = bot
        self.ping_daily = False
        self.late = False
        self.requested_number = -1
        self.dm_list = []
        self.timer = None

        reply = (
            cfg.Config.service.spreadsheets()
            .values()
            .get(spreadsheetId=cfg.Config.config["potd_sheet"], range=POTD_RANGE)
            .execute()
        )
        values = reply.get("values", [])
        self.latest_potd = int(values[0][0])

        cursor = cfg.db.cursor()
        cursor.execute(
            """INSERT OR IGNORE INTO settings (setting, value) VALUES
            ('potd_dm', 'True')
            """
        )
        cfg.db.commit()
        cursor.execute("SELECT value FROM settings WHERE setting = 'potd_dm'")
        self.enable_dm = cursor.fetchone()[0] == "True"

        schedule.every().day.at("10:00").do(self.schedule_potd).tag("cogs.daily")
        schedule.every().day.at("09:00").do(lambda: self.schedule_potd(1)).tag(
            "cogs.daily"
        )
        schedule.every().day.at("07:00").do(lambda: self.schedule_potd(3)).tag(
            "cogs.daily"
        )
        schedule.every().day.at("04:00").do(lambda: self.schedule_potd(6)).tag(
            "cogs.daily"
        )
        schedule.every().day.at("22:00").do(lambda: self.schedule_potd(12)).tag(
            "cogs.daily"
        )

    @commands.command()
    @commands.check(potd_utils.is_pc)
    async def reset_potd(self, ctx=None):
        self.requested_number = -1
        self.listening_in_channel = -1
        self.to_send = ""
        self.late = False
        self.ping_daily = False
        self.dm_list = []
        with contextlib.suppress(Exception):
            self.timer.cancel()
        self.timer = None

    def reset_if_necessary(self):
        if self.listening_in_channel != -1:
            self.bot.loop.create_task(self.reset_potd())

    def prepare_dms(self, potd_row):
        def should_dm(x):
            for i in range(4):
                if (
                    ["a", "c", "g", "n"][i] in potd_row[5].lower()
                    and x[1][4 * i] != "x"
                    and (
                        int(x[1][4 * i : 4 * i + 2])
                        <= d
                        <= int(x[1][4 * i + 2 : 4 * i + 4])
                    )
                ):
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

    def schedule_potd(self, mode=None):
        self.bot.loop.create_task(self.check_potd(mode))

    def responsible(
        self, potd_id: int, urgent: bool = False
    ):  # Mentions of responsible curators
        # Get stuff from the sheet (API call)
        potds = (
            cfg.Config.service.spreadsheets()
            .values()
            .get(spreadsheetId=cfg.Config.config["potd_sheet"], range=POTD_RANGE)
            .execute()
            .get("values", [])
        )
        curators = (
            cfg.Config.service.spreadsheets()
            .values()
            .get(spreadsheetId=cfg.Config.config["potd_sheet"], range=CURATOR_RANGE)
            .execute()
            .get("values", [])
        )
        try:
            i = int(potds[0][0]) - potd_id
        except ValueError:
            return "Invalid entry (A2) in spreadsheet! "
        potd_row = potds[i]

        # Searches for relevant curators
        mentions = ""
        r_list = []
        try:
            day = str(days.index(str(potd_row[2])))
        except Exception:
            return "Day not recognized. "
        for curator in curators:
            with contextlib.suppress(Exception):
                if curator[4] == day:
                    mentions += f"<@{curator[0]}> "
                    r_list.append(curator)
        if urgent:
            return f'{mentions}<@&{cfg.Config.config["problem_curator_role"]}> '
        if mentions == "":
            return f"No responsible curators found for the potd on {potd_row[1]}!"

        # Searches for curator whose last curation on this day of
        # the week was longest ago.
        i += 7
        while (i < len(potds)) and (len(r_list) > 1):
            with contextlib.suppress(Exception):
                for curator in r_list:
                    if curator[0] == potd_utils.curator_id(curators, potds[i][3]):
                        r_list.remove(curator)
            i += 7
        return f"<@{r_list[0][0]}> "

    async def potd_embedded(self, ctx, *, number: int):
        # It can only handle one at a time!
        if self.listening_in_channel != -1:
            await ctx.send("Please wait until the previous potd call has finished!")
            return

        reply = (
            cfg.Config.service.spreadsheets()
            .values()
            .get(spreadsheetId=cfg.Config.config["potd_sheet"], range=POTD_RANGE)
            .execute()
        )
        values = reply.get("values", [])
        current_potd = int(
            values[0][0]
        )  # this will be the top left cell which indicates the latest added potd
        potd_row = values[current_potd - number]  # this gets the row requested

        # Create the message to send
        to_tex = ""
        try:
            to_tex = (
                "<@419356082981568522>\n```tex\n \\textbf{Day "
                + str(number)
                + "} --- "
                + str(potd_row[2])
                + " "
                + str(potd_row[1])
                + "\\vspace{11pt}\\\\\\setlength\\parindent{1.5em}"
                + str(potd_row[8])
                + "```"
            )
        except IndexError:
            await ctx.send(f"There is no potd for day {number}. ")
            return
        print(to_tex)

        # Finish up
        self.requested_number = int(potd_row[0])
        self.latest_potd = int(potd_row[0])
        self.to_send = potd_utils.generate_source(potd_row)
        self.listening_in_channel = ctx.channel.id
        self.late = True
        await ctx.send(to_tex, delete_after=20)

    async def check_potd(self, mode=None):
        # Get the potds from the sheet (API call)
        potds = (
            cfg.Config.service.spreadsheets()
            .values()
            .get(spreadsheetId=cfg.Config.config["potd_sheet"], range=POTD_RANGE)
            .execute()
            .get("values", [])
        )

        # Check today's potd
        if mode is None:
            time_for_date = datetime.now()
            date = time_for_date.strftime("%d %b %Y")
            soon = [
                (time_for_date + timedelta(days=i)).strftime("%d %b %Y")
                for i in range(1, 4)
            ]
        else:
            time_for_date = datetime.now() + timedelta(hours=mode)
            date = time_for_date.strftime("%d %b %Y")
            soon = [date]
        if date[0] == "0":
            date = date[1:]
        for i in range(len(soon)):
            if soon[i][0] == "0":
                soon[i] = soon[i][1:]
        passed_current = False
        potd_row = None
        fail = False
        remind = []
        curator_role = (
            await self.bot.fetch_guild(cfg.Config.config["mods_guild"])
        ).get_role(cfg.Config.config["problem_curator_role"])
        j = 1  # TESTING
        for potd in potds:
            j += 1  # TESTING
            if len(potd) < 2:  # TESTING
                await self.bot.get_channel(cfg.Config.config["log_channel"]).send(
                    f"Invalid entry at row {j}, potd = {potd}"
                )
            if (
                passed_current and len(potd) < 8
            ):  # Then there has not been a potd on that day.
                fail = True
                await curator_role.edit(mentionable=True)
                await self.bot.get_channel(cfg.Config.config["helper_lounge"]).send(
                    f"There was no potd on {potd[1]}! "
                    f"{self.responsible(int(potd[0]), True)}"
                )
                await curator_role.edit(mentionable=False)
            if potd[1] == date:
                passed_current = True
                potd_row = potd
                if len(potd) < 8 and (mode is None):  # There is no potd.
                    fail = True
                    await curator_role.edit(mentionable=True)
                    await self.bot.get_channel(cfg.Config.config["helper_lounge"]).send(
                        f"There is no potd today! "
                        f"{self.responsible(int(potd[0]), True)}"
                    )
                    await curator_role.edit(mentionable=False)
            if potd[1] in soon:
                if len(potd) < 8:  # Then there is no potd on that day.
                    remind.append(int(potd[0]))
                soon.remove(potd[1])
        if soon != []:
            await self.bot.get_channel(cfg.Config.config["helper_lounge"]).send(
                "Insufficient rows in the potd sheet! "
            )
        if remind != []:
            mentions = "".join(self.responsible(i, mode in [1, 3]) for i in remind)
            await curator_role.edit(mentionable=True)
            await self.bot.get_channel(cfg.Config.config["helper_lounge"]).send(
                f"Remember to fill in your POTDs! {mentions}"
            )
            await curator_role.edit(mentionable=False)
        if fail or mode is not None:
            return

        print("l123")
        # Otherwise, everything has passed and we are good to go.
        # Create the message to send
        to_tex = (
            "<@419356082981568522>\n```tex\n\\textbf{Day "
            + str(potd_row[0])
            + "} --- "
            + str(potd_row[2])
            + " "
            + str(potd_row[1])
            + "\\vspace{11pt}\\\\\\setlength\\parindent{1.5em}"
            + str(potd_row[8])
            + "```"
        )
        print(to_tex)

        # Finish up
        self.requested_number = int(potd_row[0])
        self.latest_potd = int(potd_row[0])
        self.prepare_dms(potd_row)
        self.to_send = potd_utils.generate_source(potd_row, False)
        self.listening_in_channel = cfg.Config.config["potd_channel"]
        self.ping_daily = True
        self.late = False
        await self.bot.get_channel(cfg.Config.config["potd_channel"]).send(
            to_tex, delete_after=20
        )
        await self.create_potd_forum_post(self.requested_number)
        await potd_utils.edit_source(self.bot, self.requested_number - 1)
        print("l149")
        # In case Paradox unresponsive
        self.timer = threading.Timer(20, self.reset_if_necessary)
        self.timer.start()

    async def create_potd_forum_post(self, number):
        forum = self.bot.get_channel(cfg.Config.config["potd_forum"])
        await forum.create_thread(name=f"POTD {number}", content="potd")

    @Cog.listener()
    async def on_message(self, message: discord.Message):
        if (
            message.channel.id != self.listening_in_channel
            or int(message.author.id) != cfg.Config.config["paradox_id"]
        ):
            return
        self.listening_in_channel = -1  # Prevent reset
        source_msg = await message.channel.send(embed=self.to_send)
        await source_msg.add_reaction("👍")
        if self.late:
            await source_msg.add_reaction("⏰")

        if message.channel.id == cfg.Config.config["potd_channel"]:
            # record the ID of the source_msg if it is in POTD channel
            # get the row and column to update
            column = openpyxl.utils.get_column_letter(
                cfg.Config.config["potd_sheet_message_id_col"] + 1
            )
            reply = (
                cfg.Config.service.spreadsheets()
                .values()
                .get(spreadsheetId=cfg.Config.config["potd_sheet"], range=POTD_RANGE)
                .execute()
            )
            values = reply.get("values", [])
            current_potd = int(
                values[0][0]
            )  # this will be the top left cell which indicates the latest added potd
            row = (
                current_potd - self.requested_number + 2
            )  # this gets the row requested
            # update the source_msg in the sheet
            request = (
                cfg.Config.service.spreadsheets()
                .values()
                .update(
                    spreadsheetId=cfg.Config.config["potd_sheet"],
                    range=f"{column}{row}",
                    valueInputOption="RAW",
                    body={
                        "range": f"{column}{row}",
                        "values": [[str(source_msg.id)]],
                    },
                )
            )
            request.execute()

            # record the link to rendered image if it is in POTD channel
            # get the row and column to update
            column = openpyxl.utils.get_column_letter(
                cfg.Config.config["potd_sheet_image_link_col"] + 1
            )
            reply = (
                cfg.Config.service.spreadsheets()
                .values()
                .get(spreadsheetId=cfg.Config.config["potd_sheet"], range=POTD_RANGE)
                .execute()
            )
            values = reply.get("values", [])
            current_potd = int(
                values[0][0]
            )  # this will be the top left cell which indicates the latest added potd
            row = (
                current_potd - self.requested_number + 2
            )  # this gets the row requested
            # update the source_msg in the sheet
            request = (
                cfg.Config.service.spreadsheets()
                .values()
                .update(
                    spreadsheetId=cfg.Config.config["potd_sheet"],
                    range=f"{column}{row}",
                    valueInputOption="RAW",
                    body={
                        "range": f"{column}{row}",
                        "values": [[str(message.attachments[0].proxy_url)]],
                    },
                )
            )
            request.execute()

        bot_log = self.bot.get_channel(cfg.Config.config["log_channel"])

        ping_msg = None
        if self.ping_daily:
            r = self.bot.get_guild(cfg.Config.config["mods_guild"]).get_role(
                cfg.Config.config["potd_role"]
            )
            await r.edit(mentionable=True)
            ping_msg = await message.channel.send(
                f'<@&{cfg.Config.config["potd_role"]}>'
            )
            await r.edit(mentionable=False)

            if self.enable_dm:
                bot_spam = self.bot.get_channel(cfg.Config.config["bot_spam_channel"])
                potd_discussion_channel = self.bot.get_channel(
                    cfg.Config.config["potd_discussion_channel"]
                )

                ping_embed = discord.Embed(
                    title=f"POTD {self.latest_potd} has been posted: ",
                    description=f"{potd_discussion_channel.mention}\n"
                    f"{message.jump_url}",
                    colour=0xDCDCDC,
                )
                for field in self.to_send.to_dict()["fields"]:
                    ping_embed.add_field(name=field["name"], value=field["value"])
                if message.attachments == []:
                    await bot_log.send("No attachments found! ")
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
                        msg = (
                            "Remember to turn on DMs from this server to get private "
                            "notifications! "
                        )
                        for id in dm_failed:
                            msg += f"<@{id}> "
                        await bot_spam.send(msg, embed=ping_embed)

        if message.channel.id == cfg.Config.config["potd_channel"]:
            try:
                await message.publish()
                await source_msg.publish()
            except Exception:
                await bot_log.send("Failed to publish!")

        cursor = cfg.db.cursor()
        if ping_msg is None:
            cursor.execute(
                "INSERT INTO potd_info (potd_id, problem_msg_id, source_msg_id,"
                f" ping_msg_id) VALUES ('{self.latest_potd}', '{message.id}', "
                f"'{source_msg.id}', '')"
            )
        else:
            cursor.execute(
                "INSERT INTO potd_info (potd_id, problem_msg_id, source_msg_id, "
                f"ping_msg_id) VALUES ('{self.latest_potd}', '{message.id}', "
                f"'{source_msg.id}', '{ping_msg.id}')"
            )
        cfg.db.commit()

        await self.reset_potd()
        await bot_log.send("POTD execution successful.")

    @commands.command()
    @commands.check(cfg.is_staff)
    async def enable_potd_dm(self, ctx, status: bool = None):
        self.enable_dm = not self.enable_dm if status is None else status
        cursor = cfg.db.cursor()
        cursor.execute(
            f"UPDATE settings SET value = '{self.enable_dm}' WHERE setting = 'potd_dm'"
        )
        cfg.db.commit()
        await self.bot.get_channel(cfg.Config.config["log_channel"]).send(
            f"**POTD notifications set to `{self.enable_dm}` "
            f"by {ctx.author.nick} ({ctx.author.id})**"
        )

    @commands.command(
        aliases=["potd"], brief="Displays the potd with the provided number. "
    )
    @commands.check(potd_utils.is_pc)
    async def potd_display(self, ctx, number: int):
        # It can only handle one at a time!
        if self.listening_in_channel != -1:
            await potd_utils.dm_or_channel(
                ctx.author,
                self.bot.get_channel(cfg.Config.config["helper_lounge"]),
                "Please wait until the previous call has finished!",
            )
            return

        # Read from the spreadsheet
        reply = (
            cfg.Config.service.spreadsheets()
            .values()
            .get(spreadsheetId=cfg.Config.config["potd_sheet"], range=POTD_RANGE)
            .execute()
        )
        values = reply.get("values", [])
        current_potd = int(
            values[0][0]
        )  # this will be the top left cell which indicates the latest added potd
        potd_row = values[current_potd - number]  # this gets the row requested

        # Create the message to send
        to_tex = ""
        try:
            to_tex = (
                "<@419356082981568522>\n```tex\n\\textbf{Day "
                + str(potd_row[0])
                + "} --- "
                + str(potd_row[2])
                + " "
                + str(potd_row[1])
                + "\\vspace{11pt}\\\\\\setlength\\parindent{1.5em}"
                + str(potd_row[8])
                + "```"
            )
        except IndexError:
            await potd_utils.dm_or_channel(
                ctx.author,
                self.bot.get_channel(cfg.Config.config["helper_lounge"]),
                f"There is no potd for day {number}. ",
            )
            return
        print(to_tex)

        # Finish up
        self.requested_number = int(potd_row[0])
        self.latest_potd = int(potd_row[0])
        self.prepare_dms(potd_row)
        self.to_send = potd_utils.generate_source(potd_row)
        self.listening_in_channel = ctx.channel.id
        self.late = True
        self.ping_daily = False
        await ctx.send(to_tex, delete_after=20)
        # In case Paradox unresponsive
        self.timer = threading.Timer(20, self.reset_if_necessary)
        self.timer.start()

    @commands.command(
        aliases=["remove_potd"], brief="Deletes the potd with the provided number. "
    )
    @commands.check(potd_utils.is_pc)
    async def delete_potd(self, ctx, number: int):
        # It can only handle one at a time!
        if self.listening_in_channel not in [-1, -2]:
            await potd_utils.dm_or_channel(
                ctx.author,
                self.bot.get_channel(cfg.Config.config["helper_lounge"]),
                "Please wait until the previous call has finished!",
            )
            return
        self.listening_in_channel = 0

        # Delete old POTD
        cursor = cfg.db.cursor()
        cursor.execute(
            f"SELECT problem_msg_id, source_msg_id, ping_msg_id FROM potd_info "
            f"WHERE potd_id = '{number}'"
        )
        result = cursor.fetchall()
        cursor.execute(f"DELETE FROM potd_info WHERE potd_id = '{number}'")
        cfg.db.commit()
        for i in result:
            for j in i:
                with contextlib.suppress(Exception):
                    await self.bot.get_channel(
                        cfg.Config.config["potd_channel"]
                    ).get_partial_message(int(j)).delete()
        self.listening_in_channel = -1

    @commands.command(
        aliases=["update_potd"], brief="Replaces the potd with the provided number. "
    )
    @commands.check(potd_utils.is_pc)
    async def replace_potd(self, ctx, number: int):
        # It can only handle one at a time!
        if self.listening_in_channel != -1:
            await potd_utils.dm_or_channel(
                ctx.author,
                self.bot.get_channel(cfg.Config.config["helper_lounge"]),
                "Please wait until the previous call has finished!",
            )
            return

        await self.delete_potd(ctx, number)
        await self.potd_display(ctx, number)

async def setup(bot):
    await bot.add_cog(Daily(bot))
