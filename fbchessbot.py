import chess
from flask import Flask, request, send_file
import json
import os
import pickle
from PIL import Image, ImageDraw
import psycopg2
import re
import requests
from urllib.parse import urlparse, quote_plus, unquote_plus

VERIFY_TOKEN = 'tobeornottobeerobot'
PAGE_ACCESS_TOKEN = 'EAADbx7arRPQBANSbXpPFJStuljMm1ZCiiPmOA3UrG5FFkSDwffYiX3HgIVw4ZCaZAsAUsudTbIUP1ZCOTmpgajNKMMNjGB4rvqFgb0e2YMabSAv1kOvrxl0arVfqiqXKv2N2h1iu35AS95wiLxIQTx4zajbkjPzPXaeizc0rxwZDZD'
# DATABASE_URL = os.environ['DATABASE_URL']
DATABASE_URL = 'postgres://vjqgstovnxmxhf:627707772b1836a5b792c3087a1b56c401330158c24a3f3aead4ac64c0145727@ec2-184-73-236-170.compute-1.amazonaws.com:5432/ddnssqbrihnoje'

class Game:
	def __init__(self, data_row = None):
		if data_row is None:
			self.id = None
			self.active = False
			self.board = chess.Board()
		else:
			self.id, raw_board, self.active = data_row
			self.board = pickle.loads(bytes(raw_board))

	def display(self):
		print(self.board)

		# Technically it's just the board that's serialized
	def serialized(self):
		return pickle.dumps(self.board)

	def image_url(self):
		fen = quote_plus(self.board.fen().split()[0])
		return 'https://fbchessbot.herokuapp.com/image?fen=' + fen


def get_cursor():
	url = urlparse(DATABASE_URL)
	conn = psycopg2.connect(
		database=url.path[1:],
		user=url.username,
		password=url.password,
		host=url.hostname,
		port=url.port
	)
	return conn.cursor()

# I guess we'll deactivate any...
# Probably shouldn't use the game object after this...
def save_game(game):
	with get_cursor() as cur:
		cur.execute("UPDATE games SET active = FALSE WHERE 1=1")		# probably can ommit 1=1
		# Assume we only ever have an id if ...
		if game.id is None:
			cur.execute("INSERT INTO games (board, active) values (%s, TRUE)", [game.serialized()])
		else:
			# cur.execute("SELECT EXISTS(SELECT * FROM games WHERE id = %s)", [game.id])
			# if cur.fetchone()[0]:
			# Need to update
			cur.execute("UPDATE games SET board = %s, active = TRUE WHERE id = %s", [game.serialized(), game.id])
		cur.connection.commit()

# Auto intialize (bad practice)
def get_active_game():
	with get_cursor() as cur:
		cur.execute("SELECT id, board, active FROM games WHERE active = TRUE")
		row = cur.fetchone()

	if row is None:
		save_game(Game())
		return get_active_game()
	print('retrived row is', row)
	return Game(row)



app = Flask(__name__)

print('Ok, we made it to app instantiation')

@app.route('/image', methods=['GET'])
def board_image():
	print('Received image request')
	if 'fen' not in request.args:
		return 'Invalid FEN'
	fen = unquote_plus(request.args.get('fen')) + ' w - - 0 1'

	print('decoded FEN', fen)

	board = chess.Board(fen)
	board_image_name = '/tmp/' + str(board.board_zobrist_hash()) + '.png'
	
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

@app.route('/webhook', methods=['POST'])
def messages():
	print('Handling messages')
	for sender, message in messaging_events(request.get_data()):
		print('Incoming from {}: {}'.format(sender, message))
		message = message.strip()

		done = handle_help(sender, message) or handle_register(sender, message)

		if done:
			continue

		if message == 'show':
			game = get_active_game()
			send_game_rep(sender, game)
		elif message == 'new':
			game = Game()
			save_game(game)
			send_game_rep(sender, game)
		else:
			game = get_active_game()
			try:
				game.board.push_san(message)
				save_game(game)
				send_game_rep(sender, game)
			except Exception as e:
				print('Exception: ', e)
				send_message(sender, 'Something went wrong there')

def handle_help(sender, message):
	if re.match('^help$', message, re.IGNORECASE):
		send_message(sender, 'Help text coming soon...')
		return True
	else:
		return False

def handle_register(sender, message):
	m = re.match(r'^my\s+name\s+is\s+([a-z]+[0-9]*)')
	if m:
		nickname = m.groups()[0]
		if len(nickname) > 32:
			send_message(sender, 'That nickname is too long')
			return True
		register = register_user(sender, nickname)
		if register:
			send_message(sender, f'Nice to meet you {nickname}!')
		else:
			send_message(sender, f'Set your nickname to {nickname}')

		return True
	elif re.match(r'^my\s+name\s+is\s+'):
		send_message(sender, 'Nickname must match regex [a-z]+[0-9]*')
		return True
	else:
		return False

# Returns True if user was already registered
def set_nickname(sender, nickname):
	playerid = int(sender)
	with get_cursor() as cur:
		cur.execute('SELECT COUNT(*) FROM player WHERE id = %s', [playerid])
		if cur.fetchone():	# user already exists
			cur.execute('UPDATE player SET nickname = %s WHERE id = %s', [nickname, playerid])
			cur.connection.commit()
			return True
		else:				# user does not exist
			cur.execute()
			cur.connection.commit('INSERT INTO player (id, nickname) VALUES (%s, %s)', [nickname, playerid])
			return False

			# send_game_rep()

		# send_message(sender, message)
	return 'ok'
	# return 200, 'ok'

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

def send_game_rep(recipient, game):
	r = requests.post('https://graph.facebook.com/v2.9/me/messages',
		params={'access_token': PAGE_ACCESS_TOKEN},
		data=json.dumps({
			'recipient': {'id': recipient},
			# 'message': {'text': str(game.board)}
			'message': {
				'attachment': {
					'type': 'image',
					'payload': {
						'url': game.image_url()
					}
				}
			}
		}),
		headers={'Content-type': 'application/json'}
	)
	if r.status_code != requests.codes.ok:
		print('Error I think:', r.text)

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


if __name__ == '__main__':
	app.run(host='0.0.0.0')
