import random
from collections import defaultdict
from datetime import datetime

from discord.ext import commands
from discord.ext.commands import BucketType

from cogs import config as cfg
from utils import potd_utils

Cog = commands.Cog

POTD_RANGE = "POTD!A2:S"


class Marking(Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(aliases=["mark"], brief="Mark the POTD you have solved")
    @commands.cooldown(1, 5, BucketType.user)
    async def potd_mark(self, ctx, *, user_input: str):
        # parse input
        try:
            potd_numbers = [int(i) for i in user_input.split(",")]
        except ValueError:
            await ctx.send("Error: The input contains non-integer values.")
            return

        if len(potd_numbers) > 200:
            await ctx.send("Please don't send more than 200 POTDs in each call.")
            return

        # insert to DB
        added = []
        already_solved = []
        no_potd = []
        no_hint = []
        has_discussion = []
        sheet = potd_utils.get_potd_sheet()
        for potd_number in potd_numbers:
            cursor = cfg.db.cursor()
            cursor.execute(
                "SELECT discord_user_id, potd_id, create_date FROM potd_solves "
                f"WHERE discord_user_id = {ctx.author.id} "
                f"AND potd_id = {potd_number}"
            )
            result = cursor.fetchall()
            if len(result) > 0:
                already_solved.append(str(potd_number))
            else:
                cursor.execute(
                    f"INSERT INTO potd_solves (discord_user_id, potd_id, create_date) "
                    f"VALUES ('{ctx.author.id}', '{potd_number}', '{datetime.now()}')"
                )
                cursor.execute(
                    f"DELETE FROM potd_read WHERE discord_user_id = {ctx.author.id} "
                    f"AND potd_id = {potd_number}"
                )
                cursor.execute(
                    f"DELETE FROM potd_todo WHERE discord_user_id = {ctx.author.id} "
                    f"AND potd_id = {potd_number}"
                )
                added.append(str(potd_number))

            potd_row = potd_utils.get_potd_row(potd_number, sheet)
            if (
                potd_row is None
                or len(potd_row) <= cfg.Config.config["potd_sheet_statement_col"]
            ):
                no_potd.append(str(potd_number))
            else:
                if (
                    potd_row is not None
                    and random.random() < 0.25
                    and (
                        len(potd_row) <= cfg.Config.config["potd_sheet_hint1_col"]
                        or potd_row[cfg.Config.config["potd_sheet_hint1_col"]] is None
                    )
                ):
                    no_hint.append(str(potd_number))
                if potd_row is not None and (
                    len(potd_row) > cfg.Config.config["potd_sheet_discussion_col"]
                    and potd_row[cfg.Config.config["potd_sheet_discussion_col"]]
                    is not None
                    and potd_row[cfg.Config.config["potd_sheet_discussion_col"]] != ""
                ):
                    has_discussion.append(str(potd_number))

        # send confirm message
        messages = []
        if added:
            if len(added) == 1:
                messages.append(
                    f"POTD {added[0]} is added to your solved list. "
                    f"Use `-rate {added[0]} <rating>` if you want to rate the "
                    "difficulty of this problem."
                )
            else:
                messages.append(
                    f'POTD {",".join(added)} are added to your solved list.'
                )
        if already_solved:
            if len(already_solved) == 1:
                messages.append(
                    f"POTD {already_solved[0]} is already in your solved list."
                )
            else:
                messages.append(
                    f'POTD {",".join(already_solved)} are already in your solved list.'
                )
        if no_potd:
            if len(no_potd) == 1:
                messages.append(
                    f"There is no POTD {no_potd[0]}. "
                    "Are you sure you have inputted the correct number?"
                )
            else:
                messages.append(
                    f'There are no POTD  {",".join(no_potd)}. '
                    "Are you sure you have inputted the correct number?"
                )
        if no_hint:
            if len(no_hint) == 1:
                messages.append(
                    f"There is no hint for POTD {no_hint[0]}. "
                    "Would you like to contribute one? "
                    f"Contact <@{cfg.Config.config['staffmail_id']}> to submit a hint!"
                )
            else:
                messages.append(
                    f"There are no hint for POTD {','.join(no_hint)}. "
                    "Would you like to contribute one? "
                    f"Contact <@{cfg.Config.config['staffmail_id']}> to submit a hint!"
                )
        if has_discussion:
            if len(has_discussion) == 1:
                messages.append(
                    f"There is discussion for POTD {has_discussion[0]}. "
                    "Use `-discussion {has_discussion[0]}` to see the discussion."
                )
            else:
                messages.append(
                    f"Ther are discussions for POTD {','.join(has_discussion)}."
                    "Use `-discussion <number>` to see the discussions."
                )
        message = "\n".join(messages)
        await ctx.send(message)

    @commands.command(aliases=["unmark"], brief="Unmark the POTD from your solved list")
    @commands.cooldown(1, 5, BucketType.user)
    async def potd_unmark(self, ctx, *, user_input: str):
        # parse input
        try:
            potd_numbers = [int(i) for i in user_input.split(",")]
        except ValueError:
            await ctx.send("Error: The input contains non-integer values.")
            return

        if len(potd_numbers) > 200:
            await ctx.send("Please don't send more than 200 POTDs in each call.")
            return

        # delete from DB
        for potd_number in potd_numbers:
            cursor = cfg.db.cursor()
            cursor.execute(
                "DELETE FROM potd_solves "
                f"WHERE discord_user_id = {ctx.author.id} AND potd_id = {potd_number}"
            )

        # send confirm message
        if len(potd_numbers) == 1:
            await ctx.send(f"POTD {potd_numbers[0]} is removed from your solved list. ")
        else:
            await ctx.send(
                f'POTD {",".join(list(map(str,potd_numbers)))} are removed from your '
                "solved list. "
            )

    @commands.command(aliases=["read"], brief="Mark the POTD you have read")
    @commands.cooldown(1, 5, BucketType.user)
    async def potd_read(self, ctx, *, user_input: str):
        # parse input
        try:
            potd_numbers = [int(i) for i in user_input.split(",")]
        except ValueError:
            await ctx.send("Error: The input contains non-integer values.")
            return

        if len(potd_numbers) > 200:
            await ctx.send("Please don't send more than 200 POTDs in each call.")
            return

        # insert to DB
        added = []
        already_read = []
        no_potd = []
        no_hint = []
        has_discussion = []
        sheet = potd_utils.get_potd_sheet()
        for potd_number in potd_numbers:
            cursor = cfg.db.cursor()
            cursor.execute(
                "SELECT discord_user_id, potd_id, create_date FROM potd_read "
                f"WHERE discord_user_id = {ctx.author.id} "
                f"AND potd_id = {potd_number}"
            )
            result = cursor.fetchall()
            if len(result) > 0:
                already_read.append(str(potd_number))
            else:
                cursor.execute(
                    "INSERT INTO potd_read (discord_user_id, potd_id, create_date) "
                    f"VALUES ('{ctx.author.id}', '{potd_number}', '{datetime.now()}')"
                )
                cursor.execute(
                    f"DELETE FROM potd_solves WHERE discord_user_id = {ctx.author.id} "
                    f"AND potd_id = {potd_number}"
                )
                cursor.execute(
                    f"DELETE FROM potd_todo WHERE discord_user_id = {ctx.author.id} "
                    f"AND potd_id = {potd_number}"
                )
                added.append(str(potd_number))

            potd_row = potd_utils.get_potd_row(potd_number, sheet)
            if (
                potd_row is None
                or len(potd_row) <= cfg.Config.config["potd_sheet_statement_col"]
            ):
                no_potd.append(str(potd_number))
            else:
                if (
                    potd_row is not None
                    and random.random() < 0.25
                    and (
                        len(potd_row) <= cfg.Config.config["potd_sheet_hint1_col"]
                        or potd_row[cfg.Config.config["potd_sheet_hint1_col"]] is None
                    )
                ):
                    no_hint.append(str(potd_number))
                if potd_row is not None and (
                    len(potd_row) > cfg.Config.config["potd_sheet_discussion_col"]
                    and potd_row[cfg.Config.config["potd_sheet_discussion_col"]]
                    is not None
                    and potd_row[cfg.Config.config["potd_sheet_discussion_col"]] != ""
                ):
                    has_discussion.append(str(potd_number))

        # send confirm message
        messages = []
        if added:
            if len(added) == 1:
                messages.append(f"POTD {added[0]} is added to your read list.")
            else:
                messages.append(f'POTD {",".join(added)} are added to your read list.')
        if already_read:
            if len(already_read) == 1:
                messages.append(f"POTD {already_read[0]} is already in your read list.")
            else:
                messages.append(
                    f'POTD {",".join(already_read)} are already in your read list.'
                )
        if no_potd:
            if len(no_potd) == 1:
                messages.append(
                    f"There is no POTD {no_potd[0]}. "
                    "Are you sure you have inputted the correct number?"
                )
            else:
                messages.append(
                    f'There are no POTD  {",".join(no_potd)}. '
                    "Are you sure you have inputted the correct number?"
                )
        if no_hint:
            if len(no_hint) == 1:
                messages.append(
                    f"There is no hint for POTD {no_hint[0]}. "
                    "Would you like to contribute one? "
                    f"Contact <@{cfg.Config.config['staffmail_id']}> to submit a hint!"
                )
            else:
                messages.append(
                    f"There are no hint for POTD {','.join(no_hint)}. "
                    "Would you like to contribute one? "
                    f"Contact <@{cfg.Config.config['staffmail_id']}> to submit a hint!"
                )
        if has_discussion:
            if len(has_discussion) == 1:
                messages.append(
                    f"There is discussion for POTD {has_discussion[0]}. "
                    f"Use `-discussion {has_discussion[0]}` to see the discussion."
                )
            else:
                messages.append(
                    f"Ther are discussions for POTD {','.join(has_discussion)}. "
                    "Use `-discussion <number>` to see the discussions."
                )
        message = "\n".join(messages)
        await ctx.send(message)

    @commands.command(aliases=["unread"], brief="Unmark the POTD from your read list")
    @commands.cooldown(1, 5, BucketType.user)
    async def potd_unread(self, ctx, *, user_input: str):
        # parse input
        try:
            potd_numbers = [int(i) for i in user_input.split(",")]
        except ValueError:
            await ctx.send("Error: The input contains non-integer values.")
            return

        if len(potd_numbers) > 200:
            await ctx.send("Please don't send more than 200 POTDs in each call.")
            return

        # delete from DB
        for potd_number in potd_numbers:
            cursor = cfg.db.cursor()
            cursor.execute(
                "DELETE FROM potd_read "
                f"WHERE discord_user_id = {ctx.author.id} AND potd_id = {potd_number}"
            )

        # send confirm message
        if len(potd_numbers) == 1:
            await ctx.send(f"POTD {potd_numbers[0]} is removed from your read list. ")
        else:
            await ctx.send(
                f'POTD {",".join(list(map(str,potd_numbers)))} are removed from your '
                "read list. "
            )

    @commands.command(
        aliases=["solved"],
        brief="Show the POTDs you have solved or read",
        help="`-solved`: Show the POTDs you have solved or read.\n"
        "`-solved d`: Show the POTDs you have solved or read, ordered by "
        "difficulties.\n"
        "`-solved s`: Show the POTDs you have solved or read, divided into the four "
        "subjects.\n",
    )
    @commands.cooldown(1, 5, BucketType.user)
    async def potd_solved(self, ctx, flag=None):
        solved = potd_utils.get_potd_solved(ctx)
        read = potd_utils.get_potd_read(ctx)

        potd_rows = (
            cfg.Config.service.spreadsheets()
            .values()
            .get(spreadsheetId=cfg.Config.config["potd_sheet"], range=POTD_RANGE)
            .execute()
            .get("values", [])
        )
        current_potd = int(potd_rows[0][0])

        if len(solved) > 0:
            await self.generate_potd_list_output_string(
                solved, potd_rows, current_potd, flag, "solved", ctx
            )
        if len(read) > 0:
            await self.generate_potd_list_output_string(
                read, potd_rows, current_potd, flag, "read", ctx
            )
        if len(solved) == 0 and len(read) == 0:
            await ctx.send("Your solved list and read list are empty.")

    @commands.command(aliases=["todo"], brief="Mark the POTD into your TODO list")
    @commands.cooldown(1, 5, BucketType.user)
    async def potd_todo(self, ctx, *, user_input: str):
        # parse input
        try:
            potd_numbers = [int(i) for i in user_input.split(",")]
        except ValueError:
            await ctx.send("Error: The input contains non-integer values.")
            return

        if len(potd_numbers) > 200:
            await ctx.send("Please don't send more than 200 POTDs in each call.")
            return

        # insert to DB
        added = []
        already_todo = []
        for potd_number in potd_numbers:
            cursor = cfg.db.cursor()
            cursor.execute(
                "SELECT discord_user_id, potd_id, create_date FROM potd_todo "
                f"WHERE discord_user_id = {ctx.author.id} "
                f"AND potd_id = {potd_number}"
            )
            result = cursor.fetchall()
            if len(result) > 0:
                already_todo.append(str(potd_number))
            else:
                cursor.execute(
                    "INSERT INTO potd_todo (discord_user_id, potd_id, create_date) "
                    f"VALUES ('{ctx.author.id}', '{potd_number}', '{datetime.now()}')"
                )
                added.append(str(potd_number))

        # send confirm message
        messages = []
        if added:
            if len(added) == 1:
                messages.append(f"POTD {added[0]} is added to your TODO list.")
            else:
                messages.append(f'POTD {",".join(added)} are added to your TODO list.')
        if already_todo:
            if len(already_todo) == 1:
                messages.append(f"POTD {already_todo[0]} is already in your TODO list.")
            else:
                messages.append(
                    f'POTD {",".join(already_todo)} are already in your TODO list.'
                )
        message = "\n".join(messages)
        await ctx.send(message)

    @commands.command(aliases=["untodo"], brief="Unmark the POTD from your TODO list")
    @commands.cooldown(1, 5, BucketType.user)
    async def potd_untodo(self, ctx, *, user_input: str):
        # parse input
        try:
            potd_numbers = [int(i) for i in user_input.split(",")]
        except ValueError:
            await ctx.send("Error: The input contains non-integer values.")
            return

        if len(potd_numbers) > 200:
            await ctx.send("Please don't send more than 200 POTDs in each call.")
            return

        # delete from DB
        for potd_number in potd_numbers:
            cursor = cfg.db.cursor()
            cursor.execute(
                "DELETE FROM potd_todo "
                f"WHERE discord_user_id = {ctx.author.id} AND potd_id = {potd_number}"
            )

        # send confirm message
        if len(potd_numbers) == 1:
            await ctx.send(f"POTD {potd_numbers[0]} is removed from your TODO list. ")
        else:
            await ctx.send(
                f'POTD {",".join(list(map(str,potd_numbers)))} are removed from your '
                "TODO list. "
            )

    @commands.command(
        aliases=["mytodo"],
        brief="Show the POTDs in your TODO list",
        help="`-mytodo`: Show the POTDs in your TODO list.\n"
        "`-mytodo d`: Show the POTDs in your TODO list, ordered by difficulties.\n"
        "`-mytodo s`: Show the POTDs in your TODO list, divided into the four "
        "subjects.\n",
    )
    @commands.cooldown(1, 5, BucketType.user)
    async def potd_mytodo(self, ctx, flag=None):
        todo = potd_utils.get_potd_todo(ctx)

        potd_rows = (
            cfg.Config.service.spreadsheets()
            .values()
            .get(spreadsheetId=cfg.Config.config["potd_sheet"], range=POTD_RANGE)
            .execute()
            .get("values", [])
        )
        if len(todo) > 0:
            current_potd = int(potd_rows[0][0])

            await self.generate_potd_list_output_string(
                todo, potd_rows, current_potd, flag, "TODO", ctx, True
            )
        else:
            await ctx.send("Your TODO list is empty.")

    @commands.command(
        aliases=["unrated"],
        brief="Fetch a random POTD that you have solved/read but not yet rated",
        help="`-unrated`: Fetch a random POTD that you have solved/read but not yet "
        "rated.\n",
    )
    @commands.cooldown(1, 5, BucketType.user)
    async def potd_unrated(self, ctx, flag=None):
        solved = potd_utils.get_potd_solved(ctx)
        read = potd_utils.get_potd_read(ctx)
        rated = potd_utils.get_potd_rated(ctx)

        unrated = [x for x in (solved + read) if x not in rated]

        picked_potd = random.choice(unrated)
        await potd_utils.fetch(ctx, int(picked_potd))

    @commands.command(
        aliases=["unrated_list"],
        brief="Get the list of POTD that you have solved/read but not yet rated",
        help="`-unrated_list`: Get the list of POTD that you have solved/read but not "
        "yet rated.\n"
        "`-unrated_list d`: Get the list of POTD that you have solved/read but not yet "
        "rated, ordered by difficulties.\n"
        "`-unrated_list s`: Get the list of POTD that you have solved/read but not yet "
        "rated, divided into the four subjects.\n",
    )
    @commands.cooldown(1, 5, BucketType.user)
    async def potd_unrated_list(self, ctx, flag=None):
        solved = potd_utils.get_potd_solved(ctx)
        read = potd_utils.get_potd_read(ctx)
        rated = potd_utils.get_potd_rated(ctx)

        solved_unrated = [x for x in solved if x not in rated]
        read_unrated = [x for x in read if x not in rated]

        potd_rows = (
            cfg.Config.service.spreadsheets()
            .values()
            .get(spreadsheetId=cfg.Config.config["potd_sheet"], range=POTD_RANGE)
            .execute()
            .get("values", [])
        )
        current_potd = int(potd_rows[0][0])

        if solved_unrated:
            await self.generate_potd_list_output_string(
                solved_unrated,
                potd_rows,
                current_potd,
                flag,
                "unrated (solved)",
                ctx,
                True,
            )
        if read_unrated:
            await self.generate_potd_list_output_string(
                read_unrated, potd_rows, current_potd, flag, "unrated (read)", ctx, True
            )
        if not solved_unrated and not read_unrated:
            await ctx.send("You have no unrated POTD.")

    async def generate_potd_list_output_string(
        self, potd_list, potd_rows, current_potd, flag, adjective, ctx, show_total=True
    ):
        if flag == "d":
            solved_by_difficulty = {}
            for number in potd_list:
                if number > current_potd or number <= 0:
                    difficulty = "(Unknown)"
                else:
                    potd_row = potd_rows[current_potd - number]
                    if len(potd_row) > cfg.Config.config["potd_sheet_difficulty_col"]:
                        difficulty = potd_row[
                            cfg.Config.config["potd_sheet_difficulty_col"]
                        ]
                    else:
                        difficulty = "(Unknown)"

                if difficulty not in solved_by_difficulty:
                    solved_by_difficulty[difficulty] = []
                solved_by_difficulty[difficulty].append(number)

            sorted_keys = sorted(
                solved_by_difficulty.keys(),
                key=lambda x: (x.isnumeric(), int(x) if x.isnumeric() else x),
                reverse=True,
            )
            solved_by_difficulty = {
                key: solved_by_difficulty[key] for key in sorted_keys
            }

            output_string =  f"# __Your {adjective} POTD__ \n"
            for key in solved_by_difficulty:
                if show_total is True:
                    total = len(
                        [
                            potd
                            for potd in potd_rows
                            if len(potd)
                            > cfg.Config.config["potd_sheet_difficulty_col"]
                            and potd[cfg.Config.config["potd_sheet_difficulty_col"]]
                            == key
                        ]
                    )
                    output_string += (
                        "**D"
                        + key
                        + ":** "
                        + f"{solved_by_difficulty[key]} "
                        + f"({len(solved_by_difficulty[key])}/{total})\n"
                    )
                else:
                    output_string += f"**D{key}:** {solved_by_difficulty[key]} \n"
            if show_total:
                output_string += f"(Total: {len(potd_list)}/{len(potd_rows)})"
        elif flag == "s":
            solved_by_genre = {"A": [], "C": [], "G": [], "N": []}
            for number in potd_list:
                if number > current_potd or number <= 0:
                    genre = "(Unknown)"
                else:
                    potd_row = potd_rows[current_potd - number]
                    if len(potd_row) > cfg.Config.config["potd_sheet_genre_col"]:
                        genre = potd_row[cfg.Config.config["potd_sheet_genre_col"]]
                    else:
                        genre = "(Unknown)"

                if "A" in genre:
                    solved_by_genre["A"].append(number)
                if "C" in genre:
                    solved_by_genre["C"].append(number)
                if "G" in genre:
                    solved_by_genre["G"].append(number)
                if "N" in genre:
                    solved_by_genre["N"].append(number)

            output_string =  f"# __Your {adjective} POTD__ \n"
            for key in solved_by_genre:
                if show_total is True:
                    total = len(
                        [
                            potd
                            for potd in potd_rows
                            if len(potd)
                            > cfg.Config.config["potd_sheet_difficulty_col"]
                            and key in potd[cfg.Config.config["potd_sheet_genre_col"]]
                        ]
                    )
                    output_string += (
                        "**"
                        + key
                        + ":** "
                        + f"{solved_by_genre[key]} "
                        + f"({len(solved_by_genre[key])}/{total})\n"
                    )
                else:
                    output_string += f"**{key}:** {solved_by_genre[key]} \n"
            if show_total is True:
                output_string += f"(Total: {len(potd_list)}/{len(potd_rows)})"
        elif flag == "sd":
            solved_ordered = {
                "A": defaultdict(list),
                "C": defaultdict(list),
                "G": defaultdict(list),
                "N": defaultdict(list),
            }
            for number in potd_list:
                if number > current_potd or number <= 0:
                    genre = "(Unknown)"
                    difficulty = "(Unknown)"
                else:
                    potd_row = potd_rows[current_potd - number]
                    if len(potd_row) > cfg.Config.config["potd_sheet_genre_col"]:
                        genre = potd_row[cfg.Config.config["potd_sheet_genre_col"]]
                    else:
                        genre = "(Unknown)"
                    if len(potd_row) > cfg.Config.config["potd_sheet_difficulty_col"]:
                        difficulty = potd_row[cfg.Config.config["potd_sheet_difficulty_col"]]
                    else:
                        difficulty = "(Unknown)"

                for subj in "ACGN":
                    if subj in genre:
                        solved_ordered[subj][difficulty].append(number)

            output_string = f"# __Your {adjective} POTD__ \n"
            for subj in solved_ordered:
                output_string += f"## {subj}: \n"
                sorted_keys = sorted(
                    solved_ordered[subj].keys(),
                    key=lambda x: (x.isnumeric(), int(x) if x.isnumeric() else x),
                    reverse=True,
                )
                for diff in sorted_keys:
                    if show_total:
                        total = len(
                            [
                                potd
                                for potd in potd_rows
                                if len(potd) > cfg.Config.config["potd_sheet_difficulty_col"]
                                and len(potd) > cfg.Config.config["potd_sheet_genre_col"]
                                and subj in potd[cfg.Config.config["potd_sheet_genre_col"]]
                                and potd[cfg.Config.config["potd_sheet_difficulty_col"]]
                                == diff
                            ]
                        )
                        output_string += (
                            "**D"
                            + diff
                            + ":** "
                            + f"{solved_ordered[subj][diff]} ({len(solved_ordered[subj][diff])}/{total})"
                            + "\n"
                        )
                    else:
                        output_string += f"**{diff}:** {solved_ordered[subj][diff]} \n"
                if show_total:
                    probs = [potd for l in solved_ordered[subj].values() for potd in l]
                    total_subj = len(
                        [
                            potd
                            for potd in potd_rows
                            if len(potd) > cfg.Config.config["potd_sheet_genre_col"]
                            and potd[cfg.Config.config["potd_sheet_genre_col"]] == subj
                        ]
                    )
                    output_string += f"(Total: {len(probs)}/{total_subj}) \n"
        else:
            output_string = f"__**Your {adjective} POTD**__ \n{potd_list}" + "\n"
            if show_total is True:
                output_string += f"(Total: {len(potd_list)}/{len(potd_rows)})"

        await self.send_potd_solved(ctx, output_string)

    # send message in batches of 1900+e characters because of 2k character limit
    async def send_potd_solved(self, ctx, output_string):
        i = 0
        output_batch = ""
        while i < len(output_string):
            if output_batch == "":
                jump = min(1900, len(output_string) - i)
                output_batch += output_string[i : i + jump]
                i += jump
            else:
                output_batch += output_string[i]
                i += 1
            if (
                output_batch[-1] == ","
                or output_batch[-1] == "]"
                or len(output_batch) == 2000
                or i == len(output_string)
            ):  # we end a batch at "," or "]"
                await ctx.send(output_batch)
                output_batch = ""


async def setup(bot):
    await bot.add_cog(Marking(bot))
