import psycopg2
from urllib.parse import urlparse

DATABASE_URL = 'postgres://vjqgstovnxmxhf:627707772b1836a5b792c3087a1b56c401330158c24a3f3aead4ac64c0145727@ec2-184-73-236-170.compute-1.amazonaws.com:5432/ddnssqbrihnoje'

def get_cursor():
	url = urlparse(DATABASE_URL)
	conn = psycopg2.connect(
		database=url.path[1:],
		user=url.username,
		password=url.password,
		host=url.hostname,
		port=url.port
	)
	return conn.cursor()

cur = get_cursor()