from io import StringIO
import logging
import time
import csv
from datetime import datetime
from enum import Enum
from typing import Any
from typing import List
from typing import Optional
from uuid import UUID, uuid4

from discord import Member, User  # I wanted to avoid doing this here, gonna have to rewrite all the unittests.
from sqlalchemy import ForeignKey, INT, inspect, union, or_, Delete
from sqlalchemy import String, BigInteger, DateTime, \
    JSON  # I wanted to avoid using the JSON type since it locks us into certain databases, but on further research it seems to be supported by most major db distributions, and having unstructured data at times is sometimes just way too useful.
from sqlalchemy import create_engine
from sqlalchemy import func
from sqlalchemy import select, delete, update
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import Session
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

logger = logging.getLogger(__name__)

PRIVATE_LOG = 51
PUBLIC_LOG = 52 # I'm picking these numbers so they do not clash with any others and if needs be we can add more


def frmt(amount: int) -> str:
    return f'{amount//100}.{amount%100:02}'


class Base(DeclarativeBase):
    type_annotation_map= {
        dict[str, Any]: JSON
    }


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

    # attributes or some BS
    USES_EPHEMERAL = 12


    

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

UNPRIVILEGED_PERMISSIONS = [
    Permissions.USES_EPHEMERAL,
    Permissions.GOVERNMENT_OFFICIAL
]



class TaxType(Enum):
    """An Enum used to represent different types of taxes"""
    WEALTH = 0
    INCOME = 1
    VAT = 2
    TRANSACTION = 3

class TransactionType(Enum):
    """An Enum used to represent different types of transactions"""
    PERSONAL = 0
    INCOME = 1
    PURCHASE = 2



class Actions(Enum):
    """An Enum to represent different potential actions"""
    TRANSFER = 0
    MANAGE_FUNDS = 1
    UPDATE_PERMISSIONS = 2
    UPDATE_TAX_BRACKETS = 3
    UPDATE_ECONOMIES = 4
    PERFORM_TAXES = 5
    UPDATE_ACCOUNTS = 6

    
class CUD(Enum):
    CREATE = 0
    UPDATE = 1
    DELETE = 2




class Economy(Base):
    """A class used to represent an economy stored in the database"""
    __tablename__ = 'economies'
    economy_id: Mapped[UUID]  = mapped_column(primary_key=True)
#   tax_period: Mapped[int] = mapped_column(default=60*60*24*7)
#   last_tax_timestamp: Mapped[int] = mapped_column()
    owner_guild_id: Mapped[int] = mapped_column(BigInteger(), nullable=False)
    currency_name: Mapped[str] = mapped_column(String(32), unique=True)
    currency_unit: Mapped[str] = mapped_column(String(32))

    guilds: Mapped[List["Guild"]] = relationship(back_populates="economy")
    accounts: Mapped[List["Account"]] = relationship(back_populates="economy")
    applications: Mapped[List["Application"]] = relationship(back_populates="economy")
        


class Guild(Base):
    """A class used to represent a discord server stored in the database"""
    __tablename__ = 'guilds'
    guild_id: Mapped[int] = mapped_column(BigInteger(), primary_key=True) # Ticking time bomb, in roughly fifteen years this'll break if this is still around then I wish the dev all the best. 
                                                                          # (doing something like this first should fix it tho: id = id if id < 2^63 else -(id&(2^63-1)) its not ideal but unless SQL now supports unsigned types its the best your gonna get )
    economy_id = mapped_column(ForeignKey("economies.economy_id"))
    
    economy: Mapped[Economy] = relationship(back_populates="guilds")



class MCDiscordMap(Base):
    __tablename__ = 'mcdiscordlink'
    user_id: Mapped[int] = mapped_column(BigInteger(), primary_key = True)
    mc_token: Mapped[str] = mapped_column(String(22), primary_key = True)


class Application(Base):
    __tablename__ = 'applications'
    application_id: Mapped[UUID] = mapped_column(primary_key=True)
    application_name: Mapped[str] = mapped_column(String(64))
    owner_id: Mapped[int] = mapped_column(BigInteger())
    economy_id = mapped_column(ForeignKey("economies.economy_id"))
    api_keys: Mapped[List["APIKey"]] = relationship(back_populates="application")
    economy: Mapped[Economy] = relationship(back_populates="applications")


class KeyType(Enum):
    GRANT = 0 # To be used for user issued keys
    MASTER = 1 # To be used for application master keys


class APIKey(Base):
    __tablename__ = 'api_keys'
    key_id: Mapped[int] = mapped_column(INT(), primary_key=True, autoincrement=True) # using an int datatype to ensure that the id will not clash with any discord snowflakes (any discord id created after 2015-1-1-0:0:1.024 should not clash) https://discord.com/developers/docs/reference#snowflakes
    application_id = mapped_column(ForeignKey("applications.application_id", ondelete='CASCADE'))
    internal_app_id: Mapped[UUID] = mapped_column(nullable=True)
    issuer_id: Mapped[int] = mapped_column(BigInteger(), nullable=False)
    spending_limit: Mapped[int] = mapped_column(nullable=True)
    spent_to_date: Mapped[int] = mapped_column(nullable=True, default=0)
    type: Mapped[KeyType] = mapped_column(default=KeyType.GRANT)
    enabled: Mapped[bool] = mapped_column(default=False)
    application: Mapped[Application] = relationship(back_populates="api_keys")

    def activate(self):
        self.enabled = True

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
    deleted: Mapped[bool] = mapped_column(default=False)
    
    economy: Mapped[Economy] = relationship(back_populates="accounts")
    update_notifiers: Mapped[List["BalanceUpdateNotifier"]] = relationship(back_populates='account')


    def get_update_notifiers(self):
        return [i.owner_id for i in self.update_notifiers] + [self.owner_id,]

    def get_balance(self) -> str:
        """This method should be used to avoid any weird floating point shenanigans when calculating the balance"""
        return frmt(self.balance)

    def get_name(self) -> str:
        if self.account_type == AccountType.USER:
            return f'<@{self.owner_id}>'
        return self.account_name

    def delete(self):
        self.deleted = True



class Transaction(Base):
    """A class used to represent transactions stored in the database"""
    __tablename__ = 'transactions'
    transaction_id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int] = mapped_column(BigInteger(), nullable=False)
    timestamp: Mapped[DateTime] = mapped_column(DateTime(), nullable=False, default=datetime.now)
    action: Mapped[Actions] = mapped_column()
    cud: Mapped[CUD] = mapped_column() # denotes the type of action taking place, can be either CREATE UPDATE or DELETE
    economy_id: Mapped[UUID] = mapped_column(nullable=True)
    target_account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.account_id"), nullable=True) # Transfers will use target_account as the source account for the transaction
    destination_account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.account_id"), nullable=True)
    amount: Mapped[int] = mapped_column(nullable=True)

    meta: Mapped[dict[str, Any]] = mapped_column(default={}) # TODO: document this shit. 

    destination_account: Mapped[Account] = relationship(foreign_keys=[destination_account_id])
    target_account: Mapped[Account] = relationship(foreign_keys=[target_account_id])


    

    

class BalanceUpdateNotifier(Base):
    __tablename__ = 'balance_update_notifiers'
    notifier_id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(BigInteger(), nullable=False)
    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.account_id", ondelete="CASCADE"))
    account: Mapped[Account] = relationship(back_populates="update_notifiers")



class Permission(Base):
    """A class used to represent a permission as stored in the database"""
    __tablename__ = 'perms'
    entry_id: Mapped[UUID] = mapped_column(primary_key=True)
    account_id: Mapped[UUID] = mapped_column(ForeignKey('accounts.account_id'), nullable=True)
    user_id: Mapped[int] = mapped_column(BigInteger()) # can also be a role id or an api key id < 4194304, due to how discord works there are zero chances of a collision
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
    bracket_end: Mapped[int] = mapped_column(nullable=True)
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


def make_serializable(arg: Any):
    if isinstance(arg, UUID):
        return str(arg)
    elif isinstance(arg, Enum):
        return arg.name
    elif isinstance(arg, (tuple, list)):
        return [make_serializable(i) for i in arg]
    elif isinstance(arg, dict):
        new_dict = {}
        for k in arg.keys():
            new_dict[k] = make_serializable(arg[k])
        return new_dict
    else:
        return arg



class Backend:
    """A singleton used to call the backend database"""
    
    def __init__(self, path: str):
        self.engine = create_engine(path)
        self.session = Session(self.engine)
        Base.metadata.create_all(self.engine)

    def dump_accounts_csv(self, buf: StringIO):
        out_csv = csv.writer(buf, lineterminator='\n')

        columns = [column.name for column in inspect(Account).columns]
        out_csv.writerow(columns)

        extract_query = [getattr(Account, col) for col in columns]
        for mov in self.session.query(*extract_query):
            out_csv.writerow(mov)

        buf.seek(0)
        return buf

    def dump_transactions_csv(self, buf: StringIO):
        out_csv = csv.writer(buf, lineterminator='\n')

        columns = [column.name for column in inspect(Transaction).columns]
        out_csv.writerow(columns)

        extract_query = [getattr(Transaction, col) for col in columns]
        for mov in self.session.query(*extract_query):
            out_csv.writerow(mov)

        buf.seek(0)
        return buf

    async def tick(self):
        """
        Triggers a tick in the server
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
                    authorisor = await self.get_member(transfer.authorisor_id, transfer.from_account.economy.owner_guild_id)
                    if authorisor is None:
                        authorisor = StubUser(transfer.authorisor_id)
                    self.perform_transaction(authorisor, transfer.from_account, transfer.to_account, transfer.amount, transfer.transaction_type)
                    payments_left -= 1
                except BackendError as e:
                    logger.log(PRIVATE_LOG, f'Failed to perform recurring transaction of {frmt(transfer.amount)} from {transfer.from_account.account_name} to {transfer.to_account.account_name} due to : {e}')
                    self.notify_user(transfer.authorisor_id, "Your recurring transaction of {frmt(transfer.amount)} every {transfer.payment_interval/60/60/24}days to {transfer.to_account.account_name} was cancelled due to: {e}", "Failed Reccurring Transfer")
                    self.session.delete(transfer)
            else: # for those unfamiliar with for/else this is not executed if the loop breaks
                transfer.number_of_payments_left = payments_left
                transfer.last_payment_timestamp = tick_time

        self.session.commit()
        
        logger.log(PUBLIC_LOG, f'successfully performed tick')


    def _one_or_none(self, stmt):
        res = self.session.execute(stmt).one_or_none()
        return res if res is None else res[0]


    def get_permissions(self, user: Member, economy=None):
        perms = select(Permission).where(Permission.user_id.in_([user.id] + [r.id for r in user.roles]))
        if economy is not None:
            perms.where(Permission.economy == economy)
        return [i[0] for i in self.session.execute(perms).all()]

    def get_authable_accounts(self, user: Member, economy=None):
        stmt = (select(Account).distinct().join_from(Account, Permission, Account.account_id == Permission.account_id, isouter=True)
                .where(or_(Permission.user_id.in_([user.id] + [r.id for r in user.roles]),  Account.owner_id == user.id)))
        if economy is not None:
            stmt = stmt.where(Account.economy_id == economy.economy_id)

        return [i[0] for i in self.session.execute(stmt).all()]

    async def key_has_permission(self, key: APIKey, *args, **kwargs) -> bool:
        actor = await self.get_member(key.issuer_id, key.application.economy.owner_guild_id)
        return self.has_permission(StubUser(key.key_id), *args, **kwargs) and self.has_permission(actor, *args, **kwargs)

    def has_permission(self, user, permission: Permissions, account: Account = None, economy: Economy = None) -> bool:
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
        elif permission in DEFAULT_OWNER_PERMISSIONS and owner_id in [user.id] + [r.id for r in user.roles]:
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
            # Some more precedence rules
            # permissions registered to the user directly take priority over those registered to roles
            # and the higher the role in the discord ranking thing the higher the precedence
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

    """Discord Shit"""
    def notify_user(self, user_id, message, title, thumbnail=None):
        logger.warning("Backend failed to message user: {user_id}")

    def notify_users(self, user_ids, *args, **kwargs):
        for user_id in user_ids:
            self.notify_user(user_id, *args, **kwargs)

    async def get_member(self, user_id, guild_id):
        raise NotImplementedError()

    async def get_user_dms(self, user_id):
        raise NotImplementedError()

    def get_application(self, app_id):
        return self._one_or_none(select(Application).where(Application.application_id == app_id))

    def get_key(self, app: Application, ref_id: UUID) -> APIKey | None:
        return self._one_or_none(select(APIKey).where(APIKey.application == app).where(APIKey.internal_app_id == ref_id))

    def get_key_by_id(self, kid: int) -> APIKey | None:
        return self._one_or_none(select(APIKey).where(APIKey.key_id == kid))

    def initialize_key(self, app: Application, ref_id: UUID, issuer_id: int) -> APIKey:
        current_key = self.get_key(app, ref_id)
        if current_key is not None:
            self.session.delete(current_key)

        new_key = APIKey(application = app, internal_app_id=ref_id, issuer_id=issuer_id)
        self.session.add(new_key)
        return new_key



    def get_discord_id(self, mc_token):
        mc_ds_map = self._one_or_none(select(MCDiscordMap).where(MCDiscordMap.mc_token == mc_token))
        if mc_ds_map:
            return mc_ds_map.user_id
        return None

    def register_mc_token(self, user_id, mc_token):
        if len(mc_token) != 22:
            raise BackendError("Invalid mc token provided")

        current_id = self.get_discord_id(mc_token)
        if current_id is not None:
            raise BackendError("This minecraft account is already linked with a user account, contact an admin if you believe this is in error")

        current_map = self._one_or_none(select(MCDiscordMap).where(MCDiscordMap.user_id == user_id))
        if current_map is not None:
            self.session.delete(current_map)

        new_map = MCDiscordMap(user_id = user_id, mc_token = mc_token)
        self.session.add(new_map)
        self.session.commit()


    """Taxes"""


    def get_tax_bracket(self, tax_name, economy):
        return self._one_or_none(select(Tax).where(Tax.tax_name==tax_name).where(Tax.economy_id == economy.economy_id))


    def get_tax_brackets(self, economy):
        return self.session.execute(select(Tax).where(Tax.economy_id == economy.economy_id)).all()


    def create_tax_bracket(self, user: Member, tax_name: str, affected_type: AccountType, tax_type: TaxType, bracket_start: int, bracket_end: int, rate: int, to_account: Account):
        if not self.has_permission(user, Permissions.MANAGE_TAX_BRACKETS, economy=to_account.economy):
            raise BackendError("You do not have permission to create tax brackets in this economy")

        if self.get_tax_bracket(tax_name, to_account.economy) is not None:
            raise BackendError("A tax bracket of that name already exists in this economy")

        kwargs = {
            "entry_id": uuid4(),
            "tax_name": tax_name,
            "affected_type": affected_type,
            "tax_type": tax_type,
            "bracket_start": bracket_start,
            "bracket_end": bracket_end,
            "rate": rate,
            "to_account_id": to_account.account_id,
            "economy_id": to_account.economy.economy_id
        }
        tax_bracket = Tax(**kwargs)
        self.session.add(tax_bracket)
        logger.log(PUBLIC_LOG, f"Economy: {to_account.economy.currency_name}\n{user.mention} created a new tax bracket by the name {tax_name}")


        
    

        self.session.add(Transaction(
            actor_id=user.id, 
            action=Actions.UPDATE_TAX_BRACKETS, 
            cud=CUD.CREATE, 
            economy_id=to_account.economy.economy_id, 
            destination_account_id = to_account.account_id,
            meta = make_serializable(kwargs)
        ))
        self.session.commit()
        return tax_bracket




    def delete_tax_bracket(self, user: Member, tax_name: str, economy: Economy):
        if not self.has_permission(user, Permissions.MANAGE_TAX_BRACKETS, economy=economy):
            raise BackendError("You do not have permission to create tax brackets in this economy")

        tax_bracket = self.get_tax_bracket(tax_name, economy)
        tax_bracket_id = tax_bracket.entry_id
        if tax_bracket is None:
            raise BackendError("No tax bracket of that name exists in this economy")

        self.session.delete(tax_bracket)
        logger.log(PUBLIC_LOG, f"Economy: {tax_bracket.economy.currency_name}\n {user.mention} deleted the tax bracket {tax_name}")
        self.session.add(Transaction(
            actor_id = user.id,
            action=Actions.UPDATE_TAX_BRACKETS,
            cud=CUD.DELETE,
            economy_id=economy.economy_id,
            meta = make_serializable({
                "entry_id": tax_bracket_id,
                "tax_name": tax_name
            })
        ))

        self.session.commit()



    def _perform_transaction_tax(self, amount: int, transaction: Transaction, economy: Economy) -> int:
        """Performs taxation and returns the total amount of tax taken"""
        vat_taxes = self.session.execute(select(Tax).where(Tax.tax_type==TaxType.VAT)
                                         .where(Tax.economy_id==economy.economy_id)
                                         .where(Tax.affected_type == self.get_account_by_id(transaction.target_account_id).account_type)
                                         .order_by(Tax.bracket_start.desc())).all()
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


    def perform_tax(self, user:Member, economy: Economy):
        if not self.has_permission(user, Permissions.MANAGE_TAX_BRACKETS, economy=economy):
            raise BackendError("You do not have permission to trigger taxes in this economy")
        
        wealth_taxes = self.session.execute(
            select(Tax)
            .where(
                Tax.tax_type==TaxType.WEALTH,
                Tax.economy_id==economy.economy_id
            ).order_by(Tax.bracket_start.desc())
        ).scalars()
        
        for wealth_tax in wealth_taxes:
            print(wealth_tax.tax_name, wealth_tax.bracket_start, wealth_tax.bracket_end)
            
            accumulated_tax = 0
            full_tax = ((wealth_tax.bracket_end - wealth_tax.bracket_start)*wealth_tax.rate)//100

            accum = self._one_or_none(
                                select(func.sum(((Account.balance-wealth_tax.bracket_start)*wealth_tax.rate)//100))
                                .select_from(Account)
                                .where(
                                    Account.account_type == wealth_tax.affected_type,
                                    Account.balance >= wealth_tax.bracket_start,
                                    Account.balance < wealth_tax.bracket_end
                                ))

            print(accum)

            accumulated_tax += accum if accum is not None else 0
            self.session.execute(update(Account)
                .where(
                    Account.account_type == wealth_tax.affected_type,
                    Account.balance >= wealth_tax.bracket_start,
                    Account.balance < wealth_tax.bracket_end
                )
                .values(balance=Account.balance-(((Account.balance-wealth_tax.bracket_start)*wealth_tax.rate)//100))
            )

            # accum = self._one_or_none(select(func.count()).select_from(Account).where(Account.account_type == wealth_tax.affected_type).where(Account.balance >= wealth_tax.bracket_end))
            # accumulated_tax += (accum if accum is not None else 0)*full_tax
            # self.session.execute(update(Account).where(Account.account_type == wealth_tax.affected_type).where(Account.balance >= wealth_tax.bracket_end).values(balance=(Account.balance - full_tax)))
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
                        .where(Account.economy_id == income_tax.economy_id)
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
                logger.log(PRIVATE_LOG, f'Economy: {debtor.economy.currency_name}\n{debtor.account_name} failed to meet their tax obligations and still owe {frmt(debt)}')
            self.session.execute(update(Account).values(income_to_date=0))
            income_tax.to_account.balance += accumulated_tax

        logger.log(PUBLIC_LOG, f'Economy: {economy.currency_name}\n {user.mention} triggered a tax cycle')
        
        self.session.add(Transaction(
            actor_id = user.id,
            action = Actions.PERFORM_TAXES,
            cud = CUD.UPDATE,
            economy_id = economy.economy_id,
        ))

        self.session.commit()


    """Permissions"""

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

    

    def toggle_ephemeral(self, actor: Member):
        self._change_permission(actor.id, Permissions.USES_EPHEMERAL, None, None, not self.has_permission(actor, Permissions.USES_EPHEMERAL))
        self.session.commit() 


    def reset_permission(self, actor: Member, affected_id:int, permission:Permissions, account: Account = None, economy: Economy = None):
        if not self.has_permission(actor, Permissions.MANAGE_PERMISSIONS,  economy=economy):
            raise BackendError("You do not have permission to manage permissions here")

        self._reset_permission(affected_id, permission, account, economy)
        self.session.add(Transaction(
            actor_id=actor.id,
            economy_id = economy.economy_id if economy is not None else None,
            target_account_id = account.account_id if account is not None else None,
            action = Actions.UPDATE_PERMISSIONS,
            cud = CUD.DELETE,
            meta = {
                "affected_id": affected_id,
                "affected_permission": "ALL"
            }
        ))
        self.session.commit()


    def change_permissions(self, actor: Member, affected_id: int, permission: Permissions, account: Account = None, economy: Economy = None, allowed: bool = True):
        if not self.has_permission(actor, Permissions.MANAGE_PERMISSIONS, economy=economy):
            raise BackendError("You do not have permission to manage permissions here")
        self._change_permission(affected_id, permission, account, economy, allowed)
        self.session.add(Transaction(
            actor_id = actor.id,
            action = Actions.UPDATE_PERMISSIONS,
            cud = CUD.UPDATE,
            economy_id=economy.economy_id if economy is not None else None,
            target_account_id = account.account_id if account is not None else None,
            meta = make_serializable({
                "affected_id": affected_id,
                "permissions": [permission],
                "allowed": allowed
            })
        ))
        self.session.commit()

    def change_many_permissions(self, actor: Member, affected_id: int, *permissions, account: Account = None, economy: Economy = None, allowed: bool = True):
        if not self.has_permission(actor, Permissions.MANAGE_PERMISSIONS, economy=economy):
            raise BackendError("You do not have permission to manage permissions here")
        for permission in permissions:
            self._change_permission(affected_id, permission, account, economy, allowed)
        self.session.add(Transaction(
            actor_id = actor.id,
            action = Actions.UPDATE_PERMISSIONS,
            cud = CUD.UPDATE,
            economy_id =  economy.economy_id if economy is not None else None,
            target_account_id = account.account_id if account is not None else None,
            meta = make_serializable({
                "affected_id": affected_id,
                "permissions": permissions,
                "allowed": allowed
            })
        ))
        self.session.commit()


    """Economies"""

    def get_economies(self):
        return [i[0] for i in self.session.execute(select(Economy)).all()]

    def create_economy(self, user: Member, currency_name: str, currency_unit: str) -> Economy:
        if not self.has_permission(user, Permissions.MANAGE_ECONOMIES):
            raise BackendError("You do not have permission to create economies")
        
        if self.get_economy_by_name(currency_name):
            raise BackendError("An economy by that name already exists")

        economy = Economy(economy_id=uuid4(), currency_name=currency_name, currency_unit=currency_unit, owner_guild_id = user.guild.id)
        
        if self.get_guild_economy(user.guild.id) is not None:
            raise BackendError("This guild is already registered to an economy")

        self.session.add(Guild(guild_id=user.guild.id, economy_id=economy.economy_id))
        self.session.add(economy)
        self.change_many_permissions(StubUser(0), user.id, Permissions.MANAGE_PERMISSIONS, economy=economy)

        self.session.commit()
        logger.log(PUBLIC_LOG, f'{user.mention} created the economy {currency_name}')
        self.session.add(Transaction(
            actor_id = user.id,
            action = Actions.UPDATE_ECONOMIES,
            cud = CUD.CREATE,
            economy_id = economy.economy_id
        ))
        return economy


    def get_economy_by_name(self, name: str):
        return self._one_or_none(select(Economy).where(Economy.currency_name == name))
        

    def get_economy_by_id(self, economy_id: UUID):
        return self._one_or_none(select(Economy).where(Economy.economy_id == economy_id))

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
            raise BackendError("This guild is the owner guild of an economy, cannot change the economy its registered to")
        guild = self.session.get(Guild, guild_id)
        self.session.delete(guild)
        self.session.commit()
    

    def get_guild_economy(self, guild_id: int) -> Optional[Economy]:
        guild = self.session.get(Guild, guild_id)
        return None if guild is None else guild.economy

    @staticmethod
    def get_guild_ids(economy: Economy) -> List[int]:
        return [i.guild_id for i in economy.guilds]

    def delete_economy(self, user: Member, economy: Economy) -> None:
        econ_id = economy.economy_id if economy is not None else None
        if not self.has_permission(user, Permissions.MANAGE_ECONOMIES, economy=economy):
            raise BackendError("You do not have permission to delete this economy")
        self.session.execute(delete(Guild).where(Guild.economy_id == economy.economy_id))
        
        self.session.delete(economy)
        self.session.add(Transaction(
            actor_id = user.id,
            action = Actions.UPDATE_ECONOMIES,
            cud = CUD.DELETE,
            economy_id = econ_id
        ))
        self.session.commit()

    """Accounts"""

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
        elif name is not None and (acc := self.get_account_by_name(name, economy)) is not None:
            raise BackendError(f"Account with name {name} already exists")
            
        account = Account(account_id=uuid4(), account_name=name, owner_id=owner_id, account_type=account_type, balance=0, economy=economy)
        self.session.add(account)
        self.session.add(Transaction(
            actor_id = authorisor.id,
            economy_id = economy.economy_id if economy is not None else None,
            action = Actions.UPDATE_ACCOUNTS,
            cud = CUD.CREATE,
            meta = make_serializable({
                "account_type": account_type,
                "owner_id": owner_id
            })
        ))      

        self.session.commit()
        return account

    def transfer_ownership(self, authorisor: User | Member, account: Account, new_owner_id: int):
        '''
        Transfers the ownership of an account from one user to another.
        :param authorisor: The initiator of this procedure.
        :param account: The account whose ownership will be transferred.
        :param new_owner_id: The Discord user ID of the new owner.
        :returns: The account with the new changes.
        '''

        if not self.has_permission(authorisor, Permissions.CLOSE_ACCOUNT, account=account):
            raise BackendError("You do not have the permission to transfer the ownership of this account.")

        old_owner_id = account.owner_id
        try:
            account.owner_id = new_owner_id

            self.session.add(Transaction(
                actor_id = authorisor.id,
                economy_id = account.economy.economy_id,
                target_account_id = account.account_id,
                action = Actions.UPDATE_ACCOUNTS,
                cud = CUD.UPDATE,
                meta = make_serializable({
                    "old_owner_id": old_owner_id,
                    "new_owner_id": new_owner_id
                })
            ))
            
            self.session.commit()
        except Exception as e:
            self.session.rollback()
            raise BackendError(f"Could not transfer account ownership: {e}.")
        else:
            return account

    def delete_account(self, authorisor: Member, account):
        if not self.has_permission(authorisor, Permissions.CLOSE_ACCOUNT, account=account, economy=account.economy):
            raise BackendError("You do not have permission to close this account")
        acc_id = account.account_id
        econ_id = account.economy.economy_id
        account.deleted = True
        self.session.add(Transaction(
            actor_id = authorisor.id,
            economy_id = econ_id,
            target_account_id = acc_id,
            action = Actions.UPDATE_ACCOUNTS,
            cud = CUD.DELETE
        ))
        self.session.commit()

    def get_user_account(self, user_id: int, economy: Economy) -> Account | None:
        return self._one_or_none(select(Account).where(Account.owner_id == user_id).where(Account.account_type == AccountType.USER).where(Account.economy_id == economy.economy_id).where(Account.deleted==False))

    def get_account_by_name(self, account_name: str, economy: Economy) -> Account | None:
        return self._one_or_none(select(Account).where(Account.account_name == account_name).where(Account.economy_id == economy.economy_id).where(Account.deleted==False))

    def get_account_by_id(self, account_id: UUID) -> Account | None:
        return self._one_or_none(select(Account).where(Account.account_id == account_id))



    """Transfers"""


    def get_transaction_log(self, user: Member, account: Account, limit=None): 
        if not self.has_permission(user, Permissions.VIEW_BALANCE, account=account):
            raise BackendError("You do not have permissions to view the transaction log on this account")
        stmt = select(Transaction).where((Transaction.target_account_id == account.account_id) | (Transaction.destination_account_id == account.account_id)).where(Transaction.action == Actions.TRANSFER).order_by(Transaction.timestamp.desc())
        stmt = stmt.limit(limit)
        r = self.session.execute(stmt)
        results = [i[0] for i in r.all()]
        return results
    

    
    def create_recurring_transfer(self, user: Member, from_account: Account, to_account: Account, amount: int, payment_interval: int, number_of_payments: int = None, transaction_type: TransactionType = TransactionType.INCOME) -> None:
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

    def subscribe(self, user, account):
        if not self.has_permission(user, Permissions.VIEW_BALANCE, account=account):
            raise BackendError("You do not have permissions to subscribe to transaction_notifs for this account")
        self.unsubscribe(user, account)
        self.session.add(BalanceUpdateNotifier(notifier_id = uuid4(), owner_id = user.id, account_id = account.account_id))
        self.session.commit()

    def unsubscribe(self, user, account):
        [self.session.delete(notifier) for notifier in account.update_notifiers if notifier.owner_id == user.id]
        self.session.commit()

        
        
    def perform_transaction(self, user: Member, from_account: Account, to_account: Account, amount: int, transaction_type: TransactionType = TransactionType.PERSONAL):
        """Performs a transaction from one account to another accounting for tax, returns a boolean indicating if the transaction was successful"""
        if not self.has_permission(user, Permissions.TRANSFER_FUNDS, account=from_account, economy=from_account.economy):
            raise BackendError("You do not have permission to transfer funds from that account")

        if from_account.economy_id != to_account.economy_id:
            raise BackendError("Cannot transfer funds from one economy to another")

        if from_account.balance < amount:
            raise BackendError("You do not have sufficient funds to transfer from that account")

        if from_account.account_id == to_account.account_id:
            return 

        transaction = Transaction(
            actor_id=user.id,
            economy_id=from_account.economy_id,
            target_account_id=from_account.account_id,
            destination_account_id=to_account.account_id,
            action=Actions.TRANSFER,
            cud=CUD.UPDATE,
            amount=amount
        )

        if transaction_type == TransactionType.INCOME:
            to_account.income_to_date += amount
        from_account.balance -= amount
        amount -= self._perform_transaction_tax(amount, transaction, from_account.economy)
        to_account.balance += amount


        log = PRIVATE_LOG
        if self.has_permission(user, Permissions.GOVERNMENT_OFFICIAL, economy=from_account.economy):
            log = PUBLIC_LOG
        logger.log(log, f"Economy: {from_account.economy.currency_name}\n{user.mention} transferred {frmt(amount)} from {from_account.account_name} to {to_account.account_name}")
        self.session.add(transaction)

        self.notify_users(to_account.get_update_notifiers(), f"{user.mention} transferred {frmt(amount)} from {from_account.account_name} to {to_account.account_name}, \n it\'s new balance is {to_account.get_balance()}", "Balance Update")
        self.notify_users(from_account.get_update_notifiers(), f'{user.mention} transferred {frmt(amount)} from an account you watch ({from_account.account_name}), to {to_account.account_name} \n {from_account.account_name}\'s new balance is {from_account.get_balance()}', "Balance Update")
        self.session.commit()

    def print_money(self, user: Member, to_account: Account, amount: int):
        if not self.has_permission(user, Permissions.MANAGE_FUNDS, account=to_account, economy=to_account.economy):
            raise BackendError("You do not have permission to print funds")
        to_account.balance += amount
        logger.log(PUBLIC_LOG, f'Economy: {to_account.economy.currency_name}\n{user.mention} printed {frmt(amount)} to {to_account.account_name}')
        self.session.add(Transaction(
            actor_id = user.id,
            economy_id = to_account.economy.economy_id,
            destination_account_id = to_account.account_id,
            action=Actions.MANAGE_FUNDS,
            cud=CUD.CREATE,
            amount=amount
        ))
        self.notify_users(to_account.get_update_notifiers(), f'{user.mention} printed {frmt(amount)} to {to_account.account_name},\n it\'s new balance is {to_account.get_balance()}', "Balance Update")
        self.session.commit()

    def remove_funds(self, user: Member, from_account: Account, amount: int):
        if not self.has_permission(user, Permissions.MANAGE_FUNDS, account=from_account, economy=from_account.economy):
            raise BackendError("You do not have permission to remove funds")
        if from_account.balance < amount:
            raise BackendError("There are not sufficient funds in this account to perform this action")
        from_account.balance -= amount
        logger.log(PUBLIC_LOG, f'Economy: {from_account.economy.currency_name}\n {user.mention} removed {frmt(amount)} from {from_account.account_name}')
        self.session.add(Transaction(
            actor_id = user.id,
            action = Actions.MANAGE_FUNDS,
            cud = CUD.DELETE,
            target_account_id = from_account.account_id,
            economy_id = from_account.economy.economy_id,
            amount = amount
        ))
        self.notify_users(from_account.get_update_notifiers(), f'{user.mention} removed {frmt(amount)} from {from_account.account_name},\n it\'s new balance is {from_account.get_balance()}', "Balance Update")
        self.session.commit()

    def delete_key(self, key):
        self.session.execute(Delete(Permission).where(Permission.user_id == key.key_id))
        self.session.delete(key)
        self.session.commit()

