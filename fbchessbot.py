import functools
import json
import os
import re

import chess
import chess.pgn
from flask import Flask, request, send_file
from PIL import Image, ImageDraw
import requests

import dbactions
try:
	import env
except ModuleNotFoundError:
	# Heroku has us covered
	pass

VERIFY_TOKEN = os.environ['VERIFY_TOKEN']
PAGE_ACCESS_TOKEN = os.environ['PAGE_ACCESS_TOKEN']

WHITE = 1
BLACK = 0

# Outcome codes
WHITE_WINS = 1
BLACK_WINS = 2
DRAW = 3

db = dbactions.DB()

app = Flask(__name__)

@app.route('/image/<fen>', methods=['GET'])
def board_image(fen):
	board_image_name = f'/tmp/{fen}.png'
	fen = fen.replace('-', '/')  + ' w - - 0 1'
	board = chess.Board(fen)
	board_string_array = str(board).replace(' ', '').split('\n')
	board_image = create_board_image(board_string_array)
	board_image.save(board_image_name)
	return send_file(board_image_name)


@app.route('/pgn/<game_id>', methods=['GET'])
def board_pgn(game_id):
	print(f'Generating PGN for {game_id}')
	# game = db.game_from_id(game_id.strip('.pgn'))
	# print(game.board)
	board = db.board_from_id(game_id.strip('.pgn'))
	pgn = chess.pgn.Game.from_board(board)
	# print(pgn)
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


def messaging_events(payload):
	"""Generate tuples of (sender_id, message_text) from the
	provided payload.
	"""
	data = json.loads(payload)
	events = data["entry"][0]["messaging"]
	for event in events:
		if "message" in event and "text" in event["message"]:
			yield event["sender"]["id"], event["message"]["text"]
		else:
			yield event["sender"]["id"], "I can't echo this"


@app.route('/webhook', methods=['POST'])
@dontcrash
def messages():
	for sender, message in messaging_events(request.get_data()):
		message = message.strip()
		handle_message(sender, message)

	return 'ok'

def command(regex_or_func):
	if type(regex_or_func) is str:
		# Convention that regex args = they need a capture group
		regex = '^' + regex_or_func.replace(' ', r'\s+') + '$'
		def decorator(func):
			@functools.wraps(func)
			def wrapper(sender, message):
				m = re.match(regex, message.strip(), re.IGNORECASE)
				if not m:
					return False
				func(sender, m.groups()[0])
				return True
			commands.append(wrapper)
			return wrapper

		return decorator
	else:
		# Convention that directly wrapping = they only need senderid
		regex = '^' + regex_or_func.__name__ + '$'
		@functools.wraps(regex_or_func)
		def wrapper(sender, message):
			m = re.match(regex, message.strip(), re.IGNORECASE)
			if not m:
				return False
			regex_or_func(sender)
			return True
		commands.append(wrapper)
		return wrapper

def require_game(func):
	@functools.wraps(func)
	def wrapper(sender):
		game = db.get_active_gameII(sender)
		# TODO logic for if no active games with a specific person, etc.
		if not game:
			send_message(sender, 'You have no active games')
		else:
			func(sender, game)
	return wrapper

commands = []

def handle_message(sender, message):
	for func in commands:
		if func(sender, message):
			return

	(
		# handle_show(sender, message) or
		# handle_help(sender, message) or
		# handle_undo(sender, message) or
		# handle_register(sender, message) or
		handle_play(sender, message) or
		handle_new(sender, message) or
		handle_pgn(sender, message) or
		handle_resign(sender, message) or
		handle_move(sender, message)
	)

@command
@require_game
def show(sender, game):
	send_game_rep(sender, game)
	if game.is_active_color(WHITE):
		send_message(sender, 'White to move')
	else:
		send_message(sender, 'Black to move')

@command
def help(sender):
	send_message(sender, 'Help text coming soon...')

@command
@require_game
def undo(sender, game):
	g=game
	if g.undo:
		if g.is_active_player(sender):
			g.board.pop()
			db.set_undo_flag(g, False)
			db.save_game(g)
			opponentid = g.get_opponent(sender).id
			# opponentid = g.blackplayer.id if g.whiteplayer.id == sender else g.whiteplayer.id
			nickname = db.nickname_from_id(sender)
			send_message(opponentid, f'{nickname} accepted your undo request')
			show_game_to_both(g)
		else:
			send_message(sender, 'You have already requested an undo')
	else:
		# opponentid = g.blackplayer.id if g.whiteplayer.id == sender else g.whiteplayer.id
		opponentid = g.get_opponent(sender).id
		nickname = db.nickname_from_id(sender)
		db.set_undo_flag(g, True)
		send_message(opponentid, f'{nickname} has requested an undo')

# def handle_undo(sender, message):
# 	if not re.match(r'^\s*undo\s*$', message, re.IGNORECASE):
# 		return False
# 	sender = int(sender)
# 	g = db.get_active_gameII(sender)
# 	if not g:
# 		send_message(sender, 'You have no active games')
# 		return True
# 	if g.undo:
# 		if g.is_active_player(sender):
# 			g.board.pop()
# 			db.set_undo_flag(g, False)
# 			db.save_game(g)
# 			opponentid = g.blackplayer.id if g.whiteplayer.id == sender else g.whiteplayer.id
# 			nickname = db.nickname_from_id(sender)
# 			send_message(opponentid, f'{nickname} accepted your undo request')
# 			show_game_to_both(g)
# 		else:
# 			send_message(sender, 'You have already requested an undo')
# 	else:
# 		opponentid = g.blackplayer.id if g.whiteplayer.id == sender else g.whiteplayer.id
# 		nickname = db.nickname_from_id(sender)
# 		db.set_undo_flag(g, True)
# 		send_message(opponentid, f'{nickname} has requested an undo')
# 	return True

@command(r'my name is (\S*)')
def register(sender, nickname):
	print('calling from register: ', nickname)
	if len(nickname) > 32:
		send_message(sender, 'That nickname is too long (Try 32 or less characters)')

	elif re.match(r'^[a-z]+[0-9]*$', nickname, re.IGNORECASE):
		# nickname = m.groups()[0]
		user_is_new = db.set_nickname(sender, nickname)
		if user_is_new:
			send_message(sender, f'Nice to meet you {nickname}!')
		else:
			send_message(sender, f'I set your nickname to {nickname}')

	else:
		send_message(sender, r'Nickname must match regex [a-z]+[0-9]*')

	# elif re.match(r'^\s*my\s+name\s+is\s+', message, re.IGNORECASE):
	# 	send_message(sender, 'Nickname must match regex [a-z]+[0-9]*')
	# 	return True
	# else:
	# 	return False

# def handle_register(sender, message):
# 	m = re.match(r'^\s*my\s+name\s+is\s+([a-z]+[0-9]*)\s*$', message, re.IGNORECASE)
# 	if m:
# 		nickname = m.groups()[0]
# 		if len(nickname) > 32:
# 			send_message(sender, 'That nickname is too long (Try 32 or less characters)')
# 			return True
# 		user_is_new = db.set_nickname(sender, nickname)
# 		if user_is_new:
# 			send_message(sender, f'Nice to meet you {nickname}!')
# 		else:
# 			send_message(sender, f'I set your nickname to {nickname}')

# 		return True
# 	elif re.match(r'^\s*my\s+name\s+is\s+', message, re.IGNORECASE):
# 		send_message(sender, 'Nickname must match regex [a-z]+[0-9]*')
# 		return True
# 	else:
# 		return False


def handle_play(sender, message):
	playerid = int(sender)
	m = re.match(r'^\s*play\s+against\s+([a-z]+[0-9]*)$', message, re.IGNORECASE)
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
		g = db.get_active_gameII(sender)
		show_game_to_both(g)
		return True
	return False


def handle_pgn(sender, message):
	if re.match(r'^\s*pgn\s*$', message, re.IGNORECASE):
		# TODO switch to using the new method
		game = db.get_active_game_OBSOLETE(sender)
		send_pgn(sender, game)
		return True
	else:
		return False


def handle_resign(sender, message):
	sender = int(sender)
	if not re.match(r'^\s*resign\s*$', message, re.IGNORECASE):
		return False

	game = db.get_active_gameII(sender)
	if not game:
		send_message(sender, 'You have no active games')
		return True

	outcome = BLACK_WINS if sender == game.whiteplayer.id else WHITE_WINS
	db.set_outcome(game, outcome)
	opponentid = game.blackplayer.id if sender == game.whiteplayer.id else game.whiteplayer.id
	sender_nickname = db.nickname_from_id(sender)
	opponent_nickname = db.nickname_from_id(opponentid)
	send_message(game.whiteplayer.id, f'{sender_nickname} resigns. {opponent_nickname} wins!')
	send_message(game.blackplayer.id, f'{sender_nickname} resigns. {opponent_nickname} wins!')
	return True


def handle_move(sender, message):
	sender = int(sender)
	game = db.get_active_gameII(sender)
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

	opponentid = game.blackplayer.id if game.whiteplayer.id == sender else game.whiteplayer.id

	if sender == game.whiteplayer.id:
		send_game_rep(sender, game)
		send_message(opponentid, f'{nickname} played {message}')
		send_game_rep(opponentid, game, False)
	else:
		send_game_rep(sender, game, False)
		send_message(opponentid, f'{nickname} played {message}')
		send_game_rep(opponentid, game)
	
	if game.board.is_checkmate():
		outcome = WHITE_WINS if sender == game.whiteplayer.id else BLACK_WINS
		db.set_outcome(game, outcome)
		send_message(sender, f'Checkmate! {nickname} wins!')
		send_message(opponentid, f'Checkmate! {nickname} wins!')
	elif game.board.is_check():
		send_message(sender, 'Check!')
		send_message(opponentid, 'Check!')


def send_pgn(recipient, game):
	print('pgn url:', game.pgn_url())
	r = requests.post('https://graph.facebook.com/v2.9/me/messages',
		params={'access_token': PAGE_ACCESS_TOKEN},
		data=json.dumps({
			'recipient': {'id': recipient},
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
	recipient = str(recipient)			# this is probably the one place it's necessary to be a string
	r = requests.post('https://graph.facebook.com/v2.9/me/messages',
		params={'access_token': PAGE_ACCESS_TOKEN},
		data=json.dumps({
			'recipient': {'id': recipient},
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
	send_game_rep(game.whiteplayer.id, game)
	send_game_rep(game.blackplayer.id, game, False)


def send_message(recipient, text):
	r = requests.post('https://graph.facebook.com/v2.9/me/messages',
		params={'access_token': PAGE_ACCESS_TOKEN},
		data=json.dumps({
			'recipient': {'id': recipient},
			'message': {'text': text}
		}),
		headers={'Content-type': 'application/json'}
	)
	if r.status_code != requests.codes.ok:
		print('Error while sending message:', r.text)


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

if __name__ == '__main__':
	app.run(host='0.0.0.0')
