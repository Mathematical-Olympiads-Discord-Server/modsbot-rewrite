import asyncio
import operator
import time
from datetime import datetime

import bidict
import discord
from discord.ext import commands
from discord.ext.commands import BucketType

from cogs import config as cfg

Cog = commands.Cog
suggestion_list = []
tech_suggestion_list = []
statuses = bidict.bidict(
    {
        0: "Pending",
        1: "Mod-vote",
        2: "Approved",
        3: "Denied",
        4: "Revised",
        5: "Implemented",
        6: "Removed",
    }
)
status_colours = {
    0: 0xFCECB4,
    1: 0xFF8105,
    2: 0x5FE36A,
    3: 0xF4C4C4,
    4: 0xA4C4F4,
    5: 0xDCDCDC,
    6: 0x000000,
}
status_aliases = bidict.bidict(
    {
        0: ("pending", "p"),
        1: ("mod-vote", "modvote", "vote", "escalate", "escalated", "m", "v", "e"),
        2: ("approved", "approve", "accept", "accepted", "a"),
        3: ("denied", "deny", "reject", "rejected", "d"),
        4: ("revised", "revise", "r"),
        5: ("implemented", "implement", "i"),
        6: ("removed", "remove"),
    }
)


def from_list(s):
    while len(s) < 10:
        s.append("")

    # Id
    try:
        sugg_id = int(s[0])
    except ValueError:
        sugg_id = 0

    # Msg Id (string)
    msgid = s[1]

    # Time
    try:
        time = datetime.fromisoformat(s[2]) if s[2] else datetime.now()
    except ValueError:
        time = datetime.now()

    username = s[3]

    # UserID
    try:
        userid = int(s[4]) if s[4] and s[4].strip() else 0
    except ValueError:
        userid = 0

    status = s[5] or "Pending"

    # Body (Suggestion)
    body = s[7] if len(s) > 7 else ""

    # Reason (optional)
    reason = s[8] if len(s) > 8 and s[8] else None

    # Jump URL (optional)
    jump_url = s[9] if len(s) > 9 and s[9] else None

    return Suggestion(
        sugg_id,
        msgid,
        time,
        username,
        userid,
        status,
        body,
        reason,
        jump_url,
    )


async def update_suggestions():
    try:
        await asyncio.to_thread(upload_suggestion_list, suggestion_list, "Suggestions")
        await asyncio.to_thread(
            upload_suggestion_list, tech_suggestion_list, "Tech Suggestions"
        )
    except Exception as e:
        print(f"ERROR in update_suggestions: {e}")
        raise


def upload_suggestion_list(suggestion_list_var, sheet_name):
    suggestion_list_var.sort(key=operator.attrgetter("id"))
    # suggestion_list_var.sort(key=lambda x: statuses.inverse[x.status])

    # Remove duplicates by id
    suggestion_list_var = list(dict((s.id, s) for s in suggestion_list_var).values())
    suggestion_list_var.sort(key=operator.attrgetter("id"))
    # suggestion_list_var.sort(key=lambda x: statuses.inverse[x.status])

    # Clear the data rows (leave header)
    cfg.Config.service.spreadsheets().values().clear(
        spreadsheetId=cfg.Config.config["suggestion_sheet"], range=f"{sheet_name}!A2:J"
    ).execute()

    data_rows = [s.to_list() for s in suggestion_list_var]
    if not data_rows:
        return {"values": []}

    chunk_size = 100
    total_rows = len(data_rows)

    for start in range(0, total_rows, chunk_size):
        chunk = data_rows[start : start + chunk_size]
        body = {"values": chunk}
        max_retries = 3
        for attempt in range(max_retries):
            try:
                cfg.Config.service.spreadsheets().values().append(
                    spreadsheetId=cfg.Config.config["suggestion_sheet"],
                    range=f"{sheet_name}!A1",
                    valueInputOption="RAW",
                    insertDataOption="INSERT_ROWS",
                    body=body,
                ).execute()
                break
            except Exception:
                if attempt == max_retries - 1:
                    raise
                time.sleep(2**attempt)
        time.sleep(0.5)

    return {"values": data_rows}


class Suggestion:
    def __str__(self):
        return f"{self.id}: \t {self.body}"

    def __init__(
        self, id, msgid, time, username, userid, status, body, reason, jump_url
    ):
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
        return [
            self.id,
            str(self.msgid),
            self.time.isoformat(),
            self.username,
            str(self.userid),
            self.status,
            statuses.inverse[self.status],
            self.body,
            self.reason,
            self.jump_url,
        ]


class Suggestions(Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.lock = False  # Lock when changing the sheet over a period of time.
        self.initialize_suggestion_list()

    @commands.command(
        brief="Suggest a change to the server. ", cooldown_after_parsing=True
    )
    @commands.cooldown(1, 600, BucketType.user)
    async def suggest(self, ctx, *, suggestion):
        if self.lock:
            await ctx.send(
                "You're going too fast! Wait for the previous command to process!"
            )
            return

        await self.bot.get_cog("SuggestConfirmManager").suggest_confirm(
            ctx, suggestion=suggestion, mode="server"
        )

    @commands.command(
        brief="Suggest a tech change to the server. ", cooldown_after_parsing=True
    )
    @commands.cooldown(1, 600, BucketType.user)
    async def tech_suggest(self, ctx, *, suggestion):
        if self.lock:
            await ctx.send(
                "You're going too fast! Wait for the previous command to process!"
            )
            return

        await self.bot.get_cog("SuggestConfirmManager").suggest_confirm(
            ctx, suggestion=suggestion, mode="tech"
        )

    # add suggestion after confirmed
    async def add_suggestion(self, ctx, suggestion, mode):
        # check lock status, wait until unlocked
        while self.lock:
            await ctx.send(
                "You're going too fast! Wait for the previous command to process!"
            )
            return

        # Acquire the lock
        self.lock = True

        try:
            if mode == "server":
                target_channel = cfg.Config.config["suggestion_channel"]
                list_to_read = suggestion_list
                suggestion_string = "Suggestion"

            elif mode == "tech":
                target_channel = cfg.Config.config["tech_suggestion_channel"]
                list_to_read = tech_suggestion_list
                suggestion_string = "Tech Suggestion"

            # Create message
            target_channel_obj = self.bot.get_channel(target_channel)
            if target_channel_obj is None:
                await ctx.send("Suggestion channel not found.")
                return
            m = await target_channel_obj.send(
                f"**{suggestion_string} `#{len(list_to_read) + 1}` by "
                f"<@!{ctx.author.id}>:** `[Pending]`\n"
                f"<{ctx.message.jump_url}>\n"
                f"{suggestion[:1800]}"
            )
            await m.add_reaction("👍")
            await m.add_reaction("🤷")
            await m.add_reaction("👎")
            await m.add_reaction("🔔")
            await m.add_reaction("🔕")

            # Add the new suggestion
            if mode == "server":
                suggestion_list.append(
                    Suggestion(
                        len(suggestion_list) + 1,
                        str(m.id),
                        datetime.now(),
                        ctx.author.name,
                        ctx.author.id,
                        "Pending",
                        suggestion,
                        None,
                        ctx.message.jump_url,
                    )
                )
            elif mode == "tech":
                tech_suggestion_list.append(
                    Suggestion(
                        len(tech_suggestion_list) + 1,
                        str(m.id),
                        datetime.now(),
                        ctx.author.name,
                        ctx.author.id,
                        "Pending",
                        suggestion,
                        None,
                        ctx.message.jump_url,
                    )
                )

            # Update the sheet
            await update_suggestions()
        finally:
            # Release the lock
            self.lock = False

    @commands.command()
    @commands.is_owner()
    async def index_suggestions(self, ctx, *, channel: int):
        channel_obj = self.bot.get_channel(channel)
        if channel_obj is None:
            await ctx.send("Channel not found.")
            return
        messages = [x async for x in channel_obj.history(limit=200)]
        values = []
        for message in messages:
            values.append(
                [
                    message.created_at.isoformat(),
                    message.author.name,
                    str(message.author.id),
                    "Pending",
                    0,
                    message.content,
                ],
                "",
                message.jump_url,
            )
        r_body = {"values": values}
        cfg.Config.service.spreadsheets().values().append(
            spreadsheetId=cfg.Config.config["suggestion_sheet"],
            range="Suggestions!A1",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body=r_body,
        ).execute()

    @commands.command()
    @commands.is_owner()
    async def save_suggestions(self, ctx):
        try:
            update_suggestions()
        except Exception as e:
            await ctx.send(f"```Python \n {e}```")
            return
        await ctx.send("Finished!")

    @commands.command()
    @commands.check(cfg.is_mod_or_tech)
    async def fix_msgids(self, ctx):
        await ctx.send("Fixing message IDs... This may take a while.")
        fixed_count = 0
        for suggestion in suggestion_list + tech_suggestion_list:
            if suggestion.jump_url:
                try:
                    parts = suggestion.jump_url.split("/")
                    if len(parts) >= 7:
                        msg_id = int(parts[-1])
                        channel_id = int(parts[-2])
                        if command_channel := self.bot.get_channel(channel_id):
                            command_msg = await command_channel.fetch_message(msg_id)
                            command_time = command_msg.created_at
                            if suggestion in suggestion_list:
                                sugg_channel_id = cfg.Config.config[
                                    "suggestion_channel"
                                ]
                            else:
                                sugg_channel_id = cfg.Config.config[
                                    "tech_suggestion_channel"
                                ]
                            if sugg_channel := self.bot.get_channel(sugg_channel_id):
                                async for msg in sugg_channel.history(
                                    limit=10, after=command_time
                                ):
                                    if (
                                        msg.author == self.bot.user
                                        and suggestion.jump_url in msg.content
                                    ):
                                        suggestion.msgid = str(msg.id)
                                        fixed_count += 1
                                        break
                except Exception as e:
                    print(f"Error fixing msgid for suggestion {suggestion.id}: {e}")
        await update_suggestions()
        await ctx.send(f"Fixed {fixed_count} message IDs.")

    async def change_suggestion_status_back(
        self, ctx, sugg_id: int, new_status, reason, mode, notify: bool = True
    ) -> Suggestion:
        bot_spam = ctx.guild.get_channel(cfg.Config.config["bot_spam_channel"])
        if bot_spam is None:
            bot_spam = ctx.channel

        suggestion_channel = ""
        list_to_read = []
        suggestion_string = ""
        if mode == "server":
            suggestion_channel = cfg.Config.config["suggestion_channel"]
            list_to_read = suggestion_list
            suggestion_string = "Suggestion"
        elif mode == "tech":
            suggestion_channel = cfg.Config.config["tech_suggestion_channel"]
            list_to_read = tech_suggestion_list
            suggestion_string = "Tech Suggestion"

        # Make sure not locked
        # Make sure not locked
        if self.lock:
            await bot_spam.send(
                "You're going too fast! Wait for the previous command to process!"
            )
            return

        # Validate status
        if new_status not in statuses.inverse:
            await ctx.send("I didn't recognise that status!")
            return

        # Set lock and enter try block immediately
        self.lock = True
        try:
            # Figure out who needs to be notified
            ids_to_dm = set()

            # Get the message
            suggestion = next((s for s in list_to_read if s.id == sugg_id), None)
            if suggestion is None:
                await bot_spam.send("No suggestion with that ID!")
                return

            suggestion_channel_obj = self.bot.get_channel(suggestion_channel)
            if suggestion_channel_obj is None:
                await bot_spam.send("Suggestion channel not found.")
                return

            try:
                suggestion_message = await suggestion_channel_obj.fetch_message(
                    suggestion.msgid
                )
            except discord.NotFound:
                await bot_spam.send(
                    "Suggestion message not found (it may have been deleted). "
                    "Updating status anyway."
                )
                suggestion_message = None
            except discord.HTTPException as e:
                self.bot.logger.error(f"Failed to fetch suggestion message: {e}")
                await bot_spam.send(f"Error fetching suggestion message: {e}")
                return

            voted = set()
            votes_for = {}
            bell = set()
            no_bell = set()
            if suggestion_message is not None:
                for reaction in suggestion_message.reactions:
                    # Add everyone who reacted
                    if reaction.emoji == "🔔":
                        users = [x async for x in reaction.users()]
                        bell = {u.id for u in users}
                    elif reaction.emoji == "🔕":
                        users = [x async for x in reaction.users()]
                        no_bell = {u.id for u in users}
                    else:
                        users = [x async for x in reaction.users()]
                        votes_for[reaction.emoji] = len(users) - 1
                        for u in users:
                            voted.add(u.id)

            # Add everyone with the suggestions role
            # Get suggestion role (if it exists)
            suggestion_role_id = cfg.Config.config.get("suggestion_role")
            suggestion_role_obj = (
                ctx.guild.get_role(suggestion_role_id) if suggestion_role_id else None
            )
            if suggestion_role_obj:
                ping_role = {x.id for x in suggestion_role_obj.members}
            else:
                ping_role = set()
                if suggestion_role_id:
                    self.bot.logger.warning(
                        f"Role with ID {suggestion_role_id} not found in guild "
                        f"{ctx.guild.id}"
                    )

            # Get no‑notify role
            no_notify_role_id = cfg.Config.config.get("suggestion_no_notify")
            no_notify_role_obj = (
                ctx.guild.get_role(no_notify_role_id) if no_notify_role_id else None
            )
            if no_notify_role_obj:
                no_ping_role = {x.id for x in no_notify_role_obj.members}
            else:
                no_ping_role = set()
                if no_notify_role_id:
                    self.bot.logger.warning(
                        f"Role with ID {no_notify_role_id} "
                        f"not found in guild {ctx.guild.id}"
                    )

            ids_to_dm = (
                ids_to_dm.union(ping_role)
                .union(voted)
                .difference(no_bell)
                .difference(no_ping_role)
                .union(bell)
            )

            # Construct the embed
            embed = discord.Embed(
                title=f"{suggestion_string} status change",
                description=f"{suggestion_string} {suggestion.id} changed status from "
                f"{suggestion.status} to {new_status}",
                colour=status_colours[statuses.inverse[new_status]],
            )
            embed.add_field(name="Suggestor", value=suggestion.username, inline=False)
            embed.add_field(name="Content", value=suggestion.body[:1000], inline=False)
            if len(suggestion.body) > 1000:
                embed.add_field(
                    name="More content",
                    value=suggestion.body[1000:1124],
                    inline=False,  # 1024 chars max
                )
            if reason is not None:
                embed.add_field(name="Reason", value=reason[:1024], inline=False)
            embed.add_field(
                name="Date/time", value=suggestion.time.isoformat(), inline=True
            )
            embed.add_field(
                name="Vote split",
                value=(
                    f'👍: {votes_for.get("👍", 0)}, '
                    f'🤷: {votes_for.get("🤷", 0)}, '
                    f'👎: {votes_for.get("👎", 0)}'
                ),
                inline=True,
            )

            embed.set_footer(
                text=(
                    "You received this DM because you either have the "
                    "`Suggestions-Notify` role, "
                    "voted on the suggestion, or reacted with 🔔. "
                    "If you do not want to be notified about suggestion changes, "
                    "please react with 🔕. "
                )
            )

            if notify:
                dm_failed = []
                for id in ids_to_dm:
                    # Spam people :_)
                    member = ctx.guild.get_member(id)
                    try:
                        if member is not None and not member.bot:
                            await member.send(embed=embed)
                    except discord.HTTPException as e:
                        print(f"Failed to DM {member}: {e}")
                        dm_failed.append(id)
                if dm_failed != []:
                    msg = (
                        "Remember to turn on DMs from this server to get private "
                        "notifications! "
                    )
                    for id in dm_failed:
                        msg += f"<@{id}> "
                    if len(msg) > 1800:
                        msg = f"{msg[:1800]}..."
                    try:
                        await bot_spam.send(msg, embed=embed)
                    except discord.HTTPException as e:
                        self.bot.logger.error(
                            f"Failed to send DM failure notification: {e}"
                        )
                        # Try sending just the message without embed
                        try:
                            await bot_spam.send(msg)
                        except discord.HTTPException as e2:
                            self.bot.logger.error(
                                f"Failed to send DM failure message: {e2}"
                            )

            # Actually update the suggestion
            suggestion.status = new_status
            suggestion.reason = reason
            await update_suggestions()
            content = (
                f"**{suggestion_string} `#{sugg_id}` by <@!{suggestion.userid}>:** "
                f"`[{new_status}: {reason}]`\n"
                f"{suggestion.jump_url}\n"
                f"{suggestion.body[:1800]}"
            )
            if suggestion_message is not None:
                try:
                    await suggestion_message.edit(content=content)
                except discord.NotFound:
                    self.bot.logger.warning(
                        f"Suggestion message was deleted "
                        f"while processing: {suggestion.msgid}"
                    )
                except discord.HTTPException as e:
                    self.bot.logger.error(f"Failed to edit suggestion message: {e}")
                suggestion.msgid = str(suggestion_message.id)

            # Finish up
            try:
                await bot_spam.send("Finished.")
            except discord.HTTPException as e:
                self.bot.logger.error(f"Failed to send 'Finished' message: {e}")

            log_channel = ctx.guild.get_channel(cfg.Config.config["log_channel"])
            if log_channel is not None:
                try:
                    await log_channel.send(
                        f"**{suggestion_string} `#{sugg_id}` "
                        f"set to `[{new_status}]` by "
                        f"{ctx.author.nick} ({ctx.author.id})\n"
                        f"Reason: `{reason}`**\n"
                        f"{suggestion.body[:1800]}"
                    )
                except discord.HTTPException as e:
                    self.bot.logger.error(f"Failed to send log message: {e}")
        finally:
            self.lock = False
        return suggestion

    @commands.command(
        aliases=["sugg_change"], brief="Updates the status of a given suggestion. "
    )
    @commands.check(cfg.is_staff)
    async def change_suggestion_status(self, ctx, sugg_id: int, new_status, *, reason):
        await self.change_suggestion_status_back(
            ctx, sugg_id, new_status, reason, "server"
        )

    @commands.command(aliases=["escl", "modvote"])
    @commands.check(cfg.is_staff)
    async def escalate(self, ctx, sugg_id: int, *, reason=None):
        suggestion = await self.change_suggestion_status_back(
            ctx, sugg_id, "Mod-vote", reason, "server"
        )
        if suggestion is None:
            return
        suggestion_channel_obj = self.bot.get_channel(
            cfg.Config.config["suggestion_channel"]
        )
        if suggestion_channel_obj is None:
            await ctx.send("Suggestion channel not found.")
            return
        try:
            m = await suggestion_channel_obj.fetch_message(suggestion.msgid)
        except discord.NotFound:
            await ctx.send("Suggestion message not found (it may have been deleted).")
            return
        except discord.HTTPException as e:
            self.bot.logger.error(
                f"Failed to fetch suggestion message in escalate: {e}"
            )
            await ctx.send(f"Error fetching suggestion message: {e}")
            return
        await self.bot.get_cog("ModsVote").modsvote(ctx, content=m.content)
        cursor = cfg.db.cursor()
        cursor.execute("SELECT msg_id FROM mods_vote ORDER BY rowid DESC LIMIT 1")
        msg_id = cursor.fetchone()[0]
        suggestion.msgid = str(msg_id)
        await update_suggestions()

    # Modify suggestion status
    @commands.command()
    @commands.check(cfg.is_staff)
    async def approve(self, ctx, sugg_id: int, *, reason=None):
        await self.change_suggestion_status_back(
            ctx, sugg_id, "Approved", reason, "server"
        )

    @commands.command()
    @commands.check(cfg.is_staff)
    async def deny(self, ctx, sugg_id: int, *, reason=None):
        await self.change_suggestion_status_back(
            ctx, sugg_id, "Denied", reason, "server"
        )

    @commands.command()
    @commands.check(cfg.is_staff)
    async def revised(self, ctx, sugg_id: int, *, reason=None):
        await self.change_suggestion_status_back(
            ctx, sugg_id, "Revised", reason, "server"
        )

    @commands.command()
    @commands.check(cfg.is_staff)
    async def implemented(self, ctx, sugg_id: int, *, reason=None):
        await self.change_suggestion_status_back(
            ctx, sugg_id, "Implemented", reason, "server"
        )

    @commands.command()
    @commands.check(cfg.is_staff)
    async def remove_sg(self, ctx, sugg_id: int, *, reason=None):
        await self.change_suggestion_status_back(
            ctx, sugg_id, "Removed", reason, "server"
        )

    # Modify tech suggestion status
    @commands.command()
    @commands.check(cfg.is_mod_or_tech)
    async def tech_approve(self, ctx, sugg_id: int, *, reason=None):
        await self.change_suggestion_status_back(
            ctx, sugg_id, "Approved", reason, "tech"
        )

    @commands.command()
    @commands.check(cfg.is_mod_or_tech)
    async def tech_deny(self, ctx, sugg_id: int, *, reason=None):
        await self.change_suggestion_status_back(ctx, sugg_id, "Denied", reason, "tech")

    @commands.command()
    @commands.check(cfg.is_mod_or_tech)
    async def tech_revised(self, ctx, sugg_id: int, *, reason=None):
        await self.change_suggestion_status_back(
            ctx, sugg_id, "Revised", reason, "tech"
        )

    @commands.command()
    @commands.check(cfg.is_mod_or_tech)
    async def tech_implemented(self, ctx, sugg_id: int, *, reason=None):
        await self.change_suggestion_status_back(
            ctx, sugg_id, "Implemented", reason, "tech"
        )

    @commands.command()
    @commands.check(cfg.is_mod_or_tech)
    async def tech_remove_sg(self, ctx, sugg_id: int, *, reason=None):
        await self.change_suggestion_status_back(
            ctx, sugg_id, "Removed", reason, "tech"
        )

    @commands.command()
    @commands.check(cfg.is_staff)
    async def unlock_suggestions(self, ctx):
        self.lock = False

    @commands.command()
    @commands.is_owner()
    async def force_unlock(self, ctx):
        """Manually unlock the suggestions cog (owner only)."""
        self.lock = False
        await ctx.send("Lock manually released.")

    @commands.command()
    @commands.is_owner()
    async def multichg(self, ctx, *, commands):
        new_statuses = [
            [j.strip() for j in i.strip().split(" ")] for i in commands.split("\n")
        ]
        for status in new_statuses:
            suggestion = await self.change_suggestion_status_back(
                ctx,
                int(status[0]),
                status[1],
                " ".join(status[2:]) if len(status) > 2 else None,
                "server",
            )
            if status[1] == "Mod-vote":
                suggestion_channel_obj = self.bot.get_channel(
                    cfg.Config.config["suggestion_channel"]
                )
                if suggestion_channel_obj is None:
                    await ctx.send("Suggestion channel not found.")
                    continue
                mod_vote_chan_obj = self.bot.get_channel(
                    cfg.Config.config["mod_vote_chan"]
                )
                if mod_vote_chan_obj is None:
                    await ctx.send("Mod vote channel not found.")
                    continue
                try:
                    m = await suggestion_channel_obj.fetch_message(suggestion.msgid)
                except discord.NotFound:
                    await ctx.send(
                        f"Suggestion message for ID {status[0]} not found "
                        f"(it may have been deleted)."
                    )
                    continue
                except discord.HTTPException as e:
                    self.bot.logger.error(
                        f"Failed to fetch suggestion message in multichg: {e}"
                    )
                    await ctx.send(
                        f"Error fetching suggestion message for ID {status[0]}: {e}"
                    )
                    continue
                await mod_vote_chan_obj.send(m.content)

            await ctx.send(f"Done {status}")

    @commands.command()
    @commands.check(cfg.is_mod_or_tech)
    async def sync_suggestion(self, ctx):
        self.initialize_suggestion_list()
        await ctx.send("Sync with suggestion sheet completed.")

    @Cog.listener()
    async def on_message(self, message: discord.Message):
        if (
            message.channel.id != cfg.Config.config["suggestion_channel"]
            or not message.reference
        ):
            return
        if message.author.id not in cfg.Config.config["staff"]:
            return

        ctx = await self.bot.get_context(message)

        # Get suggestion
        suggestion = None
        for s in suggestion_list:
            if s.msgid == str(message.reference.message_id):
                suggestion = s
                break
        if suggestion is None:
            return

        # Identify suggestion status
        space = message.content.find(" ")
        if space == -1:
            new_status = message.content
            reason = None
        else:
            new_status = message.content[:space]
            reason = message.content[space + 1 :]
        valid = False
        for i in status_aliases.inverse:
            if new_status.lower() in i:
                new_status = statuses[status_aliases.inverse[i]]
                valid = True
                break
        if not valid:
            return

        # Change suggestion status
        await self.change_suggestion_status_back(
            ctx, int(s.id), new_status, reason, "server"
        )

        # Delete message
        await message.delete(delay=15)

    def initialize_suggestion_list(self):
        # Initialise suggestion list
        suggestion_list.clear()
        suggestions = (
            cfg.Config.service.spreadsheets()
            .values()
            .get(
                spreadsheetId=cfg.Config.config["suggestion_sheet"],
                range="Suggestions!A2:J",
            )
            .execute()
            .get("values", [])
        )
        for s in suggestions:
            suggestion_list.append(from_list(s))
        suggestion_list.sort(key=operator.attrgetter("id"))
        suggestion_list.sort(key=lambda x: statuses.inverse[x.status])

        # Initialise tech suggestion list
        tech_suggestion_list.clear()
        tech_suggestions = (
            cfg.Config.service.spreadsheets()
            .values()
            .get(
                spreadsheetId=cfg.Config.config["suggestion_sheet"],
                range="Tech Suggestions!A2:J",
            )
            .execute()
            .get("values", [])
        )
        for s in tech_suggestions:
            tech_suggestion_list.append(from_list(s))
        tech_suggestion_list.sort(key=operator.attrgetter("id"))
        tech_suggestion_list.sort(key=lambda x: statuses.inverse[x.status])


async def setup(bot):
    await bot.add_cog(Suggestions(bot))
