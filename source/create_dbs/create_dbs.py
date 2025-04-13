import argparse
import os
import sqlite3

def CreateOrderDb(dbDirectory, removeExisting):
	dbPath = os.path.join(dbDirectory, 'orders.db')
	
	if os.path.exists(dbPath) == True:
		os.remove(dbPath)
	
	conn = sqlite3.connect(os.path.join(dbDirectory, 'orders.db'))
	cursor = conn.cursor()
	
	# create table
	cursor.execute('CREATE TABLE orders(' \
		'id INTEGER PRIMARY KEY AUTOINCREMENT,' \
		'user_id INTEGER,' \
		'status TEXT,' \
		'total_price DECIMAL,' \
		'created_at TIMESTAMP,' \
		'updated_at TIMESTAMP)')
	
	cursor.execute('CREATE TABLE order_items(' \
		'id INTEGER PRIMARY KEY AUTOINCREMENT,' \
		'order_id INTEGER,' \
		'item_id INTEGER,' \
		'quantity INTEGER,' \
		'price DECIMAL)')

def main():
	parser = argparse.ArgumentParser()
	parser.add_argument('--db-directory', dest='db_directory', required=True)
	parser.add_argument('-r', action='store_true', dest='remove_existing', required=False)
	args = parser.parse_args()
	
	# print(args.db_directory)
	# print(args.remove_existing)
	CreateOrderDb(dbDirectory=args.db_directory, removeExisting=args.remove_existing)
	
	return

if __name__ == '__main__':
	main()