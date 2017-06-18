import psycopg2
from urllib.parse import urlparse

try:
	import env
except ModuleNotFoundError:
	# Heroku has us covered
	pass
	
DATABASE_URL = os.environ['DATABASE_URL']

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

def migration1():
	cur = get_cursor()
	cur.execute("SELECT EXISTS(SELECT * FROM information_schema.tables WHERE table_name=%s)", ['games'])
	if not cur.fetchone()[0]:
		print('recreating table games')
		# TODO how to parameterize table name?
		cur.execute("""
			CREATE TABLE games (
				id SERIAL PRIMARY KEY,
				board BYTEA,
				active BOOLEAN
			)
			""")
	cur.execute("INSERT INTO games (board) values (%s)", [psycopg2.Binary(b'Well hello thar')])


def migration2():
	with get_cursor() as cur:
		# cur.execute("SELECT EXISTS(SELECT * FROM information_schema.tables WHERE table_name=%s)", ['user'])
		# if not cur.fetchone()[0]:
		cur.execute("""
			CREATE TABLE IF NOT EXISTS player (
				id BIGINT PRIMARY KEY,
				nickname varchar(32),
				opponent_context BIGINT REFERENCES player(id)
			)
			""")

		cur.execute("""
			DELETE FROM games
			""")

		cur.execute("""
			ALTER TABLE games
			ADD COLUMN whiteplayer BIGINT REFERENCES player(id),
			ADD COLUMN blackplayer BIGINT REFERENCES player(id)
			""")

		cur.connection.commit()

def migration3():
	with get_cursor() as cur:
		cur.execute("""
			CREATE TABLE IF NOT EXISTS scratch (
				key VARCHAR(32) PRIMARY KEY,
				value BYTEA
			)
			""")
		cur.connection.commit()

def migration4():
	with get_cursor() as cur:
		cur.execute("""
			ALTER TABLE games
			ADD COLUMN undo BOOLEAN DEFAULT FALSE
			""")
		cur.connection.commit()

cur = None
def op():
	global cur
	cur = get_cursor()

def rlbk():
	global cur
	cur.connection.rollback()

def close():
	global cur
	cur.connection.close()
	cur.close()
	cur = None

def exe(cmd):
	global cur
	if not cur:
		cur = get_cursor()
	cur.execute(cmd)
	return list(cur)

def select(cmd):
	return exe('select ' + cmd)
	# cur = get_cursor()
	# cur.execute(cmd)
	# return cur

# migration2()
# with get_cursor() as cur:
# 	cur.execute("""
# 		INSERT INTO player (id, nickname, opponent_context) VALUES 
# 			(1, 'Jambi', NULL),
# 			(2, 'Jaother', 1)

# 		""")
# 	cur.connection.commit()

# cur = get_cursor()
# cur = migration2()

