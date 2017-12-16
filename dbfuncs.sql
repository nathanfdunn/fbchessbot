CREATE OR REPLACE FUNCTION get_playerid(
	playername VARCHAR(32)
)
RETURNS BIGINT
AS 
$$
BEGIN
	RETURN (SELECT id FROM player WHERE lower(nickname) = lower(playername));
END
$$ LANGUAGE plpgsql;



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

