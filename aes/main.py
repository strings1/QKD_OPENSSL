from aes import AES

if __name__ == '__main__':
    # plaintext   = bytes.fromhex('00112233445566778899aabbccddeeff')
    # key         = bytes.fromhex('000102030405060708090a0b0c0d0e0f')

    plaintext   = bytes.fromhex('6BC1BEE22E409F96E93D7E117393172A') # cipher: 3AD77BB4 0D7A3660 A89ECAF3 2466EF97
    key         = bytes.fromhex('2B7E151628AED2A6ABF7158809CF4F3C')

    ciphertext = AES.encrypt(plaintext, key)
    dec_text = AES.decrypt(ciphertext, key)

    print("Plaintext:", plaintext.hex())
    print("Key:", key.hex())
    print("Ciphertext:", ciphertext.hex())
    print("Decrypted back:", dec_text.hex())

    print("Plaintex equals decrypted: ", plaintext == dec_text)