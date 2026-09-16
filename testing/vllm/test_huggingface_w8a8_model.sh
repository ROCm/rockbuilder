#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.

set -uo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
UTILS_PATH="${SCRIPT_DIR}/../utils.py"
DEFAULT_MODEL_PATH="${MODEL_BENCHMARK_DEFAULT_MODEL_PATH:-/opt/rocm_sdk_models/hg/Qwen3.5-4B-W8A8}"
QUANTIZATION_MODE="${MODEL_BENCHMARK_QUANTIZATION_MODE:-int8-w8a8}"
DISPLAY_SCRIPT_NAME="${MODEL_BENCHMARK_SCRIPT_NAME:-$(basename -- "$0")}"
MODEL_PATH="${DEFAULT_MODEL_PATH}"
RESULTS_DIR="${W8A8_BENCHMARK_RESULTS_DIR:-${SCRIPT_DIR}/results}"
RESULT_FILE=""
LABEL="${W8A8_BENCHMARK_LABEL:-}"
WARMUP_RUNS="${W8A8_BENCHMARK_WARMUP_RUNS:-1}"
BENCHMARK_RUNS="${W8A8_BENCHMARK_RUNS:-3}"
BATCH_SIZE="${W8A8_BENCHMARK_BATCH_SIZE:-2}"
OUTPUT_TOKENS="${W8A8_BENCHMARK_OUTPUT_TOKENS:-128}"
INPUT_TOKENS=""
EXECUTION_MODE=""
FP8_BACKEND=""
MOE_BACKEND="${W8A8_BENCHMARK_MOE_BACKEND:-}"
PYTHON_FILE="$(mktemp --tmpdir rockbuilder-w8a8-model.XXXXXX.py)"


cleanup() {
  rm -f "${PYTHON_FILE}"
}


fail() {
  printf '\nHugging Face model benchmark: FAILED\n%s\n' "$1" >&2
  return 1
}


usage() {
  cat <<EOF
Usage: ${DISPLAY_SCRIPT_NAME} [MODEL_PATH] [OPTIONS]

Run a repeatable vLLM quantized-model benchmark and save CSV results.

Options:
  --model PATH          Model directory (default: ${DEFAULT_MODEL_PATH})
  --results-dir PATH    Default result directory (default: ${RESULTS_DIR})
  --result-file PATH    Exact CSV result path
  --label TEXT          Label identifying this build or configuration
  --warmup-runs COUNT   Warmup generations (default: ${WARMUP_RUNS})
  --runs COUNT          Measured generations (default: ${BENCHMARK_RUNS})
  --batch-size COUNT    Prompts per generation (default: ${BATCH_SIZE})
  --input-tokens COUNT  Required tokens in each input prompt
  --output-tokens COUNT Tokens generated per prompt (default: ${OUTPUT_TOKENS})
  --execution-mode MODE Required mode: eager or default
  --fp8-backend BACKEND Required for block FP8: vllm or aiter
  --moe-backend BACKEND Optional INT8 MoE backend: triton or aiter
  -h, --help            Show this help

For INT8, the script respects VLLM_ROCM_USE_AITER and
VLLM_ROCM_USE_AITER_LINEAR, which both default to 1. For block FP8, the aiter
backend enables both variables. The vllm backend disables AITER linear kernels
and preserves an explicit VLLM_ROCM_USE_AITER value, which defaults to 0.

Set VLLM_BUILD_GIT_HASH or AITER_BUILD_GIT_HASH when a wheel does not retain
its source Git revision. Otherwise, the script records any revision available
from direct_url.json and always records each wheel's RECORD fingerprint.
EOF
}


parse_arguments() {
  local positional_model_set=0

  while (($# > 0)); do
    case "$1" in
      --model)
        MODEL_PATH="${2:?--model requires a path}"
        positional_model_set=1
        shift 2
        ;;
      --results-dir)
        RESULTS_DIR="${2:?--results-dir requires a path}"
        shift 2
        ;;
      --result-file)
        RESULT_FILE="${2:?--result-file requires a path}"
        shift 2
        ;;
      --label)
        LABEL="${2:?--label requires text}"
        shift 2
        ;;
      --warmup-runs)
        WARMUP_RUNS="${2:?--warmup-runs requires a count}"
        shift 2
        ;;
      --runs)
        BENCHMARK_RUNS="${2:?--runs requires a count}"
        shift 2
        ;;
      --batch-size)
        BATCH_SIZE="${2:?--batch-size requires a count}"
        shift 2
        ;;
      --input-tokens)
        INPUT_TOKENS="${2:?--input-tokens requires a count}"
        shift 2
        ;;
      --output-tokens)
        OUTPUT_TOKENS="${2:?--output-tokens requires a count}"
        shift 2
        ;;
      --execution-mode)
        EXECUTION_MODE="${2:?--execution-mode requires a mode}"
        shift 2
        ;;
      --fp8-backend)
        FP8_BACKEND="${2:?--fp8-backend requires a backend}"
        shift 2
        ;;
      --moe-backend)
        MOE_BACKEND="${2:?--moe-backend requires a backend}"
        shift 2
        ;;
      -h | --help)
        usage
        return 2
        ;;
      -*)
        fail "unknown option: $1"
        return 1
        ;;
      *)
        if ((positional_model_set != 0)); then
          fail "only one positional model path is accepted"
          return 1
        fi
        MODEL_PATH="$1"
        positional_model_set=1
        shift
        ;;
    esac
  done
  return 0
}


validate_positive_integer() {
  local name="$1"
  local value="$2"

  if [[ ! "${value}" =~ ^[1-9][0-9]*$ ]]; then
    fail "${name} must be a positive integer: ${value}"
    return 1
  fi
  return 0
}


main() {
  local argument_status
  local label_slug
  local log_file
  local python_status
  local run_id
  local selected_linear_kernel

  trap cleanup EXIT

  parse_arguments "$@"
  argument_status=$?
  if ((argument_status == 2)); then
    return 0
  fi
  if ((argument_status != 0)); then
    return 1
  fi
  if [[ "${QUANTIZATION_MODE}" != "int8-w8a8" && "${QUANTIZATION_MODE}" != "fp8-block" ]]; then
    fail "unsupported model benchmark quantization mode: ${QUANTIZATION_MODE}"
    return 1
  fi

  validate_positive_integer "warmup run count" "${WARMUP_RUNS}" || return 1
  validate_positive_integer "benchmark run count" "${BENCHMARK_RUNS}" || return 1
  validate_positive_integer "batch size" "${BATCH_SIZE}" || return 1
  validate_positive_integer "output token count" "${OUTPUT_TOKENS}" || return 1
  if [[ -z "${INPUT_TOKENS}" && -z "${EXECUTION_MODE}" ]]; then
    fail "required workload parameters are missing:
- --input-tokens: use 32 for decode, 256 for mixed, or 1024 for prefill
- --execution-mode: use eager for kernel comparisons or default for normal vLLM execution"
    return 1
  fi
  if [[ -z "${INPUT_TOKENS}" ]]; then
    fail "--input-tokens is required; use 32 for decode, 256 for mixed, or 1024 for prefill"
    return 1
  fi
  if [[ -z "${EXECUTION_MODE}" ]]; then
    fail "--execution-mode is required; use eager for kernel comparisons or default for normal vLLM execution"
    return 1
  fi
  validate_positive_integer "input token count" "${INPUT_TOKENS}" || return 1
  if [[ "${EXECUTION_MODE}" != "eager" && "${EXECUTION_MODE}" != "default" ]]; then
    fail "invalid execution mode: ${EXECUTION_MODE}; use eager or default"
    return 1
  fi
  if [[ "${QUANTIZATION_MODE}" == "fp8-block" && -z "${FP8_BACKEND}" ]]; then
    fail "--fp8-backend is required for block FP8; use vllm or aiter"
    return 1
  fi
  if [[ -n "${FP8_BACKEND}" && "${FP8_BACKEND}" != "vllm" && "${FP8_BACKEND}" != "aiter" ]]; then
    fail "invalid FP8 backend: ${FP8_BACKEND}; use vllm or aiter"
    return 1
  fi
  if [[ -n "${MOE_BACKEND}" && "${MOE_BACKEND}" != "triton" && "${MOE_BACKEND}" != "aiter" ]]; then
    fail "invalid MoE backend: ${MOE_BACKEND}; use triton or aiter"
    return 1
  fi

  if ! python3 "${UTILS_PATH}"; then
    fail "test environment validation failed"
    return 1
  fi

  if [[ ! -f "${MODEL_PATH}/config.json" ]]; then
    fail "model config does not exist: ${MODEL_PATH}/config.json"
    return 1
  fi

  if ! compgen -G "${MODEL_PATH}/*.safetensors" >/dev/null; then
    fail "model weights do not exist below ${MODEL_PATH}"
    return 1
  fi

  export HF_HUB_OFFLINE=1
  export PYTORCH_ALLOC_CONF="${PYTORCH_ALLOC_CONF:-expandable_segments:True}"
  export TOKENIZERS_PARALLELISM=false
  if [[ "${QUANTIZATION_MODE}" == "fp8-block" ]]; then
    if [[ "${FP8_BACKEND}" == "aiter" ]]; then
      export VLLM_ROCM_USE_AITER=1
      export VLLM_ROCM_USE_AITER_LINEAR=1
    else
      export VLLM_ROCM_USE_AITER="${VLLM_ROCM_USE_AITER:-0}"
      export VLLM_ROCM_USE_AITER_LINEAR=0
    fi
  else
    export VLLM_ROCM_USE_AITER="${VLLM_ROCM_USE_AITER:-1}"
    export VLLM_ROCM_USE_AITER_LINEAR="${VLLM_ROCM_USE_AITER_LINEAR:-1}"
  fi

  if [[ -z "${LABEL}" ]]; then
    if [[ "${VLLM_ROCM_USE_AITER}" == "1" && "${VLLM_ROCM_USE_AITER_LINEAR}" == "1" ]]; then
      LABEL="aiter-on"
    else
      LABEL="aiter-off"
    fi
  fi
  label_slug="${LABEL//[^[:alnum:]_.-]/_}"
  run_id="$(date -u +%Y%m%dT%H%M%SZ)-${label_slug}-$$"
  if [[ -z "${RESULT_FILE}" ]]; then
    RESULT_FILE="${RESULTS_DIR}/${run_id}.csv"
  fi
  if [[ "${RESULT_FILE}" == *.csv ]]; then
    log_file="${RESULT_FILE%.csv}.log"
  else
    log_file="${RESULT_FILE}.log"
  fi

  mkdir -p "$(dirname -- "${RESULT_FILE}")" "$(dirname -- "${log_file}")"
  if [[ -e "${RESULT_FILE}" || -e "${log_file}" ]]; then
    fail "result or log file already exists; select a new --result-file"
    return 1
  fi

  printf '\nRunning Hugging Face quantized-model benchmark\n'
  printf 'Model: %s\n' "${MODEL_PATH}"
  printf 'Quantization mode: %s\n' "${QUANTIZATION_MODE}"
  printf 'Label: %s\n' "${LABEL}"
  printf 'VLLM_ROCM_USE_AITER: %s\n' "${VLLM_ROCM_USE_AITER}"
  printf 'VLLM_ROCM_USE_AITER_LINEAR: %s\n' "${VLLM_ROCM_USE_AITER_LINEAR}"
  printf 'Input tokens per request: %s\n' "${INPUT_TOKENS}"
  printf 'Execution mode: %s\n' "${EXECUTION_MODE}"
  printf 'Requested FP8 backend: %s\n' "${FP8_BACKEND:-not applicable}"
  printf 'Requested MoE backend: %s\n' "${MOE_BACKEND:-auto}"
  printf 'Result: %s\n' "${RESULT_FILE}"
  printf 'Log: %s\n' "${log_file}"

  cat >"${PYTHON_FILE}" <<'PYTHON'
import csv
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import statistics
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote, urlparse


SUPPORTED_ARCHITECTURES = {"gfx90a", "gfx1100", "gfx1201"}


def environment_enabled(name: str) -> bool:
    value = os.environ.get(name, "")
    ret = value.lower() in {"1", "true", "yes", "on"}
    return ret


def distribution_info(
    distribution_names: tuple[str, ...],
    module_path: str,
    git_hash_environment_name: str,
) -> dict[str, str | None]:
    distribution = None
    for distribution_name in distribution_names:
        try:
            distribution = importlib.metadata.distribution(distribution_name)
        except importlib.metadata.PackageNotFoundError:
            pass
        if distribution is not None:
            break

    git_hash = os.environ.get(git_hash_environment_name) or None
    if distribution is None:
        ret = {
            "distribution": None,
            "version": None,
            "record_sha256": None,
            "git_hash": git_hash,
            "module_path": module_path,
        }
    else:
        record = distribution.read_text("RECORD")
        record_sha256 = None
        if record is not None:
            record_sha256 = hashlib.sha256(record.encode("utf-8")).hexdigest()

        direct_url_text = distribution.read_text("direct_url.json")
        if direct_url_text is not None and git_hash is None:
            direct_url = json.loads(direct_url_text)
            git_hash = direct_url.get("vcs_info", {}).get("commit_id")
            source_url = direct_url.get("url", "")
            if git_hash is None and source_url.startswith("file://"):
                source_path = Path(unquote(urlparse(source_url).path))
                if source_path.is_dir():
                    completed = subprocess.run(
                        ["git", "-C", str(source_path), "rev-parse", "HEAD"],
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    if completed.returncode == 0:
                        git_hash = completed.stdout.strip()

        if git_hash is None:
            version_match = re.search(
                r"(?:^|[.+])g([0-9a-f]{7,40})(?:[.+]|$)",
                distribution.version.lower(),
            )
            if version_match is not None:
                git_hash = version_match.group(1)

        ret = {
            "distribution": distribution.metadata["Name"],
            "version": distribution.version,
            "record_sha256": record_sha256,
            "git_hash": git_hash,
            "module_path": module_path,
        }
    return ret


def build_prompts(tokenizer, tokens_prompt_type, batch_size: int, input_tokens: int):
    base_prompts = (
        "In two sentences, explain why deterministic software tests are useful.",
        "List three considerations when comparing GPU inference performance.",
        "Explain how quantized matrix multiplication reduces model memory use.",
        "Describe why GPU benchmarks need warmup iterations.",
    )
    ret_arr = []
    for index in range(batch_size):
        source_text = f"Request {index + 1}: {base_prompts[index % len(base_prompts)]}"
        source_token_ids = tokenizer.encode(source_text, add_special_tokens=False)
        if not source_token_ids:
            raise RuntimeError("tokenizer produced an empty benchmark prompt")
        repeat_count = (input_tokens + len(source_token_ids) - 1) // len(source_token_ids)
        prompt_token_ids = (source_token_ids * repeat_count)[:input_tokens]
        ret_arr.append(tokens_prompt_type(prompt_token_ids=prompt_token_ids))
    return ret_arr


def run_generation(
    llm,
    prompts,
    sampling_parameters,
    torch,
    use_tqdm: bool,
) -> dict[str, float | int]:
    torch.cuda.synchronize()
    start_time = time.perf_counter()
    outputs = llm.generate(prompts, sampling_parameters, use_tqdm=use_tqdm)
    torch.cuda.synchronize()
    elapsed_seconds = time.perf_counter() - start_time

    prompt_tokens = 0
    output_tokens = 0
    for index, output in enumerate(outputs, start=1):
        generated = output.outputs[0]
        if not generated.token_ids:
            raise RuntimeError(f"prompt {index} generated no tokens")
        prompt_tokens += len(output.prompt_token_ids or ())
        output_tokens += len(generated.token_ids)

    ret = {
        "elapsed_seconds": elapsed_seconds,
        "requests": len(outputs),
        "prompt_tokens": prompt_tokens,
        "output_tokens": output_tokens,
        "request_throughput": len(outputs) / elapsed_seconds,
        "prompt_tokens_per_second": prompt_tokens / elapsed_seconds,
        "output_tokens_per_second": output_tokens / elapsed_seconds,
        "total_tokens_per_second": (prompt_tokens + output_tokens) / elapsed_seconds,
    }
    return ret


def summarize_runs(runs: list[dict[str, float | int]]) -> dict[str, float]:
    total_elapsed = sum(float(run["elapsed_seconds"]) for run in runs)
    total_output_tokens = sum(int(run["output_tokens"]) for run in runs)
    ret = {
        "median_elapsed_seconds": statistics.median(float(run["elapsed_seconds"]) for run in runs),
        "median_request_throughput": statistics.median(float(run["request_throughput"]) for run in runs),
        "median_output_tokens_per_second": statistics.median(
            float(run["output_tokens_per_second"]) for run in runs
        ),
        "min_output_tokens_per_second": min(float(run["output_tokens_per_second"]) for run in runs),
        "max_output_tokens_per_second": max(float(run["output_tokens_per_second"]) for run in runs),
        "aggregate_output_tokens_per_second": total_output_tokens / total_elapsed,
    }
    return ret


def annotate_result() -> None:
    result_path = Path(sys.argv[2]).resolve()
    selected_linear_kernel = sys.argv[3]
    with result_path.open(encoding="utf-8", newline="") as result_file:
        reader = csv.DictReader(result_file)
        rows = list(reader)
        fieldnames = reader.fieldnames

    if fieldnames is None or len(rows) != 1:
        raise RuntimeError("benchmark CSV must contain exactly one result row")
    rows[0]["selected_linear_kernel"] = selected_linear_kernel
    if selected_linear_kernel == "TritonFp8BlockScaledMMKernel":
        selected_fp8_implementation = "vllm-triton"
    elif (
        selected_linear_kernel == "AiterFp8BlockScaledMMKernel"
        and rows[0]["gpu_architecture"] == "gfx90a"
    ):
        selected_fp8_implementation = "aiter-triton-fallback"
    elif selected_linear_kernel == "AiterFp8BlockScaledMMKernel":
        selected_fp8_implementation = "aiter-runtime-selected"
    else:
        selected_fp8_implementation = "not applicable or unreported"
    rows[0]["selected_fp8_implementation"] = selected_fp8_implementation

    temporary_path = result_path.with_suffix(f"{result_path.suffix}.tmp")
    with temporary_path.open("w", encoding="utf-8", newline="") as result_file:
        writer = csv.DictWriter(result_file, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    temporary_path.replace(result_path)


def main() -> None:
    import aiter
    import torch
    import vllm
    from vllm import LLM, SamplingParams
    from vllm.inputs import TokensPrompt

    model_path = Path(sys.argv[1]).resolve()
    result_path = Path(sys.argv[2]).resolve()
    label = sys.argv[3]
    warmup_runs = int(sys.argv[4])
    benchmark_runs = int(sys.argv[5])
    batch_size = int(sys.argv[6])
    output_tokens = int(sys.argv[7])
    log_path = Path(sys.argv[8]).resolve()
    input_tokens = int(sys.argv[9])
    execution_mode = sys.argv[10]
    quantization_mode = sys.argv[11]
    requested_fp8_backend = sys.argv[12] or None
    requested_moe_backend = sys.argv[13] or None
    started_at = datetime.now(UTC)

    if not torch.cuda.is_available():
        raise RuntimeError("a visible ROCm GPU is required")
    if torch.cuda.device_count() != 1:
        raise RuntimeError(
            "exactly one GPU must be visible; set ROCR_VISIBLE_DEVICES to the GPU index"
        )

    properties = torch.cuda.get_device_properties(0)
    architecture = properties.gcnArchName.split(":", 1)[0]
    if architecture not in SUPPORTED_ARCHITECTURES:
        raise RuntimeError(f"unsupported GPU architecture: {architecture}")

    with (model_path / "config.json").open(encoding="utf-8") as config_file:
        model_config = json.load(config_file)
    model_name = (
        model_config.get("_name_or_path")
        or model_config.get("model_name")
        or model_path.name
    )

    quantization_config = model_config.get("quantization_config", {})
    if quantization_mode == "int8-w8a8":
        config_groups = quantization_config.get("config_groups", {}).values()
        is_compressed_tensors_w8a8 = any(
            group.get("weights", {}).get("num_bits") == 8
            and group.get("weights", {}).get("type") == "int"
            and group.get("input_activations", {}).get("num_bits") == 8
            and group.get("input_activations", {}).get("type") == "int"
            for group in config_groups
        )
        global_quant_config = quantization_config.get("global_quant_config", {})
        quark_weight = global_quant_config.get("weight", {})
        quark_input = global_quant_config.get("input_tensors", {})
        is_quark_w8a8 = (
            quantization_config.get("quant_method") == "quark"
            and quark_weight.get("dtype") == "int8"
            and quark_input.get("dtype") == "int8"
        )
        is_expected_quantization = is_compressed_tensors_w8a8 or is_quark_w8a8
        quantization_name = "INT8 W8A8"
    else:
        is_expected_quantization = (
            quantization_config.get("quant_method") == "fp8"
            and quantization_config.get("activation_scheme") == "dynamic"
            and quantization_config.get("weight_block_size") == [128, 128]
            and quantization_config.get("fmt", "e4m3") == "e4m3"
        )
        quantization_name = "FP8 E4M3 block 128x128"
    if not is_expected_quantization:
        raise RuntimeError(
            f"model config does not match benchmark quantization mode: {quantization_mode}"
        )

    print(f"Device: {properties.name}")
    print(f"Architecture: {architecture}")
    print(f"VRAM: {properties.total_memory / 1024**3:.1f} GiB")
    print(f"Quantization: {quantization_name}")

    use_aiter = environment_enabled("VLLM_ROCM_USE_AITER")
    use_aiter_linear = environment_enabled("VLLM_ROCM_USE_AITER_LINEAR")
    if quantization_mode == "fp8-block" and requested_fp8_backend == "aiter":
        from vllm._aiter_ops import rocm_aiter_ops

        aiter_fp8_supported = (
            rocm_aiter_ops.is_block_fp8_linear_enabled()
            or rocm_aiter_ops.is_rdna_linear_enabled()
        )
        if not aiter_fp8_supported:
            raise RuntimeError(
                "AiterFp8BlockScaledMMKernel is disabled by this vLLM build "
                f"or environment on {architecture}"
            )
    force_aiter_linear = use_aiter and use_aiter_linear and (
        quantization_mode == "int8-w8a8" or requested_fp8_backend == "aiter"
    )
    dtype = "bfloat16"
    enforce_eager = execution_mode == "eager"
    gpu_memory_utilization = 0.80
    limit_mm_per_prompt = {"image": 0, "video": 0}
    max_model_len = input_tokens + output_tokens
    max_num_seqs = batch_size
    seed = 0
    tensor_parallel_size = 1
    trust_remote_code = True
    llm_arguments = {
        "model": str(model_path),
        "dtype": dtype,
        "enforce_eager": enforce_eager,
        "gpu_memory_utilization": gpu_memory_utilization,
        "limit_mm_per_prompt": limit_mm_per_prompt,
        "max_model_len": max_model_len,
        "max_num_seqs": max_num_seqs,
        "seed": seed,
        "tensor_parallel_size": tensor_parallel_size,
        "trust_remote_code": trust_remote_code,
    }
    if force_aiter_linear:
        llm_arguments["linear_backend"] = "aiter"
    if requested_moe_backend is not None:
        llm_arguments["moe_backend"] = requested_moe_backend

    initialization_start = time.perf_counter()
    llm = LLM(**llm_arguments)
    initialization_seconds = time.perf_counter() - initialization_start
    tokenizer = llm.get_tokenizer()
    prompts = build_prompts(tokenizer, TokensPrompt, batch_size, input_tokens)
    prompt_set_sha256 = hashlib.sha256(
        json.dumps(
            [prompt["prompt_token_ids"] for prompt in prompts],
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    temperature = 0.0
    ignore_eos = True
    use_tqdm = False
    sampling_parameters = SamplingParams(
        temperature=temperature,
        max_tokens=output_tokens,
        ignore_eos=ignore_eos,
    )

    print(f"Linear backend argument: {'aiter' if force_aiter_linear else 'auto'}")
    print(f"Warmup runs: {warmup_runs}")
    print(f"Measured runs: {benchmark_runs}")
    print(f"Batch size: {batch_size}")
    print(f"Output tokens per request: {output_tokens}")

    for warmup_index in range(warmup_runs):
        run_generation(llm, prompts, sampling_parameters, torch, use_tqdm)
        print(f"Warmup {warmup_index + 1}/{warmup_runs}: complete")

    torch.cuda.reset_peak_memory_stats()
    runs = []
    for run_index in range(benchmark_runs):
        run = run_generation(llm, prompts, sampling_parameters, torch, use_tqdm)
        run["run"] = run_index + 1
        runs.append(run)
        print(
            f"Run {run_index + 1}/{benchmark_runs}: "
            f"{run['elapsed_seconds']:.3f} s, "
            f"{run['output_tokens_per_second']:.2f} output tokens/s"
        )

    summary = summarize_runs(runs)
    software = {
        "python": platform.python_version(),
        "torch": torch.__version__,
        "rocm": torch.version.hip,
        "vllm": distribution_info(
            ("vllm",),
            str(Path(vllm.__file__).resolve()),
            "VLLM_BUILD_GIT_HASH",
        ),
        "aiter": distribution_info(
            ("amd-aiter", "amd_aiter", "aiter"),
            str(Path(aiter.__file__).resolve()),
            "AITER_BUILD_GIT_HASH",
        ),
    }
    vllm_info = software["vllm"]
    aiter_info = software["aiter"]
    vllm_revision = vllm_info["git_hash"] or "unavailable"
    aiter_revision = aiter_info["git_hash"] or "unavailable"
    remark = (
        f"Model={model_name}; GPU={properties.name} ({architecture}); "
        f"vLLM={vllm_info['version']} (git={vllm_revision}); "
        f"AITER={aiter_info['version']} (git={aiter_revision}); "
        f"FP8 backend={requested_fp8_backend or 'not applicable'}; "
        f"MoE backend={requested_moe_backend or 'auto'}; "
        f"VLLM_ROCM_USE_AITER={os.environ.get('VLLM_ROCM_USE_AITER')}; "
        f"VLLM_ROCM_USE_AITER_LINEAR={os.environ.get('VLLM_ROCM_USE_AITER_LINEAR')}"
    )
    completed_at = datetime.now(UTC)
    result = {
        "schema_version": 3,
        "label": label,
        "started_at_utc": started_at.isoformat(),
        "completed_at_utc": completed_at.isoformat(),
        "host": platform.node(),
        "model_name": model_name,
        "model_directory_name": model_path.name,
        "model_path": str(model_path),
        "model_config_sha256": hashlib.sha256(
            (model_path / "config.json").read_bytes()
        ).hexdigest(),
        "quantization_mode": quantization_mode,
        "quantization": quantization_name,
        "gpu_name": properties.name,
        "gpu_architecture": architecture,
        "gpu_vram_gib": properties.total_memory / 1024**3,
        "python_version": software["python"],
        "torch_version": software["torch"],
        "rocm_version": software["rocm"],
        "vllm_version": vllm_info["version"],
        "vllm_git_hash": vllm_info["git_hash"],
        "vllm_record_sha256": vllm_info["record_sha256"],
        "vllm_module_path": vllm_info["module_path"],
        "aiter_version": aiter_info["version"],
        "aiter_git_hash": aiter_info["git_hash"],
        "aiter_record_sha256": aiter_info["record_sha256"],
        "aiter_module_path": aiter_info["module_path"],
        "rocm_home": os.environ.get("ROCM_HOME"),
        "virtual_env": os.environ.get("VIRTUAL_ENV"),
        "rocr_visible_devices": os.environ.get("ROCR_VISIBLE_DEVICES"),
        "hip_visible_devices": os.environ.get("HIP_VISIBLE_DEVICES"),
        "vllm_rocm_use_aiter": os.environ.get("VLLM_ROCM_USE_AITER"),
        "vllm_rocm_use_aiter_linear": os.environ.get(
            "VLLM_ROCM_USE_AITER_LINEAR"
        ),
        "hf_hub_offline": os.environ.get("HF_HUB_OFFLINE"),
        "pytorch_alloc_conf": os.environ.get("PYTORCH_ALLOC_CONF"),
        "tokenizers_parallelism": os.environ.get("TOKENIZERS_PARALLELISM"),
        "linear_backend_argument": "aiter" if force_aiter_linear else "auto",
        "requested_fp8_backend": requested_fp8_backend,
        "requested_moe_backend": requested_moe_backend,
        "selected_linear_kernel": "",
        "selected_fp8_implementation": "",
        "gfx90a_fast_fp8_candidate": (
            quantization_mode == "fp8-block" and architecture == "gfx90a"
        ),
        "warmup_runs": warmup_runs,
        "measured_runs": benchmark_runs,
        "batch_size": batch_size,
        "input_tokens_per_request": input_tokens,
        "execution_mode": execution_mode,
        "prompt_count": len(prompts),
        "prompt_source": "repeated deterministic text, rockbuilder-v1",
        "prompt_set_sha256": prompt_set_sha256,
        "output_tokens_per_request": output_tokens,
        "temperature": temperature,
        "ignore_eos": ignore_eos,
        "use_tqdm": use_tqdm,
        "dtype": dtype,
        "enforce_eager": enforce_eager,
        "gpu_memory_utilization": gpu_memory_utilization,
        "limit_mm_image": limit_mm_per_prompt["image"],
        "limit_mm_video": limit_mm_per_prompt["video"],
        "max_model_len": max_model_len,
        "max_num_seqs": max_num_seqs,
        "seed": seed,
        "tensor_parallel_size": tensor_parallel_size,
        "trust_remote_code": trust_remote_code,
        "model_initialization_seconds": initialization_seconds,
        "prompt_tokens_per_run": runs[0]["prompt_tokens"],
        "output_tokens_per_run": runs[0]["output_tokens"],
        "run_elapsed_seconds": ";".join(
            f"{float(run['elapsed_seconds']):.6f}" for run in runs
        ),
        "run_output_tokens_per_second": ";".join(
            f"{float(run['output_tokens_per_second']):.6f}" for run in runs
        ),
        "median_elapsed_seconds": summary["median_elapsed_seconds"],
        "median_request_throughput": summary["median_request_throughput"],
        "median_output_tokens_per_second": summary[
            "median_output_tokens_per_second"
        ],
        "min_output_tokens_per_second": summary["min_output_tokens_per_second"],
        "max_output_tokens_per_second": summary["max_output_tokens_per_second"],
        "aggregate_output_tokens_per_second": summary[
            "aggregate_output_tokens_per_second"
        ],
        "log_path": str(log_path),
        "remark": remark,
    }
    with result_path.open("w", encoding="utf-8", newline="") as result_file:
        writer = csv.DictWriter(
            result_file,
            fieldnames=list(result),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerow(result)

    print(f"Median output throughput: {summary['median_output_tokens_per_second']:.2f} tokens/s")
    print(f"Aggregate output throughput: {summary['aggregate_output_tokens_per_second']:.2f} tokens/s")
    print(f"Benchmark result: {result_path}")
    print("Model benchmark: PASSED")


if __name__ == "__main__":
    if sys.argv[1] == "--annotate":
        annotate_result()
    else:
        main()
PYTHON
  python3 "${PYTHON_FILE}" \
    "${MODEL_PATH}" \
    "${RESULT_FILE}" \
    "${LABEL}" \
    "${WARMUP_RUNS}" \
    "${BENCHMARK_RUNS}" \
    "${BATCH_SIZE}" \
    "${OUTPUT_TOKENS}" \
    "${log_file}" \
    "${INPUT_TOKENS}" \
    "${EXECUTION_MODE}" \
    "${QUANTIZATION_MODE}" \
    "${FP8_BACKEND}" \
    "${MOE_BACKEND}" \
    2>&1 | tee "${log_file}"
  python_status="${PIPESTATUS[0]}"

  if ((python_status != 0)); then
    fail "model benchmark exited with code ${python_status}; log: ${log_file}"
    return 1
  fi

  selected_linear_kernel="unreported"
  if grep -Fq "Selected AiterInt8ScaledMMLinearKernel" "${log_file}"; then
    selected_linear_kernel="AiterInt8ScaledMMLinearKernel"
  elif grep -Fq "Selected AiterFp8BlockScaledMMKernel" "${log_file}"; then
    selected_linear_kernel="AiterFp8BlockScaledMMKernel"
  elif grep -Fq "Selected TritonFp8BlockScaledMMKernel" "${log_file}"; then
    selected_linear_kernel="TritonFp8BlockScaledMMKernel"
  fi

  if ! python3 "${PYTHON_FILE}" \
    --annotate \
    "${RESULT_FILE}" \
    "${selected_linear_kernel}"; then
    fail "could not annotate benchmark result: ${RESULT_FILE}"
    return 1
  fi

  if [[ "${QUANTIZATION_MODE}" == "fp8-block" ]]; then
    if [[ "${FP8_BACKEND}" == "vllm" \
      && "${selected_linear_kernel}" != "TritonFp8BlockScaledMMKernel" ]]; then
      fail "vLLM did not report selecting TritonFp8BlockScaledMMKernel"
      return 1
    fi
    if [[ "${FP8_BACKEND}" == "aiter" \
      && "${selected_linear_kernel}" != "AiterFp8BlockScaledMMKernel" ]]; then
      fail "vLLM did not report selecting AiterFp8BlockScaledMMKernel"
      return 1
    fi
  fi

  printf 'Selected linear kernel: %s\n' "${selected_linear_kernel}"
  printf '\nHugging Face model benchmark: PASSED\n'
  printf 'Result: %s\n' "${RESULT_FILE}"
  printf 'Log: %s\n' "${log_file}"
  return 0
}


main "$@"
