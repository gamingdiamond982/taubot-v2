#!/usr/bin/env python3
import asyncio
import sys
from utils import load_config, syncing, generate_transaction_csv
from middleman import BackendError, Account, Permissions, AccountType, TransactionType, TaxType, frmt
from middleman import DiscordBackendInterface as Backend
import datetime
import logging
import aiohttp
import re
import textwrap
from enum import Enum

from discord.ext import tasks, commands
from discord import app_commands
from discord import Webhook

import discord
import io
from discord import Colour
import api

red = Colour.red
yellow = Colour.yellow
blue = Colour.blue
orange = Colour.orange
green = Colour.green

init_time = datetime.datetime.now()
syncing = False
use_api = False

private_webhook_url = ""

discord_id_regex = re.compile(r'^<@!?[0-9]*>$')  # a regex that matches a discord id

id_extractor = re.compile(r'[<@!>]*')

currency_regex = re.compile(r'^[0-9]*([.,][0-9]{1,2}0*)?$')

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

discord_logger = logging.getLogger('discord')
discord_logger.setLevel(logging.DEBUG)
backend_logger = logging.getLogger('backend')
backend_logger.setLevel(logging.DEBUG)
api_logger = logging.getLogger('aiohttp.server')
api_logger.setLevel(logging.DEBUG)

stream_handler = logging.StreamHandler()

formatter = logging.Formatter('[%(asctime)s] [%(name)s] [%(levelname)s] : %(message)s')
stream_handler.setLevel(logging.INFO)
stream_handler.setFormatter(formatter)

discord_logger.addHandler(stream_handler)
backend_logger.addHandler(stream_handler)
api_logger.addHandler(stream_handler)
logger.addHandler(stream_handler)

# putting it here for the time being until frontend is refactored
class ConfirmationView(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.event = asyncio.Event()
        self.confirmation = False

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.green)
    async def yes(self, __interaction__, __btn__):
        self.confirmation = True
        self.event.set()

    @discord.ui.button(label="No", style=discord.ButtonStyle.red)
    async def no(self, __interaction__, __btn__):
        self.event.set()

    async def get_confirmation(self):
        await self.event.wait()
        return self.confirmation

class WebhookHandler(logging.Handler):
    def __init__(self, webhook_url, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._webhook_url = webhook_url

    async def send(self, *args, **kwargs):
        async with aiohttp.ClientSession() as session:
            wh = Webhook.from_url(self._webhook_url, session=session)
            await wh.send(*args, **kwargs)

    def emit(self, record: logging.LogRecord):
        print(record.levelno)
        embed = discord.Embed(colour=blue())
        embed.add_field(name=record.name, value=record.message, inline=False)
        asyncio.get_event_loop().create_task(self.send(embed=embed))

class LevelFilter(logging.Filter):
    def __init__(self, level):
        self.level = level

    def filter(self, record):
        return record.levelno == self.level

# discord rate limits global command updates so for testing purposes I'm only updating the test server I've created
test_guild = None # discord.Object(id=1236137485554155612)  # Change to None for deployment

intents = discord.Intents.default()
intents.message_content = True

login_map: dict[int, Account] = {}

tick_time = datetime.time(hour=0,
                          minute=0)  # tick at midnight UTC, might update this to twice a day if I feel like it or even once an hour, we'll see how I feel

backend: Backend = None  # pyright: ignore
# Stop any fucky undefined errors


def get_account(member):
    """
    :param member: A discord user
    :return: the discord users tau account
    """

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
    """
    :param title: title for the embed
    :param message: message for embed
    :param colour: Colour for embed
    :return:
    """

    colour = colour if colour else discord.Colour.blue()
    embed = discord.Embed(colour=colour)
    embed.add_field(name=title, value=message)
    return embed


def get_account_from_name(name, economy):
    """
    :param name: Discord username (typically a string)
    :param economy: The specific economy to look at
    :return: the specific tau account
    """

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
    """
    :param amount: the amount of tau for a specific transaction
    :return: an integer value
    """

    if not currency_regex.match(amount):
        raise ParseException(
            "Invalid currency value, please ensure you do not have more than two decimal places of precision")
    parts = amount.split('.')
    if len(parts) == 1:
        return int(parts[0]) * 100
    elif len(parts) == 2:
        part = parts[1]
        part = part.rstrip('0')
        part = part.ljust(2, '0')
        return (int(parts[0]) * 100) + int(part)
    else:
        raise ParseException("Invalid currency value")


class CommandCheck(discord.app_commands.CommandTree):
    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.type == discord.InteractionType.application_command and not interaction.guild:
            await interaction.response.send_message(embed=create_embed("Running commands in DMs is not supported", "This restriction has been placed for safety reasons until further notice.", discord.Colour.red()))
            return False
        return True

bot = commands.Bot(intents=intents, help_command=None, command_prefix='!', tree_cls=CommandCheck)

@tasks.loop(time=tick_time)
async def tick():
    await backend.tick()
    await dump(True)

async def dump(automatic=False):
    if backend is not None:
        conn = backend.engine.raw_connection()
        with io.StringIO() as buf, io.StringIO() as buf2, io.StringIO() as buf3:
            for line in conn.iterdump():
                buf.write("%s\n" % line)
            buf.seek(0)

            dump_f = discord.File(buf, filename="dump.sql")
            accounts_f = discord.File(backend.dump_accounts_csv(buf2), filename="accounts.csv")
            trans_f = discord.File(backend.dump_transactions_csv(buf3), filename="transactions.csv")

            if private_webhook_url and len(private_webhook_url) > 0:
                timestamp = int(datetime.datetime.now().timestamp())
                await Webhook.from_url(private_webhook_url, client=bot).send(
                    content=f"Database dump, triggered {'manually' if not automatic else 'automatically'} at <t:{timestamp}>",
                    files=[dump_f, accounts_f, trans_f]
                )
                
@bot.event
async def on_ready():
    tick.start()
    if syncing:
        sync = await bot.tree.sync(guild=test_guild)
        print(f'Synced {len(sync)} command(s)')
    if use_api:
        print("Starting the API")
        api.backend = backend
        api_runner = api.web.AppRunner(api.init_app())
        await api_runner.setup()
        site = api.web.TCPSite(api_runner, 'localhost', 8080)
        await site.start()
        print("Successfully started the api")
    print("Successfully started bot")

@bot.tree.command(name="ping", description="ping the bot to check if it's online", guild=test_guild)
@app_commands.describe(isalive="Give a simpler response to only check if we can talk to discord, useful if DB is really broken")
async def ping(interaction: discord.Interaction, isalive: bool = False):
    if isalive:
        await interaction.response.send_message(f'Pong!')
        return

    now = datetime.datetime.now(datetime.timezone.utc)
    keys = ["Connected to Discord: ", "Backend Exists: ", "Connected to Database: ", "Ping: ", "Uptime: "]
    values = [True, backend is not None, backend is not None, str(round((now - interaction.created_at).microseconds / 1000)) + 'ms',
              str(datetime.datetime.now() - init_time)]
    good = True
    if backend is not None:
        try:
            con = backend.engine.raw_connection()
            if con is not None:
                values[2] = True
                con.close()
            else:
                good = False
        except:
            values[2] = False
            good = False
    else:
        good = False

    def process(value):
        if type(value) == bool:
            return '🟢' if value else '🔴'  # My vim setup on this laptop isn't rendering these right, but they are the unicode emoji for a green circle and a red circle respectively
        else:
            return value

    colour = green() if good else red()
    embed = discord.Embed(colour=colour)
    keys = '\n'.join([k for k in keys])
    values = '\n'.join([process(v) for v in values])
    embed.add_field(name='All Systems Go: ', value=keys, inline=True)
    embed.add_field(name=process(good), value=values, inline=True)

    # Because I want this to work even if things are really broken I'm not using a responder thingy
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="create_economy", description="Creates a new economy", guild=test_guild)
@app_commands.describe(economy_name="The name of the economy")
@app_commands.describe(currency_unit="The unit of currency to be used in the economy")
async def create_economy(interaction: discord.Interaction, economy_name: str, currency_unit: str):
    responder = backend.get_responder(interaction)
    try:
        backend.create_economy(interaction.user, economy_name, currency_unit)
        await responder(message="Successfully created a new economy")
    except BackendError as e:
        await responder(message=f"Could not create a new economy : {e}", colour=red())


@bot.tree.command(name="list_economies", description="lists all of the currently registered economies",
                  guild=test_guild)
async def list_economies(interaction: discord.Interaction):
    responder = backend.get_responder(interaction)
    economies = backend.get_economies()
    names = '\n'.join([i.currency_name for i in economies])
    units = '\n'.join([i.currency_unit for i in economies])
    num_guilds = '\n'.join([str(len(i.guilds)) for i in economies])
    embed = discord.Embed(colour=blue())
    embed.add_field(name='economy name', value=names, inline=True)
    embed.add_field(name='currency unit', value=units, inline=True)
    embed.add_field(name='guilds present', value=num_guilds, inline=True)
    await responder(embed=embed)


@bot.tree.command(name='join_economy', description="registers this guild as a member of a named economy",
                  guild=test_guild)
@app_commands.describe(economy_name="The name of the economy you want to join")
async def join_economy(interaction: discord.Interaction, economy_name: str):
    responder = backend.get_responder(interaction)
    economy = backend.get_economy_by_name(economy_name)
    if economy is None:
        await responder(message='That economy could not be found, try creating it with `/create_economy`', colour=red())
        return

    try:
        backend.register_guild(interaction.user, interaction.guild.id, economy)
        await responder(message=f'Successfully joined economy: {economy_name}')
    except BackendError as e:
        await responder(message=f"Could not join economy {economy_name}: {e}", colour=red())

@bot.tree.command(name='leave_economy', description="removes this guild's membership from the current economy",
                  guild=test_guild)
async def leave_economy(interaction: discord.Interaction):
    responder = backend.get_responder(interaction)
    economy = backend.get_guild_economy(interaction.guild.id)
    if economy is None:
        await responder(message='This guild is not a member of an economy', colour=red())
        return
    
    try:
        backend.unregister_guild(interaction.user, interaction.guild.id)
        await responder(message=f'Successfully left economy: {economy.currency_name}')
    except BackendError as e:
        await responder(message=f"Could not leave economy {economy.currency_name}: {e}", colour=red())

@bot.tree.command(name='delete_economy', description="Deletes an economy", guild=test_guild)
@app_commands.describe(economy_name='The name of the economy')
async def delete_economy(interaction: discord.Interaction, economy_name: str):
    responder = backend.get_responder(interaction)
    economy = backend.get_economy_by_name(economy_name)
    if economy is None:
        await responder(message='That economy could not be found double check it\'s name.', colour=red())
        return

    try:
        backend.delete_economy(interaction.user, economy)
        await responder(message="Economy was successfully deleted")
    except BackendError as e:
        await responder(message=f"The economy could not be deleted: {e}", colour=red())


@bot.tree.command(name="link", description="Links your mc account with taubot", guild=test_guild)
@app_commands.describe(token="The token generated by running /link on the mc server")
async def link_account(interaction: discord.Interaction, token: str):
    responder = backend.get_responder(interaction)
    try:
        backend.register_mc_token(interaction.user.id, token)
        await responder(message="MC account and discord account successfully linked")
    except BackendError as e:
        await responder(message=f"Could not link your account due to : {e}", colour=red())


@bot.tree.command(name='open_account', description="opens a user account in this guild's economy", guild=test_guild)
async def create_account(interaction: discord.Interaction):
    responder = backend.get_responder(interaction)
    economy = backend.get_guild_economy(interaction.guild.id)
    if economy is None:
        await responder(message='This guild is not registered to an economy so an account could not be opened here',
                        colour=orange())
        return
    try:
        backend.create_account(interaction.user, interaction.user.id, economy)
        await responder(message='Your account was opened successfully')
    except BackendError as e:
        await responder(message=f'The account could not be opened: {e}', colour=red())

@app_commands.describe(new_owner="The new owner of the account.", account_name="The account you wish to transfer your ownership of. Defaults to the current logged in account.")
@bot.tree.command(name='transfer_ownership', description="Transfers your ownership of an account to another user.", guild=test_guild)
async def transfer_ownership(interaction: discord.Interaction, new_owner: discord.Member, account_name: str | None):
    responder = backend.get_responder(interaction)
    economy = backend.get_guild_economy(interaction.guild.id)
    if account_name is None:
        account = get_account(interaction.user)
    else:
        account = get_account_from_name(account_name, economy)

    if account is None:
        await responder(message='Could not find that account', colour=red())
        return

    confirmation = ConfirmationView()
    await responder(message=textwrap.dedent(f"""
        Are you sure you want to transfer the ownership of this account to {new_owner.mention}?
        You will not be able to:
        - login as the account or close it
        - view the account's balance
        - transfer funds from the account, including creating recurring transfers
        - receive updates about the account's balance
        In addition, you will be logged out of the account.
    """), view=confirmation)

    confirmed = await confirmation.get_confirmation()
    if confirmed:
        try:
            backend.transfer_ownership(interaction.user, account, new_owner.id)
        except Exception as e:
            await responder(message=e, colour=red(), edit=True, view=None)
        else:
            user_acc = backend.get_account_from_interaction(interaction)
            if user_acc:
                login_map[interaction.user.id] = user_acc
            await responder(message=f"Transferred account ownership to {new_owner.mention}.", edit=True, view=None)
    else:
        await responder(message=f"Cancelled operation.", edit=True, view=None)

@bot.tree.command(name='login', description="login to an account that is not your's in order to act as your behalf",
                  guild=test_guild)
@app_commands.describe(account_name="The account to login as")
async def login(interaction: discord.Interaction, account_name: str | None):
    responder = backend.get_responder(interaction)
    economy = backend.get_guild_economy(interaction.guild.id)
    account = get_account_from_name(account_name,
                                    economy) if account_name is not None else backend.get_account_from_interaction(
        interaction)

    if account is None:
        await responder(message=f'We could not find any account under the name : {account_name}')
        return

    if not backend.has_permission(interaction.user, Permissions.LOGIN_AS_ACCOUNT, account=account):
        await responder(message=f'You do not have permission to login as {account.account_name}', colour=red())
        return

    login_map[interaction.user.id] = account
    await responder(
        message=f'You have now logged in as {account.account_name}\n To log back into your user account simply run `/login` without any arguments')


@bot.tree.command(name='whoami', description="tells you who you are logged in as", guild=test_guild)
async def whoami(interaction: discord.Interaction):
    me = get_account(interaction.user)
    responder = backend.get_responder(interaction)
    if me is None:
        await responder(message="You do not have an account in this economy")
        return

    await responder(message=f"You are acting as {me.account_name}")


@bot.tree.command(name='open_special_account', guild=test_guild)
@app_commands.describe(owner="The owner of the new account")
@app_commands.describe(account_name="The name of the account to open")
@app_commands.describe(account_type="The type of account to open")
async def open_special_account(interaction: discord.Interaction, owner: discord.Member | discord.Role | None,
                               account_name: str, account_type: AccountType):
    responder = backend.get_responder(interaction)
    economy = backend.get_guild_economy(interaction.guild.id)
    if economy is None:
        await responder(
            message="This guild is not registered to an economy, therefore an account cannot be opened here",
            colour=red())
        return
    try:
        backend.create_account(interaction.user, owner.id if owner is not None else None, economy, name=account_name,
                               account_type=account_type)
        await responder(message="Account opened successfully")
    except BackendError as e:
        await responder(message=f"Could not open account due to : {e}", colour=red())


@bot.tree.command(name="close_account", guild=test_guild)
@app_commands.describe(account_name="The name of the account you want to close")
async def close_account(interaction: discord.Interaction, account_name: str | None):
    responder = backend.get_responder(interaction)
    economy = backend.get_guild_economy(interaction.guild.id)
    if account_name is None:
        account = get_account(interaction.user)
    else:
        account = get_account_from_name(account_name, economy)

    if account is None:
        await responder(message='Could not find that account', colour=red())
        return

    try:
        backend.delete_account(interaction.user, account)
        await responder(message="Successfully closed account")
    except BackendError as e:
        await responder(message=f"Could not close account due to {e}", colour=red())


@bot.tree.command(name='balance', guild=test_guild)
async def get_balance(interaction: discord.Interaction):
    responder = backend.get_responder(interaction)
    economy = backend.get_guild_economy(interaction.guild.id)

    if economy is None:
        await responder(message='This guild is not registered to an economy', colour=red())
        return
    account = get_account(interaction.user)
    if account is None:
        await responder(message='You do not have an account in this economy', colour=red())
        return

    if backend.has_permission(interaction.user, Permissions.VIEW_BALANCE, account=account, economy=economy):
        await responder(message=f'The balance on {account.account_name} is : {account.get_balance()}')
    else:
        await responder(message=f'You do not have permission to view the balance of {account.account_name}')


@bot.tree.command(name='transfer', guild=test_guild)
@app_commands.describe(amount="The amount to transfer")
@app_commands.describe(to_account="The account to transfer the funds too")
@app_commands.describe(transaction_type="The type of transfer that is being performed")
async def transfer_funds(interaction: discord.Interaction, amount: str, to_account: str,
                         transaction_type: TransactionType = TransactionType.PERSONAL):
    responder = backend.get_responder(interaction)
    economy = backend.get_guild_economy(interaction.guild.id)
    if economy is None:
        await responder(message='This guild is not registered to an economy', colour=red())

    to_account = get_account_from_name(to_account, economy)
    from_account = get_account(interaction.user)
    if from_account is None:
        await responder(message='You do not have an account to transfer from', colour=red())
        return

    if to_account is None:
        await responder(message='The account you tried to transfer too does not exist', colour=red())
        return

    try:
        backend.perform_transaction(interaction.user, from_account, to_account, parse_amount(amount), transaction_type)
        await responder('Successfully performed transaction')
    except (BackendError, ParseException) as e:
        await responder(message=f'Failed to perform transaction due to : {e}', colour=red())


@bot.tree.command(name="create_recurring_transfer", guild=test_guild)
@app_commands.describe(amount="The amount to transfer every interval")
@app_commands.describe(to_account="The account you want to transfer too")
@app_commands.describe(payment_interval="How often you want to perform the transaction in days")
@app_commands.describe(number_of_payments="The number of payments you want to make")
@app_commands.describe(transaction_type="The type of transfer that is being performed")
async def create_recurring_transfer(interaction: discord.Interaction, amount: str, to_account: str,
                                    payment_interval: int, number_of_payments: int | None,
                                    transaction_type: TransactionType = TransactionType.PERSONAL):
    responder = backend.get_responder(interaction)
    economy = backend.get_guild_economy(interaction.guild.id)
    if economy is None:
        await interaction.response.send_message(
            embed=create_embed('transfer', 'this guild is not registered to an economy', discord.colour.red()),
            ephemeral=True)

    to_account = get_account_from_name(to_account, economy)
    from_account = get_account(interaction.user)
    if from_account is None:
        await interaction.response.send_message(
            embed=create_embed('transfer', 'you do not have an account to transfer from', discord.colour.red()),
            ephemeral=True)
        return

    if to_account is None:
        await interaction.response.send_message(
            embed=create_embed('transfer', 'the account you tried to transfer too does not exist',
                               discord.colour.red()), ephemeral=True)
        return

    try:
        backend.create_recurring_transfer(interaction.user, from_account, to_account, parse_amount(amount),
                                          payment_interval, number_of_payments, transaction_type)
        await responder('Successfully created a recurring transfer')
    except (BackendError, ParseException) as e:
        await responder(message=f"Failed to create a recurring transfer due to: {e}", colour=red())


@bot.tree.command(name='view_permissions', guild=test_guild)
@app_commands.describe(user='The user you want to view the permissions of')
async def view_permissions(interaction: discord.Interaction, user: discord.Member | discord.Role):
    responder = backend.get_responder(interaction)
    economy = backend.get_guild_economy(interaction.guild.id)
    permissions = backend.get_permissions(user, economy)
    names = '\n'.join([str(permission.permission) for permission in permissions])
    accounts = '\n'.join([perm.account.account_name if perm.account else "null" for perm in permissions])
    alloweds = '\n'.join([str(permission.allowed) for permission in permissions])
    embed = discord.Embed()
    embed.add_field(name="permission", value=names, inline=True)
    embed.add_field(name="account", value=accounts, inline=True)
    embed.add_field(name="allowed", value=alloweds, inline=True)
    await responder(embed=embed)


class PermissionState(Enum):
    DISALLOWED = 0
    ALLOWED = 1
    DEFAULT = 2


@bot.tree.command(name="update_permission", guild=test_guild)
@app_commands.describe(affects="What you want to update the permissions for be it a user or role")
@app_commands.describe(permission="The permission to update")
@app_commands.describe(account="The account the permission should apply too")
@app_commands.describe(state="The state you want to update the permission too")
@app_commands.describe(universal="Whether or not the scope is restricted to this economy")
async def update_permissions(interaction: discord.Interaction, affects: discord.Member | discord.Role,
                             permission: Permissions, state: PermissionState, account: str | None,
                             universal: bool = False):
    economy = backend.get_guild_economy(interaction.guild.id) if not universal else None
    responder = backend.get_responder(interaction)
    if account is not None:
        account = get_account_from_name(account, economy)
        if account is None:
            await responder(message="That account could not be found", colour=red())
            return
    try:
        if state == PermissionState.DEFAULT:
            backend.reset_permission(interaction.user, affects.id, permission, account, economy=economy)
        else:
            allowed = bool(state.value)
            backend.change_permissions(interaction.user, affects.id, permission, account, economy=economy,
                                       allowed=allowed)
        await responder(message='successfully updated permissions')
    except BackendError as e:
        await responder(f'could not update permissions due to : {e}', colour=red())


@bot.tree.command(name="print_money", guild=test_guild)
@app_commands.describe(to_account="The account you want to give money too")
@app_commands.describe(amount="The amount you want to print")
async def print_money(interaction: discord.Interaction, to_account: str, amount: str):
    economy = backend.get_guild_economy(interaction.guild.id)
    responder = backend.get_responder(interaction)

    if economy is None:
        await responder('This guild is not registered to an economy.', colour=red())
        return

    to_account = get_account_from_name(to_account, economy)
    if to_account is None:
        await responder('That account could not be found.', red())
        return

    try:
        backend.print_money(interaction.user, to_account, parse_amount(amount))
        await responder('Successfully printed money')
    except (BackendError, ParseException) as e:
        await responder(f'Failed to print money due to : {e}', red())


@bot.tree.command(name="remove_funds", guild=test_guild)
@app_commands.describe(from_account="The account you want to remove funds from")
@app_commands.describe(amount="The amount you want to remove")
async def remove_funds(interaction: discord.Interaction, from_account: str, amount: str):
    responder = backend.get_responder(interaction)
    economy = backend.get_guild_economy(interaction.guild.id)
    if economy is None:
        await responder(message="This guild is not registered to an economy.", colour=red())
        return

    from_account = get_account_from_name(from_account, economy)

    if from_account is None:
        await responder(message="That account could not be found", colour=red())
        return

    try:
        backend.remove_funds(interaction.user, from_account, parse_amount(amount))
        await responder(message="Successfully removed funds")
    except (BackendError, ParseException) as e:
        await responder(message=f'Could not remove funds due to : {e}', colour=red())


@bot.tree.command(name="create_tax_bracket", guild=test_guild)
@app_commands.describe(tax_name="The name of the tax bracket you want to create")
@app_commands.describe(affected_type="The type of account that is affected by your tax")
@app_commands.describe(tax_type="The type of tax you wish to create")
@app_commands.describe(bracket_start="The starting point for the tax bracket")
@app_commands.describe(bracket_end="The ending point for the tax bracket")
@app_commands.describe(rate="The % of the income between the brackets that you wish to tax")
@app_commands.describe(to_account="The account you wish to send the revenue from taxation too")
async def create_tax_bracket(interaction: discord.Interaction, tax_name: str, affected_type: AccountType,
                             tax_type: TaxType, bracket_start: str, bracket_end: str, rate: int, to_account: str):
    economy = backend.get_guild_economy(interaction.guild.id)
    responder = backend.get_responder(interaction)
    if economy is None:
        await responder(message='This guild is not registered to an economy.', colour=red())
        return

    to_account = get_account_from_name(to_account, economy)

    if to_account is None:
        await responder(message='The destination account could not be found in this economy', colour=red())
        return

    try:
        backend.create_tax_bracket(interaction.user, tax_name, affected_type, tax_type, parse_amount(bracket_start),
                                   parse_amount(bracket_end), rate, to_account)
        await responder(message="Successfully created a tax bracket")
    except (BackendError, ParseException) as e:
        await responder(message=f"Could not create a tax bracket due to : {e}", colour=red())


@bot.tree.command(name="delete_tax_bracket", guild=test_guild)
@app_commands.describe(tax_name="The name of the tax bracket you want to delete")
async def delete_tax_bracket(interaction: discord.Interaction, tax_name: str):
    economy = backend.get_guild_economy(interaction.guild.id)
    responder = backend.get_responder(interaction)
    if economy is None:
        await responder(message='This guild is not registered to an economy', colour=red())
        return
    try:
        backend.delete_tax_bracket(interaction.user, tax_name, economy)
        await responder(message="Tax bracket deleted successfully")
    except BackendError as e:
        await responder(message=f"Could not remove tax bracket due to : {e}", colour=red())


@bot.tree.command(name="perform_tax", guild=test_guild)
async def perform_tax(interaction: discord.Interaction):
    economy = backend.get_guild_economy(interaction.guild.id)
    responder = backend.get_responder(interaction)
    if economy is None:
        await responder(message='This guild is not registered to an economy', colour=red())
        return
    try:
        backend.perform_tax(interaction.user, economy)
        await responder(message='Tax performed succesfully', colour=red())
    except BackendError as e:
        await responder(
            message=f'could not perform taxes due to : {e}\n note: no changes have been made to any balances',
            colour=red())


@bot.tree.command(name='toggle_ephemeral', guild=test_guild)
async def toggle_ephemeral(interaction: discord.Interaction):
    responder = backend.get_responder(interaction)
    backend.toggle_ephemeral(interaction.user)
    await responder("Successfully updated your prefrences")


@bot.tree.command(name='view_transaction_log', guild=test_guild)
@app_commands.describe(
    account="The account you want to view the transaction logs of, leave empty to default to the account your currently logged in as.",
    limit="The number of transactions back you wish too see (note: will not show transactions before this feature was added).",
    as_csv="Whether you wish to view the transaction log as a CSV file.")
async def view_transaction_log(interaction: discord.Interaction, account: str | None, limit: int = 10, as_csv: bool = False):
    economy = backend.get_guild_economy(interaction.guild.id)
    responder = backend.get_responder(interaction)

    if economy is None:
        return await responder(message="This guild is not registered to an economy", colour=red())

    account = get_account_from_name(account, economy)
    account = account if account is not None else get_account(interaction.user)
    try:
        transactions = backend.get_transaction_log(interaction.user, account, limit=limit)
    except BackendError as e:
        return await responder(message=f"{e}")

    if len(transactions) == 0:
        await responder(message='No transactions have been logged yet')
    else:
        if as_csv:
            file = generate_transaction_csv(transactions, currency=economy.currency_unit)
            await responder(message=f'Logged latest `{len(transactions)}` transaction(s).', as_embed=False, file=file)
        else:
            entries = '\n'.join([
                                f'{t.timestamp.strftime("%d/%m/%y %H:%M")} {t.target_account.get_name()} --{frmt(t.amount)}{economy.currency_unit}-> {t.destination_account.get_name()}'
                                for t in transactions])
            await responder(message=entries)

@bot.tree.command(name="subscribe", guild=test_guild)
@app_commands.describe(account="The account you want to get balance update notifications for")
async def subscribe(interaction: discord.Interaction, account: str):
    economy = backend.get_guild_economy(interaction.guild.id)
    responder = backend.get_responder(interaction)
    if economy is None:
        return await responder(message="This guild is not registered to an economy", colour=red())
    account = get_account_from_name(account, economy)
    try:
        backend.subscribe(interaction.user, account)
    except BackendError as e:
        return await responder(message=f'{e}')
    await responder(f'Successfully subscribed to receive balance updates from {account.account_name}')


@bot.tree.command(name="unsubscribe", guild=test_guild)
@app_commands.describe(account="The account you want to unsubscribe from.")
async def unsubscribe(interaction: discord.Interaction, account: str):
    economy = backend.get_guild_economy(interaction.guild.id)
    responder = backend.get_responder(interaction)
    if economy is None:
        return await responder(message="This guild is not registered to an economy", colour=red())

    account = get_account_from_name(account, economy)
    backend.unsubscribe(interaction.user, account)

    await responder(message=f"You will no longer receive balance updates from {account.account_name}.")


def setup_webhook(l, webhook_url, level):
    wh = WebhookHandler(webhook_url)
    wh.setLevel(level)
    wh.addFilter(LevelFilter(level))
    l.addHandler(wh)

if __name__ == '__main__':
    config = load_config()
    db_path = config.get('database_uri')
    db_path = db_path if db_path else 'sqlite:///database.db'
    backend = Backend(bot, db_path)
    token = config.get('discord_token')
    if not token:
        logger.log(logging.CRITICAL, "Discord token not found in the config file")
        sys.exit(1)

    public_webhook_url = config.get('public_webhook_url')
    private_webhook_url = config.get('private_webhook_url')

    use_api = bool(config.get('api'))

    if public_webhook_url:
        print(public_webhook_url)
        setup_webhook(backend_logger, public_webhook_url, 52)

    if private_webhook_url:
        setup_webhook(backend_logger, private_webhook_url, 51)

    bot.run(token, log_handler=None)
