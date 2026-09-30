# vLLM AITER INT8 gate comparison

This Python application reports vLLM's shipped AITER INT8 gate state and
compares three A8W8 GEMM routes:

1. AITER Triton, representing the gate-disabled route used for this comparison.
2. AITER's default backend.
3. vLLM's actual gate-enabled AITER route.

The gate-enabled implementation selects AITER's default route for gfx90a
(normally CK, with Triton fallback for unsupported shapes), Triton for gfx1100,
and CKTile for gfx1200 and gfx1201 from the input tensor's device. The
application calls that vLLM implementation directly and reports a route
failure before benchmarking if the installed vLLM and AITER packages are
incompatible.

## Supported GPUs

The full comparison requires an AITER installation containing the RockBuilder
INT8 backend and fallback patches and runs on:

- `gfx90a`
- `gfx1100`
- `gfx1200`
- `gfx1201`

The default shapes are:

- `1x1280x8192`, representing a tiny-token workload where Triton is expected
  to remain preferable.
- `32x8192x1024`, representing a shape where the tuned CKTile path is useful.
- `256x1280x8192`, representing a larger activation batch.

## Run

Run from this directory after building and installing the patched AITER and
vLLM wheels:

```bash
export ROCM_HOME=/path/to/rocm
make run
```

The Makefile defaults to RockBuilder's `.venv/bin/python`. Override it when
necessary:

```bash
make run PYTHON=/path/to/python
```

To select shapes or change timing iterations:

```bash
make check
../../../../.venv/bin/python int8_gate_compare.py \
  --shape 32x8192x1024 \
  --warmup 10 \
  --iterations 200
```

Expose only one GPU while benchmarking. For example:

```bash
ROCR_VISIBLE_DEVICES=0 make run
```

The application prints device and package information, shipped gate state,
current-route status, and a summary table containing time, speedup over Triton,
relative error, and correctness status. GPU timing uses HIP events through
PyTorch.
