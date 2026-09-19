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


def load_model_weights():
    """Load canonical INT4 weights [64, 128] from the exported ONNX model."""
    candidates = [
        "../testing_py/transformer_layer_finn.onnx",
        "testing_py/transformer_layer_finn.onnx",
        "../testing_py/transformer_layer.onnx",
        "testing_py/transformer_layer.onnx",
    ]
    path = None
    for c in candidates:
        if os.path.exists(c):
            path = c
            break
    if path is None:
        return None

    try:
        import onnx
        from onnx import numpy_helper
        m = onnx.load(path)
        # Check for FINN transposed weights (64, 128)
        for init in m.graph.initializer:
            if init.name == "Quant_1_out0":
                arr = numpy_helper.to_array(init).astype(int)
                return arr.tolist()
        # Fallback: PyTorch layout [128, 64] -> quantize and transpose to [64, 128]
        for init in m.graph.initializer:
            if init.name == "fc1.weight":
                arr = numpy_helper.to_array(init)
                scale = 0.017854882
                arr_q = [
                    [max(-8, min(7, int(round(val / scale)))) for val in row]
                    for row in arr
                ]
                # Transpose [128, 64] -> [64, 128]
                return [[arr_q[n][k] for n in range(128)] for k in range(64)]
    except Exception as e:
        print(f"Note: failed to load ONNX ({e}), falling back to seeded generation")
        return None
    return None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate test vectors for fc1 datapath")
    parser.add_argument(
        "--source",
        choices=["model", "random"],
        default="model",
        help="Use real ONNX model weights or seeded random data (default: model)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for input activation generation (default: 42)",
    )
    args = parser.parse_args()

    rng = random.Random(args.seed)

    # Real input X (16x64, INT8 [-128, 127])
    X = [[rng.randint(-128, 127) for _ in range(K)] for _ in range(M)]

    W = None
    if args.source == "model":
        W = load_model_weights()
        if W is not None:
            print("Loaded real trained/exported fc1 weights from ONNX (shape: 64x128, INT4)")

    if W is None:
        print(f"Using seeded random weights (seed={args.seed})")
        W = [[rng.randint(-8, 7) for _ in range(N)] for _ in range(K)]

    # Golden INT32 accumulation: Y = X * W
    Y = [[sum(X[m][k] * W[k][n] for k in range(K)) for n in range(N)] for m in range(M)]

    # Fixed requantization to INT8 for downstream GeLU LUT (scale Sy = 1/32)
    # M_req = (Sx * Sw) / Sy = (1/128 * 0.017854882) / (1/32) ~= 293 / 65536
    M_REQ = 293
    SHIFT = 16
    Y_int8 = [
        [
            max(-128, min(127, (Y[m][n] * M_REQ + (1 << (SHIFT - 1))) >> SHIFT))
            for n in range(N)
        ]
        for m in range(M)
    ]

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
    write_hex(f"{OUT}/golden_fc1_int8.hex", [v & 0xFF for row in Y_int8 for v in row], 2)
    for g, k in CHECK_TILES:
        write_hex(f"{OUT}/exp_w_g{g}_k{k}.hex", weight_tile(W, g, k), 8)
        write_hex(f"{OUT}/exp_act_k{k}.hex", act_lines[k * T:(k + 1) * T], 32)

    flat = [v for row in Y for v in row]
    flat_int8 = [v for row in Y_int8 for v in row]
    print(f"wrote {OUT}/: {len(act_lines)} act lines, {len(w_words)} weight words, "
          f"{len(flat)} golden INT32 words (Y range {min(flat)}..{max(flat)}), "
          f"{len(flat_int8)} golden INT8 words (Y_int8 range {min(flat_int8)}..{max(flat_int8)})")
