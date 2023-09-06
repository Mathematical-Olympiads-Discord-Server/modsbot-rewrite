import asyncio

import discord
from discord.ext import commands

from cogs import config as cfg


class SuggestConfirmManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_suggest_confirms = {}

    # Deletes suggest_confirms after a certain time.
    async def delete_after(self, timeout: int, suggest_confirm_id):
        await asyncio.sleep(timeout)
        if suggest_confirm_id in self.active_suggest_confirms:
            await self.active_suggest_confirms[suggest_confirm_id].remove()
            del self.active_suggest_confirms[suggest_confirm_id]

    async def suggest_confirm(self, ctx: commands.Context, suggestion: str, mode: str):
        suggest_confirm = SuggestConfirm(self.bot, ctx, suggestion, mode)
        await suggest_confirm.open()
        self.active_suggest_confirms[suggest_confirm.message.id] = suggest_confirm
        await self.delete_after(600, suggest_confirm.message.id)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id:
            return
        if (
            payload.message_id in self.active_suggest_confirms
            and self.active_suggest_confirms[payload.message_id].authorId
            == payload.user_id
        ):
            if payload.emoji.name == "✅":
                await self.active_suggest_confirms[payload.message_id].confirm()
                await self.delete_after(0, payload.message_id)
            elif payload.emoji.name == "❌":
                await self.delete_after(0, payload.message_id)


class SuggestConfirm:
    def __init__(self, bot, ctx: commands.Context, suggestion: str, mode: str):
        self.bot = bot
        self.ctx = ctx
        self.authorId = ctx.author.id
        self.message = None
        self.suggestion = suggestion
        self.suggestion_url = ctx.message.jump_url
        self.mode = mode

    async def open(self):
        # TODO: edit the message
        self.message = await self.ctx.send(
            f"<@!{self.authorId}> You are about to submit the following suggestion:\n<{self.suggestion_url}>\n{self.suggestion}\n\n"
            "Confirm by reacting ✅, Cancel by reacting ❌"
        )
        await self.message.add_reaction("✅")
        await self.message.add_reaction("❌")

    async def confirm(self):
        await self.bot.get_cog("Suggestions").add_suggestion(
            ctx=self.ctx, suggestion=self.suggestion, mode=self.mode
        )
        await self.remove()

    async def remove(self):
        try:
            await self.message.delete()
        except discord.NotFound:
            pass


async def setup(bot):
    await bot.add_cog(SuggestConfirmManager(bot))
