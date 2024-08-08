import discord
import asyncio
from backend import Backend, BackendError, Account, Permissions, AccountType, TransactionType, TaxType

"""
class LoopAdder:
	\"\"\"
	Allows me to synchronously call async functions when I do not care about the return result
	declaratavely tells asyncio to "go do this at some point" when called.
	\"\"\"
	def __init__(self, func):
		self.func = func

	def __call__(self, *args, **kwargs):
		print(args)
		print(kwargs)
		asyncio.get_event_loop().create_task(self.func(*args, **kwargs))

	def get_async_func(self):
		return self.func

"""

def LoopAdder(func):
	def excecute(*args, **kwargs):
		asyncio.get_event_loop().create_task(func(*args, **kwargs))
	return excecute










class DiscordBackendInterface(Backend):
	def __init__(self, bot, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.bot = bot
		

	def get_responder(self, interaction):
        '''
        Using currying to save on some of the boilerplate code we normally use
        '''
		title = interaction.command.name
		async def responder(message=None, embed=None, colour=None):
			colour = colour if colour is not None else discord.Colour.yellow()
			embed = discord.Embed(colour=discord.Colour.yellow()) if embed is None else embed
			embed.set_thumbnail(url=interaction.member.display_avater.url)
			embed.add_field(name=title, value=message) if message is not None else None
			embed.set_footer(text="This message was sent by a bot and is probably highly important")
			await interaction.response.send_message(embed=embed, ephemeral=self.has_permission(interaction.member, Permissions.USES_EPHEMERAL))
		return responder
			


	async def get_member(self, user_id, guild_id):
		guild = await self.bot.fetch_guild(guild_id)
		return await guild.fetch_member(user_id) if guild is not None else None


	async def get_user_dms(self, user_id):
		user = await self.bot.fetch_user(user_id)
		dms = user.dm_channel if user.dm_channel else await user.create_dm()
		return dms
		

	@LoopAdder
	async def notify_user(self, user_id, message, title, thumbnail=None):
		embed = discord.Embed(colour=discord.Colour.yellow())
		thumbnail = thumbnail if thumbnail is not None else self.bot.user.display_avatar.url
		embed.set_thumbnail(url=thumbnail)
		embed.add_field(name=title, value=message)
		embed.set_footer(text="This message was sent by a bot and is probably highly important")
		dms = await self.get_user_dms(user_id)
		await dms.send(embed=embed)
		

		
	










