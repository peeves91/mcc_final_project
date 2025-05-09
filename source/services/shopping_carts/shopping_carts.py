from flask import Flask, jsonify, request, make_response
from flask_expects_json import expects_json
from typing import List, Dict
import json
import logging
import os
import pika
import requests
import sqlite3
import threading

app = Flask(__name__)
app.logger.setLevel(logging.INFO)

# constants
JSON_HEADER_DATATYPE		= {'Content-type': 'application/json'}
SHOPPING_CART_SERVICE_PORT	= 6000
USERS_SERVICE_PORT			= 7000
ITEMS_SERVICE_PORT			= 8000

# globals
cartDbConn = None
dbCursor = None
dbLock = threading.Lock()

# rabbitmq channel
rmqChannel = None
shoppingCartValidatedChannel = None
shoppingCartValidatedChannelLock = threading.Lock()
orderFailedChannel = None
orderFailedChannelLock = threading.Lock()

CREATE_SHOPPING_CART_SCHEMA = {
	"type": "object",
	"properties": {
		"user_id": {"type": "integer"}
	},
	"required": ["user_id"]
}

GET_PURCHASE_CANCEL_SHOPPING_CART_SCHEMA = {
	"type": "object",
	"properties": {
		"user_id": {"type": "integer"}
	},
	"required": ["user_id"]
}

ADD_ITEM_SCHEMA = {
	"type": "object",
	"properties": {
		"user_id": {"type": "integer"},
		"item_name": {"type": "string"},
		"quantity": {"type": "integer"}
	},
	"required": ["user_id", "item_name", "quantity"]
}

GET_SC_CONTAINING_ITEM = {
	"type": "object",
	"properties": {
		"item_name": {"type": "string"},
		"user_id": {"type": "integer"}
	},
	"required": ["item_name"]
}

# helper functions
def GetUserInfoFromEmailOrId(email=None, userId=None):
	url = f'http://users_service:{USERS_SERVICE_PORT}/get_user'
	
	if email != None:
		getData = {'user_email': email}
	elif userId != None:
		getData = {'user_id': userId}
	else:
		return None
	
	resp = requests.get(url=url, data=json.dumps(getData), headers=JSON_HEADER_DATATYPE)
	
	try:
		respJson = resp.json()
	except requests.exceptions.JSONDecodeError:
		return None
	
	# if no users found, return None
	if len(respJson['results']) == 0:
		return None
	
	foundUser = respJson['results'][0]
	
	return foundUser

def GetUserIdFromEmail(email: str) -> int:
	return GetUserInfoFromEmailOrId(email=email)['user_id']

def GetItemInfoFromNameOrId(itemName: str=None, itemId: int=None) -> int:
	url = f'http://items_service:{ITEMS_SERVICE_PORT}/get_item_info'
	
	if itemName != None:
		getData = {'item_name': itemName}
	elif itemId != None:
		getData = {'item_id': itemId}
	else:
		return None
	
	resp = requests.get(url=url, data=json.dumps(getData), headers=JSON_HEADER_DATATYPE)
	
	if resp.status_code != 200:
		return make_response(resp.text, resp.status_code)
	
	try:
		respJson = resp.json()
	except requests.exceptions.JSONDecodeError:
		return None
	
	# @todo swelter: handle item not found here
	
	return respJson['item']

def CalculateTotalPriceOfItems(items: List[Dict]) -> float:
	totalPrice = 0
	
	for index in range(len(items)):
		url = f'http://items_service:{ITEMS_SERVICE_PORT}/get_item_info'
		getData = {'item_id': items[index]['item_id']}
		resp = requests.get(url=url, data=json.dumps(getData), headers=JSON_HEADER_DATATYPE)
		
		if resp.status_code != 200:
			return None
		
		try:
			respJson = resp.json()
		except requests.exceptions.JSONDecodeError:
			return None
		
		totalPrice += (respJson['item'][1] * items[index]['quantity'])
	
	return totalPrice

@app.route('/')
def HelloWorld():
	return "hello, world"

###########################################################################
##	
##	Returns the existing cart_id for a user if one exists and is open,
##	otherwise it creates one and returns it
##	
###########################################################################
@app.route('/get_or_create_cart', methods=['POST'])
@expects_json(CREATE_SHOPPING_CART_SCHEMA)
def GetOrCreateShoppingCart():
	global cartDbConn
	global dbCursor
	global dbLock
	
	reqData = request.get_json()
	
	userId = reqData['user_id']
	
	# check if cart exists
	dbCursor.execute('SELECT id FROM shopping_carts WHERE user_id = ? AND status = ?', (userId, 'open',))
	results = dbCursor.fetchone()
	
	# if we found an existing cart, return it and we're done
	if results != None:
		return jsonify({'cart_id': results[0]})
	
	# no cart found, create one and return the id
	with dbLock:
		dataToInsert = (userId, 'open')
		dbCursor.execute('INSERT INTO shopping_carts(user_id, status) VALUES(?, ?)', dataToInsert)
		cartDbConn.commit()
	
	cartId = dbCursor.lastrowid
	
	return jsonify({'cart_id': cartId})

###########################################################################
##	
##	Adds an item to the user's existing cart.  Returns an error if one
##	is not open.
##	
###########################################################################
@app.route('/add_item_to_cart', methods=['POST'])
@expects_json(ADD_ITEM_SCHEMA)
def AddItemToCart():
	global cartDbConn
	global dbCursor
	global dbLock
	
	reqData = request.get_json()
	
	userId = reqData['user_id']
	
	# get cart_id from user_Id
	dbCursor.execute('SELECT id FROM shopping_carts WHERE user_id = ? AND status = "open"', (userId,))
	cartResults = dbCursor.fetchone()
	
	# return 500 error if no cart found
	if cartResults == None:
		return make_response('no open cart found for user', 500)
	
	cartId = cartResults[0]
	
	itemInfo = GetItemInfoFromNameOrId(itemName=reqData['item_name'])
	
	with dbLock:
		dataToInsert = (cartId, itemInfo[0], reqData['quantity'], itemInfo[1],)
		dbCursor.execute('INSERT INTO shopping_cart_items(cart_id, item_id, quantity, price) VALUES(?, ?, ?, ?)', dataToInsert)
		cartDbConn.commit()
	
	return 'success'

###########################################################################
##	
##	Adds an item to the user's existing open cart.  Returns an error if one
##	is not found.
##	
###########################################################################
@app.route('/get_cart_items', methods=['GET'])
@expects_json(GET_PURCHASE_CANCEL_SHOPPING_CART_SCHEMA)
def GetShoppingCartItems():
	global dbCursor
	
	reqData = request.get_json()
	
	userId = reqData['user_id']
	
	# @todo swelter: put this in a function as it's obviously used everywhere
	# get cart_id from user_id
	dbCursor.execute('SELECT id FROM shopping_carts WHERE user_id = ? AND status = "open"', (userId,))
	cartResults = dbCursor.fetchone()
	
	# return 500 error if no cart found
	if cartResults == None:
		return make_response('no_cart', 500)
	
	cartId = cartResults[0]
	
	dbCursor.execute('SELECT item_id, quantity, price FROM shopping_cart_items WHERE cart_id = ?', (cartId,))
	itemResults = dbCursor.fetchall()
	
	# list of tuples of cart items, format:
	#	* item_id
	#	* quantity
	#	* price
	cartItems = []
	for row in itemResults:
		tempInfo = GetItemInfoFromNameOrId(itemId=row[0])
		tempItem = {'item_id': row[0], 'quantity': row[1], 'price': row[2], 'item_name': tempInfo[3]}
		cartItems.append(tempItem)
	
	return jsonify({'items': cartItems})

###########################################################################
##	
##	Marks a cart as cancelled.
##	
###########################################################################
@app.route('/cancel_cart', methods=['POST'])
@expects_json(GET_PURCHASE_CANCEL_SHOPPING_CART_SCHEMA)
def CancelCart():
	global cartDbConn
	global dbCursor
	global dbLock
	
	reqData = request.get_json()
	
	userId = reqData['user_id']
	
	with dbLock:
		dbCursor.execute('UPDATE shopping_carts SET status = ? WHERE user_id = ? AND status = "open"', ('cancelled', userId,))
		cartDbConn.commit()
		
		if dbCursor.rowcount == 0:
			app.logger.log(level=logging.WARNING, msg='unable to find cart to cancel, okay for now...')
		else:
			app.logger.log(level=logging.INFO, msg=f'canceled cart for user_id={userId}')
	
	return 'success'

###########################################################################
##	
##	Returns all purchased shopping carts containing the passed in item,
##	including details about the user that ordered it
##	
###########################################################################
@app.route('/get_sc_containing_item', methods=['GET'])
@expects_json(GET_SC_CONTAINING_ITEM)
def GetScContainingItem():
	global dbCursor
	
	reqData = request.get_json()
	
	# get item information from items service
	itemInfo = GetItemInfoFromNameOrId(itemName=reqData['item_name'])
	
	# if a user_email is passed in, get the purchased carts associated with that user
	cartResults = None
	if 'user_id' in reqData:
		# # get user_id from users service
		userId = reqData['user_id']
		
		# @todo swelter: put this in a function as it's obviously used everywhere
		# get all purchased shopping carts for specified user
		dbCursor.execute('SELECT id FROM shopping_carts WHERE user_id = ? AND status == "purchased"', (userId,))
		cartResults = dbCursor.fetchall()
	else:
		# get all purchased shopping carts
		dbCursor.execute('SELECT id FROM shopping_carts WHERE status == "purchased"')
		cartResults = dbCursor.fetchall()
	
	cartsContainingItem = []
	for cart in cartResults:
		dbCursor.execute('SELECT cart_id FROM shopping_cart_items WHERE item_id = ? AND cart_id = ?', (itemInfo[0], cart[0],))
		results = dbCursor.fetchall()
		for result in results:
			if result[0] not in cartsContainingItem:
				cartsContainingItem.append(result[0])
	
	# now we have a list of cart_ids that contain the queried item
	# build a list of tuples, where each tuple is (cart_id, user_name, user_email)
	# and return that
	finalResults = []
	for cartId in cartsContainingItem:
		# get user_id that purchased cart
		dbCursor.execute('SELECT user_id FROM shopping_carts WHERE id = ?', (cartId,))
		tempUserId = dbCursor.fetchone()[0]
		
		tempUserInfo = GetUserInfoFromEmailOrId(userId=tempUserId)
		
		tempResult = (
			cartId,
			f"{tempUserInfo['first_name']} {tempUserInfo['last_name']}",
			tempUserInfo['email']
		)
		finalResults.append(tempResult)
	
	return jsonify(finalResults)

###################################
#                                 #
#                                 #
#            RABBIT MQ            #
#                                 #
#                                 #
###################################

###########################################################################
##	
##	RabbitMq initialization
##	
###########################################################################
def RabbitMqInit():
	# setup hello world consumer
	helloWorldThread = threading.Thread(target=SetupRabbitMqHelloWorldConsumer, daemon=True)
	helloWorldThread.start()
	
	# setup order created consumer
	orderCreatedConsumerThread = threading.Thread(target=SetupRabbitMqOrderCreatedConsumer, daemon=True)
	orderCreatedConsumerThread.start()
	
	# setup shopping cart validated producer
	shoppingCartValidatedProducerThread = threading.Thread(target=SetupRabbitMqShoppignCartValidatedProducer, daemon=True)
	shoppingCartValidatedProducerThread.start()
	
	# setup order failed producer
	orderFailedProducerThread = threading.Thread(target=SetupRabbitMqOrderFailedProducer, daemon=True)
	orderFailedProducerThread.start()
	
	return

###########################################################################
##	
##	Setup RabbitMq hello world consumer
##	
###########################################################################
def SetupRabbitMqHelloWorldConsumer():
	# read rabbitmq connection url from environment variable
	amqpUrl = os.environ['AMQP_URL']
	urlParams = pika.URLParameters(amqpUrl)
	
	# connect to rabbitmq
	connection = pika.BlockingConnection(urlParams)
	
	app.logger.info('Successfully connected to RabbitMQ')
	rmqChannel = connection.channel()
	
	# declare a new queue
	rmqChannel.exchange_declare(exchange='HelloWorldTesting', exchange_type='fanout')
	result = rmqChannel.queue_declare(queue='', exclusive=True)
	queueName = result.method.queue
	rmqChannel.queue_bind(exchange='HelloWorldTesting', queue=queueName)
	
	# setup consuming queues
	rmqChannel.basic_consume(queue=result.method.queue, on_message_callback=RmqHelloWorldCb, auto_ack=True)
	
	# start consuming
	rmqChannel.start_consuming()
	
	return

###########################################################################
##	
##	Setup RabbitMq order created consumer
##	
###########################################################################
def SetupRabbitMqOrderCreatedConsumer():
	# read rabbitmq connection url from environment variable
	amqpUrl = os.environ['AMQP_URL']
	urlParams = pika.URLParameters(amqpUrl)
	
	# connect to rabbitmq
	connection = pika.BlockingConnection(urlParams)
	
	app.logger.info('Successfully connected to RabbitMQ')
	rmqChannel = connection.channel()
	
	# declare a new queue
	rmqChannel.queue_declare(queue='OrderCreatedQueue')
	rmqChannel.basic_qos(prefetch_count=1)
	
	# setup consuming queues
	rmqChannel.basic_consume(queue='OrderCreatedQueue',
							 on_message_callback=RmqOrderCreatedCallback)
	
	# rmqChannel.start_consuming()
	# connection.process_data_events()
	
	# start consuming
	rmqChannel.start_consuming()
	
	return

###########################################################################
##	
##	Setup RabbitMq shopping cart validated producer
##	
###########################################################################
def SetupRabbitMqShoppignCartValidatedProducer():
	global shoppingCartValidatedChannel
	
	# read rabbitmq connection url from environment variable
	amqpUrl = os.environ['AMQP_URL']
	urlParams = pika.URLParameters(amqpUrl)
	
	# connect to rabbitmq
	connection = pika.BlockingConnection(urlParams)
	
	app.logger.info('Successfully connected to RabbitMQ')
	shoppingCartValidatedChannel = connection.channel()
	
	shoppingCartValidatedChannel.queue_declare(queue='ShoppingCartValidatedQueue')
	
	return

###########################################################################
##	
##	Setup RabbitMq order failed producer
##	
###########################################################################
def SetupRabbitMqOrderFailedProducer():
	global orderFailedChannel
	
	# read rabbitmq connection url from environment variable
	amqpUrl = os.environ['AMQP_URL']
	urlParams = pika.URLParameters(amqpUrl)
	
	# connect to rabbitmq
	connection = pika.BlockingConnection(urlParams)
	
	app.logger.info('Successfully connected to RabbitMQ')
	orderFailedChannel = connection.channel()
	
	orderFailedChannel.queue_declare(queue='OrderFailedQueue')
	
	return

###########################################################################
##	
##	RabbitMq hello world consume callback
##	
###########################################################################
def RmqHelloWorldCb(channel, method, properties, body):
	data = body.decode('utf-8')
	app.logger.info(f'RMQ: {data}')
	
	return

###########################################################################
##	
##	RabbitMq hello world consume callback
##	
###########################################################################
def RmqOrderCreatedCallback(channel, method, properties, body):
	global cartDbConn
	global dbCursor
	global dbLock
	global shoppingCartValidatedChannel
	global shoppingCartValidatedChannelLock
	global orderFailedChannel
	global orderFailedChannelLock
	
	data = body.decode('utf-8')
	parsedData = json.loads(data)
	app.logger.info(f'Shopping carts service consumed event in OrderCreatedQueue, data is {json.dumps(parsedData)}')
	channel.basic_ack(delivery_tag=method.delivery_tag)
	
	userId = parsedData['user_id']
	orderId = parsedData['order_id']
	
	# @todo swelter: mark shopping cart as closed and fetch all items in the cart
	# get cart_id from user_Id
	dbCursor.execute('SELECT id FROM shopping_carts WHERE user_id = ? AND status = "open"', (userId,))
	cartResults = dbCursor.fetchone()
	
	# if no shopping cart found, set status message to data, publish event and return
	if cartResults == None:
		parsedData['error_message'] = 'no_sc_found'
		orderFailedChannel.basic_publish(exchange='',
											 routing_key='OrderFailedQueue',
											 body=json.dumps(parsedData),
											 properties=pika.BasicProperties(delivery_mode=2))
		
		# order error event pubhlished, we're done here
		return
	
	cartId = cartResults[0]

	# mark cart as closed
	with dbLock:
		dbCursor.execute('UPDATE shopping_carts SET status = ? WHERE id = ?', ('closed', cartId,))
		cartDbConn.commit()
	
	# fetch all items in cart
	dbCursor.execute('SELECT item_id, quantity, price FROM shopping_cart_items WHERE cart_id = ?', (cartId,))
	itemResults = dbCursor.fetchall()
	
	orderItems = []
	for item in itemResults:
		tempItem = {'item_id': item[0], 'item_quantity': item[1], 'item_price': item[2]}
		orderItems.append(tempItem)
	
	with shoppingCartValidatedChannelLock:
		eventData = {
			'user_id': userId,
			'order_id': orderId,
			'items': orderItems
		}
		shoppingCartValidatedChannel.basic_publish(exchange='',
												   routing_key='ShoppingCartValidatedQueue',
												   body=json.dumps(eventData),
												   properties=pika.BasicProperties(delivery_mode=2))
		# app.logger.info(f'Shopping cart service published event in ShoppingCartValidatedQueue')
	
	return

if __name__ == '__main__':
	RabbitMqInit()
	
	dbPath = 'db/shopping_carts.db'
	cartDbConn = sqlite3.connect(database=dbPath, check_same_thread=False)
	dbCursor = cartDbConn.cursor()
	
	app.run(host='0.0.0.0', port=SHOPPING_CART_SERVICE_PORT)