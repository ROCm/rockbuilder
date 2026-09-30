#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.

set -uo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

export MODEL_BENCHMARK_DEFAULT_MODEL_PATH="/opt/rocm_sdk_models/hg/Qwen3-4B-FP8"
export MODEL_BENCHMARK_QUANTIZATION_MODE="fp8-block"
export MODEL_BENCHMARK_SCRIPT_NAME="$(basename -- "$0")"

exec "${SCRIPT_DIR}/test_huggingface_w8a8_model.sh" "$@"
