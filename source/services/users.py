from flask import Flask, jsonify, request, Response
import argparse
import os
import sqlite3

app = Flask(__name__)
dbPath = None

@app.route('/')
def HelloWorld():
	return "hello, world"

@app.route('/get_user')
def GetUser():
	reqData = request.get_json()
	
	if 'last_name' in reqData:
		searchColumn = 'last_name'
	elif 'id' in reqData:
		searchColumn = 'id'
	else:
		return 'no valid search criteria specified', 400
	
	conn = sqlite3.connect(database=dbPath)
	cursor = conn.cursor()
	cursor.execute(f'SELECT id, email, first_name, last_name, updated_at FROM users WHERE {searchColumn} = ?', (reqData['last_name'],))
	results = cursor.fetchall()
	
	jsonResults = {'results': []}
	if results:
		for row in results:
			tempResult = {}
			tempResult['id'] = row[0]
			tempResult['email'] = row[1]
			tempResult['first_name'] = row[2]
			tempResult['last_name'] = row[3]
			tempResult['updated_at'] = row[4]
			jsonResults['results'].append(tempResult)
	
	return jsonify(jsonResults)

if __name__ == '__main__':
	parser = argparse.ArgumentParser()
	parser.add_argument('--db-directory', dest='db_directory', required=True)
	args = parser.parse_args()
	
	dbPath = os.path.join(args.db_directory, 'users.db')
	
	app.run(debug=True)