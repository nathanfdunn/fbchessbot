from PIL import Image#, ImageDraw

BORDER = 30

def create_board_image(fen, iswhite, board_image_name):
	board = dbactions.ChessBoard(fen)
	board_string_array = str(board).replace(' ', '').split('\n')

	if iswhite:
		file = 'board_white.png'
	else:
		file = 'board_black.png'
		board_string_array = [reversed(row) for row in reversed(board_string_array)]
	# file = 'board_white.png' if is_white else 'board_black.png'
	piece_image_map = {
		'r': 'sprites/blackrook.png',
		'n': 'sprites/blackknight.png',
		'b': 'sprites/blackbishop.png',
		'q': 'sprites/blackqueen.png',
		'k': 'sprites/blackking.png',
		'p': 'sprites/blackpawn.png',

		'R': 'sprites/whiterook.png',
		'N': 'sprites/whiteknight.png',
		'B': 'sprites/whitebishop.png',
		'Q': 'sprites/whitequeen.png',
		'K': 'sprites/whiteking.png',
		'P': 'sprites/whitepawn.png'
	}

	with Image.open(file).copy() as board_image:
		for i, row in enumerate(board_string_array):
			for j, piece in enumerate(row):
				if piece in piece_image_map:
					piece_image = Image.open(piece_image_map[piece])
					board_image.paste(piece_image, (BORDER + 64*j,BORDER + 64*i), piece_image)

		# return board_image
		board_image.save(board_image_name)