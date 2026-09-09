import torch
import torch.nn as nn
import numpy as np

# 1. Quantization Helpers
def quantize_int4(tensor):
    """Symmetric per-tensor INT4 quantization: maps values to [-8, 7]."""
    max_val = torch.max(torch.abs(tensor))
    scale = max_val / 7.0 if max_val != 0 else 1.0
    q_tensor = torch.clamp(torch.round(tensor / scale), -8, 7)
    return q_tensor, scale

def quantize_int8(tensor):
    """Symmetric per-tensor INT8 quantization: maps values to [-128, 127]."""
    max_val = torch.max(torch.abs(tensor))
    scale = max_val / 127.0 if max_val != 0 else 1.0
    q_tensor = torch.clamp(torch.round(tensor / scale), -128, 127)
    return q_tensor, scale


# 2. Approximate Activation LUTs for Integer Simulation
def gelu_lut(x_int8):
    """Simulates the 8-bit GeLU lookup table Koh will put in RTL."""
    # Scale from INT8 to approximate float, apply GeLU, requantize to INT8
    x_float = x_int8.float() / 32.0
    gelu_float = 0.5 * x_float * (1.0 + torch.tanh(np.sqrt(2.0 / np.pi) * (x_float + 0.044715 * torch.pow(x_float, 3))))
    return torch.clamp(torch.round(gelu_float * 32.0), -128, 127).to(torch.int8)


# 3. Quantized Linear Layer (INT8 Input x INT4 Weight -> INT8 Output)
class QuantizedLinear(nn.Module):
    def __init__(self, in_features, out_features):
        super().__init__()
        self.in_features = in_features
        self.out_features = out_features
        # Initialize float weights then quantize to INT4
        raw_w = torch.randn(out_features, in_features) * 0.1
        self.w_int4, self.w_scale = quantize_int4(raw_w)

    def forward(self, x_int8, in_scale):
        # Hardware MatMul: int32 accumulation
        out_int32 = torch.matmul(x_int8.to(torch.int32), self.w_int4.t().to(torch.int32))
        # Re-scale back to INT8
        effective_scale = in_scale * self.w_scale
        out_float = out_int32.float() * effective_scale
        out_int8, out_scale = quantize_int8(out_float)
        return out_int8, out_scale


# 4. Single-Layer Transformer Block
class SmallTransformerBlock(nn.Module):
    def __init__(self, d_model=64, n_heads=2, d_mlp=128):
        super().__init__()
        self.d_model = d_model
        self.n_heads = n_heads
        self.head_dim = d_model // n_heads

        # Attention Projections
        self.q_proj = QuantizedLinear(d_model, d_model)
        self.k_proj = QuantizedLinear(d_model, d_model)
        self.v_proj = QuantizedLinear(d_model, d_model)
        self.out_proj = QuantizedLinear(d_model, d_model)

        # Feed-Forward Network
        self.ffn1 = QuantizedLinear(d_model, d_mlp)
        self.ffn2 = QuantizedLinear(d_mlp, d_model)

    def forward(self, x_int8, x_scale):
        B, S, D = x_int8.shape

        # --- Self-Attention ---
        q, q_scale = self.q_proj(x_int8, x_scale)
        k, k_scale = self.k_proj(x_int8, x_scale)
        v, v_scale = self.v_proj(x_int8, x_scale)

        # Reshape for multi-head: (B, H, S, head_dim)
        q = q.view(B, S, self.n_heads, self.head_dim).transpose(1, 2)
        k = k.view(B, S, self.n_heads, self.head_dim).transpose(1, 2)
        v = v.view(B, S, self.n_heads, self.head_dim).transpose(1, 2)

        # Q * K^T (int32 accumulation)
        scores = torch.matmul(q.to(torch.int32), k.transpose(-2, -1).to(torch.int32))
        
        # Approximate Softmax (normalized over final dim)
        attn_probs = torch.softmax(scores.float() * (q_scale * k_scale) / np.sqrt(self.head_dim), dim=-1)
        attn_probs_int8, prob_scale = quantize_int8(attn_probs)

        # Attn * V
        context = torch.matmul(attn_probs_int8.to(torch.int32), v.to(torch.int32))
        context_float = context.float() * (prob_scale * v_scale)
        context = context.transpose(1, 2).contiguous().view(B, S, D)
        context_int8, c_scale = quantize_int8(context_float)

        attn_out, attn_scale = self.out_proj(context_int8, c_scale)

        # Residual connection
        x_post_attn = x_int8 + attn_out.to(torch.int8)

        # --- Feed-Forward Network ---
        ffn1_out, ffn1_scale = self.ffn1(x_post_attn, x_scale)
        gelu_out = gelu_lut(ffn1_out)
        ffn2_out, ffn2_scale = self.ffn2(gelu_out, ffn1_scale)

        # Residual connection
        out = x_post_attn + ffn2_out.to(torch.int8)
        return out


# Quick test run:
if __name__ == "__main__":
    torch.manual_seed(42)
    model = SmallTransformerBlock(d_model=64, n_heads=2, d_mlp=128)
    
    # Input: (Batch=1, SeqLen=16, EmbedDim=64)
    dummy_input = torch.randn(1, 16, 64)
    dummy_int8, input_scale = quantize_int8(dummy_input)

    output = model(dummy_int8, input_scale)
    print("Model executed successfully. Output shape:", output.shape)