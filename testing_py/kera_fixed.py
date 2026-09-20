"""Shared integer arithmetic, hex I/O, and metrics for the KERA RTL model."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import numpy as np

RoundingMode = Literal["half_up", "floor"]
OverflowMode = Literal["wrap", "saturate"]


def narrow_signed(values, bits: int, overflow: OverflowMode = "wrap") -> np.ndarray:
    """Narrow integers exactly like a signed ``bits``-wide RTL register."""
    if not 1 <= bits <= 64:
        raise ValueError("bits must be in [1, 64]")
    values = np.asarray(values, dtype=np.int64)
    if bits == 64:
        return values
    lo, hi = -(1 << (bits - 1)), (1 << (bits - 1)) - 1
    if overflow == "saturate":
        return np.clip(values, lo, hi)
    if overflow != "wrap":
        raise ValueError(f"unsupported overflow mode: {overflow}")
    mask = (1 << bits) - 1
    unsigned = np.bitwise_and(values, mask)
    return np.where(unsigned >= (1 << (bits - 1)), unsigned - (1 << bits), unsigned)


def requantize(
    values,
    *,
    multiplier: int = 1,
    shift: int = 0,
    out_bits: int = 8,
    rounding: RoundingMode = "half_up",
) -> np.ndarray:
    """Integer multiply/shift followed by signed saturation.

    ``half_up`` matches ``(x + 2**(shift-1)) >>> shift`` in RTL, including
    negative ties. ``floor`` is a plain arithmetic right shift (``>>>``).
    """
    if shift < 0:
        raise ValueError("shift must be non-negative")
    product = np.asarray(values, dtype=np.int64) * np.int64(multiplier)
    if shift:
        if rounding == "half_up":
            product = product + (1 << (shift - 1))
        elif rounding != "floor":
            raise ValueError(f"unsupported rounding mode: {rounding}")
        product = np.right_shift(product, shift)
    lo, hi = -(1 << (out_bits - 1)), (1 << (out_bits - 1)) - 1
    return np.clip(product, lo, hi)


def matmul_accum(lhs, rhs, *, bits: int = 32, overflow: OverflowMode = "wrap") -> np.ndarray:
    """Wide host matmul narrowed explicitly to the RTL accumulator width."""
    accum = np.matmul(np.asarray(lhs, dtype=np.int64), np.asarray(rhs, dtype=np.int64))
    return narrow_signed(accum, bits, overflow)


def pack_int4(values, word_bits: int = 32, *, lsb_first: bool = True) -> np.ndarray:
    """Pack signed INT4 values into 8/32/64-bit unsigned words without loops.

    LSB-first means input value 0 occupies word bits [3:0]. Padding, if needed,
    is appended at the high end of the final word.
    """
    if word_bits not in (8, 32, 64):
        raise ValueError("word_bits must be 8, 32, or 64")
    values = np.asarray(values)
    if np.any((values < -8) | (values > 7)):
        raise ValueError("INT4 values must be in [-8, 7]")
    per_word = word_bits // 4
    flat = np.bitwise_and(values.reshape(-1).astype(np.int64), 0xF).astype(np.uint64)
    padding = (-flat.size) % per_word
    if padding:
        flat = np.pad(flat, (0, padding))
    shifts = np.arange(per_word, dtype=np.uint64) * np.uint64(4)
    if not lsb_first:
        shifts = shifts[::-1]
    words = np.bitwise_or.reduce(np.left_shift(flat.reshape(-1, per_word), shifts), axis=1)
    return words.astype({8: np.uint8, 32: np.uint32, 64: np.uint64}[word_bits])


def unpack_int4(words, *, word_bits: int = 32, count: int | None = None,
                lsb_first: bool = True) -> np.ndarray:
    """Inverse of :func:`pack_int4`, including vectorized sign extension."""
    if word_bits not in (8, 32, 64):
        raise ValueError("word_bits must be 8, 32, or 64")
    per_word = word_bits // 4
    shifts = np.arange(per_word, dtype=np.uint64) * np.uint64(4)
    if not lsb_first:
        shifts = shifts[::-1]
    words = np.asarray(words, dtype=np.uint64).reshape(-1, 1)
    nibbles = np.bitwise_and(np.right_shift(words, shifts), 0xF).reshape(-1)
    if count is not None:
        nibbles = nibbles[:count]
    return np.where(nibbles >= 8, nibbles.astype(np.int16) - 16, nibbles).astype(np.int8)


def write_memh(path, values, bitwidth: int) -> None:
    """Batch-write one fixed-width word per line in ``$readmemh`` format."""
    if bitwidth <= 0 or bitwidth % 4:
        raise ValueError("bitwidth must be a positive multiple of four")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    width = bitwidth // 4
    mask = (1 << bitwidth) - 1
    flat = np.asarray(values).reshape(-1)
    # savetxt performs the line-oriented formatting in compiled NumPy code.
    if bitwidth <= 64:
        unsigned = flat.astype(np.uint64)
        if bitwidth < 64:
            unsigned = np.bitwise_and(unsigned, np.uint64(mask))
        np.savetxt(path, unsigned, fmt=f"%0{width}X")
    else:
        path.write_text("\n".join(f"{int(v) & mask:0{width}X}" for v in flat) + "\n")


def read_memh(path, *, bitwidth: int, signed: bool = True) -> np.ndarray:
    """Read whitespace-separated Verilator/``$readmemh`` words and comments."""
    if not 1 <= bitwidth <= 64:
        raise ValueError("read_memh supports bit widths in [1, 64]")
    text = Path(path).read_text()
    lines = (line.split("//", 1)[0].split("#", 1)[0] for line in text.splitlines())
    # $writememh may emit @<address> cursor directives. Dumps used here are
    # dense, so the directives carry no sample data and can be skipped.
    tokens = [
        token for token in " ".join(lines).replace("_", "").split()
        if not token.startswith("@")
    ]
    try:
        values = np.fromiter((int(token, 16) for token in tokens), dtype=np.uint64)
    except ValueError as exc:
        raise ValueError(f"invalid hex token in {path}: {exc}") from exc
    if bitwidth < 64:
        mask = np.uint64((1 << bitwidth) - 1)
        values = np.bitwise_and(values, mask)
    if not signed:
        return values
    sign = np.uint64(1 << (bitwidth - 1))
    signed_values = values.astype(np.int64)
    if bitwidth == 64:
        return signed_values
    return np.where(values & sign, signed_values - (1 << bitwidth), signed_values)


def error_metrics(reference, candidate, *, exact: bool = False) -> dict[str, float | int | bool]:
    """Return robust elementwise error metrics for equally shaped arrays."""
    ref = np.asarray(reference).reshape(-1)
    got = np.asarray(candidate).reshape(-1)
    if ref.size != got.size:
        raise ValueError(f"size mismatch: reference={ref.size}, candidate={got.size}")
    if not ref.size:
        raise ValueError("cannot compare empty arrays")
    ref64, got64 = ref.astype(np.float64), got.astype(np.float64)
    delta = ref64 - got64
    ref_norm, got_norm = np.linalg.norm(ref64), np.linalg.norm(got64)
    if ref_norm == 0.0 or got_norm == 0.0:
        cosine = 1.0 if np.array_equal(ref, got) else 0.0
    else:
        cosine = float(np.dot(ref64, got64) / (ref_norm * got_norm))
    result: dict[str, float | int | bool] = {
        "elements": int(ref.size),
        "mae": float(np.mean(np.abs(delta))),
        "rmse": float(np.sqrt(np.mean(delta * delta))),
        "max_abs_error": float(np.max(np.abs(delta))),
        "cosine_similarity": cosine,
    }
    if exact:
        mismatches = int(np.count_nonzero(ref != got))
        result.update({
            "bitwise_mismatches": mismatches,
            "mismatch_percent": 100.0 * mismatches / ref.size,
            "bit_accurate": mismatches == 0,
        })
    return result
