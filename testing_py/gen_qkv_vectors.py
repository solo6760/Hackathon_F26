import math
import os
import random
import numpy as np

M, D, H, DH, T = 16, 64, 2, 32, 16
OUT = "vectors_qkv"


def pack_row(vals):
    words = []
    for half in (vals[:8], vals[8:]):
        w = 0
        for i, v in enumerate(half):
            w |= (v & 0xF) << (4 * i)
        words.append(w)
    return words


def weight_tile(W, g, k):
    words = []
    for r in range(T):
        words += pack_row(W[k * T + r][g * T:(g + 1) * T])
    return words


def pack_weights_bram(W):
    words = []
    for g in range(D // T):
        for k in range(D // T):
            words += weight_tile(W, g, k)
    return words


def act_line(X, k):
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

    try:
        from sensor_fusion import generate_ares_trajectory, embed_sensor_stream
        data = generate_ares_trajectory(seq_len=M, seed=42)
        tokens, _ = embed_sensor_stream(data, d_model=D, seed=42)
        X = tokens.squeeze(0).numpy().tolist()
    except Exception:
        X = [[rng.randint(-128, 127) for _ in range(D)] for _ in range(M)]

    W_Q = [[rng.randint(-8, 7) for _ in range(D)] for _ in range(D)]
    W_K = [[rng.randint(-8, 7) for _ in range(D)] for _ in range(D)]
    W_V = [[rng.randint(-8, 7) for _ in range(D)] for _ in range(D)]

    Q = [[sum(X[m][k] * W_Q[k][n] for k in range(D)) for n in range(D)] for m in range(M)]
    K_proj = [[sum(X[m][k] * W_K[k][n] for k in range(D)) for n in range(D)] for m in range(M)]
    V = [[sum(X[m][k] * W_V[k][n] for k in range(D)) for n in range(D)] for m in range(M)]

    w_words_q = pack_weights_bram(W_Q)
    w_words_k = pack_weights_bram(W_K)
    w_words_v = pack_weights_bram(W_V)
    act_lines = [act_line(X, k) for k in range(D)]

    assert self_check_proj(w_words_q, act_lines, Q)
    assert self_check_proj(w_words_k, act_lines, K_proj)
    assert self_check_proj(w_words_v, act_lines, V)

    def requant8(mat):
        return [[max(-128, min(127, (val + 32) >> 6)) for val in row] for row in mat]

    Q_int8 = requant8(Q)
    K_int8 = requant8(K_proj)
    V_int8 = requant8(V)

    scores_h0 = [[sum(Q_int8[m][d] * K_int8[j][d] for d in range(DH)) for j in range(M)] for m in range(M)]
    scores_h1 = [[sum(Q_int8[m][DH + d] * K_int8[j][DH + d] for d in range(DH)) for j in range(M)] for m in range(M)]

    def softmax_row(row):
        max_val = max(row)
        shifted = [max(-8.0, (v - max_val) * 0.1768) for v in row]
        exp_vals = [math.exp(v) for v in shifted]
        s = sum(exp_vals)
        return [int(round((e / s) * 127)) for e in exp_vals]

    probs_h0 = [softmax_row(r) for r in scores_h0]
    probs_h1 = [softmax_row(r) for r in scores_h1]

    context_h0 = [[sum(probs_h0[m][j] * V_int8[j][d] for j in range(M)) for d in range(DH)] for m in range(M)]
    context_h1 = [[sum(probs_h1[m][j] * V_int8[j][DH + d] for j in range(M)) for d in range(DH)] for m in range(M)]

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

    print(f"Generated Q/K/V vectors in {OUT}/: {len(w_words_q)} words/proj, {len(act_lines)} act lines.")
