import os
import psycopg2
from urllib.parse import urlparse

try:
	import env
except ModuleNotFoundError:
	# Heroku has us covered
	pass

DATABASE_URL = os.environ['DATABASE_URL']

conn = None
cur = None

def init_connection():
	global conn
	if conn is None:
		try:
			url = urlparse(DATABASE_URL)
			conn = psycopg2.connect(
				database=url.path[1:],
				user=url.username,
				password=url.password,
				host=url.hostname,
				port=url.port
			)
		except psycopg2.OperationalError:
			conn = psycopg2.connect(DATABASE_URL)
	return conn

def op():
	global cur
	init_connection()
	if cur is None:
		cur = conn.cursor()
	return cur

def rlbk():
	cur.connection.rollback()

def close():
	global cur, conn
	cur.close()
	conn.close()
	cur = None
	conn = None

def exe(cmd):
	op()
	cur.execute(cmd)
	return list(cur)

def select(cmd):
	return exe('select ' + cmd)


migrations = []
def register_migration(func):
	migrations.append(func)
	return func

@register_migration
def migration1():
	op()
	cur.execute("SELECT EXISTS(SELECT * FROM information_schema.tables WHERE table_name=%s)", ['games'])
	if not cur.fetchone()[0]:
		cur.execute("""
			CREATE TABLE games (
				id SERIAL PRIMARY KEY,
				board BYTEA,
				active BOOLEAN
			)
			""")
	cur.execute("INSERT INTO games (board) values (%s)", [psycopg2.Binary(b'Well hello thar')])
	cur.connection.commit()

@register_migration
def migration2():
	op()
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

# @register_migration
def migration3():
	op()
	cur.execute("""
		CREATE TABLE IF NOT EXISTS scratch (
			key VARCHAR(32) PRIMARY KEY,
			value BYTEA
		)
		""")
	cur.connection.commit()

@register_migration
def migration4():
	op()
	cur.execute("""
		ALTER TABLE games
		ADD COLUMN undo BOOLEAN DEFAULT FALSE
		""")
	cur.connection.commit()

def migration5():
	op()
	cur.execute("""
		DROP TABLE IF EXISTS scratch
		""")
	cur.connection.commit()

@register_migration
def migration6():
	op()
	cur.execute("""
		ALTER TABLE games
		ADD COLUMN outcome BOOLEAN
		""")
	cur.connection.commit()

@register_migration
def migration7():
	op()
	cur.execute("""
		CREATE TABLE IF NOT EXISTS outcome (
			id SERIAL PRIMARY KEY,
			description VARCHAR(30)
		)
		""")
	cur.execute("""
		INSERT INTO outcome (description)
		VALUES ('White wins'), ('Black wins'), ('Draw')
		""")
	cur.execute("""
		ALTER TABLE games DROP COLUMN outcome
		""")
	cur.execute("""
		ALTER TABLE games ADD COLUMN outcome INT REFERENCES outcome(id)
		""")
	cur.connection.commit()

def apply_all_migrations():
	for m in migrations:
		m()
