#!/usr/bin/env bash

# Run all four stages:
#   GPU_ID=1 ./testing/vllm/run_deepseek_moe_w4a8_workflow.sh all
# Individual stages: preflight, quick, pack, kernel, final, benchmark,
# and benchmark-one.

set -euo pipefail

script_dir="${BASH_SOURCE[0]%/*}"
if [[ "${script_dir}" == "${BASH_SOURCE[0]}" ]]; then
  script_dir="."
fi
readonly SCRIPT_DIR="$(cd -- "${script_dir}" && pwd)"
readonly ROCKBUILDER_HOME="${ROCKBUILDER_HOME:-$(cd -- "${SCRIPT_DIR}/../.." && pwd)}"
readonly MODEL_ROOT="${MODEL_ROOT:-/opt/rocm_sdk_models/hg}"
readonly BF16_MODEL="${BF16_MODEL:-${MODEL_ROOT}/deepseek-moe-16b-chat-bf16}"
readonly W8A8_MODEL="${W8A8_MODEL:-${MODEL_ROOT}/deepseek-moe-16b-W8A8}"
readonly QUICK_MODEL="${QUICK_MODEL:-${MODEL_ROOT}/deepseek-moe-16b-chat-W4A8-quick}"
readonly FINAL_MODEL="${FINAL_MODEL:-${MODEL_ROOT}/deepseek-moe-16b-chat-W4A8}"
readonly VENV_PYTHON="${VENV_PYTHON:-${ROCKBUILDER_HOME}/.venv/bin/python}"
readonly TOOLS_DIR="${TOOLS_DIR:-${HOME}/w4a8-tools-0.11}"
readonly GPU_ID="${GPU_ID:-0}"
readonly ROCM_HOME="${ROCM_HOME:-/opt/rcb/rocm_10_0_0}"
readonly RESULT_DIR="${RESULT_DIR:-${ROCKBUILDER_HOME}/results/w4a8}"
readonly STAGE="${1:-all}"


die() {
  echo "error: $*" >&2
  exit 1
}


require_file() {
  [[ -e "$1" ]] || die "required path does not exist: $1"
}


setup_environment() {
  require_file "${VENV_PYTHON}"
  require_file "${ROCM_HOME}/bin/rocm-smi"
  export ROCM_HOME
  export PATH="${ROCKBUILDER_HOME}/.venv/bin:${ROCM_HOME}/bin:/usr/bin:/bin"
  export LD_LIBRARY_PATH="${ROCM_HOME}/lib:${ROCM_HOME}/lib64:${ROCM_HOME}/lib/rocm_sysdeps/lib"
  export PYTHONPATH="${ROCM_HOME}/share/amd_smi"
  export HIP_VISIBLE_DEVICES="${GPU_ID}"
  export TOKENIZERS_PARALLELISM=false
  mkdir -p "${RESULT_DIR}"
}


setup_tools() {
  mkdir -p "${TOOLS_DIR}"
  if ! PYTHONPATH="${TOOLS_DIR}" "${VENV_PYTHON}" -c \
    "import llmcompressor, compressed_tensors, transformers" 2>/dev/null; then
    "${VENV_PYTHON}" -m pip install \
      --no-deps \
      --target "${TOOLS_DIR}" \
      llmcompressor==0.11.0 \
      compressed-tensors==0.16.0 \
      transformers==4.57.6 \
      tokenizers==0.22.2 \
      huggingface-hub==0.36.2 \
      datasets==4.8.5 \
      accelerate==1.13.0 \
      tqdm==4.67.3
  fi

  PYTHONPATH="${TOOLS_DIR}" "${VENV_PYTHON}" - <<'PY'
import compressed_tensors
import llmcompressor
import transformers

assert llmcompressor.__version__ == "0.11.0"
assert compressed_tensors.__version__ == "0.16.0"
assert transformers.__version__ == "4.57.6"
print("W4A8 quantization tools are ready.")
PY
}


preflight() {
  require_file "${BF16_MODEL}/config.json"
  require_file "${W8A8_MODEL}/config.json"
  setup_tools

  "${VENV_PYTHON}" - "${BF16_MODEL}" "${W8A8_MODEL}" <<'PY'
import json
import sys
from pathlib import Path

bf16_path = Path(sys.argv[1])
w8a8_path = Path(sys.argv[2])
bf16 = json.loads((bf16_path / "config.json").read_text())
w8a8 = json.loads((w8a8_path / "config.json").read_text())

assert not bf16.get("quantization_config"), "BF16 source is already quantized"
quant = w8a8.get("quantization_config")
assert quant, "W8A8 baseline is missing quantization_config"
print("BF16 source and W8A8 baseline metadata are valid.")
PY

  "${ROCM_HOME}/bin/rocm-smi" --showuse --showmeminfo vram
}


quantize_model() {
  local output_dir="$1"
  local samples="$2"
  local sequence_length="$3"
  local calibrate_all_experts="$4"
  local raw_output_dir="${output_dir}.unpacked"

  require_file "${BF16_MODEL}/config.json"
  setup_tools

  if [[ -e "${output_dir}" || -e "${raw_output_dir}" ]]; then
    [[ "${ALLOW_OVERWRITE:-0}" == "1" ]] || {
      die "output exists; set ALLOW_OVERWRITE=1 to replace ${output_dir}"
    }
    rm -rf "${output_dir}"
    rm -rf "${raw_output_dir}"
  fi

  PYTHONPATH="${TOOLS_DIR}:${ROCM_HOME}/share/amd_smi" "${VENV_PYTHON}" - \
    "${BF16_MODEL}" \
    "${raw_output_dir}" \
    "${samples}" \
    "${sequence_length}" \
    "${calibrate_all_experts}" <<'PY'
import sys

from llmcompressor import oneshot
from llmcompressor.modifiers.gptq import GPTQModifier
from transformers import AutoModelForCausalLM, AutoTokenizer

model_path, output_dir, samples, sequence_length, calibrate_all = sys.argv[1:]
samples = int(samples)
sequence_length = int(sequence_length)
calibrate_all = calibrate_all == "1"

model = AutoModelForCausalLM.from_pretrained(
    model_path,
    dtype="bfloat16",
    device_map="auto",
    trust_remote_code=True,
)
tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
recipe = GPTQModifier(
    targets="Linear",
    scheme="W4A8",
    ignore=[
        "lm_head",
        "re:.*mlp\\.gate$",
        "model.layers.0.mlp.down_proj",
    ],
    actorder=None,
)

oneshot(
    model=model,
    tokenizer=tokenizer,
    dataset="ultrachat-200k",
    splits={"calibration": f"train_sft[:{samples}]"},
    recipe=recipe,
    output_dir=output_dir,
    max_seq_length=sequence_length,
    num_calibration_samples=samples,
    moe_calibrate_all_experts=calibrate_all,
)
PY

  pack_checkpoint "${raw_output_dir}" "${output_dir}"
  if [[ "${KEEP_UNPACKED:-0}" != "1" ]]; then
    rm -rf "${raw_output_dir}"
  fi
  validate_checkpoint "${output_dir}"
}


pack_checkpoint() {
  local source_dir="$1"
  local output_dir="$2"

  "${VENV_PYTHON}" - "${source_dir}" "${output_dir}" <<'PY'
import gc
import json
import shutil
import sys
from pathlib import Path

import torch
from safetensors import safe_open
from safetensors.torch import load_file, save_file

source = Path(sys.argv[1])
output = Path(sys.argv[2])
output.mkdir(parents=True, exist_ok=False)

for path in source.iterdir():
    if path.suffix != ".safetensors":
        if path.is_dir():
            shutil.copytree(path, output / path.name)
        else:
            shutil.copy2(path, output / path.name)

shifts = torch.arange(8, dtype=torch.int32) * 4
renamed_weights = {}
for shard in sorted(source.glob("*.safetensors")):
    tensors = load_file(shard, device="cpu")
    packed = {}
    converted = 0
    for name, tensor in tensors.items():
        output_name = name
        if name.endswith(".weight") and tensor.dtype == torch.int8:
            if tensor.shape[-1] % 8 != 0:
                raise ValueError(
                    f"Cannot pack {name}: input dimension {tensor.shape[-1]} "
                    "is not divisible by 8."
                )
            values = (tensor.to(torch.int32) + 8) & 0xF
            tensor = torch.sum(
                values.view(*tensor.shape[:-1], tensor.shape[-1] // 8, 8)
                << shifts,
                dim=-1,
                dtype=torch.int32,
            ).contiguous()
            if ".experts." in name:
                tensor = tensor.transpose(-1, -2).contiguous()
            converted += 1
            output_name = f"{name[:-len('.weight')]}.weight_packed"
            renamed_weights[name] = output_name
        elif ".experts." in name and name.endswith(".weight_scale"):
            tensor = tensor.transpose(-1, -2).contiguous()
        packed[output_name] = tensor

    with safe_open(shard, framework="pt", device="cpu") as handle:
        metadata = handle.metadata()
    save_file(packed, output / shard.name, metadata=metadata)
    print(f"{shard.name}: packed {converted} INT4 weight tensors")
    del tensors, packed
    gc.collect()

config_path = output / "config.json"
config = json.loads(config_path.read_text())
quant = config["quantization_config"]
quant["format"] = "pack-quantized"
for group in quant["config_groups"].values():
    group["format"] = "pack-quantized"
config_path.write_text(json.dumps(config, indent=2) + "\n")

index_path = output / "model.safetensors.index.json"
if index_path.exists():
    index = json.loads(index_path.read_text())
    index["weight_map"] = {
        renamed_weights.get(name, name): shard
        for name, shard in index["weight_map"].items()
    }
    index["metadata"]["total_size"] = sum(
        shard.stat().st_size for shard in output.glob("*.safetensors")
    )
    index_path.write_text(json.dumps(index, indent=2) + "\n")
PY
}


validate_checkpoint() {
  local model_dir="$1"
  require_file "${model_dir}/config.json"

  "${VENV_PYTHON}" - "${model_dir}" <<'PY'
import json
import sys
from pathlib import Path

model_dir = Path(sys.argv[1])
config = json.loads((model_dir / "config.json").read_text())
quant = config["quantization_config"]
assert quant["format"] == "pack-quantized", quant["format"]
groups = quant["config_groups"]
assert groups, "W4A8 checkpoint has no config groups"

for name, group in groups.items():
    weight = group["weights"]
    activation = group["input_activations"]
    assert weight["num_bits"] == 4, (name, weight)
    assert weight["group_size"] == 128, (name, weight)
    assert weight["symmetric"], (name, weight)
    assert weight.get("actorder") is None, (name, weight)
    assert activation["num_bits"] == 8, (name, activation)
    assert activation["dynamic"], (name, activation)
    assert activation["strategy"] == "token", (name, activation)
    assert activation["symmetric"], (name, activation)

shards = list(model_dir.glob("*.safetensors"))
assert shards, "W4A8 checkpoint has no safetensors files"
print(f"Validated W4A8 metadata and {len(shards)} safetensors files.")
PY
}


validate_kernel() {
  local model_dir="${1:-${QUICK_MODEL}}"
  validate_checkpoint "${model_dir}"

  "${VENV_PYTHON}" - <<'PY'
from vllm.model_executor.layers.quantization.compressed_tensors.compressed_tensors_moe import (
    compressed_tensors_moe_w4a8_int8_rocm,
)

assert hasattr(
    compressed_tensors_moe_w4a8_int8_rocm,
    "CompressedTensorsW4A8Int8RocmMoEMethod",
)
print("ROCm W4A8 MoE backend is importable.")
PY

  run_model_benchmark \
    "${model_dir}" \
    "deepseek-moe-16b-w4a8-smoke" \
    1 \
    1 \
    16
}


run_model_benchmark() {
  local model_dir="$1"
  local label="$2"
  local warmup_runs="${3:-1}"
  local benchmark_runs="${4:-3}"
  local output_tokens="${5:-128}"
  local result_file="${RESULT_DIR}/${label}.csv"
  local extra_modifications
  local benchmark_script
  local -a benchmark_command
  benchmark_script="$(mktemp --suffix=.py)"
  trap "rm -f '${benchmark_script}'" RETURN

  require_file "${model_dir}/config.json"
  if [[ ! -v BENCHMARK_EXTRA_MODIFICATIONS ]]; then
    die "set BENCHMARK_EXTRA_MODIFICATIONS to 'none' or describe all overlays"
  fi
  extra_modifications="${BENCHMARK_EXTRA_MODIFICATIONS}"
  cat >"${benchmark_script}" <<'PY'
import csv
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import re
import socket
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import torch
from vllm import LLM, SamplingParams


def git_output(path: Path, *args: str) -> list[str]:
    output = subprocess.check_output(["git", "-C", str(path), *args], text=True)
    ret_arr = [
        line for line in output.splitlines()
        if line != "Streaming Performance Monitor (SPM) is not supported on gfx90a devices"
    ]
    return ret_arr


def git_state(path: Path) -> dict:
    ret = {
        "path": str(path),
        "commit": None,
        "tracked_changes": None,
    }
    if (path / ".git").exists():
        commits = git_output(path, "rev-parse", "HEAD")
        if len(commits) != 1 or re.fullmatch(r"[0-9a-f]{40}", commits[0]) is None:
            raise ValueError(f"invalid Git revision output for {path}: {commits}")
        ret["commit"] = commits[0]
        ret["tracked_changes"] = git_output(path, "status", "--short", "--untracked-files=no")
    return ret


def distribution_version(name: str) -> str | None:
    ret = None
    try:
        ret = importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        pass
    return ret


def module_origin(name: str) -> str | None:
    spec = importlib.util.find_spec(name)
    ret = spec.origin if spec is not None else None
    return ret


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    ret = digest.hexdigest()
    return ret


def patch_inventory(rockbuilder_home: Path) -> list[dict]:
    ret_arr = []
    patch_roots = (
        rockbuilder_home
        / "changes/patches/aiter/v0.1.21.post1/aiter/base",
        rockbuilder_home / "changes/patches/vllm/v0.28.0/vllm/base",
    )
    for root in patch_roots:
        if root.exists():
            for path in sorted(root.rglob("*.patch")):
                ret_arr.append(
                    {
                        "path": str(path.relative_to(rockbuilder_home)),
                        "sha256": sha256(path),
                    }
                )
    return ret_arr


def main():
    (
        model,
        label,
        result_file,
        warmup_runs,
        benchmark_runs,
        output_tokens,
        rockbuilder_home,
        extra_modifications,
        workflow_script,
    ) = sys.argv[1:]
    warmup_runs = int(warmup_runs)
    benchmark_runs = int(benchmark_runs)
    output_tokens = int(output_tokens)
    rockbuilder_home = Path(rockbuilder_home)
    workflow_script = Path(workflow_script)
    batch_size = 2
    prompts = [
        "Explain why deterministic GPU kernel validation matters.",
        "Describe one benefit of mixture-of-experts inference.",
    ]
    sampling = SamplingParams(
        temperature=0.0,
        max_tokens=output_tokens,
        min_tokens=output_tokens,
        ignore_eos=True,
    )
    torch_profile_dir = os.environ.get("BENCHMARK_TORCH_PROFILE_DIR")
    profiler_config = None
    if torch_profile_dir:
        Path(torch_profile_dir).mkdir(parents=True, exist_ok=True)
        profiler_config = {
            "profiler": "torch",
            "torch_profiler_dir": torch_profile_dir,
            "torch_profiler_with_stack": False,
        }
    llm = LLM(
        model=model,
        dtype="bfloat16",
        enforce_eager=True,
        gpu_memory_utilization=0.8,
        max_model_len=output_tokens + 64,
        max_num_seqs=batch_size,
        linear_backend="triton",
        moe_backend="triton",
        profiler_config=profiler_config,
        trust_remote_code=True,
    )

    for _ in range(warmup_runs):
        llm.generate(prompts, sampling, use_tqdm=False)

    completion_sample = ""
    throughputs = []
    if torch_profile_dir:
        llm.start_profile(label)
    try:
        for index in range(benchmark_runs):
            start = time.perf_counter()
            outputs = llm.generate(prompts, sampling, use_tqdm=False)
            elapsed = time.perf_counter() - start
            generated = sum(len(item.outputs[0].token_ids) for item in outputs)
            throughput = generated / elapsed
            throughputs.append(throughput)
            if index == 0:
                completion_sample = outputs[0].outputs[0].text
                print(f"Completion sample: {completion_sample!r}")
            print(
                f"Run {index + 1}/{benchmark_runs}: {elapsed:.3f} s, "
                f"{throughput:.2f} output tokens/s"
            )
    finally:
        if torch_profile_dir:
            llm.stop_profile()

    median = statistics.median(throughputs)
    model_path = Path(model)
    device = torch.cuda.current_device()
    properties = torch.cuda.get_device_properties(device)
    provenance = {
        "schema_version": 1,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "hostname": socket.gethostname(),
        "label": label,
        "model": {
            "path": model,
            "config_sha256": sha256(model_path / "config.json"),
        },
        "benchmark": {
            "warmup_runs": warmup_runs,
            "measured_runs": benchmark_runs,
            "batch_size": batch_size,
            "output_tokens": output_tokens,
            "linear_backend": "triton",
            "moe_backend": "triton",
            "enforce_eager": True,
            "torch_profile_dir": torch_profile_dir,
        },
        "gpu": {
            "logical_device": device,
            "name": properties.name,
            "architecture": getattr(properties, "gcnArchName", None),
            "total_memory": properties.total_memory,
        },
        "rocm": {
            "home": os.environ.get("ROCM_HOME"),
            "torch_hip_version": torch.version.hip,
        },
        "rockbuilder": git_state(rockbuilder_home),
        "aiter_source": git_state(
            rockbuilder_home / "src_apps/aiter_0_1_21_post1"
        ),
        "vllm_source": git_state(rockbuilder_home / "src_apps/vllm_0_28"),
        "installed_distributions": {
            name: distribution_version(name)
            for name in ("vllm", "amd-aiter", "flydsl", "mori")
        },
        "installed_modules": {
            name: module_origin(name)
            for name in ("vllm", "aiter", "flydsl", "mori")
        },
        "extra_modifications": extra_modifications,
        "environment": {
            name: os.environ.get(name)
            for name in (
                "HIP_VISIBLE_DEVICES",
                "ROCR_VISIBLE_DEVICES",
                "VLLM_ROCM_USE_AITER",
                "VLLM_ROCM_USE_AITER_LINEAR",
                "VLLM_ROCM_USE_AITER_MOE",
            )
        },
        "workflow": {
            "path": str(workflow_script),
            "sha256": sha256(workflow_script),
        },
        "patches": patch_inventory(rockbuilder_home),
    }
    provenance_path = Path(result_file).with_suffix(".provenance.json")
    provenance_path.write_text(json.dumps(provenance, indent=2) + "\n")
    with open(result_file, "w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            [
                "label",
                "median_output_tokens_per_second",
                "rockbuilder_commit",
                "vllm_version",
                "aiter_version",
                "extra_modifications",
                "provenance_file",
                "completion_sample",
            ]
        )
        writer.writerow(
            [
                label,
                f"{median:.6f}",
                provenance["rockbuilder"]["commit"],
                provenance["installed_distributions"]["vllm"],
                provenance["installed_distributions"]["amd-aiter"],
                extra_modifications,
                str(provenance_path),
                completion_sample,
            ]
        )
    print(f"Median output throughput: {median:.2f} tokens/s")
    print(f"Benchmark provenance: {provenance_path}")


if __name__ == "__main__":
    main()
PY

  benchmark_command=(
    "${VENV_PYTHON}" "${benchmark_script}" "${model_dir}" "${label}"
    "${result_file}" "${warmup_runs}" "${benchmark_runs}" "${output_tokens}"
    "${ROCKBUILDER_HOME}" "${extra_modifications}" "${BASH_SOURCE[0]}"
  )
  if [[ -n "${BENCHMARK_PROFILE_DIR:-}" ]]; then
    require_file "${ROCM_HOME}/bin/rocprofv3"
    mkdir -p "${BENCHMARK_PROFILE_DIR}"
    VLLM_ROCM_USE_AITER=1 VLLM_ROCM_USE_AITER_MOE=1 \
      "${ROCM_HOME}/bin/rocprofv3" --kernel-trace --stats --output-format csv \
      --output-directory "${BENCHMARK_PROFILE_DIR}" --output-file "${label}" \
      -- "${benchmark_command[@]}"
  else
    VLLM_ROCM_USE_AITER=1 VLLM_ROCM_USE_AITER_MOE=1 "${benchmark_command[@]}"
  fi
}


benchmark_all() {
  if [[ -e "${BF16_MODEL}/config.json" ]]; then
    run_model_benchmark "${BF16_MODEL}" "deepseek-moe-16b-bf16"
  fi
  run_model_benchmark "${W8A8_MODEL}" "deepseek-moe-16b-w8a8"
  run_model_benchmark "${FINAL_MODEL}" "deepseek-moe-16b-w4a8"
}


setup_environment
case "${STAGE}" in
  preflight)
    preflight
    ;;
  quick)
    quantize_model "${QUICK_MODEL}" 128 1024 0
    ;;
  pack)
    [[ $# -eq 3 ]] || die "pack requires source and output directories"
    pack_checkpoint "$2" "$3"
    validate_checkpoint "$3"
    ;;
  kernel)
    validate_kernel "${2:-${QUICK_MODEL}}"
    ;;
  final)
    quantize_model "${FINAL_MODEL}" 512 2048 1
    ;;
  benchmark)
    benchmark_all
    ;;
  benchmark-one)
    [[ $# -ge 3 && $# -le 6 ]] || die "benchmark-one requires model, label, and up to three run counts"
    run_model_benchmark "$2" "$3" "${4:-1}" "${5:-3}" "${6:-128}"
    ;;
  all)
    preflight
    quantize_model "${QUICK_MODEL}" 128 1024 0
    validate_kernel "${QUICK_MODEL}"
    quantize_model "${FINAL_MODEL}" 512 2048 1
    benchmark_all
    ;;
  *)
    die "unknown stage '${STAGE}'; expected preflight, quick, pack, kernel, final, benchmark, benchmark-one, or all"
    ;;
esac
