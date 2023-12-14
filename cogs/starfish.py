import asyncio

import discord
from discord.ext import commands
from discord.utils import get

from cogs import config as cfg

Cog = commands.Cog


class Starfish(Cog):
    def __init__(self, bot):
        self.bot = bot

    @Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        message = (
            await self.bot.get_guild(cfg.Config.config["mods_guild"])
            .get_channel(payload.channel_id)
            .fetch_message(payload.message_id)
        )
        stars = discord.utils.get(message.reactions, emoji="⭐")
        if (
            payload.user_id == message.author.id
            and payload.emoji.name == "⭐"
            and stars.count == 1
        ):
            try:
                await message.add_reaction(cfg.Config.config["starfishing_emoji"])
            except discord.errors.Forbidden:
                # mute the mf who cheese by blocking MODSbot
                muted = get(message.guild.roles, name="muted")
                await message.author.add_roles(muted)
                await message.channel.send(
                    f'{cfg.Config.config["starfishing_emoji"]} '
                    f"{message.author.mention} "
                    f"was muted for 5 minutes for evading starfish "
                    f'{cfg.Config.config["starfishing_emoji"]}'
                )
                await asyncio.sleep(60 * 5)
                await message.author.remove_roles(muted)


async def setup(bot):
    await bot.add_cog(Starfish(bot))
