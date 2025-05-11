from .gf2_math import GF2Element

class AES:
    S_BOX = [
        [0x63, 0x7C, 0x77, 0x7B, 0xF2, 0x6B, 0x6F, 0xC5, 0x30, 0x01, 0x67, 0x2B, 0xFE, 0xD7, 0xAB, 0x76],
        [0xCA, 0x82, 0xC9, 0x7D, 0xFA, 0x59, 0x47, 0xF0, 0xAD, 0xD4, 0xA2, 0xAF, 0x9C, 0xA4, 0x72, 0xC0],
        [0xB7, 0xFD, 0x93, 0x26, 0x36, 0x3F, 0xF7, 0xCC, 0x34, 0xA5, 0xE5, 0xF1, 0x71, 0xD8, 0x31, 0x15],
        [0x04, 0xC7, 0x23, 0xC3, 0x18, 0x96, 0x05, 0x9A, 0x07, 0x12, 0x80, 0xE2, 0xEB, 0x27, 0xB2, 0x75],
        [0x09, 0x83, 0x2C, 0x1A, 0x1B, 0x6E, 0x5A, 0xA0, 0x52, 0x3B, 0xD6, 0xB3, 0x29, 0xE3, 0x2F, 0x84],
        [0x53, 0xD1, 0x00, 0xED, 0x20, 0xFC, 0xB1, 0x5B, 0x6A, 0xCB, 0xBE, 0x39, 0x4A, 0x4C, 0x58, 0xCF],
        [0xD0, 0xEF, 0xAA, 0xFB, 0x43, 0x4D, 0x33, 0x85, 0x45, 0xF9, 0x02, 0x7F, 0x50, 0x3C, 0x9F, 0xA8],
        [0x51, 0xA3, 0x40, 0x8F, 0x92, 0x9D, 0x38, 0xF5, 0xBC, 0xB6, 0xDA, 0x21, 0x10, 0xFF, 0xF3, 0xD2],
        [0xCD, 0x0C, 0x13, 0xEC, 0x5F, 0x97, 0x44, 0x17, 0xC4, 0xA7, 0x7E, 0x3D, 0x64, 0x5D, 0x19, 0x73],
        [0x60, 0x81, 0x4F, 0xDC, 0x22, 0x2A, 0x90, 0x88, 0x46, 0xEE, 0xB8, 0x14, 0xDE, 0x5E, 0x0B, 0xDB],
        [0xE0, 0x32, 0x3A, 0x0A, 0x49, 0x06, 0x24, 0x5C, 0xC2, 0xD3, 0xAC, 0x62, 0x91, 0x95, 0xE4, 0x79],
        [0xE7, 0xC8, 0x37, 0x6D, 0x8D, 0xD5, 0x4E, 0xA9, 0x6C, 0x56, 0xF4, 0xEA, 0x65, 0x7A, 0xAE, 0x08],
        [0xBA, 0x78, 0x25, 0x2E, 0x1C, 0xA6, 0xB4, 0xC6, 0xE8, 0xDD, 0x74, 0x1F, 0x4B, 0xBD, 0x8B, 0x8A],
        [0x70, 0x3E, 0xB5, 0x66, 0x48, 0x03, 0xF6, 0x0E, 0x61, 0x35, 0x57, 0xB9, 0x86, 0xC1, 0x1D, 0x9E],
        [0xE1, 0xF8, 0x98, 0x11, 0x69, 0xD9, 0x8E, 0x94, 0x9B, 0x1E, 0x87, 0xE9, 0xCE, 0x55, 0x28, 0xDF],
        [0x8C, 0xA1, 0x89, 0x0D, 0xBF, 0xE6, 0x42, 0x68, 0x41, 0x99, 0x2D, 0x0F, 0xB0, 0x54, 0xBB, 0x16]
    ]

    INV_S_BOX = [
        [0x52, 0x09, 0x6A, 0xD5, 0x30, 0x36, 0xA5, 0x38, 0xBF, 0x40, 0xA3, 0x9E, 0x81, 0xF3, 0xD7, 0xFB],
        [0x7C, 0xE3, 0x39, 0x82, 0x9B, 0x2F, 0xFF, 0x87, 0x34, 0x8E, 0x43, 0x44, 0xC4, 0xDE, 0xE9, 0xCB],
        [0x54, 0x7B, 0x94, 0x32, 0xA6, 0xC2, 0x23, 0x3D, 0xEE, 0x4C, 0x95, 0x0B, 0x42, 0xFA, 0xC3, 0x4E],
        [0x08, 0x2E, 0xA1, 0x66, 0x28, 0xD9, 0x24, 0xB2, 0x76, 0x5B, 0xA2, 0x49, 0x6D, 0x8B, 0xD1, 0x25],
        [0x72, 0xF8, 0xF6, 0x64, 0x86, 0x68, 0x98, 0x16, 0xD4, 0xA4, 0x5C, 0xCC, 0x5D, 0x65, 0xB6, 0x92],
        [0x6C, 0x70, 0x48, 0x50, 0xFD, 0xED, 0xB9, 0xDA, 0x5E, 0x15, 0x46, 0x57, 0xA7, 0x8D, 0x9D, 0x84],
        [0x90, 0xD8, 0xAB, 0x00, 0x8C, 0xBC, 0xD3, 0x0A, 0xF7, 0xE4, 0x58, 0x05, 0xB8, 0xB3, 0x45, 0x06],
        [0xD0, 0x2C, 0x1E, 0x8F, 0xCA, 0x3F, 0x0F, 0x02, 0xC1, 0xAF, 0xBD, 0x03, 0x01, 0x13, 0x8A, 0x6B],
        [0x3A, 0x91, 0x11, 0x41, 0x4F, 0x67, 0xDC, 0xEA, 0x97, 0xF2, 0xCF, 0xCE, 0xF0, 0xB4, 0xE6, 0x73],
        [0x96, 0xAC, 0x74, 0x22, 0xE7, 0xAD, 0x35, 0x85, 0xE2, 0xF9, 0x37, 0xE8, 0x1C, 0x75, 0xDF, 0x6E],
        [0x47, 0xF1, 0x1A, 0x71, 0x1D, 0x29, 0xC5, 0x89, 0x6F, 0xB7, 0x62, 0x0E, 0xAA, 0x18, 0xBE, 0x1B],
        [0xFC, 0x56, 0x3E, 0x4B, 0xC6, 0xD2, 0x79, 0x20, 0x9A, 0xDB, 0xC0, 0xFE, 0x78, 0xCD, 0x5A, 0xF4],
        [0x1F, 0xDD, 0xA8, 0x33, 0x88, 0x07, 0xC7, 0x31, 0xB1, 0x12, 0x10, 0x59, 0x27, 0x80, 0xEC, 0x5F],
        [0x60, 0x51, 0x7F, 0xA9, 0x19, 0xB5, 0x4A, 0x0D, 0x2D, 0xE5, 0x7A, 0x9F, 0x93, 0xC9, 0x9C, 0xEF],
        [0xA0, 0xE0, 0x3B, 0x4D, 0xAE, 0x2A, 0xF5, 0xB0, 0xC8, 0xEB, 0xBB, 0x3C, 0x83, 0x53, 0x99, 0x61],
        [0x17, 0x2B, 0x04, 0x7E, 0xBA, 0x77, 0xD6, 0x26, 0xE1, 0x69, 0x14, 0x63, 0x55, 0x21, 0x0C, 0x7D]
    ]

    RCON = [ 0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36 ]

    @staticmethod
    def state_to_bytes(state):
        ciphertext = bytearray(16)
        for i in range(4):
            for j in range(4):
                ciphertext[i * 4 + j] = state[j][i].poly
        return bytes(ciphertext)

    #
    # KEY MANAGEMENT METHODS
    #
    @staticmethod
    def add_round_key(state: [[GF2Element]], round_key: [[GF2Element]]) -> [[GF2Element]]:
        new_state = [[GF2Element(0) for _ in range(4)] for _ in range(4)]
        for i in range(4):
            for j in range(4):
                new_state[i][j] = state[i][j] + round_key[i][j]
        return new_state

    @staticmethod
    def rot_word(word: [GF2Element]) -> [GF2Element]:
        return [word[1], word[2], word[3], word[0]] # explicit left rotate

    @staticmethod
    def key_expansion(key: bytes) -> [[[GF2Element]]]:
        if len(key) != 16:
            raise ValueError("Key must be 16 bytes for AES-128")

        # Number of 32-bit words in key (Nk = 4 for AES-128)
        # Number of rounds (Nr = 10 for AES-128)
        # Total words needed: 4 * (Nr + 1) = 44
        Nk = 4
        Nr = 10
        Nb = 4  # Number of columns in state (always 4 for AES)
        expanded_words = [None] * (Nb * (Nr + 1))  # 44 words

        # First Nk words are the key itself
        for i in range(Nk):
            expanded_words[i] = [
                GF2Element(key[4 * i]),
                GF2Element(key[4 * i + 1]),
                GF2Element(key[4 * i + 2]),
                GF2Element(key[4 * i + 3])
            ]

        # Generate the remaining words
        for i in range(Nk, Nb * (Nr + 1)):
            temp = expanded_words[i - 1].copy()
            if i % Nk == 0:
                temp = AES.rot_word(temp)
                temp = [GF2Element(AES.S_BOX[e.poly // 16][e.poly % 16]) for e in temp]
                temp[0] = temp[0] + GF2Element(AES.RCON[(i // Nk) - 1])
            elif Nk > 6 and i % Nk == 4:
                temp = [GF2Element(AES.S_BOX[e.poly // 16][e.poly % 16]) for e in temp]

            # XOR with the word Nk positions back
            expanded_words[i] = [
                expanded_words[i - Nk][j] + temp[j] for j in range(4)
            ]

        # Convert to 4x4 round key matrices (11 rounds)
        round_keys = []
        for r in range(Nr + 1):
            round_key = [[None for _ in range(4)] for _ in range(4)]
            for i in range(4):
                for j in range(4):
                    round_key[j][i] = expanded_words[r * Nb + i][j]
            round_keys.append(round_key)

        return round_keys

    #
    # ENCRYPT METHODS
    #
    @staticmethod
    def subbytes(state: [[GF2Element]]) -> [[GF2Element]]:
        new_state: [[GF2Element]] = []

        for row in state:
            line: [GF2Element] = []
            for element in row:
                line.append(GF2Element(AES.S_BOX[element.poly // 16][element.poly % 16]))
            new_state.append(line)

        return new_state
    
    @staticmethod
    def shiftrows(state: [[GF2Element]]) -> [[GF2Element]]:
        new_state: [[GF2Element]] = []
        new_state.append(state[0])

        for i in range(1, 4):
            shifted = state[i][i:] + state[i][:i]
            new_state.append(shifted)

        return new_state

    @staticmethod
    def mixcolumn(column: [GF2Element]) -> [GF2Element]:
        mixed_column = [GF2Element(0) for _ in range(4)]
        matrix = [
            [GF2Element(0x02), GF2Element(0x03), GF2Element(0x01), GF2Element(0x01)],
            [GF2Element(0x01), GF2Element(0x02), GF2Element(0x03), GF2Element(0x01)],
            [GF2Element(0x01), GF2Element(0x01), GF2Element(0x02), GF2Element(0x03)],
            [GF2Element(0x03), GF2Element(0x01), GF2Element(0x01), GF2Element(0x02)]
        ]
        for i in range(4):
            for j in range(4):
                mixed_column[i] = mixed_column[i] + (matrix[i][j] * column[j])
        return mixed_column

    @staticmethod
    def mixcolumns(state: [[GF2Element]]) -> [[GF2Element]]:
        new_state = [[GF2Element(0) for _ in range(4)] for _ in range(4)]
        
        for i in range(4):
            column: [GF2Element] = [state[0][i], state[1][i], state[2][i], state[3][i]]
            mixed_column = AES.mixcolumn(column)
            
            for j in range(4):
                new_state[j][i] = mixed_column[j]
        
        return new_state

    @staticmethod
    def encrypt(plaintext: bytes, key: bytes) -> bytes:
        if len(plaintext) != 16 or len(key) != 16:
            raise ValueError("Plaintext and key must be 16 bytes for AES-128")

        # Initialize state
        state = [[GF2Element(0) for _ in range(4)] for _ in range(4)]
        for i in range(4):  # Column index
            for j in range(4):  # Row index
                state[j][i] = GF2Element(plaintext[i * 4 + j])

        round_keys = AES.key_expansion(key)

        # Initial round
        state = AES.add_round_key(state, round_keys[0])

        # Main rounds (1 to 9)
        for round_num in range(1, 10):
            state = AES.subbytes(state)
            state = AES.shiftrows(state)
            state = AES.mixcolumns(state)
            state = AES.add_round_key(state, round_keys[round_num])

        # Final round (10)
        state = AES.subbytes(state)
        state = AES.shiftrows(state)
        state = AES.add_round_key(state, round_keys[10])

        # Convert state back to bytes
        return AES.state_to_bytes(state)



    #
    # DECRYPT METHODS
    #
    @staticmethod
    def inv_subbytes(state: [[GF2Element]]) -> [[GF2Element]]:
        new_state: [[GF2Element]] = []
        for row in state:
            line: [GF2Element] = []
            for element in row:
                # Lookup in the inverse S-Box
                line.append(GF2Element(AES.INV_S_BOX[element.poly // 16][element.poly % 16]))
            new_state.append(line)
        return new_state

    @staticmethod
    def inv_shiftrows(state: [[GF2Element]]) -> [[GF2Element]]:
        new_state: [[GF2Element]] = [[] for _ in range(4)]
        
        new_state[0] = state[0]
        new_state[1] = state[1][-1:] + state[1][:-1]
        new_state[2] = state[2][-2:] + state[2][:-2]
        new_state[3] = state[3][-3:] + state[3][:-3]
        
        return new_state

    @staticmethod
    def inv_mixcolumn(column: [GF2Element]) -> [GF2Element]:
        mixed_column = [GF2Element(0) for _ in range(4)]
        matrix = [
            [GF2Element(0x0e), GF2Element(0x0b), GF2Element(0x0d), GF2Element(0x09)],
            [GF2Element(0x09), GF2Element(0x0e), GF2Element(0x0b), GF2Element(0x0d)],
            [GF2Element(0x0d), GF2Element(0x09), GF2Element(0x0e), GF2Element(0x0b)],
            [GF2Element(0x0b), GF2Element(0x0d), GF2Element(0x09), GF2Element(0x0e)]
        ]

        for i in range(4):
            for j in range(4):
                mixed_column[i] = mixed_column[i] + (matrix[i][j] * column[j])
        
        return mixed_column

    @staticmethod
    def inv_mixcolumns(state: [[GF2Element]]) -> [[GF2Element]]:
        new_state = [[GF2Element(0) for _ in range(4)] for _ in range(4)]
        for i in range(4):
            column: [GF2Element] = [state[j][i] for j in range(4)]
            mixed_column = AES.inv_mixcolumn(column)
            
            for j in range(4):
                new_state[j][i] = mixed_column[j]
        return new_state

    @staticmethod
    def decrypt(ciphertext: bytes, key: bytes) -> bytes:
        if len(ciphertext) != 16 or len(key) != 16:
            raise ValueError("Ciphertext and key must be 16 bytes for AES-128")

        Nr = 10 # Number of rounds for AES-128

        # Initialize state from ciphertext (column-major)
        state = [[GF2Element(0) for _ in range(4)] for _ in range(4)]
        for i in range(4):  # Column index
            for j in range(4):  # Row index
                state[j][i] = GF2Element(ciphertext[i * 4 + j])

        # Generate round keys
        round_keys = AES.key_expansion(key)

        # Initial AddRoundKey (using last round key)
        state = AES.add_round_key(state, round_keys[Nr])

        # Main rounds (Nr-1 down to 1)
        for round_num in range(Nr - 1, 0, -1):
            state = AES.inv_shiftrows(state)
            state = AES.inv_subbytes(state)
            state = AES.add_round_key(state, round_keys[round_num])
            state = AES.inv_mixcolumns(state)

        # Final round (Round 0)
        state = AES.inv_shiftrows(state)
        state = AES.inv_subbytes(state)
        state = AES.add_round_key(state, round_keys[0])

        # Convert state back to bytes
        return  AES.state_to_bytes(state)