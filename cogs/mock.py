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
        self.mocks = {}

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
            "JPMO",
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
            elif template in {"IMO", "USAMO"}:
                difficulty_bounds = [[5, 7], [7, 9], [9, 11], [5, 7], [7, 9], [9, 11]]
            elif template == "NZMO2":
                difficulty_bounds = [[1, 2], [2, 3], [3, 4], [4, 5], [5, 6]]
            elif template == "SMO2":
                difficulty_bounds = [[4, 5], [5, 6], [6, 7], [7, 8], [8, 9]]
            elif template in {"USAJMO", "JMO"}:
                difficulty_bounds = [[3, 5], [5, 7], [7, 8], [3, 5], [5, 7], [7, 8]]
            elif template == "JPMO":
                difficulty_bounds = [[4,5], [5,6], [6,7], [7,8], [8,9]]
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
        problem_ids = []
        rules = []
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

            problem_ids.append(picked_potd)
            rules.append({
                "diff_lower": difficulty_bounds[i][0],
                "diff_upper": difficulty_bounds[i][1],
                "genres": genres[i]
            })
            already_picked.append(picked_potd)
            potd_statement = potd_utils.get_potd_statement(int(picked_potd), potds)
            problems_tex.append(
                f"\\textbf{{Problem {i + 1}. (POTD {str(picked_potd)})}}\\\\ "
                f"{potd_statement}"
            )
        
        messages = await self.send_out_mock(ctx, template, problems_tex)
        message_ids = [msg.id for msg in messages]

        self.mocks[(ctx.author.id, ctx.channel.id)] = {
            "message_ids": message_ids,
            "channel_id": ctx.channel.id,
            "template": template,
            "rules": rules,
            "problem_ids": problem_ids,
            "search_unsolved": search_unsolved,
        }


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
        problem_ids = []
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
                problem_ids.append(picked_potd)
                already_picked.append(picked_potd)
                potd_statement = potd_utils.get_potd_statement(int(picked_potd), potds)
                problems_tex.append(
                    f"\\textbf{{Problem {i + 1}. (POTD {str(picked_potd)})}}\\\\ "
                    f"{potd_statement}"
                )
            
            messages = await self.send_out_mock(ctx, "Custom", problems_tex)
            message_ids = [msg.id for msg in messages]
            self.mocks[(ctx.author.id, ctx.channel.id)] = {
                "message_ids": message_ids,
                "channel_id": ctx.channel.id,
                "template": "Custom",
                "rules": parsed_rules,
                "problem_ids": problem_ids,
                "search_unsolved": True,
            }

        except Exception:
            await ctx.send(
                "Unable to create mock paper according to custom rule "
                f"({parsed_rules_string})"
            )

    async def send_out_mock(self, ctx, name, problems_tex):
        messages = []
        index = 0
        while index < len(problems_tex):  # still has problems to send out
            title = (
                r"\begin{center}\textbf{\textsf{MODSBot Mock "
                + name
                + r"}}\end{center}"
            )
            problems = ""

            while index < len(problems_tex) and len(problems + problems_tex[index]) < 1800:
                problems = problems + problems_tex[index] + r"\\ \\"
                index +=1

            problems = problems[:-5]
            to_tex = f"<@419356082981568522>\n```tex\n {title} {problems}```"
            msg = await ctx.send(to_tex)
            messages.append(msg)
            count += 1

        return messages

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
    
    async def generate_mock_content(self, template, problem_ids, search_unsolved):
        # Fetch sheet
        potds = (cfg.Config.service.spreadsheets()
                .values()
                .get(spreadsheetId=cfg.Config.config["potd_sheet"], range=POTD_RANGE)
                .execute()
                .get("values", []))

        # Build problems_tex list
        problems_tex = []
        for i, pid in enumerate(problem_ids, start=1):
            stmt = potd_utils.get_potd_statement(int(pid), potds)
            if stmt is None:
                stmt = "*(statement missing)*"
            problems_tex.append(f"\\textbf{{Problem {i}. (POTD {pid})}}\\\\ {stmt}")

        # Split into messages like send_out_mock
        contents = []
        idx = 0
        while idx < len(problems_tex):
            title = r"\begin{center}\textbf{\textsf{MODSBot Mock " + template + r"}}\end{center}"
            problems = ""
            while idx < len(problems_tex) and len(problems + problems_tex[idx]) < 1800:
                problems = problems + problems_tex[idx] + r"\\ \\"
                idx += 1
            problems = problems[:-5]   # remove trailing double backslash
            contents.append(f"<@419356082981568522>\n```tex\n{title}\n{problems}\n```")
        return contents

    @commands.command(aliases=["strike"])
    @commands.guild_only()
    async def strike(self, ctx, target: str):
        key = (ctx.author.id, ctx.channel.id)
        mock = self.mocks.get(key)
        if not mock:
            await ctx.send("You don't have a mock in this channel.")
            return

        # Parse target
        if target.lower().startswith('p'):
            try:
                index = int(target[1:]) - 1
            except ValueError:
                await ctx.send("Invalid index. Use `p1`, `p2`, etc.")
                return
            if index < 0 or index >= len(mock["problem_ids"]):
                await ctx.send(f"Problem index out of range. There are {len(mock['problem_ids'])} problems.")
                return
            old_id = mock["problem_ids"][index]
        else:
            try:
                potd_id = int(target)
            except ValueError:
                await ctx.send("Invalid input. Use `p1`, `p2`, etc. or a POTD ID.")
                return
            if potd_id not in mock["problem_ids"]:
                await ctx.send(f"POTD {potd_id} not found in your mock.")
                return
            index = mock["problem_ids"].index(potd_id)
            old_id = potd_id

        rule = mock["rules"][index]
        diff_lower = rule["diff_lower"]
        diff_upper = rule["diff_upper"]
        genre = rule["genres"]

        # Fetch current POTD sheet
        potds = (cfg.Config.service.spreadsheets()
                .values()
                .get(spreadsheetId=cfg.Config.config["potd_sheet"], range=POTD_RANGE)
                .execute()
                .get("values", []))

        # Find replacement
        exclude = mock["problem_ids"][:]   # copy
        replacement = potd_utils.pick_potd(
            diff_lower, diff_upper, genre, potds, exclude, ctx, mock["search_unsolved"], ""
        )
        if not replacement:
            await ctx.send("Could not find a suitable replacement problem.")
            return

        # Build new problem list
        new_problem_ids = mock["problem_ids"][:]
        new_problem_ids[index] = replacement

        # Generate new content
        new_contents = await self.generate_mock_content(mock["template"], new_problem_ids, mock["search_unsolved"])
        if len(new_contents) != len(mock["message_ids"]):
            await ctx.send("The mock changed length; cannot edit in place. Please create a new mock.")
            return

        # Edit each message
        channel = ctx.channel
        for i, msg_id in enumerate(mock["message_ids"]):
            try:
                msg = await channel.fetch_message(msg_id)
                await msg.edit(content=new_contents[i])
            except Exception as e:
                await ctx.send(f"Failed to edit message {i+1}: {e}")
                return

        # Update stored data
        self.mocks[key]["problem_ids"] = new_problem_ids
        await ctx.send(f"Problem {index+1} (POTD {old_id}) replaced with POTD {replacement}.")

async def setup(bot):
    await bot.add_cog(Mock(bot))
