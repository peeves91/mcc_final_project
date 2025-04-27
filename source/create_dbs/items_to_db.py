import argparse
import csv
import random
import sqlite3

def main():
	parser = argparse.ArgumentParser()
	parser.add_argument('--db-directory', dest='db_directory', required=True)
	args = parser.parse_args()
	
	conn = sqlite3.connect(args.db_directory + '/items.db')
	cursor = conn.cursor()
	
	with open('items.csv', 'r', encoding='utf8') as file:
		isFirst = True
		reader = csv.reader(file, delimiter=',', quotechar='"')
		rowsToInsert = []
		for row in reader:
			if isFirst == True:
				isFirst = False
				continue
			
			# some prices are empty, just skip it
			if row[6] == '':
				continue
			
			rowsToInsert.append((row[3], row[10], int(row[6]) / 100, random.randint(100, 1000)))
	
	cursor.executemany('INSERT INTO items(product_name, description, price, quantity_in_stock) VALUES(?, ?, ?, ?)', rowsToInsert)
	conn.commit()
	
	return

if __name__ == '__main__':
	main()