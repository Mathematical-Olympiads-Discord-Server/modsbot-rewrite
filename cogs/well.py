from datetime import datetime, timezone, time, timedelta

import schedule
from discord.ext import commands

from cogs import config as cfg

Cog = commands.Cog


WELL_RANGE = 'A2:E'

def is_well_manager(ctx):
	return cfg.Config.config['well_manager_role'] in [x.id for x in ctx.author.roles]

class Well(Cog):

	def __init__(self, bot: commands.Bot): 
		
		self.bot = bot
		
		cursor = cfg.db.cursor()
		cursor.execute(f'''INSERT OR IGNORE INTO settings (setting, value) VALUES
            ('well_time', '00:00')
            ''')					# Treated as UTC
		cfg.db.commit()
		cursor.execute("SELECT value FROM settings WHERE setting = 'well_time'")
		self.time = cursor.fetchone()[0].split(':')
		self.hour = int(self.time[0])
		self.minute = int(self.time[1])
		self.time = timedelta(hours = self.hour, minutes = self.minute)
		local_time = (self.today() + self.time).astimezone()
		self.schedule = schedule.every().day.at(f'{local_time.hour:02d}:{local_time.minute:02d}'
			).do(self.check).tag('cogs.well')

	def today(self):
		return datetime.combine(datetime.now(timezone.utc).date(), time.min, timezone.utc)

	def check(self):
		self.bot.loop.create_task(self.checkk())

	async def checkk(self):
		
		well = cfg.Config.service.spreadsheets().values().get(spreadsheetId=cfg.Config.config['well_sheet'],
                                                            	range=WELL_RANGE).execute().get('values', [])[::-1]
		today_date = self.today().date()
		remind = False
		person = None
		for i in well:
			if len(i) < 4:
				pass
			elif person != None:
				if person != i[3]:
					remind = True
				else:
					break
			elif datetime.strptime(i[0], '%d-%b-%Y').date() == today_date:
				person = i[3]
				if well[-1][0] == i[0]:
					remind = True
					break
			elif datetime.strptime(i[0], '%d-%b-%Y').date() < today_date:
				break

		if remind:
			await self.bot.get_channel(cfg.Config.config['well_channel']).send(
                        f"Next person goes in the well today! <@&{cfg.Config.config['well_manager_role']}>")

	@commands.command()
	@commands.check(is_well_manager)
	async def well_time(self, ctx, hour: int = None, min: int = 0):
		
		now = datetime.now(timezone.utc)
		today = self.today()
		if hour == None:
			next_period = now + (today + self.time - now) % timedelta(days = 1)
			await ctx.send(f"Next well period ({(next_period-self.time).strftime(r'%b %d')}) starts on <t:{cfg.timestamp(next_period)}>.\n"
							f"Use {cfg.Config.config['prefix']}well_time [hour] [min] to adjust well time.")
		else:
			self.time += timedelta(hours = hour, minutes = min)
			self.hour = int(self.time.total_seconds()) // 3600
			self.minute = int(self.time.total_seconds()) % 3600 // 60
			local_time = (today + self.time).astimezone()
			schedule.cancel_job(self.schedule)
			self.schedule = schedule.every().day.at(f'{local_time.hour:02d}:{local_time.minute:02d}'
				).do(self.check).tag('cogs.well')
			cursor = cfg.db.cursor()
			cursor.execute(f'''UPDATE settings SET value = '{self.hour:02d}:{self.minute:02d}'
				WHERE setting = 'well_time'
				''')
			cfg.db.commit()
			next_period = now + (today + self.time - now) % timedelta(days = 1)
			await ctx.send(f"Next well period ({(next_period-self.time).strftime(r'%b %d')}) starts on <t:{cfg.timestamp(next_period)}>.")

	@commands.command()
	@commands.check(is_well_manager)
	async def reset_well_time(self, ctx):
		await self.well_time(ctx, -self.hour, -self.minute)

	@commands.command()
	@commands.check(is_well_manager)
	async def well_add(self, ctx, days: int, person: int = None):
		
		if days < 1:
			await ctx.reply('Invalid number of days!')
			return
		
		if person == None:
			if ctx.message.reference == None:
				await ctx.reply('Reply to a person or specify their ID!')
				return
			else:
				p = await ctx.channel.fetch_message(ctx.message.reference.message_id)
				person_na = p.author
				person = person_na.id
		else:
			person_na = ctx.guild.get_member(person)
		if person_na == None:
			await ctx.reply("This person can't be found!")
			return
		person_name = f'{person_na.name}#{person_na.discriminator}'
		
		well = cfg.Config.service.spreadsheets().values().get(spreadsheetId=cfg.Config.config['well_sheet'],
                                                            	range=WELL_RANGE).execute().get('values', [])[::-1]
		now = datetime.now(timezone.utc)
		today = self.today()
		current = now - (now - today - self.time) % timedelta(days = 1)
		last = datetime.strptime(well[0][0], '%d-%b-%Y').replace(tzinfo = timezone.utc)
		if last + self.time < current:
			new = current - self.time
		else:
			new = last + timedelta(days = 1)

		append = []
		for i in range(days):
			append.append([(new + timedelta(days = i)).strftime('%d-%b-%Y'), i+1, person_name, str(person), 'Bucket List'])
		cfg.Config.service.spreadsheets().values().append(spreadsheetId=cfg.Config.config['well_sheet'],
			range=WELL_RANGE, valueInputOption='RAW', insertDataOption='INSERT_ROWS',
			body={"range": WELL_RANGE, "majorDimension": 'ROWS', "values": append}).execute()
		await ctx.reply(f"Scheduled <@{person}> for {days} days of well starting {new.strftime(r'%b %d')} (<t:{cfg.timestamp(new + self.time)}>).")


def setup(bot):
    bot.add_cog(Well(bot))
