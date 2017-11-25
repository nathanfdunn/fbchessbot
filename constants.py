import enum

class Color(enum.IntEnum):
	BLACK = 0
	WHITE = 1

BLACK = Color.BLACK
WHITE = Color.WHITE

class Outcome(enum.IntEnum):
	WHITE_WINS = 1
	BLACK_WINS = 2
	DRAW = 3

WHITE_WINS = Outcome.WHITE_WINS
BLACK_WINS = Outcome.BLACK_WINS
DRAW = Outcome.DRAW
