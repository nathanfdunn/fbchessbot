
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
	_targetid BIGINT
)
RETURNS INT
AS
$$
BEGIN
	IF EXISTS(
		SELECT * 
		FROM player_blockage
		WHERE playerid = _playerid AND blocked_playerid = _targetid
		)
	THEN
		RETURN 1;	-- Redundant
	END IF;

	INSERT INTO player_blockage (playerid, blocked_playerid)
	VALUES (_playerid, _targetid);
	RETURN 0;		-- Success

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


