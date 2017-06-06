import chess
from flask import Flask, request
import json
import os
import pickle
import psycopg2
import requests
from urllib.parse import urlparse

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
		cur.execute("SELECT board FROM games WHERE active = TRUE")
		row = cur.fetchone()

	if row is None:
		save_game(Game())
		return get_active_game()
	return Game(row[0])



app = Flask(__name__)

print('Ok, we made it to app instantiation')

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
		if message == 'show':
			game = get_active_game()
			send_game_rep(sender, game)
		elif message == 'new':
			game = Game()
			save_game(game)
		else:
			game = get_active_game()
			try:
				game.board.push_san(message)
				save_game(game)
				send_game_rep(sender, game)
			except Exception as e:
				print('Exception: ', e)
				send_message(sender, 'Something went wrong there')


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
			'message': {'text': str(game.board)}
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

if __name__ == '__main__':
	app.run(host='0.0.0.0')



	# cur.execute("SELECT EXISTS(SELECT * FROM information_schema.tables WHERE table_name=%s)", ['games'])
	# if not cur.fetchone()[0]:
	# 	print('recreating table games')
	# 	# TODO how to parameterize table name?
	# 	cur.execute("""
	# 		CREATE TABLE games (
	# 			id SERIAL PRIMARY KEY,
	# 			board BYTEA,
	#			active BOOLEAN
	# 		)
	# 	""")
	# cur.execute("INSERT INTO games (board) values (%s)", [psycopg2.Binary(b'Well hello thar')])
