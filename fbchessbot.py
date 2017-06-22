import chess
import chess.pgn
from flask import Flask, request, send_file
import functools
import json
import os
# import pickle
from PIL import Image, ImageDraw
import psycopg2
import re
import requests
from urllib.parse import urlparse, quote_plus, unquote_plus
import dbactions

try:
	import env
except ModuleNotFoundError:
	# Heroku has us covered
	pass

VERIFY_TOKEN = os.environ['VERIFY_TOKEN']
PAGE_ACCESS_TOKEN = os.environ['PAGE_ACCESS_TOKEN']
DATABASE_URL = os.environ['DATABASE_URL']


db = dbactions.DB()

# class Game:
# 	def __init__(self, data_row = None):
# 		if data_row is None:
# 			self.id = None
# 			self.active = False
# 			self.board = chess.Board()
# 			self.white = None
# 			self.black = None
# 			self.undo = False
# 		else:
# 			self.id, raw_board, self.active, self.white, self.black, self.undo = data_row
# 			self.white, self.black = str(self.white), str(self.black)
# 			self.board = pickle.loads(bytes(raw_board))

# 	def display(self):
# 		print(self.board)

# 		# Technically it's just the board that's serialized
# 	def serialized(self):
# 		return pickle.dumps(self.board)

# 	def image_url(self, perspective=True):
# 		BLACK = False
# 		fen = self.board.fen().split()[0]

# 		if perspective == BLACK:
# 			fen = '/'.join(line[::-1] for line in reversed(fen.split('/')))

# 		fen = fen.replace('/', '-')
# 		return f'https://fbchessbot.herokuapp.com/image/{fen}'
# 		# return 'https://fbchessbot.herokuapp.com/image?fen=' + quote_plus(fen)

# 	def is_active_player(self, playerid):
# 		WHITE = True
# 		if self.board.turn == WHITE:		
# 			return playerid == self.white
# 		else:
# 			return playerid == self.black


# def get_cursor():
# 	url = urlparse(DATABASE_URL)
# 	conn = psycopg2.connect(
# 		database=url.path[1:],
# 		user=url.username,
# 		password=url.password,
# 		host=url.hostname,
# 		port=url.port
# 	)
# 	return conn.cursor()

# def get_active_game(sender):
# 	with get_cursor() as cur:
# 		cur.execute("SELECT opponent_context FROM player WHERE id = %s", [sender])
# 		opponentid = cur.fetchone()
# 		if opponentid:
# 			opponentid = opponentid[0]
# 			cur.execute("""
# 				SELECT id, board, active, whiteplayer, blackplayer, undo
# 				FROM games WHERE 
# 				active = TRUE AND (
# 					(whiteplayer = %s AND blackplayer = %s)
# 					OR
# 					(blackplayer = %s AND whiteplayer = %s)
# 				)
# 				""", [sender, opponentid, sender, opponentid])
# 			# For now we don't want to impact the game if there is something wrong
# 			# assert cur.rowcount <= 1
# 			result = cur.fetchone()
# 			if result:
# 				return Game(result)

# 			return None
# 		else:			# no active game
# 			return None

# def save_game(game):
# 	with get_cursor() as cur:
# 		cur.execute('''
# 			UPDATE games SET board = %s WHERE id = %s
# 			''', [game.serialized(), game.id])
# 		cur.connection.commit()

# def set_undo_flag(game, undo_flag):
# 	with get_cursor() as cur:
# 		cur.execute('''
# 			UPDATE games SET undo = %s WHERE id = %s
# 			''', [undo_flag, game.id])
# 		cur.connection.commit()

# def create_new_game(whiteplayer, blackplayer):
# 	with get_cursor() as cur:
# 		new_game = Game()
# 		# TODO remove probably because we won't be able to start a new game if old isn't finished
# 		cur.execute("""
# 			UPDATE games SET active = FALSE WHERE 
# 			(whiteplayer = %s AND blackplayer = %s)
# 			OR
# 			(blackplayer = %s AND whiteplayer = %s)
# 			""", [whiteplayer, blackplayer, whiteplayer, blackplayer])

# 		cur.execute("""
# 			INSERT INTO games (board, active, whiteplayer, blackplayer, undo) VALUES (
# 				%s, TRUE, %s, %s, FALSE
# 			)
# 			""", [new_game.serialized(), whiteplayer, blackplayer])
# 		cur.connection.commit()

app = Flask(__name__)

print('Ok, we made it to app instantiation')

@app.route('/image/<fen>', methods=['GET'])
def board_image(fen):
	print('Received image request')
	# if 'fen' not in request.args:
	# 	return 'Invalid FEN'
	# fen = unquote_plus(request.args.get('fen')) + ' w - - 0 1'
	board_image_name = f'/tmp/{fen}.png'

	fen = fen.replace('-', '/')  + ' w - - 0 1'

	print('decoded FEN', fen)

	board = chess.Board(fen)
	# board_image_name = '/tmp/' + str(board.board_zobrist_hash()) + '.png'

	# TODO test if image already exists
	print('board is', board)
	board_string_array = str(board).replace(' ', '').split('\n')
	board_image = create_board_image(board_string_array)

	board_image.save(board_image_name)
	return send_file(board_image_name)
	# print('fen', request.args.get('fen'))
	# print('blah', request.args)
	# print('huh', dir(request))
	# return send_file('board.png')

@app.route('/pgn/<game_id>', methods=['GET'])
def board_pgn(game_id):
	print(f'Generating PGN for {game_id}')
	game = db.game_from_id(game_id.strip('.pgn'))
	print(game.board)
	pgn = chess.pgn.Game.from_board(game.board)
	print(pgn)
	with open(game_id, 'w') as f:
		exporter = chess.pgn.FileExporter(f)
		pgn.accept(exporter)
	return send_file(game_id)


@app.route('/', methods=['GET'])
def hello():
	print('processing root get')
	return '<h1>Hello</h1>'

@app.route('/webhook', methods=['GET'])
def verify():
	print('Handling Verification')
	if request.args.get('hub.verify_token') == VERIFY_TOKEN:
		print('Verification successful')
		return request.args.get('hub.challenge', '')
	else:
		print('Verification failed')
		return 'Error, wrong validation token'


def dontcrash(func):
	@functools.wraps(func)
	def wrapper(*args, **kwargs):
		try:
			return func(*args, **kwargs)
		except Exception as e:
			print(repr(e))
			return 'ok'
	return wrapper

# import datetime

def handle_message(sender, message):
	(handle_show(sender, message)
		or handle_help(sender, message)
		or handle_undo(sender, message)
		or handle_register(sender, message)
		or handle_play(sender, message)
		or handle_new(sender, message)
		or handle_pgn(sender, message)
		or handle_move(sender, message)
	)

@app.route('/webhook', methods=['POST'])
@dontcrash
def messages():
	# with get_cursor() as cur:
	# 	cur.execute("""
	# 		INSERT INTO scratch (key, value) VALUES (%s, %s)
	# 		""", [str(datetime.datetime.now()), pickle.dumps(request)])
	print('Handling messages')
	for sender, message in messaging_events(request.get_data()):
		print('Incoming from {}: {}'.format(sender, message))
		message = message.strip()
		handle_message(sender, message)

	return 'ok'

def handle_show(sender, message):
	if re.match(r'^\s*show\s*$', message, re.IGNORECASE):
		game = db.get_active_game(sender)
		send_game_rep(sender, game, game.white == sender)
		active = 'White' if game.board.turn else 'Black'
		send_message(sender, active + ' to move')
		return True
	return False

def handle_pgn(sender, message):
	if re.match(r'^\s*pgn\s*$', message, re.IGNORECASE):
		game = db.get_active_game(sender)
		send_pgn(sender, game)
		return True
	else:
		return False

def handle_move(sender, message):
	game = db.get_active_game(sender)
	if not game:
		send_message(sender, 'You have no active games')
		return True

	if not game.is_active_player(sender):
		send_message(sender, "It isn't your turn")
		return True

	try:
		game.board.parse_san(message)
	except ValueError:
		send_message(sender, 'That is an invalid move')
		return True

	nickname = db.nickname_from_id(sender)
	game.board.push_san(message)
	db.save_game(game)
	db.set_undo_flag(game, False)

	opponentid = game.black if game.white == sender else game.white

	if sender == game.white:
		send_game_rep(sender, game)
		send_message(opponentid, f'{nickname} played {message}')
		send_game_rep(opponentid, game, False)
	else:
		send_game_rep(sender, game, False)
		send_message(opponentid, f'{nickname} played {message}')
		send_game_rep(opponentid, game)
	
	if game.board.is_checkmate():
		send_message(sender, f'Checkmate! {nickname} wins!')
		send_message(opponentid, f'Checkmate! {nickname} wins!')
	elif game.board.is_check():
		send_message(sender, 'Check!')
		send_message(opponentid, 'Check!')

	# send_game_rep(game, )

	pass

def handle_help(sender, message):
	if re.match(r'^\s*help\s*$', message, re.IGNORECASE):
		send_message(sender, 'Help text coming soon...')
		return True
	else:
		return False

def handle_undo(sender, message):
	if not re.match(r'^\s*undo\s*$', message, re.IGNORECASE):
		return False
	g = db.get_active_game(sender)
	if not g:
		send_message(sender, 'You have no active games')
		return True
	if g.undo:
		if g.is_active_player(sender):
			g.board.pop()
			db.set_undo_flag(g, False)
			db.save_game(g)
			opponentid = g.black if g.white == sender else g.white
			nickname = db.nickname_from_id(sender)
			send_message(opponentid, f'{nickname} accepted your undo request')
			show_game_to_both(g)
		else:
			send_message(sender, 'You have already requested an undo')
	else:
		opponentid = g.black if g.white == sender else g.white
		nickname = db.nickname_from_id(sender)
		db.set_undo_flag(g, True)
		send_message(opponentid, f'{nickname} has requested an undo')
	return True



# def user_is_registered(sender):
# 	with get_cursor() as cur:
# 		cur.execute('SELECT COUNT(*) FROM player WHERE id = %s', [int(sender)])
# 		return bool(cur.fetchone()[0])


def handle_register(sender, message):
	# send_message = lambda sender, message: print(f'Send message: {sender} - {message}')
	m = re.match(r'^my\s+name\s+is\s+([a-z]+[0-9]*)\s*$', message, re.IGNORECASE)
	if m:
		nickname = m.groups()[0]
		if len(nickname) > 32:
			send_message(sender, 'That nickname is too long (Try 32 or less characters)')
			return True
		user_is_new = db.set_nickname(sender, nickname)
		if user_is_new:
			send_message(sender, f'Nice to meet you {nickname}!')
		else:
			send_message(sender, f'I set your nickname to {nickname}')

		return True
	elif re.match(r'^my\s+name\s+is\s+', message, re.IGNORECASE):
		send_message(sender, 'Nickname must match regex [a-z]+[0-9]*')
		return True
	else:
		return False


# Returns True if user is new
# def set_nickname(sender, nickname):
# 	playerid = int(sender)
# 	with get_cursor() as cur:
# 		# cur.execute('SELECT COUNT(*) FROM player WHERE id = %s', [playerid])
# 		# user_exists = cur.fetchone()[0]
# 		user_exists = user_is_registered(sender)
# 		# if cur.fetchone():	# user already exists
# 		print('user_exists', user_exists)
# 		if user_exists:
# 			print('user existed')
# 			cur.execute('UPDATE player SET nickname = %s WHERE id = %s', [nickname, playerid])
# 			cur.connection.commit()
# 			return False
# 		else:				# user does not exist
# 			print('user does not exist')
# 			cur.execute('INSERT INTO player (id, nickname) VALUES (%s, %s)', [playerid, nickname])
# 			cur.connection.commit()
# 			return True

			# send_game_rep()

		# send_message(sender, message)
	# return 'ok'
	# return 200, 'ok'
# print('register', handle_register('83832204', 'mY naMe is JejaiSS'))
# exit()

# def id_from_nickname(nickname):
# 	with get_cursor() as cur:
# 		cur.execute('SELECT id FROM player WHERE LOWER(nickname) = LOWER(%s)', [nickname])
# 		result = cur.fetchone()
# 		if result:
# 			return str(result[0])
# 		return None

# def nickname_from_id(playerid):
# 	with get_cursor() as cur:
# 		cur.execute('SELECT nickname FROM player WHERE id = %s', [playerid])
# 		result = cur.fetchone()
# 		if result:
# 			return result[0]
# 		return None

# def get_opponent_context(playerid):
# 	with get_cursor() as cur:
# 		cur.execute('SELECT opponent_context FROM player WHERE id = %s', [playerid])
# 		result = cur.fetchone()
# 		if result:
# 			return result[0]
# 		return None

nateid = db.id_from_nickname('nate')
shawnid = db.id_from_nickname('shawn')

# def set_opponent_context(challengerid, opponentid):
# 	with get_cursor() as cur:
# 		cur.execute('UPDATE player SET opponent_context = %s WHERE id = %s', [opponentid, challengerid])
# 		cur.execute('UPDATE player SET opponent_context = %s WHERE id = %s', [challengerid, opponentid])
# 		cur.connection.commit()


def handle_play(sender, message):
	playerid = int(sender)
	m = re.match(r'^play\s+against\s+([a-z]+[0-9]*)$', message, re.IGNORECASE)
	if not m:
		return False

	nickname = m.groups()[0]
	opponentid = db.id_from_nickname(nickname)
	if opponentid:
		opponent_opponent_context = db.get_opponent_context(opponentid)
		if not opponent_opponent_context:
			sender_nickname = db.nickname_from_id(sender)
			db.set_opponent_context(opponentid, sender)
			send_message(opponentid, f'You are now playing against {sender_nickname}')
		db.set_opponent_context(sender, opponentid)
		send_message(sender, f'You are now playing against {nickname}')
	else:
		send_message(sender, f"No player named '{nickname}'")

	return True

def handle_new(sender, message):
	# playerid = int(sender)
	m = re.match(r'^new game (white|black)$', message, re.IGNORECASE)
	if m:
		opponentid = db.get_opponent_context(sender)
		if not opponentid:
			send_message(sender, "You aren't playing against anyone (Use command 'play against <name>')")
			return True
		color = m.groups()[0].lower()
		if color == 'white':
			whiteplayer, blackplayer = sender, opponentid
		else:
			whiteplayer, blackplayer = opponentid, sender
		nickname = db.nickname_from_id(sender)
		db.create_new_game(whiteplayer, blackplayer)
		send_message(opponentid, f'{nickname} started a new game')
		g = db.get_active_game(sender)
		show_game_to_both(g)
		return True
	return False

# print(set_nickname('8323', 'nate'))

def messaging_events(payload):
	"""Generate tuples of (sender_id, message_text) from the
	provided payload.
	"""
	data = json.loads(payload)
	events = data["entry"][0]["messaging"]
	for event in events:
		if "message" in event and "text" in event["message"]:
			yield event["sender"]["id"], event["message"]["text"]#event["message"]["text"].encode('unicode_escape')
		else:
			yield event["sender"]["id"], "I can't echo this"

def send_pgn(recipient, game):
	print('pgn url:', game.pgn_url())
	r = requests.post('https://graph.facebook.com/v2.9/me/messages',
		params={'access_token': PAGE_ACCESS_TOKEN},
		data=json.dumps({
			'recipient': {'id': recipient},
			# 'message': {'text': str(game.board)}
			'message': {
				'attachment': {
					'type': 'file',
					'payload': {
						'url': game.pgn_url()
					}
				}
			}
		}),
		headers={'Content-type': 'application/json'}
	)
	if r.status_code != requests.codes.ok:
		print('Error I think:', r.text)

def send_game_rep(recipient, game, perspective=True):
	r = requests.post('https://graph.facebook.com/v2.9/me/messages',
		params={'access_token': PAGE_ACCESS_TOKEN},
		data=json.dumps({
			'recipient': {'id': recipient},
			# 'message': {'text': str(game.board)}
			'message': {
				'attachment': {
					'type': 'image',
					'payload': {
						'url': game.image_url(perspective)
					}
				}
			}
		}),
		headers={'Content-type': 'application/json'}
	)
	if r.status_code != requests.codes.ok:
		print('Error I think:', r.text)

def show_game_to_both(game):
	send_game_rep(game.white, game)
	send_game_rep(game.black, game, False)


def send_message(recipient, text):
	r = requests.post('https://graph.facebook.com/v2.9/me/messages',
		params={'access_token': PAGE_ACCESS_TOKEN},
		data=json.dumps({
			'recipient': {'id': recipient},
			# 'message': {'text': text.decode('unicode_escape')}
			'message': {'text': text}
		}),
		headers={'Content-type': 'application/json'}
	)
	if r.status_code != requests.codes.ok:
		print('Error I think:', r.text)

def create_board_image(board):
	board_image = Image.open('board.png').copy()

	piece_image_map = {
		'r': 'sprites/blackrook.png',
		'n': 'sprites/blackknight.png',
		'b': 'sprites/blackbishop.png',
		'q': 'sprites/blackqueen.png',
		'k': 'sprites/blackking.png',
		'p': 'sprites/blackpawn.png',

		'R': 'sprites/whiterook.png',
		'N': 'sprites/whiteknight.png',
		'B': 'sprites/whitebishop.png',
		'Q': 'sprites/whitequeen.png',
		'K': 'sprites/whiteking.png',
		'P': 'sprites/whitepawn.png'
	}
	for i, row in enumerate(board):
		for j, piece in enumerate(row):
			if piece in piece_image_map:
				piece_image = Image.open(piece_image_map[piece])
				board_image.paste(piece_image, (64*j, 64*i), piece_image)

	return board_image

import sys

if sys.flags.debug:
	def send_message (sender, message):
		print(f'Send message: {sender} - {message}')
	def send_game_rep(recipient, game, perspective=True):
		url = game.image_url(perspective)
		print(f'Send game board: {recipient} - {url}')
	def send_pgn(recipient, game):
		url = game.pgn_url()
		print(f'Send pgn: {recipient} - {url}')

if __name__ == '__main__' and not sys.flags.debug and False:
	app.run(host='0.0.0.0')