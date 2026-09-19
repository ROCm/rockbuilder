# vLLM runtime comparisons

These examples exercise vLLM paths changed or evaluated by RockBuilder patches.
They use the installed vLLM and AITER packages from RockBuilder's virtual
environment and print correctness and HIP-event timing summaries.

Available comparisons:

- `testing/int8_gate`: wave32 INT8 gate state and actual vLLM
  Triton/default/gate-enabled route performance.
- `testing/fast_fp8_dequant`: shipped, stock, and forced fast FP8 block-GEMM
  decoder paths.

Each directory contains its own build-free Makefile and README. Run an example
from its directory with:

```bash
make run
```

Set `ROCM_HOME` when it is not already exported. Override `PYTHON` to use a
different environment.
