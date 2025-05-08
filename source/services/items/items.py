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

###########################################################################
##	
##	Validate items can all be purchased.  Returns 200 if yes, returns
##	400 if not.
##	
###########################################################################
@app.route('/validate_items', methods=['GET'])
@expects_json(VALIDATE_ITEMS_SCHEMA)
def ValidateItems():
	global itemsDbConn
	
	reqData = request.get_json()
	
	items = reqData['items']
	for item in items:
		itemName = item['item_name']
		quantity = item['quantity']
		
		dbCursor.execute('SELECT id, price, quantity_in_stock FROM items WHERE product_name = ?', (itemName,))
		dbItem = dbCursor.fetchall()[0]
		
		if dbItem[2] < quantity:
			return make_response(f'"{itemName}" not enough in stock', 500)
	
	return 'success'

###########################################################################
##	
##	Validate items can all be purchased.  Returns 200 if yes, returns
##	400 if not.
##	
###########################################################################
@app.route('/decrease_item_stock', methods=['POST'])
@expects_json(DECREASE_ITEM_QUANTITY_SCHEMA)
def DecreaseItemStock():
	global itemsDbConn
	global dbLock
	
	reqData = request.get_json()
	
	itemId = reqData['item_id']
	purchasedQuantity = reqData['quantity']
	
	# fetch current quantity
	dbCursor.execute('SELECT quantity_in_stock FROM items WHERE id = ?', (itemId,))
	existingQuantity = dbCursor.fetchall()[0][0]
	
	with dbLock:
		dbCursor.execute('UPDATE items SET quantity_in_stock  = ? WHERE id = ?', (existingQuantity - purchasedQuantity, itemId,))
	
	return 'success'

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
	result = rmqChannel.queue_declare(queue='', exclusive=True)
	queueName = result.method.queue
	# rmqChannel.queue_bind(exchange='testing', queue=result.method.queue)
	rmqChannel.queue_bind(exchange='testing', queue=queueName)
	
	# to make sure the consumer receives only one message at a time
	# next message is received only after acking the previous one
	# rmqChannel.basic_qos(prefetch_count=1)
	
	# setup consuming queues
	# rmqChannel.basic_consume(queue='HelloWorldQueue', on_message_callback=RmqHelloWorldCb)
	rmqChannel.basic_consume(queue=result.method.queue, on_message_callback=RmqHelloWorldCb, auto_ack=True)
	
	# start consuming
	rmqChannel.start_consuming()
	
	return

def RmqHelloWorldCb(channel, method, properties, body):
	data = body.decode('utf-8')
	app.logger.info(f'RMQ: {data}')
	# channel.basic_ack(delivery_tag=method.delivery_tag)
	
	return

if __name__ == '__main__':
	rmqThread = threading.Thread(target=SetupRabbitMq, daemon=True)
	rmqThread.start()
	
	dbPath = 'db/items.db'
	# check_same_thread = False means the write operations aren't thread safe, but we take care of that with global var dbLock
	itemsDbConn = sqlite3.connect(database=dbPath, check_same_thread=False)
	dbCursor = itemsDbConn.cursor()
	
	app.run(host='0.0.0.0', port=ITEMS_SERVICE_PORT)