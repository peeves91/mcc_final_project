from flask import Flask, jsonify, request, make_response
from flask_expects_json import expects_json
import json
import logging
import os
import pika
import requests
import threading

app = Flask(__name__)
app.logger.setLevel(logging.INFO)

# rabbitmq channel
rmqChannel = None

# constants
JSON_HEADER_DATATYPE		= {'Content-type': 'application/json'}
ORDER_SERVICE_PROT			= 5000
SHOPPING_CART_SERVICE_PORT	= 6000
USERS_SERVICE_PORT			= 7000
ITEMS_SERVICE_PORT			= 8000

# json schemas
QUEUE_ADD_DEL_ITEM = {
	"type": "object",
	"properties": {
		"user_email": {"type": "string"},
		"item_name": {"type": "string"},
		"quantity": {"type": "integer"}
	},
	"required": ["user_email", "item_name", "quantity"]
}

GET_PURCHASE_QUEUED_ITEMS = {
	"type": "object",
	"properties": {
		"user_email": {"type": "string"}
	},
	"required": ["user_email"]
}

GET_ORDERS_MATCHING_ITEM = {
	"type": "object",
	"properties": {
		"item_name": {"type": "string"},
		"user_email": {"type": "string"}
	},
	"required": ["item_name"]
}

# helper functions
def GetUserIdFromEmail(email: str) -> int:
	url = f'http://users_service:{USERS_SERVICE_PORT}/get_user'
	resp = requests.get(url=url, data=json.dumps({'user_email': email}), headers=JSON_HEADER_DATATYPE)
	respJson = resp.json()
	
	if len(respJson['results']) == 0:
		return None
	
	return respJson['results'][0]['user_id']

@app.route('/')
def HelloWorld():
	global rmqChannel
	
	# rmqChannel.basic_publish(exchange='', routing_key='HelloWorldQueue', body=json.dumps({'hello': 'world'}), properties=pika.BasicProperties(delivery_mode=2))
	rmqChannel.basic_publish(exchange='testing', routing_key='', body=json.dumps({'hello': 'world'}))
	
	return "hello, world"

###########################################################################
##	
##	Queues the specific item
##	
###########################################################################
@app.route('/queue_item', methods=['POST'])
@expects_json(QUEUE_ADD_DEL_ITEM)
def QueueAddItem():
	reqData = request.get_json()
	
	userId = GetUserIdFromEmail(email=reqData['user_email'])
	
	# Simply ensure a cart exists
	url = f'http://sc_service:{SHOPPING_CART_SERVICE_PORT}/get_or_create_cart'
	postData = {'user_id': userId}
	resp = requests.post(url=url, data=json.dumps(postData), headers=JSON_HEADER_DATATYPE)
	
	# if something failed here, it's quite bad, just return error
	if resp.status_code != 200:
		return make_response(resp.text, resp.status_code)
	
	url = f'http://sc_service:{SHOPPING_CART_SERVICE_PORT}/add_item_to_cart'
	postData = {'user_id': userId, 'item_name': reqData['item_name'], 'quantity': reqData['quantity']}
	resp = requests.post(url=url, data=json.dumps(postData), headers=JSON_HEADER_DATATYPE)
	
	if resp.status_code != 200:
		return make_response(resp.text, 500)
	
	return 'success'

###########################################################################
##	
##	Gets current item queue
##	
###########################################################################
@app.route('/get_queued_items', methods=['GET'])
@expects_json(GET_PURCHASE_QUEUED_ITEMS)
def GetQueuedItems():
	reqData = request.get_json()
	
	userId = GetUserIdFromEmail(email=reqData['user_email'])
	
	url = f'http://sc_service:{SHOPPING_CART_SERVICE_PORT}/get_cart_items'
	getData = {'user_id': userId}
	resp = requests.get(url=url, data=json.dumps(getData), headers=JSON_HEADER_DATATYPE)
	
	# if no cart found, return empty item list
	if resp.status_code == 500:
		if resp.text == 'no_cart':
			return jsonify({'items': []})
		else:
			return make_response('error getting items in cart', 500)
	
	try:
		respJson = resp.json()
	except requests.exceptions.JSONDecodeError:
		return make_response('failed to decode json getting cart items', 500)
	
	return jsonify(respJson)

###########################################################################
##	
##	Purchase current queue of items
##	
###########################################################################
@app.route('/purchase_queue', methods=['POST'])
@expects_json(GET_PURCHASE_QUEUED_ITEMS)
def PurchaseQueuedItems():
	reqData = request.get_json()
	
	userId = GetUserIdFromEmail(email=reqData['user_email'])
	
	url = f'http://sc_service:{SHOPPING_CART_SERVICE_PORT}/purchase_cart'
	postData = {'user_id': userId}
	resp = requests.post(url=url, data=json.dumps(postData), headers=JSON_HEADER_DATATYPE)
	
	# if there was an error purchasing cart, return it
	if resp.status_code != 200:
		return make_response(resp.text, resp.status_code)
	
	try:
		respJson = resp.json()
	except requests.exceptions.JSONDecodeError:
		return make_response('failed to decode json purchasing cart items', 500)
	
	# return purchased items
	return jsonify(respJson)

###########################################################################
##	
##	Clear current queue of items
##	
###########################################################################
@app.route('/clear_queue', methods=['POST'])
@expects_json(GET_PURCHASE_QUEUED_ITEMS)
def ClearQueuedItems():
	reqData = request.get_json()
	
	userId = GetUserIdFromEmail(email=reqData['user_email'])
	
	url = f'http://sc_service:{SHOPPING_CART_SERVICE_PORT}/cancel_cart'
	postData = {'user_id': userId}
	resp = requests.post(url=url, data=json.dumps(postData), headers=JSON_HEADER_DATATYPE)
	
	# if there was an error cancelling the queue, return it
	if resp.status_code != 200:
		return make_response(resp.text, resp.status_code)
	
	return 'success'

###########################################################################
##	
##	Clear current queue of items
##	
###########################################################################
@app.route('/get_orders_containing_item', methods=['GET'])
@expects_json(GET_ORDERS_MATCHING_ITEM)
def GetOrdersContainingItem():
	reqData = request.get_json()
	
	url = f'http://sc_service:{SHOPPING_CART_SERVICE_PORT}/get_sc_containing_item'
	getData = {'item_name': reqData['item_name']}
	
	if 'user_email' in reqData:
		userId = GetUserIdFromEmail(email=reqData['user_email'])
		getData['user_id'] = userId
	
	resp = requests.get(url=url, data=json.dumps(getData), headers=JSON_HEADER_DATATYPE)
	
	return jsonify(resp.json())

def SetupRabbitMq():
	global rmqChannel
	
	# read rabbitmq connection url from environment variable
	amqpUrl = os.environ['AMQP_URL']
	urlParams = pika.URLParameters(amqpUrl)
	
	# connect to rabbitmq
	connection = pika.BlockingConnection(urlParams)
	
	app.logger.info('Successfully connected to RabbitMQ')
	rmqChannel = connection.channel()
	
	# declare a new queue
	# rmqChannel.queue_declare(queue='HelloWorldQueue')
	rmqChannel.exchange_declare(exchange='testing', exchange_type='fanout')
	
	return

if __name__ == '__main__':
	rmqThread = threading.Thread(target=SetupRabbitMq, daemon=True)
	rmqThread.start()
	
	app.run(host='0.0.0.0', port=ORDER_SERVICE_PROT)