from flask import Flask, jsonify, request, make_response
from flask_expects_json import expects_json
import json
import logging
import os
import pika
import requests
import sqlite3
import threading

app = Flask(__name__)
app.logger.setLevel(logging.INFO)

orderDbConn = None
dbCursor = None
dbLock = threading.Lock()

# channel for publishing hello world events
rmqHelloWorldChannel		= None

# channel for publishing order created events
rmqOrderCreatedChannel		= None
orderCreatedChannelLock		= threading.Lock()
orderItemsValidatedChannel	= None

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

@app.route('/')
def HelloWorld():
	global rmqHelloWorldChannel
	
	rmqHelloWorldChannel.basic_publish(exchange='HelloWorldTesting', routing_key='', body=json.dumps({'hello': 'world'}))
	
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
	global rmqOrderCreatedChannel
	global orderCreatedChannelLock
	global orderDbConn
	global dbCursor
	global dbLock
	
	reqData = request.get_json()
	
	userId = GetUserIdFromEmail(email=reqData['user_email'])

	if userId == None:
		return make_response('no user found with that cart', 500)
	
	with orderCreatedChannelLock:
		with dbLock:
			dbCursor.execute('INSERT INTO orders(user_id, status) VALUES (?, ?)', (userId, 'pending',))
			orderDbConn.commit()
			cartId = dbCursor.lastrowid
		
		# publish order created event
		eventData = {
			'user_id': userId,
			'order_id': cartId
		}
		rmqOrderCreatedChannel.basic_publish(exchange='',
											 routing_key='OrderCreatedQueue',
											 body=json.dumps(eventData),
											 properties=pika.BasicProperties(delivery_mode=2))
		# app.logger.info('Order service published event in OrderCreatedQueue')
	
	return 'success'

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
	
	itemInfo = GetItemInfoFromNameOrId(itemName=reqData['item_name'])
	
	# if user email is supplied, filter by the ID, otherwise just get all purchased carts
	if 'user_email' in reqData:
		userId = GetUserIdFromEmail(email=reqData['user_email'])
		
		dbCursor.execute('SELECT id FROM orders WHERE user_id = ? AND status == "purchased"', (userId,))
		ordersToSearch = dbCursor.fetchall()
	else:
		dbCursor.execute('SELECT id FROM orders WHERE status == "purchased"')
		ordersToSearch = dbCursor.fetchall()
	
	# go thru all orders that match search criteria, and extract order_id whenever the order contains the matching item_id
	ordersContainingItem = []
	for order in ordersToSearch:
		dbCursor.execute('SELECT order_id FROM order_items WHERE item_id = ? AND order_id = ?', (itemInfo[0], order[0],))
		results = dbCursor.fetchall()
		for result in results:
			if result[0] not in ordersContainingItem:
				ordersContainingItem.append(result[0])
	
	# build list of tuples, where each tuple is (orderId, first and last name, user email)
	finalResults = []
	for orderId in ordersContainingItem:
		# get user_id that purchased the order
		dbCursor.execute('SELECT user_id FROM orders WHERE id = ?', (orderId,))
		tempUserId = dbCursor.fetchone()[0]
		
		tempUserInfo = GetUserInfoFromEmailOrId(userId=tempUserId)
		
		tempResult = (
			orderId,
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
	# setup hello world publisher
	setupHelloWorldPublisherThread = threading.Thread(target=SetupRabbitMqHelloWorldPublisher, daemon=True)
	setupHelloWorldPublisherThread.start()
	
	# setup order created publisher
	orderCreatedPublisherThread = threading.Thread(target=SetupRabbitMqOrderCreatedPublisher, daemon=True)
	orderCreatedPublisherThread.start()
	
	# setup order items validated consumer
	orderItemsValidatedConsumerThread = threading.Thread(target=SetupRabbitMqOrderItemsValidatedConsumer, daemon=True)
	orderItemsValidatedConsumerThread.start()
	
	# setup order failed consumer
	orderFailedConsumerThread = threading.Thread(target=SetupRabbitMqOrderFailedConsumer, daemon=True)
	orderFailedConsumerThread.start()
	
	return

###########################################################################
##	
##	Setup RabbitMq hello world consumer
##	
###########################################################################
def SetupRabbitMqHelloWorldPublisher():
	global rmqHelloWorldChannel
	
	# read rabbitmq connection url from environment variable
	amqpUrl = os.environ['AMQP_URL']
	urlParams = pika.URLParameters(amqpUrl)
	
	# connect to rabbitmq
	connection = pika.BlockingConnection(urlParams)
	
	app.logger.info('Successfully connected to RabbitMQ')
	rmqHelloWorldChannel = connection.channel()
	
	# declare a new queue
	rmqHelloWorldChannel.exchange_declare(exchange='HelloWorldTesting', exchange_type='fanout')
	
	return

###########################################################################
##	
##	Setup RabbitMq order created publisher
##	
###########################################################################
def SetupRabbitMqOrderCreatedPublisher():
	global rmqOrderCreatedChannel
	
	# read rabbitmq connection url from environment variable
	amqpUrl = os.environ['AMQP_URL']
	urlParams = pika.URLParameters(amqpUrl)
	
	# connect to rabbitmq
	connection = pika.BlockingConnection(urlParams)
	
	app.logger.info('Successfully connected to RabbitMQ')
	rmqOrderCreatedChannel = connection.channel()
	
	rmqOrderCreatedChannel.queue_declare(queue='OrderCreatedQueue')
	
	return

###########################################################################
##	
##	Setup RabbitMq order items validated consumer
##	
###########################################################################
def SetupRabbitMqOrderItemsValidatedConsumer():
	# read rabbitmq connection url from environment variable
	amqpUrl = os.environ['AMQP_URL']
	urlParams = pika.URLParameters(amqpUrl)
	
	# connect to rabbitmq
	connection = pika.BlockingConnection(urlParams)
	
	app.logger.info('Successfully connected to RabbitMQ')
	rmqChannel = connection.channel()
	
	# declare a new queue
	rmqChannel.queue_declare(queue='OrderItemsValidatedQueue')
	rmqChannel.basic_qos(prefetch_count=1)
	
	# setup consuming queues
	rmqChannel.basic_consume(queue='OrderItemsValidatedQueue',
							 on_message_callback=OrderItemsValidatedCallback)
	
	rmqChannel.start_consuming()
	
	# start consuming
	rmqChannel.start_consuming()
	
	return

###########################################################################
##	
##	Setup RabbitMq order items validated consumer
##	
###########################################################################
def SetupRabbitMqOrderFailedConsumer():
	# read rabbitmq connection url from environment variable
	amqpUrl = os.environ['AMQP_URL']
	urlParams = pika.URLParameters(amqpUrl)
	
	# connect to rabbitmq
	connection = pika.BlockingConnection(urlParams)
	
	app.logger.info('Successfully connected to RabbitMQ')
	rmqChannel = connection.channel()
	
	# declare a new queue
	rmqChannel.queue_declare(queue='OrderFailedQueue')
	rmqChannel.basic_qos(prefetch_count=1)
	
	# setup consuming queues
	rmqChannel.basic_consume(queue='OrderFailedQueue',
							 on_message_callback=OrderFailedCallback)
	
	# rmqChannel.start_consuming()
	
	# start consuming
	rmqChannel.start_consuming()
	
	return

###########################################################################
##	
##	RabbitMq order items validated consume callback
##	
###########################################################################
def OrderItemsValidatedCallback(channel, method, properties, body):
	global orderDbConn
	global dbCursor
	global dbLock
	
	data = body.decode('utf-8')
	parsedData = json.loads(data)
	app.logger.info(f'Order service consumed event in OrderItemsValidatedQueue, data is {json.dumps(parsedData)}')
	channel.basic_ack(delivery_tag=method.delivery_tag)
	
	# @todo swelter: mark the order as purchased
	orderTotal = 0
	with dbLock:
		
		# add items to order_items table
		dataToInsert = []
		for item in parsedData['items']:
			itemId = item['item_id']
			itemQuantity = item['item_quantity']
			itemPrice = item['item_price']
			
			orderTotal += itemPrice * itemQuantity
			
			dataToInsert.append((parsedData['order_id'], itemId, itemQuantity, itemPrice,))
		dbCursor.executemany('INSERT INTO order_items(order_id, item_id, quantity, price) VALUES (?, ?, ?, ?)', dataToInsert)
		orderDbConn.commit()
		
		# mark order as purchased and set the price
		dbCursor.execute('UPDATE orders SET status = ?, total_price = ? WHERE id = ? AND user_id = ?', ('purchased', orderTotal, parsedData['order_id'], parsedData['user_id'],))
		orderDbConn.commit()
	
	return

###########################################################################
##	
##	RabbitMq order failed consume callback
##	
###########################################################################
def OrderFailedCallback(channel, method, properties, body):
	global orderDbConn
	global dbCursor
	global dbLock
	
	data = body.decode('utf-8')
	parsedData = json.loads(data)
	app.logger.info(f'Order service consumed event OrderFailedCallback, data is {json.dumps(parsedData)}')
	channel.basic_ack(delivery_tag=method.delivery_tag)
	
	# set the error message to the order status
	with dbLock:
		dbCursor.execute('UPDATE orders SET status = ? WHERE id = ?', (parsedData['error_message'], parsedData['order_id'],))
		orderDbConn.commit()
	
	return

if __name__ == '__main__':
	RabbitMqInit()
	
	dbPath = 'db/orders.db'
	orderDbConn = sqlite3.connect(database=dbPath, check_same_thread=False)
	dbCursor = orderDbConn.cursor()
	
	app.run(host='0.0.0.0', port=ORDER_SERVICE_PROT)