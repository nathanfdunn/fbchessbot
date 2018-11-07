
CREATE OR REPLACE FUNCTION cb.get_playerid(
	_playername VARCHAR(32)
)
RETURNS BIGINT
AS 
$$
BEGIN
	RETURN (SELECT id FROM player WHERE lower(nickname) = lower(_playername));
END
$$ LANGUAGE plpgsql;



CREATE OR REPLACE FUNCTION cb.block_player(
	_playerid BIGINT,
	_targetid BIGINT,
	_block BOOLEAN
)
RETURNS INT
AS
$$
BEGIN
	IF _block THEN
		IF EXISTS(
			SELECT * 
			FROM player_blockage
			WHERE playerid = _playerid AND blocked_playerid = _targetid
			)
		THEN
			RETURN 1;	-- Redundant
		END IF;

		-- Remove opponent context if necessary
		UPDATE player SET opponent_context = NULL
		WHERE id = _targetid AND opponent_context = _playerid;

		INSERT INTO player_blockage (playerid, blocked_playerid)
		VALUES (_playerid, _targetid);
		RETURN 0;		-- Success
	ELSE
		IF NOT EXISTS(
			SELECT * 
			FROM player_blockage
			WHERE playerid = _playerid AND blocked_playerid = _targetid
			)
		THEN
			RETURN 1;	-- Redundant
		END IF;

		DELETE FROM player_blockage WHERE playerid = _playerid AND blocked_playerid = _targetid;
		RETURN 0;		-- Success
	END IF;
END
$$ LANGUAGE plpgsql;

-- First bit indicates whether  _playerid blocked _otherid
-- Second bit indicates whether _otherid blocked _playerid
CREATE OR REPLACE FUNCTION cb.blocked(
	_playerid BIGINT,
	_otherid BIGINT
)
RETURNS INT
AS
$$
BEGIN
	RETURN 
		(SELECT CASE WHEN EXISTS(
			SELECT * 
			FROM player_blockage 
			WHERE playerid = _playerid AND blocked_playerid = _otherid
			)
			THEN 1
			ELSE 0
		END)
		|
		(SELECT CASE WHEN EXISTS(
			SELECT * 
			FROM player_blockage 
			WHERE playerid = _otherid AND blocked_playerid = _playerid
			)
			THEN 2
			ELSE 0
		END);
END
$$ LANGUAGE plpgsql;

-- Given a player id, gets the player object, the opponent (if they have any), 
-- and the game (if there is an active game between them)
CREATE OR REPLACE FUNCTION cb.get_context(
	_playerid BIGINT
)
RETURNS TABLE (
	playerid BIGINT, player_nickname VARCHAR(32), player_opponentid BIGINT, player_active BOOLEAN,
	opponentid BIGINT, opponent_nickname VARCHAR(32), opponent_opponentid BIGINT, opponent_active BOOLEAN,
	gameid INT, board BYTEA, active BOOLEAN, whiteplayer BIGINT, blackplayer BIGINT, undo BOOLEAN, outcome INT,
	last_moved_at_utc TIMESTAMP
)
AS
$$
BEGIN
	RETURN QUERY SELECT
		p.id AS playerid, p.nickname AS player_nickname, p.opponent_context AS player_opponentid, p.active AS player_active,
		o.id AS opponentid, o.nickname AS opponent_nickname, o.opponent_context AS opponent_opponentid, o.active AS opponent_active,
		g.id AS gameid, g.board, g.active, g.whiteplayer, g.blackplayer, g.undo, g.outcome, g.last_moved_at_utc
	FROM player p
	LEFT JOIN player o ON p.opponent_context = o.id
	LEFT JOIN games g ON (
			(g.whiteplayer = p.id AND g.blackplayer = o.id) 
			OR 
			(g.blackplayer = p.id AND g.whiteplayer = o.id)
		)
		AND (g.active = TRUE)
	WHERE p.id = _playerid;
END
$$ LANGUAGE plpgsql;


CREATE OR REPLACE FUNCTION cb.update_game(
	_gameid INT,
	_boardstate BYTEA = NULL,
	_undo BOOLEAN = NULL,
	_active BOOLEAN = NULL,
	_outcome INT = NULL,
	_last_moved_at_utc TIMESTAMP = NULL,
	_white_to_play BOOLEAN = NULL
)
RETURNS VOID
AS
$$
BEGIN

	UPDATE games SET
		board = COALESCE(_boardstate, board),
		undo = COALESCE(_undo, undo),
		active = COALESCE(_active, active),
		outcome = COALESCE(_outcome, outcome),
		last_moved_at_utc = COALESCE(_last_moved_at_utc, last_moved_at_utc),
		white_to_play = COALESCE(_white_to_play, white_to_play)
	WHERE id = _gameid;

END
$$ LANGUAGE plpgsql;


CREATE OR REPLACE FUNCTION cb.search_games(
	_now_utc TIMESTAMP
	, _gameid INT = NULL
	, _playerid BIGINT = NULL
	, _active BOOLEAN = NULL
	, _time_since_activity INT = NULL
	, _count INT = NULL
)
RETURNS TABLE (
	gameid INT, 
	whiteplayerid BIGINT,
	whiteplayer_nickname VARCHAR(32), 
	whiteplayer_send_reminders BOOLEAN,
	blackplayerid BIGINT,
	blackplayer_nickname VARCHAR(32), 
	blackplayer_send_reminders BOOLEAN,
	white_to_play BOOLEAN,
	delay DOUBLE PRECISION,
	board BYTEA
)
AS
$$
BEGIN
	RETURN QUERY SELECT 
		g.id + 1000, 
		w.id AS whiteplayerid, 
		w.nickname AS whiteplayer_nickname, 
		w.send_reminders AS whiteplayer_send_reminders,
		b.id AS blackplayerid,
		b.nickname AS blackplayer_nickname,
		b.send_reminders AS blackplayer_send_reminders,
		g.white_to_play,
		EXTRACT(EPOCH FROM _now_utc - COALESCE(g.last_moved_at_utc, g.created_at_utc)) AS delay,
		g.board

	FROM games g
		INNER JOIN player w ON w.id = g.whiteplayer
		INNER JOIN player b ON b.id = g.blackplayer
	WHERE 	(_gameid IS NULL OR g.id = _gameid)
		AND (_active IS NULL OR g.active = _active)
		AND (_playerid IS NULL OR w.id = _playerid OR b.id = _playerid)
		AND (_time_since_activity IS NULL OR 
				EXTRACT(EPOCH FROM _now_utc - COALESCE(g.last_moved_at_utc, g.created_at_utc)) > _time_since_activity
			)
	ORDER BY g.id
	LIMIT _count
		-- AND (w.send_reminders = TRUE
		-- 	OR
		-- 	b.send_reminders = TRUE)
		-- AND EXTRACT(EPOCH FROM _now_utc - COALESCE(g.last_moved_at_utc, g.created_at_utc)) >= 1 * 86400
	;
	-- WHERE 1=1;
		-- AND EXTRACT(EPOCH FROM (g.last_moved_at_utc - (NOW() at time zone 'utc'))) > 0;
-- TODO filter out inactive players, etc.
END
$$ LANGUAGE plpgsql;


CREATE OR REPLACE FUNCTION cb.create_game(
	_whiteplayerid BIGINT,
	_blackplayerid BIGINT,
	_initial_board_state BYTEA,
	_created_at_utc TIMESTAMP,
	_white_to_play BOOLEAN
)
RETURNS VOID
AS
$$
BEGIN
		UPDATE games 
			SET active = FALSE 
		WHERE active = TRUE AND (
			(whiteplayer = _whiteplayerid AND blackplayer = _blackplayerid)
			OR
			(blackplayer = _whiteplayerid AND whiteplayer = _blackplayerid)
		);

		INSERT INTO games (
			board, 
			active, 
			whiteplayer, 
			blackplayer, 
			undo, 
			created_at_utc,
			white_to_play
		) 
		VALUES (
			_initial_board_state, 
			TRUE, 
			_whiteplayerid, 
			_blackplayerid, 
			FALSE, 
			_created_at_utc,
			_white_to_play
		);
	-- TODO return the new game id?
END
$$ LANGUAGE plpgsql;


-- CREATE OR REPLACE FUNCTION cb.select_game(
-- 	_gameid INT
-- )
-- RETURNS TABLE (
-- 	gameid INT, 
-- 	whiteplayerid BIGINT,
-- 	whiteplayer_nickname VARCHAR(32), 
-- 	whiteplayer_send_reminders BOOLEAN,
-- 	blackplayerid BIGINT,
-- 	blackplayer_nickname VARCHAR(32), 
-- 	blackplayer_send_reminders BOOLEAN,
-- 	white_to_play BOOLEAN,
-- 	delay DOUBLE PRECISION
-- )
-- AS
-- $$
-- BEGIN
-- 	RETURN QUERY SELECT 
-- 		g.id, 
-- 		w.id AS whiteplayerid, 
-- 		w.nickname AS whiteplayer_nickname, 
-- 		w.send_reminders AS whiteplayer_send_reminders,
-- 		b.id AS blackplayerid,
-- 		b.nickname AS blackplayer_nickname,
-- 		b.send_reminders AS blackplayer_send_reminders,
-- 		g.white_to_play,
-- 		EXTRACT(EPOCH FROM _now_utc - COALESCE(g.last_moved_at_utc, g.created_at_utc)) AS delay

-- 	FROM games g
-- 		INNER JOIN player w ON w.id = g.whiteplayer
-- 		INNER JOIN player b ON b.id = g.blackplayer
-- 	WHERE g.id = _gameid

-- 		-- AND (w.send_reminders = TRUE
-- 		-- 	OR
-- 		-- 	b.send_reminders = TRUE)
-- 		-- AND EXTRACT(EPOCH FROM _now_utc - COALESCE(g.last_moved_at_utc, g.created_at_utc)) >= 1 * 86400
-- 	;
-- 	-- WHERE 1=1;
-- 		-- AND EXTRACT(EPOCH FROM (g.last_moved_at_utc - (NOW() at time zone 'utc'))) > 0;
-- -- TODO filter out inactive players, etc.
-- END
-- $$ LANGUAGE plpgsql;