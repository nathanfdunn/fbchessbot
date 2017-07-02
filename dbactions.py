import collections
import os
import pickle
from urllib.parse import urlparse

import chess
import psycopg2

try:
	import env
except ModuleNotFoundError:
	# Heroku has us covered
	pass

DATABASE_URL = os.environ['DATABASE_URL']

Player = collections.namedtuple('Player', 'id nickname opponentid color')

class Game:
	def __init__(self, id, raw_board, active, whiteplayer, blackplayer, undo, outcome):
		self.id = id
		self.board = pickle.loads(bytes(raw_board))
		# Wow I don't use any of the stuff below
		self.active = active
		self.whiteplayer = whiteplayer
		self.blackplayer = blackplayer
		self.undo = undo
		self.outcome = outcome
		# self.black = None
		# self.white = None
		# if data_row is None:
		#   self.id = None
		#   self.active = False
		#   self.board = chess.Board()
		#   self.white = None
		#   self.black = None
		#   self.undo = False
		#   self.outcome = None
		# else:
		#   (self.id, 
		#   raw_board,
		#   self.active,
		#   self.white,
		#   self.black,
		#   self.undo,
		#   self.outcome) = data_row

		#   self.white, self.black = str(self.white), str(self.black)
		#   self.board = pickle.loads(bytes(raw_board))

	def display(self):
		print(self.board)

	# Technically it's just the board that's serialized
	def serialized(self):
		return pickle.dumps(self.board)

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

	@classmethod
	def from_empty(cls):
		pass


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
		return self.conn.cursor()

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

	# Meh, we'll just set active to false. Should be fine
	def set_outcome(self, game, outcome):
		with self.cursor() as cur:
			cur.execute('''
				UPDATE games SET active = FALSE, outcome = %s WHERE id = %s
				''', [outcome, game.id])
			cur.connection.commit()

	def create_new_game(self, whiteplayer, blackplayer):
		with self.cursor() as cur:
			# new_game = Game.from_empty()
			# TODO remove probably because we won't be able to start a new game if old isn't finished
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
				""", [pickle.dumps(chess.Board()), whiteplayer, blackplayer])
			cur.connection.commit()

	# def get_player_context(self, playerid):
	#     with self.cursor() as cur:
	#         cur.execute("""
	#             SELECT
	#                 p.id, p.nickname, p.opponent_context,
	#                 o.id, o.nickname, o.opponent_context
	#             FROM player p
	#             LEFT JOIN player o ON p.opponent_context = o.id
	#             WHERE p.id = %s
	#             """, [playerid])
	#         row = cur.fetchone()
	#         player = Player(row[0], row[1], row[2])
	#         opponent = None if row[2] is None else Player(row[3], row[4], row[5])
	#         return player, opponent

	def get_active_gameII(self, playerid):
		playerid = int(playerid)
		with self.cursor() as cur:
			cur.execute("""
				SELECT
					p.id, p.nickname, p.opponent_context,
					o.id, o.nickname, o.opponent_context,
					g.id, g.board, g.active, g.whiteplayer, g.blackplayer, g.undo, g.outcome
				FROM player p
				INNER JOIN player o ON p.opponent_context = o.id
				INNER JOIN games g ON g.blackplayer = p.id OR g.whiteplayer = p.id
				WHERE p.id = %s
					AND g.active = TRUE
					AND (
						(g.whiteplayer = p.id AND g.blackplayer = o.id)
						OR
						(g.whiteplayer = o.id AND g.blackplayer = p.id)
					)
				""", [playerid])
			row = cur.fetchone()            # should be the only one
			if row is None:
				return None

			player = Player(row[0], row[1], row[2], playerid == row[9])
			opponent = Player(row[3], row[4], row[5], playerid != row[9])
			if row[9] == playerid:          # if g.whiteplayer == playerid
				whiteplayer = player
				blackplayer = opponent
			else:
				whiteplayer = opponent
				blackplayer = player

			return Game(row[6], row[7], row[8], whiteplayer, blackplayer, row[11], row[12])

	# def get_active_game(self, playerid):
	# 	with self.cursor() as cur:
	# 		cur.execute("SELECT opponent_context FROM player WHERE id = %s", [playerid])
	# 		opponentid = cur.fetchone()
	# 		if opponentid:
	# 			opponentid = opponentid[0]
	# 			cur.execute("""
	# 				SELECT id, board, active, whiteplayer, blackplayer, undo, outcome
	# 				FROM games WHERE
	# 				active = TRUE AND (
	# 					(whiteplayer = %s AND blackplayer = %s)
	# 					OR
	# 					(blackplayer = %s AND whiteplayer = %s)
	# 				)
	# 				""", [playerid, opponentid, playerid, opponentid])
	# 			# For now we don't want to impact the game if there is something wrong
	# 			# assert cur.rowcount <= 1
	# 			result = cur.fetchone()
	# 			if result:
	# 				return Game(result)
    #
	# 			return None
	# 		else:           # no active game
	# 			return None

	def board_from_id(self, game_id):
		with self.cursor() as cur:
			cur.execute("""
				SELECT board
				FROM games WHERE 
				id = %s
				""", [game_id])
			# Assumes there will be a match
			return pickle.loads(bytes(cur.fetchone()[0]))

	# def user_is_registered(self, sender):
	#     with self.cursor() as cur:
	#         cur.execute('SELECT COUNT(*) FROM player WHERE id = %s', [int(sender)])
	#         return bool(cur.fetchone()[0])

	def set_nickname(self, sender, nickname):
		playerid = int(sender)
		with self.cursor() as cur:
			cur.execute('SELECT COUNT(*) FROM player WHERE id = %s', [playerid])
			user_exists = cur.fetchone()[0]
			# user_exists = self.user_is_registered(sender)
			# if cur.fetchone():    # user already exists
			print('user_exists', user_exists)
			if user_exists:
				# print('user existed')
				cur.execute('UPDATE player SET nickname = %s WHERE id = %s', [nickname, playerid])
				cur.connection.commit()
				return False
			else:               # user does not exist
				# print('user does not exist')
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
			# cur.execute('UPDATE player SET opponent_context = %s WHERE id = %s', [challengerid, opponentid])
			cur.connection.commit()
	# def active_game(self, id):
	#   pass

	# def save_game(self, game):
	#   pass

	# def new_game(self, blackplayer, whiteplayer):
	#   pass

	# def user_exists(self, id):
	#   pass

	# def set_username(self, id, username):
	#   pass

	# def player_from_id(self, id):
	#   pass

	# def player_from_name(self, username):
	#   pass