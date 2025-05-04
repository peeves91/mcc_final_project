from flask import Flask, jsonify, request, make_response
from flask_expects_json import expects_json
from typing import List, Dict
import argparse
import json
import logging
import os
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

CREATE_SHOPPING_CART_SCHEMA = {
	"type": "object",
	"properties": {
		"user_email": {"type": "string"}
	},
	"required": ["user_email"]
}

GET_PURCHASE_CANCEL_SHOPPING_CART_SCHEMA = {
	"type": "object",
	"properties": {
		"user_email": {"type": "string"}
	},
	"required": ["user_email"]
}

ADD_ITEM_SCHEMA = {
	"type": "object",
	"properties": {
		"user_email": {"type": "string"},
		"item_name": {"type": "string"},
		"quantity": {"type": "integer"}
	},
	"required": ["user_email", "item_name", "quantity"]
}

# helper functions
def GetUserIdFromEmail(email: str) -> int:
	url = f'http://127.0.0.1:{USERS_SERVICE_PORT}/get_user'
	getData = {'email': email}
	resp = requests.get(url=url, data=json.dumps(getData), headers=JSON_HEADER_DATATYPE)
	
	try:
		respJson = resp.json()
	except requests.exceptions.JSONDecodeError:
		return None
	
	# if no users found, return None
	if len(respJson['results']) == 0:
		return None
	
	foundUser = respJson['results'][0]
	return foundUser['user_id']

def GetItemInfoFromNameOrId(itemName: str=None, itemId: int=None) -> int:
	url = f'http://127.0.0.1:{ITEMS_SERVICE_PORT}/get_item_info'
	# getData = {'item_name': itemName}
	
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
		url = f'http://127.0.0.1:{ITEMS_SERVICE_PORT}/get_item_info'
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
	
	# get user_id from users service
	userId = GetUserIdFromEmail(email=reqData['user_email'])
	
	if userId == None:
		return make_response(f'no user found with email {reqData["user_email"]}', 500)
	
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
	
	# get user_id from users service
	userId = GetUserIdFromEmail(email=reqData['user_email'])
	
	if userId == None:
		return make_response(f'no user found with email {reqData["user_email"]}', 500)
	
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
	
	# get user_id from users service
	userId = GetUserIdFromEmail(email=reqData['user_email'])
	
	if userId == None:
		return make_response(f'no user found with email {reqData["user_email"]}', 500)
	
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
	
	# get user_id from users service
	userId = GetUserIdFromEmail(email=reqData['user_email'])
	
	if userId == None:
		return make_response(f'no user found with email {reqData["user_email"]}', 500)
	
	# get cart_id from user_Id
	dbCursor.execute('SELECT id FROM shopping_carts WHERE user_id = ? AND status = "open"', (userId,))
	cartResults = dbCursor.fetchone()
	
	# return 500 error if no cart found
	if cartResults == None:
		return make_response('no_cart', 500)
	
	cartId = cartResults[0]
	
	dbCursor.execute('SELECT item_id, quantity, price FROM shopping_cart_items WHERE cart_id = ?', (cartId,))
	itemResults = dbCursor.fetchall()
	
	# @todo swelter: add a simple payment service for additional complexity
	
	# list of tuples of cart items, format:
	#	* item_id
	#	* quantity
	#	* price
	cartItems = []
	for row in itemResults:
		tempItem = {'item_id': row[0], 'quantity': row[1], 'price': row[2]}
		
		stockInfo = GetItemInfoFromNameOrId(itemId=row[0])
		
		if stockInfo[2] < tempItem['quantity']:
			return make_response(f'item_id {tempItem["item_id"]} has {stockInfo[2]} in stock, {tempItem["quantity"]} requested', 500)
		
		cartItems.append(tempItem)
	
	# if we get here, cart is validated
	totalPrice = CalculateTotalPriceOfItems(items=cartItems)
	
	if totalPrice == None:
		return make_response('error calculating shopping cart total', 500)
	
	# mark cart as purchased
	with dbLock:
		dbCursor.execute('UPDATE shopping_carts SET status = ? WHERE user_id = ? AND status = "open"', ('closed', userId))
		cartDbConn.commit()
	
	# @todo swelter: decrease bought items from stock via items service
	
	app.logger.log(level=logging.INFO, msg=f'closed cart for user_id={userId}')
	
	return jsonify({'items': cartItems, 'total_price': totalPrice})

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
	
	# get user_id from users service
	userId = GetUserIdFromEmail(email=reqData['user_email'])
	
	if userId == None:
		return make_response(f'no user found with email {reqData["user_email"]}', 500)
	
	with dbLock:
		dbCursor.execute('UPDATE shopping_carts SET status = ? WHERE user_id = ? AND status = "open"', ('closed', userId,))
		cartDbConn.commit()
		
		if dbCursor.rowcount == 0:
			app.logger.log(level=logging.WARNING, msg='unable to find cart to cancel, okay for now...')
		else:
			app.logger.log(level=logging.INFO, msg=f'canceled cart for user_id={userId}')
	
	return 'success'

if __name__ == '__main__':
	parser = argparse.ArgumentParser()
	parser.add_argument('--db-directory', dest='db_directory', required=True)
	args = parser.parse_args()
	
	dbPath = os.path.join(args.db_directory, 'shopping_carts.db')
	# check_same_thread = False means the write operations aren't thread safe, but we take care of that with global var dbLock
	cartDbConn = sqlite3.connect(database=dbPath, check_same_thread=False)
	dbCursor = cartDbConn.cursor()
	
	app.run(host='0.0.0.0', port=SHOPPING_CART_SERVICE_PORT, debug=True)