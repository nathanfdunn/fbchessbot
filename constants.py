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

EVERYONE = 'everyone'
STRANGERS = 'strangers'

special_nicknames = [EVERYONE, STRANGERS]




deactivation_message = (
	'You have been deactivated. '
	'You will no longer receive messages from Chessbot. '
	'Say "activate" at any time to be reactivated.'
	)

activation_message = (
	'You have been reactivated. Welcome back!'
	)