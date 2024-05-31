#!/usr/bin/env python3
import asyncio
import time
import sys
import json
from backend import Backend, BackendError, Account, Permissions, AccountType, TransactionType, TaxType
from typing import Callable
import datetime
import logging
import aiohttp
import re

from enum import Enum
from typing import Union

from discord.ext import tasks, commands
from discord import app_commands
from discord import Webhook

import discord


syncing = False

discord_id_regex = re.compile('\A<@!?\d*>\Z') # a regex that matches a discord id

id_extractor = re.compile('[<@!>]*')

currency_regex = re.compile('^[0-9]*([\.,][0-9]{1,2}0*)?$')



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
test_guild = None # discord.Object(id=1236137485554155612) # Change to None for deployment 

intents = discord.Intents.default()
intents.message_content = True


login_map: dict[int, Account] = {}




tick_time = datetime.time(hour=0, minute=0) # tick at midnight UTC, might update this to twice a day if I feel like it or even once an hour, we'll see how I feel

backend = None # Stop any fucky undefined errors


def get_account(member):
	economy = backend.get_guild_economy(member.guild.id)
	if economy is None:
		return None

	acc = login_map.get(member.id)
	if acc is not None and acc.economy_id != economy.economy_id:
		acc = None

	if acc is None:
		acc = backend.get_user_account(member.id, economy)
	
	return acc



def create_embed(title, message, colour=None):
	colour = colour if colour else discord.Colour.blue()
	embed = discord.Embed(colour=colour)
	embed.add_field(name=title, value=message)
	return embed
	


def get_account_from_name(name, economy):
	if name is None:
		return None
	name = name.strip()
	if discord_id_regex.match(name):
		account = backend.get_user_account(int(id_extractor.sub('', name)), economy)
	else:
		account = backend.get_account_by_name(name, economy)

	return account


class ParseException(Exception):
	pass

def parse_amount(amount: str) -> int:
	if not currency_regex.match(amount):
		raise ParseException("Invalid currency value, please ensure you do not have more than two decimal places of precision")
	parts = amount.split('.')
	if len(parts) == 1:
		return int(parts[0]) * 100
	elif len(parts) == 2:
		part = parts[1]
		part = part.rstrip('0')
		part = part.ljust(2, '0')
		return (int(parts[0])*100) + int(part)
	else:
		raise ParseException("Invalid currency value")
	




bot = commands.Bot(intents=intents, command_prefix="!", help_command=None)


@tasks.loop(time=tick_time)
async def tick():
	await backend.tick(bot)



@bot.event
async def on_ready():
	await backend.tick(bot)
	tick.start()
	if syncing:
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
		backend.create_economy(interaction.user, economy_name, currency_unit)
		await interaction.response.send_message(embed=create_embed('create-economy', 'Successfully created a new economy'), ephemeral=True)
	except BackendError as e:
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

	backend.register_guild(interaction.user, interaction.guild.id, economy)
	await interaction.response.send_message(embed=create_embed('join_economy', f'Successfully joined economy: {economy_name}'), ephemeral=True)

@bot.tree.command(name='delete_economy', description="Deletes an economy", guild=test_guild)
@app_commands.describe(economy_name='The name of the economy')
async def delete_economy(interaction: discord.Interaction, economy_name: str):
	economy = backend.get_economy_by_name(economy_name)
	if economy is None:
		await interaction.response.send_message(embed=create_embed('delete_economy', 'That economy could not be found double check the name you passed in', discord.Colour.red()), ephemeral=True)
		return

	try:
		backend.delete_economy(interaction.user, economy)
		await interaction.response.send_message(embed=create_embed('delete_economy', 'Economy was successfully deleted'), ephemeral=True)
	except BackendError as e:
		await interaction.response.send_message(embed=create_embed('delete_economy', 'The economy could not be deleted: {e}', discord.Colour.red()), ephemeral=True)

@bot.tree.command(name='open_account', description="opens a user account in this guild's economy", guild=test_guild)
async def create_account(interaction: discord.Interaction):
	economy = backend.get_guild_economy(interaction.guild.id)
	if economy is None:
		await interaction.response.send_message(embed=create_embed('open_account', 'This guild is not registered to an economy so an account cannot be opened here', discord.Colour.orange()), ephemeral=True)
		return
	try:
		backend.create_account(interaction.user, interaction.user.id, economy)
		await interaction.response.send_message(embed=create_embed('open_account', 'Your account was opened succesfully'), ephemeral=True)
	except BackendError as e:
		await interaction.response.send_message(embed=create_embed('open_account', f'The account could not be opened: {e}', discord.Colour.red()), ephemeral=True)




@bot.tree.command(name='login', description="login to an account that is not your's in order to act as your behalf", guild=test_guild)
@app_commands.describe(account_name="The account to login as")
async def login(interaction: discord.Interaction, account_name: str):
	economy = backend.get_guild_economy(interaction.guild.id)
	account = get_account_from_name(account_name, economy)
	if account is None:
		await interaction.response.send_message(embed=create_embed('login', f'We could not find any account under the name : {account_name}', discord.Colour.orange()), ephemeral=True)
		return

	if not backend.has_permission(interaction.user, Permissions.LOGIN_AS_ACCOUNT, account=account, economy=economy):
		await interaction.response.send_message(embed=create_embed('login', f'You do not have permission to login as {account.account_name}', discord.Colour.red()), ephemeral=True)
		return

	login_map[interaction.user.id] = account
	await interaction.response.send_message(embed=create_embed('login', f'You have now logged in as {account.account_name}'), ephemeral=True)

@bot.tree.command(name='whoami', description="tells you who you are logged in as", guild=test_guild)
async def whoami(interaction: discord.Interaction):
	me = get_account(interaction.user)
	if me is None:
		await interaction.response.send_message(embed=create_embed("whoami", "You do not have an account in this economy"), ephemeral=True)
		return

	await interaction.response.send_message(embed=create_embed("whoami", f"You are acting as : {me.account_name}"), ephemeral=True)



		
@bot.tree.command(name='open_special_account', guild=test_guild)
@app_commands.describe(owner="The owner of the new account")
@app_commands.describe(account_name="The name of the account to open")
@app_commands.describe(account_type="The type of account to open")
async def open_special_account(interaction: discord.Interaction, owner: discord.Member|None, account_name: str, account_type: AccountType):
	economy = backend.get_guild_economy(interaction.guild.id)
	if economy is None:
		await interaction.response.send_message(embed=create_embed('open special account', 'This guild is not registered to an economy, therefore an account cannot be opened here', discord.Colour.red()), ephemeral=True)
		return
	try:
		backend.create_account(interaction.user, owner.id if owner is not None else None, economy, name=account_name, account_type = account_type)
		await interaction.response.send_message(embed=create_embed('open special account', 'Account opened successfully'), ephemeral=True)
	except BackendError as e:
		await interaction.response.send_message(embed=create_embed('open special account', f'Could not open account due to : {e}', discord.Colour.red()), ephemeral=True)


@bot.tree.command(name="close_account", guild=test_guild)
@app_commands.describe(account_name="The name of the account you want to close")
async def close_account(interaction: discord.Interaction, account_name: str|None):
	economy = backend.get_guild_economy(interaction.guild.id)
	if account_name is None:
		account = get_account(interaction.user)
	else:
		account = get_account_from_name(account_name, economy)

	if account is None:
		await interaction.response.send_message(embed=create_embed("close account", f'could not find that account', discord.Colour.red()), ephemeral=True)
		return

	try:
		backend.delete_account(interaction.user, account)
		await interaction.response.send_message(embed=create_embed("close account", "Successfully closed account"), ephemeral=True)
	except BackendError as e:
		await interaction.response.send_message(embed=create_embed("close account", f'Could not close account due to {e}', discord.Colour.red()), ephemeral=True)


@bot.tree.command(name='balance', guild=test_guild)
async def get_balance(interaction: discord.Interaction):
	economy = backend.get_guild_economy(interaction.guild.id)
	if economy is None:
		await interaction.response.send_message(embed=create_embed('balance', 'This guild is not registered to an economy', discord.Colour.red()), ephemeral=True)
		return
	account = get_account(interaction.user)
	if account is None:
		await interaction.response.send_message(embed=create_embed('balance', 'You do not have an account in this economy', discord.Colour.red()), ephemeral=True)
		return

	if backend.has_permission(interaction.user, Permissions.VIEW_BALANCE, account=account, economy=economy):
		await interaction.response.send_message(embed=create_embed('balance', f'The balance on {account.account_name} is : {account.balance//100}.{account.balance%100:02}'), ephemeral=True)
	else:
		await interaction.response.send_message(embed=create_embed('balance', f'You do not have permission to view the balance of {account.account_name}'), ephemeral=True)


@bot.tree.command(name='transfer', guild=test_guild)
@app_commands.describe(amount="The amount to transfer")
@app_commands.describe(to_account="The account to transfer the funds too")
@app_commands.describe(transaction_type="The type of transfer that is being performed")
async def transfer_funds(interaction: discord.Interaction, amount: str, to_account: str, transaction_type: TransactionType=TransactionType.PERSONAL):
	economy = backend.get_guild_economy(interaction.guild.id)
	if economy is None:
		await interaction.response.send_message(embed=create_embed('transfer', 'this guild is not registered to an economy', discord.colour.red()), ephemeral=true)

	to_account = get_account_from_name(to_account, economy)
	from_account = get_account(interaction.user)
	if from_account is None:
		await interaction.response.send_message(embed=create_embed('transfer', 'you do not have an account to transfer from', discord.colour.red()), ephemeral=true)
		return

	if to_account is None:
		await interaction.response.send_message(embed=create_embed('transfer', 'the account you tried to transfer too does not exist', discord.colour.red()), ephemeral=true)
		return
	

	try:
		backend.perform_transaction(interaction.user, from_account, to_account, parse_amount(amount), transaction_type)
		await interaction.response.send_message(embed=create_embed('transfer', 'Successfully performed transaction'), ephemeral=True)
	except (BackendError, ParseException) as e: 
		await interaction.response.send_message(embed=create_embed('transfer', f'Failed to perform transaction due to : {e}', discord.Colour.red()), ephemeral=True)


@bot.tree.command(name="create_recurring_transfer", guild=test_guild)
@app_commands.describe(amount="The amount to transfer every interval")
@app_commands.describe(to_account="The account you want to transfer too")
@app_commands.describe(payment_interval="How often you want to perform the transaction in days")
@app_commands.describe(number_of_payments="The number of payments you want to make")
@app_commands.describe(transaction_type="The type of transfer that is being performed")
async def create_recurring_transfer(interaction: discord.Interaction, amount: str, to_account: str, payment_interval: int, number_of_payments: int|None, transaction_type:TransactionType=TransactionType.PERSONAL):
	economy = backend.get_guild_economy(interaction.guild.id)
	if economy is none:
		await interaction.response.send_message(embed=create_embed('transfer', 'this guild is not registered to an economy', discord.colour.red()), ephemeral=true)

	to_account = get_account_from_name(to_account, economy)
	from_account = get_account(interaction.user)
	if from_account is none:
		await interaction.response.send_message(embed=create_embed('transfer', 'you do not have an account to transfer from', discord.colour.red()), ephemeral=true)
		return

	if to_account is none:
		await interaction.response.send_message(embed=create_embed('transfer', 'the account you tried to transfer too does not exist', discord.colour.red()), ephemeral=true)
		return

	try:
		backend.create_recurring_transfer(interaction.user, from_account, to_account, parse_amount(amount), payment_interval, number_of_payments, transaction_type)
		await interaction.response.send_message(embed=create_embed('create recurring transfer', 'Successfully created a recurring transfer'), ephemeral=True)
	except (BackendError, ParseException) as e:
		await interaction.response.send_message(embed=create_embed('create recurring transfer', f"Failed to create a recurring transfer due to: {e}", discord.colour.red()), ephemeral=True)
	


@bot.tree.command(name='view_permissions', guild=test_guild)
@app_commands.describe(user='The user you want to view the permissions of')
async def view_permissions(interaction: discord.Interaction, user: discord.Member|discord.Role):
	economy = backend.get_guild_economy(interaction.guild.id)
	permissions = backend.get_permissions(user, economy)
	names = '\n'.join([str(permission.permission) for permission in permissions])
	accounts = '\n'.join([perm.account.account_name if perm.account else "null" for perm in permissions])
	alloweds = '\n'.join([str(permission.allowed) for permission in permissions])
	embed = discord.Embed()
	embed.add_field(name="permission", value=names, inline=True)
	embed.add_field(name="account", value=accounts, inline=True)
	embed.add_field(name="allowed", value=alloweds, inline=True)
	await interaction.response.send_message(embed=embed, ephemeral=True)




class PermissionState(Enum):
	DISALLOWED = 0
	ALLOWED = 1
	DEFAULT = 2




@bot.tree.command(name="update_permission", guild=test_guild)
@app_commands.describe(affects = "What you want to update the permissions for be it a user or role")
@app_commands.describe(permission="The permission to update")
@app_commands.describe(account = "The account the permission should apply too")
@app_commands.describe(state="The state you want to update the permission too")
async def update_permissions(interaction: discord.Interaction, affects: discord.Member | discord.Role, permission: Permissions, state:PermissionState, account: str|None):
	economy = backend.get_guild_economy(interaction.guild.id)
	if account is not None:
		account = get_account_from_name(account, economy)
		if account is None:
			await interaction.response.send_message(embed=create_embed('update permissions', "That account could not be found", discord.Colour.red()), ephemeral=True)
			return
	try:
		if state == PermissionState.DEFAULT:
			backend.reset_permission(interaction.user, affects.id, permission, account, economy=economy)
		else:
			allowed = bool(state.value)
			backend.change_permissions(interaction.user, affects.id, permission, account, economy=economy, allowed=allowed)
		
		await interaction.response.send_message(embed=create_embed('update_permissions', 'successfully updated permissions'), ephemeral=True)
	except BackendError as e:
		await interaction.response.send_message(embed=create_embed('update permissions', f'could not update permissions due to : {e}', discord.Colour.red()), ephemeral=True)
			


@bot.tree.command(name="print_money", guild=test_guild)
@app_commands.describe(to_account="The account you want to give money too")
@app_commands.describe(amount="The amount you want to print")
async def print_money(interaction: discord.Interaction, to_account: str, amount: str):
	economy = backend.get_guild_economy(interaction.guild.id)
	if economy is None:
		await interaction.response.send_message(embed=create_embed('print money', 'This guild is not registered to an economy.', discord.Colour.red()), ephemeral=True)
		return

	to_account = get_account_from_name(to_account, economy)
	if to_account is None:
		await interaction.response.send_message(embed=create_embed('print money', 'That account could not be found.', discord.Colour.red()), ephemeral=True)
		return

	try:
		backend.print_money(interaction.user, to_account, parse_amount(amount))
		await interaction.response.send_message(embed=create_embed('print money', 'Successfully printed money'), ephemeral=True)
	except (BackendError, ParseException) as e:
		await interaction.response.send_message(embed=create_embed('print money', f'Failed to print money due to : {e}', discord.Colour.red()), ephemeral=True)


@bot.tree.command(name="remove_funds", guild=test_guild)
@app_commands.describe(from_account="The account you want to remove funds from")
@app_commands.describe(amount="The amount you want to remove")
async def remove_funds(interaction: discord.Interaction, from_account: str, amount: str):
	economy = backend.get_guild_economy(interaction.guild.id)
	if economy is None:
		await interaction.response.send_message(embed=create_embed('remove funds', 'This guild is not registered to an economy.', discord.Colour.red()), ephemeral=True)
		return

	from_account = get_account_from_name(from_account, economy)

	if from_account is None:
		await interaction.response.send_message(embed=create_embed('remove funds', 'That account could not be found.', discord.Colour.red()), ephemeral=True)
		return

	try:
		backend.remove_funds(interaction.user, from_account, parse_amount(amount))
		await interaction.response.send_message(embed=create_embed('remove funds', 'Successfully removed funds'), ephemeral=True)
	except (BackendError, ParseException) as e:
		await interaction.response.send_message(embed=create_embed('remove funds', f'Could not remove funds due to : {e}', discord.Colour.red()), ephemeral=True)


@bot.tree.command(name="create_tax_bracket", guild=test_guild)
@app_commands.describe(tax_name="The name of the tax bracket you want to create")
@app_commands.describe(affected_type="The type of account that is affected by your tax")
@app_commands.describe(tax_type="The type of tax you wish to create")
@app_commands.describe(bracket_start="The starting point for the tax bracket")
@app_commands.describe(bracket_end = "The ending point for the tax bracket")
@app_commands.describe(rate="The % of the income between the brackets that you wish to tax")
@app_commands.describe(to_account="The account you wish to send the revenue from taxation too")
async def create_tax_bracket(interaction: discord.Interaction, tax_name: str,  affected_type: AccountType, tax_type: TaxType, bracket_start: str, bracket_end: str, rate: int, to_account: str):
	economy = backend.get_guild_economy(interaction.guild.id)
	if economy is None:
		await interaction.response.send_message(embed=create_embed('create tax bracket', 'This guild is not registered to an economy.', discord.Colour.red()), ephemeral=True)
		return

	to_account = get_account_from_name(to_account, economy)

	if to_account is None:
		await interaction.response.send_message(embed=create_embed('create tax bracket', 'The destination account could not be found in this economy.', discord.Colour.red()), ephemeral=True)
		return

	try:
		backend.create_tax_bracket(interaction.user, tax_name, affected_type, tax_type, parse_amount(bracket_start), parse_amount(bracket_end), rate, to_account)
		await interaction.response.send_message(embed=create_embed("create tax bracket", f'Successfully created a tax bracket'), ephemeral=True)
	except (BackendError, ParseException) as e:
		await interaction.response.send_message(embed=create_embed('create tax bracket', f'could not create tax bracket due to : {e}', discord.Colour.red()), ephemeral=True)



@bot.tree.command(name="delete_tax_bracket", guild=test_guild)
@app_commands.describe(tax_name="The name of the tax bracket you want to delete")
async def delete_tax_bracket(interaction: discord.Interaction, tax_name: str):
	economy = backend.get_guild_economy(interaction.guild.id)
	if economy is None:
		await interaction.response.send_message(embed=create_embed('delete tax bracket', 'This guild is not registered to an economy.', discord.Colour.red()), ephemeral=True)
		return
	try:
		backend.delete_tax_bracket(interaction.user, tax_name, economy)
		await interaction.response.send_message(embed=create_embed("delete tax bracket", "Tax bracket deleted successfully"), ephemeral=True)
	except BackendError as e:
		await interaction.response.send_message(embed=create_embed('delete tax bracket', f'could not remove tax bracket due to : {e}', discord.Colour.red()), ephemeral=True)


@bot.tree.command(name="perform_tax", guild=test_guild)
async def perform_tax(interaction: discord.Interaction):

	economy = backend.get_guild_economy(interaction.guild.id)
	if economy is None:
		await interaction.response.send_message(embed=create_embed('perform tax', 'This guild is not registered to an economy.', discord.Colour.red()), ephemeral=True)
		return
	try:
		backend.perform_tax(interaction.user, economy)
		await interaction.response.send_message(embed=create_embed('perform tax', 'Tax performed succesfully'), ephemeral=True)
	except BackendError as e:
		await interaction.response.send_message(embed=create_embed('perform tax', f'could perform taxes due to : {e} \n note: no changes should have been made to any balances', discord.Colour.red()), ephemeral=True)
		



def setup_webhook(logger, webhook_url, level):
	wh = WebhookHandler(webhook_url)
	wh.setLevel(level)
	logger.addHandler(wh)







def load_config():
	global syncing
	if len(sys.argv) > 3:
		print('Usage: main.py config_path -[S]')
		sys.exit(1)

	path = 'config.json' if len(sys.argv) < 2 else sys.argv[1]
	
	if len(sys.argv) == 3:
		if sys.argv[2] != "-S":
			print('Usage: main.py config_path -[S]')
			sys.exit(1)
		syncing = True

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

	

	
	

	













