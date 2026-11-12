# Display-copy optimization: host evidence

Code commit `37cbf4a46074ab138146831150841f7256862947`, focused GitHub Actions
run `43126365088`: **completed/success**, both `host-contracts` and
`native-components`. Machine-readable results and source hashes are in
`present-copy-20261112.json`; experiment, rollback and target A/B procedure
are in `../PRESENT-PERFORMANCE.md`.

- Windows clean disposable LF snapshot: **347 tests**, 27 platform skips,
  zero failures. The actual native-copy test is among the skips.
- Ubuntu: **347 tests**, one existing platform skip, zero failures. The actual
  current full/damage copy and streaming assembly executed on host RAM under
  ASan/UBSan: **24194 full-copy cases and 896 damage-copy steps**. Independent
  copy-policy tests, including visible-width/pitch and packed-size overflow
  boundaries, also passed with sanitizers. Existing allocation, lifetime,
  capability, cache, submission, timing and descriptor checks passed.
- Intel macOS CI: **15.7.9 / 24G830**, Apple Clang **17.0.0**. The same actual
  copy harness passed under ASan/UBSan with the same case counts. In the
  tightly packed 2560×1600 test, the test-only wrapper counted **one** call to
  the unchanged streaming assembly. The previous row loop would call it
  1600 times; that comparison is source-derived, **not a timing benchmark or
  FPS ratio**. Both 8-bit and narrowed 10-bit pixels, all guard/padding words,
  unchanged sources and row/tail fallbacks matched the independent oracle.
- Actual `PhxBringup.kext`, `PhxAccel.kext` and Metal plugin compiled, linked,
  signed and passed strict signature verification. The native build still
  has existing compiler/SDK/Metal warnings; it is not warning-free. No driver
  was installed and no experimental binaries were uploaded.

MemorySanitizer was **not** run; the optional runner mode is not an MSan pass.
ASan/UBSan do not instrument inline assembly memory accesses, so the fixture
also checks destination guard/padding values and the source contents. The
fake allocation/atomic environment proves neither real concurrency nor kernel
FPU save/restore across preemption. Host RAM is not a write-combined surface or
scanout BAR. These results establish no improvement to target copy latency,
GPU execution, physical panel cadence or stable frame rate, and do not verify
the installed target OS/build or active driver revision.

The duplicate expensive automatic full-stack run `43126364974` was cancelled
after the focused source/native checks passed. It is **not** a full-stack
success. Raw CI/local logs remain ignored under `build/`.
