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
	sent_game_reps.append((recipient, game.image_url(perspective)))

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

_sentinel = object()

class CustomAssertions:
	def assertLastMessageEquals(self, recipient, text, *, target_index=-1):
		expected_response = str(recipient), text
		if not sent_messages:
			raise AssertionError(f'No recorded messages. Cannot match {expected_response!r}')
		last_message = sent_messages[target_index]
		last_message = str(last_message[0]), last_message[1]
		# This only works because we're multiply inheriting from unittest.TestCase as well
		self.assertEqual(last_message, expected_response)
		# Belt and suspenders...
		self.assertNotEqual(expected_response[0], 'None')
		self.assertNotEqual(last_message[0], 'None')

	def assertLastGameRepEquals(self, recipient, rep_url, *, target_index=-1):
		rep_url = 'https://fbchessbot.herokuapp.com/image/' + rep_url
		expected_rep = str(recipient), rep_url
		if not sent_game_reps:
			raise AssertionError(f'No recorded game reps. Cannot match {expected_response!r}')
		last_rep = sent_game_reps[target_index]
		last_rep = str(last_rep[0]), last_rep[1]
		# This only works because we're multiply inheriting from unittest.TestCase as well
		self.assertEqual(last_rep, expected_rep)
		# Belt and suspenders...
		self.assertNotEqual(expected_rep[0], 'None')
		self.assertNotEqual(last_rep[0], 'None')


class BaseTest(unittest.TestCase, CustomAssertions):
	expected_replies = None

	@classmethod
	def setUpClass(cls):
		cls.db = dbactions.DB()
		cls.nate_id = '32233848429'
		cls.chad_id = '83727482939'
		cls.jess_id = '47463849663'
		cls.izzy_id = '28394578322'

	@classmethod
	def tearDownClass(cls):
		del cls.db

	def handle_message(self, recipient, message, *, expected_replies=_sentinel):
		"Utility method for player input. Accounts for possibility of unexpected replies"
		if expected_replies is _sentinel:
			expected_replies = self.expected_replies

		num_replies_start = len(sent_messages) + len(sent_game_reps) + len(sent_pgns)
		fbchessbot.handle_message(recipient, message)
		num_replies_finish = len(sent_messages) + len(sent_game_reps) + len(sent_pgns)
		actual_replies = num_replies_finish - num_replies_start
		
		if expected_replies is not None and actual_replies != expected_replies:
			raise AssertionError(f'Expected {expected_replies} replies, got {actual_replies}')

	# For setting up the board
	def perform_moves(self, white_id, black_id, move_list, clear=True):
		while move_list:
			move_pair = move_list.pop(0)
			self.handle_message(white_id, move_pair[0])
			if len(move_pair) > 1:
				self.handle_message(black_id, move_pair[1])
		if clear:
			clear_mocks()

class TestRegistration(BaseTest):
	expected_replies = 1

	def setUp(self):
		self.db.delete_all()
		clear_mocks()

	def test_can_register(self):
		with self.subTest(player='Nate'):
			self.handle_message(self.nate_id, 'My name is Nate')
			self.assertLastMessageEquals(self.nate_id, 'Nice to meet you Nate!')

		with self.subTest(player='Chad'):
			self.handle_message(self.chad_id, '   \n  MY   \n NamE is   \n CHaD  \n  ')
			self.assertLastMessageEquals(self.chad_id, 'Nice to meet you CHaD!')

		with self.subTest(player='Jess'):
			self.handle_message(self.jess_id, 'my name is jess')
			self.assertLastMessageEquals(self.jess_id, 'Nice to meet you jess!')

		with self.subTest(total_players=3):
			with self.db.cursor() as cur:
				cur.execute('SELECT COUNT(*) FROM player')
				self.assertEqual(cur.fetchone()[0], 3)

	# Coming soon!
	@unittest.expectedFailure
	def test_name_cannot_collide_when_registering(self):
		self.handle_message(self.nate_id, 'My name is Nate')
		with self.subTest():
			self.handle_message(self.chad_id, 'My name is Nate')
			self.assertLastMessageEquals(self.chad_id, 'That name is taken. Please choose another')

		with self.subTest():
			with self.db.cursor() as cur:
				cur.execute('SELECT COUNT(*) FROM player WHERE id = %s', [self.chad_id])
				self.assertEqual(cur.fetchone()[0], 0)

		with self.subTest():
			self.handle_message(self.jess_id, 'My name is nate')
			self.assertLastMessageEquals(self.jess_id, 'That name is taken. Please choose another')
		
		with self.subTest():
			with self.db.cursor() as cur:
				cur.execute('SELECT COUNT(*) FROM player WHERE id = %s', [self.jess_id])
				self.assertEqual(cur.fetchone()[0], 0)

	def test_can_rename(self):
		self.handle_message(self.nate_id, 'my name is Nate', expected_replies=None)
		with self.subTest(case='first rename'):
			self.handle_message(self.nate_id, 'my name is jonathan')
			self.assertLastMessageEquals(self.nate_id, 'I set your nickname to jonathan')
		
		with self.subTest():
			with self.db.cursor() as cur:
				cur.execute('SELECT nickname FROM player WHERE id = %s', [self.nate_id])
				self.assertEqual(cur.fetchone()[0], 'jonathan')

		with self.subTest(case='second rename'):
			self.handle_message(self.nate_id, 'my name is jonathan')
			self.assertLastMessageEquals(self.nate_id, 'I set your nickname to jonathan')

	# Coming soon!
	@unittest.expectedFailure
	def test_name_cannot_collide_when_renaming(self):
		self.handle_message(self.nate_id, 'My name is Nate', expected_replies=None)
		self.handle_message(self.chad_id, 'My name is Chad', expected_replies=None)
		self.handle_message(self.jess_id, 'My name is Jess', expected_replies=None)

		with self.subTest():
			self.handle_message(self.chad_id, 'My name is Nate')
			self.assertLastMessageEquals(self.chad_id, 'That name is taken. Please choose another')

		with self.subTest():
			with self.db.cursor() as cur:
				cur.execute('SELECT nickname FROM player WHERE id = %s', [self.chad_id])
				self.assertNotEqual(cur.fetchone()[0].casefold(), 'Nate'.casefold())

		with self.subTest():
			self.handle_message(self.jess_id, 'My name is nate')
			self.assertLastMessageEquals(self.jess_id, 'That name is taken. Please choose another')
		
		with self.subTest():
			with self.db.cursor() as cur:
				cur.execute('SELECT nickname FROM player WHERE id = %s', [self.jess_id])
				self.assertNotEqual(cur.fetchone()[0].casefold(), 'Nate'.casefold())

	def test_name_must_conform(self):
		with self.subTest(nickname='special chars'):
			self.handle_message(self.nate_id, 'my name is @*#n923')
			self.assertLastMessageEquals(self.nate_id, 'Nickname must match regex [a-z]+[0-9]*')

		with self.subTest(nickname='too long'):
			self.handle_message(self.nate_id, 'my name is jerryfrandeskiemandersonfrancansolophenofocus')
			self.assertLastMessageEquals(self.nate_id, 'That nickname is too long (Try 32 or less characters)')

		with self.subTest(nickname='too long and special chars'):
			self.handle_message(self.nate_id, 'my name is jerryfrandeskiemandersonfrancansolophenofocus#')
			self.assertLastMessageEquals(self.nate_id, 'Nickname must match regex [a-z]+[0-9]*')

# Also need to check if there are already games active
class TestOpponentContext(BaseTest):
	expected_replies = 1

	def setUp(self):
		self.db.delete_all()
		self.handle_message(self.nate_id, 'My name is Nate', expected_replies=None)
		self.handle_message(self.chad_id, 'My name is Chad', expected_replies=None)
		self.handle_message(self.jess_id, 'My name is Jess', expected_replies=None)
		self.handle_message(self.izzy_id, 'My name is Izzy', expected_replies=None)
		# Just so we can be sure these two are playing each other
		self.handle_message(self.izzy_id, 'Play against Jess', expected_replies=None)
		self.handle_message(self.jess_id, 'Play against Izzy', expected_replies=None)
		clear_mocks()

	def test_opponent_context_automatically_set_on_newbie(self):
		self.handle_message(self.nate_id, 'Play against Chad', expected_replies=2)
		self.assertLastMessageEquals(self.chad_id, 'You are now playing against Nate', target_index=-2)
		self.assertLastMessageEquals(self.nate_id, 'You are now playing against Chad', target_index=-1)

		# Yeah...still need to convert over to int ids
		self.assertEqual(self.db.get_opponent_context(self.nate_id), int(self.chad_id))
		self.assertEqual(self.db.get_opponent_context(self.chad_id), int(self.nate_id))

	def test_opponent_context_not_set_automatically_on_other(self):
		self.handle_message(self.nate_id, 'Play against Jess', expected_replies=1)
		self.assertLastMessageEquals(self.nate_id, 'You are now playing against Jess')
		self.assertEqual(self.db.get_opponent_context(self.nate_id), int(self.jess_id))
		self.assertEqual(self.db.get_opponent_context(self.jess_id), int(self.izzy_id))

	@unittest.expectedFailure
	def test_notifies_on_redundant_context_setting(self):
		self.handle_message(self.nate_id, 'Play against Chad', expected_replies=2)
		self.handle_message(self.nate_id, 'Play against Chad', expected_replies=1)
		self.assertLastMessageEquals(self.nate_id, 'You are already playing against Chad')

	def test_cannot_set_opponent_context_on_nonplayer(self):
		self.handle_message(self.nate_id, 'Play against Dave', expected_replies=1)
		self.assertLastMessageEquals(self.nate_id, "No player named 'Dave'")

class TestGameInitiation(BaseTest):
	# expected_replies = 1

	def setUp(self):
		self.db.delete_all()
		self.handle_message(self.nate_id, 'My name is Nate', expected_replies=None)
		self.handle_message(self.chad_id, 'My name is Chad', expected_replies=None)
		self.handle_message(self.jess_id, 'My name is Jess', expected_replies=None)
		self.handle_message(self.izzy_id, 'My name is Izzy', expected_replies=None)

		self.handle_message(self.nate_id, 'Play against Jess', expected_replies=None)
		self.handle_message(self.jess_id, 'Play against Nate', expected_replies=None)
		clear_mocks()

	def test_cannot_start_new_game_without_context(self):
		self.handle_message(self.chad_id, 'New game white')
		self.assertLastMessageEquals(self.chad_id, "You aren't playing against anyone (Use command 'play against <name>')")

	def test_can_start_new_game_as_white(self):
		self.handle_message(self.nate_id, 'New game white', expected_replies=3)
		self.assertLastGameRepEquals(self.nate_id, 'rnbqkbnr-pppppppp-8-8-8-8-PPPPPPPP-RNBQKBNR', target_index=-2)
		self.assertLastMessageEquals(self.jess_id, 'Nate started a new game')
		self.assertLastGameRepEquals(self.jess_id, 'RNBKQBNR-PPPPPPPP-8-8-8-8-pppppppp-rnbkqbnr', target_index=-1)

	def test_can_start_new_game_as_black(self):
		self.handle_message(self.nate_id, 'New game black', expected_replies=3)
		# Note the order of the target_index's of these two. show_to_both sends to white first. Huh.
		self.assertLastGameRepEquals(self.nate_id, 'RNBKQBNR-PPPPPPPP-8-8-8-8-pppppppp-rnbkqbnr', target_index=-1)
		self.assertLastMessageEquals(self.jess_id, 'Nate started a new game')
		self.assertLastGameRepEquals(self.jess_id, 'rnbqkbnr-pppppppp-8-8-8-8-PPPPPPPP-RNBQKBNR', target_index=-2)

	@unittest.expectedFailure
	def test_cannot_start_new_in_middle_of_game(self):
		self.handle_message(self.nate_id, 'New game white', expected_replies=None)
		clear_mocks()
		self.handle_message(self.nate_id, 'New game white', expected_replies=1)
		self.assertLastMessageEquals(self.nate_id, 'You already have an active game with Jess')

class TestUndo: #(BaseTest):
	def test_undo_offer(self):
		pass
	def test_undo_accepted(self):
		pass
	def test_undo_rejected(self):
		pass

class TestGamePlay: #(BaseTest):
	def test_cannot_make_impossible_move(self):
		pass
	def test_cannot_move_on_opponent_turn(self):
		pass
	def test_cannot_make_ambiguous_move(self):
		pass

	def test_basic_moves(self):
		pass

	def test_check(self):
		pass

class TestGameFinish: #(BaseTest):
	def test_checkmate(self):
		pass

	def test_resign(self):
		pass

	def test_draw(self):
		pass

class TestMiscellaneous: #(BaseTest):
	def test_show(self):
		pass

	def test_help(self):
		pass

	def test_pgn(self):
		pass

	def test_pgns(self):
		pass
	# def pass

	# 	pass

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
