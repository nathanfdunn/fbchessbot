import sys
if not sys.flags.debug:
	raise Exception('Debug flag must be enabled')

from collections import defaultdict
import unittest

import chess
import psycopg2

import constants
import dbactions
from dbtools import refresh_funcs
import fbchessbot

# Want to refresh early and often
refresh_funcs()

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

nateid = 32233848429
chadid = 83727482939
jessid = 47463849663
izzyid = 28394578322

class BaseTest(unittest.TestCase):
	expected_replies = None

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

	def register_player(self, player_name, playerid=None):
		if playerid is None:
			playerid = {
				'nate': nateid,
				'chad': chadid,
				'jess': jessid,
				'izzy': izzyid
			}[player_name.lower()]
		self.handle_message(playerid, f'My name is {player_name}', expected_replies=1)

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

	@classmethod
	def tearDownClass(cls):
		cls.db.delete_all()
		del cls.db

	def tearDown(self):
		self.db.delete_all()
		clear_mocks()

	def handle_message(self, recipient, message, *, expected_replies=None):
		'''Utility method for player input. Accounts for possibility of unexpected replies'''
		num_replies_start = (sum(len(messages) for messages in sent_messages.values()) +
								sum(len(games) for games in sent_game_reps.values()) +
								sum(len(pgns) for pgns in sent_pgns.values())
								)

		fbchessbot.handle_message(recipient, message)
		num_replies_finish = (sum(len(messages) for messages in sent_messages.values()) +
								sum(len(games) for games in sent_game_reps.values()) +
								sum(len(pgns) for pgns in sent_pgns.values())
								)
		actual_replies = num_replies_finish - num_replies_start
		
		if expected_replies is not None and actual_replies != expected_replies:
			raise AssertionError(f'Expected {expected_replies} replies, got {actual_replies} ({sent_messages})')

	# For setting up the board
	def perform_moves(self, white_id, black_id, move_list, clear=True):
		for move_pair in move_list:
			self.handle_message(white_id, move_pair[0], expected_replies=None)
			if len(move_pair) > 1:
				self.handle_message(black_id, move_pair[1], expected_replies=None)
		if clear:
			clear_mocks()

class TestUnregisteredResponses(BaseTest):
	def test_does_display_intro(self):
		newb = 12345678910
		self.handle_message(newb, 'Hi', expected_replies=1)
		self.assertLastMessageEquals(newb, constants.intro)

class TestRegistration(BaseTest):
	def test_can_register(self):
		with self.subTest(player='Nate'):
			self.handle_message(nateid, 'My name is Nate')
			self.assertLastMessageEquals(nateid, 'Nice to meet you Nate!')

		with self.subTest(player='Chad'):
			self.handle_message(chadid, '   \n  MY   \n NamE is   \n CHaD  \n  ')
			self.assertLastMessageEquals(chadid, 'Nice to meet you CHaD!')

		with self.subTest(player='Jess'):
			self.handle_message(jessid, 'my name is jess')
			self.assertLastMessageEquals(jessid, 'Nice to meet you jess!')

		with self.subTest(total_players=3):
			with self.db.cursor() as cur:
				cur.execute('SELECT COUNT(*) FROM player')
				self.assertEqual(cur.fetchone()[0], 3)

	def test_name_cannot_collide_when_registering(self):
		self.handle_message(nateid, 'My name is Nate')
		with self.subTest():
			self.handle_message(chadid, 'My name is Nate')
			self.assertLastMessageEquals(chadid, 'That name is taken. Please choose another')
			with self.db.cursor() as cur:
				cur.execute('SELECT COUNT(*) FROM player WHERE id = %s', [chadid])
				self.assertEqual(cur.fetchone()[0], 0)

		with self.subTest():
			self.handle_message(jessid, 'My name is nate')
			self.assertLastMessageEquals(jessid, 'That name is taken. Please choose another')
			with self.db.cursor() as cur:
				cur.execute('SELECT COUNT(*) FROM player WHERE id = %s', [jessid])
				self.assertEqual(cur.fetchone()[0], 0)

	def test_can_rename(self):
		self.handle_message(nateid, 'my name is Nate', expected_replies=None)

		with self.subTest(case='first rename'):
			self.handle_message(nateid, 'my name is jonathan')
			self.assertLastMessageEquals(nateid, 'I set your nickname to jonathan')
		
		with self.subTest():
			with self.db.cursor() as cur:
				cur.execute('SELECT nickname FROM player WHERE id = %s', [nateid])
				self.assertEqual(cur.fetchone()[0], 'jonathan')

		with self.subTest(case='second rename'):
			self.handle_message(nateid, 'my name is jonathan')
			self.assertLastMessageEquals(nateid, 'Your nickname is already jonathan')

	def test_name_cannot_collide_when_renaming(self):
		self.handle_message(nateid, 'My name is Nate', expected_replies=None)
		self.handle_message(chadid, 'My name is Chad', expected_replies=None)
		self.handle_message(jessid, 'My name is Jess', expected_replies=None)

		with self.subTest():
			self.handle_message(chadid, 'My name is Nate')
			self.assertLastMessageEquals(chadid, 'That name is taken. Please choose another')

		with self.subTest():
			with self.db.cursor() as cur:
				cur.execute('SELECT nickname FROM player WHERE id = %s', [chadid])
				self.assertNotEqual(cur.fetchone()[0].casefold(), 'Nate'.casefold())

		with self.subTest():
			self.handle_message(jessid, 'My name is nate')
			self.assertLastMessageEquals(jessid, 'That name is taken. Please choose another')
		
		with self.subTest():
			with self.db.cursor() as cur:
				cur.execute('SELECT nickname FROM player WHERE id = %s', [jessid])
				self.assertNotEqual(cur.fetchone()[0].casefold(), 'Nate'.casefold())

	def test_name_must_conform(self):
		with self.subTest(nickname='special chars'):
			self.handle_message(nateid, 'my name is @*#n923')
			self.assertLastMessageEquals(nateid, 'Nickname must match regex [a-z]+[0-9]*')

		with self.subTest(nickname='too long'):
			self.handle_message(nateid, 'my name is jerryfrandeskiemandersonfrancansolophenofocus')
			self.assertLastMessageEquals(nateid, 'That nickname is too long (Try 32 or less characters)')

		with self.subTest(nickname='too long and special chars'):
			self.handle_message(nateid, 'my name is jerryfrandeskiemandersonfrancansolophenofocus#')
			# Changing behavior of this edge case to make code cleaner
			# self.assertLastMessageEquals(nateid, 'That nickname is too long (Try 32 or less characters)')
			# Changing behavior back for similar reasons
			self.assertLastMessageEquals(nateid, 'Nickname must match regex [a-z]+[0-9]*')

# Also need to check if there are already games active
class TestOpponentContext(BaseTest):
	expected_replies = 1

	def setUp(self):
		self.register_all()
		self.handle_message(izzyid, 'Play against Jess', expected_replies=None)
		self.handle_message(jessid, 'Play against Izzy', expected_replies=None)
		clear_mocks()

	def test_unregistered_cannot_set_opponent_context(self):
		self.handle_message(839293, 'Play against Nate')
		self.assertLastMessageEquals(839293, intro)

	def test_opponent_context_automatically_set_on_newbie(self):
		self.handle_message(nateid, 'Play against Chad', expected_replies=2)
		self.assertLastMessageEquals(chadid, 'You are now playing against Nate')
		self.assertLastMessageEquals(nateid, 'You are now playing against Chad')

		self.assertEqual(self.db.get_opponent_context(nateid), chadid)
		self.assertEqual(self.db.get_opponent_context(chadid), nateid)

	def test_opponent_context_not_set_automatically_on_other(self):
		self.handle_message(nateid, 'Play against Jess', expected_replies=1)
		self.assertLastMessageEquals(nateid, 'You are now playing against Jess')
		self.assertEqual(self.db.get_opponent_context(nateid), jessid)
		self.assertEqual(self.db.get_opponent_context(jessid), izzyid)

	def test_notifies_on_redundant_context_setting(self):
		self.handle_message(nateid, 'Play against Chad', expected_replies=2)
		self.handle_message(nateid, 'Play against Chad', expected_replies=1)
		self.assertLastMessageEquals(nateid, 'You are already playing against Chad')

	def test_cannot_set_opponent_context_on_nonplayer(self):
		self.handle_message(nateid, 'Play against Dave', expected_replies=1)
		self.assertLastMessageEquals(nateid, 'There is no player by the name Dave')

	def test_context_case_insensitive(self):
		self.handle_message(nateid, 'Play against cHAd', expected_replies=2)
		self.assertLastMessageEquals(nateid, 'You are now playing against Chad')

class TestGameInitiation(BaseTest):
	# expected_replies = 1

	def setUp(self):
		self.register_all()
		self.handle_message(nateid, 'Play against Jess', expected_replies=None)
		self.handle_message(jessid, 'Play against Nate', expected_replies=None)
		clear_mocks()

	def test_cannot_use_invalid_color(self):
		self.handle_message(nateid, 'New game blue')
		self.assertLastMessageEquals(nateid, "Try either 'new game white' or 'new game black'")

	def test_cannot_start_new_game_without_context(self):
		self.handle_message(chadid, 'New game white')
		self.assertLastMessageEquals(chadid, "You aren't playing against anyone (Use command 'play against <name>')")

	def test_can_start_new_game_as_white(self):
		self.handle_message(nateid, 'New game white', expected_replies=3)
		self.assertLastGameRepEquals(nateid, 'rnbqkbnr-pppppppp-8-8-8-8-PPPPPPPP-RNBQKBNR')
		self.assertLastMessageEquals(jessid, 'Nate started a new game')
		self.assertLastGameRepEquals(jessid, 'RNBKQBNR-PPPPPPPP-8-8-8-8-pppppppp-rnbkqbnr')

	def test_can_start_new_game_as_black(self):
		self.handle_message(nateid, 'New game black', expected_replies=3)
		# Note the order of the target_index's of these two. show_to_both sends to white first. Huh.
		self.assertLastGameRepEquals(nateid, 'RNBKQBNR-PPPPPPPP-8-8-8-8-pppppppp-rnbkqbnr')
		self.assertLastMessageEquals(jessid, 'Nate started a new game')
		self.assertLastGameRepEquals(jessid, 'rnbqkbnr-pppppppp-8-8-8-8-PPPPPPPP-RNBQKBNR')

	def test_cannot_start_new_in_middle_of_game(self):
		self.handle_message(nateid, 'New game white', expected_replies=None)
		clear_mocks()
		self.handle_message(nateid, 'New game white', expected_replies=1)
		self.assertLastMessageEquals(nateid, 'You already have an active game with Jess')


class GamePlayTest(BaseTest):
	def setUp(self):
		self.register_player('Nate')
		self.register_player('Jess')
		self.register_player('Chad')
		# Izzy never registers

		self.handle_message(nateid, 'Play against Jess', expected_replies=None)
		self.handle_message(jessid, 'Play against Nate', expected_replies=None)

		self.handle_message(nateid, 'New game white')
		clear_mocks()

	def set_position(self, board, extras=' w KQkq - 0 1'):
		'''Sets the state of the game between Nate and Jess to the specified position'''
		_, _, game = self.db.get_context(nateid)
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

problemboard = None

class TestGamePlay(GamePlayTest):
	def test_basic_moves(self):
		self.handle_message(nateid, 'e4', expected_replies=3)
		self.assertLastMessageEquals(jessid, 'Nate played e4')
		self.assertLastGameRepEquals(nateid, 'rnbqkbnr-pppppppp-8-8-4P3-8-PPPP1PPP-RNBQKBNR')
		self.assertLastGameRepEquals(jessid, 'RNBKQBNR-PPP1PPPP-8-3P4-8-8-pppppppp-rnbkqbnr')

		self.handle_message(jessid, 'e5', expected_replies=3)
		self.assertLastMessageEquals(nateid, 'Jess played e5')
		# Now note the target_index's - handle_move doesn't use show_to_both
		self.assertLastGameRepEquals(nateid, 'rnbqkbnr-pppp1ppp-8-4p3-4P3-8-PPPP1PPP-RNBQKBNR')
		self.assertLastGameRepEquals(jessid, 'RNBKQBNR-PPP1PPPP-8-3P4-3p4-8-ppp1pppp-rnbkqbnr')

		self.handle_message(nateid, 'Nf3', expected_replies=3)
		self.assertLastMessageEquals(jessid, 'Nate played Nf3')
		self.assertLastGameRepEquals(nateid, 'rnbqkbnr-pppp1ppp-8-4p3-4P3-5N2-PPPP1PPP-RNBQKB1R')
		self.assertLastGameRepEquals(jessid, 'R1BKQBNR-PPP1PPPP-2N5-3P4-3p4-8-ppp1pppp-rnbkqbnr')

	def test_case_sensitivity(self):
		self.handle_message(nateid, 'E4', expected_replies=3)
		self.assertLastMessageEquals(jessid, 'Nate played e4')
		self.assertLastGameRepEquals(nateid, 'rnbqkbnr-pppppppp-8-8-4P3-8-PPPP1PPP-RNBQKBNR')
		self.assertLastGameRepEquals(jessid, 'RNBKQBNR-PPP1PPPP-8-3P4-8-8-pppppppp-rnbkqbnr')

		self.handle_message(jessid, 'E5', expected_replies=3)
		self.assertLastMessageEquals(nateid, 'Jess played e5')
		# Now note the target_index's - handle_move doesn't use show_to_both
		self.assertLastGameRepEquals(nateid, 'rnbqkbnr-pppp1ppp-8-4p3-4P3-8-PPPP1PPP-RNBQKBNR')
		self.assertLastGameRepEquals(jessid, 'RNBKQBNR-PPP1PPPP-8-3P4-3p4-8-ppp1pppp-rnbkqbnr')

		self.handle_message(nateid, 'nf3', expected_replies=3)
		self.assertLastMessageEquals(jessid, 'Nate played Nf3')
		self.assertLastGameRepEquals(nateid, 'rnbqkbnr-pppp1ppp-8-4p3-4P3-5N2-PPPP1PPP-RNBQKB1R')
		self.assertLastGameRepEquals(jessid, 'R1BKQBNR-PPP1PPPP-2N5-3P4-3p4-8-ppp1pppp-rnbkqbnr')



	def test_cannot_make_impossible_move(self):
		self.handle_message(nateid, 'e5', expected_replies=1)
		self.assertLastMessageEquals(nateid, 'That is an invalid move')

		self.handle_message(nateid, 'Ke2', expected_replies=1)
		self.assertLastMessageEquals(nateid, 'That is an invalid move')

		self.handle_message(nateid, 'e4', expected_replies=None)
		self.handle_message(jessid, 'e7', expected_replies=1)
		self.assertLastMessageEquals(jessid, 'That is an invalid move')

	def test_cannot_move_on_opponent_turn(self):
		self.handle_message(jessid, 'e5', expected_replies=1)
		self.assertLastMessageEquals(jessid, "It isn't your turn")


	def test_ambiguous_move(self):
		self.perform_moves(nateid, jessid, [('e4', 'f5'), ('c4', 'd5')])

		with self.subTest('cannot make ambiguous move'):
			self.handle_message(nateid, 'd5', expected_replies=1)
			self.assertLastMessageEquals(nateid, 'That move could refer to two or more pieces')
		
		with self.subTest('rank still ambiguous'):
			# self.perform_moves(nateid, jessid, [('e4', 'f5'), ('c4', 'd5')])
			self.handle_message(nateid, '4d5', expected_replies=1)
			self.assertLastMessageEquals(nateid, 'That move could refer to two or more pieces')

		with self.subTest('can qualify file'):
			self.perform_moves(nateid, jessid, [('e4', 'f5'), ('c4', 'd5')])
			self.handle_message(nateid, 'cd5', expected_replies=3)
			self.assertLastGameRepEquals(nateid, 'rnbqkbnr-ppp1p1pp-8-3P1p2-4P3-8-PP1P1PPP-RNBQKBNR')

	def test_ambiguous_moveII(self):
		self.perform_moves(nateid, jessid, [('Nf3', 'h6'), ('Na3', 'g6'), ('Nc4', 'a6')], False)
		with self.subTest('cannot make ambiguous move'):
			self.handle_message(nateid, 'Ne5', expected_replies=1)
			self.assertLastMessageEquals(nateid, 'That move could refer to two or more pieces')

		with self.subTest('can qualify ambiguous move'):
			self.handle_message(nateid, 'Nfe5', expected_replies=3)
			self.assertLastGameRepEquals(nateid, 'rnbqkbnr-1ppppp2-p5pp-4N3-2N5-8-PPPPPPPP-R1BQKB1R')

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
		self.handle_message(nateid, 'Bf3', expected_replies=3)

	def test_can_make_case_insensitive_pawn_move(self):
		self.handle_message(nateid, 'E4', expected_replies=3)
		self.assertLastGameRepEquals(nateid, 'rnbqkbnr-pppppppp-8-8-4P3-8-PPPP1PPP-RNBQKBNR')

	def test_can_qualify_pawn_move_piece(self):
		self.handle_message(nateid, 'Pe4', expected_replies=3)
		self.assertLastGameRepEquals(nateid, 'rnbqkbnr-pppppppp-8-8-4P3-8-PPPP1PPP-RNBQKBNR')

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
			self.handle_message(nateid, 'e8=Q', expected_replies=3)
			self.assertLastGameRepEquals(nateid, '4Q3-1k6-8-8-8-8-8-1K6')

		with self.subTest('Verbose (lower)'):
			self.set_position(board)
			self.handle_message(nateid, 'e8=q', expected_replies=3)
			self.assertLastGameRepEquals(nateid, '4Q3-1k6-8-8-8-8-8-1K6')

		with self.subTest('Minimal'):
			self.set_position(board)
			self.handle_message(nateid, 'e8Q', expected_replies=3)
			self.assertLastGameRepEquals(nateid, '4Q3-1k6-8-8-8-8-8-1K6')

		with self.subTest('Minimal (lower)'):
			self.set_position(board)
			self.handle_message(nateid, 'e8q', expected_replies=3)
			self.assertLastGameRepEquals(nateid, '4Q3-1k6-8-8-8-8-8-1K6')

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
			self.handle_message(nateid, 'O-O-O', expected_replies=3)
			self.assertLastGameRepEquals(nateid, 'r3k2r-8-8-8-8-8-8-2KR3R')

		with self.subTest('Long - 0s'):
			self.set_position(board)
			self.handle_message(nateid, '0-0-0', expected_replies=3)
			self.assertLastGameRepEquals(nateid, 'r3k2r-8-8-8-8-8-8-2KR3R')

	def test_check(self):
		self.perform_moves(nateid, jessid, [('e4', 'f5')])
		clear_mocks()
		self.handle_message(nateid, 'Qh5', expected_replies=5)
		self.assertLastMessageEquals(jessid, 'Nate played Qh5', target_index=-2)
		self.assertLastMessageEquals(jessid, 'Check!', target_index=-1)
		self.assertLastMessageEquals(nateid, 'Check!')

class TestUndo(GamePlayTest):
	def test_undo(self):
		with self.subTest('can offer'):
			self.handle_message(nateid, 'e4', expected_replies=None)
			with self.db.cursor() as cur:
				cur.execute('SELECT undo FROM games')
				self.assertEqual(cur.fetchone()[0], False)
			clear_mocks()
			self.handle_message(nateid, 'undo', expected_replies=1)
			with self.db.cursor() as cur:
				cur.execute('SELECT undo FROM games')
				self.assertEqual(cur.fetchone()[0], True)
			self.assertLastMessageEquals(jessid, 'Nate has requested an undo')

		with self.subTest('can accept'):
			self.handle_message(jessid, 'undo', expected_replies=3)
			self.assertLastMessageEquals(nateid, 'Jess accepted your undo request')
			self.assertLastGameRepEquals(nateid, 'rnbqkbnr-pppppppp-8-8-8-8-PPPPPPPP-RNBQKBNR')
			self.assertLastGameRepEquals(jessid, 'RNBKQBNR-PPPPPPPP-8-8-8-8-pppppppp-rnbkqbnr')
			with self.db.cursor() as cur:
				cur.execute('SELECT undo FROM games')
				self.assertEqual(cur.fetchone()[0], False)

	def test_undo_rejected(self):
		self.handle_message(nateid, 'e4', expected_replies=None)
		self.handle_message(nateid, 'undo', expected_replies=None)
		clear_mocks()
		self.handle_message(jessid, 'e5', expected_replies=3)
		with self.db.cursor() as cur:
			cur.execute('SELECT undo FROM games')
			self.assertEqual(cur.fetchone()[0], False)

	def test_cannot_undo_on_your_turn(self):
		self.handle_message(nateid, 'e4', expected_replies=None)
		self.handle_message(jessid, 'undo', expected_replies=1)
		self.assertLastMessageEquals(jessid, "You can't request an undo when it is your turn")
		with self.db.cursor() as cur:
			cur.execute('SELECT undo FROM games')
			self.assertEqual(cur.fetchone()[0], False)

	def test_cannot_undo_before_first_move(self):
		self.handle_message(jessid, 'undo', expected_replies=1)
		self.assertLastMessageEquals(jessid, "You haven't made any moves to undo")
		with self.db.cursor() as cur:
			cur.execute('SELECT undo FROM games')
			self.assertEqual(cur.fetchone()[0], False)

	def test_cannot_undo_without_active_game(self):
		with self.subTest('Unregistered'):
			self.handle_message(izzyid, 'undo', expected_replies=1)
			self.assertLastMessageEquals(izzyid, constants.intro)

		with self.subTest('Registered...?'):
			self.handle_message(chadid, 'undo', expected_replies=1)
			self.assertLastMessageEquals(chadid, 'You have no active games')

	def test_cannot_undo_without_active_gameII(self):
		self.handle_message(nateid, 'resign', expected_replies=None)
		self.handle_message(nateid, 'undo', expected_replies=1)
		self.assertLastMessageEquals(nateid, 'You have no active games with Jess')

	def test_redundant_undo_request(self):
		self.handle_message(nateid, 'e4', expected_replies=None)
		self.handle_message(nateid, 'undo', expected_replies=None)
		clear_mocks()
		self.handle_message(nateid, 'undo', expected_replies=1)
		self.assertLastMessageEquals(nateid, 'You have already requested an undo')



class TestGameFinish(GamePlayTest):
	def test_checkmate(self):
		self.perform_moves(nateid, jessid, [('f4', 'e5'), ('g4',)] )
		with self.subTest('Player communication'):
			self.handle_message(jessid, 'Qh4', expected_replies=5)
			self.assertLastMessageEquals(jessid, 'Checkmate! Jess wins!')
			self.assertLastMessageEquals(nateid, 'Jess played Qh4', target_index=-2)
			self.assertLastMessageEquals(nateid, 'Checkmate! Jess wins!', target_index=-1)

		with self.subTest('Outcome is set'):
			with self.db.cursor() as cur:
				cur.execute('SELECT outcome FROM games')
				self.assertEqual(cur.fetchone()[0], fbchessbot.BLACK_WINS)

		with self.subTest('Game is inactive'):
			with self.db.cursor() as cur:
				cur.execute('SELECT active FROM games')
				self.assertEqual(cur.fetchone()[0], False)

	def test_checkmate_ends_game(self):
		self.perform_moves(nateid, jessid, [('f4', 'e5'), ('g4', 'Qh4')] )
		with self.subTest('Game is inactive'):
			_, _, game = self.db.get_context(nateid)
			self.assertEqual(game, None)

		with self.subTest('Outcome is win for black'):
			with self.db.cursor() as cur:
				cur.execute('SELECT outcome FROM games')
				self.assertEqual(cur.fetchone()[0], 2)

	def test_resign(self):
		self.handle_message(nateid, 'resign', expected_replies=2)
		self.assertLastMessageEquals(nateid, 'Nate resigns. Jess wins!')
		self.assertLastMessageEquals(jessid, 'Nate resigns. Jess wins!')
		with self.db.cursor() as cur:
			cur.execute('SELECT outcome FROM games')
			self.assertEqual(cur.fetchone()[0], fbchessbot.BLACK_WINS)
		with self.db.cursor() as cur:
			cur.execute('SELECT active FROM games')
			self.assertEqual(cur.fetchone()[0], False)

	def test_resign_without_game(self):
		self.handle_message(chadid, 'resign', expected_replies=1)
		self.assertLastMessageEquals(chadid, 'You have no active games')

	@unittest.skip
	def test_draw(self):
		pass

class TestMiscellaneous(GamePlayTest):
	def test_show(self):
		with self.subTest('Unregistered'):
			self.handle_message(izzyid, 'show', expected_replies=1)
			self.assertLastMessageEquals(izzyid, constants.intro)

		with self.subTest('Without game'):
			self.handle_message(chadid, 'show', expected_replies=1)
			self.assertLastMessageEquals(chadid, 'You have no active games')

		with self.subTest('With game - White'):
			self.handle_message(nateid, 'show', expected_replies=2)
			self.assertLastGameRepEquals(nateid, 'rnbqkbnr-pppppppp-8-8-8-8-PPPPPPPP-RNBQKBNR')
			self.assertLastMessageEquals(nateid, 'White to move')

		with self.subTest('With game - Black'):
			self.handle_message(jessid, 'show', expected_replies=2)
			self.assertLastGameRepEquals(jessid, 'RNBKQBNR-PPPPPPPP-8-8-8-8-pppppppp-rnbkqbnr')
			self.assertLastMessageEquals(jessid, 'White to move')

	def test_help(self):
		self.handle_message(nateid, 'help')
		self.assertLastMessageEquals(nateid, 'Help text coming soon...')

	# Maybe should also test with unregistered user
	def test_empty(self):
		self.handle_message(nateid, '')
		self.assertLastMessageEquals(nateid, 'That is an invalid move')

	@unittest.skip
	def test_pgn(self):
		pass

	@unittest.skip
	def test_pgns(self):
		pass

	@unittest.skip
	def test_stats(self):
		pass
		# self.handle_message(nateid, 'stats', expected_replies=1)

	@unittest.skip
	def test_status(self):
		pass
		# self.handle_message(nateid, 'status', expected_replies=1)

class TestPlayerInteractions(BaseTest):
	def init_blocks(self):
		self.handle_message(nateid, 'Play against Jess')
		self.handle_message(jessid, 'Play against Nate')
		self.handle_message(nateid, 'Block Jess')

	def setUp(self):
		self.register_all()

	def test_can_block_newly_registered(self):
		with self.subTest('Block notifications'):
			self.handle_message(nateid, 'Block jess', expected_replies=1)
			self.assertLastMessageEquals(nateid, 'You have blocked Jess')
			# self.assertLastMessageEquals(jessid, 'You have been blocked by Nate')

		with self.subTest('Block effects'):
			self.handle_message(nateid, 'Play against Jess', expected_replies=1)
			self.assertLastMessageEquals(nateid, 'You have blocked Jess')

			self.handle_message(jessid, 'Play against Nate', expected_replies=1)
			self.assertLastMessageEquals(jessid, 'You have been blocked by Nate')

	def test_can_block_redundant(self):
		self.handle_message(nateid, 'Block jess', expected_replies=1)
		self.handle_message(nateid, 'Block jess', expected_replies=1)
		self.assertLastMessageEquals(nateid, 'You have already blocked Jess')

	def test_can_mutual_block(self):
		self.handle_message(nateid, 'Block jess', expected_replies=1)
		self.handle_message(jessid, 'Block nate', expected_replies=1)
		# self.assertLastMessageEquals(nateid, 'You have been blocked by Jess')
		self.assertLastMessageEquals(jessid, 'You have blocked Nate')

		with self.subTest('Self block message dominates'):
			self.handle_message(nateid, 'Play against jess', expected_replies=1)
			self.assertLastMessageEquals(nateid, 'You have blocked Jess')

			self.handle_message(jessid, 'Play against nate', expected_replies=1)
			self.assertLastMessageEquals(jessid, 'You have blocked Nate')

	def test_blocking_removes_game_context(self):
		pass


	@unittest.skip
	def test_can_block_all(self):
		with self.subTest('Sender notification'):
			self.handle_message(nateid, 'Block everyone', expected_replies=1)
			self.assertLastMessageEquals(nateid, 'You have blocked everyone')

		with self.subTest('Block effects'):
			self.handle_message(jessid, 'Play against Nate', expected_replies=1)
			self.assertLastMessageEquals(jessid, 'Nate is not accepting any challenges')

	@unittest.skip
	def test_can_block_strangers(self):
		with self.subTest('Sender notification'):
			self.handle_message(nateid, 'Block strangers', expected_replies=1)
			self.assertLastMessageEquals(nateid, 'Strangers will no longer be able to interact with you')

		with self.subTest('Stranger blocked'):
			self.handle_message(chadid, 'Play against Nate', expected_replies=1)
			self.assertLastMessageEquals(chadid, 'Nate is not accepting any challenges')

		with self.subTest('Friend not blocked'):
			self.handle_message(jessid, 'Play against Nate', expected_replies=1)
			self.assertLastMessageEquals(jessid, 'You are now playing against Nate')

	@unittest.skip
	def test_can_unblock_strangers(self):
		with self.subTest('Sender notification'):
			self.handle_message(nateid, 'Unblock strangers', expected_replies=1)
			self.assertLastMessageEquals(nateid, 'Strangers will now be able to interact with you')

		with self.subTest('Stranger unblocked'):
			self.handle_message(chadid, 'Play against Nate', expected_replies=1)
			self.assertLastMessageEquals(chadid, 'Nate is not accepting any challenges')

		with self.subTest('Friend still not blocked'):
			self.handle_message(jessid, 'Play against Nate', expected_replies=1)
			self.assertLastMessageEquals(jessid, 'You are now playing against Nate')

	def test_can_block_before_game_starts(self):
		pass

	def test_can_block_during_game(self):
		pass

	def test_can_unblock(self):
		self.handle_message(nateid, 'Block jess', expected_replies=1)

		self.handle_message(nateid, 'Unblock jess', expected_replies=1)
		self.assertLastMessageEquals(nateid, 'You have unblocked Jess')

class TestActivation(BaseTest):
	def setUp(self):
		self.register_all()

	def test_can_deactivate(self):
		self.handle_message(nateid, 'deactivate', expected_replies=1)
		self.assertLastMessageEquals(nateid, constants.deactivation_message)

	def test_can_reactivate(self):
		self.handle_message(nateid, 'activate', expected_replies=1)
		self.assertLastMessageEquals(nateid, constants.activation_message)

	def test_deactivated_player_cant_be_played_against(self):
		self.handle_message(nateid, 'Play against Jess')
		self.handle_message(nateid, 'New game white')
		self.handle_message(nateid, 'e4')
		self.handle_message(nateid, 'deactivate')
		self.handle_message(jessid, 'e5', expected_replies=1)
		self.assertLastMessageEquals(jessid, 'Nate has left Chessbot')

	def test_deactivated_player_cant_be_challenged(self):
		self.handle_message(nateid, 'deactivate')
		self.handle_message(jessid, 'Play against Nate', expected_replies=1)
		self.assertLastMessageEquals(jessid, 'Nate has left Chessbot')

	def test_deactivated_player_can_get_old_games(self):
		pass

	@unittest.expectedFailure
	def test_redundant_deactivation(self):
		self.handle_message(nateid, 'deactivate', expected_replies=1)
		self.handle_message(nateid, 'deactivate', expected_replies=1)
		self.assertLastMessageEquals(nateid, 'You are already deactivated')

	@unittest.expectedFailure
	def test_redundant_activation(self):
		# self.handle_message(nateid, 'activate', expected_replies=None)
		self.handle_message(nateid, 'activate', expected_replies=1)
		self.assertLastMessageEquals(nateid, 'You are already activated')



@unittest.skip
class TestChallengeAcceptance(BaseTest):
	def setUp(self):
		self.register_all()

	def test_newly_registered_autoaccept(self):
		self.handle_message(nateid, 'Play against jess', expected_replies=2)
		self.assertLastMessageEquals(nateid, 'You are now playing against Jess')

	def test_can_challenge_with_color(self):
		self.handle_message(nateid, 'Play against jess white', expected_replies=3)

if __name__ == '__main__':
	unittest.main()

if False:
	self = BaseTest()
	self.setUpClass()
	self.db.delete_all()
	self.handle_message(nateid, 'My name is Nate', expected_replies=None)
	self.handle_message(chadid, 'My name is Chad', expected_replies=None)
	self.handle_message(jessid, 'My name is Jess', expected_replies=None)
	self.handle_message(izzyid, 'My name is Izzy', expected_replies=None)
	# Just so we can be sure these two are playing each other
	self.handle_message(izzyid, 'Play against Jess', expected_replies=None)
	self.handle_message(jessid, 'Play against Izzy', expected_replies=None)
	self.handle_message(izzyid, 'new game white')
	# self.handle_message(izzyid, 'new game black')
	# self.handle_message(izzyid, 'new game white')
	# self.handle_message(izzyid, 'new game black')
