import argparse
import datetime
import random
import sqlite3

def RandomDatetimeStamp():
	return datetime.datetime.fromtimestamp(random.randint(0, int(datetime.datetime.now().timestamp())))

def NRandomDigits(num: int):
	retStr = ''
	
	for i in range(num):
		retStr += str(random.randint(0, 9))
	
	return retStr

def main():
	parser = argparse.ArgumentParser()
	parser.add_argument('--db-directory', dest='db_directory', required=True)
	args = parser.parse_args()
	
	conn = sqlite3.connect(args.db_directory + '/users.db')
	cursor = conn.cursor()
	
	addresses = []
	with open('addresses.txt', 'r') as file:
		rawAddresses = file.readlines()
	
	for addr in rawAddresses:
		if addr.strip() != '':
			addresses.append(addr.strip())
	
	addrIndex = 0
	rowsToInsert = []
	for row in cursor.execute('SELECT id FROM users'):
		userId = row[0]
		address = addresses[addrIndex]
		phone = f'{NRandomDigits(3)}-{NRandomDigits(3)}-{NRandomDigits(4)}'
		creditCard = f'{NRandomDigits(4)}-{NRandomDigits(4)}-{NRandomDigits(4)}-{NRandomDigits(4)}'
		
		addrIndex += 1
		
		rowsToInsert.append((userId, address, phone, creditCard))
	
	cursor.executemany('INSERT INTO user_profiles(user_id, address, phone, credit_card) VALUES(?, ?, ?, ?)', rowsToInsert)
	conn.commit()
	
	return

if __name__ == '__main__':
	main()