from flask import Flask, jsonify, request, Response
from flask_expects_json import expects_json
import argparse
import datetime
import os
import sqlite3

app = Flask(__name__)
dbPath = None

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

@app.route('/')
def HelloWorld():
	return "hello, world"

@app.route('/get_user', methods=['GET'])
def GetUser():
	reqData = request.get_json()
	
	if 'last_name' in reqData:
		searchColumn = 'last_name'
	elif 'id' in reqData:
		searchColumn = 'id'
	else:
		return 'no valid search criteria specified', 400
	
	usersConn = sqlite3.connect(database=dbPath)
	usersCursor = usersConn.cursor()
	usersCursor.execute(f'SELECT id, email, first_name, last_name, updated_at FROM users WHERE {searchColumn} = ?', (reqData['last_name'],))
	usersResults = usersCursor.fetchall()
	
	profilesConn = sqlite3.connect(database=dbPath)
	profilesCursor = profilesConn.cursor()
	
	jsonResults = {'results': []}
	if usersResults:
		for row in usersResults:
			tempResult = {}
			
			# get basic user information from users table
			tempResult['id'] = row[0]
			tempResult['email'] = row[1]
			tempResult['first_name'] = row[2]
			tempResult['last_name'] = row[3]
			tempResult['updated_at'] = row[4]
			
			# get further information from user_profiles table
			profilesCursor.execute('SELECT address, phone FROM user_profiles WHERE user_id = ?', (tempResult['id'],))
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

if __name__ == '__main__':
	parser = argparse.ArgumentParser()
	parser.add_argument('--db-directory', dest='db_directory', required=True)
	args = parser.parse_args()
	
	dbPath = os.path.join(args.db_directory, 'users.db')
	
	app.run(debug=True)