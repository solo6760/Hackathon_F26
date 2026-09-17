import math
import torch
import torch.nn as nn
import numpy as np


# ============================================================
# 1. QUANTIZATION HELPERS
# ============================================================

def quantize_int4(tensor):
    """Symmetric INT4 quantization: values from -8 to 7."""

    max_val = torch.max(torch.abs(tensor))

    scale = max_val / 7.0 if max_val != 0 else 1.0

    q_tensor = torch.clamp(
        torch.round(tensor / scale),
        -8,
        7
    )

    return q_tensor, scale


def quantize_int8(tensor):
    """Symmetric INT8 quantization: values from -128 to 127."""

    max_val = torch.max(torch.abs(tensor))

    scale = max_val / 127.0 if max_val != 0 else 1.0

    q_tensor = torch.clamp(
        torch.round(tensor / scale),
        -128,
        127
    )

    return q_tensor, scale


# ============================================================
# 2. GeLU LUT
# ============================================================

GELU_SCALE = 1 / 32

gelu_table = []


# Create all 256 LUT outputs
for q_in in range(-128, 128):

    # Convert INT8 -> real value
    x = q_in * GELU_SCALE

    # Exact GeLU
    y = 0.5 * x * (
        1 + math.erf(x / math.sqrt(2))
    )

    # Convert GeLU result -> INT8
    q_out = round(y / GELU_SCALE)

    # Keep inside INT8 range
    q_out = max(
        -128,
        min(127, q_out)
    )

    gelu_table.append(q_out)


# Store LUT as PyTorch tensor
GELU_LUT = torch.tensor(
    gelu_table,
    dtype=torch.int8
)


def gelu_lut(x_int8, in_scale):

    # Convert current INT8 input back to real values
    x_float = x_int8.float() * in_scale

    # Convert real values into our 1/32 LUT scale
    x_q = torch.round(
        x_float / GELU_SCALE
    )

    # Keep input inside LUT range
    x_q = torch.clamp(
        x_q,
        -128,
        127
    ).to(torch.int16)

    # Convert -128...127 into list indexes 0...255
    index = x_q + 128

    # Look up GeLU outputs
    output = GELU_LUT[index.long()]

    return output, GELU_SCALE


# ============================================================
# 3. SOFTMAX EXPONENTIAL LUT
# ============================================================

EXP_STEP = 0.25
EXP_MIN = -8.0
EXP_MAX = 0.0

exp_table = []

x = EXP_MIN


# Store e^x values from -8 to 0
while x <= EXP_MAX:

    exp_table.append(
        math.exp(x)
    )

    x += EXP_STEP


EXP_LUT = torch.tensor(
    exp_table,
    dtype=torch.float32
)


def softmax_lut(scores):

    # Find largest score
    max_value = torch.max(
        scores,
        dim=-1,
        keepdim=True
    ).values

    # Subtract maximum
    shifted = scores - max_value

    # Keep values inside LUT range
    shifted = torch.clamp(
        shifted,
        EXP_MIN,
        EXP_MAX
    )

    # Determine LUT index
    index = torch.round(
        (shifted - EXP_MIN) / EXP_STEP
    ).long()

    # Get approximate e^x from LUT
    exp_values = EXP_LUT.to(scores.device)[index]

    # Add exponential values
    total = torch.sum(
        exp_values,
        dim=-1,
        keepdim=True
    )

    # Normalize
    return exp_values / total


# ============================================================
# 4. QUANTIZED LINEAR LAYER
# ============================================================

class QuantizedLinear(nn.Module):

    def __init__(
        self,
        in_features,
        out_features
    ):

        super().__init__()

        self.in_features = in_features
        self.out_features = out_features

        # Create random floating-point weights
        raw_w = (
            torch.randn(
                out_features,
                in_features
            )
            * 0.1
        )

        # Convert weights to INT4
        self.w_int4, self.w_scale = quantize_int4(
            raw_w
        )


    def forward(
        self,
        x_int8,
        in_scale
    ):

        # INT8 input x INT4 weights
        # accumulate using INT32
        out_int32 = torch.matmul(
            x_int8.to(torch.int32),
            self.w_int4.t().to(torch.int32)
        )

        # Convert accumulated result back to real value
        effective_scale = (
            in_scale
            * self.w_scale
        )

        out_float = (
            out_int32.float()
            * effective_scale
        )

        # Quantize output back to INT8
        out_int8, out_scale = quantize_int8(
            out_float
        )

        return out_int8, out_scale


# ============================================================
# 5. TRANSFORMER BLOCK
# ============================================================

class SmallTransformerBlock(nn.Module):

    def __init__(
        self,
        d_model=64,
        n_heads=2,
        d_mlp=128
    ):

        super().__init__()

        self.d_model = d_model
        self.n_heads = n_heads

        self.head_dim = (
            d_model // n_heads
        )


        # Attention projections
        self.q_proj = QuantizedLinear(
            d_model,
            d_model
        )

        self.k_proj = QuantizedLinear(
            d_model,
            d_model
        )

        self.v_proj = QuantizedLinear(
            d_model,
            d_model
        )

        self.out_proj = QuantizedLinear(
            d_model,
            d_model
        )


        # Feed-forward network
        self.ffn1 = QuantizedLinear(
            d_model,
            d_mlp
        )

        self.ffn2 = QuantizedLinear(
            d_mlp,
            d_model
        )


    def forward(
        self,
        x_int8,
        x_scale
    ):

        B, S, D = x_int8.shape


        # ====================================================
        # SELF ATTENTION
        # ====================================================

        q, q_scale = self.q_proj(
            x_int8,
            x_scale
        )

        k, k_scale = self.k_proj(
            x_int8,
            x_scale
        )

        v, v_scale = self.v_proj(
            x_int8,
            x_scale
        )


        # Reshape into multiple attention heads
        q = q.view(
            B,
            S,
            self.n_heads,
            self.head_dim
        ).transpose(1, 2)

        k = k.view(
            B,
            S,
            self.n_heads,
            self.head_dim
        ).transpose(1, 2)

        v = v.view(
            B,
            S,
            self.n_heads,
            self.head_dim
        ).transpose(1, 2)


        # Q x K^T
        scores = torch.matmul(
            q.to(torch.int32),

            k.transpose(
                -2,
                -1
            ).to(torch.int32)
        )


        # Convert attention scores to real values
        scaled_scores = (
            scores.float()
            * (q_scale * k_scale)
            / np.sqrt(self.head_dim)
        )


        # ====================================================
        # OUR APPROXIMATE SOFTMAX LUT
        # ====================================================

        attn_probs = softmax_lut(
            scaled_scores
        )


        # Convert probabilities to INT8
        attn_probs_int8, prob_scale = quantize_int8(
            attn_probs
        )


        # Attention probabilities x V
        context = torch.matmul(
            attn_probs_int8.to(torch.int32),
            v.to(torch.int32)
        )


        context_float = (
            context.float()
            * (prob_scale * v_scale)
        )


        # Put heads back together
        context_float = (
            context_float
            .transpose(1, 2)
            .contiguous()
            .view(B, S, D)
        )


        # Convert back to INT8
        context_int8, c_scale = quantize_int8(
            context_float
        )


        attn_out, attn_scale = self.out_proj(
            context_int8,
            c_scale
        )


        # Residual connection
        x_post_attn = (
            x_int8
            + attn_out.to(torch.int8)
        )


        # ====================================================
        # FEED-FORWARD NETWORK
        # ====================================================

        ffn1_out, ffn1_scale = self.ffn1(
            x_post_attn,
            x_scale
        )


        # ====================================================
        # OUR GeLU LUT
        # ====================================================

        gelu_out, gelu_scale = gelu_lut(
            ffn1_out,
            ffn1_scale
        )


        # Second FFN layer
        ffn2_out, ffn2_scale = self.ffn2(
            gelu_out,
            gelu_scale
        )


        # Residual connection
        out = (
            x_post_attn
            + ffn2_out.to(torch.int8)
        )

        return out


# ============================================================
# 6. TEST GeLU LUT
# ============================================================

print("\n----- GeLU LUT TEST -----")

gelu_errors = []

for test_x in [
    -2.0,
    -1.0,
    0.0,
    1.0,
    2.0
]:

    # Exact GeLU
    exact = 0.5 * test_x * (
        1
        + math.erf(
            test_x / math.sqrt(2)
        )
    )

    # Convert input to LUT scale
    q_in = round(
        test_x / GELU_SCALE
    )

    q_in = max(
        -128,
        min(127, q_in)
    )

    # Get LUT output
    q_out = GELU_LUT[
        q_in + 128
    ].item()

    approximate = (
        q_out
        * GELU_SCALE
    )

    error = abs(
        exact
        - approximate
    )

    gelu_errors.append(
        error
    )

    print(
        "Input:",
        test_x,
        "Exact:",
        exact,
        "LUT:",
        approximate
    )


print(
    "GeLU mean error:",
    sum(gelu_errors)
    / len(gelu_errors)
)


print(
    "GeLU maximum error:",
    max(gelu_errors)
)


# ============================================================
# 7. TEST SOFTMAX LUT
# ============================================================

print("\n----- SOFTMAX LUT TEST -----")


softmax_tests = [

    [2.0, 1.0, 0.0],

    [1.2, 0.3, -0.7],

    [3.1, 2.4, 1.8],

    [-1.0, -2.0, -3.0],

    [0.2, 0.1, 0.0]

]


softmax_errors = []


for test_values in softmax_tests:

    scores = torch.tensor(
        test_values,
        dtype=torch.float32
    )


    # Exact PyTorch Softmax
    exact = torch.softmax(
        scores,
        dim=-1
    )


    # Our LUT Softmax
    approximate = softmax_lut(
        scores
    )


    print(
        "\nInput:",
        test_values
    )

    print(
        "Exact:",
        exact.tolist()
    )

    print(
        "LUT:",
        approximate.tolist()
    )


    errors = torch.abs(
        exact
        - approximate
    )


    softmax_errors.extend(
        errors.tolist()
    )


print(
    "\nSoftmax mean error:",
    sum(softmax_errors)
    / len(softmax_errors)
)


print(
    "Softmax maximum error:",
    max(softmax_errors)
)


# ============================================================
# 8. TEST FULL TRANSFORMER
# ============================================================

if __name__ == "__main__":

    print(
        "\n----- FULL TRANSFORMER TEST -----"
    )


    torch.manual_seed(42)


    model = SmallTransformerBlock(
        d_model=64,
        n_heads=2,
        d_mlp=128
    )


    # Batch = 1
    # Sequence length = 16
    # Embedding dimension = 64
    dummy_input = torch.randn(
        1,
        16,
        64
    )


    # Convert model input to INT8
    dummy_int8, input_scale = quantize_int8(
        dummy_input
    )


    # Run entire transformer
    output = model(
        dummy_int8,
        input_scale
    )


    print(
        "Model executed successfully."
    )


    print(
        "Output shape:",
        output.shape
    )
