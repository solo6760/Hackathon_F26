VERILATE       := verilator
VERILATE_FLAGS := --binary --timing --trace-fst -Wno-fatal --top-module tb_kera_ctrl

sim: src/kera_ctrl.sv tb/tb_kera_ctrl.sv prog/fc1.hex
	$(VERILATE) $(VERILATE_FLAGS) src/kera_ctrl.sv tb/tb_kera_ctrl.sv
	./obj_dir/Vtb_kera_ctrl

clean:
	rm -rf obj_dir
	rm -f waveform.fst
