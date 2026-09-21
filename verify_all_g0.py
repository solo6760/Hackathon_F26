with open('w_fc1.hex') as f:
    wmem = [int(line.strip(), 16) for line in f if line.strip()]
with open('act_fc1.hex') as f:
    amem = [line.strip() for line in f if line.strip()]
with open('golden_fc1.hex') as f:
    golden = [int(line.strip(), 16) for line in f if line.strip()]
golden = [x if x < 0x80000000 else x - 0x100000000 for x in golden]

def sign_extend(val, bits):
    if val & (1 << (bits - 1)):
        return val - (1 << bits)
    return val

errors = 0
for m in range(16):
    for n in range(16):
        total = 0
        for t in range(4):
            for k in range(16):
                w_addr = (0 << 7) | (t << 5) | (k << 1)
                if n >= 8:
                    w_word = wmem[w_addr | 1]
                    shift = 4 * (n - 8)
                else:
                    w_word = wmem[w_addr]
                    shift = 4 * n
                w_val = sign_extend((w_word >> shift) & 0xF, 4)
                
                a_addr = (t << 4) | k
                line_str = amem[a_addr]
                # 32 chars = 16 bytes. Byte m is at end - 2*(m+1) : end - 2*m
                start_idx = len(line_str) - 2 * (m + 1)
                end_idx = len(line_str) - 2 * m
                a_byte = int(line_str[start_idx:end_idx], 16)
                a_val = sign_extend(a_byte, 8)
                
                total += w_val * a_val
        gold = golden[m * 128 + n]
        if total != gold:
            print(f"Mismatch at m={m}, n={n}: calculated={total}, golden={gold}")
            errors += 1

if errors == 0:
    print("ALL 256 ELEMENTS (Tokens 0..15, Channels 0..15) MATCH GOLDEN PERFECTLY!")
else:
    print(f"Found {errors} mismatches.")

