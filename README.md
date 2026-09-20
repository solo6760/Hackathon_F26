# KERA: FPGA Sensor-Fusion Attention Accelerator

KERA is a hardware/software co-design project for low-latency sensor-fusion
attention on FPGA. The software side trains a compact transformer, quantizes it
to INT8 activations and INT4 weights, generates BRAM images and golden vectors,
and compares raw RTL simulation dumps against a bit-accurate reference.

The target configuration follows the project proposal:

| Parameter | Value |
| --- | ---: |
| Sequence length | 64 tokens |
| Model dimension | 64 |
| Attention heads | 1 |
| Head dimension | 64 |
| FFN dimension | 128 |
| GEMM tile | 16 × 16 × 16 |
| Activations | Signed INT8, Q3.5 (`2^-5`) |
| Weights | Signed INT4, per-tensor power-of-two scale |
| Accumulators | Signed INT32 |

## Current status

Implemented and verified:

- Deterministic ARES-style sensor trajectory generation.
- Training for a 64-token, single-head sensor-fusion transformer.
- Trained FP32 checkpoint and lightweight deployment artifact.
- INT4 weight and INT8 activation quantization with shift-only scaling.
- Bit-accurate Python reference for Q/K/V, attention, GeLU, FFN, and residuals.
- Vectorized INT4 BRAM packing and batched `$readmemh` output.
- Q/K/V, score, probability, and context golden-vector generation.
- Raw RTL dump ingestion with mismatch, MAE, RMSE, and cosine metrics.
- Behavioral SystemVerilog verification of one INT8 × INT4 GEMM tile.
- Trained QONNX export with a `[1, 64, 64]` input shape.

Not included in this repository yet:

- A synthesizable Q/K/V and tiled-attention datapath DUT.
- Synthesizable online-softmax and reciprocal units.
- FPGA top level, UART/SPI interface, and board constraints.
- Vivado synthesis, timing, power, and utilization reports.

The existing `datapath/tb_kera_gemm.sv` is a behavioral testbench. It proves
the data representation and golden arithmetic but is not itself an FPGA core.

## Fixed-point contract

RTL must use the same conventions as the Python reference:

| Stage | Format or operation |
| --- | --- |
| Sensor input | Signed INT8 Q3.5 |
| Packed weights | Signed INT4, first weight in word bits `[3:0]` |
| Dot-product accumulator | Signed INT32 |
| Q/K/V requantization | Current checkpoint: arithmetic `>>> 5` |
| Attention LUT index | QK accumulator `>>> 11` for a 64-wide head |
| Softmax exponential | 33-entry Q15 LUT over `[-8, 0]`, step `0.25` |
| Softmax probability | Unsigned magnitude in `[0, 127]` |
| Context normalization | Arithmetic `>>> 7` |
| Output projection | Current checkpoint: arithmetic `>>> 5` |
| FFN1 | Current checkpoint: arithmetic `>>> 4` |
| FFN2 | Current checkpoint: arithmetic `>>> 5` |
| Rounding | Add half, then arithmetic right shift |
| Narrowing | Signed saturation to INT8 |

The checkpoint is the authoritative source for per-layer shifts. Retraining can
change weight scales, so RTL should consume the exported metadata rather than
silently hard-code old values.

### Nibble ordering

INT4 weights are packed LSB-first:

```text
word[31:0] = {W7, W6, W5, W4, W3, W2, W1, W0}
word[3:0]   = W0
word[7:4]   = W1
...
word[31:28] = W7
```

Negative weights use four-bit two's-complement representation.

## Repository layout

```text
.
├── Makefile
├── control_path/
│   ├── src/kera_ctrl.sv          # Synthesizable tile/control sequencer
│   └── tb/tb_kera_ctrl.sv        # Controller testbench
├── datapath/
│   ├── gen_fc1_vectors.py        # FC1 vectors and BRAM packing
│   └── tb_kera_gemm.sv           # Behavioral GEMM verification model
├── testing_py/
│   ├── train_model.py            # Training, quantization, checkpoint export
│   ├── sensor_fusion.py           # Sensor data and Q3.5 embedding
│   ├── pytorch_model.py           # FP32 and bit-accurate transformer reference
│   ├── kera_fixed.py              # Shared arithmetic, packing, hex, and metrics
│   ├── gen_qkv_vectors.py         # Trained attention vector exporter
│   ├── test_reference_vec.py      # GEMM vectors and RTL comparison
│   ├── ablation_study.py          # A/B/C analytical comparison and dump metrics
│   ├── transformer_script.py      # Trained QONNX export
│   ├── kera_sensor_fusion_trained.pt
│   └── kera_sensor_fusion_trained.npz
├── softmax_lut.py
└── Koh_work/koh_python.py
```

Generated `.hex` files and vector directories are intentionally ignored by Git.
Each developer should regenerate them from the committed model artifacts.

## Requirements

Core Python flow:

```bash
python3 -m pip install numpy torch
```

RTL GEMM simulation also requires Icarus Verilog:

Debian/Ubuntu
```bash
sudo apt install iverilog
```
Fedora
```bash
sudo dnf install iverilog gtkwave
```
macOS - brew
```bash
brew install icarus-verilog
```

QONNX export requires Brevitas and ONNX:

```bash
python3 -m pip install brevitas onnx
```

FINN conversion requires a separately configured FINN environment. It is not a
standard dependency of the core test suite.

## Quick start

Run commands from the repository root:

```bash
# Reproduce the trained checkpoint and deployment artifact
make train

# Run all core model, LUT, vector, ablation, and GEMM RTL checks
make test

# Export the trained FFN layer to QONNX
make qonnx
```

A successful `make test` ends with:

```text
bitwise_mismatches    : 0
mismatch_percent      : 0.0
bit_accurate          : True
```

Check the shell result as well:

```bash
make test
echo $?
```

An exit status of `0` means every target completed successfully.

## Make targets

| Target | Purpose |
| --- | --- |
| `make train` | Retrain and export `.pt` and `.npz` model artifacts |
| `make model` | Compare FP32 and bit-accurate transformer outputs |
| `make sensor-fusion` | Generate and quantize one sensor trajectory |
| `make vectors` | Generate the 16 × 16 GEMM test vectors |
| `make qkv-vectors` | Generate trained 64-token Q/K/V and attention vectors |
| `make ablation` | Report A/B/C numerical and memory estimates |
| `make sim-rtl` | Run the behavioral SystemVerilog GEMM simulation |
| `make verify-rtl` | Compare the GEMM RTL dump against the Python golden |
| `make test` | Run all core automated checks |
| `make qonnx` | Export the trained QONNX model |
| `make finn-convert` | Convert QONNX in a configured FINN environment |
| `make clean` | Remove generated vectors and Python caches |

## Generated RTL vectors

`make vectors` creates the basic GEMM files in the repository root:

```text
act_tile.hex
weights_bram.hex
golden_out.hex
```

`make qkv-vectors` creates `testing_py/vectors_qkv/` containing:

```text
act_in.hex
w_q.hex
w_k.hex
w_v.hex
golden_q.hex
golden_k.hex
golden_v.hex
golden_scores_h0.hex
golden_probs_h0.hex
golden_context_h0.hex
```

`act_in.hex` uses logical 512-bit lines: one byte per token for all 64 tokens.
An Artix-7 implementation must bank each logical line across narrower BRAM ports
or adapt the exporter once the physical BRAM interface is finalized.

## FPGA handoff

An RTL developer with access to this branch should run:

```bash
make qkv-vectors
make verify-rtl
```

The minimum handoff consists of:

- This README and the fixed-point contract above.
- `testing_py/kera_sensor_fusion_trained.npz`.
- `testing_py/gen_qkv_vectors.py` and `testing_py/kera_fixed.py`.
- The regenerated `testing_py/vectors_qkv/` directory.

For the planned Artix-7 device, the model storage is approximately 128 Kbits and
the estimated KERA buffers are approximately 242 Kbits, comfortably below the
available 1,800 Kbits of block RAM. Compute fit depends on the exact device's
DSP48E1 count. The analytical cycle model assumes 256 MACs, so the synthesizable
design may need a smaller time-multiplexed MAC array.

The device's advertised maximum clock is not the accelerator's guaranteed
frequency. Actual frequency must be established by Vivado implementation and
timing closure; 100–200 MHz is a sensible initial constraint range.

## Latest validated results

The committed deterministic training configuration produced:

| Measurement | Result |
| --- | ---: |
| FP32 validation MSE | `0.000031` |
| INT8/INT4 block validation MSE | `0.000806` |
| FP32 vs fixed-point cosine similarity | `0.99780` |
| FP32 vs fixed-point MAE | `0.04733` |
| GEMM Python/RTL mismatches | `0 / 256` |
| Input activation saturation | `0%` on the validation trajectory |
| Q/K/V projection saturation | `0%` on the validation trajectory |

These results validate the software reference and behavioral GEMM interface.
They are not substitutes for synthesis utilization, timing, power, or full-DUT
FPGA measurements.
