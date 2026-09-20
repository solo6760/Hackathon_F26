"""Vectorized Test Vector Generator for the FC1 Datapath.

Hardware specs:
  - Input X: 16x64 Signed INT8 [-128, 127]
  - Weights W: 64x128 Signed INT4 [-8, 7]
  - Accumulator Y: 16x128 Signed INT32
  - BRAM layout: Tile-major (8 groups x 4 K-tiles), LSB-first nibble packing (8 INT4/32-bit word)
"""

import os
import random
import numpy as np

M, K, N = 16, 64, 128
T = 16
K_TILES, GROUPS = K // T, N // T
CHECK_TILES = [(0, 0), (4, 1), (7, 3)]
OUT = "vectors"


def pack_weights_bram_fast(W):
    """Vectorized tile-major BRAM packing (8 INT4 nibbles per 32-bit word, LSB-first)."""
    W = np.asarray(W, dtype=np.int8)
    tiled = W.reshape(K_TILES, T, GROUPS, T).transpose(2, 0, 1, 3)
    nibbles = tiled.reshape(-1, 8).astype(np.uint32) & 0x0F
    shifts = np.array([0, 4, 8, 12, 16, 20, 24, 28], dtype=np.uint32)
    return np.bitwise_or.reduce(np.left_shift(nibbles, shifts), axis=1)


def unpack_weights_bram_fast(words):
    """Vectorized unpacking of BRAM words back to (64, 128) for bitwise self-check."""
    words = np.asarray(words, dtype=np.uint32)[:, None]
    shifts = np.array([0, 4, 8, 12, 16, 20, 24, 28], dtype=np.uint32)
    nibbles = np.bitwise_and(np.right_shift(words, shifts), 0x0F)
    signed_w = np.where(nibbles >= 8, nibbles - 16, nibbles).astype(np.int8)
    return signed_w.reshape(GROUPS, K_TILES, T, T).transpose(1, 2, 0, 3).reshape(K, N)


def pack_act_lines_fast(X):
    """Vectorized packaging of M=16 tokens across K=64 into 64 lines x 128-bit hex strings."""
    X = np.asarray(X, dtype=np.int8)
    u8_rev = X[::-1, :].astype(np.uint8)
    return [bytes(u8_rev[:, k]).hex().upper() for k in range(K)]


def batch_write_hex(filepath, values, width_chars=8):
    """High-speed batch disk writer producing $readmemh-compliant hex files."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    if isinstance(values[0], str):
        buf = "\n".join(values) + "\n"
    elif width_chars == 8:
        arr = np.asarray(values, dtype=np.uint32)
        buf = "\n".join(f"{int(x):08X}" for x in arr.flatten()) + "\n"
    elif width_chars == 2:
        arr = np.asarray(values, dtype=np.uint8)
        buf = "\n".join(f"{int(x):02X}" for x in arr.flatten()) + "\n"
    else:
        mask = (1 << (4 * width_chars)) - 1
        buf = "\n".join(f"{int(x) & mask:0{width_chars}X}" for x in values) + "\n"
    with open(filepath, "w") as f:
        f.write(buf)


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
                return numpy_helper.to_array(init).astype(np.int8)
        for init in m.graph.initializer:
            if init.name == "fc1.weight":
                arr = numpy_helper.to_array(init)
                scale = 0.017854882
                arr_q = np.clip(np.round(arr / scale), -8, 7).astype(np.int8)
                return arr_q.T
    except Exception:
        return None
    return None


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["model", "random"], default="model")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = np.random.RandomState(args.seed)
    X = rng.randint(-128, 128, size=(M, K), dtype=np.int8)

    W = load_model_weights() if args.source == "model" else None
    if W is None:
        W = rng.randint(-8, 8, size=(K, N), dtype=np.int8)

    # Bit-accurate matrix multiplication: INT8 x INT4 -> INT32
    Y = np.matmul(X.astype(np.int32), W.astype(np.int32))

    # Bit-accurate fixed-point requantization for GeLU LUT (scale Sy = 1/32)
    # Mult M_REQ = 293, Shift = 16, round-to-nearest (+ 0x8000), saturated clamp
    scaled = np.right_shift((Y.astype(np.int64) * 293) + 0x8000, 16)
    Y_int8 = np.clip(scaled, -128, 127).astype(np.int8)

    w_words = pack_weights_bram_fast(W)
    act_lines = pack_act_lines_fast(X)

    # Self-check
    unpacked_w = unpack_weights_bram_fast(w_words)
    assert np.array_equal(unpacked_w, W), "FC1 BRAM packing self-check failed!"
    assert np.array_equal(np.matmul(X.astype(np.int32), unpacked_w.astype(np.int32)), Y)

    os.makedirs(OUT, exist_ok=True)
    batch_write_hex(f"{OUT}/act_fc1.hex", act_lines, width_chars=32)
    batch_write_hex(f"{OUT}/w_fc1.hex", w_words, width_chars=8)
    batch_write_hex(f"{OUT}/golden_fc1.hex", Y, width_chars=8)
    batch_write_hex(f"{OUT}/golden_fc1_int8.hex", Y_int8, width_chars=2)

    # Check tiles
    for g, k in CHECK_TILES:
        tile_w = W[k * T:(k + 1) * T, g * T:(g + 1) * T]
        batch_write_hex(f"{OUT}/exp_w_g{g}_k{k}.hex", pack_weights_bram_fast(np.pad(tile_w, ((0, 64-T), (0, 128-T))))[:32], width_chars=8)
        batch_write_hex(f"{OUT}/exp_act_k{k}.hex", act_lines[k * T:(k + 1) * T], width_chars=32)

    print(f"Vectorized FC1 export ({OUT}/): {len(act_lines)} act lines, {len(w_words)} weight words, {Y.size} golden words.")
