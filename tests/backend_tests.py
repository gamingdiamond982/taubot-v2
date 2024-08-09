#!/usr/bin/env python3
import sys
import unittest
import time
import datetime
from os import path
import asyncio

from discord_utils import *

sys.path.append(path.join(path.dirname(path.dirname(path.abspath(__file__))), 'src'))

from middleman import *
from backend import *

logger.setLevel(100) # shut that thing up

guild_id = 554769523635650580
other_guild_id = 1236137485554155612

user_id = 529676139837521920
other_user_id = 646434492101165068
admin_id = 0




    
        

bot = StubBot()






simdem = StubGuild(guild_id, [], [])
guilds[guild_id] = simdem

other_guild = StubGuild(other_guild_id, [], [])
guilds[other_guild_id] = other_guild


def add_member(user_id, roles = None, guild=simdem):
    user = StubMember(user_id, [] if roles is None else roles, guild)
    guild.members.append(simdem)
    return user

admin = add_member(0)




def create_test_backend(path=":memory:"):
    return DiscordBackendInterface(bot, f"sqlite:///{path}") # This is for testing purposes only in production a postgresql backend should be used instead

class BackendTests(unittest.TestCase):

    def test_create_and_delete_economy(self):
        backend = create_test_backend()
        self.assertEqual(backend.get_guild_economy(guild_id), None)
        self.assertEqual(backend.get_economy_by_name('tau'), None)
        test_economy = backend.create_economy(admin, 'tau', 't')
        self.assertEqual(backend.get_economy_by_name('tau'), test_economy)
        
        self.assertEqual(backend.get_guild_economy(guild_id), test_economy)
        self.assertEqual(backend.get_guild_economy(other_guild_id), None)
        
        backend.register_guild(admin, other_guild_id, test_economy)

        self.assertEqual(backend.get_guild_economy(other_guild_id), test_economy)
        backend.delete_economy(admin, test_economy)
        self.assertEqual(backend.get_economy_by_name('tau'), None)
        
        test_economy = backend.create_economy(admin, 'euro', 'e')       

        self.assertEqual(backend.get_guild_economy(guild_id), test_economy)
        
        
        
        

    def test_open_and_close_account(self):
        backend = create_test_backend()
        econ = backend.create_economy(admin, 'tau', 't')
        user = add_member(user_id)
        self.assertEqual(backend.get_user_account(user_id, econ), None)
        acc = backend.create_account(user, user_id, econ)
        self.assertEqual(backend.get_user_account(user_id, econ), acc)
        
        # Testing opening multiple accounts
        self.assertRaises(BackendError, lambda : backend.create_account(user, user_id, econ))

        admin_other_guild = add_member(0, guild=other_guild)
        econ2 = backend.create_economy(admin_other_guild, 'USD', '$')

        # ensure we can still open user accounts in other economes
        acc2 = backend.create_account(user, user_id, econ2)

        # Ensure non-admins can't close other accounts
        other_user = add_member(other_user_id)
        self.assertRaises(BackendError, lambda : backend.delete_account(other_user, acc))

        backend.delete_account(user, acc)

        self.assertEqual(backend.get_user_account(user_id, econ), None)
        self.assertEqual(backend.get_user_account(user_id, econ2), acc2)


    def test_transfer_funds(self):
        backend = create_test_backend()
        econ = backend.create_economy(admin, 'tau', 't')
        user = add_member(user_id)
        from_acc = backend.create_account(user, user_id, econ)
        other_user = add_member(other_user_id)
        to_acc   = backend.create_account(other_user, other_user_id, econ)

        backend.print_money(admin, from_acc, 100)

        self.assertEqual(backend.get_user_account(user_id, econ).balance, 100)

        backend.perform_transaction(user, from_acc, to_acc, 50)
        
        self.assertEqual(backend.get_user_account(user_id, econ).balance, 50)
        self.assertEqual(backend.get_user_account(other_user_id, econ).balance, 50)

        self.assertRaises(BackendError, lambda : backend.perform_transaction(other_user, from_acc, to_acc, 10))

        self.assertRaises(BackendError, lambda : backend.perform_transaction(user, from_acc, to_acc, 100))

        self.assertRaises(BackendError, lambda : backend.remove_funds(other_user, from_acc, 10))
        backend.remove_funds(admin, from_acc, 50)
        
        self.assertEqual(backend.get_user_account(user_id, econ).balance, 0)

        self.assertRaises(BackendError, lambda : backend.remove_funds(admin, from_acc, 10))
        
        
    

    
    def test_permissions(self):
        backend = create_test_backend()
        econ = backend.create_economy(admin, 'tau', 't')
        other_user = add_member(other_user_id)
        user = add_member(user_id)


        self.assertTrue(backend.has_permission(user, Permissions.OPEN_ACCOUNT, economy=econ))
        self.assertFalse(backend.has_permission(user, Permissions.MANAGE_FUNDS, economy=econ))
        acc = backend.create_account(user, user_id, econ)
        self.assertTrue(backend.has_permission(user, Permissions.TRANSFER_FUNDS, account=acc, economy=econ))
        self.assertFalse(backend.has_permission(other_user, Permissions.TRANSFER_FUNDS, account=acc, economy=econ))

        backend.change_permissions(admin, other_user_id, Permissions.TRANSFER_FUNDS, economy=econ, allowed=True)

        self.assertTrue(backend.has_permission(other_user, Permissions.TRANSFER_FUNDS, account=acc, economy=econ))

        # since other_user_id has permission to transfer_funds on all accounts in the economy this should do nothing        
        backend.change_permissions(admin, other_user_id, Permissions.TRANSFER_FUNDS, account=acc, economy=econ, allowed=False)

        self.assertTrue(backend.has_permission(other_user, Permissions.TRANSFER_FUNDS, account=acc, economy=econ))

        backend.reset_permission(admin, other_user_id, Permissions.TRANSFER_FUNDS, economy=econ)

        self.assertFalse(backend.has_permission(other_user, Permissions.TRANSFER_FUNDS, account=acc, economy=econ))

        backend.change_permissions(admin, user_id, Permissions.TRANSFER_FUNDS, allowed=False)
        
        self.assertFalse(backend.has_permission(user, Permissions.TRANSFER_FUNDS, account=acc, economy=econ))
        
    def test_recurring_transfers(self):
        backend = create_test_backend()
        econ = backend.create_economy(admin, 'tau', 't')
        user = add_member(user_id)
        other_user = add_member(other_user_id)
        from_acc = backend.create_account(user, user_id, econ)
        to_acc = backend.create_account(other_user, other_user_id, econ)
        backend.print_money(admin, from_acc, 1000)
        backend.create_recurring_transfer(user, from_acc, to_acc, 10, 60*60*24, 10)
        
        self.assertEqual(backend.get_user_account(user_id, econ).balance, 990)
        old_time_func = time.time
        time.time = lambda: old_time_func() + 60*60 # monkey patching the time function so that we can time travel
        l = asyncio.get_event_loop()

        l.run_until_complete(backend.tick())
        self.assertEqual(backend.get_user_account(user_id, econ).balance, 990)
        time.time = lambda: old_time_func() + 60*60*24

        l.run_until_complete(backend.tick())
        
        self.assertEqual(backend.get_user_account(user_id, econ).balance, 980)

        time.time = lambda: old_time_func() + 60*60*24*7 # testing what would happen if the bot was left offline for a while

        l.run_until_complete(backend.tick())
    
        self.assertEqual(backend.get_user_account(user_id, econ).balance, 920)
    
        time.time = lambda: old_time_func() + 60*60*24*12 # making sure the bot stops when it's meant too   
            
        l.run_until_complete(backend.tick())
        self.assertEqual(backend.get_user_account(user_id, econ).balance, 900)

    def test_taxes(self):
        backend = create_test_backend()
        econ = backend.create_economy(admin, 'tau', 't')
        gov = backend.create_account(admin, admin.id, econ, 'government', AccountType.GOVERNMENT)
        test_tax = backend.create_tax_bracket(admin, 'test_tax_1', AccountType.USER, TaxType.WEALTH, 1000, 2000, 10, gov)
        
        backend.perform_tax(admin, econ)

        user = add_member(user_id)
        test_acc = backend.create_account(user, user_id, econ)
        backend.print_money(admin, test_acc, 2000)
        backend.perform_tax(admin, econ)

        self.assertEqual(backend.get_user_account(user_id, econ).balance, 1900)

        self.assertEqual(gov.balance, 100)
        backend.perform_tax(admin, econ)

        self.assertEqual(backend.get_user_account(user_id, econ).balance, 1810)

        self.assertEqual(gov.balance, 190)


        backend.delete_tax_bracket(admin, 'test_tax_1', econ)


        test_tax = backend.create_tax_bracket(admin, 'test_tax_2', AccountType.USER, TaxType.INCOME, 1000, 2000, 10, gov)
        
        other_user = add_member(other_user_id)
#       test_acc_2 = backend.create_account(other_user, other_user_id, 

        





    
        
        
        

        

        
        






