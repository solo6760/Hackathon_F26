import numpy as np
from pathlib import Path

from qonnx.core.modelwrapper import ModelWrapper
import qonnx.core.onnx_exec as oxe
from qonnx.util.cleanup import cleanup
from finn.transformation.qonnx.convert_qonnx_to_finn import ConvertQONNXtoFINN

script_dir = Path(__file__).resolve().parent
original_path = script_dir / "transformer_layer.onnx"
cleaned_path = script_dir / "transformer_layer_clean.onnx"
finn_path = script_dir / "transformer_layer_finn.onnx"

# Clean the QONNX model
cleanup(original_path, out_file=cleaned_path)
print("Cleaned QONNX model created.")

# Load cleaned QONNX model
qonnx_model = ModelWrapper(cleaned_path)

input_name = qonnx_model.graph.input[0].name

# Same input shape as your transformer layer
rng = np.random.default_rng(42)
test_input = rng.standard_normal((1, 64, 64), dtype=np.float32)

# Run QONNX model
qonnx_output_dict = oxe.execute_onnx(
    qonnx_model,
    {input_name: test_input}
)

qonnx_output = qonnx_output_dict[list(qonnx_output_dict.keys())[0]]

# Convert QONNX -> FINN-ONNX
finn_model = ModelWrapper(cleaned_path)
finn_model = finn_model.transform(ConvertQONNXtoFINN())
finn_model.save(finn_path)

print("FINN-ONNX model created.")

# Run converted FINN model
finn_model = ModelWrapper(finn_path)

finn_input_name = finn_model.graph.input[0].name

finn_output_dict = oxe.execute_onnx(
    finn_model,
    {finn_input_name: test_input}
)

finn_output = finn_output_dict[list(finn_output_dict.keys())[0]]

# Compare outputs
matches = np.allclose(
    qonnx_output,
    finn_output,
    rtol=1e-4,
    atol=1e-5
)

print("QONNX output shape:", qonnx_output.shape)
print("FINN output shape:", finn_output.shape)
print("Outputs match:", matches)

if not matches:
    raise RuntimeError("FINN conversion changed the model output!")

print("SUCCESS: QONNX -> FINN conversion verified.")
