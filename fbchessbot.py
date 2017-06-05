#!/usr/bin/env python3

from flask import Flask, request
import requests

app = Flask(__name__)

@app.route('/')
def hello():
	return '<h2>Stuff</h2>'

@app.route('/webhook')
def verify():
	return '<h2>Idk</h2>'

@app.route('/blah', methods=['GET'])
def other():
	return '<h3>IIII</h3>'

if __name__ == '__main__':
	# app.run(debug=True)
	app.run(host='0.0.0.0')

