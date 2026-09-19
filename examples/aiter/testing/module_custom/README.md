# Wave Split-K FP8 standalone comparison

This HIP C++ application compares:

1. The legacy production AITER `wvSplitKQ` kernel.
2. The N-specialized, two-stage AITER split-K kernel.
3. FP8 dequantization followed by rocBLAS FP16 GEMM.
4. A CPU FP32 matrix-multiplication accuracy reference.

The application asks independently whether to run each implementation. Its
summary reports execution time, selected split count, effective TFLOP/s,
speedup over legacy AITER, maximum absolute error, maximum relative error,
NRMSE, and tolerance status.

## Supported GPUs

The same source and test shapes run on:

- `gfx90a`
- `gfx942`
- `gfx1100`
- `gfx1200`
- `gfx1201`

The shape matrix contains `1x4x16`, `1x7x496`, `1x4096x32768`, `2x60x96`,
`3x17x6192`, `3x65x1024`, `4x320x16400`, and `4x2048x16384`. The `1x7x496`
and `3x65x1024` workloads also appear in AITER's Python validation. The two
large workloads provide longer-running measurements with one and four
activation rows and different output widths. Together, the cases cover both
Wave Split-K dispatch paths, one-to-four activation rows, output-column tails,
and small and large inner dimensions. Performance should only be compared
between implementations on the same GPU. Raw timings from different GPU
architectures are not directly comparable.

The application currently tests FP16 output. The AITER kernel also supports
BF16 output, which can be added as a separate comparison.

## Build

Run from this directory:

```bash
export ROCM_HOME=/path/to/rocm
make
```

The Makefile defaults to this RockBuilder AITER checkout:

```text
src_apps/aiter_0_1_21_post1
```

Override it when necessary:

```bash
export AITER_SOURCE_DIR=/path/to/patched/aiter
export GPU_ARCH=gfx1201
make
```

`GPU_ARCH` is detected with `rocm_agent_enumerator` when it is not set. On a
mixed-GPU host, set `GPU_ARCH` explicitly and expose a matching device with
`ROCR_VISIBLE_DEVICES`.

The build compiles `csrc/kernels/custom_kernels.cu` from the selected AITER
checkout. This ensures the test executes the production kernel instead of a
copied approximation.

## Run

```bash
make run
```

`make run` rebuilds the application before starting it. By default, the
application runs every implementation without prompting. Run
`./build/wvsplitkq_compare` directly to use an existing build, or `make clean`
to remove the build directory.

Pass `-q` to answer `y` or `n` for:

1. Legacy production AITER `wvSplitKQ`.
2. Optimized AITER split-K, except on `gfx942`.
3. HIP FP8 dequantization plus rocBLAS FP16 GEMM.
4. CPU FP32 reference.

```bash
./build/wvsplitkq_compare -q
```

Selecting the CPU reference provides the most useful accuracy summary. When it
is disabled, the rocBLAS path becomes the accuracy reference if selected.

To select one implementation without prompting, set
`AITER_WVSPLITKQ_COMPARE` to `all`, `legacy`, `splitk`, `rocblas`, or `cpu`:

```bash
AITER_WVSPLITKQ_COMPARE=all ./build/wvsplitkq_compare
```

Set `AITER_WVSPLITKQ_SPLIT_COUNT` to `1`, `2`, `4`, `8`, or `16` to
override the split-count heuristic during standalone tuning:

```bash
AITER_WVSPLITKQ_COMPARE=splitk \
AITER_WVSPLITKQ_SPLIT_COUNT=16 \
./build/wvsplitkq_compare
```

GPU timing uses five warm-up launches and twenty measured launches. The rocBLAS
time includes both FP8 dequantization kernels and GEMM because together they
form the fallback pipeline.
