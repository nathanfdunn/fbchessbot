import chess
import collections
import os
import pickle
import psycopg2
from urllib.parse import urlparse

try:
	import env
except ModuleNotFoundError:
	# Heroku has us covered
	pass

DATABASE_URL = os.environ['DATABASE_URL']

Player = collections.namedtuple('Player', 'id name opponent')

class Game:
	def __init__(self, data_row = None):
		if data_row is None:
			self.id = None
			self.active = False
			self.board = chess.Board()
			self.white = None
			self.black = None
			self.undo = False
		else:
			self.id, raw_board, self.active, self.white, self.black, self.undo = data_row
			self.white, self.black = str(self.white), str(self.black)
			self.board = pickle.loads(bytes(raw_board))

	def display(self):
		print(self.board)

		# Technically it's just the board that's serialized
	def serialized(self):
		return pickle.dumps(self.board)

	def image_url(self, perspective=True):
		BLACK = False
		fen = self.board.fen().split()[0]

		if perspective == BLACK:
			# fen = '/'.join(line[::-1] for line in reversed(fen.split('/')))
			# cool property of FEN
			fen = fen[::-1]

		fen = fen.replace('/', '-')
		return f'https://fbchessbot.herokuapp.com/image/{fen}'
		# return 'https://fbchessbot.herokuapp.com/image?fen=' + quote_plus(fen)

	def pgn_url(self):
		return f'https://fbchessbot.herokuapp.com/pgn/{self.id}.pgn'

	def is_active_player(self, playerid):
		WHITE = True
		if self.board.turn == WHITE:		
			return playerid == self.white
		else:
			return playerid == self.black


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

	def create_new_game(self, whiteplayer, blackplayer):
		with self.cursor() as cur:
			new_game = Game()
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
				""", [new_game.serialized(), whiteplayer, blackplayer])
			cur.connection.commit()

	def get_active_game(self, sender):
		with self.cursor() as cur:
			cur.execute("SELECT opponent_context FROM player WHERE id = %s", [sender])
			opponentid = cur.fetchone()
			if opponentid:
				opponentid = opponentid[0]
				cur.execute("""
					SELECT id, board, active, whiteplayer, blackplayer, undo
					FROM games WHERE 
					active = TRUE AND (
						(whiteplayer = %s AND blackplayer = %s)
						OR
						(blackplayer = %s AND whiteplayer = %s)
					)
					""", [sender, opponentid, sender, opponentid])
				# For now we don't want to impact the game if there is something wrong
				# assert cur.rowcount <= 1
				result = cur.fetchone()
				if result:
					return Game(result)

				return None
			else:			# no active game
				return None

	def game_from_id(self, game_id):
		with self.cursor() as cur:
			cur.execute("""
				SELECT id, board, active, whiteplayer, blackplayer, undo
				FROM games WHERE 
				id = %s
				""", [game_id])
			# Assumes there will be a match
			return Game(cur.fetchone())

	def user_is_registered(self, sender):
		with self.cursor() as cur:
			cur.execute('SELECT COUNT(*) FROM player WHERE id = %s', [int(sender)])
			return bool(cur.fetchone()[0])

	def set_nickname(self, sender, nickname):
		playerid = int(sender)
		with self.cursor() as cur:
			# cur.execute('SELECT COUNT(*) FROM player WHERE id = %s', [playerid])
			# user_exists = cur.fetchone()[0]
			user_exists = self.user_is_registered(sender)
			# if cur.fetchone():	# user already exists
			print('user_exists', user_exists)
			if user_exists:
				print('user existed')
				cur.execute('UPDATE player SET nickname = %s WHERE id = %s', [nickname, playerid])
				cur.connection.commit()
				return False
			else:				# user does not exist
				print('user does not exist')
				cur.execute('INSERT INTO player (id, nickname) VALUES (%s, %s)', [playerid, nickname])
				cur.connection.commit()
				return True

	def id_from_nickname(self, nickname):
		with self.cursor() as cur:
			cur.execute('SELECT id FROM player WHERE LOWER(nickname) = LOWER(%s)', [nickname])
			result = cur.fetchone()
			if result:
				return str(result[0])
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
	# 	pass

	# def save_game(self, game):
	# 	pass

	# def new_game(self, blackplayer, whiteplayer):
	# 	pass

	# def user_exists(self, id):
	# 	pass

	# def set_username(self, id, username):
	# 	pass

	# def player_from_id(self, id):
	# 	pass

	# def player_from_name(self, username):
	# 	pass