import os
import random

M, K, N = 16, 64, 128
T = 16
K_TILES, GROUPS = K // T, N // T
CHECK_TILES = [(0, 0), (4, 1), (7, 3)]
OUT = "vectors"


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


def self_check(w_words, act_lines, Y):
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


def load_model_weights():
    candidates = [
        "../testing_py/transformer_layer_finn.onnx",
        "testing_py/transformer_layer_finn.onnx",
        "../testing_py/transformer_layer.onnx",
        "testing_py/transformer_layer.onnx",
    ]
    path = next((c for c in candidates if os.path.exists(c)), None)
    if path is None:
        return None

    try:
        import onnx
        from onnx import numpy_helper
        m = onnx.load(path)
        for init in m.graph.initializer:
            if init.name == "Quant_1_out0":
                return numpy_helper.to_array(init).astype(int).tolist()
        for init in m.graph.initializer:
            if init.name == "fc1.weight":
                arr = numpy_helper.to_array(init)
                scale = 0.017854882
                arr_q = [[max(-8, min(7, int(round(v / scale)))) for v in row] for row in arr]
                return [[arr_q[n][k] for n in range(128)] for k in range(64)]
    except Exception:
        return None
    return None


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["model", "random"], default="model")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    X = [[rng.randint(-128, 127) for _ in range(K)] for _ in range(M)]

    W = load_model_weights() if args.source == "model" else None
    if W is None:
        W = [[rng.randint(-8, 7) for _ in range(N)] for _ in range(K)]

    Y = [[sum(X[m][k] * W[k][n] for k in range(K)) for n in range(N)] for m in range(M)]

    M_REQ, SHIFT = 293, 16
    Y_int8 = [
        [max(-128, min(127, (Y[m][n] * M_REQ + (1 << (SHIFT - 1))) >> SHIFT)) for n in range(N)]
        for m in range(M)
    ]

    w_words = []
    for g in range(GROUPS):
        for k in range(K_TILES):
            w_words += weight_tile(W, g, k)
    act_lines = [act_line(X, k) for k in range(K)]

    assert self_check(w_words, act_lines, Y)

    os.makedirs(OUT, exist_ok=True)
    write_hex(f"{OUT}/act_fc1.hex", act_lines, 32)
    write_hex(f"{OUT}/w_fc1.hex", w_words, 8)
    write_hex(f"{OUT}/golden_fc1.hex", [v for row in Y for v in row], 8)
    write_hex(f"{OUT}/golden_fc1_int8.hex", [v & 0xFF for row in Y_int8 for v in row], 2)
    for g, k in CHECK_TILES:
        write_hex(f"{OUT}/exp_w_g{g}_k{k}.hex", weight_tile(W, g, k), 8)
        write_hex(f"{OUT}/exp_act_k{k}.hex", act_lines[k * T:(k + 1) * T], 32)

    flat = [v for row in Y for v in row]
    print(f"wrote {OUT}/: {len(act_lines)} act lines, {len(w_words)} weight words, {len(flat)} golden words.")
