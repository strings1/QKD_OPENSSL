#== Author: Darie Alexandru ===========================================#
# This is the implementation for the QKD API based on the structure    #
# suggested by ETSI (Electronic Telecomunication Standard Institution).#
# This API is for any nodes, the implementation allows scalability.    #
# Includes BB84 logic with basis exchange and sifting.                 #
#----------------------------------------------------------------------#
# For more information about the api, feel free to consult ETSI's doc. #
#======================================================================#

from flask import Flask, jsonify, request
import time
import requests
import os
import hashlib
import threading
import argparse # For command-line arguments

# --- QKD Node Imports ---
try:
    from node_type_interface import QKD_Node # Base class is good practice
    from node_type_hardware import QKD_Node_Hardware
    from node_type_gui import QKD_Node_GUI
except ImportError as e:
    print(f"Error importing node types: {e}. Make sure node_type_*.py files are present.")
    exit(1)
# --- End QKD Node Imports ---

# --- Default Configuration (can be overridden by command-line args) ---
DEFAULT_MY_ADDRESS = "0.0.0.0"
DEFAULT_MY_PORT = 5000
DEFAULT_PEER_ADDRESS = "127.0.0.1" # MUST BE SET VIA CMD LINE ARGS
DEFAULT_PEER_PORT = 5001           # MUST BE SET VIA CMD LINE ARGS
DEFAULT_NODE_TYPE = "gui"          # "hardware" or "gui"
DEFAULT_TIME_BETWEEN = 0.5         # Time per bit transmission (seconds)
DEFAULT_KEY_LENGTH_BITS = 256      # Desired final sifted key length (bits)
DEFAULT_RAW_KEY_MULTIPLIER = 4     # Generate more raw bits than needed for sifting (e.g., 4x)
# --- End Configuration ---

app = Flask(__name__)

# --- Global State ---
config = {} # Will hold runtime configuration
connections = {} # Stores state for each key_handle
# Example connection entry:
# {
#   "key_handle_123": {
#     "role": "alice" / "bob", # Determined by who calls qkd_open
#     "local_connected": False,
#     "peer_connected": False,
#     "status": "idle", # idle, calibrating, generating, transmitting, receiving, exchanging_bases, sifting, ready, error
#     "local_bases": None,  # Bases used/chosen by this node (string)
#     "peer_bases": None,   # Bases received from the peer (string)
#     "raw_key_hex_alice": None, # Raw key data (Alice only initially)
#     "received_colors_bob": None, # List of colors detected by Bob
#     "sifted_key": None,   # The final key after basis comparison (hex string)
#     "error_message": None
#   }
# }
qkd_node = None # Global instance of the QKD node
# --- End Global State ---

# --- QKD Protocol Logic ---

def perform_write_alice(key_handle, requested_length_bits):
    """Alice generates data, calibrates, writes, and sends bases."""
    global connections, qkd_node, config

    if not qkd_node:
        connections[key_handle]["status"] = "error"
        connections[key_handle]["error_message"] = "QKD Node not initialized"
        print(f"[{key_handle}] Error: QKD Node not initialized.")
        return

    print(f"[{key_handle}] Starting QKD protocol (Alice)...")

    try:
        # 1. Calibration (Optional but recommended for hardware)
        if isinstance(qkd_node, QKD_Node_Hardware): # Check specific type if needed
            connections[key_handle]["status"] = "calibrating"
            print(f"[{key_handle}] Calibrating node...")
            qkd_node.calibrate(n=3) # Perform a short calibration

        # 2. Generate Raw Key Data
        connections[key_handle]["status"] = "generating"
        # Generate more bits than needed to account for sifting losses
        raw_bits_needed = requested_length_bits * config['raw_key_multiplier']
        raw_key_bytes_needed = (raw_bits_needed + 7) // 8
        raw_key_hex = os.urandom(raw_key_bytes_needed).hex()
        connections[key_handle]["raw_key_hex_alice"] = raw_key_hex
        actual_raw_bits = len(raw_key_hex) * 4
        print(f"[{key_handle}] Generated {actual_raw_bits} raw bits.")

        # 3. Transmit Data using QKD Node
        connections[key_handle]["status"] = "transmitting"
        print(f"[{key_handle}] Writing data to quantum channel...")
        # write() should return the bases used for transmission
        alice_bases_list = qkd_node.write(raw_key_hex)
        if len(alice_bases_list) != actual_raw_bits:
             raise ValueError(f"Length mismatch: write() returned {len(alice_bases_list)} bases, expected {actual_raw_bits}")
        connections[key_handle]["local_bases"] = "".join(alice_bases_list) # Store as a string
        print(f"[{key_handle}] Transmission complete.")

        # 4. Send Bases to Bob (after transmission is fully done)
        connections[key_handle]["status"] = "exchanging_bases"
        print(f"[{key_handle}] Sending bases to Bob...")
        try:
            response = requests.post(
                f"{config['peer_url']}/qkd_exchange_bases",
                json={"key_handle": key_handle, "bases": connections[key_handle]["local_bases"]},
                timeout=10 # Allow time for peer to respond
            )
            response.raise_for_status()
            print(f"[{key_handle}] Bases sent successfully.")
        except requests.exceptions.RequestException as e:
            # Don't raise here, just log and set error state, sifting won't happen
            connections[key_handle]["status"] = "error"
            connections[key_handle]["error_message"] = f"Failed to send bases to peer: {e}"
            print(f"[{key_handle}] Error: {connections[key_handle]['error_message']}")
            return # Stop processing for Alice

        # 5. Wait for Bob's Bases (will arrive via /qkd_exchange_bases)
        print(f"[{key_handle}] Waiting for Bob's bases...")
        # Sifting will be triggered by the /qkd_exchange_bases endpoint when Bob's bases arrive

    except Exception as e:
        connections[key_handle]["status"] = "error"
        connections[key_handle]["error_message"] = str(e)
        print(f"[{key_handle}] Error during Alice QKD protocol: {e}")
        # Consider notifying Bob about the error if possible

def perform_read_bob(key_handle, requested_length_bits):
    """Bob reads data, generates bases, and sends bases."""
    global connections, qkd_node, config

    if not qkd_node:
        connections[key_handle]["status"] = "error"
        connections[key_handle]["error_message"] = "QKD Node not initialized"
        print(f"[{key_handle}] Error: QKD Node not initialized.")
        return

    print(f"[{key_handle}] Starting QKD protocol (Bob)...")

    try:
        # 1. Determine Expected Number of Bits
        raw_bits_expected = requested_length_bits * config['raw_key_multiplier']

        # 2. Generate Bob's Bases RANDOMLY *before* reading
        connections[key_handle]["status"] = "generating" # Bob generates bases
        bob_bases_list = [qkd_node.basis[os.urandom(1)[0] % 2] for _ in range(raw_bits_expected)]
        connections[key_handle]["local_bases"] = "".join(bob_bases_list)
        print(f"[{key_handle}] Generated {raw_bits_expected} measurement bases.")

        # 3. Receive Data using QKD Node
        connections[key_handle]["status"] = "receiving"
        print(f"[{key_handle}] Reading {raw_bits_expected} bits from quantum channel...")
        try:
			# --- Call the implemented read method ---
            received_colors = qkd_node.read(num_bits=raw_bits_expected) # Pass expected length

            if received_colors is None:
                # read() returned None, indicating an error or timeout during read
                raise RuntimeError("QKD Node read operation failed or timed out.")

            # Optional: Check if the number of received colors matches expected
            # Note: read() might return fewer if end signal was early. Sifting needs to handle length mismatches.
            if len(received_colors) != raw_bits_expected:
                print(f"[{key_handle}] Warning: Expected {raw_bits_expected} colors, but received {len(received_colors)}. Proceeding with received data.")
                # Adjust Bob's local bases to match the length of received colors before sifting
                # This is crucial if sifting assumes equal lengths.
                connections[key_handle]["local_bases"] = connections[key_handle]["local_bases"][:len(received_colors)]
                print(f"[{key_handle}] Adjusted local bases length to {len(connections[key_handle]['local_bases'])}.")


            connections[key_handle]["received_colors_bob"] = received_colors
            print(f"[{key_handle}] Reception complete. Received {len(received_colors)} colors.")
            # --- End actual read call ---

        except AttributeError:
             raise NotImplementedError("The 'read' method in the QKD node class needs to accept 'num_bits' argument and return a list of colors.")
        except Exception as read_err:
             raise RuntimeError(f"Error during qkd_node.read(): {read_err}")


        # 4. Send Bases to Alice (after reception is fully done)
        connections[key_handle]["status"] = "exchanging_bases"
        print(f"[{key_handle}] Sending bases to Alice...")
        try:
            response = requests.post(
                f"{config['peer_url']}/qkd_exchange_bases",
                json={"key_handle": key_handle, "bases": connections[key_handle]["local_bases"]},
                timeout=10
            )
            response.raise_for_status()
            print(f"[{key_handle}] Bases sent successfully.")
        except requests.exceptions.RequestException as e:
            # Don't raise here, just log and set error state, sifting won't happen
            connections[key_handle]["status"] = "error"
            connections[key_handle]["error_message"] = f"Failed to send bases to peer: {e}"
            print(f"[{key_handle}] Error: {connections[key_handle]['error_message']}")
            return # Stop processing for Bob

        # 5. Wait for Alice's Bases (will arrive via /qkd_exchange_bases)
        print(f"[{key_handle}] Waiting for Alice's bases...")
        # Sifting will be triggered by the /qkd_exchange_bases endpoint when Alice's bases arrive

    except Exception as e:
        connections[key_handle]["status"] = "error"
        connections[key_handle]["error_message"] = str(e)
        print(f"[{key_handle}] Error during Bob QKD protocol: {e}")
        # Consider notifying Alice about the error if possible


def sift_key(key_handle):
    """Compares bases and generates the sifted key. Called by /qkd_exchange_bases."""
    global connections
    print(f"[{key_handle}] Performing key sifting...")
    connections[key_handle]["status"] = "sifting"

    conn_data = connections[key_handle]
    local_bases = conn_data.get("local_bases")
    peer_bases = conn_data.get("peer_bases")
    role = conn_data.get("role")

    if not all([local_bases, peer_bases, role]):
        conn_data["status"] = "error"
        conn_data["error_message"] = "Missing data for sifting (bases or role)."
        print(f"[{key_handle}] Error: Missing data for sifting.")
        return

    sifted_key_bin = ""
    match_count = 0
    mismatch_count = 0 # Count basis mismatches

    # Ensure bases have the same length before proceeding
    if len(local_bases) != len(peer_bases):
        conn_data["status"] = "error"
        conn_data["error_message"] = f"Basis length mismatch: Local={len(local_bases)}, Peer={len(peer_bases)}"
        print(f"[{key_handle}] Error: {conn_data['error_message']}")
        return

    # Alice uses her raw key bits
    if role == "alice":
        raw_key_hex = conn_data.get("raw_key_hex_alice")
        if not raw_key_hex:
            conn_data["status"] = "error"; conn_data["error_message"] = "Alice missing raw key for sifting."
            print(f"[{key_handle}] Error: {conn_data['error_message']}")
            return
        try:
            # Ensure binary string has correct length, padding with leading zeros if needed
            expected_len = len(local_bases)
            raw_key_bin = bin(int(raw_key_hex, 16))[2:].zfill(len(raw_key_hex) * 4)
            if len(raw_key_bin) != expected_len:
                 # This might happen if raw_key_hex had leading zeros stripped implicitly
                 # Or if multiplier calculation was off. Pad or error.
                 # Let's pad assuming the hex was correct but bin() removed leading zeros
                 raw_key_bin = raw_key_bin.zfill(expected_len)
                 if len(raw_key_bin) != expected_len: # Still wrong? Error.
                     raise ValueError(f"Raw key binary length ({len(raw_key_bin)}) doesn't match basis length ({expected_len}) after padding.")

        except ValueError as e:
             conn_data["status"] = "error"; conn_data["error_message"] = f"Invalid raw key hex or length mismatch: {e}"
             print(f"[{key_handle}] Error: {conn_data['error_message']}")
             return

        # Compare bases bit by bit
        for i in range(len(local_bases)):
            if local_bases[i] == peer_bases[i]:
                sifted_key_bin += raw_key_bin[i]
                match_count += 1
            else:
                mismatch_count += 1

    # Bob uses his interpreted received colors
    elif role == "bob":
        received_colors = conn_data.get("received_colors_bob")
        if not received_colors:
            conn_data["status"] = "error"; conn_data["error_message"] = "Bob missing received colors for sifting."
            print(f"[{key_handle}] Error: {conn_data['error_message']}")
            return

        if len(received_colors) != len(local_bases):
             conn_data["status"] = "error"; conn_data["error_message"] = f"Length mismatch: Bob received {len(received_colors)} colors, expected {len(local_bases)}"
             print(f"[{key_handle}] Error: {conn_data['error_message']}")
             return

        # Define the inverse mapping: (Basis, Color) -> Bit
        # This MUST match the encoding scheme in QKD_Node.colors
        color_to_bit = {
            '+': {'Blue': '0', 'Green': '1'}, # Basis +
            'X': {'Blue': '0', 'Red': '1'}    # Basis X
            # Add handling for 'Off' or unexpected colors if read() can return them
        }

        # Compare bases bit by bit
        for i in range(len(local_bases)):
            if local_bases[i] == peer_bases[i]:
                basis = local_bases[i]
                color = received_colors[i]
                try:
                    # Look up the bit based on the matching basis and received color
                    bit = color_to_bit[basis].get(color)
                    if bit is not None:
                        sifted_key_bin += bit
                        match_count += 1
                    else:
                        # Basis matched, but color was unexpected for that basis (e.g., Red in + basis)
                        # This indicates a transmission error or detection error. Discard the bit.
                        print(f"[{key_handle}] Sift Warning: Discarding bit {i}. Unexpected color '{color}' for basis '{basis}'.")
                        mismatch_count += 1 # Count as effective mismatch for stats
                except KeyError:
                    # Should not happen if basis is always '+' or 'X'
                     print(f"[{key_handle}] Sift Error: Invalid basis '{basis}' at index {i}.")
                     mismatch_count += 1
            else:
                # Bases don't match, discard the bit
                mismatch_count += 1

    else:
        conn_data["status"] = "error"; conn_data["error_message"] = "Unknown role for sifting."
        print(f"[{key_handle}] Error: Unknown role '{role}' for sifting.")
        return

    # Convert final binary sifted key to hex
    if not sifted_key_bin:
        sifted_key_hex = ""
    else:
        try:
            sifted_key_int = int(sifted_key_bin, 2)
            # Calculate required hex length (pad with leading zero if needed)
            hex_len = (len(sifted_key_bin) + 3) // 4
            sifted_key_hex = format(sifted_key_int, f'0{hex_len}x')
        except ValueError:
            conn_data["status"] = "error"; conn_data["error_message"] = "Failed to convert sifted binary key to hex."
            print(f"[{key_handle}] Error: {conn_data['error_message']}")
            return


    conn_data["sifted_key"] = sifted_key_hex
    conn_data["status"] = "ready" # Key is ready!
    qber = (mismatch_count / len(local_bases)) * 100 if len(local_bases) > 0 else 0
    print(f"[{key_handle}] Sifting complete.")
    print(f"  Basis Matches: {match_count}/{len(local_bases)}")
    print(f"  Basis Mismatches (Discarded): {mismatch_count}/{len(local_bases)}")
    print(f"  Estimated QBER: {qber:.2f}%")
    print(f"  Final Sifted Key Length: {len(sifted_key_bin)} bits")
    print(f"  Sifted Key (hex, first 16): {sifted_key_hex[:16]}...")
ƒ
    # TODO: Add error correction and privacy amplification here if needed based on QBER

# --- End QKD Protocol Logic ---


# --- API Endpoints ---

@app.route('/qkd_open', methods=['POST'])
def qkd_open():
    # Initiator (Alice) calls this
    global connections, config
    data = request.json
    key_handle = data.get("key_handle")
    # Use configured default key length
    requested_length = config.get('key_length_bits', DEFAULT_KEY_LENGTH_BITS)

    if key_handle and key_handle in connections:
        return jsonify({"status": 3, "error": "key_handle already in use"}), 400
    elif not key_handle:
        key_handle = os.urandom(8).hex()

    # Initialization for connection - This node is Alice
    connections[key_handle] = {
        "role": "alice", "local_connected": False, "peer_connected": False,
        "status": "idle", "local_bases": None, "peer_bases": None,
        "raw_key_hex_alice": None, "received_colors_bob": None,
        "sifted_key": None, "error_message": None
    }
    print(f"[API /qkd_open] Initiating as Alice for key_handle {key_handle}")

    # Notify peer (Bob) to register the same key_handle
    try:
        print(f"[API /qkd_open] Notifying peer {config['peer_url']}...")
        response = requests.post(
            f"{config['peer_url']}/qkd_register_peer",
            json={"key_handle": key_handle, "requested_length": requested_length},
            timeout=5
        )
        response.raise_for_status()
        print(f"[API /qkd_open] Peer registration successful.")

    except requests.exceptions.RequestException as e:
        # Clean up if peer registration fails
        if key_handle in connections: del connections[key_handle]
        print(f"[API /qkd_open] Peer unreachable or registration failed: {e}")
        return jsonify({"status": 4, "error": f"PEER_REGISTRATION_FAILED: {e}"}), 500

    # Return immediately, QKD process starts after connection
    return jsonify({"key_handle": key_handle, "status": 0})

@app.route('/qkd_register_peer', methods=['POST'])
def qkd_register_peer():
    # Called by Alice on Bob
    global connections, config
    data = request.json
    key_handle = data.get("key_handle")
    # Use length requested by Alice, or default
    requested_length = data.get("requested_length", config.get('key_length_bits', DEFAULT_KEY_LENGTH_BITS))

    if not key_handle:
        return jsonify({"status": 1, "error": "Missing key_handle"}), 400

    if key_handle in connections:
        return jsonify({"status": 3, "error": "key_handle already in use"}), 400

    # Initialize connection state - This node is Bob
    connections[key_handle] = {
        "role": "bob", "local_connected": False, "peer_connected": False,
        "status": "idle", "local_bases": None, "peer_bases": None,
        "raw_key_hex_alice": None, "received_colors_bob": None,
        "sifted_key": None, "error_message": None
    }
    # Store requested length for Bob's use
    connections[key_handle]["requested_length"] = requested_length
    print(f"[API /qkd_register_peer] Registered as Bob for key_handle {key_handle}")
    return jsonify({"status": 0})


@app.route('/qkd_connect_blocking', methods=['POST'])
def qkd_connect_blocking():
    # Establishes connection and *then* starts the appropriate QKD process
    global connections, config
    data = request.json
    key_handle = data.get("key_handle")
    timeout = data.get("timeout", 15000) # Timeout for the connection handshake

    if key_handle not in connections:
        return jsonify({"status": 2, "error": "Invalid key_handle"}), 400

    conn_data = connections[key_handle]
    if conn_data["status"] not in ["idle", "error", "ready"]: # Allow reconnect after success/error
         return jsonify({"status": 5, "error": f"Connection busy or already active: {conn_data['status']}"}), 400

    # Reset state for potential reconnection
    conn_data["status"] = "idle"
    conn_data["error_message"] = None
    conn_data["local_connected"] = True # Mark THIS node as wanting to connect
    conn_data["peer_connected"] = False # Reset peer connection status
    conn_data["local_bases"] = None   # Reset QKD state
    conn_data["peer_bases"] = None
    conn_data["raw_key_hex_alice"] = None
    conn_data["received_colors_bob"] = None
    conn_data["sifted_key"] = None

    print(f"[API /qkd_connect_blocking] Node ready for {key_handle}. Starting handshake...")

    start_time = time.time()
    peer_ready_and_connected = False

    # Handshake: Poll peer until peer is also ready, then confirm connection
    while time.time() - start_time < timeout / 1000:
        if conn_data.get("peer_connected"): # Check if peer already confirmed via /qkd_connect_peer
             peer_ready_and_connected = True
             print(f"[API /qkd_connect_blocking] Peer confirmed connection via /qkd_connect_peer for {key_handle}.")
             break

        try:
            # Ask peer if they are ready (called connect_blocking)
            check_response = requests.post(
                f"{config['peer_url']}/qkd_check_peer_connection",
                json={"key_handle": key_handle},
                timeout=1
            )
            if check_response.status_code == 200 and check_response.json().get("peer_ready"):
                 # Peer is also ready, now try to finalize connection with peer
                 print(f"[API /qkd_connect_blocking] Peer is ready for {key_handle}. Confirming connection...")
                 connect_response = requests.post(
                     f"{config['peer_url']}/qkd_connect_peer",
                     json={"key_handle": key_handle},
                     timeout=2
                 )
                 if connect_response.status_code == 200:
                     # We successfully told peer we are connecting, assume connected for now
                     # Peer might confirm back via /qkd_connect_peer shortly
                     peer_ready_and_connected = True
                     conn_data["peer_connected"] = True # Optimistically mark peer connected
                     print(f"[API /qkd_connect_blocking] Connection confirmation sent to peer for {key_handle}.")
                     break # Exit polling loop
                 else:
                     print(f"[API /qkd_connect_blocking] Peer check OK, but connect_peer failed ({connect_response.status_code}). Retrying...")
            # else:
                 # print(f"[API /qkd_connect_blocking] Waiting for peer ({key_handle})...")

        except requests.exceptions.RequestException as e:
            print(f"[API /qkd_connect_blocking] Warning during handshake {key_handle}: {e}")
            # Keep trying until timeout
        time.sleep(0.5) # Poll interval

    if peer_ready_and_connected:
        # --- Start the actual QKD protocol based on role ---
        role = conn_data["role"]
        requested_length = conn_data.get("requested_length", config['key_length_bits']) # Get length for Bob
        print(f"[API /qkd_connect_blocking] Handshake successful for {key_handle}. Starting QKD thread as {role}.")
        if role == "alice":
            qkd_thread = threading.Thread(target=perform_write_alice, args=(key_handle, requested_length))
        elif role == "bob":
            qkd_thread = threading.Thread(target=perform_read_bob, args=(key_handle, requested_length))
        else:
             conn_data["status"] = "error"; conn_data["error_message"] = "Invalid role for starting QKD"
             print(f"[API /qkd_connect_blocking] Invalid role '{role}' for {key_handle}.")
             return jsonify({"status": 5, "error": "INTERNAL_ERROR_INVALID_ROLE"}), 500

        qkd_thread.start()
        # Return success immediately, client polls /qkd_get_key or status endpoint
        return jsonify({"status": 0})
    else:
        # Timeout occurred or connection failed
        conn_data["local_connected"] = False # Reset local status
        conn_data["status"] = "error"
        conn_data["error_message"] = "TIMEOUT or PEER_CONNECT_FAILED during handshake"
        print(f"[API /qkd_connect_blocking] Handshake failed for {key_handle}: {conn_data['error_message']}")
        # Optionally notify peer to reset if possible
        return jsonify({"status": 4, "error": conn_data['error_message']}), 400


@app.route('/qkd_connect_peer', methods=['POST'])
def qkd_connect_peer():
    # Called by peer during the connect_blocking handshake to confirm they are connecting
    global connections
    key_handle = request.json.get("key_handle")
    if key_handle not in connections:
        return jsonify({"status": 2, "error": "Invalid key_handle"}), 400

    conn_data = connections[key_handle]
    # Check if this node is actually trying to connect
    if not conn_data.get("local_connected"):
        # Peer trying to connect, but this node hasn't called connect_blocking yet
        print(f"[API /qkd_connect_peer] Received connect from peer for {key_handle}, but local node not ready.")
        return jsonify({"status": 5, "error": "Node not in connecting state"}), 400

    conn_data["peer_connected"] = True # Mark peer as connected (confirmation received)
    print(f"[API /qkd_connect_peer] Peer confirmation received for {key_handle}.")
    # If this node is waiting in connect_blocking's loop, this helps it break
    return jsonify({"status": 0})

@app.route('/qkd_check_peer_connection', methods=['POST'])
def qkd_check_peer_connection():
    # Called by peer during connect_blocking handshake to see if this node is ready
    global connections
    key_handle = request.json.get("key_handle")
    if key_handle not in connections:
        return jsonify({"peer_ready": False}), 400 # Or status 2?

    # "Ready" means this node has also called connect_blocking
    is_ready = connections[key_handle].get("local_connected", False)
    # print(f"[API /qkd_check_peer_connection] Peer check for {key_handle}. This node ready: {is_ready}")
    return jsonify({"peer_ready": is_ready})


# --- Unified Endpoint for Basis Exchange ---
@app.route('/qkd_exchange_bases', methods=['POST'])
def qkd_exchange_bases():
    """Called by peer to send their bases."""
    global connections
    data = request.json
    key_handle = data.get("key_handle")
    peer_bases = data.get("bases")

    if key_handle not in connections:
        return jsonify({"status": 2, "error": "Invalid key_handle"}), 400

    if not peer_bases or not isinstance(peer_bases, str):
        return jsonify({"status": 1, "error": "Missing or invalid bases format (must be string)"}), 400

    conn_data = connections[key_handle]

    # Basic state check - should ideally be exchanging_bases or maybe transmitting/receiving
    if conn_data["status"] not in ["transmitting", "receiving", "exchanging_bases", "error"]:
         print(f"[{key_handle}] Warning: Received bases in unexpected state: {conn_data['status']}")
         # Allow proceeding if local bases are set, maybe bases arrived out of order
         # if not conn_data.get("local_bases"):
         #     return jsonify({"status": 5, "error": f"Not ready for bases exchange (State: {conn_data['status']})"}), 400

    print(f"[{key_handle}] Received peer bases ({len(peer_bases)} bases).")
    conn_data["peer_bases"] = peer_bases
    # Update status if it was transmitting/receiving
    if conn_data["status"] in ["transmitting", "receiving"]:
        conn_data["status"] = "exchanging_bases"


    # --- Trigger Key Sifting if local bases are also ready ---
    if conn_data.get("local_bases") and conn_data.get("peer_bases"):
        if conn_data["status"] not in ["sifting", "ready", "error"]: # Avoid multiple sift calls
            print(f"[{key_handle}] Both sets of bases received. Starting sifting thread...")
            sift_thread = threading.Thread(target=sift_key, args=(key_handle,))
            sift_thread.start()
        else:
             print(f"[{key_handle}] Bases received, but sifting already started/completed/failed (Status: {conn_data['status']}).")
    else:
        print(f"[{key_handle}] Peer bases received. Waiting for local bases before sifting.")

    return jsonify({"status": 0, "message": "Bases received."})


@app.route('/qkd_get_key', methods=['POST'])
def qkd_get_key():
    # Returns the final sifted key
    global connections
    data = request.json
    key_handle = data.get("key_handle")

    if key_handle not in connections:
        return jsonify({"status": 2, "error": "Invalid key_handle"}), 400

    conn_info = connections[key_handle]

    # Check QKD protocol status first
    if conn_info["status"] == "ready" and conn_info["sifted_key"] is not None:
        print(f"[API /qkd_get_key] Returning sifted key for {key_handle}.")
        return jsonify({
            "key_buffer": conn_info["sifted_key"],
            "status": 0
        })
    elif conn_info["status"] == "error":
        err_msg = conn_info.get('error_message', 'Unknown error')
        print(f"[API /qkd_get_key] Error occurred for {key_handle}: {err_msg}")
        return jsonify({"status": 7, "error": f"Key generation failed: {err_msg}"}), 500
    else: # Not ready, still processing
        print(f"[API /qkd_get_key] Key not ready yet for {key_handle} (Status: {conn_info['status']}).")
        # ETSI suggests status 1 (PEER_NOT_CONNECTED) or 6 (QKD_GET_KEY_FAILED)
        # Use 6 for "not ready yet"
        return jsonify({"status": 6, "error": f"Key generation not complete (Status: {conn_info['status']})"}), 400


@app.route('/qkd_close', methods=['POST'])
def qkd_close():
    # Closes the connection locally and notifies the peer
    global connections, config
    key_handle = request.json.get("key_handle")

    # Notify peer first (if reachable and handle exists locally)
    if key_handle in connections:
        try:
            print(f"[API /qkd_close] Notifying peer to close {key_handle}.")
            requests.post(
                    f"{config['peer_url']}/qkd_close_peer",
                    json={"key_handle": key_handle},
                    timeout=2 # Short timeout for close notification
                )
        except requests.exceptions.RequestException as e:
            print(f"[API /qkd_close] Peer unreachable during close for {key_handle}: {e}")
            # Continue with local cleanup anyway

    # Cleanup local state regardless of peer notification success
    if key_handle in connections:
        del connections[key_handle]
        print(f"[API /qkd_close] Closed local connection state for {key_handle}.")
        return jsonify({"status": 0})
    else:
        # ETSI: status 0 if successful, 2 if invalid handle
        print(f"[API /qkd_close] Invalid or already closed key_handle: {key_handle}.")
        return jsonify({"status": 2, "error": "Invalid key_handle"}), 400


@app.route('/qkd_close_peer', methods=['POST'])
def qkd_close_peer():
    # Called by peer to close a key_handle
    global connections
    key_handle = request.json.get("key_handle")

    if key_handle in connections:
        del connections[key_handle]
        print(f"[API /qkd_close_peer] Closed connection for {key_handle} due to peer request.")

    # Always return success even if handle was already gone
    return jsonify({"status": 0})

# --- End API Endpoints ---

# --- Main Execution ---
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="QKD Node API Server (BB84)")
    parser.add_argument("--host", default=DEFAULT_MY_ADDRESS, help=f"Host address to bind to (default: {DEFAULT_MY_ADDRESS})")
    parser.add_argument("--port", type=int, default=DEFAULT_MY_PORT, help=f"Port to listen on (default: {DEFAULT_MY_PORT})")
    parser.add_argument("--peer-host", required=True, help="Peer node host address (REQUIRED)")
    parser.add_argument("--peer-port", type=int, required=True, help="Peer node port (REQUIRED)")
    parser.add_argument("--node-type", choices=["gui", "hardware"], default=DEFAULT_NODE_TYPE, help=f"Type of QKD node interface (default: {DEFAULT_NODE_TYPE})")
    parser.add_argument("--time-between", type=float, default=DEFAULT_TIME_BETWEEN, help=f"Time between bit transmissions (seconds, default: {DEFAULT_TIME_BETWEEN})")
    parser.add_argument("--key-len", type=int, default=DEFAULT_KEY_LENGTH_BITS, help=f"Target sifted key length in bits (default: {DEFAULT_KEY_LENGTH_BITS})")
    parser.add_argument("--raw-mult", type=int, default=DEFAULT_RAW_KEY_MULTIPLIER, help=f"Multiplier for raw bits generation (raw = key_len * raw_mult, default: {DEFAULT_RAW_KEY_MULTIPLIER})")
    args = parser.parse_args()

    # Store config globally
    config['my_address'] = args.host
    config['my_port'] = args.port
    config['peer_address'] = args.peer_host
    config['peer_port'] = args.peer_port
    config['peer_url'] = f"http://{args.peer_host}:{args.peer_port}"
    config['node_type'] = args.node_type
    config['time_between'] = args.time_between
    config['key_length_bits'] = args.key_len
    config['raw_key_multiplier'] = args.raw_mult

    # Initialize the QKD Node
    try:
        print("--- QKD Node Configuration ---")
        for key, value in config.items():
            print(f"  {key}: {value}")
        print("-----------------------------")

        print("Initializing QKD Node...")
        if config['node_type'] == "hardware":
            qkd_node = QKD_Node_Hardware(time_between=config['time_between'])
            print(f"Hardware Node (RPi.GPIO) initialized.")
        elif config['node_type'] == "gui":
            qkd_node = QKD_Node_GUI(time_between=config['time_between'])
            print(f"GUI Node (Tkinter) initialized.")
        else:
            raise ValueError(f"Invalid NODE_TYPE: {config['node_type']}") # Should be caught by argparse

    except Exception as e:
        print(f"FATAL: Failed to initialize QKD Node: {e}")
        qkd_node = None # Ensure qkd_node is None if init fails
        exit(1) # Exit if node cannot be initialized

    # Start Flask Server
    print(f"Starting QKD API Server on {config['my_address']}:{config['my_port']}")
    print(f"Expecting Peer at {config['peer_url']}")
    try:
        # Use threaded=True for Flask dev server to handle concurrent requests
        app.run(host=config['my_address'], port=config['my_port'], threaded=True)
    except Exception as e:
        print(f"Failed to run server: {e}")
    finally:
        # Cleanup GPIO if hardware node was used
        if isinstance(qkd_node, QKD_Node_Hardware):
            print("Cleaning up GPIO...")
            qkd_node.cleanup()
        print("Server stopped.")
        
# python qkd_api_node.py --port 5001 --peer-host 192.168.1.233 --peer-port 5000 --node-type hardware --time-between 0.5