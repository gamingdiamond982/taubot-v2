from typing import List
from typing import Optional

from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import String, BigInteger, Date
from sqlalchemy import create_engine

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from sqlalchemy.orm import DeclarativeBase





class Base(DeclarativeBase):
	pass



class AccountType(Enum):
	USER = 0
	GOVERNMENT = 1
	CORPORATION = 2
	CHARITY = 3
	

class Permissions(Enum):

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

class TaxType(Enum):
	WEALTH = 0
	INCOME = 1
	
	





class Economy(Base):
	__tablename__ = 'economies'
	economy_id: Mapped[UUID]  = mapped_column(primary_key=True)
	currency_name: Mapped[str] = mapped_column(String(32))
	currency_unit: Mapped[str] = mapped_column(String(32))

	guilds: Mapped[List["Guild"]] = relationship(back_populates="economy")
	accounts: Mapped[List["Account"]] = relationship(back_populates="economy")



class Guild(Base):
	__tablename__ = 'guilds'
	guild_id: Mapped[int] = mapped_column(BigInteger(), primary_key=True) # Ticking time bomb, in roughly fifteen years this'll break if this is still around then I wish the dev all the best.
	economy_id = mapped_column(ForeignKey("economies.economy_id"))
	
	economy: Mapped[Economy] = relationship(back_populates="guilds")


class Account(Base):
	__tablename__ = 'accounts'
	account_id: Mapped[UUID] = mapped_column(primary_key=True)
	account_name: Mapped[str] = mapped_column(String(32))
	owner_id: Mapped[int] = mapped_column(BigInteger())
	account_type: Mapped[AccountType] = mapped_column()
	balance: Mapped[int] = mapped_column(default=0)
	economy_id = mapped_column(ForeignKey("economies.economy_id"))
	
	economy: Mapped[Economy] = relationship(back_populates="accounts")


class Permission(Base):
	__tablename__ = 'permissions'
	entry_id: Mapped[UUID] = mapped_column(primary_key=True)
	account_id: Mapped[UUID] = mapped_column(ForeignKey('accounts.account_id'), nullable=True)
	user_id: Mapped[int] = mapped_column(BigInteger())
	permission: Mapped[Permissions] = mapped_column()
	allowed: Mapped[bool] = mapped_column()
	economy_id: Mapped[UUID] = mapped_column(ForeignKey("economies.economy_id"), nullable=True)
	
	economy: Mapped[Economy] = relationship()


class Tax(Base):
	__tablename__ = 'taxes'
	entry_id: Mapped[UUID] = mapped_column(primary_key=True)
	affected_type: Mapped[AccountType] = mapped_column()
	tax_type: Mapped[TaxType] = mapped_column()
	bracket_start: Mapped[int] = mapped_column()
	bracket_end: Mapped[int] = mapped_column()
	rate: Mapped[int] = mapped_column()


class RecurringTransfer(Base):
	__tablename__ = 'recurring_transfers'
	entry_id: Mapped[UUID] = mapped_column(primary_key=True)
	
	from_account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.account_id"))
	from_account: Mapped[Account] = relationship(foreign_keys=from_account_id)

	to_account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.account_id"))
	to_account: Mapped[Account] = relationship(foreign_keys=to_account_id)

	amount: Mapped[int] = mapped_column()
	last_payment_timestamp = mapped_column(Date)
	next_payment_timestamp = mapped_column(Date)
	payment_interval: Mapped[int] = mapped_column()

	

	
class Backend:
	"""A singleton used to call the backend database"""
	
	def __init__(self, path):
		engine = create_engine(path)
		Base.metadata.create_all(engine)
		

if __name__ == '__main__':
	Backend('sqlite:///database.db')











