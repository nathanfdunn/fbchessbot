import sys
if not sys.flags.debug:
	raise Exception('Debug flag must be enabled')
import fbchessbot
# import dbtools
import dbactions
import psycopg2

import unittest

# def remake_db():
# 	dbtools.conn = psycopg2.connect("dbname='fbchessbottest' user='nathandunn' host='localhost' password=''")
# 	dbtools.apply_all_migrations()

# Must be run with debug flag
sent_messages = []
def mock_send_message(recipient, text):
	sent_messages.append((recipient, text))

sent_game_reps = []
def mock_send_game_rep(recipient, game, perspective=True):
	sent_messages.append((recipient, game.image_url(perspective)))

sent_pgns = []
def mock_send_pgn(recipient, game):
	sent_pgns.append((recipient, game.pgn_url()))

def clear_mocks():
	global sent_messages, sent_game_reps, sent_pgns
	sent_messages = []
	sent_game_reps = []
	sent_pgns = []

fbchessbot.send_message = mock_send_message
fbchessbot.send_game_rep = mock_send_game_rep
fbchessbot.send_pgn = mock_send_pgn
# dbactions = fbchessbot = psycopg2 = None

class CustomAssertions:
	def assertLastMessageEquals(self, recipient, text):
		expected_response = recipient, text
		if not sent_messages:
			raise AssertionError(f'No recorded messages. Cannot match {expected_response!r}')
		last_message = sent_messages[-1]
		# This only works because we're multiply inheriting from unittest.TestCase as well
		self.assertEqual(last_message, expected_response)
		# if last_message != expected_response:
			# raise AssertionError(f'Message {last_message!r} != {expected_response!r}')

class BaseTest(unittest.TestCase, CustomAssertions):
	@classmethod
	def setUpClass(cls):
		cls.db = dbactions.DB()
		cls.nate_id = '32233848429'
		cls.chad_id = '83727482939'
		cls.jess_id = '47463849663'

	@classmethod
	def tearDownClass(cls):
		del cls.db


class TestRegistration(BaseTest):
	def setUp(self):
		self.db.delete_all()
		clear_mocks()

	def test_can_register(self):
		with self.subTest(player='Nate'):
			fbchessbot.handle_message(self.nate_id, 'My name is Nate')
			self.assertLastMessageEquals(self.nate_id, 'Nice to meet you Nate!')

		with self.subTest(player='Chad'):
			fbchessbot.handle_message(self.chad_id, '   \n  MY   \n NamE is   \n CHaD  \n  ')
			self.assertLastMessageEquals(self.chad_id, 'Nice to meet you CHaD!')

		with self.subTest(player='Jess'):
			fbchessbot.handle_message(self.jess_id, 'my name is jess')
			self.assertLastMessageEquals(self.jess_id, 'Nice to meet you jess!')

		with self.subTest(total_players=3):
			with self.db.cursor() as cur:
				cur.execute('SELECT COUNT(*) FROM player')
				self.assertEqual(cur.fetchone()[0], 3)

	# Coming soon!
	@unittest.expectedFailure
	def test_name_cant_collide_when_registering(self):
		fbchessbot.handle_message(self.nate_id, 'My name is Nate')
		with self.subTest():
			fbchessbot.handle_message(self.chad_id, 'My name is Nate')
			self.assertLastMessageEquals(self.chad_id, 'That name is taken. Please choose another')

		with self.subTest():
			with self.db.cursor() as cur:
				cur.execute('SELECT COUNT(*) FROM player WHERE id = %s', [self.chad_id])
				self.assertEqual(cur.fetchone()[0], 0)

		with self.subTest():
			fbchessbot.handle_message(self.jess_id, 'My name is nate')
			self.assertLastMessageEquals(self.jess_id, 'That name is taken. Please choose another')
		
		with self.subTest():
			with self.db.cursor() as cur:
				cur.execute('SELECT COUNT(*) FROM player WHERE id = %s', [self.jess_id])
				self.assertEqual(cur.fetchone()[0], 0)

	def test_can_rename(self):
		fbchessbot.handle_message(self.nate_id, 'my name is Nate')
		with self.subTest(case='first rename'):
			fbchessbot.handle_message(self.nate_id, 'my name is jonathan')
			self.assertLastMessageEquals(self.nate_id, 'I set your nickname to jonathan')
		
		with self.subTest():
			with self.db.cursor() as cur:
				cur.execute('SELECT nickname FROM player WHERE id = %s', [self.nate_id])
				self.assertEqual(cur.fetchone()[0], 'jonathan')

		with self.subTest(case='second rename'):
			fbchessbot.handle_message(self.nate_id, 'my name is jonathan')
			self.assertLastMessageEquals(self.nate_id, 'I set your nickname to jonathan')

	# Coming soon!
	@unittest.expectedFailure
	def test_name_cant_collide_when_renaming(self):
		fbchessbot.handle_message(self.nate_id, 'My name is Nate')
		fbchessbot.handle_message(self.chad_id, 'My name is Chad')
		fbchessbot.handle_message(self.jess_id, 'My name is Jess')

		with self.subTest():
			fbchessbot.handle_message(self.chad_id, 'My name is Nate')
			self.assertLastMessageEquals(self.chad_id, 'That name is taken. Please choose another')

		with self.subTest():
			with self.db.cursor() as cur:
				cur.execute('SELECT nickname FROM player WHERE id = %s', [self.chad_id])
				self.assertNotEqual(cur.fetchone()[0].casefold(), 'Nate'.casefold())

		with self.subTest():
			fbchessbot.handle_message(self.jess_id, 'My name is nate')
			self.assertLastMessageEquals(self.jess_id, 'That name is taken. Please choose another')
		
		with self.subTest():
			with self.db.cursor() as cur:
				cur.execute('SELECT nickname FROM player WHERE id = %s', [self.jess_id])
				self.assertNotEqual(cur.fetchone()[0].casefold(), 'Nate'.casefold())

	def test_name_must_conform(self):
		with self.subTest(nickname='special chars'):
			fbchessbot.handle_message(self.nate_id, 'my name is @*#n923')
			self.assertLastMessageEquals(self.nate_id, 'Nickname must match regex [a-z]+[0-9]*')

		with self.subTest(nickname='too long'):
			fbchessbot.handle_message(self.nate_id, 'my name is jerryfrandeskiemandersonfrancansolophenofocus')
			self.assertLastMessageEquals(self.nate_id, 'That nickname is too long (Try 32 or less characters)')

		with self.subTest(nickname='too long and special chars'):
			fbchessbot.handle_message(self.nate_id, 'my name is jerryfrandeskiemandersonfrancansolophenofocus#')
			self.assertLastMessageEquals(self.nate_id, 'Nickname must match regex [a-z]+[0-9]*')


# class TestOpponentContext(BaseTest):
# 	def setUp(self):
# 		self.db.delete_all()
# 		fbchessbot.handle_message(self.nate_id, 'My name is Nate')
# 		# fbchessbot.handle_message(self.)
# 		clear_mocks()

	# def test_can_

		# with self.subTest(nickname)

	# def test_can_self():
	# 	pass

	# def test_can_rename(self):
	# 	pass

	# def test_can_register(self):
	# 	print('blah')

	# def test_should_fail(self):
	# 	print('a')

# def main():
	# set_up_total()


if __name__ == '__main__':
	unittest.main()
