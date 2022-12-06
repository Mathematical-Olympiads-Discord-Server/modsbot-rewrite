import os
import pickle

import discord
from discord.ext import commands

from cogs import config as cfg

Cog = commands.Cog
invites = {}


class Invites(Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        if os.path.exists('data/invites.p'):
            temp = pickle.load(open('data/invites.p', 'rb'))
            for invite in temp:
                invites[invite] = temp[invite]

    @commands.is_owner()
    @commands.command(aliases=['ui'])
    async def update_invites(self, ctx):
        inv_list = await ctx.guild.invites()
        for invite in inv_list:
            invites[invite.code] = invite.uses
        pickle.dump(invites, open('data/invites.p', 'wb+'))
        print(invites)

    @Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        invites[invite.code] = 0
        pickle.dump(invites, open('data/invites.p', 'wb+'))

    @Cog.listener()
    async def on_member_join(self, member: discord.Member):
        temp_invites = await member.guild.invites()

        # Check possible places they could have joined from
        possible_joins = set()
        for invite in temp_invites:
            if invite.uses > invites[invite.code]:
                possible_joins.add(invite)
            invites[invite.code] = invite.uses
        possible_string = ' '.join([f'{invite.code} by {invite.inviter.mention}' for invite in possible_joins])
        embed = discord.Embed()
        embed.add_field(name='User Joined', value=member.mention, inline=False)
        embed.add_field(name='Possible Invites', value=possible_string if possible_string != '' else 'None (probably Discovery)', inline=False)

        join_delta = member.joined_at.timestamp() - member.created_at.timestamp()
        if join_delta > 1800:
            await member.guild.get_channel(cfg.Config.config['log_channel']).send(embed=embed)
        else:
            embed.add_field(name='Recently Created', value=f'{join_delta} seconds ago', inline=False)
            await self.bot.get_channel(cfg.Config.config['warn_channel']).send(embed=embed)


async def setup(bot: commands.Bot):
    i = Invites(bot)
    await bot.add_cog(i)
