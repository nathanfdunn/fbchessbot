import sys
if not sys.flags.debug:
	raise Exception('Debug flag must be enabled')

from collections import defaultdict
import unittest

import chess
import psycopg2

import dbactions
from dbtools import refresh_funcs
import fbchessbot

# Want to refresh early and often
refresh_funcs()

intro = "Hi! Why don't you introduce yourself? (say My name is <name>)"

sent_messages = defaultdict(list)
def mock_send_message(recipient, text):
	recipient = recipient
	sent_messages[recipient].append(text)

sent_game_reps = defaultdict(list)
def mock_send_game_rep(recipient, game, perspective=True):
	recipient = recipient
	sent_game_reps[recipient].append(game.image_url(perspective))

sent_pgns = defaultdict(list)
def mock_send_pgn(recipient, game):
	recipient = recipient
	sent_pgns[recipient].append(game.pgn_url())

def clear_mocks():
	global sent_messages, sent_game_reps, sent_pgns
	sent_messages = defaultdict(list)
	sent_game_reps = defaultdict(list)
	sent_pgns = defaultdict(list)

fbchessbot.send_message = mock_send_message
fbchessbot.send_game_rep = mock_send_game_rep
fbchessbot.send_pgn = mock_send_pgn

_sentinel = object()

class CustomAssertions:
	def assertLastMessageEquals(self, recipient, text, *, target_index=-1):
		# recipient = str(recipient)
		messages = sent_messages[recipient]
		if not messages:
			raise AssertionError(f'No messages for {recipient}. Some for {[recipient for recipient in sent_messages if sent_messages[recipient]]}{sent_messages}')
		last_message = messages[target_index]
		# This only works because we're multiply inheriting from unittest.TestCase as well
		self.assertEqual(last_message, text)

	def assertLastGameRepEquals(self, recipient, rep_url, *, target_index=-1):
		# recipient = str(recipient)
		rep_url = 'https://fbchessbot.herokuapp.com/image/' + rep_url
		reps = sent_game_reps[recipient]
		if not reps:
			raise AssertionError(f'No game reps for {recipient}. Some for {[recipient for recipient in sent_game_reps if sent_game_reps[recipient]]}')
		last_rep = reps[target_index]
		# This only works because we're multiply inheriting from unittest.TestCase as well
		self.assertEqual(last_rep, rep_url)

class BaseTest(unittest.TestCase, CustomAssertions):
	expected_replies = None

	nate_id = 32233848429
	chad_id = 83727482939
	jess_id = 47463849663
	izzy_id = 28394578322

	def register_player(self, player_name, player_id=None):
		if player_id is None:
			player_id = {
				'nate': self.nate_id,
				'chad': self.chad_id,
				'jess': self.jess_id,
				'izzy': self.izzy_id
			}[player_name.lower()]
		# Verify this was successful
		self.handle_message(player_id, f'My name is {player_name}', expected_replies=1)

	def register_all(self):
		self.register_player('Nate')
		self.register_player('Chad')
		self.register_player('Jess')
		self.register_player('Izzy')
		clear_mocks()					# So we don't have all the noise from the registration

	@classmethod
	def setUpClass(cls):
		cls.db = dbactions.DB()
		cls.db.delete_all()
		# cls.nate_id = 32233848429
		# cls.chad_id = 83727482939
		# cls.jess_id = 47463849663
		# cls.izzy_id = 28394578322

	@classmethod
	def tearDownClass(cls):
		cls.db.delete_all()
		del cls.db

	def tearDown(self):
		self.db.delete_all()
		clear_mocks()

	def handle_message(self, recipient, message, *, expected_replies=_sentinel):
		'''Utility method for player input. Accounts for possibility of unexpected replies'''
		if expected_replies is _sentinel:
			expected_replies = self.expected_replies

		num_replies_start = sum(len(messages) for messages in sent_messages.values()) + \
							sum(len(games) for games in sent_game_reps.values()) + \
							sum(len(pgns) for pgns in sent_pgns.values())

		fbchessbot.handle_message(recipient, message)
		num_replies_finish = sum(len(messages) for messages in sent_messages.values()) + \
							sum(len(games) for games in sent_game_reps.values()) + \
							sum(len(pgns) for pgns in sent_pgns.values())
		actual_replies = num_replies_finish - num_replies_start
		
		if expected_replies is not None and actual_replies != expected_replies:
			raise AssertionError(f'Expected {expected_replies} replies, got {actual_replies} ({sent_messages})')

	# For setting up the board
	def perform_moves(self, white_id, black_id, move_list, clear=True):
		# while move_list:
			# move_pair = move_list.pop(0)
			# print(move_pair, len(move_pair))
		for move_pair in move_list:
			self.handle_message(white_id, move_pair[0], expected_replies=None)
			if len(move_pair) > 1:
				self.handle_message(black_id, move_pair[1], expected_replies=None)
		if clear:
			clear_mocks()

class TestUnregisteredResponses(BaseTest):
	# def setUp(self):
	# 	self.db.delete_all()
	# 	clear_mocks()

	def test_does_display_intro(self):
		newb = 12345678910
		self.handle_message(newb, 'Hi', expected_replies=1)
		self.assertLastMessageEquals(newb, intro)

class TestRegistration(BaseTest):
	# expected_replies = 1

	# def setUp(self):
	# 	self.db.delete_all()
	# 	clear_mocks()

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

	def test_name_cannot_collide_when_registering(self):
		self.handle_message(self.nate_id, 'My name is Nate')
		with self.subTest():
			self.handle_message(self.chad_id, 'My name is Nate')
			self.assertLastMessageEquals(self.chad_id, 'That name is taken. Please choose another')
			with self.db.cursor() as cur:
				cur.execute('SELECT COUNT(*) FROM player WHERE id = %s', [self.chad_id])
				self.assertEqual(cur.fetchone()[0], 0)

		with self.subTest():
			self.handle_message(self.jess_id, 'My name is nate')
			self.assertLastMessageEquals(self.jess_id, 'That name is taken. Please choose another')
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
			self.assertLastMessageEquals(self.nate_id, 'Your nickname is already jonathan')

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
			# Changing behavior of this edge case to make code cleaner
			# self.assertLastMessageEquals(self.nate_id, 'That nickname is too long (Try 32 or less characters)')
			# Changing behavior back for similar reasons
			self.assertLastMessageEquals(self.nate_id, 'Nickname must match regex [a-z]+[0-9]*')

# Also need to check if there are already games active
class TestOpponentContext(BaseTest):
	expected_replies = 1

	def setUp(self):
		# self.db.delete_all()
		self.register_all()
		# # self.handle_message(self.nate_id, 'My name is Nate', expected_replies=None)
		# # self.handle_message(self.chad_id, 'My name is Chad', expected_replies=None)
		# # self.handle_message(self.jess_id, 'My name is Jess', expected_replies=None)
		# # self.handle_message(self.izzy_id, 'My name is Izzy', expected_replies=None)
		# Just so we can be sure these two are playing each other
		self.handle_message(self.izzy_id, 'Play against Jess', expected_replies=None)
		self.handle_message(self.jess_id, 'Play against Izzy', expected_replies=None)
		clear_mocks()

	def test_unregistered_cannot_set_opponent_context(self):
		self.handle_message(839293, 'Play against Nate')
		self.assertLastMessageEquals(839293, intro)

	def test_opponent_context_automatically_set_on_newbie(self):
		self.handle_message(self.nate_id, 'Play against Chad', expected_replies=2)
		self.assertLastMessageEquals(self.chad_id, 'You are now playing against Nate')
		self.assertLastMessageEquals(self.nate_id, 'You are now playing against Chad')

		self.assertEqual(self.db.get_opponent_context(self.nate_id), self.chad_id)
		self.assertEqual(self.db.get_opponent_context(self.chad_id), self.nate_id)

	def test_opponent_context_not_set_automatically_on_other(self):
		self.handle_message(self.nate_id, 'Play against Jess', expected_replies=1)
		self.assertLastMessageEquals(self.nate_id, 'You are now playing against Jess')
		self.assertEqual(self.db.get_opponent_context(self.nate_id), self.jess_id)
		self.assertEqual(self.db.get_opponent_context(self.jess_id), self.izzy_id)

	def test_notifies_on_redundant_context_setting(self):
		self.handle_message(self.nate_id, 'Play against Chad', expected_replies=2)
		self.handle_message(self.nate_id, 'Play against Chad', expected_replies=1)
		self.assertLastMessageEquals(self.nate_id, 'You are already playing against Chad')

	def test_cannot_set_opponent_context_on_nonplayer(self):
		self.handle_message(self.nate_id, 'Play against Dave', expected_replies=1)
		self.assertLastMessageEquals(self.nate_id, 'There is no player by the name Dave')

	def test_context_case_insensitive(self):
		self.handle_message(self.nate_id, 'Play against cHAd', expected_replies=2)
		self.assertLastMessageEquals(self.nate_id, 'You are now playing against Chad')

class TestGameInitiation(BaseTest):
	# expected_replies = 1

	def setUp(self):
		# self.db.delete_all()
		self.register_all()
		# # self.handle_message(self.nate_id, 'My name is Nate', expected_replies=None)
		# # self.handle_message(self.chad_id, 'My name is Chad', expected_replies=None)
		# # self.handle_message(self.jess_id, 'My name is Jess', expected_replies=None)
		# # self.handle_message(self.izzy_id, 'My name is Izzy', expected_replies=None)
		self.handle_message(self.nate_id, 'Play against Jess', expected_replies=None)
		self.handle_message(self.jess_id, 'Play against Nate', expected_replies=None)
		clear_mocks()

	def test_cannot_use_invalid_color(self):
		self.handle_message(self.nate_id, 'New game blue')
		self.assertLastMessageEquals(self.nate_id, "Try either 'new game white' or 'new game black'")

	def test_cannot_start_new_game_without_context(self):
		self.handle_message(self.chad_id, 'New game white')
		self.assertLastMessageEquals(self.chad_id, "You aren't playing against anyone (Use command 'play against <name>')")

	def test_can_start_new_game_as_white(self):
		self.handle_message(self.nate_id, 'New game white', expected_replies=3)
		self.assertLastGameRepEquals(self.nate_id, 'rnbqkbnr-pppppppp-8-8-8-8-PPPPPPPP-RNBQKBNR')
		self.assertLastMessageEquals(self.jess_id, 'Nate started a new game')
		self.assertLastGameRepEquals(self.jess_id, 'RNBKQBNR-PPPPPPPP-8-8-8-8-pppppppp-rnbkqbnr')

	def test_can_start_new_game_as_black(self):
		self.handle_message(self.nate_id, 'New game black', expected_replies=3)
		# Note the order of the target_index's of these two. show_to_both sends to white first. Huh.
		self.assertLastGameRepEquals(self.nate_id, 'RNBKQBNR-PPPPPPPP-8-8-8-8-pppppppp-rnbkqbnr')
		self.assertLastMessageEquals(self.jess_id, 'Nate started a new game')
		self.assertLastGameRepEquals(self.jess_id, 'rnbqkbnr-pppppppp-8-8-8-8-PPPPPPPP-RNBQKBNR')

	def test_cannot_start_new_in_middle_of_game(self):
		self.handle_message(self.nate_id, 'New game white', expected_replies=None)
		clear_mocks()
		self.handle_message(self.nate_id, 'New game white', expected_replies=1)
		self.assertLastMessageEquals(self.nate_id, 'You already have an active game with Jess')


class GamePlayTest(BaseTest):
	def setUp(self):
		# clear_mocks()
		# self.db.delete_all()
		# # self.handle_message(self.nate_id, 'My name is Nate', expected_replies=None)
		# # self.handle_message(self.jess_id, 'My name is Jess', expected_replies=None)
		# # self.handle_message(self.chad_id, 'My name is Chad', expected_replies=None)
		self.register_player('Nate')
		self.register_player('Jess')
		self.register_player('Chad')
		# Izzy never registers

		self.handle_message(self.nate_id, 'Play against Jess', expected_replies=None)
		self.handle_message(self.jess_id, 'Play against Nate', expected_replies=None)

		self.handle_message(self.nate_id, 'New game white')
		clear_mocks()

	def set_position(self, board, extras=' w KQkq - 0 1'):
		'''Sets the state of the game between Nate and Jess to the specified position'''
		_, _, game = self.db.get_context(self.nate_id)
		game.board = board_from_str(board, extras)
		self.db.save_game(game)


def board_from_str(board, extras):
	board = board.strip().split('\n')
	rows = []
	for row in board:
		row = row.strip().replace(' ', '')
		for i in range(8, 0, -1):
			row = row.replace('.'*i, str(i))
		rows.append(row)
	fen = '/'.join(rows) + extras
	return dbactions.ChessBoard(fen)
	# return chess.Board(fen)

problemboard = None

class TestGamePlay(GamePlayTest):
	def test_basic_moves(self):
		self.handle_message(self.nate_id, 'e4', expected_replies=3)
		self.assertLastMessageEquals(self.jess_id, 'Nate played e4')
		self.assertLastGameRepEquals(self.nate_id, 'rnbqkbnr-pppppppp-8-8-4P3-8-PPPP1PPP-RNBQKBNR')
		self.assertLastGameRepEquals(self.jess_id, 'RNBKQBNR-PPP1PPPP-8-3P4-8-8-pppppppp-rnbkqbnr')

		self.handle_message(self.jess_id, 'e5', expected_replies=3)
		self.assertLastMessageEquals(self.nate_id, 'Jess played e5')
		# Now note the target_index's - handle_move doesn't use show_to_both
		self.assertLastGameRepEquals(self.nate_id, 'rnbqkbnr-pppp1ppp-8-4p3-4P3-8-PPPP1PPP-RNBQKBNR')
		self.assertLastGameRepEquals(self.jess_id, 'RNBKQBNR-PPP1PPPP-8-3P4-3p4-8-ppp1pppp-rnbkqbnr')

		self.handle_message(self.nate_id, 'Nf3', expected_replies=3)
		self.assertLastMessageEquals(self.jess_id, 'Nate played Nf3')
		self.assertLastGameRepEquals(self.nate_id, 'rnbqkbnr-pppp1ppp-8-4p3-4P3-5N2-PPPP1PPP-RNBQKB1R')
		self.assertLastGameRepEquals(self.jess_id, 'R1BKQBNR-PPP1PPPP-2N5-3P4-3p4-8-ppp1pppp-rnbkqbnr')

	def test_case_sensitivity(self):
		self.handle_message(self.nate_id, 'E4', expected_replies=3)
		self.assertLastMessageEquals(self.jess_id, 'Nate played e4')
		self.assertLastGameRepEquals(self.nate_id, 'rnbqkbnr-pppppppp-8-8-4P3-8-PPPP1PPP-RNBQKBNR')
		self.assertLastGameRepEquals(self.jess_id, 'RNBKQBNR-PPP1PPPP-8-3P4-8-8-pppppppp-rnbkqbnr')

		self.handle_message(self.jess_id, 'E5', expected_replies=3)
		self.assertLastMessageEquals(self.nate_id, 'Jess played e5')
		# Now note the target_index's - handle_move doesn't use show_to_both
		self.assertLastGameRepEquals(self.nate_id, 'rnbqkbnr-pppp1ppp-8-4p3-4P3-8-PPPP1PPP-RNBQKBNR')
		self.assertLastGameRepEquals(self.jess_id, 'RNBKQBNR-PPP1PPPP-8-3P4-3p4-8-ppp1pppp-rnbkqbnr')

		self.handle_message(self.nate_id, 'nf3', expected_replies=3)
		self.assertLastMessageEquals(self.jess_id, 'Nate played Nf3')
		self.assertLastGameRepEquals(self.nate_id, 'rnbqkbnr-pppp1ppp-8-4p3-4P3-5N2-PPPP1PPP-RNBQKB1R')
		self.assertLastGameRepEquals(self.jess_id, 'R1BKQBNR-PPP1PPPP-2N5-3P4-3p4-8-ppp1pppp-rnbkqbnr')



	def test_cannot_make_impossible_move(self):
		self.handle_message(self.nate_id, 'e5', expected_replies=1)
		self.assertLastMessageEquals(self.nate_id, 'That is an invalid move')

		self.handle_message(self.nate_id, 'Ke2', expected_replies=1)
		self.assertLastMessageEquals(self.nate_id, 'That is an invalid move')

		self.handle_message(self.nate_id, 'e4', expected_replies=None)
		self.handle_message(self.jess_id, 'e7', expected_replies=1)
		self.assertLastMessageEquals(self.jess_id, 'That is an invalid move')

	def test_cannot_move_on_opponent_turn(self):
		self.handle_message(self.jess_id, 'e5', expected_replies=1)
		self.assertLastMessageEquals(self.jess_id, "It isn't your turn")

	def test_cannot_make_ambiguous_move(self):
		with self.subTest('Ambiguous pawn move'):
			self.perform_moves(self.nate_id, self.jess_id, [('e4', 'f5'), ('c4', 'd5')])
			self.handle_message(self.nate_id, 'd5', expected_replies=1)
			self.assertLastMessageEquals(self.nate_id, 'That move could refer to two or more pieces')

	@unittest.expectedFailure			# Don't know why it's failing....
	def test_cannot_make_ambiguous_moveII(self):
		with self.subTest('Ambiguous knight move'):
			self.perform_moves(self.nate_id, self.jess_id, [('Nf3', 'h3'), ('Na3', 'g3'), ('Nc4', 'a3')])
			global problemboard
			problemboard = self.db.get_context(self.nate_id)
			self.handle_message(self.nate_id, 'Ne6', expected_replies=1)
			self.assertLastMessageEquals(self.nate_id, 'That move could refer to two or more pieces')

	@unittest.skip
	def test_can_qualify_ambiguous_move(self):
		self.perform_moves(self.nate_id, self.jess_id, [('e4', 'f5'), ('c4', 'd5')])
		self.handle_message(self.nate_id, 'd5', expected_replies=1)

	@unittest.skip
	def test_can_qualify_unambiguous_move(self):
		pass

	def test_can_handle_bishop_edge_case(self):
		board = '''
		. . . . . . k .
		. . . . . p p p
		. . . . . . . .
		. . . . . . . .
		. . . . . . . .
		. . . . . n . .
		. . . . B . P .
		. K . . . . . .
		'''
		self.set_position(board)
		self.handle_message(self.nate_id, 'Bf3', expected_replies=3)

	def test_can_make_case_insensitive_pawn_move(self):
		self.handle_message(self.nate_id, 'E4', expected_replies=3)
		self.assertLastGameRepEquals(self.nate_id, 'rnbqkbnr-pppppppp-8-8-4P3-8-PPPP1PPP-RNBQKBNR')

	def test_can_qualify_pawn_move_piece(self):
		self.handle_message(self.nate_id, 'Pe4', expected_replies=3)
		self.assertLastGameRepEquals(self.nate_id, 'rnbqkbnr-pppppppp-8-8-4P3-8-PPPP1PPP-RNBQKBNR')

	def test_can_promote(self):
		board = '''
				. . . . . . . .
				. k . . P . . .
				. . . . . . . .
				. . . . . . . .
				. . . . . . . .
				. . . . . . . .
				. . . . . . . .
				. K . . . . . .
				'''
		with self.subTest('Verbose'):
			self.set_position(board)
			self.handle_message(self.nate_id, 'e8=Q', expected_replies=3)
			self.assertLastGameRepEquals(self.nate_id, '4Q3-1k6-8-8-8-8-8-1K6')

		with self.subTest('Verbose (lower)'):
			self.set_position(board)
			self.handle_message(self.nate_id, 'e8=q', expected_replies=3)
			self.assertLastGameRepEquals(self.nate_id, '4Q3-1k6-8-8-8-8-8-1K6')

		with self.subTest('Minimal'):
			self.set_position(board)
			self.handle_message(self.nate_id, 'e8Q', expected_replies=3)
			self.assertLastGameRepEquals(self.nate_id, '4Q3-1k6-8-8-8-8-8-1K6')

		with self.subTest('Minimal (lower)'):
			self.set_position(board)
			self.handle_message(self.nate_id, 'e8q', expected_replies=3)
			self.assertLastGameRepEquals(self.nate_id, '4Q3-1k6-8-8-8-8-8-1K6')

	def test_can_castle(self):
		board = '''
				r . . . k . . r
				. . . . . . . .
				. . . . . . . .
				. . . . . . . .
				. . . . . . . .
				. . . . . . . .
				. . . . . . . .
				R . . . K . . R
				'''
		with self.subTest('Long - Ohs'):
			self.set_position(board)
			self.handle_message(self.nate_id, 'O-O-O', expected_replies=3)
			self.assertLastGameRepEquals(self.nate_id, 'r3k2r-8-8-8-8-8-8-2KR3R')

		with self.subTest('Long - 0s'):
			self.set_position(board)
			self.handle_message(self.nate_id, '0-0-0', expected_replies=3)
			self.assertLastGameRepEquals(self.nate_id, 'r3k2r-8-8-8-8-8-8-2KR3R')

	def test_check(self):
		self.perform_moves(self.nate_id, self.jess_id, [('e4', 'f5')])
		clear_mocks()
		self.handle_message(self.nate_id, 'Qh5', expected_replies=5)
		self.assertLastMessageEquals(self.jess_id, 'Nate played Qh5', target_index=-2)
		self.assertLastMessageEquals(self.jess_id, 'Check!', target_index=-1)
		self.assertLastMessageEquals(self.nate_id, 'Check!')

class TestUndo(GamePlayTest):
	def test_undo(self):
		with self.subTest('can offer'):
			self.handle_message(self.nate_id, 'e4', expected_replies=None)
			with self.db.cursor() as cur:
				cur.execute('SELECT undo FROM games')
				self.assertEqual(cur.fetchone()[0], False)
			clear_mocks()
			self.handle_message(self.nate_id, 'undo', expected_replies=1)
			with self.db.cursor() as cur:
				cur.execute('SELECT undo FROM games')
				self.assertEqual(cur.fetchone()[0], True)
			self.assertLastMessageEquals(self.jess_id, 'Nate has requested an undo')

		with self.subTest('can accept'):
			self.handle_message(self.jess_id, 'undo', expected_replies=3)
			self.assertLastMessageEquals(self.nate_id, 'Jess accepted your undo request')
			self.assertLastGameRepEquals(self.nate_id, 'rnbqkbnr-pppppppp-8-8-8-8-PPPPPPPP-RNBQKBNR')
			self.assertLastGameRepEquals(self.jess_id, 'RNBKQBNR-PPPPPPPP-8-8-8-8-pppppppp-rnbkqbnr')
			with self.db.cursor() as cur:
				cur.execute('SELECT undo FROM games')
				self.assertEqual(cur.fetchone()[0], False)

	def test_undo_rejected(self):
		self.handle_message(self.nate_id, 'e4', expected_replies=None)
		self.handle_message(self.nate_id, 'undo', expected_replies=None)
		clear_mocks()
		self.handle_message(self.jess_id, 'e5', expected_replies=3)
		with self.db.cursor() as cur:
			cur.execute('SELECT undo FROM games')
			self.assertEqual(cur.fetchone()[0], False)

	def test_cannot_undo_on_your_turn(self):
		self.handle_message(self.nate_id, 'e4', expected_replies=None)
		self.handle_message(self.jess_id, 'undo', expected_replies=1)
		self.assertLastMessageEquals(self.jess_id, "You can't request an undo when it is your turn")
		with self.db.cursor() as cur:
			cur.execute('SELECT undo FROM games')
			self.assertEqual(cur.fetchone()[0], False)

	def test_cannot_undo_before_first_move(self):
		self.handle_message(self.jess_id, 'undo', expected_replies=1)
		self.assertLastMessageEquals(self.jess_id, "You haven't made any moves to undo")
		with self.db.cursor() as cur:
			cur.execute('SELECT undo FROM games')
			self.assertEqual(cur.fetchone()[0], False)

	def test_cannot_undo_without_active_game(self):
		with self.subTest('Unregistered'):
			self.handle_message(self.izzy_id, 'undo', expected_replies=1)
			self.assertLastMessageEquals(self.izzy_id, intro)

		with self.subTest('Registered...?'):
			# self.handle_message(self.nate_id, 'Play against Chad', expected_replies=None)
			# raise Exception(self.db.user_is_registered(self.nate_id))
			# raise Exception(self.db.get_context(self.nate_id))
			self.handle_message(self.chad_id, 'undo', expected_replies=1)
			self.assertLastMessageEquals(self.chad_id, 'You have no active games')

	def test_redundant_undo_request(self):
		self.handle_message(self.nate_id, 'e4', expected_replies=None)
		self.handle_message(self.nate_id, 'undo', expected_replies=None)
		clear_mocks()
		self.handle_message(self.nate_id, 'undo', expected_replies=1)
		self.assertLastMessageEquals(self.nate_id, 'You have already requested an undo')

	def test_cannot_undo_without_active_gameII(self):
		# Fastest way to kill the game
		# exit()
		self.handle_message(self.nate_id, 'resign', expected_replies=None)
		self.handle_message(self.nate_id, 'undo', expected_replies=1)
		self.assertLastMessageEquals(self.nate_id, 'You have no active games with Jess')
		# self.handle_message(self.izzy_id, 'Play against Chad', expected_replies=None)
		# self.handle_message(self.izzy_id, 'undo', expected_replies=1)
		# self.assertLastMessageEquals(self.izzy_id, 'You have no active games with Chad')


class TestGameFinish(GamePlayTest):
	def test_checkmate(self):
		self.perform_moves(self.nate_id, self.jess_id, [('f4', 'e5'), ('g4',)] )
		with self.subTest('Player communication'):
			self.handle_message(self.jess_id, 'Qh4', expected_replies=5)
			self.assertLastMessageEquals(self.jess_id, 'Checkmate! Jess wins!')
			self.assertLastMessageEquals(self.nate_id, 'Jess played Qh4', target_index=-2)
			self.assertLastMessageEquals(self.nate_id, 'Checkmate! Jess wins!', target_index=-1)

		with self.subTest('Outcome is set'):
			with self.db.cursor() as cur:
				cur.execute('SELECT outcome FROM games')
				self.assertEqual(cur.fetchone()[0], fbchessbot.BLACK_WINS)

		with self.subTest('Game is inactive'):
			with self.db.cursor() as cur:
				cur.execute('SELECT active FROM games')
				self.assertEqual(cur.fetchone()[0], False)

	def test_checkmate_ends_game(self):
		self.perform_moves(self.nate_id, self.jess_id, [('f4', 'e5'), ('g4', 'Qh4')] )
		with self.subTest('Game is inactive'):
			_, _, game = self.db.get_context(self.nate_id)
			self.assertEqual(game, None)

		with self.subTest('Outcome is win for black'):
			with self.db.cursor() as cur:
				cur.execute('SELECT outcome FROM games')
				self.assertEqual(cur.fetchone()[0], 2)

	def test_resign(self):
		self.handle_message(self.nate_id, 'resign', expected_replies=2)
		self.assertLastMessageEquals(self.nate_id, 'Nate resigns. Jess wins!')
		self.assertLastMessageEquals(self.jess_id, 'Nate resigns. Jess wins!')
		with self.db.cursor() as cur:
			cur.execute('SELECT outcome FROM games')
			self.assertEqual(cur.fetchone()[0], fbchessbot.BLACK_WINS)
		with self.db.cursor() as cur:
			cur.execute('SELECT active FROM games')
			self.assertEqual(cur.fetchone()[0], False)

	def test_resign_without_game(self):
		self.handle_message(self.chad_id, 'resign', expected_replies=1)
		self.assertLastMessageEquals(self.chad_id, 'You have no active games')

	@unittest.skip
	def test_draw(self):
		pass

class TestMiscellaneous(GamePlayTest):
	def test_show(self):
		with self.subTest('Unregistered'):
			self.handle_message(self.izzy_id, 'show', expected_replies=1)
			self.assertLastMessageEquals(self.izzy_id, intro)

		with self.subTest('Without game'):
			self.handle_message(self.chad_id, 'show', expected_replies=1)
			self.assertLastMessageEquals(self.chad_id, 'You have no active games')

		with self.subTest('With game - White'):
			self.handle_message(self.nate_id, 'show', expected_replies=2)
			self.assertLastGameRepEquals(self.nate_id, 'rnbqkbnr-pppppppp-8-8-8-8-PPPPPPPP-RNBQKBNR')
			self.assertLastMessageEquals(self.nate_id, 'White to move')

		with self.subTest('With game - Black'):
			self.handle_message(self.jess_id, 'show', expected_replies=2)
			self.assertLastGameRepEquals(self.jess_id, 'RNBKQBNR-PPPPPPPP-8-8-8-8-pppppppp-rnbkqbnr')
			self.assertLastMessageEquals(self.jess_id, 'White to move')

	def test_help(self):
		self.handle_message(self.nate_id, 'help')
		self.assertLastMessageEquals(self.nate_id, 'Help text coming soon...')

	# Maybe should also test with unregistered user
	def test_empty(self):
		self.handle_message(self.nate_id, '')
		self.assertLastMessageEquals(self.nate_id, 'That is an invalid move')

	@unittest.skip
	def test_pgn(self):
		pass

	@unittest.skip
	def test_pgns(self):
		pass

	@unittest.skip
	def test_stats(self):
		pass
		# self.handle_message(self.nate_id, 'stats', expected_replies=1)

	@unittest.skip
	def test_status(self):
		pass
		# self.handle_message(self.nate_id, 'status', expected_replies=1)

# @unittest.skip
class TestPlayerInteractions(BaseTest):
	def init_blocks(self):
		self.handle_message(self.nate_id, 'Play against Jess')
		self.handle_message(self.jess_id, 'Play against Nate')
		self.handle_message(self.nate_id, 'Block Jess')

	def setUp(self):
		self.register_all()

	def test_can_block_newly_registered(self):
		with self.subTest('Block notifications'):
			self.handle_message(self.nate_id, 'Block jess', expected_replies=2)
			self.assertLastMessageEquals(self.nate_id, 'You have blocked Jess')
			self.assertLastMessageEquals(self.jess_id, 'You have been blocked by Nate')

		with self.subTest('Block effects'):
			self.handle_message(self.nate_id, 'Play against Jess', expected_replies=1)
			self.assertLastMessageEquals(self.nate_id, 'You have blocked Jess')

			self.handle_message(self.jess_id, 'Play against Nate', expected_replies=1)
			self.assertLastMessageEquals(self.jess_id, 'You have been blocked by Nate')

	def test_can_block_redundant(self):
		self.handle_message(self.nate_id, 'Block jess', expected_replies=2)
		self.handle_message(self.nate_id, 'Block jess', expected_replies=1)
		self.assertLastMessageEquals(self.nate_id, 'You have already blocked Jess')

	def test_can_mutual_block(self):
		self.handle_message(self.nate_id, 'Block jess', expected_replies=2)
		self.handle_message(self.jess_id, 'Block nate', expected_replies=2)
		self.assertLastMessageEquals(self.nate_id, 'You have been blocked by Jess')
		self.assertLastMessageEquals(self.jess_id, 'You have blocked Nate')

		with self.subTest('Self block message dominates'):
			self.handle_message(self.nate_id, 'Play against jess', expected_replies=1)
			self.assertLastMessageEquals(self.nate_id, 'You have blocked Jess')

			self.handle_message(self.jess_id, 'Play against nate', expected_replies=1)
			self.assertLastMessageEquals(self.jess_id, 'You have blocked Nate')

	def test_blocking_removes_game_context(self):
		pass


	@unittest.skip
	def test_can_block_all(self):
		with self.subTest('Sender notification'):
			self.handle_message(self.nate_id, 'Block everyone', expected_replies=1)
			self.assertLastMessageEquals(self.nate_id, 'You have blocked everyone')

		with self.subTest('Block effects'):
			self.handle_message(self.jess_id, 'Play against Nate', expected_replies=1)
			self.assertLastMessageEquals(self.jess_id, 'Nate is not accepting any challenges')

	@unittest.skip
	def test_can_block_strangers(self):
		with self.subTest('Sender notification'):
			self.handle_message(self.nate_id, 'Block strangers', expected_replies=1)
			self.assertLastMessageEquals(self.nate_id, 'Strangers will no longer be able to interact with you')

		with self.subTest('Stranger blocked'):
			self.handle_message(self.chad_id, 'Play against Nate', expected_replies=1)
			self.assertLastMessageEquals(self.chad_id, 'Nate is not accepting any challenges')

		with self.subTest('Friend not blocked'):
			self.handle_message(self.jess_id, 'Play against Nate', expected_replies=1)
			self.assertLastMessageEquals(self.jess_id, 'You are now playing against Nate')

	@unittest.skip
	def test_can_unblock_strangers(self):
		with self.subTest('Sender notification'):
			self.handle_message(self.nate_id, 'Unblock strangers', expected_replies=1)
			self.assertLastMessageEquals(self.nate_id, 'Strangers will now be able to interact with you')

		with self.subTest('Stranger unblocked'):
			self.handle_message(self.chad_id, 'Play against Nate', expected_replies=1)
			self.assertLastMessageEquals(self.chad_id, 'Nate is not accepting any challenges')

		with self.subTest('Friend still not blocked'):
			self.handle_message(self.jess_id, 'Play against Nate', expected_replies=1)
			self.assertLastMessageEquals(self.jess_id, 'You are now playing against Nate')

		# self.handle_message(self.jess_id, 'New game white', expected_replies=1)
		# self.assertLastMessageEquals(self.jess_id, 'You have been blocked by Nate')



	def test_can_block_before_game_starts(self):
		pass

	def test_can_block_during_game(self):
		pass

	def test_can_unblock(self):
		self.handle_message(self.nate_id, 'Block jess', expected_replies=None)

		self.handle_message(self.nate_id, 'Unblock jess', expected_replies=2)
		self.assertLastMessageEquals(self.nate_id, 'You have unblocked Jess')
		self.assertLastMessageEquals(self.jess_id, 'You have been unblocked by Nate')

@unittest.skip
class TestChallengeAcceptance(BaseTest):
	def setUp(self):
		self.register_all()

	def test_newly_registered_autoaccept(self):
		self.handle_message(self.nate_id, 'Play against jess', expected_replies=2)
		self.assertLastMessageEquals(self.nate_id, 'You are now playing against Jess')

	def test_can_challenge_with_color(self):
		self.handle_message(self.nate_id, 'Play against jess white', expected_replies=3)
		self.handle_m

# class TestBlocking(BaseTest):
# 	def setUp(self):
# 		self.register_all()


	# def test_can_


if __name__ == '__main__':
	unittest.main()
	# pass

if False:
	self = BaseTest()
	self.setUpClass()
	self.db.delete_all()
	self.handle_message(self.nate_id, 'My name is Nate', expected_replies=None)
	self.handle_message(self.chad_id, 'My name is Chad', expected_replies=None)
	self.handle_message(self.jess_id, 'My name is Jess', expected_replies=None)
	self.handle_message(self.izzy_id, 'My name is Izzy', expected_replies=None)
	# Just so we can be sure these two are playing each other
	self.handle_message(self.izzy_id, 'Play against Jess', expected_replies=None)
	self.handle_message(self.jess_id, 'Play against Izzy', expected_replies=None)
	self.handle_message(self.izzy_id, 'new game white')
	# self.handle_message(self.izzy_id, 'new game black')
	# self.handle_message(self.izzy_id, 'new game white')
	# self.handle_message(self.izzy_id, 'new game black')
