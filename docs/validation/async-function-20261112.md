# Async function scheduling validation — 2026-11-12

Production change: `885c11737a7f82ced6aaee2598af714140f6f09d`.
Corrected fixture and validated source tree:
`99e647e01cbaa05a6f2efd3c0533d1378cca582e` on `AgnoyZ/nullarc`,
`downstream/780m-tahoe`.
Evidence class: **host-verified**, experimental; no target GPU execution.

## Completed checks

Focused Actions run **43144322860** succeeded: `host-contracts` and
`native-components` both passed. No experimental binaries were uploaded.

- Windows clean LF staged-tree checkout identical to the validated commit:
  **358 tests, 27 skipped, zero failures**.
- Ubuntu: **358 tests, 1 skipped, zero failures**, plus existing POSIX
  sanitizer/contract checks. No Foundation execution is claimed on Ubuntu.
- Intel macOS **15.7.9**, build **24G830**, Apple Clang **17.0.0**:
  actual extracted named-specialization/descriptor completion-handler method
  bodies and all three existing queue/width helpers executed under **ASan/UBSan**
  and separately **TSan**, using real Metal function descriptors and constants.
- Existing source/stitching async library, base-translation sharing and
  background-cache I/O checks passed with both sanitizers. Existing present-copy,
  lifecycle, capability and other focused checks passed as well.
- Actual **PhxBringup** and **PhxAccel** kexts compiled, linked, signed and
  passed strict verification. The actual Metal plugin compiled, linked, signed
  and passed verification. Existing build warnings remain.

Initial run **43143909880** passed Ubuntu checks but failed to compile the
fixture: the inherited descriptor factory declares a base-class return type,
which was assigned to a subclass pointer under `-Werror`. The fixture now uses
the native subclass's `new` constructor. Strict warnings and sanitizer checks
remain enabled. That failed run is not native execution evidence.
Superseded full-stack run **43143909698** and duplicate full-stack run
**43144322679** were cancelled; neither is counted as passing evidence.

## Scheduling behavior exercised

Each sanitizer executes fresh processes at compile-pool widths **one and two**.
Synchronous function creation and logging are synthetic. Production async
wrappers, the existing queue and native Metal snapshot objects execute directly.

- A suspended queue lets both APIs return without running synchronous work.
  Later name mutation, indexed/named constant replacement/reset and descriptor
  field replacement leave the queued results unchanged.
- Native `MTLFunctionDescriptor` options/specialized names and the
  `MTLIntersectionFunctionDescriptor` subclass survive copying.
- Gated builds occupy the shared pool while all submitters return. Peak active
  builds equal the configured width; no completion runs before the gate opens.
- Synthetic success, failure and success-with-warning values reach handlers
  unchanged. Nil/invalid inputs reach the synthetic synchronous implementation.
  Non-copyable invalid descriptors avoid a new unconditional copy exception.
- Nil handlers perform no copy, enqueue, compilation or callback, preserving
  these APIs' previous behavior.
- Callbacks execute outside compile operation slots; a handler submits and
  waits for a nested request even at width one.
- Both APIs retain a queued temporary library owner and release it after work
  completes. There is no persistent queue/block retention cycle in the fixture.
- **1600 mixed requests from 16 submitters per width** check request identity,
  exactly-once callback delivery and zero active builds at completion:
  3200 stress requests per sanitizer, 6400 across both. These are test counts,
  not a timing or speedup measurement.

The JSON companion records both native reports and source SHA-256 hashes,
checked against the validated Git blobs, together with independently checked
extracted method/helper hashes. Raw logs and local checkouts/binaries remain
ignored and uncommitted.

## Limits and target acceptance

No Metal device, real function specialization, AIR translator or GPU work is
executed by this fixture. Host scheduling tests establish dispatch, snapshot,
ownership and callback behavior; they do not establish real shader output,
lower launch latency, reduced memory use or stable frame rates.

The queue bounds active asynchronous operations, not pending count/bytes, direct
synchronous calls, backend compiler threads or process RSS. Native copying is
not a deep-copy promise for arbitrary nested objects or foreign descriptors;
mutation concurrent with copying remains unsupported. The synchronous methods,
translator and mesh-pipeline wrapper are unchanged.

The actual Hackintosh OS build, driver deployment and Tahoe migration remain
unverified. No EFI, NVRAM, BIOS, disk or security change was performed. Real
function/shader output and fixed-workload caller latency/memory/frame-time A/B
are still required for a target performance claim.
