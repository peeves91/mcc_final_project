import argparse
import os
import sqlite3

def CreateOrderDb(dbDirectory, removeExisting):
	dbPath = os.path.join(dbDirectory, 'orders.db')
	
	if os.path.exists(dbPath) == True:
		os.remove(dbPath)
	
	conn = sqlite3.connect(dbPath)
	cursor = conn.cursor()
	
	# create table
	cursor.execute('CREATE TABLE orders(' \
		'id INTEGER PRIMARY KEY AUTOINCREMENT,' \
		'user_id INTEGER,' \
		'status TEXT,' \
		'total_price DECIMAL)')#,' \
		# 'total_price DECIMAL,' \
		# 'created_at TIMESTAMP,' \
		# 'updated_at TIMESTAMP)')
	
	cursor.execute('CREATE TABLE order_items(' \
		# 'id INTEGER PRIMARY KEY AUTOINCREMENT,' \
		'order_id INTEGER,' \
		'item_id INTEGER,' \
		'quantity INTEGER,'
		'price DECIMAL)')#,' \
		# 'price DECIMAL)')

def CreateUserDb(dbDirectory, removeExisting):
	dbPath = os.path.join(dbDirectory, 'users.db')
	
	if os.path.exists(dbPath) == True:
		os.remove(dbPath)
	
	conn = sqlite3.connect(dbPath)
	cursor = conn.cursor()
	
	cursor.execute('CREATE TABLE users(' \
		'id INTEGER PRIMARY KEY AUTOINCREMENT,' \
		'email TEXT,' \
		'first_name TEXT,' \
		'last_name TEXT,' \
		'created_at TIMESTAMP,' \
		'updated_at TIMESTAMP)')
	
	cursor.execute('CREATE TABLE user_profiles(' \
		'user_id INTEGER,' \
		'address TEXT,' \
		'phone TEXT,' \
		'credit_card TEXT)')

def CreateItemDb(dbDirectory, removeExisting):
	dbPath = os.path.join(dbDirectory, 'items.db')
	
	if os.path.exists(dbPath) == True:
		os.remove(dbPath)
	
	conn = sqlite3.connect(dbPath)
	cursor = conn.cursor()
	
	cursor.execute('CREATE TABLE items(' \
		'id INTEGER PRIMARY KEY AUTOINCREMENT,' \
		'product_name TEXT,' \
		'description TEXT,' \
		'price DECIMAL,' \
		'quantity_in_stock INTEGER)')

def CreateShoppingCartDb(dbDirectory, removeExisting):
	dbPath = os.path.join(dbDirectory, 'shopping_carts.db')
	
	if os.path.exists(dbPath) == True:
		os.remove(dbPath)
	
	conn = sqlite3.connect(dbPath)
	cursor = conn.cursor()
	
	cursor.execute('CREATE TABLE shopping_carts(' \
		'id INTEGER PRIMARY KEY AUTOINCREMENT,' \
		'user_id INTEGER,' \
		'status TEXT)')
	
	cursor.execute('CREATE TABLE shopping_cart_items(' \
		'cart_id INTEGER,' \
		'item_id INTEGER,' \
		'quantity INTEGER,' \
		'price DECIMAL)')

def main():
	parser = argparse.ArgumentParser()
	parser.add_argument('--db-directory', dest='db_directory', required=True)
	parser.add_argument('-r', action='store_true', dest='remove_existing', required=False)
	args = parser.parse_args()
	
	# CreateOrderDb(dbDirectory=args.db_directory, removeExisting=args.remove_existing)
	# CreateUserDb(dbDirectory=args.db_directory, removeExisting=args.remove_existing)
	# CreateItemDb(dbDirectory=args.db_directory, removeExisting=args.remove_existing)
	CreateShoppingCartDb(dbDirectory=args.db_directory, removeExisting=args.remove_existing)
	
	return

if __name__ == '__main__':
	main()