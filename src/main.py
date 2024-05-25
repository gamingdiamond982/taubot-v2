#!/usr/bin/env python3
import asyncio
import time
import sys
import json
from backend import Backend, BackendError, Account
from typing import Callable
import datetime
import logging
import aiohttp
import re

from typing import Union

from discord.ext import tasks, commands
from discord import app_commands
from discord import Webhook

import discord


discord_id_regex = re.compile('\A<@!?\d*>\Z') # a regex that matches a discord id
id_extractor = re.compile('[<@!>]*')


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

discord_logger = logging.getLogger('discord')
discord_logger.setLevel(logging.DEBUG)
backend_logger = logging.getLogger('backend')
backend_logger.setLevel(logging.DEBUG)

stream_handler = logging.StreamHandler()

formatter = logging.Formatter('[%(asctime)s] [%(name)s] [%(levelname)s] : %(message)s')
stream_handler.setLevel(logging.INFO)
stream_handler.setFormatter(formatter)

discord_logger.addHandler(stream_handler)
backend_logger.addHandler(stream_handler)
logger.addHandler(stream_handler)


class WebhookHandler(logging.Handler):
	def __init__(self, webhook_url, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self._webhook_url = webhook_url

	async def send(self, *args, **kwargs):
		async with aiohttp.ClientSession() as session:
			wh = Webhook.from_url(self._webhook_url, session=session)
			await wh.send(*args, **kwargs)

	def emit(self, record: logging.LogRecord):
		embed = discord.Embed(colour=discord.Colour.blue())
		embed.add_field(name=record.name, value=record.message, inline=False)
		asyncio.get_event_loop().create_task(self.send(embed=embed))






# discord rate limits global command updates so for testing purposes I'm only updating the test server I've created
test_guild = discord.Object(id=1236137485554155612) # Change to None for deployment 

intents = discord.Intents.default()
intents.message_content = True


login_map: dict[int, Account] = {}



tick_time = datetime.time(hour=0, minute=0) # tick at midnight UTC, might update this to twice a day if I feel like it or even once an hour, we'll see how I feel

backend = None # Stop any fucky undefined errors



def create_embed(title, message, colour=None):
	colour = colour if colour else discord.Colour.blue()
	embed = discord.Embed(colour=colour)
	embed.add_field(name=title, value=message)
	return embed
	


@tasks.loop(time=tick_time)
async def tick():
	backend.tick()




bot = commands.Bot(intents=intents, command_prefix="!", help_command=None)

@bot.event
async def on_ready():
	backend.tick()
	tick.start()
	sync = await bot.tree.sync(guild=test_guild)
	print(f'Synced {len(sync)} command(s)')
	print("Successfully started bot")


@bot.tree.command(name="ping", description="ping the bot to check if it's online", guild=test_guild)
async def ping(interaction: discord.Interaction):
	await interaction.response.send_message(f'Pong!')

@bot.tree.command(name="create_economy", description="Creates a new economy", guild=test_guild)
@app_commands.describe(economy_name="The name of the economy")
@app_commands.describe(currency_unit="The unit of currency to be used in the economy")
async def create_economy(interaction: discord.Interaction, economy_name: str, currency_unit: str):
	try:
		backend.create_economy(interaction.user.id, economy_name, currency_unit)
		await interaction.response.send_message(embed=create_embed('create-economy', 'Successfully created a new economy'), ephemeral=True)
	except Exception as e:
		await interaction.response.send_message(embed=create_embed('create_economy', f'Could not create a new economy : {e}', colour=discord.Colour.red()), ephemeral=True)

@bot.tree.command(name="list_economies", description="lists all of the currently registered economies", guild=test_guild)
async def list_economies(interaction: discord.Interaction):
	economies = backend.get_economies()
	names = '\n'.join([i.currency_name for i in economies])
	units = '\n'.join([i.currency_unit for i in economies])
	num_guilds = '\n'.join([str(len(i.guilds)) for i in economies])
	embed = discord.Embed(colour=discord.Colour.blue())
	embed.add_field(name='economy name', value=names, inline=True)
	embed.add_field(name='currency unit', value=units, inline=True)
	embed.add_field(name='guilds present', value=num_guilds, inline=True)
	await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name='join_economy', description="registers this guild as a member of a named economy", guild=test_guild)
@app_commands.describe(economy_name="The name of the economy you want to join")
async def join_economy(interaction: discord.Interaction, economy_name: str):
	economy = backend.get_economy_by_name(economy_name)
	if economy is None:
		await interaction.response.send_message(embed=create_embed('join_economy', 'That economy could not be found, try creating it with /create_economy', discord.Colour.red()), ephemeral=True)
		return

	backend.register_guild(interaction.user.id, interaction.guild.id, economy)
	await interaction.response.send_message(embed=create_embed('join_economy', f'Successfully joined economy: {economy_name}'), ephemeral=True)

@bot.tree.command(name='delete_economy', description="Deletes an economy", guild=test_guild)
@app_commands.describe(economy_name='The name of the economy')
async def delete_economy(interaction: discord.Interaction, economy_name: str):
	economy = backend.get_economy_by_name(economy_name)
	if economy is None:
		await interaction.response.send_message(embed=create_embed('delete_economy', 'That economy could not be found double check the name you passed in', discord.Colour.red()), ephemeral=True)
		return

	try:
		backend.delete_economy(interaction.user.id, economy)
		await interaction.response.send_message(embed=create_embed('delete_economy', 'Economy was successfully deleted'), ephemeral=True)
	except Exception as e:
		await interaction.response.send_message(embed=create_embed('delete_economy', 'The economy could not be deleted: {e}', discord.Colour.red()), ephemeral=True)

@bot.tree.command(name='open_account', description="opens a user account in this guild's economy", guild=test_guild)
async def create_account(interaction: discord.Interaction):
	economy = backend.get_guild_economy(interaction.guild.id)
	try:
		backend.create_account(interaction.user.id, interaction.user.id, economy)
		await interaction.response.send_message(embed=create_embed('open_account', 'Your account was opened succesfully'), ephemeral=True)
	except BackendError as e:
		await interaction.response.send_message(embed=create_embed('open_account', f'The account could not be opened: {e}', discord.Colour.red()), ephemeral=True)

@bot.tree.command(name='login', description="login to an account that is not your's in order to act as your behalf", guild=test_guild)
@app_commands.describe(account_name="The account to login as")
async def login(interaction: discord.Interaction, account_name: str):
	account_name = account_name.strip()
	economy = backend.get_guild_economy(interaction.guild.id)
	if discord_id_regex.match(account_name):
		account = backend.get_user_account(int(id_extractor.sub('', account_name)), economy)
	else:
		account = backend.get_account_by_name(account_name, economy)

	if account is None:
		await interaction.response.send_message(embed=create_embed('login', f'We could not find any account under the name : {account_name}', discord.Colour.orange(), ephemeral=True)



def setup_webhook(logger, webhook_url, level):
	wh = WebhookHandler(webhook_url)
	wh.setLevel(level)
	logger.addHandler(wh)







def load_config():
	if len(sys.argv) > 2:
		print('Usage: main.py config_path')
		sys.exit(1)

	path = 'config.json' if len(sys.argv) != 2 else sys.argv[1]
	try:
		with open(path) as file:
			return json.load(file)
	except:
		return {}




if __name__ == '__main__':
	config = load_config()
	db_path = config.get('database_uri')
	db_path = db_path if db_path else 'sqlite:///database.db'
	backend = Backend(db_path)

	token = config.get('discord_token')
	if not token:
		logger.log(logging.CRITICAL, "Discord token not found in the config file")
		sys.exit(1)

	public_webhook_url = config.get('public_webhook_url')
	private_webhook_url = config.get('private_webhook_url')

	if public_webhook_url:
		setup_webhook(backend_logger, public_webhook_url, 52)
	
	if private_webhook_url:
		setup_webhook(backend_logger, private_webhook_url, 51)
	
		
	bot.run(token, log_handler=None)

	

	
	

	













