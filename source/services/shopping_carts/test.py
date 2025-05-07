from flask import Flask, jsonify, request, make_response
from flask_expects_json import expects_json
from typing import List, Dict
import argparse
import json
import logging
import os
import requests
import sqlite3
import threading

app = Flask(__name__)
app.logger.setLevel(logging.INFO)

@app.route('/')
def HelloWorld():
	return 'success'

if __name__ == '__main__':
	app.run(host='0.0.0.0', port=6000)#, debug=True)