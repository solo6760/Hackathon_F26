"""Test vector and BRAM hex generator for Attention Projections (Q/K/V) and Tiled Attention.

Generates ground-truth test vectors for Kade's core RTL engine:
  - W_Q, W_K, W_V packed INT4 weights (64x64, tile-major, 8 weights/word)
  - Q, K, V golden outputs (16x64, INT32 accumulation)
  - Scaled QK^T dot-product attention scores (16x16 per head, INT32 accumulation)
  - Context AV dot-product accumulation (16x32 per head, INT32 accumulation)
  - Softmax LUT probabilities (16x16 per head, INT8)

Outputs are written into ./vectors_qkv/ with full self-check validation.
"""

import math
import os
import random
import numpy as np

M = 16   # Sequence length
D = 64   # Model dimension
H = 2    # Heads
DH = 32  # Head dimension (D // H)
T = 16   # Hardware GEMM tile size (16x16)

OUT = "vectors_qkv"


def pack_row(vals):
    """Pack 16 INT4 values into two 32-bit words (LSB-first nibbles)."""
    words = []
    for half in (vals[:8], vals[8:]):
        w = 0
        for i, v in enumerate(half):
            w |= (v & 0xF) << (4 * i)
        words.append(w)
    return words


def weight_tile(W, g, k):
    """32 words for weight tile (g, k): rows 16k.., cols 16g.."""
    words = []
    for r in range(T):
        row = W[k * T + r][g * T:(g + 1) * T]
        words += pack_row(row)
    return words


def pack_weights_bram(W):
    """Packs a (K, N) = (64, 64) matrix into 512 32-bit BRAM words (tile-major)."""
    words = []
    k_tiles = 64 // T  # 4
    groups = 64 // T   # 4
    for g in range(groups):
        for k in range(k_tiles):
            words += weight_tile(W, g, k)
    return words


def act_line(X, k):
    """128-bit line holding column k across M=16 tokens: X[0..15][k]."""
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


def self_check_proj(w_words, act_lines, Y, K=64, N=64):
    """Rebuild Y from packed BRAM words and act lines to ensure layout integrity."""
    k_tiles, groups = K // T, N // T
    acc = [[0] * N for _ in range(M)]
    for g in range(groups):
        for k in range(k_tiles):
            tile = w_words[(g * k_tiles + k) * 32:(g * k_tiles + k + 1) * 32]
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

    # 1. Generate Input Activations X (16x64, INT8 [-128, 127])
    # Try importing ARES sensor trajectory if available
    try:
        from sensor_fusion import generate_ares_trajectory, embed_sensor_stream
        data = generate_ares_trajectory(seq_len=M, seed=42)
        tokens, _ = embed_sensor_stream(data, d_model=D, seed=42)
        X = tokens.squeeze(0).numpy().tolist()
        print("Using ARES robotics sensor-fusion trajectory as input X")
    except Exception:
        X = [[rng.randint(-128, 127) for _ in range(D)] for _ in range(M)]
        print("Using seeded random input X")

    # 2. Generate INT4 Weights for W_Q, W_K, W_V (64x64, [-8, 7])
    W_Q = [[rng.randint(-8, 7) for _ in range(D)] for _ in range(D)]
    W_K = [[rng.randint(-8, 7) for _ in range(D)] for _ in range(D)]
    W_V = [[rng.randint(-8, 7) for _ in range(D)] for _ in range(D)]

    # 3. Compute Golden Projections (16x64, INT32 accumulation)
    Q = [[sum(X[m][k] * W_Q[k][n] for k in range(D)) for n in range(D)] for m in range(M)]
    K_proj = [[sum(X[m][k] * W_K[k][n] for k in range(D)) for n in range(D)] for m in range(M)]
    V = [[sum(X[m][k] * W_V[k][n] for k in range(D)) for n in range(D)] for m in range(M)]

    # Pack weights and activations
    w_words_q = pack_weights_bram(W_Q)
    w_words_k = pack_weights_bram(W_K)
    w_words_v = pack_weights_bram(W_V)
    act_lines = [act_line(X, k) for k in range(D)]

    assert self_check_proj(w_words_q, act_lines, Q), "W_Q packed words failed self-check"
    assert self_check_proj(w_words_k, act_lines, K_proj), "W_K packed words failed self-check"
    assert self_check_proj(w_words_v, act_lines, V), "W_V packed words failed self-check"
    print("Q, K, V projection BRAM layouts verified successfully.")

    # 4. Attention Heads: Split into 2 heads of DH=32
    # Rescale Q and K projections to INT8 for attention dot-product:
    # Sx = 1/128, Sw = 1/64, Sy = 1/128 -> scale = Sw = 1/64 (approx right shift by 6)
    def requant8(mat):
        return [[max(-128, min(127, (val + 32) >> 6)) for val in row] for row in mat]

    Q_int8 = requant8(Q)
    K_int8 = requant8(K_proj)
    V_int8 = requant8(V)

    # QK^T per head: Q_h (16x32) x K_h^T (32x16) -> (16x16, INT32 acc)
    scores_h0 = [[sum(Q_int8[m][d] * K_int8[j][d] for d in range(DH)) for j in range(M)] for m in range(M)]
    scores_h1 = [[sum(Q_int8[m][DH + d] * K_int8[j][DH + d] for d in range(DH)) for j in range(M)] for m in range(M)]

    # Softmax LUT approximation per row (scaled by 1/sqrt(32) ~= 0.1768)
    def softmax_row(row):
        max_val = max(row)
        shifted = [max(-8.0, (v - max_val) * 0.1768) for v in row]
        exp_vals = [math.exp(v) for v in shifted]
        s = sum(exp_vals)
        probs = [e / s for e in exp_vals]
        # Quantize to INT8 [0, 127]
        return [int(round(p * 127)) for p in probs]

    probs_h0 = [softmax_row(r) for r in scores_h0]
    probs_h1 = [softmax_row(r) for r in scores_h1]

    # Context AV per head: P_h (16x16) x V_h (16x32) -> (16x32, INT32 acc)
    context_h0 = [[sum(probs_h0[m][j] * V_int8[j][d] for j in range(M)) for d in range(DH)] for m in range(M)]
    context_h1 = [[sum(probs_h1[m][j] * V_int8[j][DH + d] for j in range(M)) for d in range(DH)] for m in range(M)]

    # 5. Export Hex Files
    os.makedirs(OUT, exist_ok=True)
    write_hex(f"{OUT}/w_q.hex", w_words_q, 8)
    write_hex(f"{OUT}/w_k.hex", w_words_k, 8)
    write_hex(f"{OUT}/w_v.hex", w_words_v, 8)
    write_hex(f"{OUT}/act_in.hex", act_lines, 32)

    write_hex(f"{OUT}/golden_q.hex", [v for r in Q for v in r], 8)
    write_hex(f"{OUT}/golden_k.hex", [v for r in K_proj for v in r], 8)
    write_hex(f"{OUT}/golden_v.hex", [v for r in V for v in r], 8)

    write_hex(f"{OUT}/golden_scores_h0.hex", [v for r in scores_h0 for v in r], 8)
    write_hex(f"{OUT}/golden_scores_h1.hex", [v for r in scores_h1 for v in r], 8)

    write_hex(f"{OUT}/golden_probs_h0.hex", [v for r in probs_h0 for v in r], 2)
    write_hex(f"{OUT}/golden_probs_h1.hex", [v for r in probs_h1 for v in r], 2)

    write_hex(f"{OUT}/golden_context_h0.hex", [v for r in context_h0 for v in r], 8)
    write_hex(f"{OUT}/golden_context_h1.hex", [v for r in context_h1 for v in r], 8)

    print(f"Generated complete Q/K/V and attention test vector suite in {OUT}/:")
    print(f"  w_q.hex, w_k.hex, w_v.hex     : {len(w_words_q)} 32-bit words each (512 words = 2 KB per projection)")
    print(f"  act_in.hex                    : {len(act_lines)} lines x 128 bits")
    print(f"  golden_q/k/v.hex              : 1024 INT32 words each (16x64)")
    print(f"  golden_scores_h0/h1.hex       : 256 INT32 words each (16x16 score matrix)")
    print(f"  golden_context_h0/h1.hex      : 512 INT32 words each (16x32 context)")
