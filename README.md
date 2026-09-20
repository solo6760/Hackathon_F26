# Hackathon F26: Quantized Transformer Accelerator

Hardware/software co-design and verification environment for an INT8/INT4 quantized transformer block targeting FPGA implementation.

This repo holds the Python golden models, Brevitas QONNX export scripts, and RTL test vector generators used to verify our custom hardware pipeline.

---

## Architecture & Numerical Specs

| Parameter | Specification | Notes |
| :--- | :--- | :--- |
| **Activations** | Signed INT8 (`[-128, 127]`) | Q3.5, scale `2^-5` |
| **Weights** | Signed INT4 (`[-8, 7]`) | Per-tensor power-of-two scale |
| **Accumulator** | Signed INT32 | Prevents overflow across dot products |
| **Tile Dimensions** | `M=16, K=16, N=16` | Standard GEMM tile for hardware verification |
| **Model Dimensions** | `d_model=64`, `seq_len=64` | One attention head, `head_dim=64` |
| **MLP / FFN Dim** | `d_mlp=128` | Expansion factor of 2x |
| **Activation Function** | GeLU via 8-bit LUT | Simulates hardware lookup table |

---

## Directory Structure

```text
├── Koh_work/
│   └── test.py                 # RTL / hardware simulation scratchpad
└── testing_py/
    ├── pytorch_model.py        # Quantized PyTorch reference model (MHSA + FFN + GeLU LUT)
    ├── train_model.py          # Deterministic ARES training and deployment export
    ├── gen_qkv_vectors.py      # Trained Q/K/V BRAM and attention golden vectors
    ├── kera_fixed.py           # Shared fixed-point, packing, hex, and metric utilities
    ├── test_reference_vec.py   # Test vector & BRAM hex file generator for RTL testbenches
    └── transformer_script.py   # Brevitas INT8/INT4 layer definition & QONNX export for FINN
```

---

## File Details

### `testing_py/pytorch_model.py`
Software golden model for a single-layer quantized transformer block.
- Implements symmetric INT4 weight and INT8 activation quantization.
- Models multi-head self-attention, integer matrix multiplications, fixed-point scaling, and an 8-bit GeLU LUT approximation matching the RTL implementation.
- Verifies full forward pass integrity with residual additions.

### `testing_py/train_model.py`
- Trains the 64-token, single-head sensor-fusion model using one stable sensor embedding basis.
- Exports a PyTorch checkpoint and compact NumPy deployment artifact containing trained INT4
  weights and the power-of-two requantization shifts used by the RTL reference.
- Reports both FP32 validation MSE and post-training INT8/INT4 validation MSE.

### `testing_py/test_reference_vec.py`
Generates deterministic test vectors and golden outputs for RTL testbench validation using fixed seed `42` on a `16x16x16` tile:
- `act_tile.hex`: INT8 activation tile (1 byte per line, hex format).
- `weights_bram.hex`: INT4 signed weights packed LSB-first into 32-bit BRAM words (8 weights / 4 bytes per line).
- `golden_out.hex`: Exact 32-bit signed integer accumulation outputs for hardware comparison.

### `testing_py/transformer_script.py`
Minimal quantized linear block constructed with Xilinx/AMD Brevitas:
- Quantized input identity (`INT8`) and linear projection (`INT4` weights).
- Exports the graph to QONNX format (`transformer_layer.onnx`) for consumption by the FINN FPGA compiler.

---

## Memory Layout (BRAM Packing)

Weights in `weights_bram.hex` are packed into 32-bit BRAM words (8 INT4 weights per line, little-endian nibble ordering):

```text
Word [31:0] = [ W7:W6 | W5:W4 | W3:W2 | W1:W0 ]
Each byte contains:
  [7:4] -> High weight (odd index)
  [3:0] -> Low weight  (even index)
```

---

## Usage

### Dependencies

```bash
pip install torch numpy brevitas
```

### Quick Start (Make)

```bash
make help          # Show all available make targets
make train         # Retrain and export .pt and lightweight .npz deployment artifacts
make model         # Run PyTorch quantized transformer golden model & LUT tests
make vectors       # Generate RTL test vectors (act_tile.hex, weights_bram.hex, golden_out.hex)
make qkv-vectors   # Generate 64-token vectors from the trained Q/K/V weights
make verify-rtl    # Run the GEMM simulation and compare its raw dump with Python
make lut-gelu      # Run standalone GeLU LUT quantization & error analysis
make lut-softmax   # Run standalone Softmax LUT approximation & error analysis
make qonnx         # Export Brevitas INT8/INT4 layer to QONNX format
make finn-convert  # Run QONNX cleanup & FINN-ONNX conversion verification
make clean         # Remove generated hex files and Python caches
```

### Manual Commands

```bash
# Run Model Simulation
python testing_py/pytorch_model.py

# Generate Hardware Test Vectors
python testing_py/test_reference_vec.py

# Retrain and regenerate vectors from trained weights
make train qkv-vectors

# Export QONNX Graph
python testing_py/transformer_script.py
```
This writes `act_tile.hex`, `weights_bram.hex`, and `golden_out.hex` in the current working directory for simulation in ModelSim / Vivado / Verilator.

### Export QONNX Graph
```bash
python testing_py/transformer_script.py
```
Outputs `transformer_layer.onnx` for FINN synthesis.
