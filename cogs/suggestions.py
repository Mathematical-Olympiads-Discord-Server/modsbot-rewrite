import operator
from datetime import datetime

import bidict
import discord
from discord.ext import commands
from discord.ext.commands import BucketType

from cogs import config as cfg

Cog = commands.Cog
suggestion_list = []
statuses = bidict.bidict(
    {0: 'Pending', 1: 'Mod-vote', 2: 'Approved', 3: 'Denied', 4: 'Revised', 5: 'Implemented', 6: 'Removed'})
status_colours = {0: 0xFCECB4, 1: 0xFF8105, 2: 0x5FE36A, 3: 0xF4C4C4, 4: 0xA4C4F4, 5: 0xDCDCDC, 6: 0x000000}
status_aliases = bidict.bidict(
    {0: ('pending', 'p'), 1: ('mod-vote', 'modvote', 'vote', 'escalate', 'escalated', 'm', 'v', 'e'), 
    2: ('approved', 'approve', 'accept', 'accepted', 'a'), 3: ('denied', 'deny', 'reject', 'rejected', 'd'), 
    4: ('revised', 'revise', 'r'), 5: ('implemented', 'implement', 'i'), 6: ('removed', 'remove')})


def from_list(s):
    """Creates a Suggestion object from a list. """
    return Suggestion(int(s[0]), s[1], datetime.fromisoformat(s[2]), s[3], int(s[4]), s[5], s[7],
                      s[8] if len(s) > 8 else None, s[9] if len(s) > 9 else None)


def update_suggestions():
    # Sort the list
    suggestion_list.sort(key=operator.attrgetter('id'))
    suggestion_list.sort(key=lambda x: statuses.inverse[x.status])

    # Clear the sheet
    cfg.Config.service.spreadsheets().values().clear(spreadsheetId=cfg.Config.config['suggestion_sheet'],
                                                     range='Suggestions!A2:J').execute()
    # Write new data
    r_body = {'values': [s.to_list() for s in suggestion_list]}
    cfg.Config.service.spreadsheets().values().append(spreadsheetId=cfg.Config.config['suggestion_sheet'],
                                                      range='Suggestions!A1', valueInputOption='RAW',
                                                      insertDataOption='INSERT_ROWS', body=r_body).execute()


class Suggestion:
    def __str__(self):
        return '{}: \t {}'.format(self.id, self.body)

    def __init__(self, id, msgid, time, username, userid, status, body, reason, jump_url):
        self.id = id
        self.msgid = msgid
        self.time = time
        self.username = username
        self.userid = userid
        self.status = status
        self.body = body
        self.reason = reason
        self.jump_url = jump_url

    def to_list(self):
        return [self.id, str(self.msgid), self.time.isoformat(), self.username, str(self.userid), self.status,
                statuses.inverse[self.status], self.body, self.reason, self.jump_url]


class Suggestions(Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.lock = False  # Lock when changing the sheet over a period of time.

        # Initialise suggestion list
        suggestion_list.clear()
        suggestions = cfg.Config.service.spreadsheets().values().get(
            spreadsheetId=cfg.Config.config['suggestion_sheet'],
            range='Suggestions!A2:J').execute().get('values', [])
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
            f'**Suggestion `#{len(suggestion_list) + 1}` by <@!{ctx.author.id}>:** `[Pending]`\n<{ctx.message.jump_url}>\n{suggestion}')
        await m.add_reaction('👍')
        await m.add_reaction('🤷')
        await m.add_reaction('👎')
        await m.add_reaction('🔔')
        await m.add_reaction('🔕')

        # Add the new suggestion
        suggestion_list.append(
            Suggestion(len(suggestion_list) + 1, str(m.id), datetime.now(), ctx.author.name, ctx.author.id, 'Pending',
                       suggestion, None, ctx.message.jump_url))

        # Update the sheet
        update_suggestions()
        self.lock = False

    @commands.command()
    @commands.is_owner()
    async def index_suggestions(self, ctx, *, channel: int):
        messages = [message async for message in await self.bot.get_channel(channel).history(limit=200)]
        values = []
        for message in messages:
            values.append([message.created_at.isoformat(), message.author.name, str(message.author.id), 'Pending', 0,
                           message.content], "", message.jump_url)
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

    async def change_suggestion_status_back(self, ctx, sugg_id: int, new_status, reason,
                                            notify: bool = True) -> Suggestion:

        bot_spam = ctx.guild.get_channel(cfg.Config.config['bot_spam_channel'])
        
        # Make sure not locked
        if self.lock:
            await bot_spam.send("You're going too fast! Wait for the previous command to process!")
            return

        self.lock = True

        # Validate status
        if new_status not in statuses.inverse:
            await ctx.send("I didn't recognise that status!")
            self.lock = False
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
            await bot_spam.send("No suggestion with that ID!")
            self.lock = False
            return

        suggestion_message = await self.bot.get_channel(cfg.Config.config['suggestion_channel']).fetch_message(
            suggestion.msgid)
        voted = set()
        votes_for = {}
        if suggestion_message is not None:
            for reaction in suggestion_message.reactions:
                # Add everyone who reacted
                if reaction.emoji == '🔔':
                    bell = set([x.id for x in await reaction.users().flatten()])
                elif reaction.emoji == '🔕':
                    no_bell = set([x.id for x in await reaction.users().flatten()])
                else:
                    users = await reaction.users().flatten()
                    votes_for[reaction.emoji] = len(users) - 1
                    for u in users:
                        voted.add(u.id)
        # Add everyone with the suggestions role
        ping_role = set([x.id for x in ctx.guild.get_role(cfg.Config.config['suggestion_role']).members])
        no_ping_role = set([x.id for x in ctx.guild.get_role(cfg.Config.config['suggestion_no_notify']).members])
        ids_to_dm = set()
        ids_to_dm = ids_to_dm.union(ping_role).union(voted).difference(no_bell).difference(no_ping_role).union(bell)

        # Print out ids_to_dm for logging purposes
        # print(ids_to_dm)

        # Construct the embed
        embed = discord.Embed(title="Suggestion status change",
                              description="Suggestion {} changed status from {} to {}".format(suggestion.id,
                                                                                              suggestion.status,
                                                                                              new_status),
                              colour=status_colours[statuses.inverse[new_status]])
        embed.add_field(name='Suggestor', value=suggestion.username, inline=False)
        embed.add_field(name='Content', value=suggestion.body[:1000], inline=False)
        if len(suggestion.body) > 1000:
            embed.add_field(name='More content', value=suggestion.body[1000:], inline=False)
        if reason is not None:
            embed.add_field(name='Reason', value=reason, inline=False)
        embed.add_field(name='Date/time', value=suggestion.time.isoformat(), inline=True)
        embed.add_field(name='Vote split',
                        value='👍: {}, 🤷: {}, 👎: {}'.format(votes_for['👍'], votes_for['🤷'], votes_for['👎']),
                        inline=True)

        embed.set_footer(
            text='You received this DM because you either have the `Suggestions-Notify` role, '
                 'voted on the suggestion, or reacted with 🔔. If you do not want to be notified '
                 'about suggestion changes, please react with 🔕. ')

        if notify:
            dm_failed = []
            for id in ids_to_dm:
                # Spam people :_)
                member = ctx.guild.get_member(id)
                try:
                    if member is not None and not member.bot:
                        await member.send(embed=embed)
                except Exception:
                    dm_failed.append(id)
            if dm_failed != []:
                msg = 'Remember to turn on DMs from this server to get private notifications! '
                for id in dm_failed: msg += f'<@{id}> '
                await bot_spam.send(msg, embed=embed)

        # Actually update the suggestion
        suggestion.status = new_status
        suggestion.reason = reason
        update_suggestions()
        suggestion_message = await suggestion_message.edit(
            content=f'**Suggestion `#{sugg_id}` by <@!{suggestion.userid}>:** `[{new_status}]`\n{suggestion.jump_url}\n{suggestion.body}')

        # Finish up
        await bot_spam.send('Finished.')
        await ctx.guild.get_channel(cfg.Config.config['log_channel']).send(
            f'**Suggestion `#{sugg_id}` set to `[{new_status}]` by {ctx.author.nick} ({ctx.author.id})\nReason: `{reason}`**\n{suggestion.body}')
        self.lock = False
        return suggestion

    @commands.command(aliases=['sugg_change'], brief='Updates the status of a given suggestion. ')
    @commands.check(cfg.is_staff)
    async def change_suggestion_status(self, ctx, sugg_id: int, new_status, *, reason):
        await self.change_suggestion_status_back(ctx, sugg_id, new_status, reason)

    @commands.command(aliases=['escl', 'modvote'])
    @commands.check(cfg.is_staff)
    async def escalate(self, ctx, sugg_id: int, *, reason=None):
        suggestion = await self.change_suggestion_status_back(ctx, sugg_id, 'Mod-vote', reason)
        m = await self.bot.get_channel(cfg.Config.config['suggestion_channel']).fetch_message(suggestion.msgid)
        await self.bot.get_channel(cfg.Config.config['mod_vote_chan']).send(m.content)

    @commands.command()
    @commands.check(cfg.is_staff)
    async def approve(self, ctx, sugg_id: int, *, reason=None):
        await self.change_suggestion_status_back(ctx, sugg_id, 'Approved', reason)

    @commands.command()
    @commands.check(cfg.is_staff)
    async def deny(self, ctx, sugg_id: int, *, reason=None):
        await self.change_suggestion_status_back(ctx, sugg_id, 'Denied', reason)

    @commands.command()
    @commands.check(cfg.is_staff)
    async def implemented(self, ctx, sugg_id: int, *, reason=None):
        await self.change_suggestion_status_back(ctx, sugg_id, 'Implemented', reason)

    @commands.command()
    @commands.check(cfg.is_staff)
    async def remove_sg(self, ctx, sugg_id: int, *, reason=None):
        await self.change_suggestion_status_back(ctx, sugg_id, 'Removed', reason)

    @commands.command()
    @commands.check(cfg.is_staff)
    async def unlock_suggestions(self, ctx):
        self.lock = False

    @commands.command()
    @commands.is_owner()
    async def multichg(self, ctx, *, commands):
        new_statuses = [[j.strip() for j in i.strip().split(' ')] for i in commands.split('\n')]
        for status in new_statuses:
            suggestion = await self.change_suggestion_status_back(ctx, int(status[0]), status[1],
                                                                  ' '.join(status[2:]) if len(status) > 2 else None)
            if status[1] == 'Mod-vote':
                m = await self.bot.get_channel(cfg.Config.config['suggestion_channel']). \
                    fetch_message(suggestion.msgid)
                await self.bot.get_channel(cfg.Config.config['mod_vote_chan']).send(m.content)

            await ctx.send(f'Done {status}')

    @Cog.listener()
    async def on_message(self, message: discord.Message):
        if (message.channel.id == cfg.Config.config['suggestion_channel']) and message.reference:

            if not message.author.id in cfg.Config.config['staff']:
                return

            ctx = await self.bot.get_context(message)

            # Get suggestion
            suggestion = None
            for s in suggestion_list:
                if s.msgid == str(message.reference.message_id):
                    suggestion = s
                    break
            if suggestion == None:
                return

            # Identify suggestion status
            space = message.content.find(' ')
            if space == -1:
                new_status = message.content
                reason = None
            else:
                new_status = message.content[:space]
                reason = message.content[space + 1:]
            valid = False
            for i in status_aliases.inverse:
                if new_status.lower() in i:
                    new_status = statuses[status_aliases.inverse[i]]
                    valid = True
                    break
            if not valid:
                return

            # Change suggestion status
            await self.change_suggestion_status_back(ctx, int(s.id), new_status, reason)

            # Delete message
            await message.delete(delay=15)


async def setup(bot):
    await bot.add_cog(Suggestions(bot))
