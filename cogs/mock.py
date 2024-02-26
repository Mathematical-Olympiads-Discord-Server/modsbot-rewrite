import random
import re

from discord.ext import commands
from discord.ext.commands import BucketType

from cogs import config as cfg
from utils import potd_utils

Cog = commands.Cog

POTD_RANGE = "POTD!A2:S"


class Mock(Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(
        aliases=["mock"],
        brief="Create a mock paper using past POTDs.",
        help="`-mock IMO`: create mock IMO paper\n"
        "\n"
        "See below for a list of available templates and respective difficulty ranges\n"
        "(e.g. [5,7],[7,9],[9,11],[5,7],[7,9],[9,11] means problem 1 is d5-7, "
        "problem 2 is d7-9, etc.) \n"
        "\n"
        "IMO (International Mathematical Olympiad):\n"
        "[5,7],[7,9],[9,11],[5,7],[7,9],[9,11]\n"
        "AMO (Australian Mathematical Olympiad):\n"
        "[2,3],[3,4],[4,5],[5,6],[2,3],[3,4],[4,5],[5,6]\n"
        "APMO (Asian Pacific Mathematics Olympiad):\n"
        "[4,5],[5,6],[6,7],[7,8],[8,10]\n"
        "BMO1 (British Mathematical Olympiad Round 1):\n"
        "[1,2],[1,2],[2,3],[2,3],[3,5],[3,6]\n"
        "BMO2 (British Mathematical Olympiad Round 2):\n"
        "[3,4],[4,5],[5,6],[6,7]\n"
        "IGO (Iranian Geometry Olympiad):\n"
        "[5,6],[6,7],[7,8],[8,9],[9,10]\n"
        "NZMO2 (New Zealand Mathematical Olympiad Round 2):\n"
        "[1,2],[2,3],[3,4],[4,5],[5,6]\n"
        "SMO2 (Singapore Mathematical Olympiad Open Round 2):\n"
        "[4,5],[5,6],[6,7],[7,8],[8,9]\n"
        "USAMO (United States of America Mathematical Olympiad):\n"
        "[5,7],[7,9],[9,11],[5,7],[7,9],[9,11]\n"
        "USAJMO/JMO (United States of America Junior Mathematical Olympiad):\n"
        "[3,5],[5,7],[7,8],[3,5],[5,7],[7,8]\n"
        "CHINA (Crushingly Hard Imbalanced Nightmarish Assessment):\n"
        "[7,8],[8,10],[10,12],[7,8],[8,10],[10,12]",
        cooldown_after_parsing=True,
    )
    @commands.cooldown(1, 30, BucketType.user)
    async def potd_mock(self, ctx, template: str = "IMO", search_unsolved: bool = True):
        template = template.upper()
        template_list = [
            "IMO",
            "AMO",
            "APMO",
            "BMO1",
            "BMO2",
            "IGO",
            "NZMO2",
            "SMO2",
            "USAMO",
            "USAJMO",
            "JMO",
            "CHINA",
        ]
        if template not in template_list and template != "AFMO":
            await ctx.send(
                f"Template not found. Possible templates: {', '.join(template_list)}. "
                "Use `-help potd_mock` for more details."
            )
            return
        else:
            if template == "AFMO":  # easter egg
                difficulty_bounds = [[12, "T"], [12, "T"], [12, "T"], [13, "T"]]
            elif template == "AMO":
                difficulty_bounds = [
                    [2, 3],
                    [3, 4],
                    [4, 5],
                    [5, 6],
                    [2, 3],
                    [3, 4],
                    [4, 5],
                    [5, 6],
                ]
            elif template == "APMO":
                difficulty_bounds = [[4, 5], [5, 6], [6, 7], [7, 8], [8, 10]]
            elif template == "BMO1":
                difficulty_bounds = [[1, 2], [1, 2], [2, 3], [2, 3], [3, 5], [3, 6]]
            elif template == "BMO2":
                difficulty_bounds = [[3, 4], [4, 5], [5, 6], [6, 7]]
            elif template == "CHINA":
                difficulty_bounds = [
                    [7, 8],
                    [8, 10],
                    [10, 12],
                    [7, 8],
                    [8, 10],
                    [10, 12],
                ]
            elif template == "IGO":
                difficulty_bounds = [[5, 6], [6, 7], [7, 8], [8, 9], [9, 10]]
            elif template in ["IMO", "USAMO"]:
                difficulty_bounds = [[5, 7], [7, 9], [9, 11], [5, 7], [7, 9], [9, 11]]
            elif template == "NZMO2":
                difficulty_bounds = [[1, 2], [2, 3], [3, 4], [4, 5], [5, 6]]
            elif template == "SMO2":
                difficulty_bounds = [[4, 5], [5, 6], [6, 7], [7, 8], [8, 9]]
            elif template in ["USAJMO", "JMO"]:
                difficulty_bounds = [[3, 5], [5, 7], [7, 8], [3, 5], [5, 7], [7, 8]]
        # SMO2 seems to have an unspoken rule to start with geometry at P1 and nowhere
        # else
        if template == "SMO2":
            genre_rule = ["G", "ACN", "ACN", "ACN", "ACN"]
        elif template == "IGO":
            genre_rule = ["G", "G", "G", "G", "G"]
        else:
            genre_rule = ["ACGN"] * len(difficulty_bounds)

        # pick the genre of each problem
        genres = []
        while not self.is_genre_legit(genres, template, genre_rule):
            genres = list(map(lambda x: random.choice(x), genre_rule))

        potds = (
            cfg.Config.service.spreadsheets()
            .values()
            .get(spreadsheetId=cfg.Config.config["potd_sheet"], range=POTD_RANGE)
            .execute()
            .get("values", [])
        )
        already_picked = []

        # set up variables
        problems_tex = []
        # render the mock paper
        for i in range(len(difficulty_bounds)):
            picked_potd = potd_utils.pick_potd(
                difficulty_bounds[i][0],
                difficulty_bounds[i][1],
                genres[i],
                potds,
                already_picked,
                ctx,
                search_unsolved,
            )
            already_picked.append(picked_potd)
            potd_statement = potd_utils.get_potd_statement(int(picked_potd), potds)
            problems_tex.append(
                f"\\textbf{{Problem {i + 1}. (POTD {str(picked_potd)})}}\\\\ "
                f"{potd_statement}"
            )

        if template in {"IMO", "AMO", "USAMO", "USAJMO", "CHINA"}:  # 2-day contests
            if template in {"IMO", "CHINA", "USAMO", "USAJMO"}:
                index_day1 = [0, 1, 2]
                index_day2 = [3, 4, 5]
            elif template in {"AMO"}:
                index_day1 = [0, 1, 2, 3]
                index_day2 = [4, 5, 6, 7]

            name_day1 = f"{template} (Day 1)"
            problems_tex_day1 = [problems_tex[index] for index in index_day1]
            await self.send_out_mock(ctx, name_day1, problems_tex_day1)

            name_day2 = f"{template} (Day 2)"
            problems_tex_day2 = [problems_tex[index] for index in index_day2]
            await self.send_out_mock(ctx, name_day2, problems_tex_day2)
        else:  # 1-day contests
            await self.send_out_mock(ctx, template, problems_tex)

    @commands.command(
        aliases=["mock_custom", "custom_mock"],
        brief="Create a custom mock paper using past POTDs.",
        help="`-mock_custom [5 7] [7 9] [9 11] [5 7] [7 9] [9 11]`: create a mock "
        "paper where problem 1 is d5-7, problem 2 is d7-9, etc.\n"
        "`-mock_custom [3 4 G] [4 5 G] [5 6 G] [6 7 G]`: create a mock paper where "
        "problem 1 is d3-4 geometry, problem 2 is d4-5 geometry, etc.",
        cooldown_after_parsing=True,
    )
    @commands.cooldown(1, 30, BucketType.user)
    async def potd_mock_custom(self, ctx, *, rules):
        # parse the user inputed rules
        parsed_rules = self.parse_mock_rules(rules)

        # handle garbage or too long input
        if parsed_rules is False:
            await ctx.send(
                "Custom rule input error! Please input the custom rule like this: "
                "`[5 7] [7 9] [9 11]`."
            )
            return
        if len(parsed_rules) > 15:
            await ctx.send("Maximum number of problems allowed is 15.")
            return

        # get the genre rule
        genre_rule = []
        for parsed_rule in parsed_rules:
            if parsed_rule["genres"] == "":
                genre_rule.append("ACGN")
            else:
                genre_rule.append(parsed_rule["genres"])

        # pick the genre of each problem
        genres = []
        while not self.is_genre_legit(genres, "Custom", genre_rule):
            genres = list(map(lambda x: random.choice(x), genre_rule))

        # get the difficulty bounds
        difficulty_bounds = [
            [parsed_rule["diff_lower"], parsed_rule["diff_upper"]]
            for parsed_rule in parsed_rules
        ]
        # set up variables
        problems_tex = []
        potds = (
            cfg.Config.service.spreadsheets()
            .values()
            .get(spreadsheetId=cfg.Config.config["potd_sheet"], range=POTD_RANGE)
            .execute()
            .get("values", [])
        )
        already_picked = []
        parsed_rules_string = self.stringify_mock_rules(parsed_rules)

        # render the mock paper
        try:
            for i in range(len(difficulty_bounds)):
                picked_potd = potd_utils.pick_potd(
                    difficulty_bounds[i][0],
                    difficulty_bounds[i][1],
                    genres[i],
                    potds,
                    already_picked,
                    ctx,
                    True,
                )
                already_picked.append(picked_potd)
                potd_statement = potd_utils.get_potd_statement(int(picked_potd), potds)
                problems_tex.append(
                    f"\\textbf{{Problem {i + 1}. (POTD {str(picked_potd)})}}\\\\ "
                    f"{potd_statement}"
                )

            await ctx.send(
                f"<@{ctx.author.id}> Custom Mock created ({parsed_rules_string})"
            )
            await self.send_out_mock(ctx, "(Custom)", problems_tex)
        except Exception:
            await ctx.send(
                "Unable to create mock paper according to custom rule "
                f"({parsed_rules_string})"
            )

    async def send_out_mock(self, ctx, name, problems_tex):
        while len(problems_tex) > 0:  # still has problems to send out
            title = (
                r"\begin{center}\textbf{\textsf{MODSBot Mock "
                + name
                + r"}}\end{center}"
            )
            problems = ""
            while (
                len(problems_tex) > 0 and len(problems + problems_tex[0]) < 1800
            ):  # add problems one-by-one until no problems left or it's too long
                problems = problems + problems_tex.pop(0) + r"\\ \\"
            problems = problems[:-5]
            to_tex = f"<@419356082981568522>\n```tex\n {title} {problems}```"
            await ctx.send(to_tex, delete_after=5)

    def is_genre_legit(self, genres, template, genre_rule):
        if len(genres) != len(genre_rule):
            return False

        different_genre_number = len(set("".join(genre_rule)))
        # the paper should cover as many genre listed in genre_rule as possible
        question_number = len(genre_rule)
        genres_needed = min(question_number, different_genre_number)

        if len(genres) < genres_needed:
            return False

        # the selected genres need to match the genre_rule
        for i in range(len(genres)):
            if genres[i] not in genre_rule[i]:
                return False

        if template == "IMO":
            # P3 and P6 should be different genre
            if genres[2] == genres[5]:
                return False

            # The three problems on each day should be different genre
            if len({genres[0], genres[1], genres[2]}) < 3:
                return False
            if len({genres[3], genres[4], genres[5]}) < 3:
                return False

            # Geoff Smith Rule
            genres_geoff_smith = [genres[index] for index in [0, 1, 3, 4]]
            if (
                "A" not in genres_geoff_smith
                or "C" not in genres_geoff_smith
                or "G" not in genres_geoff_smith
                or "N" not in genres_geoff_smith
            ):
                return False

        return True

    def parse_mock_rules(self, rules):
        parsed_rules = []

        rules = rules.replace(",", " ")
        res = re.findall(r"\[.*?\]", rules)

        for substring in res:
            modified_substring = substring[1:-1].split(" ")

            if len(modified_substring) not in [2, 3]:
                return False
            if len(modified_substring) == 2:
                modified_substring.append("ACGN")

            try:
                int(modified_substring[0])
                int(modified_substring[1])
            except Exception:
                return False
            if int(modified_substring[0]) > int(modified_substring[1]):
                return False

            diff_lower = max(int(modified_substring[0]), 0)
            diff_upper = min(int(modified_substring[1]), 14)
            genres = ""
            possible_genres = ["A", "C", "G", "N"]
            for char in modified_substring[2]:
                if char.upper() in possible_genres and char.upper() not in genres:
                    genres += char.upper()

            parsed_rule = {
                "diff_lower": diff_lower,
                "diff_upper": diff_upper,
                "genres": genres,
            }

            parsed_rules.append(parsed_rule)

        return parsed_rules

    def stringify_mock_rules(self, parsed_rules):
        rule_strings = []
        for parse_rule in parsed_rules:
            if parse_rule["genres"] not in ["", "ACGN"]:
                rule_string = (
                    f"[{parse_rule['diff_lower']} {parse_rule['diff_upper']} "
                    f"{parse_rule['genres']}]"
                )
            else:
                rule_string = f"[{parse_rule['diff_lower']} {parse_rule['diff_upper']}]"
            rule_strings.append(rule_string)
        return " ".join(rule_strings)


async def setup(bot):
    await bot.add_cog(Mock(bot))
