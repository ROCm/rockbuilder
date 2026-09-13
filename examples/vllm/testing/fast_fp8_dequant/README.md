# vLLM fast FP8 decoder comparison

This Python application compares:

1. vLLM's shipped `w8a8_triton_block_scaled_mm` wrapper.
2. The stock Triton FP8 decoder with the fast gate disabled.
3. The gfx90a fast decoder forced through the private Triton kernel.

The comparison makes the architecture gate visible. On gfx90a, eligible
inputs select the fast decoder through the shipped wrapper. Other GPUs retain
the stock decoder. The forced result shows whether extending the current
gfx90a-specific implementation would be useful; it does not change vLLM's
runtime gate.

## Coverage

The default FP8 block-scaled GEMM shape is `32x7168x5120` with `128x128`
quantization blocks, FP32 scales, E4M3 FN operands, and BF16 output. The
application reports:

- selected device and architecture;
- installed vLLM version;
- shipped fast-decoder eligibility;
- NaN propagation;
- HIP-event latency;
- speedup over the stock decoder;
- mean relative error; and
- correctness status.

The fast path is intentionally limited to gfx90a by the vLLM patch. The
disabled and forced paths can also be measured on gfx1100 and gfx1201 to
validate that exclusion.

## Run

Run from this directory after building and installing the patched vLLM wheel:

```bash
export ROCM_HOME=/path/to/rocm
make run
```

The Makefile defaults to RockBuilder's `.venv/bin/python`. Override it when
necessary:

```bash
make run PYTHON=/path/to/python
```

To change the workload or timing iterations:

```bash
make check
../../../../.venv/bin/python fast_fp8_dequant_compare.py \
  --rows 32 \
  --columns 7168 \
  --inner 5120 \
  --warmup 5 \
  --iterations 20
```

`--columns` and `--inner` must be multiples of 128. Expose only one GPU while
benchmarking. On a mixed-GPU host, for example:

```bash
ROCR_VISIBLE_DEVICES=0 make run
```

The direct stock and forced implementations use a private vLLM Triton kernel
and are release-specific comparison code, not public API examples.
