import psycopg2
from urllib.parse import urlparse

DATABASE_URL = 'postgres://vjqgstovnxmxhf:627707772b1836a5b792c3087a1b56c401330158c24a3f3aead4ac64c0145727@ec2-184-73-236-170.compute-1.amazonaws.com:5432/ddnssqbrihnoje'

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

