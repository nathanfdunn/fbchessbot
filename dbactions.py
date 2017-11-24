import collections
import os
import pickle
from urllib.parse import urlparse

import chess
import psycopg2
import psycopg2.extras

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

Player = collections.namedtuple('Player', 'id nickname opponentid color')

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

class Game:
	def __init__(self, id, raw_board, active, whiteplayer, blackplayer, undo, outcome):
		self.id = id
		# self.board = pickle.loads(bytes(raw_board))
		self.board = ChessBoard.from_byte_string(raw_board)

		self.active = active
		self.whiteplayer = whiteplayer
		self.blackplayer = blackplayer
		self.undo = undo
		self.outcome = outcome

	def display(self):
		print(self.board)

	# Technically it's just the board that's serialized
	def serialized(self):
		return self.board.to_byte_string()
		# return pickle.dumps(self.board)

	def image_url(self, perspective=True):
		BLACK = False
		fen = self.board.fen().split()[0]

		if perspective == BLACK:
			fen = fen[::-1]

		fen = fen.replace('/', '-')
		return f'https://fbchessbot.herokuapp.com/image/{fen}'

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

	def __del__(self):
		self.conn.close()

	def delete_all(self):
		with self.cursor() as cur:
			cur.execute('''
				DELETE FROM games
				''')
			cur.execute('''
				DELETE FROM player
				''')
			cur.connection.commit()

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
				UPDATE games SET board = %s WHERE id = %s
				''', [game.serialized(), game.id])
			cur.connection.commit()

	def set_undo_flag(self, game, undo_flag):
		with self.cursor() as cur:
			cur.execute('''
				UPDATE games SET undo = %s WHERE id = %s
				''', [undo_flag, game.id])
			cur.connection.commit()

	# Also 'finishes' the game by setting active to false
	def set_outcome(self, game, outcome):
		with self.cursor() as cur:
			cur.execute('''
				UPDATE games SET active = FALSE, outcome = %s WHERE id = %s
				''', [outcome, game.id])
			cur.connection.commit()

	def create_new_game(self, whiteplayer, blackplayer):
		with self.cursor() as cur:
			# There shouldn't be any active games...but I guess it doesn't hurt?
			cur.execute("""
				UPDATE games SET active = FALSE WHERE 
				(whiteplayer = %s AND blackplayer = %s)
				OR
				(blackplayer = %s AND whiteplayer = %s)
				""", [whiteplayer, blackplayer, whiteplayer, blackplayer])

			cur.execute("""
				INSERT INTO games (board, active, whiteplayer, blackplayer, undo) VALUES (
					%s, TRUE, %s, %s, FALSE
				)
				""", [ChessBoard().to_byte_string(), whiteplayer, blackplayer])
				# """, [pickle.dumps(chess.Board()), whiteplayer, blackplayer])
			cur.connection.commit()

	# Returns specified Player, opponent Player, active Game
	def get_context(self, player_id):
		with self.cursor() as cur:
			cur.execute("""
				SELECT
					p.id AS playerid, p.nickname AS player_nickname, p.opponent_context AS player_opponent_id,
					o.id AS opponentid, o.nickname AS opponent_nickname, o.opponent_context AS opponent_opponent_id,
					g.id AS gameid, g.board, g.active, g.whiteplayer, g.blackplayer, g.undo, g.outcome
				FROM player p
				LEFT JOIN player o ON p.opponent_context = o.id
				LEFT JOIN games g ON (
						(g.whiteplayer = p.id AND g.blackplayer = o.id) 
						OR 
						(g.blackplayer = p.id AND g.whiteplayer = o.id)
					)
					AND (g.active = TRUE)
				WHERE p.id = %s
				""", [player_id])
			row = cur.fetchone()
			if row is None:						# user isn't even registered
				return None, None, None

			if row[9] is None:					# Indicates there is no game
				player_color = None 			# so they have no color
				opponent_color = None
			else:
				player_color = (player_id == row[9])
				opponent_color = (player_id != row[9])

			player = Player(row[0], row[1], row[2], player_color)
			if row[3] is None:
				opponent = None
			else:
				opponent = Player(row[3], row[4], row[5], opponent_color)

			if row[9] == player_id:          # if g.whiteplayer == playerid
				whiteplayer = player
				blackplayer = opponent
			else:
				whiteplayer = opponent
				blackplayer = player

			if row[6] is None:
				game = None
			else:
				game = Game(row[6], bytes(row[7]), row[8], whiteplayer, blackplayer, row[11], row[12])

			return player, opponent, game


	def board_from_id(self, game_id):
		with self.cursor() as cur:
			cur.execute("""
				SELECT board
				FROM games WHERE 
				id = %s
				""", [game_id])
			# Assumes there will be a match
			# return pickle.loads(bytes(cur.fetchone()[0]))
			return ChessBoard.from_byte_string(bytes(cur.fetchone()[0]))

	def set_nickname(self, sender, nickname):
		playerid = int(sender)
		with self.cursor() as cur:
			cur.execute('SELECT COUNT(*) FROM player WHERE id = %s', [playerid])
			user_exists = cur.fetchone()[0]

			if user_exists:
				cur.execute('UPDATE player SET nickname = %s WHERE id = %s', [nickname, playerid])
				cur.connection.commit()
				return False
			else:               # user does not exist
				cur.execute('INSERT INTO player (id, nickname) VALUES (%s, %s)', [playerid, nickname])
				cur.connection.commit()
				return True

	def id_from_nickname(self, nickname):
		with self.cursor() as cur:
			cur.execute('SELECT id FROM player WHERE LOWER(nickname) = LOWER(%s)', [nickname])
			result = cur.fetchone()
			if result:
				return result[0]
			return None

	def nickname_from_id(self, playerid):
		with self.cursor() as cur:
			cur.execute('SELECT nickname FROM player WHERE id = %s', [playerid])
			result = cur.fetchone()
			if result:
				return result[0]
			return None

	def get_opponent_context(self, playerid):
		with self.cursor() as cur:
			cur.execute('SELECT opponent_context FROM player WHERE id = %s', [playerid])
			result = cur.fetchone()
			if result:
				return result[0]
			return None

	def set_opponent_context(self, challengerid, opponentid):
		with self.cursor() as cur:
			cur.execute('UPDATE player SET opponent_context = %s WHERE id = %s', [opponentid, challengerid])
			cur.connection.commit()

	def user_is_registered(self, playerid):
		with self.cursor() as cur:
			cur.execute('SELECT id FROM player WHERE id = %s', [playerid])
			result = cur.fetchone()
			return result is not None

	def player_from_nickname(self, nickname):
		with self.cursor() as cur:
			cur.execute('SELECT id, nickname FROM player WHERE nickname = %s', [nickname])
			result = cur.fetchone()
			# Don't like overloading this...see what happens for now
			if result is None:
				return Player(None, nickname, None, None)
			else:
				return Player(result[0], result[1], None, None)
