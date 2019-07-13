import enum

class Color(enum.IntEnum):
	BLACK = 0
	WHITE = 1

	def __getattr__(self, attr):
		if attr == 'other':
			return self.BLACK if self is self.WHITE else self.WHITE
		else:
			return self.__getattribute__(attr)

class MessageType(enum.IntEnum):
	PLAYER_MESSAGE = 1
	CHESSBOT_TEXT = 2
	CHESSBOT_IMAGE = 3

BLACK = Color.BLACK
WHITE = Color.WHITE

class Outcome(enum.IntEnum):
	WHITE_WINS = 1
	BLACK_WINS = 2
	DRAW = 3

WHITE_WINS = Outcome.WHITE_WINS
BLACK_WINS = Outcome.BLACK_WINS
DRAW = Outcome.DRAW

class Relationship(enum.IntEnum):
	FRIEND_REQUEST = 1
	FRIENDS = 2
	BLOCKED = 3
	STRANGERS = 4

EVERYONE = 'everyone'
STRANGERS = 'strangers'

special_nicknames = [EVERYONE, STRANGERS]


# Yeah, this should be in a different module

deactivation_message = (
	'You have been deactivated. '
	'You will no longer receive messages from Chessbot. '
	'Say "activate" at any time to be reactivated.'
	)

activation_message = (
	'You have been reactivated. Welcome back!'
	)

intro = "Hi! Why don't you introduce yourself? (say My name is <name>)"

no_opponent = "You are not playing against anyone. Say 'play against <player>' to start playing against someone. (Try 'play against Nate' if you don't know anyone else on Chessbot)"
no_game = "You have no active games with {0}. Say 'new game white' or 'new game black' to start a new game"
