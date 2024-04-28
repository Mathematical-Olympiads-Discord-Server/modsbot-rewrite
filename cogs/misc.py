from datetime import datetime, timezone
from random import choice

import discord
from discord.ext import commands

from cogs import config as cfg

Cog = commands.Cog
word_file = "/usr/share/dict/words"
words = open(word_file).read().splitlines()
waiting_for = set()
aphasiad = set()
in_verif_speedrun_mode = set()
embargo = False


class Misc(Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        cursor = cfg.db.cursor()
        cursor.execute(
            """INSERT OR IGNORE INTO settings VALUES
            ('embargo', 'False')
            """
        )
        cursor.execute(
            """SELECT value
            FROM settings
            WHERE setting = 'embargo';
            """
        )
        result = cursor.fetchone()
        if result is not None:
            self.embargo = result[0]

    def record(self):
        # TODO: work out what to do with this
        g = self.bot.get_guild(cfg.Config.config["mods_guild"])  # noqa: F841

    @Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.channel_id != cfg.Config.config["welcome_channel"]:
            return
        if payload.user_id in in_verif_speedrun_mode:
            time_elapsed = (
                datetime.now(timezone.utc).timestamp()
                - payload.member.joined_at.timestamp()
            )
            await self.bot.get_channel(cfg.Config.config["bot_spam_channel"]).send(
                f"<@!{payload.user_id}>: `{time_elapsed}`s"
            )

        guild = self.bot.get_guild(cfg.Config.config["mods_guild"])
        user = guild.get_member(payload.user_id)

        role_ids = {r.id for r in user.roles}
        m = await self.bot.get_channel(payload.channel_id).fetch_message(
            payload.message_id
        )
        await m.remove_reaction(payload.emoji, discord.Object(payload.user_id))
        if (
            user is not None
            and payload.emoji
            and cfg.Config.config["unverified_role"] in role_ids
        ):
            verif_time_delta = (
                datetime.now(timezone.utc).timestamp()
                - payload.member.joined_at.timestamp()
            )
            if verif_time_delta < 15 and payload.user_id not in in_verif_speedrun_mode:
                await self.bot.get_channel(cfg.Config.config["warn_channel"]).send(
                    f"{payload.member.mention} verified in like, "
                    f"epsilon time ({verif_time_delta}s exactly)"
                )

            try:
                await user.remove_roles(
                    guild.get_role(cfg.Config.config["unverified_role"])
                )
            except discord.HTTPException as e:
                print(e)

            if payload.user_id not in in_verif_speedrun_mode:
                await self.bot.get_user(payload.user_id).send(
                    "Welcome to the server! Check out the self-assignable "
                    "roles in <#671639229293395978> or start chatting in "
                    "our <#533153217119387660>. If you have any issues "
                    "related to the server, please feel free to DM "
                    "<@!696261358932721694>. We hope you enjoy your time "
                    "here. 😄\n\n*Please note that we are a Mathematical "
                    "Olympiad discord server. If you want help with "
                    "non-Olympiad mathematics, please visit the "
                    "**Mathematics** discord server at "
                    "<https://discord.sg/math> or the **Homework Help** "
                    "discord server at <https://discord.gg/YudDZtb>.*"
                )

    @commands.command(
        aliases=["t"], brief="Sends the message associated with the given tag. "
    )
    async def retrieve_tag(self, ctx, *, tag):
        tags = (
            cfg.Config.service.spreadsheets()
            .values()
            .get(spreadsheetId=cfg.Config.config["tags_sheet"], range="Tags!A2:D")
            .execute()
            .get("values", [])
        )
        tag_dict = {}
        for t in tags:
            tag_dict[t[0]] = t[3]
            tag_dict[t[1]] = t[3]

        if tag == "all":
            await ctx.send([[t[0], t[1]] for t in tags])
        elif tag in tag_dict:
            await ctx.send(tag_dict[tag])
        else:
            await ctx.send("I don't recognise that tag!")

    @commands.command(brief="Return my User ID")
    async def myid(self, ctx):
        name = ctx.author.name
        author_id = ctx.author.id
        await ctx.send(f"{name}'s User ID: {author_id}")

    @commands.command()
    async def verify_speedrun_mode(self, ctx):
        in_verif_speedrun_mode.add(ctx.author.id)
        await ctx.author.send("You're in verify speedrun mode now!")

    @commands.command()
    @commands.check(cfg.is_staff)
    async def aphasia(self, ctx, user: discord.User):
        aphasiad.add(user.id)

    @commands.command()
    @commands.check(cfg.is_staff)
    async def unaphasia(self, ctx, user: discord.User):
        aphasiad.remove(user.id)

    @commands.command()
    @commands.check(cfg.is_staff)
    async def toggle_embargo(self, ctx, status: bool):
        cursor = cfg.db.cursor()
        cursor.execute(
            f"""UPDATE settings
            SET value = '{status}'
            WHERE setting = 'embargo';
            """
        )
        self.embargo = status
        await ctx.send(f"Embargo status toggled to {status}")

    @commands.command()
    @commands.check(cfg.is_staff)
    async def embargo_status(self, ctx):
        await ctx.send(f"Current embargo status: {self.embargo}")

    @Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.id in aphasiad:
            m_len = len(message.content.split())
            x = " ".join(choice(words) for _ in range(m_len))
            await message.delete()
            await message.channel.send(f"{message.author.mention}: {x}")


async def setup(bot):
    await bot.add_cog(Misc(bot))
