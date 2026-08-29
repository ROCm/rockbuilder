# Dropped development patches

- `0010-renumber-rocm-system-patches.patch`: Release-series transition that
  is unnecessary for a new development patch series.
- `0012-fix-amdsmi-lib64-linkging-errors.patch`: Obsolete placeholder used
  only to preserve release-series numbering.
- `0013-add-debug-to-find_library-cmake-call.patch`: Diagnostic logging that
  is not required for normal builds.
- `0017-rocprofiler-sdk-do-not-build-external-yaml-cpp.patch`: YAML-CPP
  handling is already present in the development source.
- `0018-rocprofiler-systems-use-therock-provided-elfutils.patch`: Superseded
  by the current `THEROCK_BUNDLED_ELFUTILS` dependency handling.
