# SPDX-License-Identifier: MIT
# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.

THIS_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
ROCKBUILDER_DIR := $(abspath $(THIS_DIR)/../../../..)
PYTHON ?= $(ROCKBUILDER_DIR)/.venv/bin/python
SCRIPT := $(THIS_DIR)/fast_fp8_dequant_compare.py

.PHONY: all check run

all: run

check:
	@test -n "$(ROCM_HOME)" || { echo "ERROR: Set ROCM_HOME to the ROCm SDK directory."; exit 1; }
	@test -x "$(PYTHON)" || { echo "ERROR: Python is not executable: $(PYTHON)"; exit 1; }
	@test -f "$(SCRIPT)" || { echo "ERROR: Comparison script not found: $(SCRIPT)"; exit 1; }

run: check
	env \
	  ROCM_HOME="$(ROCM_HOME)" \
	  PYTHONPATH="$(ROCM_HOME)/share/amd_smi:$${PYTHONPATH}" \
	  LD_LIBRARY_PATH="$(ROCM_HOME)/lib:$(ROCM_HOME)/lib64:$${LD_LIBRARY_PATH}" \
	  "$(PYTHON)" "$(SCRIPT)"
