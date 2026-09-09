import torch
# PyTorch compatibility shim for Brevitas FX tracer
import torch.fx._symbolic_trace
if not hasattr(torch.fx._symbolic_trace, "_is_fx_tracing_flag"):
    torch.fx._symbolic_trace._is_fx_tracing_flag = False

import brevitas.nn as qnn
from brevitas.export import export_qonnx

# 1. Define the minimal layer using the agreed dimensions (D=64, MLP=128)
class FinnTransformerBlock(torch.nn.Module):
    def __init__(self, in_features=64, hidden_features=128):
        super().__init__()
        # Input quantizer: INT8
        self.quant_in = qnn.QuantIdentity(bit_width=8, return_quant_tensor=True)
        # Linear layer: INT4 weights
        self.fc1 = qnn.QuantLinear(
            in_features, 
            hidden_features, 
            bias=False, 
            weight_bit_width=4
        )

    def forward(self, x):
        return self.fc1(self.quant_in(x))

# 2. Instantiate and export
model = FinnTransformerBlock()
model.eval()

# Dummy input matching Sequence Length = 16, Embedding Dim = 64
dummy_input = torch.randn(1, 16, 64)

# 3. Export to QONNX format for FINN
export_qonnx(model, args=dummy_input, export_path="transformer_layer.onnx")
print("Successfully generated transformer_layer.onnx")