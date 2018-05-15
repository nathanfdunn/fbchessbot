from PIL import Image, ImageDraw, ImageFont

BORDER = 30
PIECE = 200

DARK = '#8aa'  #'#444'
LIGHT = '#fff' #'#aaa'

def base_board():
	board_image = Image.new('RGB', (8*PIECE + 2*BORDER, 8*PIECE + 2*BORDER))
	draw = ImageDraw.Draw(board_image)
	for i in range(8):
		for j in range(8):
			color = LIGHT if (i+j) % 2 else DARK
			coord = (BORDER + i*PIECE, BORDER + j*PIECE, BORDER + (i+1)*PIECE, BORDER + (j+1)*PIECE)
			draw.rectangle(coord, color)

	board_image.save('board_.png')

# board = Image.open('board.png').copy()
# board.convert('RGBA')
# piece = Image.open('sprites/blackrook.png')
# piece.convert('RGBA')
# board.paste(piece, (0,0), piece)

# board.save('test.png')

def create_board_image(board):
	board_image = Image.open('board_.png').copy()

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
				board_image.paste(piece_image, (BORDER + PIECE*j, BORDER + PIECE*i), piece_image)

	board_image.save('filled_.png')

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

# # base_board()
# create_board_image(board)
# exit()

# board_image = create_board_image(board)
# board_image.save('test.png')
# exit()

DARK = '#8aa'  #'#444'
LIGHT = '#fff' #'#aaa'


border = 30
piece = 64

img = Image.new('RGB', (border*2 + 8*piece, border*2+8*piece))

draw = ImageDraw.Draw(img)

# my_font = ImageFont.trutype()
# font = ImageFont.load("arial.pil")
font = ImageFont.truetype("arial.ttf", 30)

for i in range(8):
	for j in range(8):
		# color = LIGHT if (i+j) % 2 else DARK
		color = DARK if (i+j) % 2 else LIGHT
		coord = (border + i*64, border + j*64, border + (i+1)*64, border + (j+1)*64)
		draw.rectangle(coord, color)
		if j == 0:
			draw.text((border*1.7 + i*64,0), 'ABCDEFGH'[i], font=font)
			draw.text((border*1.7 + i*64,border + 64*8), 'ABCDEFGH'[i], font=font)
		if i == 0:
			draw.text((border/5, border*1.6 + j*64), str(8-j), font=font)
			draw.text((8*64 + border*1.25, border*1.6 + j*64), str(8-j), font=font)
			# draw.text((8*64, border*1.6 + j*64), str(j), font=font)
			
			# draw.text((border + 64*8, border*1.7 + j*64), str(j), font=font)

img.save('board_white.png')



img = Image.new('RGB', (border*2 + 8*piece, border*2+8*piece))

draw = ImageDraw.Draw(img)

# my_font = ImageFont.trutype()
# font = ImageFont.load("arial.pil")
font = ImageFont.truetype("arial.ttf", 30)

for i in range(8):
	for j in range(8):
		# color = LIGHT if (i+j) % 2 else DARK
		color = DARK if (i+j) % 2 else LIGHT
		coord = (border + i*64, border + j*64, border + (i+1)*64, border + (j+1)*64)
		draw.rectangle(coord, color)
		if j == 0:
			draw.text((border*1.7 + i*64,0), 'ABCDEFGH'[7-i], font=font)
			draw.text((border*1.7 + i*64,border + 64*8), 'ABCDEFGH'[7-i], font=font)
		if i == 0:
			draw.text((border/5, border*1.6 + j*64), str(j+1), font=font)
			draw.text((8*64 + border*1.25, border*1.6 + j*64), str(j+1), font=font)
			
			# draw.text((8*64, border*1.6 + j*64), str(j), font=font)
			
			# draw.text((border + 64*8, border*1.7 + j*64), str(j), font=font)

img.save('board_black.png')

def draw_logo():
	center = (8*PIECE + 2*BORDER, 8*PIECE + 2*BORDER)/2

	logo_image = Image.open('board.png').copy()

	king = Image.open('sprites/whiteking.png')
	logo_image.paste(king, )

j, piece in enumerate(row):
			if piece in piece_image_map:
				piece_image = Image.open(piece_image_map[piece])
				board_image.paste(piece_image, (BORDER + PIECE*j, BORDER + PIECE*i), piece_image)

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
