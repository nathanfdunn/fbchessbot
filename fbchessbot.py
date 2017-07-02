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
	board = db.board_from_id(game_id.strip('.pgn'))
	pgn = chess.pgn.Game.from_board(board)
	with open(game_id, 'w') as f:
		exporter = chess.pgn.FileExporter(f)
		pgn.accept(exporter)
	return send_file(game_id)


@app.route('/', methods=['GET'])
def hello():
	return '<h1>Hello</h1>'


@app.route('/webhook', methods=['GET'])
def verify():
	if request.args.get('hub.verify_token') == VERIFY_TOKEN:
		return request.args.get('hub.challenge', '')
	else:
		return 'Error, wrong validation token'


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
def messages():
	try:
		for sender, message in messaging_events(request.get_data()):
			sender, message = int(sender), message.strip()
			handle_message(sender, message)
	except Exception as e:
		print('Error handling messages:', repr(e))
	finally:
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
			if sender == game.whiteplayer.id:
				func(game.whiteplayer, game.blackplayer, game)
			else:
				func(game.blackplayer, game.whiteplayer, game)
	return wrapper

commands = []
def handle_message(sender, message):
	for func in commands:
		if func(sender, message):
			return
	handle_move(sender, message)


@command
@require_game
def show(player, opponent, game):
	send_game_rep(player.id, game)
	if game.is_active_color(WHITE):
		send_message(player.id, 'White to move')
	else:
		send_message(player.id, 'Black to move')


@command
def help(sender):
	send_message(sender, 'Help text coming soon...')


@command
@require_game
def undo(player, opponent, game):
	if game.undo:
		if game.is_active_player(player.id):
			game.board.pop()
			db.set_undo_flag(game, False)
			db.save_game(game)
			send_message(opponent.id, f'{player.nickname} accepted your undo request')
			show_game_to_both(game)
		else:
			send_message(player.id, 'You have already requested an undo')
	else:
		db.set_undo_flag(game, True)
		send_message(opponent.id, f'{player.nickname} has requested an undo')


@command(r'my name is (\S*)')
def register(sender, nickname):
	if len(nickname) > 32:
		send_message(sender, 'That nickname is too long (Try 32 or less characters)')

	elif re.match(r'^[a-z]+[0-9]*$', nickname, re.IGNORECASE):
		user_is_new = db.set_nickname(sender, nickname)
		if user_is_new:
			send_message(sender, f'Nice to meet you {nickname}!')
		else:
			send_message(sender, f'I set your nickname to {nickname}')

	else:
		send_message(sender, r'Nickname must match regex [a-z]+[0-9]*')


@command(r'play against (\S*)')
def play_against(sender, nickname):
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


@command(r'new game (\S*)')
def new_game(sender, color):
	color = color.lower()
	if color not in ['white', 'black']:
		send_message(sender, "Try either 'new game white' or 'new game black'")
		return
	opponentid = db.get_opponent_context(sender)
	if not opponentid:
		send_message(sender, "You aren't playing against anyone (Use command 'play against <name>')")
		return
	if color == 'white':
		whiteplayer, blackplayer = sender, opponentid
	else:
		whiteplayer, blackplayer = opponentid, sender
	nickname = db.nickname_from_id(sender)
	db.create_new_game(whiteplayer, blackplayer)
	send_message(opponentid, f'{nickname} started a new game')
	g = db.get_active_gameII(sender)
	show_game_to_both(g)


@command
def pgn(sender):
	game = db.get_active_gameII(sender)
	send_pgn(sender, game)


@command
@require_game
def resign(player, opponent, game):
	outcome = BLACK_WINS if player.color == WHITE else WHITE_WINS
	db.set_outcome(game, outcome)
	send_message(player.id, f'{player.nickname} resigns. {opponent.nickname} wins!')
	send_message(opponent.id, f'{player.nickname} resigns. {opponent.nickname} wins!')


def handle_move(sender, message):
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
		print('Error while sending image:', r.text)


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
