"""Vectorized, bit-accurate Q/K/V and attention vector generation.

INT4 weights use LSB-first nibble order: the first logical weight occupies
word[3:0], the second word[7:4], and so on. Weight words are tile-major.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

try:  # Support both direct execution and ``import testing_py...``.
    from .kera_fixed import matmul_accum, pack_int4, requantize, unpack_int4, write_memh
except ImportError:
    from kera_fixed import matmul_accum, pack_int4, requantize, unpack_int4, write_memh

M, D, H, DH, T = 16, 64, 2, 32, 16
K_TILES, GROUPS = D // T, D // T
OUT = "vectors_qkv"
ACC_BITS = 32
PROJ_SHIFT = 6
ATTN_MULT, ATTN_SHIFT = 45, 6  # quarter-step index: (1/sqrt(32)) * 4 ~= 45/64
EXP_Q_BITS = 15
EXP_LUT_Q15 = np.floor(
    np.exp(np.arange(-32, 1) / 4.0) * ((1 << EXP_Q_BITS) - 1) + 0.5
).astype(np.int32)


def pack_weights_bram_fast(weights):
    """Pack a (64, 64) matrix into tile-major uint32 BRAM words."""
    weights = np.asarray(weights, dtype=np.int8)
    if weights.shape != (D, D):
        raise ValueError(f"expected ({D}, {D}), got {weights.shape}")
    tiled = weights.reshape(K_TILES, T, GROUPS, T).transpose(2, 0, 1, 3)
    return pack_int4(tiled, word_bits=32, lsb_first=True)


def unpack_weights_bram_fast(words, K=D, N=D):
    """Unpack tile-major uint32 BRAM words to a (K, N) matrix."""
    if K % T or N % T:
        raise ValueError("K and N must be multiples of the tile size")
    tiled = unpack_int4(words, word_bits=32, count=K * N).reshape(N // T, K // T, T, T)
    return tiled.transpose(1, 2, 0, 3).reshape(K, N)


def pack_act_lines_fast(activations):
    """Return 64 128-bit words; token 0 is the least-significant byte."""
    activations = np.asarray(activations, dtype=np.int8)
    if activations.shape != (M, D):
        raise ValueError(f"expected ({M}, {D}), got {activations.shape}")
    return np.ascontiguousarray(activations.T[:, ::-1]).view(np.uint8)


def softmax_lut_fixed(scores_int32):
    """Integer attention scaling, Q15 exp LUT, and integer normalization."""
    scores = np.asarray(scores_int32, dtype=np.int64)
    quarter_steps = requantize(
        scores, multiplier=ATTN_MULT, shift=ATTN_SHIFT, out_bits=32, rounding="half_up"
    )
    delta = quarter_steps - np.max(quarter_steps, axis=-1, keepdims=True)
    lut_index = np.clip(delta, -32, 0).astype(np.intp) + 32
    exponent = EXP_LUT_Q15[lut_index].astype(np.int64)
    denominator = np.sum(exponent, axis=-1, keepdims=True, dtype=np.int64)
    # Integer division mirrors an RTL normalizer; denominator/2 rounds half-up.
    return np.clip((exponent * 127 + denominator // 2) // denominator, 0, 127).astype(np.int8)


def _write_wide_memh(path, byte_rows):
    rows = np.asarray(byte_rows, dtype=np.uint8)
    text = "\n".join(row.tobytes().hex().upper() for row in rows) + "\n"
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def generate_attention_vectors(seed=42, out_dir=OUT):
    rng = np.random.RandomState(seed)
    try:
        try:
            from .sensor_fusion import embed_sensor_stream, generate_ares_trajectory
        except ImportError:
            from sensor_fusion import embed_sensor_stream, generate_ares_trajectory

        tokens, _ = embed_sensor_stream(
            generate_ares_trajectory(M, seed=seed), D, seed, as_numpy=True
        )
        activations = tokens[0]
    except ImportError:
        activations = rng.randint(-128, 128, size=(M, D), dtype=np.int8)

    weights = rng.randint(-8, 8, size=(3, D, D), dtype=np.int8)
    packed = tuple(pack_weights_bram_fast(weight) for weight in weights)
    for name, words, weight in zip("QKV", packed, weights):
        if not np.array_equal(unpack_weights_bram_fast(words), weight):
            raise AssertionError(f"W_{name} BRAM pack round-trip failed")

    # Wide host operations avoid accidental overflow; explicitly narrow every
    # accumulator result to the signed 32-bit RTL register.
    projections = np.stack([
        matmul_accum(activations, weight, bits=ACC_BITS, overflow="wrap") for weight in weights
    ])
    projected_int8 = requantize(
        projections, shift=PROJ_SHIFT, out_bits=8, rounding="half_up"
    ).astype(np.int8)
    q_h, k_h, v_h = (
        value.reshape(M, H, DH).transpose(1, 0, 2) for value in projected_int8
    )
    scores = matmul_accum(q_h, k_h.transpose(0, 2, 1), bits=ACC_BITS, overflow="wrap")
    probabilities = softmax_lut_fixed(scores)
    context = matmul_accum(probabilities, v_h, bits=ACC_BITS, overflow="wrap")

    out = Path(out_dir)
    for stem, words in zip(("w_q", "w_k", "w_v"), packed):
        write_memh(out / f"{stem}.hex", words, 32)
    _write_wide_memh(out / "act_in.hex", pack_act_lines_fast(activations))
    for stem, values in zip(("golden_q", "golden_k", "golden_v"), projections):
        write_memh(out / f"{stem}.hex", values, 32)
    for head in range(H):
        write_memh(out / f"golden_scores_h{head}.hex", scores[head], 32)
        write_memh(out / f"golden_probs_h{head}.hex", probabilities[head], 8)
        write_memh(out / f"golden_context_h{head}.hex", context[head], 32)

    print(f"Generated bit-accurate vectors in {out}/")
    print(f"  weights: {packed[0].size} x 32-bit words/matrix, LSB-first INT4")
    print(f"  activations: {D} x {M * 8}-bit words, token 0 in bits [7:0]")
    print(f"  attention: {H} heads, integer quarter-step scale {ATTN_MULT}/2^{ATTN_SHIFT}")
    return {
        "activations": activations,
        "weights": weights,
        "projections": projections,
        "projected_int8": projected_int8,
        "scores": scores,
        "probabilities": probabilities,
        "context": context,
    }


if __name__ == "__main__":
    generate_attention_vectors()
