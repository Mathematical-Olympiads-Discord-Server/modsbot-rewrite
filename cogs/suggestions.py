import operator
from datetime import datetime

import bidict
import discord
from discord.ext import commands
from discord.ext.commands import BucketType

from cogs import config as cfg

Cog = commands.Cog
suggestion_list = []
statuses = bidict.bidict({0: 'Pending', 1: 'Mod vote', 2: 'Approved', 3: 'Denied', 4: 'Revised', 5: 'Implemented'})
status_colours = {0: 0xFCECB4, 1: 0xFF8105, 2: 0x5FE36A, 3: 0xF4C4C4, 4: 0xA4C4F4, 5: 0xDCDCDC}


def from_list(s):
    """Creates a Suggestion object from a list. """
    return Suggestion(int(s[0]), s[1], datetime.fromisoformat(s[2]), s[3], int(s[4]), s[5], s[7],
                      s[8] if len(s) > 8 else None)


def update_suggestions():
    # Sort the list
    suggestion_list.sort(key=operator.attrgetter('id'))
    suggestion_list.sort(key=lambda x: statuses.inverse[x.status])

    # Clear the sheet
    cfg.Config.service.spreadsheets().values().clear(spreadsheetId=cfg.Config.config['suggestion_sheet'],
                                                     range='Suggestions!A2:I').execute()
    # Write new data
    r_body = {'values': [s.to_list() for s in suggestion_list]}
    cfg.Config.service.spreadsheets().values().append(spreadsheetId=cfg.Config.config['suggestion_sheet'],
                                                      range='Suggestions!A1', valueInputOption='RAW',
                                                      insertDataOption='INSERT_ROWS', body=r_body).execute()


class Suggestion:
    def __str__(self):
        return '{}: \t {}'.format(self.id, self.body)

    def __init__(self, id, msgid, time, username, userid, status, body, reason):
        self.id = id
        self.msgid = msgid
        self.time = time
        self.username = username
        self.userid = userid
        self.status = status
        self.body = body
        self.reason = reason

    def to_list(self):
        return [self.id, str(self.msgid), self.time.isoformat(), self.username, str(self.userid), self.status,
                statuses.inverse[self.status], self.body, self.reason]


class Suggestions(Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.lock = False  # Lock when changing the sheet over a period of time.

        # Initialise suggestion list
        suggestion_list.clear()
        suggestions = cfg.Config.service.spreadsheets().values().get(
            spreadsheetId=cfg.Config.config['suggestion_sheet'],
            range='Suggestions!A2:I').execute().get('values', [])
        for s in suggestions:
            suggestion_list.append(from_list(s))
        suggestion_list.sort(key=operator.attrgetter('id'))
        suggestion_list.sort(key=lambda x: statuses.inverse[x.status])
        # print([str(x) for x in suggestion_list])

    @commands.command(brief='Suggest a change to the server. ')
    @commands.cooldown(1, 600, BucketType.user)
    async def suggest(self, ctx, *, suggestion):
        if self.lock:
            await ctx.send("You're going too fast! Wait for the previous command to process!")
            return

        self.lock = True

        # Create message
        m = await self.bot.get_channel(cfg.Config.config['suggestion_channel']).send(
            '**Suggestion by <@!{}>**: (`#{}`) \n{}'.format(ctx.author.id, len(suggestion_list) + 1, suggestion))
        await m.add_reaction('👍')
        await m.add_reaction('🤷')
        await m.add_reaction('👎')
        await m.add_reaction('🔔')
        await m.add_reaction('🔕')

        # Add the new suggestion
        suggestion_list.append(
            Suggestion(len(suggestion_list) + 1, m.id, datetime.now(), ctx.author.name, ctx.author.id, 'Pending',
                       suggestion, None))

        # Update the sheet
        update_suggestions()
        self.lock = False

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

    @commands.command()
    @commands.is_owner()
    async def save_suggestions(self, ctx):
        try:
            update_suggestions()
        except Exception as e:
            await ctx.send('```Python \n {}```'.format(e))
            return
        await ctx.send('Finished!')

    @commands.command(aliases=['sugg_change'], brief='Updates the status of a given suggestion. ')
    @commands.check(cfg.is_staff)
    async def change_suggestion_status(self, ctx, sugg_id: int, new_status, *, reason):
        # Make sure not locked
        if self.lock:
            await ctx.send("You're going too fast! Wait for the previous command to process!")
            return

        self.lock = True

        # Validate status
        if new_status not in statuses.inverse:
            await ctx.send("I didn't recognise that status!")
            return

        # Figure out who needs to be notified
        ids_to_dm = set()

        # Get the message
        suggestion = None
        for s in suggestion_list:
            if s.id == sugg_id:
                suggestion = s
                break

        if suggestion is None:
            await ctx.send("No suggestion with that ID!")
            return

        suggestion_message = await self.bot.get_channel(cfg.Config.config['suggestion_channel']).fetch_message(
            suggestion.msgid)
        no_ping = set()
        votes_for = {}
        for reaction in suggestion_message.reactions:
            # Add everyone who reacted
            if not reaction.emoji == '🔕':
                users = await reaction.users().flatten()
                votes_for[reaction.emoji] = users - 1
                for u in users:
                    ids_to_dm.add(u.id)
            else:
                users = await reaction.users().flatten()
                for u in users:
                    no_ping.add(u.id)
        # Add everyone with the suggestions role
        suggestions_role_members = ctx.guild.get_role(cfg.Config.config['suggestion_role']).members
        for u in suggestions_role_members:
            ids_to_dm.add(u.id)

        # print(no_ping)
        # Remove everyone who reacted with no_bell
        for u in no_ping:
            if u in ids_to_dm:
                ids_to_dm.remove(u)

        # Print out ids_to_dm for logging purposes
        # print(ids_to_dm)

        # Construct the embed
        embed = discord.Embed(title="Suggestion status change",
                              description="Suggestion {} changed status from {} to {}".format(suggestion.id,
                                                                                              suggestion.status,
                                                                                              new_status),
                              colour=status_colours[statuses.inverse[new_status]])
        embed.add_field(name='Suggestor', value=suggestion.username, inline=False)
        embed.add_field(name='Content', value=suggestion.body, inline=False)
        embed.add_field(name='Reason', value=reason, inline=False)
        embed.add_field(name='Date/time', value=suggestion.time.isoformat(), inline=True)
        embed.add_field(name='Vote split',
                        value='👍: {}, 🤷: {}, 👎: {}'.format(votes_for['👍'], votes_for['🤷'], votes_for['👎']),
                        inline=True)

        embed.set_footer(
            text='You received this DM because you either have the `Suggestions-Notify` role, '
                 'voted on the suggestion, or reacted with 🔔. If you do not want to be notified '
                 'about suggestion changes, please react with 🔕. ')

        for u in ids_to_dm:
            # Spam people :_)
            member = ctx.guild.get_member(u)
            try:
                if member is not None and not member.bot:
                    await member.send(embed=embed)
            except discord.Forbidden:
                await ctx.guild.get_channel(cfg.Config.config['suggestion_discussion_channel']).send(member.mention,
                                                                                                     embed=embed)

        # Actually update the suggestion
        suggestion.status = new_status
        suggestion.reason = reason
        update_suggestions()

        # Finish up
        await ctx.send(
            "Finished. I have DMed the following people: {}. The following people requested not to be DMed: {}. ".format(
                [ctx.guild.get_member(x).display_name for x in ids_to_dm if ctx.guild.get_member(x) is not None],
                [ctx.guild.get_member(x).display_name for x in no_ping if ctx.guild.get_member(x) is not None]))
        self.lock = False


def setup(bot):
    bot.add_cog(Suggestions(bot))
