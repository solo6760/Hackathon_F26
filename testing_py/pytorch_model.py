import math
import torch
import torch.nn as nn
import numpy as np


def quantize_int4(tensor):
    max_val = torch.max(torch.abs(tensor))
    scale = max_val / 7.0 if max_val != 0 else 1.0
    return torch.clamp(torch.round(tensor / scale), -8, 7), scale


def quantize_int8(tensor):
    max_val = torch.max(torch.abs(tensor))
    scale = max_val / 127.0 if max_val != 0 else 1.0
    return torch.clamp(torch.round(tensor / scale), -128, 127), scale


GELU_SCALE = 1 / 32
gelu_table = []
for q_in in range(-128, 128):
    x = q_in * GELU_SCALE
    y = 0.5 * x * (1 + math.erf(x / math.sqrt(2)))
    gelu_table.append(max(-128, min(127, round(y / GELU_SCALE))))
GELU_LUT = torch.tensor(gelu_table, dtype=torch.int8)


def gelu_lut(x_int8, in_scale):
    x_float = x_int8.float() * in_scale
    x_q = torch.clamp(torch.round(x_float / GELU_SCALE), -128, 127).to(torch.int16)
    return GELU_LUT[(x_q + 128).long()], GELU_SCALE


EXP_STEP, EXP_MIN, EXP_MAX = 0.25, -8.0, 0.0
exp_table = []
x = EXP_MIN
while x <= EXP_MAX:
    exp_table.append(math.exp(x))
    x += EXP_STEP
EXP_LUT = torch.tensor(exp_table, dtype=torch.float32)


def softmax_lut(scores):
    max_value = torch.max(scores, dim=-1, keepdim=True).values
    shifted = torch.clamp(scores - max_value, EXP_MIN, EXP_MAX)
    index = torch.round((shifted - EXP_MIN) / EXP_STEP).long()
    exp_values = EXP_LUT.to(scores.device)[index]
    return exp_values / torch.sum(exp_values, dim=-1, keepdim=True)


class QuantizedLinear(nn.Module):
    def __init__(self, in_features, out_features):
        super().__init__()
        self.in_features = in_features
        self.out_features = out_features
        raw_w = torch.randn(out_features, in_features) * 0.1
        self.w_int4, self.w_scale = quantize_int4(raw_w)

    def forward(self, x_int8, in_scale):
        out_int32 = torch.matmul(x_int8.to(torch.int32), self.w_int4.t().to(torch.int32))
        effective_scale = in_scale * self.w_scale
        return quantize_int8(out_int32.float() * effective_scale)


class SmallTransformerBlock(nn.Module):
    def __init__(self, d_model=64, n_heads=2, d_mlp=128):
        super().__init__()
        self.d_model = d_model
        self.n_heads = n_heads
        self.head_dim = d_model // n_heads

        self.q_proj = QuantizedLinear(d_model, d_model)
        self.k_proj = QuantizedLinear(d_model, d_model)
        self.v_proj = QuantizedLinear(d_model, d_model)
        self.out_proj = QuantizedLinear(d_model, d_model)
        self.ffn1 = QuantizedLinear(d_model, d_mlp)
        self.ffn2 = QuantizedLinear(d_mlp, d_model)

    def forward(self, x_int8, x_scale):
        B, S, D = x_int8.shape

        q, q_scale = self.q_proj(x_int8, x_scale)
        k, k_scale = self.k_proj(x_int8, x_scale)
        v, v_scale = self.v_proj(x_int8, x_scale)

        q = q.view(B, S, self.n_heads, self.head_dim).transpose(1, 2)
        k = k.view(B, S, self.n_heads, self.head_dim).transpose(1, 2)
        v = v.view(B, S, self.n_heads, self.head_dim).transpose(1, 2)

        scores = torch.matmul(q.to(torch.int32), k.transpose(-2, -1).to(torch.int32))
        scaled_scores = scores.float() * (q_scale * k_scale) / np.sqrt(self.head_dim)
        attn_probs = softmax_lut(scaled_scores)
        attn_probs_int8, prob_scale = quantize_int8(attn_probs)

        context = torch.matmul(attn_probs_int8.to(torch.int32), v.to(torch.int32))
        context_float = (context.float() * (prob_scale * v_scale)).transpose(1, 2).contiguous().view(B, S, D)
        context_int8, c_scale = quantize_int8(context_float)

        attn_out, attn_scale = self.out_proj(context_int8, c_scale)
        x_post_attn = x_int8 + attn_out.to(torch.int8)

        ffn1_out, ffn1_scale = self.ffn1(x_post_attn, x_scale)
        gelu_out, gelu_scale = gelu_lut(ffn1_out, ffn1_scale)
        ffn2_out, ffn2_scale = self.ffn2(gelu_out, gelu_scale)

        return x_post_attn + ffn2_out.to(torch.int8)


if __name__ == "__main__":
    print("\n----- GeLU LUT TEST -----")
    gelu_errors = []
    for test_x in [-2.0, -1.0, 0.0, 1.0, 2.0]:
        exact = 0.5 * test_x * (1 + math.erf(test_x / math.sqrt(2)))
        q_in = max(-128, min(127, round(test_x / GELU_SCALE)))
        approximate = GELU_LUT[q_in + 128].item() * GELU_SCALE
        gelu_errors.append(abs(exact - approximate))
        print("Input:", test_x, "Exact:", exact, "LUT:", approximate)
    print("GeLU mean error:", sum(gelu_errors) / len(gelu_errors))
    print("GeLU max error:", max(gelu_errors))

    print("\n----- SOFTMAX LUT TEST -----")
    softmax_tests = [[2.0, 1.0, 0.0], [1.2, 0.3, -0.7], [3.1, 2.4, 1.8], [-1.0, -2.0, -3.0], [0.2, 0.1, 0.0]]
    softmax_errors = []
    for test_values in softmax_tests:
        scores = torch.tensor(test_values, dtype=torch.float32)
        exact = torch.softmax(scores, dim=-1)
        approximate = softmax_lut(scores)
        softmax_errors.extend(torch.abs(exact - approximate).tolist())
    print("Softmax mean error:", sum(softmax_errors) / len(softmax_errors))
    print("Softmax max error:", max(softmax_errors))

    print("\n----- FULL TRANSFORMER TEST -----")
    torch.manual_seed(42)
    model = SmallTransformerBlock(d_model=64, n_heads=2, d_mlp=128)
    dummy_input = torch.randn(1, 16, 64)
    dummy_int8, input_scale = quantize_int8(dummy_input)
    output = model(dummy_int8, input_scale)
    print("Model executed successfully. Output shape:", output.shape)
