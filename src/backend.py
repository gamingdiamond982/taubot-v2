import asyncio
import time

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
	TRANSFER_FUNDS = 2 # admins will have transfer funds on the global account construct
	CREATE_RECCURRING_TRANSFER = 3

	# Admin/Developer
	PRINT_MONEY = 4
	DELETE_MONEY = 5
	CREATE_PROXY = 6
	
	CREATE_TAX_BRACKET = 7
	DELETE_TAX_BRACKET = 8
	
	MANAGE_PERMISSIONS = 9 # The scary one, users with this permission will be able to manage even permissions they do not hold.
	MANAGE_ECONOMIES = 10
	

CONSOLE_USER_ID = 0 # a user id for the console - if I ever decide to strap a CLI onto this thing that will be its user id, 0 is an impossible discord id to have so it works for our purposes	

DEFAULT_GLOBAL_PERMISSIONS = [
	Permission.OPEN_ACCOUNT
]

DEFAULT_OWNER_PERMISSIONS = [
	Permissions.CLOSE_ACCOUNT,
	Permissions.TRANSFER_FUNDS,
	Permissions.CREATE_RECCURRING_TRANSFER
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
	currency_name: Mapped[str] = mapped_column(String(32))
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
	
	from_account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.account_id"))
	from_account: Mapped[Account] = relationship(foreign_keys=from_account_id)

	to_account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.account_id"))
	to_account: Mapped[Account] = relationship(foreign_keys=to_account_id)

	amount: Mapped[int] = mapped_column()
	last_payment_timestamp = mapped_column(Date)
	payment_interval: Mapped[int] = mapped_column()
	number_of_payments: Mapped[int] = mapped_column() # thanks hackerman!

	transaction_type: Mapped[TransactionType] = mapped_column()

class Backend:
	"""A singleton used to call the backend database"""
	
	def __init__(self, path: str):
		self.engine = create_engine(path)
		self.session = Session(self.engine)
		Base.metadata.create_all(self.engine)
		
	
	def tick(self):
		"""Triggers a tick in the server should be called externally"""
		print("ticked!")


	def has_permission(self, user_id: int, permission: Permissions, account: Account = None, economy: Economy = None) -> bool:
		"""
		Checks if a user is allowed to do something, returns false if you've somehow ended up with multiple results in the db
		this should be impossible, but I'd rather err on the side of caution when it comes to permissions.
		"""
		if user_id == CONSOLE_USER_ID:
			return True

		stmt = select(Permission).where(Permission.user_id == user_id).where(Permission.permission == permission)
		stmt = stmt.where(Permission.account_id == account.account_id if account is not None else None)
		stmt = stmt.where(Permission.economy_id == economy.economy_id if economy is not None else None)
		default = False
		owner_id = account.owner_id if account is not None else None

		if permission in DEFAULT_GLOBAL_PERMISSIONS:
			default = True
			stmt = stmt.where(Permission.allowed == False)
		elif permission in DEFAULT_OWNER_PERMISSIONS and user_id == owner_id:
			default = True
			stmt = stmt.where(Permission.allowed == False)
		else:
			stmt = stmt.where(Permission.allowed == True)
		
		try:
			result = self.session.execute(stmt).one_or_none()
		except MultipleResultsFound:
			return False # This code path should be impossible but better be safe than sorry

		if result is None:
			return default
		
		return not default
		
	def _reset_permission(self, user_id, permission, account, economy):
		stmt = (delete(Permission)
				.where(Permission.user_id == user_id)
				.where(Permission.permission == permission)
				.where(Permission.economy_id == economy.economy_id)
				.where(Permission.account_id == account.account_id)
		)
		self.session.execute(stmt)
		self.session.commit()
		


	def change_permissions(self, actor_id: int, user_id: int, permission: Permissions, account: Account = None, economy: Economy = None, allowed: bool = True) -> bool:
		if not self.has_permission(actor_id, Permissions.MANAGE_PERMISSIONS):
			return False

		self._reset_permissions(user_id, permission, account, economy)
		permission = Permission(entry_id=uuid4(), account_id=account.account_id, economy_id=economy.economy_id,  permission=permission, allowed=allowed)
		self.session.add(permission)
		self.session.commit()
		return True		



	def create_economy(self, user_id: int, currency_name: str, currency_unit: str) -> Economy:
		if not self.has_permission(user_id, Permissions.MANAGE_ECONOMIES):
			return None

		economy = Economy(economy_id=uuid4(), currency_name=currency_name, currency_unit=currency_unit)	
		self.session.add(economy)
		self.session.commit()
		return economy


	def register_guild(self, user_id: int, guild_id: int, economy: Economy) -> bool:
		if not self.has_permission(user_id, Permissions.MANAGE_ECONOMIES):
			return False

		if self.get_guild_economy(guild_id) is not None:
			self.unregister_guild(user_id, guild_id)
		guild = Guild(guild_id=guild_id, economy_id=economy.economy_id)
		self.session.add(guild)
		self.session.commit()
		return True
	
	def unregister_guild(self, user_id: int, guild_id:int) -> bool:
		if not self.has_permission(user_id, Permissions.MANAGE_ECONOMIES):
			return False

		guild = self.session.get(Guild, guild_id)
		self.session.delete(guild)
		self.session.commit()
		return True
	

	def get_guild_economy(self, guild_id: int) -> Optional[Economy]:
		guild = self.session.get(Guild, guild_id)
		return None if guild is None else guild.economy

	def get_guild_ids(self, economy: Economy) -> List[int]:
		return [i.guild_id for i in economy.guilds]

	def delete_economy(self, user_id: int, economy: Economy) -> bool:
		if not self.has_permission(user_id, Permissions.MANAGE_ECONOMIES):
			return False
		self.session.delete(economy)
		self.session.commit()
		return True

	def create_account(self, owner_id, economy, name=None, account_type=AccountType.USER) -> Account:
		if not self.has_permission(user_id, Permissions.OPEN_ACCOUNT):
			return None
		name = name if name is not None else f"<@!{owner_id}> 's account"
		account = Account(account_id=uuid4(), account_name=name, owner_id=owner_id, account_type=account_type, balance=0, economy=economy)
		self.session.add(account)
		self.session.commit()
		return account

	def perform_transaction_tax(self, amount: int, transaction_type: TransactionType) -> int:
		"""Performs taxation and returns the total amount of tax taken"""
		return 0 # TODO: make this actually do something
	
	def perform_transaction(self, user_id: int, from_account: Account, to_account: Account, amount: int, transaction_type: TransactionType = TransactionType.PERSONAL) -> bool:
		"""Performs a transaction from one account to another accounting for tax, returns a boolean indicating if the transaction was successful"""
		if not self.has_permission(user_id, Permissions.TRANSFER_FUNDS, account=from_account, economy=from_account.economy):
			return False

		if from_account.balance < amount:
			return False
		from_account.balance -= amount
		amount -= perform_transaction_tax(amount, transaction_type)
		to_account.balance += amount
		return True
		



if __name__ == '__main__':
	backend = Backend('sqlite:///database.db')
	economy = backend.create_economy("tau", "t")
	backend.get_guild_economy(12345)
	backend.register_guild(12345, economy)
	account = backend.create_account(12345, economy)












