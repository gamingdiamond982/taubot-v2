import time
import datetime
import logging

import discord
from discord import Member # I wanted to avoid doing this here, gonna have to rewrite all the unittests.

from typing import List
from typing import Optional
from typing import Callable

from enum import Enum
from uuid import UUID, uuid4
from sqlalchemy import func

from sqlalchemy import String, BigInteger, Date
from sqlalchemy import create_engine
from sqlalchemy import select, delete, update

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from sqlalchemy.orm import Session
from sqlalchemy.orm import DeclarativeBase

from sqlalchemy.exc import MultipleResultsFound



logger = logging.getLogger(__name__)

PRIVATE_LOG = 51
PUBLIC_LOG = 52 # I'm picking these numbers so they do not clash with any others and if needs be we can add more



class Base(DeclarativeBase):
	pass



class AccountType(Enum):
	"""Enum used to represent the different possible account types"""
	USER = 0
	GOVERNMENT = 1
	CORPORATION = 2
	CHARITY = 3
	

class Permissions(Enum):
	"""An Enum that's used to represent different permissions"""
	# Citizen
	OPEN_ACCOUNT = 0
	VIEW_BALANCE = 1
	CLOSE_ACCOUNT = 2
	TRANSFER_FUNDS = 3 
	CREATE_RECCURRING_TRANSFER = 4

	# Admin/Developer
	MANAGE_FUNDS = 5
	
	MANAGE_TAX_BRACKETS = 6
	
	MANAGE_PERMISSIONS = 7 # The scary one, users with this permission will be able to manage even permissions they do not hold.
	MANAGE_ECONOMIES = 8
	OPEN_SPECIAL_ACCOUNT = 9

	LOGIN_AS_ACCOUNT = 10

	GOVERNMENT_OFFICIAL = 11

	

CONSOLE_USER_ID = 0 # a user id for the console - if I ever decide to strap a CLI onto this thing that will be its user id, 0 is an impossible discord id to have so it works for our purposes	

DEFAULT_GLOBAL_PERMISSIONS = [
	Permissions.OPEN_ACCOUNT
]

DEFAULT_OWNER_PERMISSIONS = [
	Permissions.CLOSE_ACCOUNT,
	Permissions.TRANSFER_FUNDS,
	Permissions.CREATE_RECCURRING_TRANSFER,
	Permissions.VIEW_BALANCE,
	Permissions.LOGIN_AS_ACCOUNT
]




class TaxType(Enum):
	"""An Enum used to represent different types of taxes"""
	WEALTH = 0
	INCOME = 1
	VAT = 2

class TransactionType(Enum):
	"""An Enum used to represent different types of transactions"""
	PERSONAL = 0
	INCOME = 1
	PURCHASE = 2





class Economy(Base):
	"""A class used to represent an economy stored in the database"""
	__tablename__ = 'economies'
	economy_id: Mapped[UUID]  = mapped_column(primary_key=True)
#	tax_period: Mapped[int] = mapped_column(default=60*60*24*7)
#	last_tax_timestamp: Mapped[int] = mapped_column()
	owner_guild_id: Mapped[int] = mapped_column(BigInteger(), nullable=False)
	currency_name: Mapped[str] = mapped_column(String(32), unique=True)
	currency_unit: Mapped[str] = mapped_column(String(32))

	guilds: Mapped[List["Guild"]] = relationship(back_populates="economy")
	accounts: Mapped[List["Account"]] = relationship(back_populates="economy")
		



class Guild(Base):
	"""A class used to represent a discord server stored in the database"""
	__tablename__ = 'guilds'
	guild_id: Mapped[int] = mapped_column(BigInteger(), primary_key=True) # Ticking time bomb, in roughly fifteen years this'll break if this is still around then I wish the dev all the best. 
																		  # (doing something like this first should fix it tho: id = id if id < 2^63 else -(id&(2^63-1)) its not ideal but unless SQL now supports unsigned types its the best your gonna get )
	economy_id = mapped_column(ForeignKey("economies.economy_id"))
	
	economy: Mapped[Economy] = relationship(back_populates="guilds")


class Account(Base):
	"""A class used to represent an account stored in the database"""
	__tablename__ = 'accounts'
	account_id: Mapped[UUID] = mapped_column(primary_key=True)
	account_name: Mapped[str] = mapped_column(String(64))
	owner_id: Mapped[int] = mapped_column(BigInteger(), nullable=True)
	account_type: Mapped[AccountType] = mapped_column()
	balance: Mapped[int] = mapped_column(default=0)
	income_to_date: Mapped[int] = mapped_column(default=0)
	economy_id = mapped_column(ForeignKey("economies.economy_id"))
	
	economy: Mapped[Economy] = relationship(back_populates="accounts")



class Permission(Base):
	"""A class used to represent a permission as stored in the database"""
	__tablename__ = 'perms'
	entry_id: Mapped[UUID] = mapped_column(primary_key=True)
	account_id: Mapped[UUID] = mapped_column(ForeignKey('accounts.account_id'), nullable=True)
	user_id: Mapped[int] = mapped_column(BigInteger()) # can also be a role id, due to how discord works there is zero chances of a collision
	permission: Mapped[Permissions] = mapped_column()
	allowed: Mapped[bool] = mapped_column()
	economy_id: Mapped[UUID] = mapped_column(ForeignKey("economies.economy_id", ondelete="CASCADE"), nullable=True)
	
	account: Mapped[Account] = relationship()	
	economy: Mapped[Economy] = relationship()


class Tax(Base):
	"""A class used to represent a tax bracket stored in the database"""
	__tablename__ = 'taxes'
	entry_id: Mapped[UUID] = mapped_column(primary_key=True)
	tax_name: Mapped[str] = mapped_column(String(32))
	affected_type: Mapped[AccountType] = mapped_column()
	tax_type: Mapped[TaxType] = mapped_column()
	bracket_start: Mapped[int] = mapped_column()
	bracket_end: Mapped[int] = mapped_column()
	rate: Mapped[int] = mapped_column()
	to_account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.account_id"))
	economy_id: Mapped[UUID] = mapped_column(ForeignKey("economies.economy_id"))
	to_account: Mapped[Account] = relationship()
	economy: Mapped[Economy] = relationship()


class RecurringTransfer(Base):
	"""A class used to represent a recurring transfer as stored in the database"""
	__tablename__ = 'recurring_transfers'
	entry_id: Mapped[UUID] = mapped_column(primary_key=True)
	
	authorisor_id: Mapped[int] = mapped_column(BigInteger())

	from_account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.account_id"))
	from_account: Mapped[Account] = relationship(foreign_keys=from_account_id)

	to_account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.account_id"))
	to_account: Mapped[Account] = relationship(foreign_keys=to_account_id)

	amount: Mapped[int] = mapped_column()
	last_payment_timestamp: Mapped[int] = mapped_column()
	payment_interval: Mapped[int] = mapped_column()
	number_of_payments_left: Mapped[int] = mapped_column(nullable=True) # thanks hackerman!

	transaction_type: Mapped[TransactionType] = mapped_column()

class BackendError(Exception):
	pass


class StubUser:
	"""
	A class to be used if the user could not be found anymore
	this could be if the user was deleted or if the guild was deleted
	"""
	def __init__(self, user_id):
		self.id = user_id
		self.mention = f"<@{user_id}>"
		self.roles = []


class Backend:
	"""A singleton used to call the backend database"""
	
	def __init__(self, path: str):
		self.engine = create_engine(path)
		self.session = Session(self.engine)
		Base.metadata.create_all(self.engine)



	def get_tax_bracket(self, tax_name, economy):
		return self._one_or_none(select(Tax).where(Tax.tax_name==tax_name).where(Tax.economy_id == economy.economy_id))


	def get_tax_brackets(self, economy):
		return self.session.execute(select(Tax).where(Tax.economy_id == economy.economy_id)).all()


	def create_tax_bracket(self, user: Member, tax_name: str, affected_type: AccountType, tax_type: TaxType, bracket_start: int, bracket_end: int, rate: int, to_account: Account):
		if not self.has_permission(user, Permissions.MANAGE_TAX_BRACKETS, economy=to_account.economy):
			raise BackendError("You do not have permission to create tax brackets in this economy")

		if self.get_tax_bracket(tax_name, to_account.economy) is not None:
			raise BackendError("A tax bracket of that name already exists in this economy")
		tax_bracket = Tax(
			entry_id = uuid4(),
			tax_name=tax_name,
			affected_type = affected_type,
			tax_type = tax_type,
			bracket_start = bracket_start,
			bracket_end = bracket_end,
			rate = rate,
			to_account_id = to_account.account_id,
			economy_id = to_account.economy.economy_id
		)
		self.session.add(tax_bracket)
		self.session.commit()
		logger.log(PUBLIC_LOG, f"{user.mention} created a new tax bracket by the name {tax_name}")
		return tax_bracket




	def delete_tax_bracket(self, user: Member, tax_name: str, economy: Economy):
		if not self.has_permission(user, Permissions.MANAGE_TAX_BRACKETS, economy=economy):
			raise BackendError("You do not have permission to create tax brackets in this economy")

		tax_bracket = self.get_tax_bracket(tax_name, economy)
		if tax_bracket is None:
			raise BackendError("No tax bracket of that name exists in this economy")

		self.session.delete(tax_bracket)
		self.session.commit()
		logger.log(PUBLIC_LOG, f"{user.mention} deleted the tax bracket {tax_name}")


	def _perform_transaction_tax(self, amount: int, transaction_type: TransactionType, economy: Economy) -> int:
		"""Performs taxation and returns the total amount of tax taken"""
		if transaction_type == TransactionType.PURCHASE:
			vat_taxes = self.session.execute(select(Tax).where(Tax.tax_type==TaxType.VAT).where(Tax.economy_id==economy.economy_id).order_by(Tax.bracket_start.desc())).all()
			total_cum_tax = 0
			for vat_tax in vat_taxes:
				vat_tax = vat_tax[0]
				
				accumulated_tax = 0

				full_tax = ((vat_tax.bracket_end - vat_tax.bracket_start)*vat_tax.rate)//100
				if amount >= vat_tax.bracket_end:
					accumulated_tax += full_tax
				else:
					accumulated_tax += ((amount - vat_tax.bracket_start)*vat_tax.rate)//100
				amount -= accumulated_tax
				vat_tax.to_account.balance += accumulated_tax
				total_cum_tax += accumulated_tax
			return total_cum_tax
		return 0


	def perform_tax(self, user:Member, economy: Economy):
		if not self.has_permission(user, Permissions.MANAGE_TAX_BRACKETS, economy=economy):
			raise BackendError("You do not have permission to trigger taxes in this economy")
		
		wealth_taxes = self.session.execute(select(Tax).where(Tax.tax_type==TaxType.WEALTH).where(Tax.economy_id==economy.economy_id).order_by(Tax.bracket_start.desc())).all()
		
		for wealth_tax in wealth_taxes:
			wealth_tax = wealth_tax[0]
			
			accumulated_tax = 0
			full_tax = ((wealth_tax.bracket_end - wealth_tax.bracket_start)*wealth_tax.rate)//100

			accum = self._one_or_none(
								select(func.sum(((Account.balance-wealth_tax.bracket_start)*wealth_tax.rate)//100))
								.select_from(Account)
								.where(Account.account_type==wealth_tax.affected_type)
								.where(Account.balance >= wealth_tax.bracket_start)
								.where(Account.balance < wealth_tax.bracket_end))

			accumulated_tax += accum if accum is not None else 0
			self.session.execute(update(Account)
				.where(Account.account_type == wealth_tax.affected_type)
				.where(Account.balance >= wealth_tax.bracket_start)
				.where(Account.balance < wealth_tax.bracket_end)
				.values(balance=Account.balance-(((Account.balance-wealth_tax.bracket_start)*wealth_tax.rate)//100))
			)

			accum = self._one_or_none(select(func.count()).select_from(Account).where(Account.account_type == wealth_tax.affected_type).where(Account.balance >= wealth_tax.bracket_end))
			accumulated_tax += (accum if accum is not None else 0)*full_tax
			self.session.execute(update(Account).where(Account.account_type == wealth_tax.affected_type).where(Account.balance >= wealth_tax.bracket_end).values(balance=(Account.balance - full_tax)))
			wealth_tax.to_account.balance += accumulated_tax

		income_taxes = self.session.execute(select(Tax).where(Tax.tax_type==TaxType.INCOME).where(Tax.economy_id == economy.economy_id).order_by(Tax.bracket_start.desc())).all()

		for income_tax in income_taxes:
			income_tax = income_tax[0]
			
			accumulated_tax = 0

			full_tax = ((income_tax.bracket_end - income_tax.bracket_start)*income_tax.rate)//100
			accum = self._one_or_none(
						select(func.sum(((Account.income_to_date-income_tax.bracket_start)*income_tax.rate)//100))
						.select_from(Account)
						.where(Account.account_type == income_tax.affected_type)
						.where(Account.income_to_date >= income_tax.bracket_start)
						.where(Account.income_to_date < income_tax.bracket_end)
			)

			self.session.execute(
						update(Account)
						.where(Account.account_type == income_tax.affected_type)
						.where(Account.income_to_date >= income_tax.bracket_start)
						.where(Account.income_to_date < income_tax.bracket_end)
						.values(balance=((Account.income_to_date-income_tax.bracket_start)*income_tax.rate)//100)
			)
			
			accumulated_tax += accum if accum is not None else 0
			
			accum = self._one_or_none(select(func.count()).select_from(Account).where(Account.account_type == income_tax.affected_type).where(Account.income_to_date >= income_tax.bracket_end))
			accumulated_tax += (accum if accum is not None else 0) * full_tax
			self.session.execute(
						update(Account)
						.where(Account.account_type==income_tax.affected_type)
						.where(Account.income_to_date >= income_tax.bracket_end)
						.values(balance=(Account.balance - full_tax))
			)
			
			debtors = self.session.execute(select(Account).where(Account.balance < 0)).all()
			for debtor in debtors:
				debtor = debtor[0]
				debt = -debtor.balance
				accumulated_tax -= debt
				debtor.balance = 0
				logger.log(PRIVATE_LOG, f'{debtor.account_name} failed to meet their tax obligations and still owe {debt}')
			self.session.execute(update(Account).values(income_to_date=0))
			income_tax.to_account.balance += accumulated_tax

		logger.log(PUBLIC_LOG, f'{user.mention} triggered a tax cycle')
		self.session.commit()
			
		
		
		


	
	def create_recurring_transfer(self, user: Member, from_account: Account, to_account: Account, amount: int, payment_interval: int, number_of_payments: int = None, transaction_type: TransactionType = TransactionType.INCOME) -> bool:
		if not self.has_permission(user, Permissions.TRANSFER_FUNDS, account=from_account, economy=from_account.economy):
			raise BackendError("You do not have permission to transfer funds on this account")
		rec_transfer = RecurringTransfer(
				entry_id = uuid4(),
				authorisor_id = user.id,
				from_account_id=from_account.account_id,
				to_account_id = to_account.account_id,
				amount = amount,
				last_payment_timestamp = time.time(),
				payment_interval = payment_interval,
				transaction_type = transaction_type,
				number_of_payments_left = number_of_payments - 1
		)

		self.session.add(rec_transfer)
		self.session.commit()
		self.perform_transaction(user, rec_transfer.from_account, rec_transfer.to_account, rec_transfer.amount, rec_transfer.transaction_type)
	
			
	
	async def tick(self, bot):
		"""
		Triggers a tick in the server should be called externally
		Must be triggered externally 		
		"""


		tick_time = time.time()
		stmt = select(RecurringTransfer).where((RecurringTransfer.last_payment_timestamp + RecurringTransfer.payment_interval) <= tick_time)
		transfers = self.session.execute(stmt).all()
		for transfer in transfers:
			transfer = transfer[0]
			number_of_transfers = int((tick_time - transfer.last_payment_timestamp) // transfer.payment_interval)
			payments_left = transfer.number_of_payments_left # I'm extracting this value since updating ORM objects is more expensive than updating an int and informing the ORM of the changes at the end.
			for i in range(number_of_transfers):
				if payments_left == 0:
					self.session.delete(transfer)
					break
				
				try:
					guild = await bot.fetch_guild(transfer.from_account.economy.owner_guild_id)
					authorisor = await guild.fetch_member(transfer.authorisor_id) if guild is not None else None
					if authorisor is None:
						authorisor = StubUser(transfer.authorisor_id)
					self.perform_transaction(authorisor, transfer.from_account, transfer.to_account, transfer.amount, transfer.transaction_type)
					payments_left -= 1
				except BackendError as e:
					logger.log(PRIVATE_LOG, f'Failed to perform recurring transaction of {transfer.amount} from {transfer.from_account.account_name} to {transfer.to_account.account_name} due to : {e}')
					user = await bot.fetch_user(transfer.authorisor_id)
					if user is not None:
						dms = user.dm_channel if user.dm_channel else await user.create_dm()
						embed = discord.Embed(discord.Colour.red())
						embed.add_field("Recurring Transaction Failed!", "Your recurring transaction of {transfer.amount} every {transfer.payment_interval/60/60/24}days to {transfer.to_account.account_name} was cancelled due to: {e}")
						dms.send(embed=embed)
					self.session.delete(transfer)
			else: # for those unfamiliar with for/else this is not executed if the loop breaks
				transfer.number_of_payments_left = payments_left
				transfer.last_payment_timestamp = tick_time
		self.session.commit()
		logger.log(PUBLIC_LOG, f'successfully performed tick')


	def _one_or_none(self, stmt):
		res = self.session.execute(stmt).one_or_none()
		return res if res is None else res[0]


	def get_permissions(user: Member, economy=None):
		self.session.excecute(select(Permission).where(Permission.economy_id == economy.economy_id if economy is not None else None)).all()


	def has_permission(self, user: Member, permission: Permissions, account: Account = None, economy: Economy = None) -> bool:
		"""
		Checks if a user is allowed to do something
		"""
		if user.id == CONSOLE_USER_ID:
			return True

		if account is not None and economy is None:
			economy = account.economy

		stmt = select(Permission).where(Permission.user_id.in_([user.id] + [r.id for r in user.roles])).where(Permission.permission == permission)
		stmt = stmt.where((Permission.account_id == (account.account_id if account is not None else None)) | (Permission.account_id == None))
		stmt = stmt.where((Permission.economy_id == (economy.economy_id if economy is not None else None)) | (Permission.economy_id == None))
		default = False
		owner_id = account.owner_id if account is not None else None

		if permission in DEFAULT_GLOBAL_PERMISSIONS:
			default = True
		elif permission in DEFAULT_OWNER_PERMISSIONS and user.id == owner_id:
			default = True
		
		
		result = list(self.session.execute(stmt).all())
		
		if len(result) == 0:
			return default


		def evaluate(perm):
			# Precedence for result : 
			# 1. account & economy are null
			# 2. account is null
			# 3. account & economy are not null
			# Economy cannot be null without account being null
			if perm.account_id is None and perm.economy_id is None:
				return 1
			if perm.account_id is None:
				return 2
			return 3

		best = result.pop(0)[0]
		for r in result:
			r = r[0]
			if evaluate(best) > evaluate(r):
				best = r
				continue
			if evaluate(best) == evaluate(r):
				if best.user_id == user.id:
					continue
				elif r.user_id == user.id:
					best = r
				elif user.guild.get_role(best.user_id) < user.guild.get_role(r.user_id):
					best = r
		
		return best.allowed

		
	def _reset_permission(self, user_id, permission, account, economy):
		stmt = (delete(Permission)
				.where(Permission.user_id == user_id)
				.where(Permission.permission == permission)
				.where(Permission.economy_id == (economy.economy_id if economy is not None else None))
				.where(Permission.account_id == (account.account_id if account is not None else None))
		)
		self.session.execute(stmt)
	
	

	def _change_permission(self, user_id, permission, account, economy, allowed):
		if economy is None and account is not None:
			economy = account.economy
		self._reset_permission(user_id, permission, account, economy)
		acc_id = account.account_id if account is not None else None
		econ_id = economy.economy_id if economy is not None else None
		permission = Permission(entry_id=uuid4(), user_id = user_id, account_id=acc_id, economy_id=econ_id,  permission=permission, allowed=allowed)
		self.session.add(permission)

	
	def reset_permission(self, actor: Member, affected_id:int, permission:Permissions, account: Account = None, economy: Economy = None):
		if not self.has_permission(actor, Permissions.MANAGE_PERMISSIONS,  economy=economy):
			raise BackendError("You do not have permission to manage permissions here")

		self._reset_permission(affected_id, permission, account, economy)
		self.session.commit()


	def change_permissions(self, actor: Member, affected_id: int, permission: Permissions, account: Account = None, economy: Economy = None, allowed: bool = True):
		if not self.has_permission(actor, Permissions.MANAGE_PERMISSIONS, economy=economy):
			raise BackendError("You do not have permission to manage permissions here")
		self._change_permission(affected_id, permission, account, economy, allowed)
		self.session.commit()

	def change_many_permissions(self, actor: Member, affected_id: int, *permissions, account: Account = None, economy: Economy = None, allowed: bool = True):
		if not self.has_permission(actor, Permissions.MANAGE_PERMISSIONS, economy=economy):
			raise BackendError("You do not have permission to manage permissions here")
		for permission in permissions:
			self._change_permission(affected_id, permission, account, economy, allowed)
		self.session.commit()

	def get_economies(self):
		return [i[0] for i in self.session.execute(select(Economy)).all()]

	def create_economy(self, user: Member, currency_name: str, currency_unit: str) -> Economy:
		if not self.has_permission(user, Permissions.MANAGE_ECONOMIES):
			raise BackendError("You do not have permission to create economies")
		
		if self.get_economy_by_name(currency_name):
			raise BackendError("An economy by that name already exists")

		now = time.time()
		economy = Economy(economy_id=uuid4(), currency_name=currency_name, currency_unit=currency_unit, owner_guild_id = user.guild.id)
		
		if self.get_guild_economy(user.guild.id) is not None:
			raise BackendError("This guild is already registered to an economy")

		self.session.add(Guild(guild_id=user.guild.id, economy_id=economy.economy_id))
		self.session.add(economy)
		self.change_many_permissions(StubUser(0), user.id, Permissions.MANAGE_PERMISSIONS, economy=economy)

		self.session.commit()
		logger.log(PUBLIC_LOG, f'{user.mention} created the economy {currency_name}')
		return economy


	def get_economy_by_name(self, name: str):
		return self._one_or_none(select(Economy).where(Economy.currency_name == name))
		

	def register_guild(self, user: Member, guild_id: int, economy: Economy):
		if not self.has_permission(user, Permissions.MANAGE_ECONOMIES, economy=economy):
			raise BackendError("You do not have permission to manage economies")

		if self._one_or_none(select(Guild).where(Guild.guild_id == guild_id)) is not None:
			self.unregister_guild(user, guild_id)
		guild = Guild(guild_id=guild_id, economy_id=economy.economy_id)
		self.session.add(guild)
		logger.log(PUBLIC_LOG, f'{user.mention} registered the guild with id: {guild_id} to the economy {economy.currency_name}')
		self.session.commit()
	
	def unregister_guild(self, user: Member, guild_id:int):
		if not self.has_permission(user, Permissions.MANAGE_ECONOMIES, economy=self.get_guild_economy(guild_id)):
			raise BackendError("You do not have permission to manage economies")
		
		if len(self.session.execute(select(Economy).where(Economy.owner_guild_id == guild_id)).all()) != 0:
			raise BackendError("This guild is the owner guild of an economy, cannot change the economy its registered too")
		guild = self.session.get(Guild, guild_id)
		self.session.delete(guild)
		self.session.commit()
	

	def get_guild_economy(self, guild_id: int) -> Optional[Economy]:
		guild = self.session.get(Guild, guild_id)
		return None if guild is None else guild.economy

	def get_guild_ids(self, economy: Economy) -> List[int]:
		return [i.guild_id for i in economy.guilds]

	def delete_economy(self, user: Member, economy: Economy) -> bool:
		if not self.has_permission(user, Permissions.MANAGE_ECONOMIES, economy=economy):
			raise BackendError("You do not have permission to delete this economy")
		self.session.execute(delete(Guild).where(Guild.economy_id == economy.economy_id))
		
		self.session.delete(economy)
		self.session.commit()

	def create_account(self, authorisor: Member, owner_id: int, economy: Economy, name: str=None, account_type: AccountType=AccountType.USER) -> Account:
		if not self.has_permission(authorisor, Permissions.OPEN_ACCOUNT, economy=economy):
			raise BackendError("You do not have permissions to open accounts")

		name = name if name is not None else f"<@!{owner_id}> 's account"
		if len(name) > 64:
			raise BackendError("That name is too long")
		if account_type == AccountType.USER and owner_id is not None and owner_id == authorisor.id:
			acc = self.get_user_account(owner_id, economy)
			if acc is not None:
				raise BackendError("You already have a user account")
		elif not self.has_permission(authorisor, Permissions.OPEN_SPECIAL_ACCOUNT, economy=economy):
			raise BackendError("You do not have permission to open special accounts")
			
		account = Account(account_id=uuid4(), account_name=name, owner_id=owner_id, account_type=account_type, balance=0, economy=economy)
		self.session.add(account)
		self.session.commit()
		return account

	def delete_account(self, authorisor: Member, account):
		if not self.has_permission(authorisor, Permissions.CLOSE_ACCOUNT, account=account, economy=account.economy):
			raise BackendError("You do not have permission to close this account")
		self.session.delete(account)
		self.session.commit()

	def get_user_account(self, user_id: int, economy: Economy) -> Account | None:
		return self._one_or_none(select(Account).where(Account.owner_id == user_id).where(Account.account_type == AccountType.USER).where(Account.economy_id == economy.economy_id))

	def get_account_by_name(self, account_name: str, economy: Economy) -> Account | None:
		return self._one_or_none(select(Account).where(Account.account_name == account_name).where(Account.economy_id == economy.economy_id))

	
	def perform_transaction(self, user: Member, from_account: Account, to_account: Account, amount: int, transaction_type: TransactionType = TransactionType.PERSONAL):
		"""Performs a transaction from one account to another accounting for tax, returns a boolean indicating if the transaction was successful"""
		if not self.has_permission(user, Permissions.TRANSFER_FUNDS, account=from_account, economy=from_account.economy):
			raise BackendError("You do not have permission to transfer funds from that account")

		if from_account.economy_id != to_account.economy_id:
			raise BackendError("Cannot transfer funds from one economy to another")

		if from_account.balance < amount:
			raise BackendError("You do not have sufficient funds to transfer from that account")

		if transaction_type == TransactionType.INCOME:
			to_account.income_to_date += amount
		from_account.balance -= amount
		amount -= self._perform_transaction_tax(amount, transaction_type, from_account.economy)
		to_account.balance += amount

		log = PRIVATE_LOG
		if self.has_permission(user, Permissions.GOVERNMENT_OFFICIAL, economy=from_account.economy):
			log = PUBLIC_LOG
		logger.log(log, f"{user.mention} transferred {amount} from {from_account.account_name} to {to_account.account_name}")

		self.session.commit()

	def print_money(self, user: Member, to_account: Account, amount: int):
		if not self.has_permission(user, Permissions.MANAGE_FUNDS, account=to_account, economy=to_account.economy):
			raise BackendError("You do not have permission to print funds")
		to_account.balance += amount

		logger.log(PUBLIC_LOG, f'{user.mention} printed {amount} to {to_account.account_name}')
		self.session.commit()

	def remove_funds(self, user: Member, from_account: Account, amount: int):
		if not self.has_permission(user, Permissions.MANAGE_FUNDS, account=from_account, economy=from_account.economy):
			raise BackendError("You do not have permission to remove funds")
		if from_account.balance < amount:
			raise BackendError("There are not sufficient funds in this account to perform this action")
		from_account.balance -= amount
		logger.log(PUBLIC_LOG, f'{user.mention} removed {amount} from {from_account.account_name}')
		self.session.commit()




