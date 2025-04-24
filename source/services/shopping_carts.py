from flask import Flask, jsonify, request, make_response
from flask_expects_json import expects_json
import argparse
import logging
import os
import sqlite3
import threading

app = Flask(__name__)
app.logger.setLevel(logging.INFO)

# globals
cartDbConn = None
dbCursor = None
dbLock = threading.Lock()

CREATE_SHOPPING_CART_SCHEMA = {
	"type": "object",
	"properties": {
		"user_id": {"type": "integer"}
	},
	"required": []
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
		"item_id": {"type": "integer"},
		"item_quantity": {"type": "integer"}
	},
	"required": ["user_id", "item_id", "quantity"]
}

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
	
	# check if cart exists
	dbCursor.execute('SELECT id FROM shopping_carts WHERE user_id = ? AND status = ?', (reqData['user_id'], 'open',))
	results = dbCursor.fetchone()
	
	# if we found an existing cart, return it and we're done
	if results != None:
		return jsonify({'cart_id': results[0]})
	
	# no cart found, create one and return the id
	with dbLock:
		dataToInsert = (reqData['user_id'], 'open')
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
	
	# get cart_id from user_Id
	dbCursor.execute('SELECT id FROM shopping_carts WHERE user_id = ? AND status = "open"', (reqData['user_id'],))
	cartResults = dbCursor.fetchone()
	
	# return 500 error if no cart found
	if cartResults == None:
		return make_response('no open cart found for user', 500)
	
	cartId = cartResults[0]
	
	# TODO swelter: fetch item price from item service
	itemPrice = 12
	
	with dbLock:
		dataToInsert = (cartId, reqData['item_id'], reqData['quantity'], itemPrice,)
		print(dataToInsert)
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
	
	# TODO swelter: put this in a function as it's obviously used everywhere
	# get cart_id from user_id
	dbCursor.execute('SELECT id FROM shopping_carts WHERE user_id = ? AND status = "open"', (reqData['user_id'],))
	cartResults = dbCursor.fetchone()
	
	# return 500 error if no cart found
	if cartResults == None:
		return make_response('no open cart found for user', 500)
	
	cartId = cartResults[0]
	
	dbCursor.execute('SELECT item_id, quantity, price FROM shopping_cart_items WHERE cart_id = ?', (cartId,))
	itemResults = dbCursor.fetchall()
	
	# list of tuples of cart items, format:
	#	* item_id
	#	* quantity
	#	* price
	cartItems = []
	for row in itemResults:
		tempItem = {'item_id': row[0], 'quantity': row[1], 'price': row[2]}
		cartItems.append(tempItem)
	
	return jsonify({'items': cartItems})

###########################################################################
##	
##	Marks a cart as closed and returns all associated items with it.
##	
###########################################################################
@app.route('/purchase_cart', methods=['POST'])
@expects_json(GET_PURCHASE_CANCEL_SHOPPING_CART_SCHEMA)
def PurchaseShoppingCart():
	global cartDbConn
	global dbCursor
	global dbLock
	
	reqData = request.get_json()
	
	# get cart_id from user_Id
	dbCursor.execute('SELECT id FROM shopping_carts WHERE user_id = ? AND status = "open"', (reqData['user_id'],))
	cartResults = dbCursor.fetchone()
	
	# return 500 error if no cart found
	if cartResults == None:
		return make_response('no open cart found for user', 500)
	
	cartId = cartResults[0]
	
	dbCursor.execute('SELECT item_id, quantity, price FROM shopping_cart_items WHERE cart_id = ?', (cartId,))
	itemResults = dbCursor.fetchall()
	
	# list of tuples of cart items, format:
	#	* item_id
	#	* quantity
	#	* price
	cartItems = []
	for row in itemResults:
		tempItem = {'item_id': row[0], 'quantity': row[1], 'price': row[2]}
		cartItems.append(tempItem)
	
	# mark cart as purchased
	with dbLock:
		dbCursor.execute('UPDATE shopping_carts SET status = ? WHERE user_id = ? AND status = "open"', ('closed', reqData['user_id']))
		cartDbConn.commit()
	
	app.logger.log(level=logging.INFO, msg=f'closed cart for user_id={reqData["user_id"]}')
	
	return jsonify({'items': cartItems})

###########################################################################
##	
##	Marks a cart as closed.
##	
###########################################################################
@app.route('/cancel_cart', methods=['POST'])
@expects_json(GET_PURCHASE_CANCEL_SHOPPING_CART_SCHEMA)
def CancelCart():
	global cartDbConn
	global dbCursor
	global dbLock
	
	reqData = request.get_json()
	
	with dbLock:
		dbCursor.execute('UPDATE shopping_carts SET status = ? WHERE user_id = ? AND status = "open"', ('closed', reqData['user_id'],))
		cartDbConn.commit()
		
		if dbCursor.rowcount == 0:
			app.logger.log(level=logging.WARNING, msg='unable to find cart to cancel, okay for now...')
		else:
			app.logger.log(level=logging.INFO, msg=f'canceled cart for user_id={reqData["user_id"]}')
	
	return 'success'

if __name__ == '__main__':
	parser = argparse.ArgumentParser()
	parser.add_argument('--db-directory', dest='db_directory', required=True)
	args = parser.parse_args()
	
	dbPath = os.path.join(args.db_directory, 'shopping_carts.db')
	# check_same_thread = False means the write operations aren't thread safe, but we take care of that with global var dbLock
	cartDbConn = sqlite3.connect(database=dbPath, check_same_thread=False)
	dbCursor = cartDbConn.cursor()
	
	app.run(debug=True)