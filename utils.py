import math

def hex_to_bin(hex_string):
    """Converts a hex string to a binary string, padding to ensure correct length."""
    if not hex_string:
        return ""
    scale = 16 ## equals to hexadecimal
    num_of_bits = len(hex_string) * 4
    try:
        return bin(int(hex_string, scale))[2:].zfill(num_of_bits)
    except ValueError:
        print(f"Error: Invalid hex string '{hex_string}'")
        return None # Or raise error

def bin_to_hex(bin_string):
    """Converts a binary string to a hex string."""
    if not bin_string:
        return ""
    try:
        num = int(bin_string, 2)
        hex_len = math.ceil(len(bin_string) / 4)
        return format(num, f'0{hex_len}x')
    except ValueError:
        print(f"Error: Invalid binary string '{bin_string}'")
        return None # Or raise error

def calculate_parity(binary_block):
    """Calculates the parity of a binary string (0 for even 1s, 1 for odd 1s)."""
    return binary_block.count('1') % 2

def get_block_parities(binary_key, block_size):
    """Divides a binary key into blocks and calculates parity for each."""
    parities = []
    if not binary_key:
        return parities
    for i in range(0, len(binary_key), block_size):
        block = binary_key[i:i+block_size]
        # Handle potential partial block at the end if needed,
        # though typically keys are padded or block size chosen carefully.
        # For simplicity, we only process full blocks here or assume padding.
        if len(block) == block_size: # Process only full blocks
             parities.append(calculate_parity(block))
        # else:
        #    print(f"Warning: Skipping partial block of size {len(block)}")
    return parities

# --- Example Usage (Conceptual) ---
alice_sifted_key_hex = "a1b2c3d4"
bob_sifted_key_hex = "a1b3c3d4" # Example with one error in 2nd byte

alice_sifted_key_bin = hex_to_bin(alice_sifted_key_hex)
bob_sifted_key_bin = hex_to_bin(bob_sifted_key_hex)

block_size = 8 # Example block size (1 byte)

if alice_sifted_key_bin and bob_sifted_key_bin:
    alice_parities = get_block_parities(alice_sifted_key_bin, block_size)
    bob_parities = get_block_parities(bob_sifted_key_bin, block_size)

    print("Alice's Parities:", alice_parities)
    print("Bob's Parities:  ", bob_parities)

    mismatched_blocks = []
    for i in range(min(len(alice_parities), len(bob_parities))):
        if alice_parities[i] != bob_parities[i]:
            print(f"Parity mismatch found in block {i}")
            mismatched_blocks.append(i)
            # Next step would be interactive error location for these blocks
