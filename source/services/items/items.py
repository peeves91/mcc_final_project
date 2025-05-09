from flask import Flask, jsonify, request, make_response
from flask_expects_json import expects_json
import json
import logging
import os
import pika
import sqlite3
import threading

app = Flask(__name__)
app.logger.setLevel(logging.INFO)

# constants
ORDER_SERVICE_PROT			= 5000
SHOPPING_CART_SERVICE_PORT	= 6000
USERS_SERVICE_PORT			= 7000
ITEMS_SERVICE_PORT			= 8000

# globals
itemsDbConn = None
dbCursor = None
dbLock = threading.Lock()

# rabbitmq channel
rmqChannel = None
orderItemsValidatedChannel = None
orderItemsValidatedChannelLock = threading.Lock()
orderFailedChannel = None
orderFailedChannelLock = threading.Lock()

@app.route('/')
def HelloWorld():
	return "hello, world"

GET_ITEM_INFO_SCHEMA = {
	"type": "object",
	"properties": {
		"item_name": {"type": "string"},
		"item_id": {"type": "integer"}
	}
}

VALIDATE_ITEMS_SCHEMA = {
	"$schema": "http://json-schema.org/draft-07/schema#",
	"items": {
		"type": "object",
		"properties": {
			"name": {"type": "string"},
			"quantity": {"type": "integer"}
		},
		"required": ["name", "quantity"]
	}
}

DECREASE_ITEM_QUANTITY_SCHEMA = {
	"type": "object",
	"properties": {
		"item_id": {"type": "integer"},
		"quantity": {"type": "integer"}
	},
	"required": ["item_id", "quantity"]
}

###########################################################################
##	
##	Returns the item ID, quantity, and price from the item name.
##	
###########################################################################
@app.route('/get_item_info', methods=['GET'])
@expects_json(GET_ITEM_INFO_SCHEMA)
def GetItemInfo():
	global itemsDbConn
	
	reqData = request.get_json()
	
	if 'item_name' in reqData:
		searchColumn = 'product_name'
		searchValue = reqData['item_name']
	elif 'item_id' in reqData:
		searchColumn = 'id'
		searchValue = reqData['item_id']
	else:
		return make_response('no valid search criteria specified', 500)
	
	dbCursor.execute(f'SELECT id, price, quantity_in_stock, product_name FROM items WHERE {searchColumn} = ?', (searchValue,))
	item = dbCursor.fetchall()[0]
	
	return jsonify({'item': item})

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
	shoppingCartValidatedConsumerThread = threading.Thread(target=SetupRabbitMqShoppingCartValidatedConsumer, daemon=True)
	shoppingCartValidatedConsumerThread.start()
	
	# setup shopping cart validated producer
	orderItemsValidatedProducerThread = threading.Thread(target=SetupRabbitMqOrderItemsValidatedProducer, daemon=True)
	orderItemsValidatedProducerThread.start()
	
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
##	Setup RabbitMq shopping cart validated consumer
##	
###########################################################################
def SetupRabbitMqShoppingCartValidatedConsumer():
	# read rabbitmq connection url from environment variable
	amqpUrl = os.environ['AMQP_URL']
	urlParams = pika.URLParameters(amqpUrl)
	
	# connect to rabbitmq
	connection = pika.BlockingConnection(urlParams)
	
	app.logger.info('Successfully connected to RabbitMQ')
	rmqChannel = connection.channel()
	
	# declare a new queue
	rmqChannel.queue_declare(queue='ShoppingCartValidatedQueue')
	rmqChannel.basic_qos(prefetch_count=1)
	
	# setup consuming queues
	rmqChannel.basic_consume(queue='ShoppingCartValidatedQueue',
							 on_message_callback=RmqOrderCreatedCallback)
	
	rmqChannel.start_consuming()
	
	# start consuming
	rmqChannel.start_consuming()
	
	return

###########################################################################
##	
##	Setup RabbitMq order items validated producer
##	
###########################################################################
def SetupRabbitMqOrderItemsValidatedProducer():
	global orderItemsValidatedChannel
	
	# read rabbitmq connection url from environment variable
	amqpUrl = os.environ['AMQP_URL']
	urlParams = pika.URLParameters(amqpUrl)
	
	# connect to rabbitmq
	connection = pika.BlockingConnection(urlParams)
	
	app.logger.info('Successfully connected to RabbitMQ')
	orderItemsValidatedChannel = connection.channel()
	
	orderItemsValidatedChannel.queue_declare(queue='OrderItemsValidatedQueue')
	
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
##	RabbitMq order created consume callback
##	
###########################################################################
def RmqOrderCreatedCallback(channel, method, properties, body):
	global itemsDbConn
	global dbCursor
	global dbLock
	global orderItemsValidatedChannel
	global orderItemsValidatedChannelLock
	
	data = body.decode('utf-8')
	parsedData = json.loads(data)
	app.logger.info(f'Items service consumed event in OrderItemsValidatedQueue, data is {json.dumps(parsedData)}')
	channel.basic_ack(delivery_tag=method.delivery_tag)
	
	# list of tuples of (new_quantity, item_id) to write if all quantities are valid
	dataToInsert = []
	
	# validate all items are in stock
	for item in parsedData['items']:
		dbCursor.execute('SELECT quantity_in_stock FROM items WHERE id = ?', (item['item_id'],))
		quantityInStock = dbCursor.fetchone()[0]
		
		# if not enough in stock publish order failed event and return
		if item['item_quantity'] > quantityInStock:
			eventData = {
				'user_id': parsedData['user_id'],
				'order_id': parsedData['order_id'],
				'error_message': 'not_enough_in_stock'
			}
			orderFailedChannel.basic_publish(exchange='',
												routing_key='OrderFailedQueue',
												body=json.dumps(eventData),
												properties=pika.BasicProperties(delivery_mode=2))
			
			# order error event pubhlished, we're done here
			return
		
		dataToInsert.append((quantityInStock - item['item_quantity'], item['item_id'],))
	
	# if we got here, all items are valid, decrement stock
	with dbLock:
		dbCursor.executemany('UPDATE items SET quantity_in_stock = ? WHERE id = ?', dataToInsert)
		itemsDbConn.commit()
	
	with orderItemsValidatedChannelLock:
		orderItemsValidatedChannel.basic_publish(exchange='',
												 routing_key='OrderItemsValidatedQueue',
												 body=json.dumps(parsedData),
												 properties=pika.BasicProperties(delivery_mode=2))
		# app.logger.info(f'Items service published event in OrderItemsValidatedQueue')
	
	return

if __name__ == '__main__':
	RabbitMqInit()
	
	dbPath = 'db/items.db'
	# check_same_thread = False means the write operations aren't thread safe, but we take care of that with global var dbLock
	itemsDbConn = sqlite3.connect(database=dbPath, check_same_thread=False)
	dbCursor = itemsDbConn.cursor()
	
	app.run(host='0.0.0.0', port=ITEMS_SERVICE_PORT)