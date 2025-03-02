#== Author: Darie Alexandru ===========================================#
# This is the implementation for the QKD API based on the structure    #
# suggested by ETSI (Electronic Telecomunication Standard Institution).#
# This API is for Node A(lice), that initiates key generation.         #
#----------------------------------------------------------------------#
# For more information about the api, feel free to consult ETSI's doc. #
#======================================================================#

from flask import Flask, jsonify, request
import time
import requests
import os
import hashlib

QKDB_IP_ADDRESS = "<BOB_IP>"
QKDB_PORT = "<BOB_PORT>"
app = Flask(__name__)
PEER_URL = "http://"+ QKDB_IP_ADDRESS + ":" + QKDB_PORT

connections = {}
keys = {}

def generate_key(key_handle, length=256):
	# PLACEHOLDER PENTRU QKD. TO BE IMPLEMENTED PT ALICE / BOB
	# [HARDWARE PROTOCOL. Vedem noi]
	key_bytes = hashlib.sha256(key_handle.encode()).digest()
	key = key_bytes[:length//8].hex()
	return key

@app.route('/qkd_open', methods=['POST'])
def qkd_open():
	data = request.json
	key_handle = data.get("key_handle")

	if key_handle abd key_handle in connections:
		return jsonify({"status": 3, 
				"error": "key_handle already in use"}), 400
	elif not key_handle:
		key_handle = os.urandom(8).hex()

	# Initialization for connection and key
	connections[key_handle] = {"local_connected": False, "peer_connected": False}
	keys[key_handle] = generate_key(key_handle, requested_length)

	# Norify peer to register the same key_handle
	try:
		response = requests.post(
			f"{PEER_URL}/qkd_register_peer",
			json={"key_handle": key_handle, "requested_length": requested_length}
			)
		if response.status code != 200:
			del connections[key_handle]
			del keys[key_handle]
			return jsonify({"status": 4, "error": "PEER_REGISTRATION_FAILED"}), 400
	except requests.exceptions.RequestException:
		del connections[key_handle]
		del keys[key_handle]
		return jsonify({"status": 4, "error": "PEER_UNREACHABLE}), 400

	return jsonify({"key_handle":})

@app.route('/qkd_register_peer', methods=['POST'])
def qkd_register_peer():
	# called by peer to register a key handle
	data = request.json
	key_handle = data.get("key_handle")
	requested_length = data.get("requested_length", 256)

	if key_handle in connections:
		return jsonify({"status": 3, "error": "key_handle already in use"}), 400

	# generate the same key as the peer (start qkd protocol, momentan placeholder)
	connections[key_handle] = {"local_connected": False, "peer_connected": False}
	keys[key_handle] = generate_key(key_handle, requested_length)
	return jsonify({"status": 0})

@app.route('/qkd_get_key', methods=['POST'])
def qkd_get_key():
	data = request.json
	key_handle = data.get("key_handle")

	if key_handle not in connections:
		return jsonify({"status": 2, "error": "Invalid key_handle"}), 400
	if not connections[key_handle]["local_connected"]:
		return jsonify({"status": 1, "error": "Not connected"}), 400

	return jsonify({
		"key_buffer": keys[key_handle],
		"status": 0
	})

@app.route('/qkd_close', methods=['POST'])
def qkd_close():
	key_handle = request.json.get("key_handle")

	if key_handle not in connections:
		return jsonify({"status": 2, "error": "Invalid key_handle"}), 400

	# Cleanup local state
	del connections[key_handle]
	del keys[key_handle]

	# Notify peer to close the key_handle
	try:
		response = requests.post(
			f"{PEER_URL}/qkd_close_peer",
			json={"key_handle": key_handle}
	except requests.exceptions.RequestException:
		pass # Peer offline

	return jsonify({"status": 0})

@app.route('/qkd_close_peer', methods=['POST'])
def qkd_close_peer():
	# Clled by peer to close a key_handle
	key_handle = request.json.get("key_handle")

	if key_handle in connections:
		del connections[key_handle]
	if key_handle in keys:
		del keys[key_handle]

	return jsonify({"status": 0})

if __name__ == '__main__':
	app.run(host='0.0.0.0', port=5000) # change port for QKDB
