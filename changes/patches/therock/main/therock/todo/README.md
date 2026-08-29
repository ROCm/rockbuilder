# Deferred development patches

- `0001-asan-build-fixes.patch`: The superproject changes and the nested
  aqlprofile and roctracer patches apply. The nested MIOpen patch must be
  rebased onto the current `rocm-libraries` source.
- `0002-add-roctracer-as-a-dependency-to-rocprofiler-systems.patch`: The
  superproject change applies, but the current profiler dependency topology
  has changed. Validate that the explicit dependency is still required.
