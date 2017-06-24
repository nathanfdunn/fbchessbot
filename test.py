import sys
if not sys.flags.debug:
	raise Exception('Debug flag must be enabled')
# import fbchessbot
# import dbtools
# import dbactions
# import psycopg2
import unittest

# def remake_db():
# 	dbtools.conn = psycopg2.connect("dbname='fbchessbottest' user='nathandunn' host='localhost' password=''")
# 	dbtools.apply_all_migrations()

# Must be run with debug flag
sent_messages = []
def mock_send_message(recipient, text):
	sent_messages.append((recipient, text))

sent_game_reps = []
def mock_send_game_rep(recipient, game, perspective=True):
	sent_messages.append((recipient, game.image_url(perspective)))

sent_pgns = []
def mock_send_pgn(recipient, game):
	sent_pgns.append((recipient, game.pgn_url()))

def clear_mocks():
	global sent_messages, sent_game_reps, sent_pgns
	sent_messages = []
	sent_game_reps = []
	sent_pgns = []

dbactions = fbchessbot = psycopg2 = None

class TestRegistration(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		import dbactions as dba
		import fbchessbot as fbcb
		import psycopg2 as psy
		global dbactions, fbchessbot, psycopg2
		dbactions = dba
		fbchessbot = fbcb
		psycopg2 = psy

		cls.db = dbactions.DB()
		cls.nate_id = '32233848429'
		cls.chad_id = '83727482939'
		cls.jess_id = '47463849663'
		# db.delete_all()
		fbchessbot.send_message = mock_send_message
		fbchessbot.send_game_rep = mock_send_game_rep
		fbchessbot.send_pgn = mock_send_pgn

	@classmethod
	def tearDownClass(cls):
		del cls.db

	def setUp(self):
		print('deleting all')
		self.db.delete_all()
		clear_mocks()

	def test_can_register(self):
		fbchessbot.handle_message(self.nate_id, 'my name is Nate')
		expected_response = self.nate_id, 'Nice to meet you Nate!'
		self.assertEqual(sent_messages[-1], expected_response)

		fbchessbot.handle_message(self.chad_id, '     MY    NamE is    CHaD    ')
		expected_response = self.chad_id, 'Nice to meet you CHaD!'
		self.assertEqual(sent_messages[-1], expected_response)

		fbchessbot.handle_message(self.jess_id, 'my name is jess')
		expected_response = self.jess_id, 'Nice to meet you jess!'
		self.assertEqual(sent_messages[-1], expected_response)

		with self.db.cursor() as cur:
			cur.execute('SELECT COUNT(*) FROM player')
			self.assertEqual(cur.fetchone()[0], 3)

	# def test_can_self():
	# 	pass

	# def test_can_rename(self):
	# 	pass

	# def test_can_register(self):
	# 	print('blah')

	# def test_should_fail(self):
	# 	print('a')

# def main():
	# set_up_total()
	

if __name__ == '__main__':
	unittest.main()
