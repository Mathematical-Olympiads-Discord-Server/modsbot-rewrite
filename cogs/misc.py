import logging
from datetime import datetime
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


class Misc(Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def record(self):
        g = self.bot.get_guild(cfg.Config.config['mods_guild'])

    @Cog.listener()
    async def on_raw_reaction_add(self, payload):
        logging.info(f'Reaction clicked:       {datetime.utcnow().timestamp() - payload.member.joined_at.timestamp()}')
        logging.info(f'Reaction seen:          {datetime.utcnow().timestamp() - payload.member.joined_at.timestamp()}')
        if payload.channel_id != cfg.Config.config['welcome_channel']: return
        guild = self.bot.get_guild(cfg.Config.config['mods_guild'])
        user = guild.get_member(payload.user_id)
        logging.info(f'Sanitised:              {datetime.utcnow().timestamp() - payload.member.joined_at.timestamp()}')

        role_ids = set()
        for r in user.roles:
            role_ids.add(r.id)
        m = await self.bot.get_channel(payload.channel_id).fetch_message(payload.message_id)
        await m.remove_reaction(payload.emoji, discord.Object(payload.user_id))
        logging.info(f'Reaction removed:       {datetime.utcnow().timestamp() - payload.member.joined_at.timestamp()}')
        if user is not None and payload.emoji and cfg.Config.config['unverified_role'] in role_ids:

            verif_time_delta = datetime.utcnow().timestamp() - payload.member.joined_at.timestamp()
            if verif_time_delta < 15:
                await self.bot.get_channel(cfg.Config.config['warn_channel']).send(
                    f'{payload.member.mention} verified in like, epsilon time ({verif_time_delta}s exactly)')

            logging.info(
                f'Sent timing message:    {datetime.utcnow().timestamp() - payload.member.joined_at.timestamp()}')
            try:
                await user.remove_roles(guild.get_role(cfg.Config.config['unverified_role']))
            except discord.HTTPException as e:
                print(e)

            if payload.user_id in in_verif_speedrun_mode:
                await self.bot.get_channel(cfg.Config.config['bot_spam_channel']).send(
                    f"<@!{payload.user_id}>: `{datetime.utcnow().timestamp() - payload.member.joined_at.timestamp()}`s")
            else:
                await self.bot.get_channel(cfg.Config.config['lounge_channel']).send(
                    f"Welcome to the Mathematical Olympiads Discord server {user.mention}! "
                    "Check out the self-assignable roles in "
                    f"<#{cfg.Config.config['roles_channel']}> and enjoy your time here. :smile:"
                )
            logging.info(
                f'Sent welcome message:   {datetime.utcnow().timestamp() - payload.member.joined_at.timestamp()}')

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

    @commands.command()
    async def verify_speedrun_mode(self, ctx):
        in_verif_speedrun_mode.add(ctx.author.id)
        await ctx.author.send('You\'re in verify speedrun mode now!')

    @commands.command()
    @commands.check(cfg.is_staff)
    async def aphasia(self, ctx, user: discord.User):
        aphasiad.add(user.id)

    @commands.command()
    @commands.check(cfg.is_staff)
    async def unaphasia(self, ctx, user: discord.User):
        aphasiad.remove(user.id)

    @Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.id in aphasiad:
            m_len = len(message.content.split())
            x = ' '.join((choice(words) for i in range(m_len)))
            await message.delete()
            await message.channel.send(f'{message.author.mention}: {x}')


def setup(bot):
    bot.add_cog(Misc(bot))
