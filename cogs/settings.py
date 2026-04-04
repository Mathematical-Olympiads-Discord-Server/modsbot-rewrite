from discord.ext import commands

from cogs import config as cfg

Cog = commands.Cog


class InvalidSettingError(Exception):
    pass


class InvalidValueError(Exception):
    pass


async def get_setting(ctx, setting: str, can_auto=False):
    if setting not in cfg.Config.config["settings"]:
        raise InvalidSettingError
    cursor = cfg.db.cursor()
    cursor.execute(
        "SELECT * FROM user_settings WHERE userid = ? AND setting = ? LIMIT 1",
        (ctx.author.id, setting),
    )
    result = cursor.fetchone()
    if result is None:
        # auto
        return "auto" if can_auto else cfg.Config.config[setting][0]
    else:
        # not auto
        return result[2]


async def set_setting(ctx, setting: str, value: str):
    if setting not in cfg.Config.config["settings"]:
        raise InvalidSettingError
    cursor = cfg.db.cursor()
    if value == "auto":
        cursor.execute(
            "DELETE FROM user_settings WHERE userid = ? AND setting = ?",
            (ctx.author.id, setting),
        )
    elif value in cfg.Config.config[setting]:
        cursor.execute(
            "INSERT OR REPLACE INTO user_settings (userid, setting, value) "
            "VALUES (?, ?, ?)",
            (ctx.author.id, setting, value),
        )
    else:
        raise InvalidValueError


class Settings(Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def get_setting_wrapper(self, ctx, setting: str):
        try:
            value = await get_setting(ctx, setting, True)
            if value == "auto":
                await ctx.send(
                    f"<@{ctx.author.id}> Setting `{setting}` is currently `auto`. "
                    f"In the current server configuration, this is equivalent to "
                    f"`{cfg.Config.config[setting][0]}`."
                )
            else:
                await ctx.send(
                    f"<@{ctx.author.id}> Setting `{setting}` is currently `{value}`."
                )
        except InvalidSettingError:
            await ctx.send(f"<@{ctx.author.id}> `{setting}` is not a valid setting!")
        except Exception as e:
            print(f"Failed to get user preferences: {e}")
            await ctx.send("Failed to get user preferences")

    async def set_setting_wrapper(self, ctx, setting: str, value: str):
        try:
            await set_setting(ctx, setting, value)
            if value == "auto":
                await ctx.send(
                    f"<@{ctx.author.id}> Setting `{setting}` has been set to `auto`. "
                    f"In the current server configuration, this is equivalent to "
                    f"`{cfg.Config.config[setting][0]}`."
                )
            else:
                await ctx.send(
                    f"<@{ctx.author.id}> Setting `{setting}` has been set to `{value}`."
                )
        except InvalidValueError:
            await ctx.send(
                f"<@{ctx.author.id}> `{value}` is not a valid value for "
                f"setting `{setting}`! "
                f"Valid values: {'`' + '`, `'.join(cfg.Config.config[setting]) + '`'}"
            )
        except InvalidSettingError:
            await ctx.send(f"<@{ctx.author.id}> `{setting}` is not a valid setting!")
        except Exception as e:
            print(f"Failed to set user preferences: {e}")
            await ctx.send("Failed to set user preferences")

    async def display_settings(self, ctx):
        output = "# Your settings:\n```\n"
        for setting in cfg.Config.config["settings"]:
            value = await get_setting(ctx, setting, True)
            output += f"{setting}: {value}\n"
        output += "```"
        await ctx.send(output)

    @commands.command(aliases=["s"], brief="Manages user preferences.")
    async def settings(self, ctx, setting: str = "", value: str = ""):
        if setting:
            if not value:
                await self.get_setting_wrapper(ctx, setting)
            else:
                await self.set_setting_wrapper(ctx, setting, value)
        else:
            await self.display_settings(ctx)


async def setup(bot):
    await bot.add_cog(Settings(bot))
