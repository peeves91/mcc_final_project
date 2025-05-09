from create_dbs.create_dbs import CreateUserDb, CreateShoppingCartDb, CreateOrderDb, CreateItemDb
from create_dbs.items_to_db import ItemsCsvToDb
import os

def main():
	CreateUserDb(dbDirectory=os.path.join('..', 'db'), removeExisting=True)
	CreateShoppingCartDb(dbDirectory=os.path.join('..', 'db'), removeExisting=True)
	CreateOrderDb(dbDirectory=os.path.join('..', 'db'), removeExisting=True)
	CreateItemDb(dbDirectory=os.path.join('..', 'db'), removeExisting=True)
	ItemsCsvToDb(dbDirectory=os.path.join('..', 'db'), csvPath=os.path.join('create_dbs', 'items.csv'))
	
	return

if __name__ == '__main__':
	main()