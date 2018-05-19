import os
from urllib.parse import urlparse

import psycopg2

try:
	import env
except ModuleNotFoundError:
	# Heroku has us covered
	pass
from dbactions import DB

DATABASE_URL = os.environ['DATABASE_URL']

conn = None
cur = None

def apply_all_migrations():
	for m in migrations:
		m()

def refresh_funcs():
	# print('refreshing!')
	with op() as cursor, open('dbfuncs.sql') as f:
		# Remove all existing functions
		cursor.execute('''
			CREATE OR REPLACE FUNCTION pg_temp.f_delfunc(_sch text)
			  RETURNS void AS
			$func$
			DECLARE
			   _sql text;
			BEGIN
			   SELECT INTO _sql
			          string_agg(format('DROP FUNCTION %s(%s);'
			                          , p.oid::regproc
			                          , pg_get_function_identity_arguments(p.oid))
			                   , E'\n')
			   FROM   pg_proc      p
			   JOIN   pg_namespace ns ON ns.oid = p.pronamespace
			   WHERE  ns.nspname = _sch;

			   IF _sql IS NOT NULL THEN
			      --  RAISE NOTICE '%', _sql;  -- for debugging
			      EXECUTE _sql;
			   END IF;
			END
			$func$ LANGUAGE plpgsql;
			SELECT pg_temp.f_delfunc('cb');
			''')

		cursor.execute(f.read())
		cursor.connection.commit()

def pickle_backup():
	op()
	cur.execute("""
		SELECT id, description FROM outcome
		""")
	outcomes = list(cur)

	cur.execute("""
		SELECT id, board, active, whiteplayer, blackplayer, undo, outcome FROM games
		""")
	games = list(cur)

	better = []
	for game in games:
		game = game[0], bytes(game[1]), *game[2:]
		better.append(game)

	cur.execute("""
		SELECT id, nickname, opponent_context FROM player
		""")
	players = list(cur)

	save = {'outcome': outcomes, 'games': better, 'players': players}
	import pickle
	with open('backup.pkl', 'wb') as f:
		pickle.dump(save, f)

def unpickle_backup():
	import pickle
	with open('backup.pkl', 'rb') as f:
		save = pickle.load(f)
	outcomes = save['outcome']
	players = save['players']
	games = save['games']
	op()
	cur.execute('SET CONSTRAINTS ALL DEFERRED')

	cur.executemany("""
		INSERT INTO player (id, nickname, opponent_context) VALUES (%s, %s, %s)
		""", players)
	cur.executemany("""
		INSERT INTO games (id, board, active, whiteplayer, blackplayer, undo, outcome) VALUES (%s, %s, %s, %s, %s, %s, %s)
		""", games)
	cur.connection.commit()


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
	if cur is None or cur.closed:
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

# @register_migration
# def migration8():
# 	op()
# 	cur.execute("""
# 		ALTER TABLE 
# 		""")
@register_migration
def migration9():
	import pickle
	import dbactions
	op()
	cur.execute('''
		SELECT id, board FROM games
		''')
	boards = list(cur)
	for id, board in boards:
		old_board = pickle.loads(bytes(board))
		# Assuming that we only have games that start in standard position
		new_board = dbactions.ChessBoard()
		for move in old_board.move_stack:
			new_board.push(move)
		cur.execute('''
			UPDATE games SET board = %s WHERE id = %s
			''', [new_board.to_byte_string(), id])
	cur.connection.commit()
	cur.close()

@register_migration
def migration10():
	op()
	cur.execute('''
		ALTER TABLE player ADD 
			active BOOLEAN NOT NULL DEFAULT TRUE
		''')
	cur.execute('''
		CREATE TABLE IF NOT EXISTS player_blockage (
			playerid BIGINT REFERENCES player(id),
			blocked_playerid BIGINT REFERENCES player(id),
			PRIMARY KEY(playerid, blocked_playerid)
		)
		''')
	cur.execute('''
		CREATE OR REPLACE FUNCTION get_playerid(
			playername VARCHAR(32)
		)
		RETURNS INT
		AS 
		$$
		BEGIN
			RETURN (SELECT id FROM player WHERE lower(nickname) = lower(playername));
		END
		$$ LANGUAGE plpgsql;
		''')
	cur.execute('''
		CREATE OR REPLACE FUNCTION block_player(
			playerid BIGINT,
			blocked_nickname VARCHAR(32)
		)
		RETURNS INT
		AS
		$$
		DECLARE blocked_playerid BIGINT;
		BEGIN
			blocked_playerid := get_playerid(blocked_nickname);
			IF blocked_playerid IS NULL THEN
				RETURN 1;	-- Error, no player by that name
			END IF;

			IF NOT EXISTS(SELECT * FROM player WHERE playerid = playerid) THEN
				RETURN 2;
			END IF;			-- Error, no player by that id

			IF EXISTS(SELECT * FROM player_blockage 
				WHERE playerid = playerid AND blocked_playerid = blocked_playerid) THEN
				RETURN 3; 	-- Not quite an error, but already blocked
			END IF;

			INSERT INTO player_blockage (playerid, blocked_playerid)
			VALUES (playerid, blocked_playerid);

			RETURN 0;		-- All good
		END
		$$ LANGUAGE plpgsql;
		''')
	cur.connection.commit()
	cur.close()

def migration11():
	op()
	cur.execute('''
		CREATE SCHEMA cb
		''')
	cur.connection.commit()

def migration12():
	op()
	cur.execute('''
		CREATE TABLE cb.message_log ( --note, we use the schema here
			id SERIAL PRIMARY KEY,
			senderid BIGINT, --REFERENCES player(id),
			recipientid BIGINT, --REFERENCES player(id),
			message VARCHAR(1024),
			-- Not worth another table: 1 = from player, 2 = text from chessbot, 3 = image from chessbot
			message_typeid SMALLINT
		)
		''')
	cur.connection.commit()

def migration13():
	op()
	cur.execute('''
		ALTER TABLE cb.message_log
		ADD COLUMN sentat TIMESTAMP DEFAULT (NOW() at time zone 'utc')
		''')
	cur.connection.commit()

@register_migration
def migration14():
	op()
	cur.execute('''
		ALTER TABLE player
		ADD COLUMN 	send_reminders BOOLEAN NOT NULL DEFAULT (FALSE),
					add column last_reminded_at_utc TIMESTAMP;
		ALTER TABLE games
		ADD COLUMN last_moved_at_utc TIMESTAMP;
		''')
	cur.connection.commit()

@register_migration
def migration15():
	op()
	cur.execute('''
		ALTER TABLE games ADD COLUMN created_at_utc TIMESTAMP NOT NULL DEFAULT (NOW() at time zone 'utc')
		''')
	cur.connection.commit()

@register_migration
def migration16():
	op()
	cur.execute('''
		ALTER TABLE games ADD COLUMN white_to_play BOOLEAN NOT NULL DEFAULT(TRUE)
		''')
	cur.connection.commit()