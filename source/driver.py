import json
import logging
import requests

# constants
JSON_HEADER_DATATYPE		= {'Content-type': 'application/json'}
ORDER_SERVICE_PROT			= 5000
SHOPPING_CART_SERVICE_PORT	= 6000
USERS_SERVICE_PORT			= 7000
ITEMS_SERVICE_PORT			= 8000

TEST_ITEM_NAMES				= ['Zed Loafers', 'AW Bellies', 'Ladela Bellies', "Oye Boy's Dungaree"]

def main():
	# setup logging
	logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
	
	logger = logging.getLogger()
	
	# create user 1
	url = f'http://127.0.0.1:{USERS_SERVICE_PORT}/create_user'
	firstUserInfo = {
		'email': 'user1@yahoo.com',
		'first_name': 'First1',
		'last_name': 'Last1',
		'phone': '111-222-3333',
		'address': '123 Test Rd, Milwaukee WI',
		'credit_card': '4444-5555-6666-7777'
	}
	resp = requests.post(url=url, data=json.dumps(firstUserInfo), headers=JSON_HEADER_DATATYPE)
	
	assert resp.status_code == 200
	logger.info("Successfully created user 1 w/ email {firstUserInfo['email']} (and other data)")
	
	# create user 2
	url = f'http://127.0.0.1:{USERS_SERVICE_PORT}/create_user'
	secondUserInfo = {
		'email': 'user2@gmail.com',
		'first_name': 'First2',
		'last_name': 'Last2',
		'phone': '111-222-3333',
		'address': '456 Test Rd, Milwaukee WI',
		'credit_card': '7777-6666-5555-4444'
	}
	resp = requests.post(url=url, data=json.dumps(secondUserInfo), headers=JSON_HEADER_DATATYPE)
	
	assert resp.status_code == 200
	logger.info("Successfully created user 1 w/ email {secondUserInfo['email']} (and other data)")
	
	# add 2 items to the first user's cart
	url = f'http://127.0.0.1:{ORDER_SERVICE_PROT}/queue_item'
	postData = {
		'user_email': firstUserInfo['email'],
		'item_name': TEST_ITEM_NAMES[0],
		'quantity': 2,
	}
	resp = requests.post(url=url, data=json.dumps(postData), headers=JSON_HEADER_DATATYPE)
	assert resp.status_code == 200
	
	postData['item_name'] = TEST_ITEM_NAMES[1]
	postData['quantity'] = 1
	resp = requests.post(url=url, data=json.dumps(postData), headers=JSON_HEADER_DATATYPE)
	assert resp.status_code == 200
	
	logger.info("Successfully added 2 different items to first user\'s cart")
	
	# verify the items in user 1's cart match
	url = f'http://127.0.0.1:{ORDER_SERVICE_PROT}/get_queued_items'
	resp = requests.get(url=url, data=json.dumps({'user_email': firstUserInfo['email']}), headers=JSON_HEADER_DATATYPE)
	assert resp.status_code == 200
	respJson = resp.json()
	
	assert respJson['items'][0]['item_name'] == TEST_ITEM_NAMES[0]
	assert respJson['items'][1]['item_name'] == TEST_ITEM_NAMES[1]
	assert respJson['items'][0]['quantity'] == 2
	assert respJson['items'][1]['quantity'] == 1
	
	logger.info("Successfully validated 2 items in first user's cart")
	
	# clear first user's cart and ensure service returns no items in it now
	url = f'http://127.0.0.1:{ORDER_SERVICE_PROT}/clear_queue'
	resp = requests.post(url=url, data=json.dumps({'user_email': firstUserInfo['email']}), headers=JSON_HEADER_DATATYPE)
	assert resp.status_code == 200
	
	url = f'http://127.0.0.1:{ORDER_SERVICE_PROT}/get_queued_items'
	resp = requests.get(url=url, data=json.dumps({'user_email': firstUserInfo['email']}), headers=JSON_HEADER_DATATYPE)
	assert resp.status_code == 200
	
	respJson = resp.json()
	assert len(respJson['items']) == 0
	
	logger.info("Successfully cleared first user's cart and verified service returns no items in it")
	
	# add 1 items to the first user's cart
	url = f'http://127.0.0.1:{ORDER_SERVICE_PROT}/queue_item'
	postData = {
		'user_email': firstUserInfo['email'],
		'item_name': TEST_ITEM_NAMES[2],
		'quantity': 3,
	}
	resp = requests.post(url=url, data=json.dumps(postData), headers=JSON_HEADER_DATATYPE)
	assert resp.status_code == 200
	
	logger.info("Successfully added 1 item to first user\'s cart")
	
	# verify the items in user 1's cart match
	url = f'http://127.0.0.1:{ORDER_SERVICE_PROT}/get_queued_items'
	resp = requests.get(url=url, data=json.dumps({'user_email': firstUserInfo['email']}), headers=JSON_HEADER_DATATYPE)
	assert resp.status_code == 200
	respJson = resp.json()
	
	assert respJson['items'][0]['item_name'] == TEST_ITEM_NAMES[2]
	assert respJson['items'][0]['quantity'] == 3
	
	logger.info("Successfully validated 2 items in first user's cart")
	
	# add 2 items to the second user's cart
	url = f'http://127.0.0.1:{ORDER_SERVICE_PROT}/queue_item'
	postData = {
		'user_email': secondUserInfo['email'],
		'item_name': TEST_ITEM_NAMES[0],
		'quantity': 4,
	}
	resp = requests.post(url=url, data=json.dumps(postData), headers=JSON_HEADER_DATATYPE)
	assert resp.status_code == 200
	
	postData['item_name'] = TEST_ITEM_NAMES[2]
	postData['quantity'] = 5
	resp = requests.post(url=url, data=json.dumps(postData), headers=JSON_HEADER_DATATYPE)
	assert resp.status_code == 200
	
	logger.info("Successfully added 2 different items to first user\'s cart")
	
	# verify the items in user 2's cart match
	url = f'http://127.0.0.1:{ORDER_SERVICE_PROT}/get_queued_items'
	resp = requests.get(url=url, data=json.dumps({'user_email': secondUserInfo['email']}), headers=JSON_HEADER_DATATYPE)
	assert resp.status_code == 200
	respJson = resp.json()
	
	assert respJson['items'][0]['item_name'] == TEST_ITEM_NAMES[0]
	assert respJson['items'][1]['item_name'] == TEST_ITEM_NAMES[2]
	assert respJson['items'][0]['quantity'] == 4
	assert respJson['items'][1]['quantity'] == 5
	
	logger.info("Successfully validated 2 items in second user's cart")
	
	# purchase first user's cart
	url = f'http://127.0.0.1:{ORDER_SERVICE_PROT}/purchase_queue'
	resp = requests.post(url=url, data=json.dumps({'user_email': firstUserInfo['email']}), headers=JSON_HEADER_DATATYPE)
	assert resp.status_code == 200
	purchasedItems = resp.json()
	assert len(purchasedItems['items']) == 1
	assert purchasedItems['items'][0]['item_name'] == TEST_ITEM_NAMES[2]
	assert purchasedItems['items'][0]['quantity'] == 3
	
	logger.info("Successfully purchased first user's cart and the item was what we expected")
	
	# purchase second user's cart
	url = f'http://127.0.0.1:{ORDER_SERVICE_PROT}/purchase_queue'
	resp = requests.post(url=url, data=json.dumps({'user_email': secondUserInfo['email']}), headers=JSON_HEADER_DATATYPE)
	assert resp.status_code == 200
	purchasedItems = resp.json()
	assert len(purchasedItems['items']) == 2
	assert purchasedItems['items'][0]['item_name'] == TEST_ITEM_NAMES[0]
	assert purchasedItems['items'][1]['item_name'] == TEST_ITEM_NAMES[2]
	assert purchasedItems['items'][0]['quantity'] == 4
	assert purchasedItems['items'][1]['quantity'] == 5
	
	logger.info("Successfully purchased second user's cart and the items were what we expected")
	
	# verify first and second user's carts are empty
	url = f'http://127.0.0.1:{ORDER_SERVICE_PROT}/get_queued_items'
	resp = requests.get(url=url, data=json.dumps({'user_email': firstUserInfo['email']}), headers=JSON_HEADER_DATATYPE)
	assert resp.status_code == 200
	respJson = resp.json()
	assert len(respJson['items']) == 0
	
	logger.info("Successfully validated first user's cart is empty")
	
	url = f'http://127.0.0.1:{ORDER_SERVICE_PROT}/get_queued_items'
	resp = requests.get(url=url, data=json.dumps({'user_email': secondUserInfo['email']}), headers=JSON_HEADER_DATATYPE)
	assert resp.status_code == 200
	respJson = resp.json()
	assert len(respJson['items']) == 0
	
	logger.info("Successfully validated second user's cart is empty")
	
	return

if __name__ == '__main__':
	main()