# Base-shader translation sharing: host evidence

Source commit `c640196ec14cd23f274d900b707a45c8fe861f8d`, focused GitHub
Actions run `43130840259`: **completed/success**, both `host-contracts` and
`native-components`. Machine-readable reports and source hashes are in
`translation-sharing-20261112.json`.

- Windows clean LF checkout of that exact commit: **349 tests**, 27 platform
  skips, zero failures. Extraction and wrong-host refusal run on Windows;
  Foundation concurrency execution is not a Windows pass.
- Ubuntu: **349 tests**, one existing platform skip, zero failures. Existing
  allocation/lifetime/cache-I/O/capability/submission/display-copy/timing/
  descriptor regression checks passed. The Foundation sharing fixture is
  explicitly macOS-only, not a Linux-native concurrency test.
- Intel macOS **15.7.9 / 24G830**, Apple Clang **17.0.0**: the extracted actual
  base-translation entry and real sharing header passed **ASan/UBSan** and a
  separate **ThreadSanitizer** execution. Each run held an owner until 31
  callers attached: **32 requests caused one fake-translator invocation**.
  Success, failure, exception and disk-cache-disabled batches all passed,
  with buffer cleanup and later retry. Each run also passed **1600 actual-entry
  requests across 16 workers**, full input identity/framing, independent-key
  parallelism, copied mutable key, recursive bypass, simulated saturation,
  timeout without stealing the owner's entry, and cache/direct-SPIR-V/backend
  refusal paths. No sanitizer failure was reported in these fixtures.
- Actual PhxBringup/PhxAccel kexts and the actual Metal plugin compiled, linked,
  signed and passed strict verification. Existing compiler/SDK/Metal warnings
  remain; the build is not warning-free. Source integrity was checked after
  native compilation. No driver was installed and no binaries were uploaded.

The fixture uses a fake translator, cache access and logging. It does not
validate real AIR/SPIR-V output, translator-library internals, target GPU
execution, installed target OS/build or active driver revision. The 32-to-one
count is neither a measured cold-start speedup nor an FPS multiplier. Timeout
tests override the wait to 50 ms; production uses 30 seconds, with no change
to the translator's own lifetime. The 64-entry capacity fixture deliberately
simulates a full registry instead of creating 64 blocked OS threads.

The duplicate automatic full-stack run `43130840264` was cancelled after the
focused checks passed; it is **not** a full-stack success. Raw logs and the
record generator remain ignored under `build/`. See `../TRANSLATION-SHARING.md`
for the runtime switch, constraints, rollback and outstanding target A/B.
