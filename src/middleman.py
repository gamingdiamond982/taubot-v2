import discord
import asyncio
import typing
from backend import Backend, Permissions, BackendError, Account, AccountType, TransactionType, TaxType, frmt, logger, PRIVATE_LOG

def loop_adder(func: typing.Callable[..., typing.Coroutine]):
    """
    Decorator that schedules an async function to run in the event loop as a task.
    :param func: The coroutine to be scheduled.
    :returns: A wrapped function that schedules the original coroutine as a task when called.
    """
    def execute(*args, **kwargs):
        asyncio.get_event_loop().create_task(func(*args, **kwargs))
    return execute

class DiscordBackendInterface(Backend):
    """
    A discord-aware interface of the backend.
    """

    def __init__(self, bot: discord.Client, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot

    def get_responder(self, interaction: discord.Interaction):
        """
        Returns the responder function used to reply in response to commands.

        :param interaction: The Discord interaction object, specifically a command interaction.
        :returns: The responder function.

        .. note
        This is used in consideration of a user's ephemeral preferences and to avoid repeating boilerplate code.
        """
        
        assert interaction.command
        title = interaction.command.name
        async def responder(message=None, colour=None, embed=None, thumbnail=interaction.user.display_avatar.url, *, edit=False, as_embed=True, **kwargs):
            colour = colour if colour is not None else discord.Colour.yellow()
            embed = discord.Embed(colour=colour) if embed is None and as_embed else embed
            if embed:
                embed.set_thumbnail(url=thumbnail)
                embed.add_field(name=title, value=message) if message is not None else None
                embed.set_footer(text="This message was sent by a bot and is probably highly important")
            ephemeral = self.has_permission(interaction.user, Permissions.USES_EPHEMERAL)
            if edit:
                await interaction.edit_original_response(content=message if message and not as_embed else None, embed=embed, **kwargs)
            else:
                await interaction.response.send_message(content=message if message and not as_embed else None, embed=embed, ephemeral=ephemeral, **kwargs)
        return responder

    def get_account_from_interaction(self, interaction: discord.Interaction):
        """
        Returns the interaction user's account in the interaction guild's economy.

        :param interaction: The Discord interaction object.
        :returns: The account if it exists, else `None`.
        """

        if not interaction.guild:
            return None

        economy = self.get_guild_economy(interaction.guild.id)
        if not economy:
            return None

        return self.get_user_account(interaction.user.id, economy)

    async def get_member(self, user_id: int, guild_id: int):
        """
        Fetches a user with a specified ID from a specific guild. 

        :param user_id: User ID.
        :param guild_id: Guild ID.
        :returns: The user as a member object if it and the guild exist, else `None`.
        """

        guild = await self.bot.fetch_guild(guild_id)
        return await guild.fetch_member(user_id) if guild is not None else None

    async def get_user_dms(self, user_id: int):
        """
        Fetches a user's private messages with the bot.

        :param user_id: User ID.
        :returns: The DM channel used between the user and the bot.
        """

        user = await self.bot.fetch_user(user_id)
        dms = user.dm_channel if user.dm_channel else await user.create_dm()
        return dms

    @loop_adder
    async def notify_user(self, user_id: int, message: str, title: str, thumbnail=None):
        """
        Notifies a user of a change through private messages.

        :param user_id: User ID.
        :param message: The message you wish to notify the user of.
        :param title: The title of the notification embed.
        :param thumbnail: The URL of the image used in the notification embed's thumbnail.
        """

        if not user_id:
            return

        embed = discord.Embed(colour=discord.Colour.yellow())
        embed.set_thumbnail(url=thumbnail)
        embed.add_field(name=title, value=message)
        embed.set_footer(text="This message was sent by a bot and is probably highly important")
        dms = await self.get_user_dms(user_id)

        try:
            await dms.send(embed=embed)
        except discord.Forbidden:
            logger.log(PRIVATE_LOG, f"Could not send message to <@!{user_id}> in private messages")