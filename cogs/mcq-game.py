import random

import mysql.connector
from discord.ext import commands

Cog = commands.Cog
f = open('data/dbcred.txt', 'r')
db = mysql.connector.connect(
    host=f.readline(),
    user=f.readline(),
    password=f.readline(),
    database=f.readline()
)
cursor = db.cursor()
number_of_questions = cursor.execute('SELECT COUNT(*) from problems;')

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
        cursor.execute('SELECT * FROM problems WHERE idproblem = {}'.format(qid))
        problem = cursor.fetchone()
        m = await self.ctx.send(problem[1])  # problem statement
        await m.delete()
        if not problem[2] == '':
            await self.ctx.send('Extra links: \n{}'.format(problem[2]))  # extra attachments
        self.current_answer = problem[3]
        self.previous_source = problem[4]
        self.has_answered.clear()

    async def process(self, message):
        if message.author not in self.players:
            return

        await message.delete()
        if message.author in self.has_answered:
            await self.ctx.send('You have already answered!')
            return
        else:
            self.has_answered.add(message.author)
            if message.content == self.current_answer:
                await self.ctx.send('Correct answer from {}'.format(message.author.display_name))
                await self.ctx.send('Previous source: {}'.format(self.previous_source))
                await self.new_question()
                self.players[message.author] += 1
            else:
                await message.author.send('Wrong!')


class MCQ_Game_Controller(Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def get_random_problem(self, ctx):
        qid = random.randint(1, number_of_questions)
        cursor.execute('SELECT * FROM problems WHERE idproblem = {}'.format(qid))
        problem = cursor.fetchone()
        m = await ctx.send(problem[1])  # problem statement
        await m.delete()
        if not problem[2] == '':
            await ctx.send('Extra links: \n{}'.format(problem[2]))  # extra attachments

    @commands.command()
    @commands.is_owner()
    async def new_game(self, ctx, questions: int = 10):
        if ctx.channel.id in games:
            await ctx.send('Game already running in this channel')
            return
        else:
            await ctx.send('New game starting in 1 minute. ')
            games[ctx.channel.id] = Game(ctx, questions)

    @commands.command()
    async def join_game(self, ctx):
        chan = ctx.channel.id
        if chan in games and games[chan].is_accepting_owners:
            games[chan].players = 0
        else:
            await ctx.send('No game in this channel!')

    @Cog.listener()
    async def on_message(self, message):
        if message.channel.id in games:
            games[message.channel.id].process(message)
        else:
            await message.channel.send('No game in this channel!')


def setup(bot):
    bot.add_cog(MCQ_Game_Controller(bot))
