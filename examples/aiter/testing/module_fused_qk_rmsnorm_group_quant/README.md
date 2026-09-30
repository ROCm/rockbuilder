# Fused QK RMSNorm group-quant standalone comparison

This HIP C++ application compares:

1. The production AITER `fused_qk_rmsnorm_group_quant` kernel.
2. Separate test-local HIP RMSNorm and FP8 group-quantization kernels.
3. A scalar CPU FP32 accuracy reference.

The AITER source file is compiled directly into the application. The test
therefore measures the production kernel rather than a copied approximation.
The separate HIP path is a portable fallback baseline; it is not an AITER
runtime fallback.

## Coverage

The same FP16-input, FP8-output cases run on:

- `gfx90a`, using E4M3 FNUZ FP8
- `gfx1100`, using E4M3 OCP FP8
- `gfx1201`, using E4M3 OCP FP8

The DeepSeekV2 MLA-oriented cases use 1536 Q elements, 512 K elements, group
size 128, and 32, 256, 8192, and 16384 tokens. Every one of those token counts
runs with and without a Q residual.

Two additional workloads vary dimensions and boundaries:

- `17x128+128` uses one quantization group and a non-power-of-two token count.
- `513x4096+1024+res` crosses a 512-token boundary, widens Q and K, and uses a
  residual.
- `32768x1536+512` and `32768x1536+512+res` double the largest standard token
  count to provide longer-running measurements.

Accuracy is reported separately for:

- dequantized Q output;
- Q group scales;
- unquantized K output; and
- Q-plus-residual output, when enabled.

Before each GPU implementation runs, the test fills output buffers with FP8,
FP16, and FP32 NaN sentinels. The `Invalid` column reports values that remain
non-finite, making missing output writes visible independently of tolerance
checks.

Performance output includes HIP-event latency, effective semantic memory
bandwidth, and fused-kernel speedup over the separate HIP fallback.

## Build

Run from this directory:

```bash
export ROCM_HOME=/path/to/rocm
export GPU_ARCH=gfx1201
make
```

The Makefile defaults to this RockBuilder AITER checkout:

```text
src_apps/aiter_0_1_21_post1
```

Override it when necessary:

```bash
export AITER_SOURCE_DIR=/path/to/patched/aiter
make
```

`GPU_ARCH` is detected with `rocm_agent_enumerator` when it is not set. On a
mixed-GPU host, set `GPU_ARCH` explicitly and expose a matching device with
`ROCR_VISIBLE_DEVICES`.

## Run

```bash
make run
```

By default, the application runs the fused AITER kernel, the separate HIP
fallback, and the CPU reference without prompting. Pass `-q` to select them
interactively:

```bash
./build/fused_qk_rmsnorm_group_quant_compare -q
```

To select one implementation without prompting:

```bash
AITER_FUSED_QK_COMPARE=all \
./build/fused_qk_rmsnorm_group_quant_compare
```

Valid selections are `all`, `fused`, `fallback`, and `cpu`.

GPU timing uses five warm-up launches and twenty measured launches. Accuracy
requires the CPU reference; selecting only a GPU implementation reports timing
without pass/fail results.
