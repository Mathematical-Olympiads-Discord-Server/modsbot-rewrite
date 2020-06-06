from datetime import datetime

import discord
from discord.ext import commands
from discord.ext.commands import BucketType

from cogs import config as cfg

Cog = commands.Cog

waiting_for = set()


class Misc(Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def record(self):
        g = self.bot.get_guild(cfg.Config.config['mods_guild'])

    @commands.command()
    @commands.cooldown(1, 600, BucketType.user)
    async def suggest(self, ctx, *, suggestion):
        await self.bot.get_channel(cfg.Config.config['suggestion_channel']).send(
            '**Suggestion by <@!{}>**: \n{}'.format(ctx.author.id, suggestion))

        r_body = {
            'values': [[datetime.now().isoformat(), ctx.author.name, str(ctx.author.id), 'Pending', 0, suggestion]]
        }
        cfg.Config.service.spreadsheets().values().append(spreadsheetId=cfg.Config.config['suggestion_sheet'],
                                                          range='Suggestions!A1', valueInputOption='RAW',
                                                          insertDataOption='INSERT_ROWS', body=r_body).execute()

    @Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.channel_id != cfg.Config.config['welcome_channel']: return
        guild = self.bot.get_guild(cfg.Config.config['mods_guild'])
        user = guild.get_member(payload.user_id)

        role_ids = set()
        for r in user.roles:
            role_ids.add(r.id)
        m = await self.bot.get_channel(payload.channel_id).fetch_message(payload.message_id)
        await m.remove_reaction(payload.emoji, discord.Object(payload.user_id))
        if user is not None and payload.emoji and cfg.Config.config['unverified_role'] in role_ids:
            try:
                await user.remove_roles(guild.get_role(cfg.Config.config['unverified_role']))
            except discord.HTTPException as e:
                print(e)

            await self.bot.get_channel(cfg.Config.config['lounge_channel']).send(
                f"Welcome to the Mathematical Olympiads Discord server {user.mention}! "
                "Check out the self-assignable roles in "
                f"<#{cfg.Config.config['roles_channel']}> and enjoy your time here. :smile:"
            )

    @commands.command()
    @commands.is_owner()
    async def index_suggestions(self, ctx, *, channel: int):
        messages = await self.bot.get_channel(channel).history(limit=200).flatten()
        values = []
        for message in messages:
            values.append([message.created_at.isoformat(), message.author.name, str(message.author.id), 'Pending', 0,
                           message.content])
        r_body = {'values': values}
        cfg.Config.service.spreadsheets().values().append(spreadsheetId=cfg.Config.config['suggestion_sheet'],
                                                          range='Suggestions!A1', valueInputOption='RAW',
                                                          insertDataOption='INSERT_ROWS', body=r_body).execute()


def setup(bot):
    bot.add_cog(Misc(bot))
