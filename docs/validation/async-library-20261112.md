# Async library scheduling validation — 2026-11-12

Code: `6258ccca768cf423107a8560a05ada350314199d` on
`AgnoyZ/nullarc`, `downstream/780m-tahoe`.
Evidence class: **host-verified**, experimental; no target GPU execution.

## Completed checks

Focused Actions run **43142206872** succeeded: both `host-contracts` and
`native-components` passed. Duplicate full-stack run **43142206754** was
cancelled after the focused run succeeded; it is not a passing run. No
experimental binaries were uploaded.

- Windows clean LF staged-tree checkout identical to the code commit:
  **355 tests, 27 skipped, zero failures**.
- Ubuntu: **355 tests, 1 skipped, zero failures**, plus existing POSIX
  sanitizer/contract checks. No Foundation execution is claimed on Ubuntu.
- Intel macOS **15.7.9**, build **24G830**, Apple Clang **17.0.0**:
  actual extracted source/stitching completion-handler method bodies and the
  three existing compile-queue/width helper bodies executed with real Foundation
  and Metal descriptor classes under **ASan/UBSan** and separately **TSan**.
- Existing base-translation sharing and background-cache I/O tests passed with
  both sanitizers. The present-copy, lifecycle, capability and other existing
  focused checks passed as well.
- Actual **PhxBringup** and **PhxAccel** kexts compiled, linked, signed and
  passed strict verification. The actual Metal plugin compiled, linked, signed
  and passed verification. Existing build warnings remain.

## Scheduling behavior exercised

Each sanitizer runs the native fixture in fresh processes with compile-pool
widths **one and two**. Only synchronous compilation and logging are synthetic;
the production API bodies, width selection and NSOperationQueue are executed.

- A suspended queue lets both API calls return before their synthetic compiler
  starts. Subsequent mutation of the source string and replacement of options
  macros/descriptor graph arrays do not change the queued snapshots.
- Gated builds keep the existing pool occupied while all submitters return.
  Peak active operations equal the configured width and callbacks do not run
  until the synthetic compiler is released.
- Success/failure paths preserve result/error delivery. A successful source
  result retains its synthetic warning; successful stitching suppresses it,
  matching the previous wrappers. Nil inputs reach the synchronous path, and
  nil handlers still cause creation without a callback.
- Completion callbacks run outside the compile queue. A callback can submit
  another library and wait for it even at width one, without occupying its slot.
- A queued operation retains its device owner, and that temporary owner is
  released after completion rather than retained by a queue/block cycle.
- **1600 mixed requests from 16 submitters per width** verify output identity,
  exactly-once callback delivery and zero active builds at completion. That is
  3200 stress requests per sanitizer, 6400 across both; it is not a speed ratio.

The JSON companion records both native reports, input SHA-256 hashes checked
against the committed Git blobs and independently checked extracted-method and
queue-helper hashes. Raw CI logs and local binaries/checkouts stay uncommitted.

## Limits and target acceptance

The fixture requests no Metal device and invokes no Apple source/stitch compiler,
AIR translator or GPU work. Its synthetic compiler validates dispatch, snapshot,
lifetime and callback behavior; it does not establish real shader correctness,
launch-time savings, frame-time improvement or stable FPS.

The existing queue limit covers active asynchronous compile operations, not
pending snapshot bytes, direct synchronous calls, backend compiler threads or
process RSS. Native object-copy semantics are not a deep-copy guarantee for
arbitrary nested objects. Async function/mesh wrappers are outside this change.

The Hackintosh's actual OS build and deployed driver remain unverified. No Tahoe
migration, driver deployment, EFI or security change was performed. Real library
output and fixed-workload caller latency/memory/frame-time A/B remain required.
