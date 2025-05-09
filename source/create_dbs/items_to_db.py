import argparse
import csv
import os
import random
import sqlite3

def ItemsCsvToDb(dbDirectory, csvPath):
	conn = sqlite3.connect(os.path.join(dbDirectory, 'items.db'))
	cursor = conn.cursor()
	
	with open(csvPath, 'r', encoding='utf8') as file:
		isFirst = True
		reader = csv.reader(file, delimiter=',', quotechar='"')
		rowsToInsert = []
		counter = 0
		for row in reader:
			if isFirst == True:
				isFirst = False
				continue
			
			# some prices are empty, just skip it
			if row[6] == '':
				continue
			
			rowsToInsert.append((row[3], row[10], int(row[6]) / 100, counter + 100))
			counter += 1
	
	cursor.executemany('INSERT INTO items(product_name, description, price, quantity_in_stock) VALUES(?, ?, ?, ?)', rowsToInsert)
	conn.commit()
	
	return

if __name__ == '__main__':
	ItemsCsvToDb()