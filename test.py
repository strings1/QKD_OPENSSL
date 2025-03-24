import requests

ALICE_URL = "http://192.168.1.233:5000"
BOB_URL = "http://192.168.1.137:5001"

# Step 1: Open key_handle
try:
    response = requests.post(f"{ALICE_URL}/qkd_open", json={})
    if response.status_code != 200:
        print(f"Open failed: {response.json()}")
        exit()
    key_handle = response.json()["key_handle"]
    print(f"Key Handle: {key_handle}")
except Exception as e:
    print(f"Error opening key_handle: {e}")
    exit()

# Step 2: Connect blocking
try:
    # Connect Alice
    alice_connect = requests.post(
        f"{ALICE_URL}/qkd_connect_blocking",
        json={"key_handle": key_handle}
    )
    if alice_connect.status_code != 200:
        print(f"Alice connection failed: {alice_connect.json()}")
        exit()

    # Connect Bob
    bob_connect = requests.post(
        f"{BOB_URL}/qkd_connect_blocking",
        json={"key_handle": key_handle}
    )
    if bob_connect.status_code != 200:
        print(f"Bob connection failed: {bob_connect.json()}")
        exit()
except Exception as e:
    print(f"Connection error: {e}")
    exit()

# Step 3: Get keys
try:
    alice_key = requests.post(f"{ALICE_URL}/qkd_get_key", json={"key_handle": key_handle}).json()
    if "key_buffer" not in alice_key:
        print(f"Alice key error: {alice_key}")
        exit()
    bob_key = requests.post(f"{BOB_URL}/qkd_get_key", json={"key_handle": key_handle}).json()
    if "key_buffer" not in bob_key:
        print(f"Bob key error: {bob_key}")
        exit()

    print(f"Alice Key: {alice_key['key_buffer']}")
    print(f"Bob Key: {bob_key['key_buffer']}")
    assert alice_key["key_buffer"] == bob_key["key_buffer"], "Keys do not match!"
except Exception as e:
    print(f"Key retrieval error: {e}")
    exit()

# Step 4: Close connection
requests.post(f"{ALICE_URL}/qkd_close", json={"key_handle": key_handle})
requests.post(f"{BOB_URL}/qkd_close", json={"key_handle": key_handle})
print("Success!")