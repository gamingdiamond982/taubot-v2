import time
import datetime
import logging

from typing import List
from typing import Optional
from typing import Callable

from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import String, BigInteger, Date
from sqlalchemy import create_engine
from sqlalchemy import select, delete

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from sqlalchemy.orm import Session
from sqlalchemy.orm import DeclarativeBase

from sqlalchemy.exc import MultipleResultsFound



logger = logging.getLogger(__name__)



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
	CLOSE_ACCOUNT = 1
	TRANSFER_FUNDS = 2 
	CREATE_RECCURRING_TRANSFER = 3

	# Admin/Developer
	MANAGE_FUNDS = 3
	
	CREATE_TAX_BRACKET = 4
	DELETE_TAX_BRACKET = 5
	
	MANAGE_PERMISSIONS = 6 # The scary one, users with this permission will be able to manage even permissions they do not hold.
	MANAGE_ECONOMIES = 7
	OPEN_SPECIAL_ACCOUNT = 8
	

CONSOLE_USER_ID = 0 # a user id for the console - if I ever decide to strap a CLI onto this thing that will be its user id, 0 is an impossible discord id to have so it works for our purposes	

DEFAULT_GLOBAL_PERMISSIONS = [
	Permissions.OPEN_ACCOUNT
]

DEFAULT_OWNER_PERMISSIONS = [
	Permissions.CLOSE_ACCOUNT,
	Permissions.TRANSFER_FUNDS,
	Permissions.CREATE_RECCURRING_TRANSFER
]

DEFAULT_ADMIN_PERMISSIONS = [
	Permissions.MANAGE_PERMISSIONS,
	Permissions.MANAGE_FUNDS,
	Permissions.TRANSFER_FUNDS,
	Permissions.CLOSE_ACCOUNT,
	Permissions.OPEN_ACCOUNT,
	Permissions.OPEN_SPECIAL_ACCOUNT
]



class TaxType(Enum):
	"""An Enum used to represent different types of taxes"""
	WEALTH = 0
	INCOME = 1
	VAT = 2
	GIFT = 3

class TransactionType(Enum):
	"""An Enum used to represent different types of transactions"""
	PERSONAL = 0
	INCOME = 1
	PURCHASE = 2





class Economy(Base):
	"""A class used to represent an economy stored in the database"""
	__tablename__ = 'economies'
	economy_id: Mapped[UUID]  = mapped_column(primary_key=True)
	currency_name: Mapped[str] = mapped_column(String(32), unique=True)
	currency_unit: Mapped[str] = mapped_column(String(32))

	guilds: Mapped[List["Guild"]] = relationship(back_populates="economy")
	accounts: Mapped[List["Account"]] = relationship(back_populates="economy")
		



class Guild(Base):
	"""A class used to represent a discord server stored in the database"""
	__tablename__ = 'guilds'
	guild_id: Mapped[int] = mapped_column(BigInteger(), primary_key=True) # Ticking time bomb, in roughly fifteen years this'll break if this is still around then I wish the dev all the best. 
																		  # (doing something like this first should fix it tho: id = id if id < 2^63 else -(id&(2^63-1)) its not ideal but unless SQL now supports unsigned types its the best your gonna get )
	economy_id = mapped_column(ForeignKey("economies.economy_id", ondelete="CASCADE"))
	
	economy: Mapped[Economy] = relationship(back_populates="guilds")


class Account(Base):
	"""A class used to represent an account stored in the database"""
	__tablename__ = 'accounts'
	account_id: Mapped[UUID] = mapped_column(primary_key=True)
	account_name: Mapped[str] = mapped_column(String(32))
	owner_id: Mapped[int] = mapped_column(BigInteger())
	account_type: Mapped[AccountType] = mapped_column()
	balance: Mapped[int] = mapped_column(default=0)
	economy_id = mapped_column(ForeignKey("economies.economy_id"))
	
	economy: Mapped[Economy] = relationship(back_populates="accounts")



class Permission(Base):
	"""A class used to represent a permission as stored in the database"""
	__tablename__ = 'permissions'
	entry_id: Mapped[UUID] = mapped_column(primary_key=True)
	account_id: Mapped[UUID] = mapped_column(ForeignKey('accounts.account_id'), nullable=True)
	user_id: Mapped[int] = mapped_column(BigInteger())
	permission: Mapped[Permissions] = mapped_column()
	allowed: Mapped[bool] = mapped_column()
	economy_id: Mapped[UUID] = mapped_column(ForeignKey("economies.economy_id"), nullable=True)
	
	economy: Mapped[Economy] = relationship()


class Tax(Base):
	"""A class used to represent a tax bracket stored in the database"""
	__tablename__ = 'taxes'
	entry_id: Mapped[UUID] = mapped_column(primary_key=True)
	affected_type: Mapped[AccountType] = mapped_column()
	tax_type: Mapped[TaxType] = mapped_column()
	bracket_start: Mapped[int] = mapped_column()
	bracket_end: Mapped[int] = mapped_column()
	rate: Mapped[int] = mapped_column()
	to_account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.account_id"))
	to_account: Mapped[Account] = relationship()


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



class Backend:
	"""A singleton used to call the backend database"""
	
	def __init__(self, path: str):
		self.engine = create_engine(path)
		self.session = Session(self.engine)
		Base.metadata.create_all(self.engine)
	
	def create_recurring_transfer(self, user_id: int, from_account: Account, to_account: Account, amount: int, payment_interval: int, number_of_payments: int = None, transaction_type: TransactionType = TransactionType.INCOME) -> bool:
		if not self.has_permission(user_id, Permissions.TRANSFER_FUNDS, account=from_account, economy=from_account.economy):
			raise Exception("You do not have permission to transfer funds on this account")
		rec_transfer = RecurringTransfer(
				entry_id = uuid4(),
				authorisor_id = user_id,
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
		self.perform_recurring_transfer(rec_transfer)


	def perform_recurring_transfer(self, rec_transfer: RecurringTransfer) -> bool:
		try:
			self.perform_transaction(rec_transfer.authorisor_id, rec_transfer.from_account, rec_transfer.to_account, rec_transfer.amount, transaction_type=rec_transfer.transaction_type)
			return True
		except BackendError as e:
			logger.log(51, f'Failed to perform recurring transaction of {rec_transfer.amount} from {rec_transfer.from_account.account_name} to {rec_transfer.to_account.account_name} due to : {e}')
			return False
		
			
	
	def tick(self):
		"""Triggers a tick in the server should be called externally"""
		# TODO: implement a callbacks system that dms users whenever their transactions have terminated for unexpected reasons
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
				if not self.perform_recurring_transfer(transfer):
					# The user no longer has permission to perform the transfer or sufficient funds to do so, so it should be deleted
					# TODO: log this
					self.session.delete(transfer)
					break
				payments_left -= 1
			else: # for those unfamiliar with for/else this is not executed if the loop breaks
				transfer.number_of_payments_left = payments_left
				transfer.last_payment_timestamp = tick_time
		self.session.commit()
		logger.log(52, f'successfully performed tick')


	def _one_or_none(self, stmt):
		res = self.session.execute(stmt).one_or_none()
		return res if res is None else res[0]

	def has_permission(self, user_id: int, permission: Permissions, account: Account = None, economy: Economy = None) -> bool:
		"""
		Checks if a user is allowed to do something
		"""
		if user_id == CONSOLE_USER_ID:
			return True

		if account is not None and economy is None:
			economy = account.economy

		stmt = select(Permission).where(Permission.user_id == user_id).where(Permission.permission == permission)
		stmt = stmt.where((Permission.account_id == (account.account_id if account is not None else None)) | (Permission.account_id == None))
		stmt = stmt.where((Permission.economy_id == (economy.economy_id if economy is not None else None)) | (Permission.economy_id == None))
		default = False
		owner_id = account.owner_id if account is not None else None

		if permission in DEFAULT_GLOBAL_PERMISSIONS:
			default = True
		elif permission in DEFAULT_OWNER_PERMISSIONS and user_id == owner_id:
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
			perm = perm[0]
			if perm.account_id is None and perm.economy_id is None:
				return 1
			if perm.account_id is None:
				return 2
			return 3
		result.sort(key=evaluate)
		
		
		return result[0][0].allowed

		
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

	
	def reset_permission(self, actor_id:int, user_id:int, permission:Permissions, account: Account = None, economy: Economy = None):
		if not self.has_permission(actor_id, Permissions.MANAGE_PERMISSIONS,  economy=economy):
			raise Exception("You do not have permission to manage permissions here")

		self._reset_permission(user_id, permission, account, economy)
		self.session.commit()


	def change_permissions(self, actor_id: int, user_id: int, permission: Permissions, account: Account = None, economy: Economy = None, allowed: bool = True):
		if not self.has_permission(actor_id, Permissions.MANAGE_PERMISSIONS, economy=economy):
			raise Exception("You do not have permission to manage permissions here")
		self._change_permission(user_id, permission, account, economy, allowed)
		self.session.commit()

	def change_many_permissions(self, actor_id, user_id, *permissions, account: Account = None, economy: Economy = None, allowed: bool = True):
		if not self.has_permission(actor_id, Permissions.MANAGE_PERMISSIONS, economy=economy):
			raise Exception("You do not have permission to manage permissions here")
		for permission in permissions:
			self._change_permission(user_id, permission, account, economy, allowed)
		self.session.commit()
		return True

	def get_economies(self):
		return [i[0] for i in self.session.execute(select(Economy)).all()]

	def create_economy(self, user_id: int, currency_name: str, currency_unit: str) -> Economy:
		if not self.has_permission(user_id, Permissions.MANAGE_ECONOMIES):
			raise Exception("You do not have permission to create economies")
		
		if self.get_economy_by_name(currency_name):
			raise Exception("An economy by that name already exists")

		economy = Economy(economy_id=uuid4(), currency_name=currency_name, currency_unit=currency_unit)	
		self.session.add(economy)
		self.change_many_permissions(0, user_id, *DEFAULT_ADMIN_PERMISSIONS, economy=economy)
		self.session.commit()
		logger.log(52, f'<@{user_id}> created the economy {currency_name}')
		return economy


	def get_economy_by_name(self, name: str):
		return self._one_or_none(select(Economy).where(Economy.currency_name == name))
		

	def register_guild(self, user_id: int, guild_id: int, economy: Economy) -> bool:
		if not self.has_permission(user_id, Permissions.MANAGE_ECONOMIES, economy=economy):
			raise Exception("You do not have permission to manage economies")

		if self._one_or_none(select(Guild).where(Guild.guild_id == guild_id)) is not None:
			self.unregister_guild(user_id, guild_id)
		guild = Guild(guild_id=guild_id, economy_id=economy.economy_id)
		self.session.add(guild)
		logger.log(52, f'<@{user_id}> registered the guild with id: {guild_id} to the economy {economy.currency_name}')
		self.session.commit()
	
	def unregister_guild(self, user_id: int, guild_id:int) -> bool:
		if not self.has_permission(user_id, Permissions.MANAGE_ECONOMIES, economy=self.get_guild_economy(guild_id)):
			raise Exception("You do not have permission to manage economies")

		guild = self.session.get(Guild, guild_id)
		self.session.delete(guild)
		self.session.commit()
	

	def get_guild_economy(self, guild_id: int) -> Optional[Economy]:
		guild = self.session.get(Guild, guild_id)
		return None if guild is None else guild.economy

	def get_guild_ids(self, economy: Economy) -> List[int]:
		return [i.guild_id for i in economy.guilds]

	def delete_economy(self, user_id: int, economy: Economy) -> bool:
		if not self.has_permission(user_id, Permissions.MANAGE_ECONOMIES, economy=economy):
			raise Exception("You do not have permission to delete this economy")
		self.session.delete(economy)
		self.session.commit()

	def create_account(self, authorisor_id: int, owner_id: int, economy: Economy, name: str=None, account_type: AccountType=AccountType.USER) -> Account:
		if not self.has_permission(authorisor_id, Permissions.OPEN_ACCOUNT, economy=economy):
			raise Exception("You do not have permissions to open accounts")

		name = name if name is not None else f"<@!{owner_id}> 's account"
		if account_type == AccountType.USER:
			acc = self.get_user_account(owner_id, economy)
			if acc is not None:
				raise Exception("You already have a user account")
		elif not self.has_permission(authorisor_id, Permissions.OPEN_SPECIAL_ACCOUNT, economy=economy):
			raise Exception("You do not have permission to open special accounts")
			
		account = Account(account_id=uuid4(), account_name=name, owner_id=owner_id, account_type=account_type, balance=0, economy=economy)
		self.session.add(account)
		self.session.commit()
		return account

	def delete_account(self, authorisor_id: int, account):
		if not self.has_permission(authorisor_id, Permissions.CLOSE_ACCOUNT, account=account, economy=account.economy):
			raise Exception("You do not have permission to close this account")
		self.session.delete(account)
		self.session.commit()

	def get_user_account(self, user_id: int, economy):
		return self._one_or_none(select(Account).where(Account.owner_id == user_id).where(Account.account_type == AccountType.USER).where(Account.economy_id == economy.economy_id))

	def perform_transaction_tax(self, amount: int, transaction_type: TransactionType) -> int:
		"""Performs taxation and returns the total amount of tax taken"""
		return 0 # TODO: make this actually do something
	
	def perform_transaction(self, user_id: int, from_account: Account, to_account: Account, amount: int, transaction_type: TransactionType = TransactionType.PERSONAL):
		"""Performs a transaction from one account to another accounting for tax, returns a boolean indicating if the transaction was successful"""
		if not self.has_permission(user_id, Permissions.TRANSFER_FUNDS, account=from_account, economy=from_account.economy):
			raise Exception("You do not have permission to transfer funds from that account")

		if from_account.balance < amount:
			raise Exception("You do not have sufficient funds to transfer from that account")
		from_account.balance -= amount
		amount -= self.perform_transaction_tax(amount, transaction_type)
		to_account.balance += amount
		self.session.commit()

	def print_money(self, user_id: int, to_account: Account, amount: int):
		if not self.has_permission(user_id, Permissions.MANAGE_FUNDS, account=to_account, economy=to_account.economy):
			raise Exception("You do not have permission to print funds")
		to_account.balance += amount
		self.session.commit()

	def remove_funds(self, user_id: int, from_account: Account, amount: int):
		if not self.has_permission(user_id, Permissions.MANAGE_FUNDS, account=from_account, economy=from_account.economy):
			raise Exception("You do not have permission to remove funds")
		if from_account.balance < amount:
			raise Exception("There are not sufficient funds in this account to perform this action")
		from_account.balance -= amount
		self.session.commit()
		
		














