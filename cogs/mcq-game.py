import random

from discord.ext import commands

from cogs import config as cfg

Cog = commands.Cog

cursor = cfg.db.cursor()
cursor.execute("SELECT COUNT(*) from problems;")
number_of_questions = cursor.fetchone()[0]
games = {}


class Game:
    def __init__(self, ctx, questions):
        self.players = {}
        self.has_answered = set()
        self.ctx = ctx
        self.num_questions = questions
        self.current_question = 0
        self.current_answer = None
        self.previous_source = None

    async def new_question(self):
        qid = random.randint(1, number_of_questions)
        cursor.execute(f"SELECT * FROM problems WHERE idproblems = {qid}")
        problem = cursor.fetchone()
        m = await self.ctx.send(problem[1])  # problem statement
        await m.delete()
        if problem[2] != "":
            await self.ctx.send(f"Extra links: \n{problem[2]}")  # extra attachments
        self.current_answer = problem[3]
        self.previous_source = problem[4]
        self.has_answered.clear()

    async def process(self, message):
        if message.author not in self.players:
            return

        await message.delete()
        if message.author in self.has_answered:
            await self.ctx.send("You have already answered!")
            return
        else:
            self.has_answered.add(message.author)
            if message.content == self.current_answer:
                await self.ctx.send(
                    f"Correct answer from {message.author.display_name}"
                )
                await self.ctx.send(f"Previous source: {self.previous_source}")
                await self.new_question()
                self.players[message.author] += 1
            else:
                await message.author.send("Wrong!")


class MCQ_Game_Controller(Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=["prob"])
    async def get_random_problem(self, ctx):
        qid = random.randint(1, number_of_questions)
        cursor.execute(f"SELECT * FROM problems WHERE idproblems = {qid}")
        problem = cursor.fetchone()
        m = await ctx.send(problem[1])  # problem statement
        await m.delete()
        if problem[2] != "":
            await ctx.send(f"Extra links: \n{problem[2]}")  # extra attachments

    @commands.command()
    @commands.is_owner()
    async def new_game(self, ctx, questions: int = 10):
        if ctx.channel.id in games:
            await ctx.send("Game already running in this channel")
            return
        else:
            await ctx.send("New game starting in 1 minute. ")
            games[ctx.channel.id] = Game(ctx, questions)

    @commands.command()
    async def join_game(self, ctx):
        chan = ctx.channel.id
        if chan in games and games[chan].is_accepting_owners:
            games[chan].players = 0
        else:
            await ctx.send("No game in this channel!")

    @Cog.listener()
    async def on_message(self, message):
        if message.channel.id in games:
            games[message.channel.id].process(message)


async def setup(bot):
    await bot.add_cog(MCQ_Game_Controller(bot))
