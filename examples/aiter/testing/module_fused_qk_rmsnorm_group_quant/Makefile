# SPDX-License-Identifier: MIT
# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.

THIS_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
ROCKBUILDER_DIR := $(abspath $(THIS_DIR)/../../../..)
AITER_SOURCE_DIR ?= $(ROCKBUILDER_DIR)/src_apps/aiter_0_1_21_post1

HIPCC = $(ROCM_HOME)/bin/hipcc
ENUMERATOR = $(ROCM_HOME)/bin/rocm_agent_enumerator
GPU_ARCH ?= $(shell "$(ENUMERATOR)" 2>/dev/null | awk '/^gfx/ && $$0 != "gfx000" { print; exit }')
ROCM_LIB_DIR = $(if $(wildcard $(ROCM_HOME)/lib/libamdhip64.so),$(ROCM_HOME)/lib,$(ROCM_HOME)/lib64)

TEST_SOURCE := $(THIS_DIR)/fused_qk_rmsnorm_group_quant_compare.cu
AITER_KERNEL := $(AITER_SOURCE_DIR)/csrc/kernels/fused_qk_rmsnorm_group_quant.cu
AITER_HEADER := $(AITER_SOURCE_DIR)/csrc/include/fused_qk_rmsnorm_group_quant.h
TARGET := $(THIS_DIR)/build/fused_qk_rmsnorm_group_quant_compare

CXXFLAGS ?= -O3
SUPPORTED_GPUS := gfx90a gfx1100 gfx1201

.PHONY: all build check clean run

all: build

check:
	@test -n "$(ROCM_HOME)" || { echo "ERROR: Set ROCM_HOME to the ROCm SDK directory."; exit 1; }
	@test -x "$(HIPCC)" || { echo "ERROR: $(HIPCC) is not executable."; exit 1; }
	@test -f "$(AITER_KERNEL)" || { echo "ERROR: AITER kernel not found: $(AITER_KERNEL)"; exit 1; }
	@test -f "$(AITER_HEADER)" || { echo "ERROR: AITER header not found: $(AITER_HEADER)"; exit 1; }
	@test -n "$(GPU_ARCH)" || { echo "ERROR: Set GPU_ARCH; GPU detection failed."; exit 1; }
	@echo "$(SUPPORTED_GPUS)" | tr ' ' '\n' | grep -Fxq "$(GPU_ARCH)" || { \
	  echo "ERROR: GPU_ARCH must be one of: $(SUPPORTED_GPUS)"; exit 1; \
	}

build: check
	@mkdir -p "$(dir $(TARGET))"
	"$(HIPCC)" \
	  -std=c++20 \
	  $(CXXFLAGS) \
	  -DENABLE_CK=0 \
	  "--offload-arch=$(GPU_ARCH)" \
	  -I"$(AITER_SOURCE_DIR)/csrc/include" \
	  "$(TEST_SOURCE)" \
	  "$(AITER_KERNEL)" \
	  -L"$(ROCM_LIB_DIR)" \
	  "-Wl,-rpath,$(ROCM_LIB_DIR)" \
	  -o "$(TARGET)"
	@echo "Built $(TARGET) for $(GPU_ARCH)"

run: build
	"$(TARGET)"

clean:
	rm -rf "$(THIS_DIR)/build"
