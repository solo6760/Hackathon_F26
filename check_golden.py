with open('w_fc1.hex') as f:
    wmem = [int(line.strip(), 16) for line in f if line.strip()]
with open('act_fc1.hex') as f:
    amem = [line.strip() for line in f if line.strip()]

def sign_extend(val, bits):
    if val & (1 << (bits - 1)):
        return val - (1 << bits)
    return val

total = 0
for t in range(4):
    tile_sum = 0
    for k in range(16):
        w_addr = (0 << 7) | (t << 5) | (k << 1)
        w_lo = wmem[w_addr]
        vert0 = sign_extend(w_lo & 0xF, 4)
        
        a_addr = (t << 4) | k
        line_str = amem[a_addr]
        # byte 0 is the last 2 hex digits in verilog readmemh
        val_byte = int(line_str[-2:], 16)
        horiz0 = sign_extend(val_byte, 8)
        
        tile_sum += vert0 * horiz0
    total += tile_sum
    print(f"Tile {t}: tile_sum = {tile_sum}, running total = {total}")

with open('golden_fc1.hex') as f:
    golden = [int(line.strip(), 16) for line in f if line.strip()]
golden = [x if x < 0x80000000 else x - 0x100000000 for x in golden]
print(f"Golden Y[0][0] = {golden[0]}")

