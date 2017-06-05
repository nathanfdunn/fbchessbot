##!/usr/bin/env python3

from flask import Flask, request
import json
import requests

VERIFY_TOKEN = 'tobeornottobeerobot'
PAGE_ACCESS_TOKEN = 'EAADbx7arRPQBANSbXpPFJStuljMm1ZCiiPmOA3UrG5FFkSDwffYiX3HgIVw4ZCaZAsAUsudTbIUP1ZCOTmpgajNKMMNjGB4rvqFgb0e2YMabSAv1kOvrxl0arVfqiqXKv2N2h1iu35AS95wiLxIQTx4zajbkjPzPXaeizc0rxwZDZD';

app = Flask(__name__)

@app.route('/webhook', methods=['GET'])
def verify():
	print('Handling Verification')
	if request.args.get('hub.verify_token') == VERIFY_TOKEN:
		print('Verification successful')
		return request.args.get('hub.challenge', '')
	else:
		print('Verification failed')
		return 'Error, wrong validation token'

@app.route('/webhook', methods=['POST'])
def messages():
	print('Handling messages')
	payload = request.get_data()
	print(payload)
	for sender, message in messaging_events(payload):
		print('Incoming from {}: {}'.format(sender, message))
		send_message(sender, message)
	# return 'ok'
	return 200, 'ok'

def messaging_events(payload):
	"""Generate tuples of (sender_id, message_text) from the
	provided payload.
	"""
	data = json.loads(payload)
	events = data["entry"][0]["messaging"]
	for event in events:
		if "message" in event and "text" in event["message"]:
			yield event["sender"]["id"], event["message"]["text"].encode('unicode_escape')
		else:
			yield event["sender"]["id"], "I can't echo this"

def send_message(recipient, text):
	r = request.post('https://graph.facebook.com/v2.9/me/messages',
		params={'access_token': PAGE_ACCESS_TOKEN},
		data=json.dumps({
			'recipient': {'id': recipient},
			'message': {'text': text.decode('unicode_escape')}
		}),
		headers={'Content-type': 'application/json'})
	if r.status_code != requests.codes.ok:
		print('Error I think:', r.text)

if __name__ == '__main__':
	# app.run(debug=True)
	app.run(host='0.0.0.0')

