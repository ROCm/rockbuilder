#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.

set -uo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly -a TEST_NAMES=(
  "AITER FlyDSL FlashAttention"
  "vLLM AITER INT8 routing"
  "vLLM AITER INT8 runtime"
)
readonly -a TEST_SCRIPTS=(
  "${SCRIPT_DIR}/aiter/test_flydsl_fmha.py"
  "${SCRIPT_DIR}/vllm/test_gfx90a_int8_linear.py"
  "${SCRIPT_DIR}/vllm/test_int8_gate_compare.py"
)


main() {
  local -a test_results=()
  local index
  local overall_result=0

  for ((index = 0; index < ${#TEST_SCRIPTS[@]}; index++)); do
    printf '\n========== %s ==========\n' "${TEST_NAMES[index]}"
    if python3 "${TEST_SCRIPTS[index]}"; then
      test_results+=("PASSED")
    else
      test_results+=("FAILED")
      overall_result=1
    fi
  done

  printf '\n========== Test summary ==========\n'
  for ((index = 0; index < ${#TEST_NAMES[@]}; index++)); do
    printf '%-32s %s\n' "${TEST_NAMES[index]}" "${test_results[index]}"
  done

  return "${overall_result}"
}


main "$@"
