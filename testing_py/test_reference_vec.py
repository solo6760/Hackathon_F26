"""Generate GEMM vectors and compare raw RTL dumps with the integer golden."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

try:  # Support both direct execution and ``import testing_py...``.
    from .kera_fixed import error_metrics, matmul_accum, pack_int4, read_memh, unpack_int4, write_memh
except ImportError:
    from kera_fixed import error_metrics, matmul_accum, pack_int4, read_memh, unpack_int4, write_memh


def pack_int4_to_uint32_lsb(weights_int4):
    """Pack signed INT4 values; value 0 goes to word[3:0] (LSB-first)."""
    return pack_int4(weights_int4, word_bits=32, lsb_first=True)


def unpack_uint32_to_int4_lsb(words_uint32, count=None):
    return unpack_int4(words_uint32, word_bits=32, count=count, lsb_first=True)


def load_rtl_hex(filepath, bitwidth=32, is_signed=True):
    """Load a whitespace-separated Verilator/RTL hex dump."""
    path = Path(filepath)
    return read_memh(path, bitwidth=bitwidth, signed=is_signed) if path.exists() else None


def compare_golden_vs_rtl(golden, rtl):
    """Compute exact mismatches plus magnitude and directional error metrics."""
    return error_metrics(golden, rtl, exact=True)


def generate_tile_vectors(M=16, K=16, N=16, seed=42, out_dir="."):
    rng = np.random.RandomState(seed)
    act_int8 = rng.randint(-128, 128, size=(M, K), dtype=np.int8)
    weights_int4 = rng.randint(-8, 8, size=(K, N), dtype=np.int8)
    golden_out = matmul_accum(act_int8, weights_int4, bits=32, overflow="wrap").astype(np.int32)

    out = Path(out_dir)
    write_memh(out / "act_tile.hex", act_int8, 8)
    packed_words = pack_int4_to_uint32_lsb(weights_int4)
    write_memh(out / "weights_bram.hex", packed_words, 32)
    write_memh(out / "golden_out.hex", golden_out, 32)

    unpacked = unpack_uint32_to_int4_lsb(packed_words, weights_int4.size).reshape(K, N)
    if not np.array_equal(unpacked, weights_int4):
        raise AssertionError("LSB-first INT4 pack/unpack round-trip failed")
    return act_int8, weights_int4, golden_out


def _print_report(report):
    for name, value in report.items():
        print(f"  {name:<22}: {value}")


def main():
    parser = argparse.ArgumentParser(description="GEMM vector generator and RTL dump verifier")
    parser.add_argument("--rtl-dump", type=Path, help="Verilator/RTL output hex")
    parser.add_argument("--rtl-bitwidth", type=int, default=32)
    parser.add_argument("--unsigned-rtl", action="store_true")
    parser.add_argument("--out-dir", type=Path, default=Path("."))
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    act, weights, golden = generate_tile_vectors(seed=args.seed, out_dir=args.out_dir)
    print("Generated M=16, K=16, N=16 vectors:")
    print(f"  act_tile.hex     : {act.size} INT8 words")
    print(f"  weights_bram.hex : {weights.size // 8} uint32 words (LSB-first nibbles)")
    print(f"  golden_out.hex   : {golden.size} INT32 words ({golden.min()}..{golden.max()})")

    if args.rtl_dump:
        rtl = load_rtl_hex(args.rtl_dump, args.rtl_bitwidth, not args.unsigned_rtl)
        if rtl is None:
            parser.error(f"RTL dump does not exist: {args.rtl_dump}")
        print("\nRTL vs quantized Python golden:")
        _print_report(compare_golden_vs_rtl(golden, rtl))


if __name__ == "__main__":
    main()
