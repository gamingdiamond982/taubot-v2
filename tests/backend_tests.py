#!/usr/bin/env python3
import sys
import unittest
import time
import datetime
from os import path


sys.path.append(path.join(path.dirname(path.dirname(path.abspath(__file__))), 'src'))

from backend import *

logger.setLevel(100) # shut that thing up

guild_id = 554769523635650580
user_id = 529676139837521920
other_user_id = 646434492101165068
admin_id = 0


def create_test_backend():
	return Backend("sqlite:///:memory:") # This is for testing purposes only in production a postgresql backend should be used instead



class BackendTests(unittest.TestCase):

	def test_create_and_delete_economy(self):
		backend = create_test_backend()
		self.assertEqual(backend.get_guild_economy(guild_id), None)
		self.assertEqual(backend.get_economy_by_name('tau'), None)
		test_economy = backend.create_economy(admin_id, 'tau', 't')
		self.assertEqual(backend.get_economy_by_name('tau'), test_economy)
		
		backend.register_guild(admin_id, guild_id, test_economy)
		
		self.assertEqual(backend.get_guild_economy(guild_id), test_economy)
		backend.unregister_guild(admin_id, guild_id)
		self.assertEqual(backend.get_guild_economy(guild_id), None)
		
		backend.register_guild(admin_id, guild_id, test_economy)
		backend.delete_economy(admin_id, test_economy)
		self.assertEqual(backend.get_economy_by_name('tau'), None)
		
		test_economy = backend.create_economy(admin_id, 'euro', 'e')		
		backend.register_guild(admin_id, guild_id, test_economy)

		self.assertEqual(backend.get_guild_economy(guild_id), test_economy)
		



	def test_open_and_close_account(self):
		backend = create_test_backend()
		econ = backend.create_economy(admin_id, 'tau', 't')

		self.assertEqual(backend.get_user_account(user_id, econ), None)
		acc = backend.create_account(user_id, user_id, econ)
		self.assertEqual(backend.get_user_account(user_id, econ), acc)
		
		# Testing opening multiple accounts		
		self.assertRaises(Exception, lambda : backend.create_account(user_id, user_id, econ))

		econ2 = backend.create_economy(admin_id, 'USD', '$')

		# ensure we can still open user accounts in other economes
		acc2 = backend.create_account(user_id, user_id, econ2)

		# Ensure non-admins can't close other accounts
		self.assertRaises(Exception, lambda : backend.delete_account(other_user_id, acc))

		backend.delete_account(user_id, acc)

		self.assertEqual(backend.get_user_account(user_id, econ), None)
		self.assertEqual(backend.get_user_account(user_id, econ2), acc2)


	def test_transfer_funds(self):
		backend = create_test_backend()
		econ = backend.create_economy(admin_id, 'tau', 't')
		from_acc = backend.create_account(user_id, user_id, econ)
		to_acc   = backend.create_account(other_user_id, other_user_id, econ)

		backend.print_money(admin_id, from_acc, 100)

		self.assertEqual(backend.get_user_account(user_id, econ).balance, 100)

		backend.perform_transaction(user_id, from_acc, to_acc, 50)
		
		self.assertEqual(backend.get_user_account(user_id, econ).balance, 50)
		self.assertEqual(backend.get_user_account(other_user_id, econ).balance, 50)

		self.assertRaises(Exception, lambda : backend.perform_transaction(other_user_id, from_acc, to_acc, 10))

		self.assertRaises(Exception, lambda : backend.perform_transaction(user_id, from_acc, to_acc, 100))

		self.assertRaises(Exception, lambda : backend.remove_funds(other_user_id, from_acc, 10))
		backend.remove_funds(admin_id, from_acc, 50)
		
		self.assertEqual(backend.get_user_account(user_id, econ).balance, 0)

		self.assertRaises(Exception, lambda : backend.remove_funds(admin_id, from_acc, 10))
		
		
	

	
	def test_permissions(self):
		backend = create_test_backend()
		econ = backend.create_economy(admin_id, 'tau', 't')
		self.assertTrue(backend.has_permission(user_id, Permissions.OPEN_ACCOUNT, economy=econ))
		self.assertFalse(backend.has_permission(user_id, Permissions.MANAGE_FUNDS, economy=econ))
		acc = backend.create_account(user_id, user_id, econ)
		self.assertTrue(backend.has_permission(user_id, Permissions.TRANSFER_FUNDS, account=acc, economy=econ))
		self.assertFalse(backend.has_permission(other_user_id, Permissions.TRANSFER_FUNDS, account=acc, economy=econ))

		backend.change_permissions(admin_id, other_user_id, Permissions.TRANSFER_FUNDS, economy=econ, allowed=True)

		self.assertTrue(backend.has_permission(other_user_id, Permissions.TRANSFER_FUNDS, account=acc, economy=econ))

		# since other_user_id has permission to transfer_funds on all accounts in the economy this should do nothing		
		backend.change_permissions(admin_id, other_user_id, Permissions.TRANSFER_FUNDS, account=acc, economy=econ, allowed=False)

		self.assertTrue(backend.has_permission(other_user_id, Permissions.TRANSFER_FUNDS, account=acc, economy=econ))

		backend.reset_permission(admin_id, other_user_id, Permissions.TRANSFER_FUNDS, economy=econ)

		self.assertFalse(backend.has_permission(other_user_id, Permissions.TRANSFER_FUNDS, account=acc, economy=econ))

		backend.change_permissions(admin_id, user_id, Permissions.TRANSFER_FUNDS, allowed=False)
		
		self.assertFalse(backend.has_permission(user_id, Permissions.TRANSFER_FUNDS, account=acc, economy=econ))
		
		
	def test_recurring_transfers(self):
		backend = create_test_backend()
		econ = backend.create_economy(admin_id, 'tau', 't')
		from_acc = backend.create_account(user_id, user_id, econ)
		to_acc = backend.create_account(other_user_id, other_user_id, econ)
		backend.print_money(admin_id, from_acc, 1000)
		backend.create_recurring_transfer(user_id, from_acc, to_acc, 10, 60*60*24, 10)
		
		self.assertEqual(backend.get_user_account(user_id, econ).balance, 990)
		old_time_func = time.time
		time.time = lambda: old_time_func() + 60*60 # monkey patching the time function so that we can time travel
		backend.tick()
		self.assertEqual(backend.get_user_account(user_id, econ).balance, 990)
		time.time = lambda: old_time_func() + 60*60*24
		backend.tick()
		self.assertEqual(backend.get_user_account(user_id, econ).balance, 980)

		time.time = lambda: old_time_func() + 60*60*24*7 # testing what would happen if the bot was left offline for a while

		backend.tick()
	
		self.assertEqual(backend.get_user_account(user_id, econ).balance, 920)
	
		time.time = lambda: old_time_func() + 60*60*24*12 # making sure the bot stops when it's meant too	
		backend.tick()
		self.assertEqual(backend.get_user_account(user_id, econ).balance, 900)

	def test_taxes(self):
		pass





	
		
		
		

		

		
		






