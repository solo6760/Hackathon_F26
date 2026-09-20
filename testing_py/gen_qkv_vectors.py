"""Vectorized Q/K/V vector generator (LSB-first INT4, tile-major uint32)."""


from __future__ import annotations

from pathlib import Path

import numpy as np

try:  # Support both direct execution and ``import testing_py...``.
    from .kera_fixed import matmul_accum, pack_int4, requantize, unpack_int4, write_memh
except ImportError:
    from kera_fixed import matmul_accum, pack_int4, requantize, unpack_int4, write_memh

D, T = 64, 16
K_TILES, GROUPS = D // T, D // T
OUT = "vectors_qkv"
ACC_BITS = 32
ACT_SCALE = 2.0 ** -5
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
    """Return D lines of M-byte words; token 0 is the least-significant byte."""
    activations = np.asarray(activations, dtype=np.int8)
    M_len, D_len = activations.shape
    if D_len != D:
        raise ValueError(f"expected D={D}, got {D_len}")
    return np.ascontiguousarray(activations.T[:, ::-1]).view(np.uint8)


def attention_index_scale(head_dim, activation_scale=ACT_SCALE):
    """Return reduced fixed multiplier for QK accum -> quarter-step LUT index."""
    factor = 4.0 * activation_scale * activation_scale / np.sqrt(head_dim)
    shift = 24
    multiplier = max(1, round(factor * (1 << shift)))
    while shift and multiplier % 2 == 0:
        multiplier //= 2
        shift -= 1
    return multiplier, shift


def softmax_lut_fixed(scores_int32, multiplier=1, shift=15):
    """Integer attention scaling, Q15 exp LUT, and integer normalization."""
    scores = np.asarray(scores_int32, dtype=np.int64)
    quarter_steps = requantize(
        scores, multiplier=multiplier, shift=shift, out_bits=32, rounding="half_up"
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


def load_trained_qkv_weights(checkpoint_path="testing_py/kera_sensor_fusion_trained.pt",
                             return_shifts=False):
    """Load trained [K,N] INT4 weights, preferring the lightweight NPZ export."""
    ckpt_file = Path(checkpoint_path)
    local_file = Path(__file__).resolve().parent / ckpt_file.name
    if not ckpt_file.exists() and local_file.exists():
        ckpt_file = local_file
    if not ckpt_file.exists():
        return None
    deploy_file = ckpt_file.with_suffix(".npz")
    if deploy_file.exists():
        with np.load(deploy_file) as deploy:
            weights = np.stack([deploy["w_q"], deploy["w_k"], deploy["w_v"]]).astype(np.int8)
            shifts = deploy["projection_shifts"].astype(np.int64)
    else:
        import torch

        ckpt = torch.load(ckpt_file, map_location="cpu")
        qw = ckpt["quantized_weights"]
        weights = np.stack([
            qw["w_q"].numpy().T, qw["w_k"].numpy().T, qw["w_v"].numpy().T
        ]).astype(np.int8)
        shifts = np.array([
            ckpt["requant_shifts"][key] for key in ("w_q", "w_k", "w_v")
        ], dtype=np.int64)
    return (weights, shifts) if return_shifts else weights


def generate_attention_vectors(seq_len=64, n_heads=1, seed=42,
                               checkpoint_path="testing_py/kera_sensor_fusion_trained.pt",
                               out_dir=OUT, allow_random=False):
    rng = np.random.RandomState(seed)
    M_len = seq_len
    H_len = n_heads
    DH_len = D // n_heads
    if D % n_heads:
        raise ValueError("D must be divisible by n_heads")
    attn_mult, attn_shift = attention_index_scale(DH_len)

    # 1. Load Input Activations X from ARES Trajectory
    try:
        try:
            from .sensor_fusion import embed_sensor_stream, generate_ares_trajectory
        except ImportError:
            from sensor_fusion import embed_sensor_stream, generate_ares_trajectory

        tokens, _ = embed_sensor_stream(
            generate_ares_trajectory(M_len, seed=seed), D, seed, as_numpy=True
        )
        activations = tokens[0]
    except ImportError:
        activations = rng.randint(-128, 128, size=(M_len, D), dtype=np.int8)

    # 2. Load Real Trained INT4 Weights from Checkpoint (or fallback to seeded)
    trained = load_trained_qkv_weights(checkpoint_path, return_shifts=True)
    if trained is not None:
        weights, projection_shifts = trained
        print(f"Loaded real trained Q/K/V weights from {checkpoint_path}")
    elif allow_random:
        print("Using seeded INT4 weights (checkpoint not found)")
        weights = rng.randint(-8, 8, size=(3, D, D), dtype=np.int8)
        projection_shifts = np.full(3, 6, dtype=np.int64)
    else:
        raise FileNotFoundError(f"trained checkpoint not found: {checkpoint_path}")

    packed = tuple(pack_weights_bram_fast(weight) for weight in weights)
    for name, words, weight in zip("QKV", packed, weights):
        if not np.array_equal(unpack_weights_bram_fast(words), weight):
            raise AssertionError(f"W_{name} BRAM pack round-trip failed")

    # 3. Hardware Integer Matrix Multiply (INT8 x INT4 -> INT32 accum)
    projections = np.stack([
        matmul_accum(activations, weight, bits=ACC_BITS, overflow="wrap") for weight in weights
    ])

    # Requantize to INT8 (>>> 6)
    projected_int8 = np.stack([
        requantize(projection, shift=int(shift), out_bits=8, rounding="half_up")
        for projection, shift in zip(projections, projection_shifts)
    ]).astype(np.int8)

    q_h, k_h, v_h = (
        value.reshape(M_len, H_len, DH_len).transpose(1, 0, 2) for value in projected_int8
    )

    # QK^T in INT32
    scores = matmul_accum(q_h, k_h.transpose(0, 2, 1), bits=ACC_BITS, overflow="wrap")
    probabilities = softmax_lut_fixed(scores, attn_mult, attn_shift)
    context = matmul_accum(probabilities, v_h, bits=ACC_BITS, overflow="wrap")

    out = Path(out_dir)
    for stem, words in zip(("w_q", "w_k", "w_v"), packed):
        write_memh(out / f"{stem}.hex", words, 32)
    _write_wide_memh(out / "act_in.hex", pack_act_lines_fast(activations))
    for stem, values in zip(("golden_q", "golden_k", "golden_v"), projections):
        write_memh(out / f"{stem}.hex", values, 32)
    for head in range(H_len):
        write_memh(out / f"golden_scores_h{head}.hex", scores[head], 32)
        write_memh(out / f"golden_probs_h{head}.hex", probabilities[head], 8)
        write_memh(out / f"golden_context_h{head}.hex", context[head], 32)

    print(f"Generated bit-accurate vectors in {out}/ (S={M_len} tokens, H={H_len} heads):")
    print(f"  weights: {packed[0].size} x 32-bit words/matrix, LSB-first INT4")
    print(f"  activations: {D} lines x {M_len * 8}-bit words")
    print(f"  projections: {projections[0].shape} INT32 accumulator words")
    print(f"  scores: {scores[0].shape} INT32 score matrix")
    print(f"  context: {context[0].shape} INT32 context output")
    return {
        "activations": activations,
        "weights": weights,
        "projections": projections,
        "projected_int8": projected_int8,
        "projection_shifts": projection_shifts,
        "scores": scores,
        "probabilities": probabilities,
        "context": context,
    }


if __name__ == "__main__":
    generate_attention_vectors(seq_len=64, n_heads=1)
