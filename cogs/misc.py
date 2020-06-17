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

    @commands.command(aliases=['t'], brief='Sends the message associated with the given tag. ')
    async def retrieve_tag(self, ctx, *, tag):
        tags = cfg.Config.service.spreadsheets().values().get(
            spreadsheetId=cfg.Config.config['tags_sheet'],
            range='Tags!A2:D').execute().get('values', [])
        tag_dict = {}
        for t in tags:
            tag_dict[t[0]] = t[3]
            tag_dict[t[1]] = t[3]

        if tag == 'all':
            await ctx.send([[t[0], t[1]] for t in tags])
        elif tag in tag_dict:
            await ctx.send(tag_dict[tag])
        else:
            await ctx.send('I don\'t recognise that tag!')



def setup(bot):
    bot.add_cog(Misc(bot))
