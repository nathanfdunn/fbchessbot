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


def handle_message(sender, message):
	(handle_show(sender, message)
		or handle_help(sender, message)
		or handle_undo(sender, message)
		or handle_register(sender, message)
		or handle_play(sender, message)
		or handle_new(sender, message)
		or handle_pgn(sender, message)
		or handle_resign(sender, message)
		or handle_move(sender, message)
	)


def handle_show(sender, message):
	if re.match(r'^\s*show\s*$', message, re.IGNORECASE):
		game = db.get_active_game(sender)
		send_game_rep(sender, game, game.white == sender)
		active = 'White' if game.board.turn else 'Black'
		send_message(sender, active + ' to move')
		return True
	return False


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


def handle_register(sender, message):
	m = re.match(r'^\s*my\s+name\s+is\s+([a-z]+[0-9]*)\s*$', message, re.IGNORECASE)
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
	elif re.match(r'^\s*my\s+name\s+is\s+', message, re.IGNORECASE):
		send_message(sender, 'Nickname must match regex [a-z]+[0-9]*')
		return True
	else:
		return False


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
		g = db.get_active_game(sender)
		show_game_to_both(g)
		return True
	return False


def handle_pgn(sender, message):
	if re.match(r'^\s*pgn\s*$', message, re.IGNORECASE):
		game = db.get_active_game(sender)
		send_pgn(sender, game)
		return True
	else:
		return False


def handle_resign(sender, message):
	if not re.match(r'^\s*resign\s*$', message, re.IGNORECASE):
		return False

	game = db.get_active_game(sender)
	if not game:
		send_message(sender, 'You have no active games')
		return True

	outcome = BLACK_WINS if sender == game.white else WHITE_WINS
	db.set_outcome(game, outcome)
	opponentid = game.black if sender == game.white else game.white
	sender_nickname = db.nickname_from_id(sender)
	opponent_nickname = db.nickname_from_id(opponentid)
	send_message(game.white, f'{sender_nickname} resigns. {opponent_nickname} wins!')
	send_message(game.black, f'{sender_nickname} resigns. {opponent_nickname} wins!')
	return True


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
		outcome = WHITE_WINS if sender == game.white else BLACK_WINS
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
	send_game_rep(game.white, game)
	send_game_rep(game.black, game, False)


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
