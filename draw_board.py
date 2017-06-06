from PIL import Image, ImageDraw



# board = Image.open('board.png').copy()
# board.convert('RGBA')
# piece = Image.open('sprites/blackrook.png')
# piece.convert('RGBA')
# board.paste(piece, (0,0), piece)

# board.save('test.png')




def create_board_image(board):
	board_image = Image.open('board.png').copy()

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
	for i, row in enumerate(board):
		for j, piece in enumerate(row):
			if piece in piece_image_map:
				piece_image = Image.open(piece_image_map[piece])
				board_image.paste(piece_image, (64*j, 64*i), piece_image)

	return board_image

board = [
	'rnbqkbnr',
	'pppppppp',
	'        ',
	'        ',
	'        ',
	'        ',
	'PPPPPPPP',
	'RNBQKBNR'
]

board_image = create_board_image(board)
board_image.save('test.png')
exit()

DARK = '#8aa'  #'#444'
LIGHT = '#fff' #'#aaa'

img = Image.new('RGB', (512, 512))

draw = ImageDraw.Draw(img)

for i in range(8):
	for j in range(8):
		color = LIGHT if (i+j) % 2 else DARK
		coord = (i*64, j*64, (i+1)*64, (j+1)*64)
		draw.rectangle(coord, color)

img.save('board.png')
