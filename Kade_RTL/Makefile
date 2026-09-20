IVERILOG ?= iverilog
VVP ?= vvp
SRC := $(wildcard src/*.sv)
BUILD_DIR := build

.PHONY: all lint test primitives systolic clean

all: test

$(BUILD_DIR):
	mkdir -p $@

lint: | $(BUILD_DIR)
	$(IVERILOG) -g2012 -Wall -s sysController -o $(BUILD_DIR)/lint $(SRC)

primitives: | $(BUILD_DIR)
	$(IVERILOG) -g2012 -Wall -s tb_primitives -o $(BUILD_DIR)/tb_primitives $(SRC) tb/tb_primitives.sv
	$(VVP) $(BUILD_DIR)/tb_primitives

systolic: | $(BUILD_DIR)
	$(IVERILOG) -g2012 -Wall -s tb_sysController -o $(BUILD_DIR)/tb_sysController $(SRC) tb/tb_sysController.sv
	$(VVP) $(BUILD_DIR)/tb_sysController

test: lint primitives systolic

clean:
	rm -rf $(BUILD_DIR)
