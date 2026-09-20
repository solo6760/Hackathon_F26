"""Bit-accurate PyTorch reference model and RTL pipeline simulator."""


import math
import numpy as np
import torch
import torch.nn as nn

GELU_SCALE = 1.0 / 32.0  # 2^(-5)
EXP_STEP, EXP_MIN, EXP_MAX = 0.25, -8.0, 0.0
ACT_SCALE = 1.0 / 32.0
ACC_BITS = 32


def attention_index_scale(head_dim, activation_scale=ACT_SCALE):
    """Fixed multiplier for converting QK accumulators to quarter-step LUT indices."""
    factor = 4.0 * activation_scale * activation_scale / math.sqrt(head_dim)
    shift = 24
    multiplier = max(1, round(factor * (1 << shift)))
    while shift and multiplier % 2 == 0:
        multiplier //= 2
        shift -= 1
    return multiplier, shift


def quantize_int4_weights(weight_tensor):
    """Symmetric INT4 quantization with an exactly representable power-of-two scale."""
    max_val = torch.max(torch.abs(weight_tensor))
    scale = 2.0 ** math.ceil(math.log2(max_val.item() / 7.0)) if max_val != 0 else 1.0
    q = torch.clamp(torch.floor(weight_tensor / scale + 0.5), -8, 7).to(torch.int8)
    return q, scale


def quantize_int8_act(act_tensor, scale=ACT_SCALE):
    """Symmetric INT8 quantization using the calibrated Q3.5 activation scale."""
    q = torch.clamp(torch.floor(act_tensor / scale + 0.5), -128, 127).to(torch.int8)
    return q, scale


# 1. Hardware GeLU LUT (256 entries, step 1/32 = 0.03125)
gelu_table = []
for q_in in range(-128, 128):
    x = q_in * GELU_SCALE
    y = 0.5 * x * (1.0 + math.erf(x / math.sqrt(2.0)))
    gelu_table.append(max(-128, min(127, math.floor(y / GELU_SCALE + 0.5))))
GELU_LUT = torch.tensor(gelu_table, dtype=torch.int8)


def gelu_lut_rtl(x_int8):
    """Bit-accurate RTL GeLU lookup: table index = input + 128."""
    idx = (x_int8.to(torch.int16) + 128).clamp(0, 255).long()
    return GELU_LUT[idx]


# 2. Hardware Exponential Softmax LUT (33 entries, step 0.25 = 2^(-2))
EXP_LUT_Q15 = torch.tensor(
    [math.floor(math.exp(EXP_MIN + i * EXP_STEP) * 32767 + 0.5) for i in range(33)],
    dtype=torch.int64,
)


def softmax_lut_rtl(scores_int32, multiplier=1, shift=15):
    """Integer score scaling, Q15 exponential lookup, and integer normalization."""
    quarter_steps = requantize_rtl(
        scores_int32, mult=multiplier, shift=shift, out_bits=32
    ).to(torch.int64)
    delta = quarter_steps - torch.max(quarter_steps, dim=-1, keepdim=True).values
    idx = torch.clamp(delta, -32, 0).long() + 32
    exp_vals = EXP_LUT_Q15.to(scores_int32.device)[idx]
    denominator = torch.sum(exp_vals, dim=-1, keepdim=True)
    return torch.clamp((exp_vals * 127 + denominator // 2) // denominator, 0, 127).to(torch.int8)


# 3. Requantization Unit (Emulates hardware rounding, shift, and saturation)
def requantize_rtl(accum, mult=None, shift=16, round_nearest=True, out_bits=8):
    """RTL ``multiply + optional half + >>> shift`` followed by saturation.

    ``round_nearest=False`` is an arithmetic shift (floor for negatives), not
    C-style truncation toward zero. This distinction is explicit for RTL parity.
    """
    if shift < 0:
        raise ValueError("shift must be non-negative")
    scaled = accum.to(torch.int64) * (1 if mult is None else mult)
    if shift:
        if round_nearest:
            scaled = scaled + (1 << (shift - 1))
        scaled = scaled >> shift
    lo, hi = -(1 << (out_bits - 1)), (1 << (out_bits - 1)) - 1
    dtype = torch.int8 if out_bits <= 8 else torch.int32
    return torch.clamp(scaled, lo, hi).to(dtype)


def narrow_accumulator_rtl(accum, bits=ACC_BITS):
    """Apply signed two's-complement wrapping at the accumulator register."""
    mask = (1 << bits) - 1
    value = torch.bitwise_and(accum.to(torch.int64), mask)
    return torch.where(value >= (1 << (bits - 1)), value - (1 << bits), value).to(torch.int32)


# 4. Bit-Accurate Quantized Linear Layer
class QuantizedLinearRTL(nn.Module):
    def __init__(self, in_features, out_features, req_mult=293, req_shift=16):
        super().__init__()
        self.in_features = in_features
        self.out_features = out_features
        self.req_mult = req_mult
        self.req_shift = req_shift

        # Random init and quantize to INT4
        raw_w = torch.randn(out_features, in_features) * 0.1
        w_int4, self.w_scale = quantize_int4_weights(raw_w)
        self.register_buffer("w_fp32", raw_w)
        self.register_buffer("w_int4", w_int4)

    def forward_rtl(self, x_int8):
        """Strict hardware integer datapath: INT8 x INT4 -> INT32 accum -> requantize INT8."""
        # Matrix multiply in INT32: (B, S, in_features) x (in_features, out_features)
        # Target dimensions are bounded far below INT32 overflow; using INT32
        # is both cycle-faithful and substantially faster than host INT64 GEMM.
        accum = torch.matmul(x_int8.to(torch.int32), self.w_int4.t().to(torch.int32))
        accum_int32 = narrow_accumulator_rtl(accum)
        # Fixed-point requantization unit
        return requantize_rtl(accum_int32, mult=self.req_mult, shift=self.req_shift)

    def forward_fp32(self, x_fp32):
        """Unquantized floating-point reference."""
        return torch.matmul(x_fp32, self.w_fp32.t())


# 5. Full Transformer Block (Side-by-side RTL and FP32)
class SmallTransformerBlockRTL(nn.Module):
    def __init__(self, d_model=64, n_heads=1, d_mlp=128):
        super().__init__()
        self.d_model = d_model
        self.n_heads = n_heads
        self.head_dim = d_model // n_heads
        if d_model % n_heads:
            raise ValueError("d_model must be divisible by n_heads")
        self.attn_mult, self.attn_shift = attention_index_scale(self.head_dim)

        # Requantization shifts are derived from power-of-two weight scales
        # below, then replaced by the exported shifts when a checkpoint loads.
        self.q_proj = QuantizedLinearRTL(d_model, d_model, req_mult=None, req_shift=0)
        self.k_proj = QuantizedLinearRTL(d_model, d_model, req_mult=None, req_shift=0)
        self.v_proj = QuantizedLinearRTL(d_model, d_model, req_mult=None, req_shift=0)
        self.out_proj = QuantizedLinearRTL(d_model, d_model, req_mult=None, req_shift=0)
        self.ffn1 = QuantizedLinearRTL(d_model, d_mlp, req_mult=None, req_shift=0)
        self.ffn2 = QuantizedLinearRTL(d_mlp, d_model, req_mult=None, req_shift=0)
        # Random-model defaults are also scale-consistent; checkpoint loading
        # replaces these with its exported per-layer shifts.
        for layer in (self.q_proj, self.k_proj, self.v_proj, self.out_proj):
            layer.req_shift = int(round(-math.log2(layer.w_scale)))
        self.ffn1.req_mult = None
        self.ffn1.req_shift = int(round(-math.log2(self.ffn1.w_scale))) + 2
        self.ffn2.req_shift = int(round(-math.log2(self.ffn2.w_scale))) - 2

    def load_trained_checkpoint(self, checkpoint_path="testing_py/kera_sensor_fusion_trained.pt"):
        from pathlib import Path

        checkpoint_path = Path(checkpoint_path)
        if not checkpoint_path.exists():
            return False
        ckpt = torch.load(checkpoint_path, map_location="cpu")
        config = ckpt["config"]
        expected = (self.d_model, self.n_heads)
        actual = (config["d_model"], config["n_heads"])
        if actual != expected:
            raise ValueError(f"checkpoint model/head dimensions {actual} do not match {expected}")
        shifts = ckpt["requant_shifts"]
        scales = ckpt["scales"]
        qw = ckpt["quantized_weights"]
        sd = ckpt["model_state_dict"]
        for key, layer, state_key in (
            ("w_q", self.q_proj, "q_proj.weight"),
            ("w_k", self.k_proj, "k_proj.weight"),
            ("w_v", self.v_proj, "v_proj.weight"),
            ("w_out", self.out_proj, "out_proj.weight"),
            ("w_ffn1", self.ffn1, "ffn1.weight"),
            ("w_ffn2", self.ffn2, "ffn2.weight"),
        ):
            layer.w_int4.copy_(qw[key])
            layer.w_fp32.copy_(sd[state_key])
            layer.w_scale = scales[key]
            layer.req_mult = None
            layer.req_shift = shifts[key]
        return True

    def forward_rtl(self, x_int8):
        """Cycle- and bit-accurate execution of the full KERA hardware pipeline."""
        B, S, D = x_int8.shape

        # 1. Q, K, V Projections (INT8 in, INT4 weights, INT8 out)
        q = self.q_proj.forward_rtl(x_int8)
        k = self.k_proj.forward_rtl(x_int8)
        v = self.v_proj.forward_rtl(x_int8)

        # 2. Multi-head split: (B, H, S, head_dim)
        q_h = q.view(B, S, self.n_heads, self.head_dim).transpose(1, 2)
        k_h = k.view(B, S, self.n_heads, self.head_dim).transpose(1, 2)
        v_h = v.view(B, S, self.n_heads, self.head_dim).transpose(1, 2)

        # 3. Scaled dot-product: QK^T in INT32
        scores_int32 = narrow_accumulator_rtl(
            torch.matmul(q_h.to(torch.int32), k_h.transpose(-2, -1).to(torch.int32))
        )

        # 4. Softmax LUT -> INT8 probabilities [0, 127]
        probs = softmax_lut_rtl(scores_int32, self.attn_mult, self.attn_shift)

        # 5. Context accumulation: P x V in INT32 -> requantize to INT8 (>>> 7)
        context_int32 = narrow_accumulator_rtl(
            torch.matmul(probs.to(torch.int32), v_h.to(torch.int32))
        )
        context_int8 = requantize_rtl(context_int32, mult=None, shift=7)
        context_merged = context_int8.transpose(1, 2).contiguous().view(B, S, D)

        # 6. Attention Out Projection + Residual 1
        attn_out = self.out_proj.forward_rtl(context_merged)
        x_post_attn = torch.clamp(x_int8.to(torch.int16) + attn_out.to(torch.int16), -128, 127).to(torch.int8)

        # 7. FFN1 -> GeLU LUT -> FFN2 + Residual 2
        ffn1_out = self.ffn1.forward_rtl(x_post_attn)
        gelu_out = gelu_lut_rtl(ffn1_out)
        ffn2_out = self.ffn2.forward_rtl(gelu_out)
        out = torch.clamp(x_post_attn.to(torch.int16) + ffn2_out.to(torch.int16), -128, 127).to(torch.int8)

        return out

    def forward_fp32(self, x_fp32):
        """Unquantized floating-point reference forward pass."""
        B, S, D = x_fp32.shape
        q = self.q_proj.forward_fp32(x_fp32).view(B, S, self.n_heads, self.head_dim).transpose(1, 2)
        k = self.k_proj.forward_fp32(x_fp32).view(B, S, self.n_heads, self.head_dim).transpose(1, 2)
        v = self.v_proj.forward_fp32(x_fp32).view(B, S, self.n_heads, self.head_dim).transpose(1, 2)

        scores = torch.matmul(q, k.transpose(-2, -1)) / math.sqrt(self.head_dim)
        probs = torch.softmax(scores, dim=-1)
        context = torch.matmul(probs, v).transpose(1, 2).contiguous().view(B, S, D)

        attn_out = self.out_proj.forward_fp32(context)
        x_post_attn = x_fp32 + attn_out

        ffn1_out = self.ffn1.forward_fp32(x_post_attn)
        # Exact GeLU
        gelu_out = 0.5 * ffn1_out * (1.0 + torch.erf(ffn1_out / math.sqrt(2.0)))
        ffn2_out = self.ffn2.forward_fp32(gelu_out)
        return x_post_attn + ffn2_out


def evaluate_numerical_fidelity(model, dummy_input_fp32):
    """Computes MAE, Max Error, and Cosine Similarity between FP32 baseline and bit-accurate RTL."""
    model.eval()
    with torch.no_grad():
        out_fp32 = model.forward_fp32(dummy_input_fp32)
        # Quantize input to INT8
        x_int8, in_scale = quantize_int8_act(dummy_input_fp32, scale=ACT_SCALE)
        out_rtl_int8 = model.forward_rtl(x_int8)

        # Dequantize RTL output for fair comparison
        out_rtl_fp = out_rtl_int8.float() * in_scale

        flat_fp32 = out_fp32.flatten().numpy()
        flat_rtl = out_rtl_fp.flatten().numpy()

        mae = float(np.mean(np.abs(flat_fp32 - flat_rtl)))
        max_err = float(np.max(np.abs(flat_fp32 - flat_rtl)))
        denominator = np.linalg.norm(flat_fp32) * np.linalg.norm(flat_rtl)
        cos_sim = float(np.dot(flat_fp32, flat_rtl) / denominator) if denominator else 0.0

        return {
            "mae": mae,
            "max_err": max_err,
            "cosine_sim": cos_sim,
            "rtl_out_range": (int(out_rtl_int8.min()), int(out_rtl_int8.max()))
        }


if __name__ == "__main__":
    torch.manual_seed(42)
    # Proposal target: S=64 tokens, H=1 single attention head, D=64, d_mlp=128
    model = SmallTransformerBlockRTL(d_model=64, n_heads=1, d_mlp=128)
    loaded = model.load_trained_checkpoint("testing_py/kera_sensor_fusion_trained.pt")
    if loaded:
        print("Loaded real trained weights from testing_py/kera_sensor_fusion_trained.pt")

    try:
        from .sensor_fusion import embed_sensor_stream, generate_ares_trajectory
    except ImportError:
        from sensor_fusion import embed_sensor_stream, generate_ares_trajectory
    sensor_tokens, _ = embed_sensor_stream(generate_ares_trajectory(64, seed=999), 64, seed=42)
    dummy_in = sensor_tokens.float() * ACT_SCALE

    metrics = evaluate_numerical_fidelity(model, dummy_in)
    print("Bit-Accurate RTL Model vs FP32 Baseline (S=64 tokens, H=1 head):")
    print(f"  Mean Absolute Error (MAE): {metrics['mae']:.5f}")
    print(f"  Max Absolute Error       : {metrics['max_err']:.5f}")
    print(f"  Cosine Similarity        : {metrics['cosine_sim']:.5f}")
    print(f"  RTL Output Range (INT8)  : {metrics['rtl_out_range'][0]} to {metrics['rtl_out_range'][1]}")
