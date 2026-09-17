PYTHON ?= python3

.PHONY: help all model vectors lut-gelu lut-softmax qonnx finn-convert test clean

help:
	@echo "Hackathon F26 - Quantized Transformer Accelerator"
	@echo ""
	@echo "Available targets:"
	@echo "  make model         - Run PyTorch quantized transformer golden model & LUT tests"
	@echo "  make vectors       - Generate RTL test vectors (act_tile.hex, weights_bram.hex, golden_out.hex)"
	@echo "  make lut-gelu      - Run standalone GeLU LUT quantization & error analysis"
	@echo "  make lut-softmax   - Run standalone Softmax LUT approximation & error analysis"
	@echo "  make qonnx         - Export Brevitas INT8/INT4 layer to QONNX format"
	@echo "  make finn-convert  - Run QONNX cleanup & FINN-ONNX conversion verification"
	@echo "  make test          - Run model simulation, LUT checks, and test vector generation"
	@echo "  make clean         - Remove generated hex files and Python cache"
	@echo ""

all: model vectors

model:
	$(PYTHON) testing_py/pytorch_model.py

vectors:
	$(PYTHON) testing_py/test_reference_vec.py

lut-gelu:
	$(PYTHON) Koh_work/koh_python.py

lut-softmax:
	$(PYTHON) softmax_lut.py

qonnx:
	$(PYTHON) testing_py/transformer_script.py

finn-convert:
	cd testing_py && $(PYTHON) finn_convert.py

test: model lut-gelu lut-softmax vectors

clean:
	rm -f act_tile.hex weights_bram.hex golden_out.hex testing_py/*.hex
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
