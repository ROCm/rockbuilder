# Fused QK RMSNorm group-quant optimization plan

## Scope

Optimize the production AITER `fused_qk_rmsnorm_group_quant` FP16-to-FP8
group-quantization path for `gfx90a`, `gfx1100`, and `gfx1201`. Correct output
on every target is a prerequisite for performance comparisons.

The standalone comparison compiles the production kernel source whose SHA-256
was:

```text
b8da7587f9049e3e51e4366114b1a76b89d079253f0314e93d9ced99e2958350
```

The initial tests used ROCm SDK `/opt/rcb/rocm_10_0_0`, FP16 input, FP8 E4M3
output, group size 128, Q width 1536, K width 512, and token counts 32, 256,
8192, and 16384. Each token count was tested with and without Q residual.

## Initial baseline

The exact build form was:

```bash
make -B \
  ROCM_HOME=/opt/rcb/rocm_10_0_0 \
  AITER_SOURCE_DIR=/home/butler/rockbuilder_ai_workspace/rockbuilder/src_apps/aiter_0_1_21_post1 \
  GPU_ARCH=<gfx90a|gfx1100|gfx1201> \
  build
```

The exact run form was:

```bash
ROCR_VISIBLE_DEVICES=<device> \
AITER_FUSED_QK_COMPARE=all \
./build/fused_qk_rmsnorm_group_quant_compare
```

Observed results:

- `gfx1201`: every fused and fallback case passed with zero invalid values.
  Fused latency ranged from 4.416 microseconds at 32 tokens with residual to
  354.579 microseconds at 16384 tokens with residual. The fused path was 2.71
  to 8.15 times faster than the separate HIP fallback.
- `gfx90a`: K and residual outputs passed, but every fused FP8 Q case failed.
  The fused Q NRMSE was about 0.5, while the fallback passed with Q NRMSE near
  0.004. Fused latency ranged from 9.104 to 284.289 microseconds. The two large
  non-residual cases also produced 9 and 18 invalid values.
- `gfx1100`: every fused case failed. Sentinel counts show that Q FP8, K, and
  residual stores remain unwritten while scale stores execute. The fallback
  passed every case with zero invalid values. The reported fused timing must
  not be treated as a performance baseline because the kernel did not complete
  the required work.

## Phase 1: correctness prerequisites

### gfx90a FP8 format

`opus::finfo<fp8_t>` selects FNUZ limits only for `gfx942`. On `gfx90a`, it
therefore computes scales with the OCP maximum of 448 even though the packed
conversion instruction produces the FNUZ format whose maximum is 240.

1. Extend the Opus FP8 format selection to identify every FNUZ architecture,
   including `gfx90a`.
2. Keep the existing packed hardware conversion.
3. Re-run raw scale, raw FP8 byte, dequantized Q, K, and residual comparisons.
4. Verify both group-size 128 and per-token paths before performance tuning.

### gfx1100 FP8 conversion and missing outputs

Opus explicitly compiles `fp32_to_fp8`, packed x2, and packed x4 conversion as
zero-producing stubs on `gfx1100`. The fused kernel reaches those functions,
so successful compilation is not functional support.

1. Replace the conversion stubs used by this kernel with OCP E4M3 software
   conversion based on HIP FP8 types.
2. Implement and compare scalar, packed x2, and packed x4 conversion variants.
3. Use the standalone test's NaN sentinel counts to identify exactly which Q,
   K, scale, and residual regions are not written.
4. Test the four launch branches independently:
   - small token count with separate Q and K blocks;
   - small token count with residual;
   - large token count with K fused into the Q block; and
   - large token count with residual.
5. Inspect wave32 load/store lane mapping and the fused-K `row_offset` path.
   Fix those paths before using gfx1100 latency for tuning decisions.

## Phase 2: measurement controls

Add temporary tuning controls to the standalone application or production
dispatcher for:

- block size;
- thread data size;
- separate versus fused K launch;
- packed FP8 conversion width; and
- warm-up, measured iteration, and repetition counts.

Run at least five benchmark repetitions after correctness passes. Compare
medians on an otherwise idle GPU and retain a change only when it improves the
relevant shape range without regressing another requested architecture.

Add BF16 inputs, group sizes 32 and 64, per-token quantization, optional
unquantized Q output, transposed scales, and Gemma RMSNorm as correctness
coverage. Keep the initial FP16/group-128 matrix as the primary performance
baseline so results remain comparable.

## Phase 3: architecture-specific tuning

### gfx90a

1. Measure 128-, 256-, and 512-thread dispatches for Q width 1536 and K width
   512. Wave64 changes the number of active waves and reduction cost compared
   with RDNA.
2. Retain packed `v_pk_mul_f32` and packed FP8 conversion; inspect generated
   code to confirm vector values remain in VGPRs.
3. Compare the current DPP group-maximum reduction with a wave64-specialized
   reduction that avoids unnecessary cross-wave work for 128-element groups.
4. Sweep the token threshold that changes from separate Q/K blocks to the
   serial fused-K phase. The current threshold of 1024 is architecture-neutral
   and may not be optimal for MI210 occupancy.

### gfx1100

1. Start with packed x4 HIP OCP conversion. Four scalar conversions are the
   expected bottleneck when native packed FP8 instructions are unavailable.
2. Specialize group reduction and lane mapping for wave32 rather than relying
   on wave64-oriented DPP assumptions.
3. Compare 96- and 128-thread logical participation while keeping physical
   block sizes compatible with the reduction templates.
4. Benchmark separate Q/K blocks against fused-K processing across all token
   counts. Do not infer the threshold from gfx1201 because conversion cost and
   occupancy differ.

### gfx1201

1. Preserve native packed OCP FP8 conversion and verify that generated stores
   use the widest legal packed form.
2. Compare wave32-specialized maximum reduction against the current generic
   path for eight-thread groups.
3. Tune block size and the Q/K fusion threshold. The initial results show that
   residual traffic and large-token scaling deserve separate measurements.
4. Inspect whether Q residual output can share already loaded values without
   increasing VGPR pressure enough to reduce occupancy.

## Acceptance criteria

- Every requested architecture passes all standalone accuracy cases.
- No output remains equal to its sentinel value.
- The existing Python operation tests continue to pass.
- Performance is compared only after correctness and with identical semantic
  outputs.
- Retained changes improve median latency on their intended architecture and
  do not regress another requested architecture beyond normal run variance.
- A fresh RockBuilder checkout applies the resulting patch series and rebuilds
  the same test.

## Alternatives considered

- Use Triton as the standalone fallback: rejected for this C++ test because it
  requires Python and does not provide a directly callable C++ component.
- Use MIOpen, rocBLAS, or CK as a drop-in reference: rejected because none
  exposes the same fused RMSNorm, residual, K output, FP8 group scale, and
  quantized Q contract.
- Replace the production kernel with the portable fallback: rejected because
  the fallback is a correctness and timing baseline with extra intermediate
  memory traffic, not an optimized implementation.
- Apply one dispatch policy to all three GPUs: rejected because wave size, FP8
  format, conversion instructions, and occupancy differ materially.
