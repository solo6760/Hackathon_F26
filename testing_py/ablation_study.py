"""KERA precision/streaming ablation and three-tier RTL verification."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np

try:  # Support both direct execution and ``import testing_py...``.
    from .kera_fixed import error_metrics, matmul_accum, read_memh
except ImportError:
    from kera_fixed import error_metrics, matmul_accum, read_memh


def load_hex_dump(filepath, bitwidth=32, is_signed=True):
    path = Path(filepath)
    return read_memh(path, bitwidth=bitwidth, signed=is_signed) if path.exists() else None


def _pow2_quantize(values, qmin, qmax):
    """Quantize with a shift-compatible, per-tensor power-of-two scale."""
    values = np.asarray(values, dtype=np.float64)
    peak = float(np.max(np.abs(values)))
    scale = 1.0 if peak == 0.0 else 2.0 ** math.ceil(math.log2(peak / qmax))
    quantized = np.clip(np.floor(values / scale + 0.5), qmin, qmax).astype(np.int8)
    return quantized, scale


def compute_metrics(ref_fp32, quant_ref, rtl_sim=None, *, quant_scale=1.0):
    """Compare FP32, integer Python, and RTL in their correct numeric domains."""
    reports = {}
    quant = np.asarray(quant_ref)
    quant_real = quant.astype(np.float64) * quant_scale
    if ref_fp32 is not None:
        reports["FP32_vs_Quant"] = error_metrics(ref_fp32, quant_real)
    if rtl_sim is not None:
        rtl = np.asarray(rtl_sim)
        reports["Quant_vs_RTL"] = error_metrics(quant, rtl, exact=True)
        if ref_fp32 is not None:
            reports["FP32_vs_RTL"] = error_metrics(
                ref_fp32, rtl.astype(np.float64) * quant_scale
            )
    return reports


def run_ablation_model(seq_len=64, d_model=64, n_heads=1, d_mlp=128, seed=42, return_vectors=False):
    total_weights = 4 * d_model * d_model + 2 * d_model * d_mlp
    weight_kb = {"A": total_weights / 1024.0, "B": total_weights / 2048.0}
    bram = {
        "A": math.ceil(total_weights * 8 / 36864),
        "B": math.ceil(total_weights * 4 / 36864),
    }

    # MAC counts scaled to seq_len
    total_macs = seq_len * (4 * d_model * d_model + 2 * d_model * d_mlp + d_model * seq_len + seq_len * d_model)
    mac_cycles = (total_macs + 255) // 256

    # Dynamic buffer footprint (Bytes):
    # Materialized (Config A & B) must store the full S x S INT32 score matrix and INT8 prob matrix
    score_matrix_bytes = n_heads * seq_len * seq_len * 4  # INT32
    prob_matrix_bytes = n_heads * seq_len * seq_len * 1   # INT8
    act_buffer_bytes = seq_len * d_model * 5 + seq_len * d_mlp
    peak_buf_materialized = act_buffer_bytes + score_matrix_bytes + prob_matrix_bytes

    # Tiled (Config C - KERA) streams T x T tiles (16x16) and only maintains online softmax running state
    online_softmax_state_bytes = 2 * seq_len * 4  # running max and running sum
    tile_buf_bytes = 16 * 16 * 4                  # INT32 tile
    peak_buf_tiled = act_buffer_bytes + online_softmax_state_bytes + tile_buf_bytes

    # Memory traffic (Bytes):
    # Projections and FFN: seq_len * d_model * 10
    base_act_traffic = seq_len * d_model * 10
    # Config A & B write and read the intermediate S x S score matrix
    traffic_tiled = total_weights * 0.5 + base_act_traffic  # eliminates intermediate score matrix traffic

    rng = np.random.default_rng(seed)
    x_fp = rng.standard_normal((seq_len, d_model), dtype=np.float32)
    w_fp = (rng.standard_normal((d_model, d_mlp), dtype=np.float32) * 0.1).astype(np.float32)
    y_fp = x_fp @ w_fp
    x_q, x_scale = _pow2_quantize(x_fp, -128, 127)
    w8_q, w8_scale = _pow2_quantize(w_fp, -128, 127)
    w4_q, w4_scale = _pow2_quantize(w_fp, -8, 7)
    y8_acc = matmul_accum(x_q, w8_q, bits=32, overflow="wrap").astype(np.int32)
    y4_acc = matmul_accum(x_q, w4_q, bits=32, overflow="wrap").astype(np.int32)
    mae8 = error_metrics(y_fp, y8_acc * (x_scale * w8_scale))["mae"]
    mae4 = error_metrics(y_fp, y4_acc * (x_scale * w4_scale))["mae"]

    results = {
        "A": {"w_kb": weight_kb["A"], "bram": bram["A"], "buf": peak_buf_materialized,
              "traffic": total_weights * 1.0 + base_act_traffic + 2 * score_matrix_bytes,
              "cycles": mac_cycles + 768, "mae": mae8},
        "B": {"w_kb": weight_kb["B"], "bram": bram["B"], "buf": peak_buf_materialized,
              "traffic": total_weights * 0.5 + base_act_traffic + 2 * score_matrix_bytes,
              "cycles": mac_cycles + 512, "mae": mae4},
        "C": {"w_kb": weight_kb["B"], "bram": bram["B"], "buf": peak_buf_tiled,
              "traffic": traffic_tiled,
              "cycles": mac_cycles + 128, "mae": mae4},
    }
    if return_vectors:
        return results, {"fp32": y_fp, "quant": y4_acc, "scale": x_scale * w4_scale}
    return results


def _print_metrics(reports):
    for tier, report in reports.items():
        print(f"[{tier}]")
        for name, value in report.items():
            print(f"  {name:<22}: {value}")


def main():
    parser = argparse.ArgumentParser(description="KERA ablation and RTL dump verification")
    parser.add_argument("--rtl-dump", type=Path, help="raw Verilator/RTL output hex")
    parser.add_argument("--quant-hex", "--golden-hex", dest="quant_hex", type=Path,
                        help="integer Python golden corresponding to the RTL dump")
    parser.add_argument("--fp32-npy", type=Path,
                        help="optional FP32 baseline array corresponding to the dump")
    parser.add_argument("--quant-scale", type=float, default=1.0,
                        help="real-value scale for integer golden/RTL outputs")
    parser.add_argument("--rtl-bitwidth", type=int, default=32)
    parser.add_argument("--unsigned-rtl", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    results, generated = run_ablation_model(seed=args.seed, return_vectors=True)
    print("KERA THREE-WAY ABLATION")
    print(f"{'Metric':<30} {'A: INT8':>14} {'B: INT4':>14} {'C: KERA':>14}")
    for label, key, fmt in (
        ("Weight storage (KiB)", "w_kb", ".1f"),
        ("BRAM36K count", "bram", ".0f"),
        ("Peak buffer (bytes)", "buf", ".0f"),
        ("Memory traffic (bytes)", "traffic", ".0f"),
        ("Latency (cycles)", "cycles", ".0f"),
        ("MAE vs FP32", "mae", ".6f"),
    ):
        vals = [format(results[cfg][key], fmt) for cfg in "ABC"]
        print(f"{label:<30} {vals[0]:>14} {vals[1]:>14} {vals[2]:>14}")

    if args.rtl_dump:
        rtl = load_hex_dump(args.rtl_dump, args.rtl_bitwidth, not args.unsigned_rtl)
        if rtl is None:
            parser.error(f"RTL dump does not exist: {args.rtl_dump}")
        if args.quant_hex:
            quant = load_hex_dump(args.quant_hex, args.rtl_bitwidth, not args.unsigned_rtl)
            fp32 = np.load(args.fp32_npy) if args.fp32_npy else None
            scale = args.quant_scale
        else:
            quant, fp32, scale = generated["quant"], generated["fp32"], generated["scale"]
        print("\nTHREE-TIER NUMERICAL VERIFICATION")
        _print_metrics(compute_metrics(fp32, quant, rtl, quant_scale=scale))


if __name__ == "__main__":
    main()
