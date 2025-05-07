from create_dbs.create_dbs import CreateUserDb, CreateShoppingCartDb
import os

def main():
	CreateUserDb(dbDirectory=os.path.join('..', 'db'), removeExisting=True)
	CreateShoppingCartDb(dbDirectory=os.path.join('..', 'db'), removeExisting=True)
	
	return

if __name__ == '__main__':
	main()