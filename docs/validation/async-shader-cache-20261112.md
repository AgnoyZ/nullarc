# Background base-shader cache validation — 2026-11-12

Code: `59e4e568253f2dad99bffa515623c6607fbdb26d` on
`AgnoyZ/nullarc`, `downstream/780m-tahoe`.
Evidence class: **host-verified**, experimental; no target GPU execution.

## Completed checks

Focused GitHub Actions run **43139325816** completed successfully:
`host-contracts` and `native-components` both passed. The duplicate full-stack
run **43139325721** was cancelled after the focused checks succeeded; it is not
reported as a passing run. No experimental binaries were uploaded.

- Windows, clean LF staged-tree checkout identical to the code commit:
  **352 tests, 27 skipped, zero failures**.
- Ubuntu: **352 tests, 1 skipped, zero failures**, plus the existing POSIX
  sanitizer/contract checks. Foundation execution is not claimed on Ubuntu.
- Intel macOS **15.7.9**, build **24G830**, Apple Clang **17.0.0**:
  actual extracted `nvmtl_compile_library_entry()` and save wrapper, actual
  pending-queue helper, and actual checked atomic filesystem helper executed
  under **ASan/UBSan** and separately **ThreadSanitizer**.
- Existing translation-sharing actual-entry tests also passed with both
  sanitizers while explicitly using the synchronous rollback path.
- Actual **PhxBringup** and **PhxAccel** kexts compiled, linked, signed and
  passed strict signature verification. The actual Metal plugin compiled,
  linked, signed and passed verification. Existing warnings remain.

## Behavior exercised

The new fixture produces synthetic 20-byte translator output, while using real
temporary host files and the production atomic-write helper. It verifies:

- the compile caller returns while the writer's `fsync` is held;
- 100 subsequent same-input misses reuse pending output without translating
  again; a forced stale initial miss is recovered by the secondary disk lookup
  after writer retirement;
- 32 queued-plus-active entries fill the count bound; a duplicate does not
  enqueue another write, and overflow skips persistence but returns the shader;
- a 32 MiB active payload fills the byte bound; an extra payload, an oversize
  payload and an unavailable identity are refused without blocking disk I/O;
- accepted mutable key/data/path snapshots remain unchanged by later mutation;
- injected `fsync` failure preserves an older valid file; failure and an
  injected Objective-C store exception retire pending state and allow retry;
  completed failure paths leave no unique temporary files;
- `NVMTL_SPVCACHE_ASYNC_OFF` restores synchronous persistence; existing
  `NVMTL_SPVCACHE_OFF` bypasses disk/pending reads while retaining writes;
- **1600 actual-entry requests on 16 workers** preserve synthetic output,
  free translator allocations, stay within queue accounting bounds and finish
  with zero pending entries/bytes.

The JSON companion contains both fixture reports, input SHA-256 hashes checked
against the committed Git blobs, the extracted-body hash and the evidence
limits. Raw CI logs, binaries, temporary files and local validation checkouts
remain outside committed evidence.

## What this does not establish

Returning while a deliberately gated `fsync` is pending proves control flow,
not a measured launch-time or frame-time improvement. The fake translator does
not validate real AIR/SPIR-V, Metal shader output or GPU execution. The queue's
32 MiB payload accounting is not a process RSS bound, and process exit does not
drain queued writes or guarantee persistence.

The actual Hackintosh OS build, active driver revision, real shader correctness,
cold/warm latency, memory pressure, target frame-time distribution and stable
FPS remain unverified. No Tahoe migration or driver/EFI deployment was performed.
For an isolated target A/B, restart the application with only the async-off
switch changed; keep sharing, workload and physical raster fixed.
