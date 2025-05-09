from flask import Flask, jsonify, request, make_response
from flask_expects_json import expects_json
import datetime
import logging
import os
import pika
import sqlite3
import threading

app = Flask(__name__)
app.logger.setLevel(logging.INFO)

dbPath = None

# rabbitmq channel
rmqChannel = None

# constants
ORDER_SERVICE_PROT			= 5000
SHOPPING_CART_SERVICE_PORT	= 6000
USERS_SERVICE_PORT			= 7000
ITEMS_SERVICE_PORT			= 8000

CREATE_USER_SCHEMA = {
	"type": "object",
	"properties": {
		"email": {"type": "string"},
		"first_name": {"type": "string"},
		"last_name": {"type": "string"},
		"phone": {"type": "string"},
		"address": {"type": "string"},
		"credit_card": {"type": "string"}
	},
	"required": ["email", "first_name", "last_name", "phone", "address", "credit_card"]
}

GET_USER_SCHEMA = {
	"type": "object",
	"properties": {
		"user_email": {"type": "string"},
		"last_name": {"type": "string"},
		"user_id": {"type": "integer"}
	}
}

@app.route('/')
def HelloWorld():
	return "hello, world"

# @todo swelter: add schema here
@app.route('/get_user', methods=['GET'])
@expects_json(GET_USER_SCHEMA)
def GetUser():
	reqData = request.get_json()
	
	if 'last_name' in reqData:
		searchColumn = 'last_name'
		searchData = reqData['last_name']
	elif 'user_id' in reqData:
		searchColumn = 'id'
		searchData = reqData['user_id']
	elif 'user_email' in reqData:
		searchColumn = 'email'
		searchData = reqData['user_email']
	else:
		return make_response('no valid search criteria specified', 500)
	
	usersConn = sqlite3.connect(database=dbPath)
	usersCursor = usersConn.cursor()
	usersCursor.execute(f'SELECT id, email, first_name, last_name, updated_at FROM users WHERE {searchColumn} = ?', (searchData,))
	usersResults = usersCursor.fetchall()
	
	profilesConn = sqlite3.connect(database=dbPath)
	profilesCursor = profilesConn.cursor()
	
	jsonResults = {'results': []}
	if usersResults:
		for row in usersResults:
			tempResult = {}
			
			# get basic user information from users table
			tempResult['user_id'] = row[0]
			tempResult['email'] = row[1]
			tempResult['first_name'] = row[2]
			tempResult['last_name'] = row[3]
			tempResult['updated_at'] = row[4]
			
			# get further information from user_profiles table
			profilesCursor.execute('SELECT address, phone FROM user_profiles WHERE user_id = ?', (tempResult['user_id'],))
			profileData = profilesCursor.fetchall()[0]
			tempResult['address'] = profileData[0]
			tempResult['phone'] = profileData[1]
			
			jsonResults['results'].append(tempResult)
	
	return jsonify(jsonResults)

@app.route('/create_user', methods=['POST'])
@expects_json(CREATE_USER_SCHEMA)
def CreateUser():
	if request.method != 'POST':
		return 'get not available for endpoint', 400
	
	reqData = request.get_json()
	
	usersConn = sqlite3.connect(database=dbPath)
	usersCursor = usersConn.cursor()
	
	currTimeStr = str(datetime.datetime.now())
	
	# create user in users table
	dataToInsert = (reqData['email'], reqData['first_name'], reqData['last_name'], currTimeStr, currTimeStr,)
	usersCursor.execute('INSERT INTO users(email, first_name, last_name, created_at, updated_at) VALUES (?, ?, ?, ?, ?)', dataToInsert)
	usersConn.commit()
	userId = usersCursor.lastrowid
	
	# create user profile in user_profiles table
	profilesConn = sqlite3.connect(database=dbPath)
	profilesCursor = profilesConn.cursor()
	dataToInsert = (userId, reqData['address'], reqData['phone'], reqData['credit_card'],)
	profilesCursor.execute('INSERT INTO user_profiles(user_id, address, phone, credit_card) VALUES(?, ?, ?, ?)', dataToInsert)
	profilesConn.commit()
	
	return 'success'

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
	helloWorldThread = threading.Thread(target=SetupRabbitMqHelloWorldConsumer, daemon=True)
	helloWorldThread.start()
	
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
##	RabbitMq hello world consume callback
##	
###########################################################################
def RmqHelloWorldCb(channel, method, properties, body):
	data = body.decode('utf-8')
	app.logger.info(f'RMQ: {data}')
	
	return

if __name__ == '__main__':
	RabbitMqInit()
	
	dbPath = 'db/users.db'
	
	app.run(host='0.0.0.0', port=USERS_SERVICE_PORT)