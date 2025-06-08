import contextlib
import random
from datetime import datetime, timedelta

import discord
from discord import app_commands
from discord.ext import commands
from discord.ext.commands import BucketType

from cogs import config as cfg
from utils import potd_utils

Cog = commands.Cog

POTD_RANGE = "POTD!A2:S"


class Potd(Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(
        aliases=["fetch"],
        brief="Fetch a potd by id.",
        help="`-fetch 1`: Fetch POTD Day 1 in TeX format (auto-deletes after 5 seconds).\n"
        "`-fetch 0`: Fetch today's POTD (updates at 1800 GMT).\n"
        "`-fetch -3`: Fetch POTD from 3 days ago.\n"
        "`-fetch 1 s`: Fetch POTD Day 1, masked by spoiler "
        "(auto-deletes after 5 seconds).\n"
        "`-fetch 1 t`: Fetch POTD Day 1, in TeX form "
        "(permanent, no auto-delete).\n",
    )
    @commands.cooldown(1, 5, BucketType.user)
    async def potd_fetch(self, ctx, number: int, flag: str = ""):
        await potd_utils.fetch(ctx, number, flag)

    @commands.command(
        aliases=["source"],
        brief="Get the source of a potd by id.",
        cooldown_after_parsing=True,
    )
    @commands.cooldown(1, 5, BucketType.user)
    async def potd_source(self, ctx, number: int):
        sheet = potd_utils.get_potd_sheet()
        potd_row = potd_utils.get_potd_row(number, sheet)

        if potd_row is None:
            await ctx.send(f"There is no potd for day {number}. ")
            return
        else:
            if datetime.now() - timedelta(hours=10) - timedelta(
                days=1
            ) > datetime.strptime(
                potd_row[cfg.Config.config["potd_sheet_date_col"]], "%d %b %Y"
            ):
                source = potd_utils.generate_source(potd_row, True, ctx.author.id)
            else:
                source = potd_utils.generate_source(potd_row, False, ctx.author.id)
            await ctx.send(embed=source)

    @commands.command(
        aliases=["search"],
        brief="Search for a POTD by genre and difficulty.",
        help="`-search 4 6`: Search for a POTD with difficulty d4 to d6 (inclusive).\n"
        "`-search 4 6 C`: Search for a POTD with difficulty d4 to d6 and genres "
        "including combinatorics.\n"
        "`-search 4 6 CG`: Search for a POTD with difficulty d4 to d6 and genres "
        "including combinatorics or geometry.\n"
        "`-search 4 6 'CG'`: Search for a POTD with difficulty d4 to d6 and genres "
        "including (combinatorics AND geometry).\n"
        "`-search 4 6 A'CG'N`: Search for a POTD with difficulty d4 to d6 and genres "
        "including (algebra OR (combinatorics AND geometry) OR number theory).\n"
        "`-search 4 6 ACGN false`: Search for a POTD with difficulty d4 to d6. "
        "Allow getting problems marked in the `-solved` list.",
        cooldown_after_parsing=True,
    )
    @commands.cooldown(1, 5, BucketType.user)
    async def potd_search(
        self,
        ctx,
        diff_lower_bound: int,
        diff_upper_bound: int,
        genre: str = "ACGN",
        search_unsolved: bool = True,
    ):
        if diff_lower_bound > diff_upper_bound:
            await ctx.send("Difficulty lower bound cannot be higher than upper bound.")
            return

        # Set up the genre filter
        genre_filter = self.parse_genre_input(genre)

        # set up the difficulty filter
        diff_lower_bound_filter = max(0, diff_lower_bound)
        diff_upper_bound_filter = max(
            min(99, diff_upper_bound), diff_lower_bound_filter
        )

        potds = (
            cfg.Config.service.spreadsheets()
            .values()
            .get(spreadsheetId=cfg.Config.config["potd_sheet"], range=POTD_RANGE)
            .execute()
            .get("values", [])
        )
        picked_potd = potd_utils.pick_potd(
            diff_lower_bound_filter,
            diff_upper_bound_filter,
            genre_filter,
            potds,
            [],
            ctx,
            search_unsolved,
            "",
        )
        if picked_potd is not None:
            # fetch the picked POTD
            await potd_utils.fetch(ctx, int(picked_potd))
        else:
            await ctx.send("No POTD found!")

    @commands.command(
        aliases=["search_tag"],
        brief="Search for a POTD by tag and difficulty.",
        help="`-search 4 6`: Search for a POTD with difficulty d4 to d6 (inclusive).\n"
        "`-search 4 6 FE`: Search for a POTD with difficulty d4 to d6 and tags "
        "including functional equation.\n"
        "`-search 4 6 FE,IN`: Search for a POTD with difficulty d4 to d6 and tags "
        "including both functional equation and inequality.\n"
        "`-search 4 6 FE false`: Search for a FE POTD with difficulty d4 to d6. "
        "Allow getting problems marked in the `-solved` list.\n"
        '(See the "Tags and Difficulty" sheet in the POTD spreadsheet for a full '
        "list of tags) ",
        cooldown_after_parsing=True,
    )
    @commands.cooldown(1, 5, BucketType.user)
    async def potd_search_tag(
        self,
        ctx,
        diff_lower_bound: int,
        diff_upper_bound: int,
        tags: str = "",
        search_unsolved: bool = True,
    ):
        if diff_lower_bound > diff_upper_bound:
            await ctx.send("Difficulty lower bound cannot be higher than upper bound.")
            return

        # set up the difficulty filter
        diff_lower_bound_filter = max(0, diff_lower_bound)
        diff_upper_bound_filter = max(
            min(99, diff_upper_bound), diff_lower_bound_filter
        )

        potds = (
            cfg.Config.service.spreadsheets()
            .values()
            .get(spreadsheetId=cfg.Config.config["potd_sheet"], range=POTD_RANGE)
            .execute()
            .get("values", [])
        )
        picked_potd = potd_utils.pick_potd(
            diff_lower_bound_filter,
            diff_upper_bound_filter,
            "",
            potds,
            [],
            ctx,
            search_unsolved,
            tags,
        )
        if picked_potd is not None:
            # fetch the picked POTD
            await potd_utils.fetch(ctx, int(picked_potd))
        else:
            await ctx.send("No POTD found!")

    def potds_filtered_by_keywords(self, keyword_list: list[str]):
        potds = (
            cfg.Config.service.spreadsheets()
            .values()
            .get(spreadsheetId=cfg.Config.config["potd_sheet"], range=POTD_RANGE)
            .execute()
            .get("values", [])
        )
        return [
            x
            for x in potds
            if len(x) > cfg.Config.config["potd_sheet_statement_col"]
            and all(
                keyword.lower()
                in x[cfg.Config.config["potd_sheet_statement_col"]].lower()
                for keyword in keyword_list
            )
        ]

    async def potd_search_keywords_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        filtered_potds = self.potds_filtered_by_keywords(current.split())
        filtered_potd_statements = [
            potd[cfg.Config.config["potd_sheet_statement_col"]]
            for potd in filtered_potds
        ]
        # Only 25 responses are supported in autocomplete, and they must be at most 100
        # characters
        return [
            app_commands.Choice(name=statement[:100], value=statement[:100])
            for statement in filtered_potd_statements
        ][:25]

    @app_commands.command()
    @app_commands.describe(keywords="Search past potds using these keywords")
    @app_commands.autocomplete(keywords=potd_search_keywords_autocomplete)
    @commands.cooldown(1, 10, BucketType.user)
    async def potd_keywords(self, interaction: discord.Interaction, keywords: str):
        """Search potds using keywords"""

        if filtered_potds := self.potds_filtered_by_keywords(keywords.split()):
            picked_potd_row = random.choice(filtered_potds)
            if image_link := potd_utils.check_for_image_link(picked_potd_row):
                await interaction.response.send_message(f"[image]({image_link})")
            else:
                output = (
                    "<@"
                    + str(cfg.Config.config["paradox_id"])
                    + ">\n"
                    + potd_utils.texify_potd(picked_potd_row)
                )
                await interaction.response.send_message(output, delete_after=5)
        else:
            await interaction.response.send_message("No POTD found!", ephemeral=True)

    @commands.command(
        aliases=["hint"], brief="Get hint for the POTD.", cooldown_after_parsing=True
    )
    @commands.cooldown(1, 10, BucketType.user)
    async def potd_hint(self, ctx, number: int, hint_number: int = 1):
        sheet = potd_utils.get_potd_sheet()
        potd_row = potd_utils.get_potd_row(number, sheet)
        if potd_row is None:
            await ctx.send(f"There is no potd for day {number}. ")
            return
        else:
            if hint_number == 1:
                if (
                    len(potd_row) <= cfg.Config.config["potd_sheet_hint1_col"]
                    or potd_row[cfg.Config.config["potd_sheet_hint1_col"]] is None
                    or potd_row[cfg.Config.config["potd_sheet_hint1_col"]] == ""
                ):
                    await ctx.send(
                        f"There is no hint for POTD {number}. "
                        "Would you like to contribute one? "
                        f"Contribute by commenting in <https://docs.google.com/"
                        f"spreadsheets/d/{cfg.Config.config['potd_sheet']}>"
                    )
                    return
                else:
                    await ctx.send(f"Hint for POTD {number}:\n")
                    latex = potd_row[cfg.Config.config["potd_sheet_hint1_col"]]
                    await ctx.send(
                        f"<@{cfg.Config.config['paradox_id']}> texsp \n"
                        f"||```latex\n{latex}```||",
                    )
                    if (
                        len(potd_row) > cfg.Config.config["potd_sheet_hint2_col"]
                        and potd_row[cfg.Config.config["potd_sheet_hint2_col"]]
                        is not None
                        and potd_row[cfg.Config.config["potd_sheet_hint2_col"]] != ""
                    ):
                        await ctx.send(
                            "There is another hint for this POTD. "
                            f"Use `-hint {number} 2` to get the hint."
                        )
            elif hint_number == 2:
                if (
                    len(potd_row) <= cfg.Config.config["potd_sheet_hint2_col"]
                    or potd_row[cfg.Config.config["potd_sheet_hint2_col"]] is None
                    or potd_row[cfg.Config.config["potd_sheet_hint2_col"]] == ""
                ):
                    await ctx.send(
                        f"There is no hint 2 for POTD {number}. "
                        "Would you like to contribute one? "
                        f"Contribute by commenting in <https://docs.google.com/"
                        f"spreadsheets/d/{cfg.Config.config['potd_sheet']}>"
                    )
                    return
                else:
                    await ctx.send(f"Hint 2 for POTD {number}:\n")
                    latex = potd_row[cfg.Config.config["potd_sheet_hint2_col"]]
                    await ctx.send(
                        f"<@{cfg.Config.config['paradox_id']}> texsp \n"
                        f"||```latex\n{latex}```||",
                    )
                    if (
                        len(potd_row) > cfg.Config.config["potd_sheet_hint3_col"]
                        and potd_row[cfg.Config.config["potd_sheet_hint3_col"]]
                        is not None
                        and potd_row[cfg.Config.config["potd_sheet_hint3_col"]] != ""
                    ):
                        await ctx.send(
                            "There is another hint for this POTD. "
                            f"Use `-hint {number} 3` to get the hint."
                        )
            elif hint_number == 3:
                if (
                    len(potd_row) <= cfg.Config.config["potd_sheet_hint3_col"]
                    or potd_row[cfg.Config.config["potd_sheet_hint3_col"]] is None
                    or potd_row[cfg.Config.config["potd_sheet_hint3_col"]] == ""
                ):
                    await ctx.send(
                        f"There is no hint 3 for POTD {number}. "
                        "Would you like to contribute one? "
                        f"Contribute by commenting in <https://docs.google.com/"
                        f"spreadsheets/d/{cfg.Config.config['potd_sheet']}>"
                    )
                    return
                else:
                    await ctx.send(f"Hint 3 for POTD {number}:\n")
                    latex = potd_row[cfg.Config.config["potd_sheet_hint3_col"]]
                    await ctx.send(
                        f"<@{cfg.Config.config['paradox_id']}> texsp \n"
                        f"||```latex\n{latex}```||",
                    )
            else:
                await ctx.send("Hint number should be from 1 to 3.")

    @commands.command(
        aliases=["answer"],
        brief="Get answer for the POTD.",
        cooldown_after_parsing=True,
    )
    @commands.cooldown(1, 10, BucketType.user)
    async def potd_answer(self, ctx, number: int):
        sheet = potd_utils.get_potd_sheet()
        potd_row = potd_utils.get_potd_row(number, sheet)
        if potd_row is None:
            await ctx.send(f"There is no potd for day {number}. ")
            return
        else:
            if (
                len(potd_row) <= cfg.Config.config["potd_sheet_answer_col"]
                or potd_row[cfg.Config.config["potd_sheet_answer_col"]] is None
                or potd_row[cfg.Config.config["potd_sheet_answer_col"]] == ""
            ):
                await ctx.send(
                    f"There is no answer provided for POTD {number}. "
                    "Would you like to contribute one? "
                    f"Contribute by commenting in <https://docs.google.com/"
                    f"spreadsheets/d/{cfg.Config.config['potd_sheet']}>"
                )
                return
            else:
                await ctx.send(f"Answer for POTD {number}:\n")
                latex = potd_row[cfg.Config.config["potd_sheet_answer_col"]]
                await ctx.send(
                    f"<@{cfg.Config.config['paradox_id']}> texsp \n"
                    f"||```latex\n{latex}```||",
                )

    @commands.command(
        aliases=["discussion"],
        brief="Get discussion for the POTD.",
        cooldown_after_parsing=True,
    )
    @commands.cooldown(1, 10, BucketType.user)
    async def potd_discussion(self, ctx, number: int):
        sheet = potd_utils.get_potd_sheet()
        potd_row = potd_utils.get_potd_row(number, sheet)
        if potd_row is None:
            await ctx.send(f"There is no potd for day {number}. ")
            return
        else:
            if (
                len(potd_row) <= cfg.Config.config["potd_sheet_discussion_col"]
                or potd_row[cfg.Config.config["potd_sheet_discussion_col"]] is None
                or potd_row[cfg.Config.config["potd_sheet_discussion_col"]] == ""
            ):
                await ctx.send(f"There is no discussion provided for POTD {number}.")
                return
            else:
                await ctx.send(f"Discussion for POTD {number}:\n")
                latex = potd_row[cfg.Config.config["potd_sheet_discussion_col"]]
                await ctx.send(
                    f"<@{cfg.Config.config['paradox_id']}> texsp \n"
                    f"||```latex\n{latex}```||",
                    delete_after=5,
                )

    @commands.command(
        aliases=["solution"],
        brief="Get solution for the POTD.",
        cooldown_after_parsing=True,
    )
    @commands.cooldown(1, 10, BucketType.user)
    async def potd_solution(self, ctx, number: int):
        sheet = potd_utils.get_potd_sheet()
        potd_row = potd_utils.get_potd_row(number, sheet)
        if potd_row is None:
            await ctx.send(f"There is no potd for day {number}. ")
            return
        else:
            if (
                len(potd_row) <= cfg.Config.config["potd_sheet_solution_col"]
                or potd_row[cfg.Config.config["potd_sheet_solution_col"]] is None
                or potd_row[cfg.Config.config["potd_sheet_solution_col"]] == ""
            ):
                solution = None
            else:
                solution = potd_row[cfg.Config.config["potd_sheet_solution_col"]]
            if (
                len(potd_row) <= cfg.Config.config["potd_sheet_solution_link_col"]
                or potd_row[cfg.Config.config["potd_sheet_solution_link_col"]] is None
                or potd_row[cfg.Config.config["potd_sheet_solution_link_col"]] == ""
            ):
                solution_link = None
            else:
                solution_link = potd_row[
                    cfg.Config.config["potd_sheet_solution_link_col"]
                ]

            if solution is None and solution_link is None:
                await ctx.send(
                    f"There is no solution provided for POTD {number}. "
                    "Would you like to contribute one? "
                    f"Contribute by commenting in <https://docs.google.com/"
                    f"spreadsheets/d/{cfg.Config.config['potd_sheet']}>"
                )
                return
            if solution is not None:
                await ctx.send(f"Solution for POTD {number}:\n")
                await ctx.send(
                    f"<@{cfg.Config.config['paradox_id']}> texsp \n||```latex\n"
                    f"{potd_row[cfg.Config.config['potd_sheet_solution_col']]}``` ||",
                    delete_after=5,
                )
            if solution_link is not None:
                await ctx.send(
                    f"Solution Link for POTD {number}:\n"
                    f"||{potd_row[cfg.Config.config['potd_sheet_solution_link_col']]}"
                    " ||"
                )

    def format(self, rating):
        return f"d||`{rating}`||" if rating >= 10 else f"d||`{rating} `||"

    def potd_notif_embed(self, ctx, colour):
        result = None

        def subcriteria(a):
            if result[1][a] == "x":
                return "Off"
            else:
                return f"D{int(result[1][a:a+2])}-{int(result[1][a+2:a+4])}"

        cursor = cfg.db.cursor()
        cursor.execute(f"SELECT * FROM potd_ping2 WHERE user_id = {ctx.author.id}")
        result = cursor.fetchone()
        if result is None:
            return None
        embed = discord.Embed(colour=colour)
        try:
            if ctx.author.nick is None:
                embed.add_field(name="Username", value=ctx.author.name)
            else:
                embed.add_field(name="Nickname", value=ctx.author.nick)
        except Exception:
            embed.add_field(name="Username", value=ctx.author.name)
        for i in range(4):
            embed.add_field(
                name=["Algebra", "Combinatorics", "Geometry", "Number Theory"][i],
                value=subcriteria(4 * i),
            )
        embed.set_footer(text="Use `-help pn` for help. ")
        return embed

    @commands.command(
        aliases=["pn"],
        brief="Customizes potd pings. ",
        help="`-pn`: enable POTD notifications or show settings\n"
        "`-pn a1-7`: set difficulty range for category\n"
        "`-pn c`: toggle notifications for category\n"
        "`-pn a1-7 c`: combine commands\n"
        "`-pn off`: disable notifications",
    )
    async def potd_notif(self, ctx, *criteria: str):
        # Empty criteria
        cursor = cfg.db.cursor()
        criteria = list(criteria)
        if not criteria:
            cursor.execute(
                f"SELECT * FROM potd_ping2 WHERE user_id = '{ctx.author.id}'"
            )
            result = cursor.fetchone()
            if result is None:
                cursor.execute(
                    f"""INSERT INTO potd_ping2 (user_id, criteria)
                    VALUES('{ctx.author.id}', '0 120 120 120 12')"""
                )
                cfg.db.commit()
                await ctx.send(
                    "Your POTD notification settings have been updated: ",
                    embed=self.potd_notif_embed(ctx, 0x5FE36A),
                )
            else:
                await ctx.send(
                    "Here are your POTD notification settings: ",
                    embed=self.potd_notif_embed(ctx, 0xDCDCDC),
                )
            return

        # Turn off ping
        if criteria[0].lower() == "off":
            cursor.execute(f"DELETE FROM potd_ping2 WHERE user_id = '{ctx.author.id}'")
            cfg.db.commit()
            await ctx.send("Your POTD notifications have been turned off. ")
            return

        # Run criteria
        cursor.execute(f"SELECT * FROM potd_ping2 WHERE user_id = '{ctx.author.id}'")
        result = cursor.fetchone()
        if result is None:
            cursor.execute(
                f"""INSERT INTO potd_ping2 (user_id, criteria)
                VALUES('{ctx.author.id}', 'xxxxxxxxxxxxxxxx')"""
            )
            cursor.execute(
                f"SELECT * FROM potd_ping2 WHERE user_id = '{ctx.author.id}'"
            )
            result = cursor.fetchone()
        result = list(result)

        temp = "".join(criteria).lower()
        criteria = [temp[0]]
        for i in temp[1:]:
            if i in ["a", "c", "g", "n"]:
                criteria.append(i)
            else:
                criteria[-1] += i

        # Difficulty only
        if len(criteria) == 1:
            temp = criteria[0].split("-")
            if len(temp) == 2:
                with contextlib.suppress(ValueError):
                    min_difficulty = int(temp[0])
                    max_difficulty = int(temp[1])
                    if 0 <= min_difficulty <= max_difficulty <= 12:
                        if result[1] == "xxxxxxxxxxxxxxxx":
                            result[1] = "                "
                        temp = "".join(
                            (
                                "xxxx"
                                if result[1][4 * i] == "x"
                                else str(min_difficulty).ljust(2)
                                + str(max_difficulty).ljust(2)
                            )
                            for i in range(4)
                        )
                        cursor.execute(
                            f"UPDATE potd_ping2 SET criteria = '{temp}' "
                            f"WHERE user_id = '{ctx.author.id}'"
                        )
                        cfg.db.commit()
                        await ctx.send(
                            "Your POTD notification settings have been updated: ",
                            embed=self.potd_notif_embed(ctx, 0x5FE36A),
                        )
                    else:
                        cfg.db.rollback()
                        await ctx.send(f"`{criteria[0]}` Invalid difficulty range! ")
                    return
        remaining = ["a", "c", "g", "n"]
        for i in criteria:
            if i in remaining:
                # Category without difficulty
                remaining.remove(i)
                index = ["a", "c", "g", "n"].index(i[0])
                if result[1][4 * index] == "x":
                    result[
                        1
                    ] = f"{result[1][:4 * index]}0 12{result[1][4 * index + 4:]}"
                else:
                    result[
                        1
                    ] = f"{result[1][:4 * index]}xxxx{result[1][4 * index + 4:]}"
            else:
                # Category with difficulty
                criterion = i[1:].split("-")
                if (i[0] not in remaining) or (len(criterion) != 2):
                    cfg.db.rollback()
                    await ctx.send(f"`{i}` Invalid input format! ")
                    return
                try:
                    min_difficulty = int(criterion[0])
                    max_difficulty = int(criterion[1])
                    if not (0 <= min_difficulty <= max_difficulty <= 12):
                        cfg.db.rollback()
                        await ctx.send(f"`{i}` Invalid difficulty range! ")
                        return
                except ValueError:
                    cfg.db.rollback()
                    await ctx.send(f"`{i}` Invalid input format! ")
                    return
                remaining.remove(i[0])
                index = ["a", "c", "g", "n"].index(i[0])
                result[1] = (
                    f"{result[1][:4*index]}{str(min_difficulty).ljust(2)}"
                    f"{str(max_difficulty).ljust(2)}{result[1][4*index+4:]}"
                )

        cursor.execute(
            f"UPDATE potd_ping2 SET criteria = '{result[1]}' "
            f"WHERE user_id = '{ctx.author.id}'"
        )
        cfg.db.commit()
        await ctx.send(
            "Your POTD notification settings have been updated: ",
            embed=self.potd_notif_embed(ctx, 0x5FE36A),
        )

    def parse_genre_input(self, genre):
        complex_genres = genre.split("'")[1::2]
        simple_genres = "".join(genre.split("'")[::2])

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


async def setup(bot):
    await bot.add_cog(Potd(bot))
