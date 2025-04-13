import requests
import time
import threading # Import threading

ALICE_URL = "http://192.168.1.140:5001"
BOB_URL = "http://192.168.1.137:5000"
POLL_INTERVAL = 5 # Seconds between checking key status
MAX_WAIT_TIME = 600 # Maximum seconds to wait for keys (adjust based on key length/time_between)
CONNECT_TIMEOUT = 30 # Timeout for the connect_blocking calls themselves (seconds)

key_handle = None # Initialize key_handle
connect_results = {} # To store results from threads

# --- Function to call connect_blocking ---
def connect_node(node_name, url, handle):
    global connect_results
    try:
        print(f"  Thread starting connection for {node_name}...")
        response = requests.post(
            f"{url}/qkd_connect_blocking",
            json={"key_handle": handle},
            timeout=CONNECT_TIMEOUT
        )
        response.raise_for_status()
        print(f"  {node_name} connect call successful (QKD thread started on server).")
        connect_results[node_name] = {"success": True, "response": response.json()}
    except requests.exceptions.Timeout:
        print(f"  ERROR: {node_name} connection timed out after {CONNECT_TIMEOUT}s.")
        connect_results[node_name] = {"success": False, "error": "Timeout"}
    except requests.exceptions.RequestException as e:
        print(f"  ERROR: {node_name} connection failed: {e}")
        error_detail = "Unknown error"
        try:
            error_detail = e.response.json() if e.response else str(e)
        except: # Handle cases where response is not JSON
             error_detail = str(e)
        connect_results[node_name] = {"success": False, "error": error_detail}
    except Exception as e:
        print(f"  ERROR: Unexpected error connecting {node_name}: {e}")
        connect_results[node_name] = {"success": False, "error": str(e)}
# --- End function ---


# Step 1: Open key_handle
try:
    print("Step 1: Opening key handle...")
    response = requests.post(f"{ALICE_URL}/qkd_open", json={}, timeout=10)
    response.raise_for_status() # Raise exception for bad status codes (4xx or 5xx)
    key_handle = response.json()["key_handle"]
    print(f"  Key Handle: {key_handle}")
except requests.exceptions.RequestException as e:
    print(f"Error opening key_handle: {e}")
    exit(1)
except Exception as e:
    print(f"Unexpected error during open: {e}")
    exit(1)

# Step 2: Connect blocking (using threads)
try:
    print("\nStep 2: Connecting nodes concurrently (triggers QKD)...")
    alice_thread = threading.Thread(target=connect_node, args=("Alice", ALICE_URL, key_handle))
    bob_thread = threading.Thread(target=connect_node, args=("Bob", BOB_URL, key_handle))

    alice_thread.start()
    bob_thread.start()

    alice_thread.join() # Wait for Alice's connect call to finish/timeout
    bob_thread.join()   # Wait for Bob's connect call to finish/timeout

    # Check results from threads
    if not connect_results.get("Alice", {}).get("success", False):
        print(f"Alice connection failed: {connect_results.get('Alice', {}).get('error', 'Unknown')}")
        raise ConnectionError("Alice failed to connect")
    if not connect_results.get("Bob", {}).get("success", False):
        print(f"Bob connection failed: {connect_results.get('Bob', {}).get('error', 'Unknown')}")
        raise ConnectionError("Bob failed to connect")

    print("  Both connect calls initiated successfully.")
    print("  QKD protocol should now be running on both nodes...")

except Exception as e:
    print(f"Connection error during threading/joining: {e}")
    if key_handle: # Try to close if open succeeded
        print("Attempting cleanup...")
        requests.post(f"{ALICE_URL}/qkd_close", json={"key_handle": key_handle}, timeout=5)
        requests.post(f"{BOB_URL}/qkd_close", json={"key_handle": key_handle}, timeout=5)
    exit(1)

# --- Wait for key generation ---
input("Press Enter to continue...") # Optional pause before polling
# Step 3: Poll for and Get keys (Keep the polling logic from previous version)
print(f"\nStep 3: Waiting for key generation (up to {MAX_WAIT_TIME}s)...")
start_wait_time = time.time()
alice_key_data = None
bob_key_data = None

while time.time() - start_wait_time < MAX_WAIT_TIME:
    try:
        # Check Alice
        alice_resp = requests.post(f"{ALICE_URL}/qkd_get_key", json={"key_handle": key_handle}, timeout=5)
        alice_status = alice_resp.json()

        # Check Bob
        bob_resp = requests.post(f"{BOB_URL}/qkd_get_key", json={"key_handle": key_handle}, timeout=5)
        bob_status = bob_resp.json()

        alice_ready = alice_resp.status_code == 200 and "key_buffer" in alice_status
        bob_ready = bob_resp.status_code == 200 and "key_buffer" in bob_status

        alice_error = alice_status.get("status") == 7 # Check for specific error status
        bob_error = bob_status.get("status") == 7

        if alice_ready and bob_ready:
            print("  Both nodes reported key ready.")
            alice_key_data = alice_status
            bob_key_data = bob_status
            break # Exit loop, keys are ready
        elif alice_error or bob_error:
            print("  Error reported by at least one node during key generation.")
            print(f"  Alice Status: {alice_status}")
            print(f"  Bob Status: {bob_status}")
            alice_key_data = alice_status # Store status for potential later inspection
            bob_key_data = bob_status
            break # Exit loop on error
        else:
            # Use .get() with default values for safer status printing
            alice_s = alice_status.get('status', 'N/A') if isinstance(alice_status, dict) else 'Invalid Resp'
            bob_s = bob_status.get('status', 'N/A') if isinstance(bob_status, dict) else 'Invalid Resp'
            print(f"  Waiting... (Alice status: {alice_s}, Bob status: {bob_s})")
            time.sleep(POLL_INTERVAL)

    except requests.exceptions.RequestException as e:
        print(f"  Polling error: {e}. Retrying...")
        time.sleep(POLL_INTERVAL)
    except Exception as e:
         print(f"  Unexpected error during polling: {e}")
         break # Exit loop on unexpected error

else: # Loop finished without break (timeout)
    print(f"Error: Timeout after {MAX_WAIT_TIME}s waiting for keys.")
    # Attempt to get final status if possible
    try:
        alice_key_data = requests.post(f"{ALICE_URL}/qkd_get_key", json={"key_handle": key_handle}, timeout=5).json()
        bob_key_data = requests.post(f"{BOB_URL}/qkd_get_key", json={"key_handle": key_handle}, timeout=5).json()
        print(f"  Final Alice Status: {alice_key_data}")
        print(f"  Final Bob Status: {bob_key_data}")
    except Exception as e:
        print(f"  Could not retrieve final status: {e}")
    # Proceed to cleanup

# --- Process results after loop ---
alice_key = None
bob_key = None
success = False

if alice_key_data and bob_key_data:
    if isinstance(alice_key_data, dict) and isinstance(bob_key_data, dict) and \
       "key_buffer" in alice_key_data and "key_buffer" in bob_key_data:
        alice_key = alice_key_data["key_buffer"]
        bob_key = bob_key_data["key_buffer"]
        print(f"\n  Alice Key: {alice_key[:32]}...") # Print first 32 chars
        print(f"  Bob Key:   {bob_key[:32]}...")
        if alice_key == bob_key and len(alice_key) > 0: # Check key is not empty
            print("  Keys MATCH!")
            success = True
        elif len(alice_key) == 0 and len(bob_key) == 0:
             print("  Key generation resulted in empty keys (check QBER/raw bits).")
        else:
            print("  ERROR: Keys DO NOT MATCH!")
    else:
        print("\n  Key generation failed or timed out.")
        if isinstance(alice_key_data, dict) and "error" in alice_key_data: print(f"  Alice Error: {alice_key_data['error']}")
        if isinstance(bob_key_data, dict) and "error" in bob_key_data: print(f"  Bob Error: {bob_key_data['error']}")
else:
     print("\n  Could not retrieve key status from one or both nodes after waiting.")


# Step 4: Close connection
if key_handle:
    print("\nStep 4: Closing connection...")
    try:
        requests.post(f"{ALICE_URL}/qkd_close", json={"key_handle": key_handle}, timeout=5)
        requests.post(f"{BOB_URL}/qkd_close", json={"key_handle": key_handle}, timeout=5)
        print("  Connection closed.")
    except requests.exceptions.RequestException as e:
        print(f"  Error closing connection: {e}")

if success:
    print("\nSuccess!")
else:
    print("\nFailed!")
    exit(1)