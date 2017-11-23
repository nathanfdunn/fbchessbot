import functools
import json
import inspect
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
	# board = chess.Board(fen)
	board = dbactions.ChessBoard(fen)
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
	failed = False
	try:
		if request.args.get('hub.verify_token') == VERIFY_TOKEN:
			return request.args.get('hub.challenge', '')
		else:
			return 'Error, wrong validation token'
	except Exception as e:
		failed = True
		print('Got an exception in verification?', str(e))
	finally:
		print('failure:', failed)

def messaging_events(payload):
	"""Generate tuples of (sender_id, message_text) from the
	provided payload.
	"""
	data = json.loads(payload)
	print('message(s) received:\n', payload)
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

commands = []
anonymous_commands = []
def handle_message(sender, message):
	message = message.strip()
	# print('sender', sender, 'message', message)
	if db.user_is_registered(sender):
		if not any(func(sender, message) for func in commands):
			handle_move(sender, message)
	else:
		if not any(func(sender, message) for func in anonymous_commands):
			send_message(sender, "Hi! Why don't you introduce yourself? (say My name is <name>)")

def command(*, require_game=False, allow_anonymous=False, require_person=False, receive_args=False):
	def decorator(func):
		parms = set(inspect.signature(func).parameters.keys())
		# Validate underlying arguments
		# if not require_game and not require_person and 'sender' not in parms:
		# 	raise Exception('Regular commands must accept the "sender" parameter')
		if require_game and not parms >= {'player', 'opponent', 'game'}:
			raise Exception('Missing parameters required to receive game context')
		elif require_person and 'other' not in parms:
			raise Exception('Missing parameters required to receive other player')

		regex = func.__name__.replace('_', r'\s+')
		if require_person or receive_args:
			regex += r'\s+(.*)'

		@functools.wraps(func)
		def wrapper(sender, message):
			kwargs = {}
			if 'sender' in parms:
				kwargs['sender'] = sender
			m = re.fullmatch(regex, message, flags=re.IGNORECASE | re.DOTALL)
			if not m:
				return False
			if require_person:
				nickname = m.group(1).strip()
				if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9]{0,31}', nickname.strip()):
					send_message(sender, 'That is an invalid screen name')
					return True
				else:
					other_player = db.player_from_nickname(nickname)
					if other_player is None:
						send_message(sender, f'There is no player by the name {nickname}')
						return True
					else:
						kwargs['other'] = other_player

			if require_game:
				player, opponent, game = db.get_context(sender)
				if not game:
					if opponent is None:
						send_message(sender, 'You have no active games')
						return True
					else:
						send_message(sender, f'You have no active games with {opponent.nickname}')
						return True
				else:
					kwargs.update(player=player, opponent=opponent, game=game)

			if receive_args:
				func(m.group(1).strip(), **kwargs)
			else:
				func(**kwargs)

			return True			# cuz it must have matched

		if allow_anonymous:
			anonymous_commands.append(wrapper)
		
		commands.append(wrapper)

		return wrapper

	return decorator


@command(require_game=True)
def show(player, opponent, game):
	send_game_rep(player.id, game, player.color)
	if game.is_active_color(WHITE):
		send_message(player.id, 'White to move')
	else:
		send_message(player.id, 'Black to move')

@command(allow_anonymous=True)
def help(sender):
	send_message(sender, 'Help text coming soon...')


@command(require_game=True)
def undo(player, opponent, game):
	if game.undo:
		if game.is_active_player(player.id):
			game.board.pop()
			db.set_undo_flag(game, False)
			db.save_game(game)
			send_message(opponent.id, f'{player.nickname} accepted your undo request')
			send_game_rep(player.id, game, player.color)
			send_game_rep(opponent.id, game, opponent.color)
		else:
			send_message(player.id, 'You have already requested an undo')
	else:
		if game.is_active_player(player.id):
			send_message(player.id, "You can't request an undo when it is your turn")
		else:
			if game.board.stack:
				db.set_undo_flag(game, True)
				send_message(opponent.id, f'{player.nickname} has requested an undo')
			else:
				send_message(player.id, "You haven't made any moves to undo")


@command(allow_anonymous=True, receive_args=True)
def my_name_is(nickname, sender):
	if not re.fullmatch(r'[a-z][a-z0-9]*', nickname, flags=re.IGNORECASE):
		# TODO better error message
		send_message(sender, r'Nickname must match regex [a-z]+[0-9]*')
		return
	if len(nickname) > 32:
		send_message(sender, 'That nickname is too long (Try 32 or less characters)')
		return

	user_id = db.id_from_nickname(nickname)
	if user_id is not None:
		if user_id == sender:
			send_message(sender, f'Your nickname is already {nickname}')
		else:
			send_message(sender, 'That name is taken. Please choose another')
		return

	user_is_new = db.set_nickname(sender, nickname)
	if user_is_new:
		send_message(sender, f'Nice to meet you {nickname}!')
	else:
		send_message(sender, f'I set your nickname to {nickname}')


# @command(r'play against (.*)')
@command(require_person=True)
def play_against(sender, other):
	nickname = other.nickname
	current_opponent = db.get_opponent_context(sender)
	opponentid = db.id_from_nickname(nickname)
	if current_opponent == opponentid != None:
		send_message(sender, f'You are already playing against {nickname}')
	elif opponentid:
		opponent_opponent_context = db.get_opponent_context(opponentid)
		if not opponent_opponent_context:
			sender_nickname = db.nickname_from_id(sender)
			db.set_opponent_context(opponentid, sender)
			send_message(opponentid, f'You are now playing against {sender_nickname}')
		db.set_opponent_context(sender, opponentid)
		send_message(sender, f'You are now playing against {nickname}')
	else:
		send_message(sender, f"No player named '{nickname}'")


@command(receive_args=True)
def new_game(color, sender):
	if color.lower() not in ['black', 'white']:
		send_message(sender, "Try either 'new game white' or 'new game black'")
		return

	player, opponent, game = db.get_context(sender)
	if opponent is None:
		send_message(sender, "You aren't playing against anyone (Use command 'play against <name>')")
		return

	if game is not None:
		send_message(sender, f'You already have an active game with {opponent.nickname}')
		return

	if color.lower() == 'white':
		whiteplayer, blackplayer = sender, opponent.id
	else:
		whiteplayer, blackplayer = opponent.id, sender
	nickname = db.nickname_from_id(sender)
	db.create_new_game(whiteplayer, blackplayer)
	send_message(opponent.id, f'{nickname} started a new game')
	_, _, g = db.get_context(sender)
	show_game_to_both(g)


@command()
def pgn(sender):
	game = db.get_active_gameII(sender)
	send_pgn(sender, game)


@command(require_game=True)
def resign(player, opponent, game):
	outcome = BLACK_WINS if player.color == WHITE else WHITE_WINS
	db.set_outcome(game, outcome)
	send_message(player.id, f'{player.nickname} resigns. {opponent.nickname} wins!')
	send_message(opponent.id, f'{player.nickname} resigns. {opponent.nickname} wins!')


@command()
def status(sender):
	pass

@command()
def stats(sender):
	pass

# @command
# @require_person
# def block(sender, nickname):
# 	pass

# @command
# @require_person
# def unblock(sender, nickname):
# 	pass



def normalize_move(game, move):
	if not move:
		return move

	move = move.upper()

	# Resolve crazy edge case - go with bishop move if ambiguous
	if move[0] == 'B':
		bishopMove = 'B' + move[1:]
		pawnMove = 'b' + move[1:]
		try:
			game.board.parse_san(bishopMove)
			bishopWorks = True
		except ValueError:
			bishopWorks = False
		try:
			game.board.parse_san(pawnMove)
			pawnWorks = True
		except ValueError:
			pawnWorks = False

		if bishopWorks and pawnWorks:
			return bishopMove
		elif bishopWorks:
			return bishopMove
		elif pawnWorks:
			return pawnMove

	if move[0] in 'NRBKQP':
		move = move[0] + move[1:].lower()
	else:
		move = move.lower()

	# Fix the .lower() for castling (will allow case-insensitive castling)
	move = move.replace('o', 'O')
	# 0 only valid in castling
	move = move.replace('0', 'O')
	# P at beginning must be pawn move
	move = move.lstrip('P')
	return move


def handle_move(sender, message):
	player, opponent, game = db.get_context(sender)
	if not game:
		send_message(sender, 'You have no active games')
		return

	if not game.is_active_player(player.id):
		send_message(sender, "It isn't your turn")
		return

	move = normalize_move(game, message)

	try:
		game.board.parse_san(move)
	except ValueError as e:
		if 'ambiguous' in str(e):
			send_message(player.id, 'That move could refer to two or more pieces')
		else:
			send_message(player.id, 'That is an invalid move')
		return

	game.board.push_san(move)
	db.save_game(game)
	db.set_undo_flag(game, False)

	send_game_rep(player.id, game, player.color)
	send_message(opponent.id, f'{player.nickname} played {move}')
	send_game_rep(opponent.id, game, opponent.color)

	opponentid = game.blackplayer.id if game.whiteplayer.id == sender else game.whiteplayer.id

	if game.board.is_checkmate():
		outcome = WHITE_WINS if sender == game.whiteplayer.id else BLACK_WINS
		db.set_outcome(game, outcome)
		send_message(player.id, f'Checkmate! {player.nickname} wins!')
		send_message(opponent.id, f'Checkmate! {player.nickname} wins!')
	elif game.board.is_check():
		send_message(player.id, 'Check!')
		send_message(opponent.id, 'Check!')


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
	print('sending message: ', recipient, text)
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
	else:
		print('supposedly message was good.')


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


# def command(regex_or_func, regex_opts=re.IGNORECASE | re.DOTALL):
# 	if type(regex_or_func) is str:
# 		regex = regex_or_func
# 		# Convention that regex args => they need a capture group
# 		original_regex = '^' + regex.replace(' ', r'\s+') + '$'
# 		lenient_regex = re.sub(r'\(.*\)', r'(.*)', original_regex)
# 		def decorator(func):
# 			@functools.wraps(func)
# 			def wrapper(sender, message):
# 				m = re.match(lenient_regex, message.strip(), re.IGNORECASE | re.DOTALL)
# 				if not m:
# 					return False
# 				m = re.match(original_regex, message.strip(), regex_opts)
# 				if m:
# 					func(sender, m.groups()[0])
# 				else:
# 					func(sender, None)
# 				return True
# 			commands.append(wrapper)
# 			return wrapper

# 		return decorator

# 	else:
# 		func = regex_or_func
# 		# Convention that directly wrapping = they only need senderid
# 		regex = '^' + func.__name__ + '$'
# 		@functools.wraps(func)
# 		def wrapper(sender, message):
# 			m = re.match(regex, message.strip(), re.IGNORECASE)
# 			if not m:
# 				return False
# 			func(sender)
# 			return True
# 		commands.append(wrapper)
# 		return wrapper

# def require_game(func):
# 	@functools.wraps(func)
# 	def wrapper(sender):
# 		player, opponent, game = db.get_context(sender)
# 		# game = db.get_active_gameII(sender)
# 		# TODO logic for if no active games with a specific person, etc.
# 		if not game:
# 			if opponent is None:
# 				send_message(sender, 'You have no active games')
# 			else:
# 				send_message(sender, f'You have no active games with {opponent.nickname}')
# 		else:
# 			# if sender == game.whiteplayer.id:
# 			# 	func(game.whiteplayer, game.blackplayer, game)
# 			# else:
# 			# 	func(game.blackplayer, game.whiteplayer, game)
# 			func(player, opponent, game)
# 	return wrapper

# def require_person(func):
# 	raise NotImplementedError
# 	# @functools.wraps(func)
# 	# def wrapper(sender):


# def allow_anonymous(func):
# 	anonymous_commands.append(func)
# 	return func

# def require_nickname(func):
