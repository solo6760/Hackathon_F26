# ==============================================================================
# Vivado Batch Build Script for Basys 3 (Artix-7 xc7a35tcpg236-1)
# ==============================================================================

set PART xc7a35tcpg236-1
set TOP  basys3_top

puts "=== Building $TOP for $PART ==="

# 1. Read Design Sources
read_verilog -sv [glob Kade_RTL/src/*.sv]
read_verilog -sv control_path/src/kera_ctrl.sv

# 2. Read Constraints
read_xdc basys3.xdc

# 3. Synthesis (Setting -max_dsp 0 ensures multipliers map to LUTs, fitting the 256 PUs on Basys 3)
synth_design -top $TOP -part $PART -max_dsp 0 -flatten_hierarchy rebuilt

# 4. Reports after synthesis
report_utilization -file synth_utilization.txt
report_timing_summary -file synth_timing.txt

# 5. Optimization & Implementation
opt_design
place_design
phys_opt_design
route_design

# 6. Reports after implementation
report_utilization -file impl_utilization.txt
report_timing_summary -file impl_timing.txt

# 7. Generate Bitstream
write_bitstream -force basys3_top.bit
puts "=== Bitstream generated: basys3_top.bit ==="

