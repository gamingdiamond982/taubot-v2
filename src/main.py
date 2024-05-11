#!/usr/bin/env python3
import asyncio
import time
import sys
import json
from backend import Backend
from typing import Callable
import datetime

from discord.ext import tasks, commands
from discord import app_commands

import discord

# discord rate limits global command updates so for testing purposes I'm only updating the test server I've created
test_guild = discord.Object(id=1236137485554155612) # Change to None for deployment 

intents = discord.Intents.default()
intents.message_content = True


tick_time = datetime.time(hour=0, minute=0) # tick at midnight UTC, might update this to twice a day if I feel like it or even once an hour, we'll see how I feel

backend = None # Stop any fucky undefined errors




@tasks.loop(time=tick_time)
async def tick():
	print("ticking!")
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
async def hello(interaction: discord.Interaction):
	await interaction.response.send_message(f'Pong!')













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
		print("Discord token not found in the config file")
		sys.exit(1)
		
	bot.run(token)

	

	
	

	













