import discord
from discord.ext import commands

from cogs import config as cfg

Cog = commands.Cog


class Contest(Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.check(cfg.is_contest_chair)
    async def award_contest_medals(self, ctx, confirm: bool = False):
        # read google sheet
        sheet = get_contest_sheet()
        values = sheet.get("values", [])
        contest_name = values[0][5]
        gold_medalists = []
        silver_medalists = []
        bronze_medalists = []
        hm_medalists = []
        for i in range(1, len(values)):
            row = values[i]
            if len(row) >= 3:
                username = row[1]
                medal = row[2]
                if medal == "Gold Award":
                    gold_medalists.append(username)
                elif  medal == "Silver Award":
                    silver_medalists.append(username)
                elif  medal == "Bronze Award":
                    bronze_medalists.append(username)
                elif  medal == "Honourable Mention":
                    hm_medalists.append(username)

        if not confirm:
            # output contest name instruction
            await ctx.send(
                f"We are going to award medals for the contest "
                f"`{contest_name}`. Run `-award_contest_medals true` "
                f"after confirming the list of medalists is correct."
            )
            # output embed of medalists
            batch_size = 20
            gold_batches = [
                gold_medalists[i : i + batch_size]
                for i in range(0, len(gold_medalists), batch_size)
            ]
            j = 0
            for gold_batch in gold_batches:
                gold_embed = discord.Embed()
                length = len(gold_batch)
                gold_embed.add_field(
                    name="Gold Medalists",
                    value="\n".join(
                        [
                            f"`{i + 1 + 20*j}.` <@!{gold_batch[i]}>"
                            for i in range(length)
                        ]
                    ),
                )
                await ctx.send(embed=gold_embed)
                j = j + 1

            silver_batches = [
                silver_medalists[i : i + batch_size]
                for i in range(0, len(silver_medalists), batch_size)
            ]
            j = 0
            for silver_batch in silver_batches:
                silver_embed = discord.Embed()
                length = len(silver_batch)
                silver_embed.add_field(
                    name="Silver Medalists",
                    value="\n".join(
                        [
                            f"`{i + 1 + 20*j}.` <@!{silver_batch[i]}>"
                            for i in range(length)
                        ]
                    ),
                )
                await ctx.send(embed=silver_embed)
                j = j + 1

            bronze_batches = [
                bronze_medalists[i : i + batch_size]
                for i in range(0, len(bronze_medalists), batch_size)
            ]
            j = 0
            for bronze_batch in bronze_batches:
                bronze_embed = discord.Embed()
                length = len(bronze_batch)
                bronze_embed.add_field(
                    name="Bronze Medalists",
                    value="\n".join(
                        [
                            f"`{i + 1 + 20*j}.` <@!{bronze_batch[i]}>"
                            for i in range(length)
                        ]
                    ),
                )
                await ctx.send(embed=bronze_embed)
                j = j + 1

            hm_batches = [
                hm_medalists[i : i + batch_size]
                for i in range(0, len(hm_medalists), batch_size)
            ]
            j = 0
            for hm_batch in hm_batches:
                hm_embed = discord.Embed()
                length = len(hm_batch)
                hm_embed.add_field(
                    name="Honourable Mentions",
                    value="\n".join(
                        [f"`{i + 1 + 20*j}.` <@!{hm_batch[i]}>" for i in range(length)]
                    ),
                )
                await ctx.send(embed=hm_embed)
                j = j + 1
        else:
            contest_gold_role = ctx.guild.get_role(
                cfg.Config.config["contest_gold_role"]
            )
            contest_silver_role = ctx.guild.get_role(
                cfg.Config.config["contest_silver_role"]
            )
            contest_bronze_role = ctx.guild.get_role(
                cfg.Config.config["contest_bronze_role"]
            )
            contest_hm_role = ctx.guild.get_role(cfg.Config.config["contest_hm_role"])
            # Remove existing medalists
            for user in contest_gold_role.members:
                await user.remove_roles(contest_gold_role)
            for user in contest_silver_role.members:
                await user.remove_roles(contest_silver_role)
            for user in contest_bronze_role.members:
                await user.remove_roles(contest_bronze_role)
            for user in contest_hm_role.members:
                await user.remove_roles(contest_hm_role)
            await ctx.send("Removed all existing Contest Medals.")
            # Award the medals
            for user_id in gold_medalists:
                member = await ctx.guild.fetch_member(int(user_id))
                await member.add_roles(contest_gold_role)
            await ctx.send("Finished awarding Gold Medals.")
            for user_id in silver_medalists:
                member = await ctx.guild.fetch_member(int(user_id))
                await member.add_roles(contest_silver_role)
            await ctx.send("Finished awarding Silver Medals.")
            for user_id in bronze_medalists:
                member = await ctx.guild.fetch_member(int(user_id))
                await member.add_roles(contest_bronze_role)
            await ctx.send("Finished awarding Bronze Medals.")
            for user_id in hm_medalists:
                member = await ctx.guild.fetch_member(int(user_id))
                await member.add_roles(contest_hm_role)
            await ctx.send("Finished awarding Honourable Mentions.")
            # Send confirmation messages
            await ctx.send(f"Finished awarding all the medals for {contest_name}")


def get_contest_sheet():
    return (
        cfg.Config.service.spreadsheets()
        .values()
        .get(spreadsheetId=cfg.Config.config["contest_sheet"], range="Awards!A1:F")
        .execute()
    )


async def setup(bot):
    await bot.add_cog(Contest(bot))
