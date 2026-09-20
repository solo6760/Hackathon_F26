# Kade RTL

Synthesizable SystemVerilog for one signed INT8-by-INT4 output-stationary GEMM
tile. The default array is 16x16 and retains every result in a signed INT32
accumulator before serializing signed INT8 values through a FIFO. `INNER_DIM`
sets the independent GEMM K dimension, so a 16x16 array can directly accumulate
a 16x64-by-64x16 projection tile by setting `INNER_DIM=64`.

## Interface contract

Pulse `tile_start` for one clock while the controller is idle. During the
following `compute_active` interval, drive skewed matrix edges on every clock
cycle `t`:

```text
horiz_input[row] = A[row][t-row]  when 0 <= t-row < INNER_DIM, otherwise 0
vert_input[col]   = B[t-col][col]  when 0 <= t-col < INNER_DIM, otherwise 0
```

The controller computes for `INNER_DIM+2*SIZE-2` cycles and pulses `tile_done`.
Pulse `drain_start` after that event. Results are emitted in row-major order.
Assert `fifo_ren` to consume them; `fifo_dout` is valid whenever `fifo_valid` is
high. The controller automatically stalls the drain when the FIFO is full.

Requantization adds a signed half-LSB bias, arithmetic-right-shifts by
`REQUANT_SHIFT`, and saturates to `[-128, 127]`. Exact half-way cases round away
from zero. `REQUANT_SHIFT=5` therefore divides the accumulator scale by 32; it
does not imply that an arbitrary INT32 value fits in INT8 without saturation.

`asyncFIFO` keeps its historical filename, but it is intentionally a
single-clock FIFO and must not be used for clock-domain crossing.

## Verification

Install Icarus Verilog and run:

```bash
make -C Kade_RTL test
```

The self-checking tests cover the counter, shift register, FIFO, BRAM, signed
PE MAC, systolic data skew, INT32 accumulation, signed rounding, saturation,
row-major draining, and FIFO backpressure.
