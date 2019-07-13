import functools
import json
import inspect
import os
import random
import re
import sys

import chess
import chess.pgn
from flask import Flask, request, send_file, render_template, escape as flask_encode_html
from PIL import Image, ImageDraw
import requests

import constants
from constants import WHITE, BLACK, WHITE_WINS, BLACK_WINS, DRAW, MessageType
import dbactions
import drawing
try:
	import env
except ModuleNotFoundError:
	# Heroku has us covered
	pass

VERIFY_TOKEN = os.environ['VERIFY_TOKEN']
PAGE_ACCESS_TOKEN = os.environ['PAGE_ACCESS_TOKEN']

# WHITE = 1
# BLACK = 0

# # Outcome codes
# WHITE_WINS = 1
# BLACK_WINS = 2
# DRAW = 3

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

@app.route('/sprites/<img>', methods=['GET'])
def sprites(img):
	return send_file('sprites/' + img)

@app.route('/board/<fen>', methods=['GET'])
def board_imageII(fen):
	# perspective = BLACK if request.args.get('perspective') == 'b' else WHITE
	perspective_arg = request.args.get('perspective') or 'w'
	perspective_arg = perspective_arg[0].lower()

	perspective_iswhite = (perspective_arg == 'w')

	# print(fen, perspective_iswhite)
	fen = fen.split('?')[0] # don't know if it includes the query characters...
	board_image_name = f'/tmp/{fen}_{perspective_arg}.png'

	fen = fen.replace('-', '/')  + ' w - - 0 1'

	drawing.create_board_image(fen, perspective_iswhite, board_image_name)

	# board = chess.Board(fen)
	
	# board_image = create_board_image(board_string_array)
	# board_image.save(board_image_name)
	return send_file(board_image_name)

# def format_reminders(reminders):

def format_reminder(reminder):
	if reminder.white_to_play:
		opponent_nickname = reminder.blackplayer_nickname
	else:
		opponent_nickname = reminder.whiteplayer_nickname
	return f'Game with {opponent_nickname} inactive for {round(reminder.days, 1)} days'

def reminder_sort_key(reminder):
	if reminder.white_to_play:
		opponent_nickname = reminder.blackplayer_nickname
	else:
		opponent_nickname = reminder.whiteplayer_nickname
	return reminder.days, opponent_nickname

@app.route('/send_reminders', methods=['GET'])
def send_reminders():
	reminders = db.get_reminders()
	format_reminders = {}
	for playerid, reminders_for_player in reminders.items():
		concatenated = '\n'.join(format_reminder(reminder) for reminder in sorted(reminders_for_player, key=reminder_sort_key))
		send_message(playerid, concatenated)

	# fail = False
	# for recipient, messages in reminders.items():
	# 	for message in messages:
	# 		if 'rylan' in message.lower() and 'nate' in message.lower():
	# 			if recipient == 1331390946942076:
	# 				send_message(recipient, message)
	# 			else:
	# 				fail = True
	# if fail:
	# 	raise Exception('Still spamming people....')


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

@app.route('/explore', methods=['GET'], defaults={'game_id': None})
@app.route('/explore/<game_id>', methods=['GET', 'POST'])
def explore(game_id):
	if game_id is None:
		gameids = [rec.gameid for rec in db.get_recent_games()]
		return render_template('explore-index.html', gameids=gameids)

	if request.method == 'POST':
		whiteplayerid = request.values.get('whiteplayerid')
		blackplayerid = request.values.get('blackplayerid') # Your form's
		fen = request.values.get('fen')

		db.create_new_game(whiteplayerid, blackplayerid, fen)

		return 'Success!'

	else:
		board = db.board_from_id(game_id)
		imgurls = board.get_img_urls()

		return render_template('explore.html',
			imgurls=imgurls,
			whiteplayerid=1498820443505655,
			blackplayerid=1331390946942076
			)

@app.route('/coordinate-trainer')
def coordinate_trainer():
	return render_template('chess-coordinate-trainer.html')

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
			yield event["sender"]["id"], "Invalid message"


@app.route('/webhook', methods=['POST'])
def messages():
	try:
		for sender, message in messaging_events(request.get_data()):
			sender, message = int(sender), message.strip()
			db.log_message(message, MessageType.PLAYER_MESSAGE, senderid=sender)
			handle_message(sender, message)
	except Exception as e:
		print('Error handling messages:', repr(e))
	finally:
		return 'ok'

commands = []
anonymous_commands = []
def handle_message(sender, message):
	message = message.strip()

	# Minor hack to intercept almost helps
	if message.lower() != 'help' and 'help' in message.lower():
		message = 'almosthelp'

	# print('sender', sender, 'message', message)
	if db.user_is_registered(sender):
		if not any(func(sender, message) for func in commands):
			handle_move(sender, message)
	else:
		if not any(func(sender, message) for func in anonymous_commands):
			send_message(sender, "Hi! Why don't you introduce yourself? (say My name is <name>)")

def command(function=None, *, require_game=False, allow_anonymous=False, require_person=False, receive_args=False):
	if function is not None:
		# raise Exception('Use command(), not command. (This is not a decorator, it is a function that returns a decorator)')
		return command()(function)

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
				if nickname.lower() in constants.special_nicknames:
					kwargs['other'] = nickname.lower()
				if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9]{0,31}', nickname.strip()):
					send_message(sender, 'That is an invalid screen name')
					return True
				else:
					other_player = db.player_from_nickname(nickname)
					if other_player is None:
						send_message(sender, f'There is no player by the name {nickname}')
						return True
					elif not other_player.active:
						send_message(sender, f'{other_player.nickname} has left Chessbot')
						return True;
					else:
						blockage = db.is_blocked(sender, other_player.id)
						if blockage[0]:
							send_message(sender, f'You have blocked {other_player.nickname}')
							return True
						elif blockage[1]:
							send_message(sender, f'You have been blocked by {other_player.nickname}')
							return True

						kwargs['other'] = other_player

			if require_game:
				player, opponent, game = db.get_context(sender)
				if opponent is not None and not db.player_is_active(opponent.id):
					send_message(sender, f'{opponent.nickname} has left Chessbot')
					return True

				if game:
					kwargs.update(player=player, opponent=opponent, game=game)
				else:
					if opponent is None:
						send_message(sender, 'You have no active games')
						return True
					else:
						send_message(sender, f'You have no active games with {opponent.nickname}')
						return True

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

helptext = '''help - Display this help text.

my name is <username> - Choose the name other users can call you by.

play against <playername> - Start playing with another user.

new game <color> - Start a new game with the user you are currently playing against.

show - Display the state of the current game.

resign - Resign the current game.

undo - Request to undo your last move (or accept your opponent's request to undo their move).

<move> - Make a move in your current game. Use algebraic notation, such as e4, Nf3, O-O-O.


See https://www.facebook.com/Chessbot-173074776551825/ for any questions.'''

@command(allow_anonymous=True)
def help(sender):
	send_message(sender, helptext)

almosthelptext = 'It looks like you are asking for help. Try typing just "help" (without the quotes)'

@command(allow_anonymous=True)
def almosthelp(sender):
	send_message(sender, almosthelptext)


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
	if not re.fullmatch(r'[a-z0-9]*', nickname, flags=re.IGNORECASE):
		# TODO better error message
		send_message(sender, r'Nickname must be only letters and numbers and not have spaces')
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
		send_message(sender, constants.registered.format(nickname))
	else:
		send_message(sender, f'I set your nickname to {nickname}')


# @command(r'play against (.*)')
@command(require_person=True)
def play_against(sender, other):
	current_opponentid = db.get_opponent_context(sender)
	opponentid = other.id
	blocked = db.is_blocked(sender, other.id)

	# This should be ok...?
	# if not other.active:
	# 	send_message(sender, f'{other.nickname} has left Chessbot')
	# 	return;
	# if blocked[0]:
	# 	send_message(sender, f'You have blocked {other.nickname}')
	# 	return;
	# elif blocked[1]:
	# 	send_message(sender, f'You have been blocked by {other.nickname}')
	# 	return

	if current_opponentid == opponentid:
		send_message(sender, f'You are already playing against {other.nickname}')
		return
	else:
		opponent_opponent_context = db.get_opponent_context(opponentid)
		if not opponent_opponent_context:
			sender_nickname = db.nickname_from_id(sender)
			db.set_opponent_context(opponentid, sender)
			send_message(opponentid, f'You are now playing against {sender_nickname}')
		db.set_opponent_context(sender, opponentid)
		send_message(sender, f'You are now playing against {other.nickname}')
		return


def new_game_base(color, sender, is_960=False):
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
	

	if is_960:
		board = chess.Board(chess960=is_960)
		board.set_chess960_pos(random.randint(0, 959))
		db.create_new_game(whiteplayer, blackplayer, board.fen())
	else:
		db.create_new_game(whiteplayer, blackplayer)

	send_message(opponent.id, f'{nickname} started a new game')
	_, _, g = db.get_context(sender)
	show_game_to_both(g)

@command(receive_args=True)
def new_960(color, sender):
	if color.lower() not in ['black', 'white']:
		send_message(sender, "Try either 'new 960 white' or 'new 960 black'")
		return
	new_game_base(color, sender, True)


@command(receive_args=True)
def new_game(color, sender):
	new_game_base(color, sender)


@command
def pgn(sender):
	gameid = db.get_most_recent_gameid(sender)
	send_pgn(sender, gameid)
	# game = db.get_most_recent_game(sender)
	# game = db.get_active_gameII(sender)
	# send_pgn(sender, game)


@command(require_game=True)
def resign(player, opponent, game):
	outcome = BLACK_WINS if player.color == WHITE else WHITE_WINS
	db.set_outcome(game, outcome)
	send_message(player.id, f'{player.nickname} resigns. {opponent.nickname} wins!')
	send_message(opponent.id, f'{player.nickname} resigns. {opponent.nickname} wins!')


@command
def status(sender):
	pass

@command
def stats(sender):
	pass

# @command(require_person=True)
@command(receive_args=True)
def block(other, sender):
	if other == constants.EVERYONE:
		pass
	elif other == constants.STRANGERS:
		pass
	else:
		otherid = db.id_from_nickname(other)
		other_nickname = db.nickname_from_id(otherid)		# get canonical nickname
		result = db.block_player(sender, otherid)
		if result == 0:
			send_message(sender, f'You have blocked {other_nickname}')
			# blocker_name = db.nickname_from_id(sender)
			# send_message(otherid, f'You have been blocked by {blocker_name}')
		else:
			send_message(sender, f'You have already blocked {other_nickname}')


# @command(require_person=True)
@command(receive_args=True)
def unblock(other, sender):
	if other == constants.EVERYONE:
		pass
	elif other == constants.STRANGERS:
		pass
	else:
		otherid = db.id_from_nickname(other)
		other_nickname = db.nickname_from_id(otherid)		# get canonical nickname
		result = db.unblock_player(sender, otherid)
		if result == 0:
			send_message(sender, f'You have unblocked {other_nickname}')
			# unblocker_name = db.nickname_from_id(sender)
			# send_message(otherid, f'You have been unblocked by {unblocker_name}')
		else:
			send_message(sender, f'You have already blocked {other_nickname}')

		# result = db.unblock_player(sender, other.id)
		# if result == 0:
		# 	send_message(sender, f'You have unblocked {other.nickname}')
		# 	unblocker_name = db.nickname_from_id(sender)
		# 	send_message(other.id, f'You have been unblocked by {unblocker_name}')
		# else:
		# 	send_message(sender, f'{other.nickname} was already unblocked')


@command
def deactivate(sender):
	db.set_player_activation(sender, False)
	send_message(sender, constants.deactivation_message)

@command
def activate(sender):
	db.set_player_activation(sender, True)
	send_message(sender, constants.activation_message)

@command(receive_args=True)
def reminders(offon, sender):
	offon = offon.lower()
	if offon == 'off':
		db.set_player_reminders(sender, False)
		send_message(sender, 'You will no longer receive reminders')
	elif offon == 'on':
		db.set_player_reminders(sender, True)
		send_message(sender, 'You will now receive reminders')
	else:
		send_message(sender, "Try either 'reminders off' or 'reminders on'")

@command(require_game=True)
def ping(player, opponent, game):
	if game.is_active_player(player.id):
		send_message(player.id, f'It is your turn. Did not ping {opponent.nickname}')
	else:
		send_message(opponent.id, f'It is your turn in your game with {player.nickname}')
		send_message(player.id, f'Pinged {opponent.nickname}')

@command(require_game=True)
def explore(player, opponent, game):
	fen = game.board.fen()
	fen = fen.split('-')[0]
	fen = fen.replace(' ', '_') + '-'
	lichessurl = 'https://lichess.org/analysis/standard/' + fen
	send_message(player.id, lichessurl)

@command(receive_args=True)
def say(text, sender):
	player, opponent, game = db.get_context(sender)
	if opponent is None:
		send_message(player.id, 'There is no one to message')
	else:
		send_message(opponent.id, f'{player.nickname} says\n{text}')
		send_message(player.id, f'You messaged {opponent.nickname}')

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
	if not opponent:
		send_message(sender, constants.no_opponent)
		return
	elif not game:
		send_message(sender, constants.no_game.format(opponent.nickname))
		return

	if not game.is_active_player(player.id):
		send_message(sender, "It isn't your turn")
		return

	if not opponent.active:
		send_message(sender, f'{opponent.nickname} has left Chessbot')
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

def send_pgn(recipient, gameid):
	r = requests.post('https://graph.facebook.com/v2.9/me/messages',
		params={'access_token': PAGE_ACCESS_TOKEN},
		data=json.dumps({
			'recipient': {'id': recipient},
			'message': {
				'attachment': {
					'type': 'file',
					'payload': {
						'url': f'https://fbchessbot.herokuapp.com/pgn/{gameid}.pgn'
					}
				}
			}
		}),
		headers={'Content-type': 'application/json'}
	)
	if r.status_code != requests.codes.ok:
		print('Error I think:', r.text)


# def send_pgn(recipient, game):
# 	r = requests.post('https://graph.facebook.com/v2.9/me/messages',
# 		params={'access_token': PAGE_ACCESS_TOKEN},
# 		data=json.dumps({
# 			'recipient': {'id': recipient},
# 			'message': {
# 				'attachment': {
# 					'type': 'file',
# 					'payload': {
# 						'url': game.pgn_url()
# 					}
# 				}
# 			}
# 		}),
# 		headers={'Content-type': 'application/json'}
# 	)
# 	if r.status_code != requests.codes.ok:
# 		print('Error I think:', r.text)

def send_game_rep(recipient, game, perspective=WHITE):
	board_image_url = game.image_url(perspective)
	db.log_message(board_image_url, MessageType.CHESSBOT_IMAGE, recipientid=recipient)
	r = requests.post('https://graph.facebook.com/v2.9/me/messages',
		params={'access_token': PAGE_ACCESS_TOKEN},
		data=json.dumps({
			'recipient': {'id': str(recipient)},
			'message': {
				'attachment': {
					'type': 'image',
					'payload': {
						'url': board_image_url #game.image_url(perspective)
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
	# Leave in the print for good measure
	print('sending message: ', recipient, text)
	db.log_message(text, MessageType.CHESSBOT_TEXT, recipientid=recipient)
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
	# with Image.open('board.png').copy() as board_image:
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


if sys.flags.debug:
	messages = []
	def send_message(recipient, text):
		messages.append(('cb-msg', text))
		print(recipient, text)

	def send_pgn(recipient, gameid):
		messages.append(('cb-pgn', gameid))
		print(recipient, gameid)

	def send_game_rep(recipient, game, perspective=WHITE):
		board_image_url = game.image_url(perspective)
		messages.append(('cb-game', board_image_url))
		print(recipient, board_image_url)

	print('starting up repl')
	# TODO templates?
	@app.route('/repl', methods=['GET', 'POST'])
	def repl():
		if request.method == 'POST':
			sender = request.form.get('sender') or ''
			sender = db.id_from_nickname(sender) or sender
			message = request.form.get('message') or ''
			print(f'repl: {sender}, {message}')
			messages.append((sender, message))
			handle_message(sender, message)

		# if request.method == 'GET':
		table = '<table>'
		for sender, message in messages:
			payload = f'<img height="200" src="{message}">' if message.startswith('https://') else message
			table += f'''
				<tr>
					<td>{sender}</td>
					<td>{payload}</td>
				</tr>'''
		table += '</table>'

		return f'''
			{table}
			<form action="/repl" method="post">
				<input type="text" name="sender" value="">
				<input type="text" name="message">
				<input type="submit">
			</form>
			'''

	# handle_message(67890, 'My name is Jess')
	# del messages[0]
	# @app.route('/mock_repl', methods=['POST'])
	# def mock_repl():


if __name__ == '__main__':
	app.run(host='0.0.0.0', debug=True)
