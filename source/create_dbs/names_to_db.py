import argparse
import datetime
import random
import sqlite3

def RandomDatetimeStamp():
	return datetime.datetime.fromtimestamp(random.randint(0, int(datetime.datetime.now().timestamp())))

def main():
	parser = argparse.ArgumentParser()
	parser.add_argument('--db-directory', dest='db_directory', required=True)
	args = parser.parse_args()
	
	with open('names.txt', 'r') as file:
		names = file.readlines()
	
	conn = sqlite3.connect(args.db_directory + '/users.db')
	cursor = conn.cursor()
	
	emailProviders = ['gmail.com', 'yahoo.com', 'hotmail.com', 'aol.com', 'outlook.com']
	
	rowsToInsert = []
	for name in names:
		name = name.strip()
		
		tempEmail = name.replace(' ', '').lower() + '@' + random.choice(emailProviders)
		tempFirstName = name.split(' ')[0].lower()
		tempLastName = name.split(' ')[1].lower()
		tempCreatedAt = str(RandomDatetimeStamp())
		
		rowsToInsert.append((tempEmail, tempFirstName, tempLastName, tempCreatedAt, tempCreatedAt))
	
	cursor.executemany('INSERT INTO users(email, first_name, last_name, created_at, updated_at) VALUES(?, ?, ?, ?, ?)', rowsToInsert)
	conn.commit()
	
	return

if __name__ == '__main__':
	main()