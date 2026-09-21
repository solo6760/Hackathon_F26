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
| Target board | Digilent Basys 3 (Xilinx Artix-7 XC7A35T) |

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
- Synthesizable FC1 GEMM datapath in `Kade_RTL/` (16 × 16 INT8 × INT4 array,
  packed-BRAM reader, output FIFO and buffer). `tb_sysController` runs all 8
  output groups of the FC1 layer and matches `golden_fc1.hex` on all 2048
  INT32 words (see [RTL datapath](#rtl-datapath-kade_rtl)).
- Synthesizable control path in `control_path/`: `kera_ctrl` fetches,
  decodes, and sequences a three-opcode micro-ISA (`HALT`, `LOADRUN`,
  `DRAIN`) and drives the datapath handshake, with a self-checking testbench.
- Trained QONNX export with a `[1, 64, 64]` input shape.

Not included in this repository yet:

- Synthesizable Q/K/V and attention datapath. The RTL covers the FC1 GEMM
  only (16 × 64 by 64 × 128).
- Synthesizable online-softmax and reciprocal units.
- One testbench that runs `kera_ctrl` and the datapath together. `kera_ctrl`
  and `sysController` share the same handshake signals, but
  `tb_sysController` generates the strobes itself.
- FPGA top level, UART/SPI interface, and Basys 3 constraints.
- Vivado synthesis, timing, power, and utilization reports.

`datapath/tb_kera_gemm.sv` is a behavioral testbench. It proves the data
representation and golden arithmetic but is not an FPGA core; the synthesizable
GEMM is in `Kade_RTL/`.

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
├── Kade_RTL/
│   ├── src/
│   │   ├── sysController.sv      # Tile and drain sequencer, ready handshake
│   │   ├── sysArr.sv             # 16 × 16 array of PU cells
│   │   ├── PU.sv                 # INT8 × INT4 multiply-accumulate cell
│   │   ├── kera_mem.sv           # Packed BRAM reader, unpacker, output buffer
│   │   ├── asyncFIFO.sv          # Single-clock row FIFO (historical name)
│   │   ├── flexCounter.sv        # Rolling counter
│   │   └── flexSR.sv, flexMultiplex.sv   # Helpers, not in the current build
│   └── tb/tb_sysController.sv    # Full FC1 check against golden_fc1.hex
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
├── w_fc1.hex, act_fc1.hex, golden_fc1.hex   # FC1 vectors read by tb_sysController
├── exp_w_g*_k*.hex, exp_act_k*.hex           # Expected tiles for addressing checks
├── check_golden.py, verify_all_g0.py         # Python cross-checks of tile addressing
├── softmax_lut.py
└── Koh_work/koh_python.py
```

Generated `.hex` files and vector directories are ignored by Git, with one
exception: the FC1 vector files at the repository root are committed so
`tb_sysController` runs without the Python flow. Every other developer-generated
file should be regenerated from the committed model artifacts.

## Requirements

Core Python flow:

```bash
python3 -m pip install -r requirements.txt
```

**RTL GEMM simulation also requires Icarus Verilog**:

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

The `Kade_RTL/` testbench is built with **Verilator** (5.020 was used) and
needs a C++ toolchain and `make`:

```bash
sudo apt install verilator
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

## RTL datapath (`Kade_RTL/`)

`Kade_RTL/` is a synthesizable INT8 × INT4 GEMM for the FC1 layer: 16 tokens ×
64 inputs by 64 × 128 weights, with raw INT32 outputs. It is a 16 × 16
output-stationary array. Each cell multiplies its row's INT8 activation by its
column's INT4 weight every cycle and accumulates in its own INT32 register.
Operands are broadcast to the cells instead of forwarded between them, so the
inputs are not skewed.

| Module | Role |
| --- | --- |
| `sysController` | Runs the COMPUTE, DRAIN, and DRAIN_FLUSH states, owns `ready`, and connects the array, FIFO, and memory |
| `sysArr`, `PU` | 256 multiply-accumulate cells; `acc_clear` zeroes every sum, and one row of 16 sums is selected for the drain |
| `kera_mem` | Reads packed weights and activations, unpacks INT4 to one signed value per column, and stores drained rows |
| `asyncFIFO` | Single-clock FIFO of 512-bit rows (16 INT32 values) between the array and `kera_mem` |

The port names follow the outputs of `kera_ctrl`:

- Inputs: `tile_start`, `drain_start`, `tile_index`, `group_index`,
  `acc_clear`, `acc_en`, and `res_addr` for reading results back.
- Outputs: `ready`, `computer_active`, `drain_active`, and `res_data`.
- `ready` is high when idle with an empty FIFO and low while a tile or drain is
  in flight.

A tile takes 16 cycles, one K step per cycle. A group is four tiles along K
with `acc_clear` on the first, then one `drain_start`, which pushes 16 rows of
16 INT32 values through the FIFO into the output buffer.

| Memory | Layout |
| --- | --- |
| Weights | 1024 words × 32 bits. Tile = 4 × group + K-tile. Row `k` of a tile is word `2k` (channels 0–7) and `2k+1` (channels 8–15), INT4 LSB-first |
| Activations | 64 lines × 128 bits, one line per K index. Byte `m` is token `m` |
| Output | 128 lines × 512 bits. Line = 8 × token + group. `res_addr` = token × 128 + channel, so it indexes `golden_fc1.hex` directly |

Run from the repository root, because the memories load `w_fc1.hex`,
`act_fc1.hex`, and `golden_fc1.hex` from the working directory:

```bash
verilator --binary -j 0 --trace -Wall -Wno-fatal -I./Kade_RTL/src \
  ./Kade_RTL/src/PU.sv ./Kade_RTL/src/flexCounter.sv ./Kade_RTL/src/sysArr.sv \
  ./Kade_RTL/src/asyncFIFO.sv ./Kade_RTL/src/kera_mem.sv \
  ./Kade_RTL/src/sysController.sv ./Kade_RTL/tb/tb_sysController.sv \
  --top-module tb_sysController
./obj_dir/Vtb_sysController
```

A passing run ends with:

```text
=== SUCCESS: ALL 2048 WORDS MATCH GOLDEN FC1! ===
```

The testbench drives the strobes itself. Under that stimulus one group takes
about 90 cycles and the whole FC1 layer about 720 cycles at the simulated 10 ns
clock. That is not an end-to-end count, because the control path adds its own
cycles between operations. This test is not yet a `make` target, and the
design has not been synthesized. `check_golden.py` and `verify_all_g0.py`
recompute tile outputs from the packed vectors in plain Python and check the
addressing independently of the RTL.

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

For the Basys 3 (Artix-7 XC7A35T), the model storage is approximately 128 Kbits
and the estimated KERA buffers are approximately 242 Kbits, comfortably below
the 1,800 Kbits of block RAM. The device has 90 DSP48E1 slices, and the 16 × 16
array has 256 INT8 × INT4 multipliers, so it cannot use one DSP per cell. Whether
Vivado maps the small products to LUTs or DSPs, and whether the full array fits,
has not been measured. If it does not fit, the design may need a smaller
time-multiplexed MAC array.

The device's advertised maximum clock is not the accelerator's guaranteed
frequency. Actual frequency must be established by Vivado implementation and
timing closure. The board's 100 MHz oscillator is the natural first constraint.

## Latest validated results

The committed deterministic training configuration produced:

| Measurement | Result |
| --- | ---: |
| FP32 validation MSE | `0.000031` |
| INT8/INT4 block validation MSE | `0.000806` |
| FP32 vs fixed-point cosine similarity | `0.99780` |
| FP32 vs fixed-point MAE | `0.04733` |
| GEMM Python/RTL mismatches | `0 / 256` |
| FC1 RTL vs `golden_fc1.hex` (Verilator, `tb_sysController`) | `0 / 2048` |
| Input activation saturation | `0%` on the validation trajectory |
| Q/K/V projection saturation | `0%` on the validation trajectory |

These results validate the software reference, the behavioral GEMM interface,
and the FC1 datapath in simulation.
They are not substitutes for synthesis utilization, timing, power, or full-DUT
FPGA measurements.
