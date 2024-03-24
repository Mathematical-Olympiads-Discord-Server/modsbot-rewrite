import os
import sqlite3
from datetime import datetime, timezone

import bidict
from apiclient import discovery
from discord.ext import commands
from google.oauth2 import service_account
from ruamel import yaml

Cog = commands.Cog
db = sqlite3.connect("data/modsdb.db")


def is_staff(ctx):
    return False if ctx.guild is None else ctx.author.id in Config.config["staff"]


def is_mod_or_tech(ctx):
    if ctx.guild is None or ctx.guild.id != Config.config["mods_guild"]:
        return False
    roles = list(map(lambda x: x.id, ctx.author.roles))
    return Config.config["mod_role"] in roles or Config.config["tech_role"] in roles


def is_contest_chair(ctx):
    if ctx.guild is None or ctx.guild.id != Config.config["mods_guild"]:
        return False
    roles = list(map(lambda x: x.id, ctx.author.roles))
    return (
        Config.config["mod_role"] in roles
        or Config.config["contest_chair_role"] in roles
    )


def timestamp(dt: datetime):
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return int((dt - datetime(1970, 1, 1, tzinfo=timezone.utc)).total_seconds())


class Config(Cog):
    config = None

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    secret_file = os.path.join(os.getcwd(), "config/credentials.json")

    credentials = service_account.Credentials.from_service_account_file(
        secret_file, scopes=scopes
    )
    service = discovery.build("sheets", "v4", credentials=credentials)

    def __init__(self, bot):
        with open("config/config_test.yml") as cfgfile:
            Config.config = yaml.safe_load(cfgfile)
        self.bot = bot

        Config.config["pc_codes"] = bidict.bidict()
        problem_curators = (
            Config.service.spreadsheets()
            .values()
            .get(spreadsheetId=Config.config["potd_sheet"], range="Curators!A3:E")
            .execute()
            .get("values", [])
        )
        for pc in problem_curators:
            Config.config["pc_codes"][int(pc[0])] = pc[2]
        print(Config.config["pc_codes"])

    @commands.command(
        aliases=["cfl"],
        brief="Gets a config variable from the loaded config.yml file. ",
    )
    async def config_load(self, ctx, name):
        if name not in Config.config:
            await ctx.send("No config with that name found!")
        else:
            await ctx.send(str(Config.config[name]))


async def setup(bot):
    await bot.add_cog(Config(bot))
