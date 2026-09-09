import numpy as np

# Fixed seed so everyone gets identical numbers
np.random.seed(42)

# Dimensions agreed with Kade
M, K, N = 16, 16, 16  # Tile shape

# 1. Generate random valid inputs
# Signed INT8 activations: [-128, 127]
act_int8 = np.random.randint(-128, 128, size=(M, K), dtype=np.int8)
# Signed INT4 weights: [-8, 7]
weights_int4 = np.random.randint(-8, 8, size=(K, N), dtype=np.int8)

# 2. Compute exact golden output (32-bit integer accumulation)
golden_out = np.matmul(act_int8.astype(np.int32), weights_int4.astype(np.int32))

# 3. Export activations (1 byte per line, hex format)
with open("act_tile.hex", "w") as f:
    for val in act_int8.flatten():
        f.write(f"{int(val) & 0xFF:02X}\n")

# 4. Pack INT4 weights LSB-first into 32-bit BRAM words (8 weights / 4 bytes per line)
flat_w = weights_int4.flatten()
packed_words = []
for i in range(0, len(flat_w), 8):
    chunk = flat_w[i:i+8]
    word = 0
    for j in range(4):
        low = int(chunk[2*j]) & 0x0F
        high = int(chunk[2*j+1]) & 0x0F
        byte = (high << 4) | low
        word |= (byte << (8 * j))
    packed_words.append(word)

with open("weights_bram.hex", "w") as f:
    for word in packed_words:
        f.write(f"{word:08X}\n")

# 5. Export golden expected output (32-bit signed hex)
with open("golden_out.hex", "w") as f:
    for val in golden_out.flatten():
        f.write(f"{int(val) & 0xFFFFFFFF:08X}\n")

print("Generated act_tile.hex, weights_bram.hex, and golden_out.hex successfully.")