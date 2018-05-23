import collections
import datetime
import os
import pickle
from urllib.parse import urlparse

import chess
import psycopg2
import psycopg2.extras

import constants

try:
	import env
except ModuleNotFoundError:
	# Heroku has us covered
	pass

DATABASE_URL = os.environ['DATABASE_URL']

# # Person = collections.namedtuple('Person', 'id nickname')
# class Person:
# 	def __init__(self, id, nickname):
# 		self.id = id
# 		self.nickname = nickname

# 	def isregistered(self):
# 		return self.id is not None

Player = collections.namedtuple('Player', 'id nickname opponentid color active')

BlockResult = collections.namedtuple('BlockResult', 'success sender_not_found blocked_not_found is_redundant')

Reminder = collections.namedtuple('Reminder', 'whiteplayerid, whiteplayer_nickname, blackplayerid, blackplayer_nickname, white_to_play, days')

GameSummary = Reminder

class ChessBoard(chess.Board):
	def to_byte_string(self):
		original_fen = self.original_fen()
		blank = ChessBoard(original_fen)
		move_indices = []
		for move in self.move_stack:
			legal_moves = self._order_moves(blank)
			move_indices.append(legal_moves.index(move))
			blank.push(move)

		# Hopefully there can only ever be 255 legal moves in chess...
		# Pretty sure it's true for regular chess...maybe wrong for not real chess
		return original_fen.encode('ascii') + b'\xff' + bytes(move_indices)

	@staticmethod
	def _order_moves(board):
		'''Just an arbitrary ordering to be consistent'''
		return sorted(board.legal_moves, key=lambda move: move.uci())

	@classmethod
	def from_byte_string(cls, bytestring):
		original_fen, moves = bytestring.split(b'\xff')
		out = cls(original_fen.decode('ascii'))
		for byte in moves:
			legal_moves = cls._order_moves(out)
			out.push(legal_moves[byte])
		return out

	# TODO the only reason I have this is for my test framework...maybe remove???
	def original_fen(self):
		'''The fen that the game started with (not necessarily standard position)'''
		board = self.copy()			# This will actually be a standard chess.Board, not a ChessBoard
		while board.move_stack:
			board.pop()
		return board.fen()

	def image_url(self, perspective=True):
		fen = self.fen().split()[0].replace('/','-')
		query_arg = 'w' if perspective else 'b'

		return (f'https://fbchessbot.herokuapp.com/board/{fen}'
				f'?perspective={query_arg}')

	def get_img_urls(self):
		out = []
		while self.move_stack:
			self.pop()
			out.append(self.image_url())
		return out

		# BLACK = False
		# fen = self.board.fen().split()[0]

		# if perspective == BLACK:
		# 	fen = fen[::-1]

		# fen = fen.replace('/', '-')
		# return f'https://fbchessbot.herokuapp.com/image/{fen}'

	# def fen_history(self):
	# 	board = self.copy()
	# 	out = []
	# 	out.append(board.fen())
	# 	while board.move_stack:
	# 		board.pop()
	# 		out.append(board.fen())
		
	# 	return list(reversed(out))


class Game:
	def __init__(self, id, raw_board, active, whiteplayer, blackplayer, undo, outcome, last_moved_at_utc):
		self.id = id
		self.board = ChessBoard.from_byte_string(raw_board)

		self.active = active
		self.whiteplayer = whiteplayer
		self.blackplayer = blackplayer
		self.undo = undo
		self.outcome = outcome
		self.last_moved_at_utc = last_moved_at_utc

	# @classmethod
	# def fromboard(cls, board):
	# 	return cls(None, )

	def display(self):
		print(self.board)

	# Technically it's just the board that's serialized
	def serialized(self):
		return self.board.to_byte_string()

	# def fen_history(self):
	# 	board = self.copy()
	# 	out = []
	# 	out.append(board.fen())
	# 	while board.move_stack:
	# 		board.pop()
	# 		out.append(board.fen())
		
	# 	return list(reversed(out))

	def image_url(self, perspective=True):
		return self.board.image_url(perspective)
		# fen = self.board.fen().split()[0].replace('/','-')
		# query_arg = 'w' if perspective else 'b'

		# return (f'https://fbchessbot.herokuapp.com/board/{fen}'
		# 		f'?perspective={query_arg}')


		# BLACK = False
		# fen = self.board.fen().split()[0]

		# if perspective == BLACK:
		# 	fen = fen[::-1]

		# fen = fen.replace('/', '-')
		# return f'https://fbchessbot.herokuapp.com/image/{fen}'

	def pgn_url(self):
		return f'https://fbchessbot.herokuapp.com/pgn/{self.id}.pgn'

	def is_active_player(self, playerid):
		playerid = int(playerid)
		WHITE = True
		if self.board.turn == WHITE:        
			return playerid == self.whiteplayer.id
		else:
			return playerid == self.blackplayer.id

	def is_active_color(self, color):
		return self.board.turn == color

	def get_opponent(self, playerid):
		playerid = int(playerid)
		if self.blackplayer.id == playerid:
			return self.whiteplayer
		elif self.whiteplayer.id == playerid:
			return self.blackplayer
		else:
			raise ValueError(f'{playerid} is not in this game. {self.blackplayer}, {self.whiteplayer}')

class DB:
	def __init__(self):
		try:
			url = urlparse(DATABASE_URL)
			self.conn = psycopg2.connect(
				database=url.path[1:],
				user=url.username,
				password=url.password,
				host=url.hostname,
				port=url.port
			)
		except psycopg2.OperationalError:
			# This happens when we're testing against
			# our local postgres db (hack)
			self.conn = psycopg2.connect(DATABASE_URL)
		self.conn.autocommit = True
		self.now_provider = datetime.datetime
		# self.now_provider = None

	def __del__(self):
		self.conn.close()

	def delete_all(self):
		with self.cursor() as cur:
			cur.execute('''
				DELETE FROM player_blockage
				''')
			cur.execute('''
				DELETE FROM games
				''')
			cur.execute('''
				DELETE FROM player
				''')
			# cur.connection.commit()

	def cursor(self):
		# return self.conn.cursor()
		return self.conn.cursor(cursor_factory=psycopg2.extras.NamedTupleCursor)

	# def get_stats(self, playerid):
	# 	pass

	# def get_status(self, playerid):
	# 	pass

	# Just saves the serialized board
	def save_game(self, game):
		with self.cursor() as cur:
			cur.execute('''
				SELECT  cb.update_game(
					_gameid=>%s,
					_boardstate=>%s,
					_last_moved_at_utc=>%s,
					_white_to_play=>%s);
				''', [game.id, game.serialized(), self.now_provider.utcnow(), game.is_active_player(constants.WHITE)])
			# cur.execute('''
			# 	UPDATE games SET board = %s WHERE id = %s
			# 	''', [game.serialized(), game.id])
			# cur.connection.commit()

	def set_undo_flag(self, game, undo_flag):
		with self.cursor() as cur:
			cur.execute('''
				UPDATE games SET undo = %s WHERE id = %s
				''', [undo_flag, game.id])
			# cur.connection.commit()

	# Also 'finishes' the game by setting active to false
	def set_outcome(self, game, outcome):
		with self.cursor() as cur:
			cur.execute('''
				UPDATE games SET active = FALSE, outcome = %s WHERE id = %s
				''', [int(outcome), game.id])
			# cur.connection.commit()

	def create_new_game(self, whiteplayer, blackplayer):
		with self.cursor() as cur:
			cur.execute('''
				SELECT cb.create_game(%s, %s, %s, %s)
				''', [whiteplayer, blackplayer, ChessBoard().to_byte_string(), self.now_provider.utcnow()])

	# TODO wrap this into a form of search_games...?
	# Returns specified Player, opponent Player, active Game
	def get_context(self, playerid):
		with self.cursor() as cur:
			cur.execute('''
				SELECT playerid, player_nickname, player_opponentid, player_active,
					opponentid, opponent_nickname, opponent_opponentid, opponent_active,
					gameid, board, active, whiteplayer, blackplayer, undo, outcome, last_moved_at_utc
				FROM cb.get_context(%s)
				''', [playerid])
			# cur.connection.commit()
			row = cur.fetchone()
			if row is None:						# user isn't even registered
				return None, None, None

			if row.whiteplayer is None:					# Indicates there is no game
				player_color = None 			# so they have no color
				opponent_color = None
			else:
				player_color = constants.WHITE if playerid == row.whiteplayer else constants.BLACK
				opponent_color = not player_color

			player = Player(row.playerid, row.player_nickname, row.player_opponentid, player_color, row.player_active)
			if row.opponentid is None:
				opponent = None
			else:
				opponent = Player(row.opponentid, row.opponent_nickname, row.opponent_opponentid, opponent_color, row.opponent_active)

			if row.whiteplayer == playerid:
				whiteplayer = player
				blackplayer = opponent
			else:
				whiteplayer = opponent
				blackplayer = player

			if row.gameid is None:
				game = None
			else:
				game = Game(row.gameid, bytes(row.board), row.active, whiteplayer, blackplayer, row.undo, row.outcome, row.last_moved_at_utc)

			return player, opponent, game

	# def get_most_recent_game(self, playerid):
	# 	with self.cursor() as cur:
	# 		cur.execute("""
	# 			SELECT id, board FROM games WHERE id = (SELECT max(id) FROM games)
	# 			""")

	# 		gameid = 
	# 		board = ChessBoard.from_byte_string(bytes(cur.fetchone()[0]))
	# 		return Game()
	# 		id, raw_board, active, whiteplayer, blackplayer, undo, outcome):
	def get_most_recent_gameid(self, playerid):
		with self.cursor() as cur:
			cur.execute("""
				SELECT max(id) FROM games WHERE (blackplayer = %s OR whiteplayer = %s)
				""", [playerid, playerid])
			# cur.connection.commit()
			return cur.fetchone()[0]


	def board_from_id(self, gameid):
		with self.cursor() as cur:
			cur.execute("""
				SELECT board
				FROM games WHERE 
				id = %s
				""", [gameid])
			# cur.connection.commit()
			# Assumes there will be a match
			return ChessBoard.from_byte_string(bytes(cur.fetchone()[0]))

	def set_nickname(self, sender, nickname):
		playerid = int(sender)
		with self.cursor() as cur:
			cur.execute('SELECT COUNT(*) FROM player WHERE id = %s', [playerid])
			user_exists = cur.fetchone()[0]

			if user_exists:
				cur.execute('UPDATE player SET nickname = %s WHERE id = %s', [nickname, playerid])
				# cur.connection.commit()
				return False
			else:               # user does not exist
				cur.execute('INSERT INTO player (id, nickname) VALUES (%s, %s)', [playerid, nickname])
				# cur.connection.commit()
				return True

	def id_from_nickname(self, nickname):
		with self.cursor() as cur:
			# cur.execute('SELECT id FROM player WHERE LOWER(nickname) = LOWER(%s)', [nickname])
			cur.execute('SELECT cb.get_playerid(%s)', [nickname])
			result = cur.fetchone()
			# cur.connection.commit()
			if result:
				return result[0]
			return None

	def nickname_from_id(self, playerid):
		with self.cursor() as cur:
			cur.execute('SELECT nickname FROM player WHERE id = %s', [playerid])
			result = cur.fetchone()
			# cur.connection.commit()
			if result:
				return result[0]
			return None

	def get_opponent_context(self, playerid):
		with self.cursor() as cur:
			cur.execute('SELECT opponent_context FROM player WHERE id = %s', [playerid])
			result = cur.fetchone()
			# cur.connection.commit()
			if result:
				return result[0]
			return None

	def set_opponent_context(self, challengerid, opponentid):
		with self.cursor() as cur:
			cur.execute('UPDATE player SET opponent_context = %s WHERE id = %s', [opponentid, challengerid])
			# cur.connection.commit()

	def user_is_registered(self, playerid):
		with self.cursor() as cur:
			cur.execute('SELECT id FROM player WHERE id = %s', [playerid])
			result = cur.fetchone()
			# cur.connection.commit()
			return result is not None

	def player_from_nickname(self, nickname):
		with self.cursor() as cur:
			# cur.execute('SELECT id, nickname FROM player WHERE lower(nickname) = lower(%s)', [nickname])
			cur.execute('SELECT id, nickname, active FROM player WHERE id = cb.get_playerid(%s)', [nickname])
			# cur.connection.commit()
			result = cur.fetchone()
			# Don't like overloading this...see what happens for now
			if result is None:
				# return Player(None, nickname, None, None)
				return None
			else:
				return Player(result.id, result.nickname, None, None, result.active)

	def block_player(self, playerid, targetid):
		with self.cursor() as cur:
			cur.execute('''
				SELECT cb.block_player(%s, %s, TRUE)
				''', [playerid, targetid])
			# cur.connection.commit()
			return cur.fetchone()[0]

	def unblock_player(self, playerid, targetid):
		with self.cursor() as cur:
			cur.execute('''
				SELECT cb.block_player(%s, %s, FALSE)
				''', [playerid, targetid])
			# cur.connection.commit()
			return cur.fetchone()[0]

	def is_blocked(self, playerid, otherid):
		with self.cursor() as cur:
			cur.execute('''
				SELECT cb.blocked(%s, %s)
				''', [playerid, otherid])
			# cur.connection.commit()
			result = cur.fetchone()[0]
			return [(result & 1 > 0), (result & 2 > 0)]

	def log_message(self, message, message_type, *, senderid=None, recipientid=None):
		with self.cursor() as cur:
			# TODO make a function I guess
			cur.execute('''
				INSERT INTO cb.message_log (
					senderid,
					recipientid,
					message,
					message_typeid
				)
				VALUES (%s, %s, %s, %s)
				''', [senderid, recipientid, message, int(message_type)])
			# cur.connection.commit()

	def deactivate_player(self, playerid):
		with self.cursor() as cur:
			cur.execute('''
				UPDATE player SET active = FALSE WHERE id = %s
				''', [playerid])
			# cur.connection.commit()

	def set_player_activation(self, playerid, activate):
		with self.cursor() as cur:
			cur.execute('''
				UPDATE player SET active = %s WHERE id = %s
				''', [activate, playerid])
			# cur.connection.commit()

	def set_player_reminders(self, playerid, send_reminders):
		with self.cursor() as cur:
			cur.execute('''
				UPDATE player SET send_reminders = %s WHERE id = %s
				''', [send_reminders, playerid])

	def player_is_active(self, playerid):
		with self.cursor() as cur:
			cur.execute('''
				SELECT active FROM player WHERE id = %s
				''', [playerid])
			# cur.connection.commit()
			return cur.fetchone()[0]

	# def format_reminder(self, player_nickname, opponent_nickname, days):
	# 	return f"Hi {player_nickname}, I see you haven't made a move in your game with {opponent_nickname} in {days} days"

	# def get_game(gameid):
	# 	games = self.search_games(gameid=gameid)
	# 	if games:
	# 		return games[0]
	# 	return None

	# def search_games(self, *, gameid=None, now_utc=None, playerid=None, active=None, time_since_activity=None):
	# 	if now_utc is None:
	# 		now_utc = self.now_provider.utcnow()
	# 	with self.cursor() as cur:
	# 		cur.execute('''
	# 			SELECT whiteplayerid, whiteplayer_nickname, whiteplayer_send_reminders,
	# 				blackplayerid, blackplayer_nickname, blackplayer_send_reminders,
	# 				white_to_play,
	# 				delay,
	# 				board
	# 			FROM cb.search_games(_now_utc=>%s, _gameid=>%s, _playerid=>%s, _active=>%s, _time_since_activity=>%s)
	# 			''', [now_utc, playerid, active, time_since_activity])

	# 		out = []
	# 		for row in cur:
	# 			whiteplayer = Player(row.whiteplayerid, row.whiteplayer_nickname, None, constants.WHITE, None)
	# 			blackplayer = Player(row.blackplayerid, row.blackplayer_nickname, None, constants.BLACK, None)
	# 			game = Game(row.gameid, bytes(row.board), None, whiteplayer, blackplayer, None, None, None)

	# 		return game


	delay_threshold = 86400/2#86400*2
	# Returns a Dict[int, Set[Tuple[int, str, int, str, double]]]
	def get_reminders(self, delay_threshold=None):
		if delay_threshold is None:
			delay_threshold = self.delay_threshold
		out = collections.defaultdict(set)
		with self.cursor() as cur:
			cur.execute('''
				SELECT whiteplayerid, whiteplayer_nickname, whiteplayer_send_reminders,
					blackplayerid, blackplayer_nickname, blackplayer_send_reminders,
					white_to_play,
					delay
				FROM cb.search_games(%s)
				''', [self.now_provider.utcnow()])

			for value in cur:
				if value.delay < delay_threshold:
					continue

				# days = round(value.delay / 86400, 1)
				days = value.delay / 86400
				if value.whiteplayer_send_reminders and value.white_to_play:
					out[value.whiteplayerid].add(Reminder(
						value.whiteplayerid,
						value.whiteplayer_nickname,
						value.blackplayerid,
						value.blackplayer_nickname,
						value.white_to_play,
						days
						))
				if value.blackplayer_send_reminders and not value.white_to_play:
					out[value.blackplayerid].add(Reminder(
						value.whiteplayerid,
						value.whiteplayer_nickname,
						value.blackplayerid,
						value.blackplayer_nickname,
						value.white_to_play,
						days
						))
		return dict(out.items())