import asyncio

from discord.ext import commands

from cogs import config as cfg
from utils import potd_utils

Cog = commands.Cog


class Proposals(Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def post_proposed_potd(self):
        self.bot.loop.create_task(self.post_proposed_potd_task())

    async def post_proposed_potd_task(self):
        # Read from spreadsheet
        proposed_problems = (
            cfg.Config.service.spreadsheets()
            .values()
            .get(spreadsheetId=cfg.Config.config["potd_proposal_sheet"], range="A:M")
            .execute()
            .get("values", [])
        )

        for i, problem in enumerate(proposed_problems):
            # Find unposted problems
            if len(problem) < 12 or problem[11] == "":
                number = i
                user = problem[1]
                user_id = problem[2]
                problem_statement = problem[3]
                source = problem[4]
                genre = problem[5]
                difficulty = problem[6]
                hint1 = problem[7]
                try:
                    hint2 = problem[8]
                except Exception:
                    hint2 = ""
                try:
                    hint3 = problem[9]
                except Exception:
                    hint3 = ""
                try:
                    proposer_msg = problem[10]
                except Exception:
                    proposer_msg = ""

                # Post in forum
                forum = self.bot.get_channel(cfg.Config.config["potd_proposal_forum"])
                content = (
                    f"POTD Proposal #{number} "
                    f"from {user} <@!{user_id}> ({user_id})\n"
                    f"Problem Statement: ```latex\n"
                    f"{problem_statement}\n```"
                )
                post_result = await forum.create_thread(
                    name=f"POTD Proposal #{number} from {user}",
                    content=content,
                    applied_tags=[
                        forum.get_tag(
                            cfg.Config.config["potd_proposal_forum_tag_pending"]
                        )
                    ],
                )
                thread = post_result[0]

                problem_info = (
                    f"Source: ||{source}|| \n"
                    + f"Genre: ||{genre}  || \n"
                    + f"Difficulty: ||{difficulty}  ||"
                )
                if proposer_msg not in ["", None]:
                    problem_info += f"\nProposer's message: {proposer_msg}\n"
                await thread.send(problem_info)
                await asyncio.sleep(10)

                await thread.send("Hint 1:")
                await thread.send(
                    f"<@{cfg.Config.config['paradox_id']}> texsp\n"
                    f"||```latex\n{hint1}```||"
                )
                await asyncio.sleep(10)
                if hint2 not in ["", None]:
                    await thread.send("Hint 2:")
                    await thread.send(
                        f"<@{cfg.Config.config['paradox_id']}> texsp\n"
                        f"||```latex\n{hint2}```||"
                    )
                    await asyncio.sleep(10)
                if hint3 not in ["", None]:
                    await thread.send("Hint 3:")
                    await thread.send(
                        f"<@{cfg.Config.config['paradox_id']}> texsp\n"
                        f"||```latex\n{hint3}```||"
                    )
                    await asyncio.sleep(10)

                # Mark problem as posted
                request = (
                    cfg.Config.service.spreadsheets()
                    .values()
                    .update(
                        spreadsheetId=cfg.Config.config["potd_proposal_sheet"],
                        range=f"L{i+1}",
                        valueInputOption="RAW",
                        body={"range": f"L{i+1}", "values": [["Y"]]},
                    )
                )
                request.execute()

                # Mark thread ID
                request = (
                    cfg.Config.service.spreadsheets()
                    .values()
                    .update(
                        spreadsheetId=cfg.Config.config["potd_proposal_sheet"],
                        range=f"M{i+1}",
                        valueInputOption="RAW",
                        body={"range": f"M{i+1}", "values": [[str(thread.id)]]},
                    )
                )
                request.execute()

                # Send notification to proposer
                try:
                    guild = self.bot.get_guild(cfg.Config.config["mods_guild"])
                    member = guild.get_member(int(user_id))
                    if member is not None and not member.bot:
                        await member.send(
                            f"Hi! We have received your POTD Proposal `{source}`. "
                            "Thanks for your submission!"
                        )
                except Exception as e:
                    print(e)

    @commands.command()
    @commands.check(potd_utils.is_pc)
    async def potd_pending(self, ctx, number: int):
        await self.potd_proposal_status_change(ctx, number, "Pending")
        await ctx.send(f"POTD Proposal #{number} status modified to Pending")

    @commands.command()
    @commands.check(potd_utils.is_pc)
    async def potd_accept(self, ctx, number: int):
        await self.potd_proposal_status_change(ctx, number, "Accepted")
        await ctx.send(f"POTD Proposal #{number} status modified to Accepted")

    @commands.command()
    @commands.check(potd_utils.is_pc)
    async def potd_reject(self, ctx, number: int):
        await self.potd_proposal_status_change(ctx, number, "Rejected")
        await ctx.send(f"POTD Proposal #{number} status modified to Rejected")

    async def potd_proposal_status_change(self, ctx, number: int, status):
        tag_id = 0
        if status == "Pending":
            tag_id = cfg.Config.config["potd_proposal_forum_tag_pending"]
        elif status == "Accepted":
            tag_id = cfg.Config.config["potd_proposal_forum_tag_accepted"]
        elif status == "Rejected":
            tag_id = cfg.Config.config["potd_proposal_forum_tag_rejected"]

        # Load the proposal sheet
        proposed_problems = (
            cfg.Config.service.spreadsheets()
            .values()
            .get(spreadsheetId=cfg.Config.config["potd_proposal_sheet"], range="A:M")
            .execute()
            .get("values", [])
        )

        # Edit the thread tag
        forum = self.bot.get_channel(cfg.Config.config["potd_proposal_forum"])
        row = number
        thread_id = proposed_problems[row][12]
        thread = ctx.guild.get_thread(int(thread_id))
        await thread.edit(applied_tags=[forum.get_tag(tag_id)])

    # manually invoke the proposal check
    @commands.command()
    @commands.check(cfg.is_mod_or_tech)
    async def potd_proposal(self, ctx):
        self.bot.loop.create_task(self.post_proposed_potd_task())


async def setup(bot):
    await bot.add_cog(Proposals(bot))
