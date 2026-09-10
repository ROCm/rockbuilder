# TopK plain standalone comparison

This HIP C++ application compares:

1. The production AITER `topk_plain` implementation.
2. AITER's stable one-block `top_k_per_row_prefill` implementation.
3. A test-local hipCUB block radix-sort fallback.
4. A CPU `std::partial_sort` accuracy reference.

The second AITER path is a useful independent comparison for these workloads.
Their dimensions keep `topk_plain` on its adaptive BlockTopk kernels, while the
per-row call explicitly uses the stable radix one-block kernel. Both AITER
implementations come from the selected AITER checkout.

The HIP fallback uses one `hipCUB::BlockRadixSort` block per row and sorts up
to 4096 FP32 values before emitting the selected `k` values. It provides a
parallel, implementation-independent GPU baseline. It still does more work
than a specialized TopK kernel because it sorts the complete row.

## Coverage

The FP32 workloads include the wave32 regression dimensions and larger batches:

- `8x32 k=1 max`
- `8x64 k=16 max`
- `8x128 k=16 min`
- `8x4096 k=16 max`
- `8x4096 k=64 max`
- `8x4096 k=128 max`
- `256x4096 k=128 max`
- `1024x4096 k=128 max`

The AITER per-row kernel supports largest-value selection, so the minimum TopK
case compares `topk_plain`, the HIP fallback, and the CPU reference.

The summary reports execution time, effective TB/s from semantic input and
output bytes, speedup over the HIP fallback, mismatched and invalid indices,
maximum selected value error, and pass/fail status.

## Build

Run from this directory:

```bash
export ROCM_HOME=/path/to/rocm
export GPU_ARCH=gfx1100
make
```

The Makefile defaults to this RockBuilder AITER checkout:

```text
src_apps/aiter_0_1_21_post1
```

`topk_plain_kernels.cu` uses CK Tile types, so the build also includes the
Composable Kernel checkout bundled below the AITER source directory.

Override it when necessary:

```bash
export AITER_SOURCE_DIR=/path/to/patched/aiter
make
```

Builds are stored in `build_<GPU_ARCH>`, allowing binaries for multiple GPU
architectures to coexist.

## Run

By default, every implementation runs without prompting:

```bash
./build_gfx1100/topk_plain_compare
```

Pass `-q` to select implementations interactively:

```bash
./build_gfx1100/topk_plain_compare -q
```

To select one implementation without prompting, set
`AITER_TOPK_PLAIN_COMPARE` to `all`, `plain`, `per-row`, `hip`, or `cpu`:

```bash
AITER_TOPK_PLAIN_COMPARE=plain ./build_gfx1100/topk_plain_compare
```

GPU timing uses five warm-up launches and twenty measured launches.
