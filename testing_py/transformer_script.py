from pathlib import Path

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

# 2. Instantiate and load the trained FFN1 weights
torch.manual_seed(42)
model = FinnTransformerBlock()
script_dir = Path(__file__).resolve().parent
checkpoint = torch.load(script_dir / "kera_sensor_fusion_trained.pt", map_location="cpu")
with torch.no_grad():
    model.fc1.weight.copy_(checkpoint["model_state_dict"]["ffn1.weight"])
model.eval()

# Dummy input matching Sequence Length = 64, Embedding Dim = 64
dummy_input = torch.randn(1, 64, 64)

# 3. Export to QONNX format for FINN
export_path = script_dir / "transformer_layer.onnx"
# FINN/QONNX consumes the legacy custom Quant operators. Explicitly disable
# Dynamo so newer PyTorch releases do not emit a separate external-data file.
export_qonnx(model, args=dummy_input, export_path=export_path, dynamo=False)
print(f"Successfully generated {export_path}")
