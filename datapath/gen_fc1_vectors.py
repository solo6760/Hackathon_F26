"""Test vectors for the fc1 datapath: Y (16x128, INT32) = X (16x64, INT8) x W (64x128, INT4).

Writes into ./vectors/:
  act_fc1.hex      64 lines x 128 bits, K-major: line k = X[0..15][k], byte m at bits [8m+7:8m]
  w_fc1.hex        1024 x 32-bit words, tile-major: tile t = group*4 + k, 32 words per tile,
                   row r at words t*32 + 2r (n 0-7) and t*32 + 2r + 1 (n 8-15), LSB-first nibbles
  golden_fc1.hex   2048 x 32-bit words, Y in (M, N) row-major, two's complement
  exp_w_g{g}_k{k}.hex / exp_act_k{k}.hex   single-tile dumps for the addressing check

Layouts match datapath/PLAN.md section 4. Pure Python, no numpy needed.
"""
import os
import random

M, K, N = 16, 64, 128
T = 16
K_TILES, GROUPS = K // T, N // T
CHECK_TILES = [(0, 0), (4, 1), (7, 3)]  # (group, k): first, middle, last

OUT = "vectors"


def pack_row(vals):
    """16 INT4 values -> two 32-bit words, value i at bits [4i+3:4i] of its word."""
    words = []
    for half in (vals[:8], vals[8:]):
        w = 0
        for i, v in enumerate(half):
            w |= (v & 0xF) << (4 * i)
        words.append(w)
    return words


def weight_tile(W, g, k):
    """32 words for weight tile (g, k): rows K = 16k.., cols N = 16g.."""
    words = []
    for r in range(T):
        row = W[k * T + r][g * T:(g + 1) * T]
        words += pack_row(row)
    return words


def act_line(X, k):
    """128-bit value holding X[0..15][k], byte m at bits [8m+7:8m]."""
    line = 0
    for m in range(M):
        line |= (X[m][k] & 0xFF) << (8 * m)
    return line


def write_hex(path, values, digits):
    with open(path, "w") as f:
        for v in values:
            f.write(f"{v & ((1 << (4 * digits)) - 1):0{digits}X}\n")


def sext(v, bits):
    return v - (1 << bits) if v & (1 << (bits - 1)) else v


def self_check(w_words, act_lines, Y):
    """Rebuild Y from the packed files alone, so a layout bug can't hide."""
    acc = [[0] * N for _ in range(M)]
    for g in range(GROUPS):
        for k in range(K_TILES):
            tile = w_words[(g * K_TILES + k) * 32:(g * K_TILES + k + 1) * 32]
            for r in range(T):
                kk = k * T + r
                wrow = [sext((tile[2 * r + n // 8] >> (4 * (n % 8))) & 0xF, 4) for n in range(T)]
                xcol = [sext((act_lines[kk] >> (8 * m)) & 0xFF, 8) for m in range(M)]
                for m in range(M):
                    for n in range(T):
                        acc[m][g * T + n] += xcol[m] * wrow[n]
    return acc == Y


if __name__ == "__main__":
    rng = random.Random(42)
    X = [[rng.randint(-128, 127) for _ in range(K)] for _ in range(M)]
    W = [[rng.randint(-8, 7) for _ in range(N)] for _ in range(K)]
    Y = [[sum(X[m][k] * W[k][n] for k in range(K)) for n in range(N)] for m in range(M)]

    w_words = []
    for g in range(GROUPS):
        for k in range(K_TILES):
            w_words += weight_tile(W, g, k)
    act_lines = [act_line(X, k) for k in range(K)]

    assert self_check(w_words, act_lines, Y), "packed files don't reproduce Y"

    os.makedirs(OUT, exist_ok=True)
    write_hex(f"{OUT}/act_fc1.hex", act_lines, 32)
    write_hex(f"{OUT}/w_fc1.hex", w_words, 8)
    write_hex(f"{OUT}/golden_fc1.hex", [v for row in Y for v in row], 8)
    for g, k in CHECK_TILES:
        write_hex(f"{OUT}/exp_w_g{g}_k{k}.hex", weight_tile(W, g, k), 8)
        write_hex(f"{OUT}/exp_act_k{k}.hex", act_lines[k * T:(k + 1) * T], 32)

    flat = [v for row in Y for v in row]
    print(f"wrote {OUT}/: {len(act_lines)} act lines, {len(w_words)} weight words, "
          f"{len(flat)} golden words (Y range {min(flat)}..{max(flat)})")
