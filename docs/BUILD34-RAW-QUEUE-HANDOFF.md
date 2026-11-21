# Build34 R3 raw-debug and queue ownership handoff

This source-only prerequisite derives the public-timer stage on default
`upstream34/vram-layout-fix`, PhxBringup build34. It addresses untracked raw
debug writers and adoption metadata that could invalidate an exact completion
observation. It does not admit a kernel candidate or complete R3. The device
reader and exact mode stay null/unbound, and service/GPU quarantine remains.
All 172 production inputs, earlier stages, ABI/dependencies, installed driver,
accepted R1b/R2a/plugin/startup/recovery, daily PR28 250 ms/WindowServer exclusion
and disabled resident monitoring remain unchanged. R4–R6 stay pending.

## Concrete source gaps

The preceding composed native source has leases on submit, VM/resource,
watchdog and selected callback paths. Its public raw register/VRAM/doorbell,
firmware, SMU/PSP and debug system-buffer entrypoints have none. A client gate
and per-client lock are not a service callback lease or a service-wide writer
exclusion. In particular, the previous raw VRAM write can write the value that
the checked fence decoder subsequently reports as completion; decoding cannot
distinguish a CPU spoof from a GPU write. Re-adoption also clears history and
seeds the fence without establishing old-writer drain. A second queue may
alias the first queue's fence and overwrite it with its CPU adoption seed.

The test reproduces those behaviors with the actual preceding method bodies
and CPU bytes. These are source/model counterexamples, not evidence that an
installed driver or physical GPU exhibited a false completion. The preceding
reader remains unbound in native source.

## Narrow staged change

`tools/build34_exact_raw_handoff.py` derives the frozen public-timer source.
It adds an embedded service-wide `CallbackGate<1>` for raw transactions and a
two-element, GPU-lock-protected, one-shot adoption latch. It changes only the
following method bodies; the runner proves every other method and field
byte-identical after removing these explicit additions.

| Methods | Admission and lifetime |
| --- | --- |
| `writeReg`, `vramWrite`, `doorbellWrite`, `sysMem`, `smuMessage`, `pspRing`, `pspSubmit`, `fwStage`, `loadIpFw`, `pspCtl`, `pspRaw` | Hold a service callback lease plus the exclusive raw-transaction lease through every return, lock and sleep. A concurrent raw transaction returns Busy; a closed raw/service gate returns NotReady. Neither gate waits for an owner. |
| `readRegs`, `vramRead` | Hold a service callback lease through the entire mapping/read path. They remain diagnostic reads, not coherent snapshots or trusted native fence readers. |
| `adoptQueue` | Validate bounded, disjoint ranges, refuse an already-adopted queue, close raw admission permanently, and require the raw gate drained before changing generations, history or fence bytes. A busy writer causes immediate Busy after closing admission; a later adoption retry can proceed once that writer leaves. |

One raw transaction at a time also prevents two public raw mutators from
concurrently replacing/freeing the shared debug system buffer or racing PSP
metadata. It is not proof that a previously submitted GPU/firmware operation
has stopped using that buffer. Existing internal helper lock/lifetime contracts
remain; no extra GPU or timer lock is held across PSP/SMU sleeps.

Adoption checks use subtraction after validating offsets, preventing 64-bit
user scalar wrap. Ring, 32-byte writeback and eight-byte fence ranges must be
pairwise disjoint within the requested queue and from an adopted peer; their
aligned eight-byte doorbells must differ. Peer reservations and each queue's
one-shot latch survive `ready=false`, invalidation, sleep, fault and stop.
Neither a fresh generation nor an adoption seed is an old-work drain proof.

The one-way close occurs under the existing GPU lock but never waits there
for a raw writer. An admitted writer still owns its service lease when an
adoption returns Busy or stop closes public admission. It may finish against
the retained resources; CPU drain never authorizes freeing those mappings,
reclaiming GPU resources or consuming service quarantine.

## Paired bootstrap ordering

The real `mesboot.c` scheduler first sets up and adopts compute, then sets up
GFX with more raw writes. Closing raw admission at that first adoption would
break the second setup. The same transform therefore stages a paired bootstrap
change, without changing any production file or adding an ABI selector.

Both existing adoption blocks copy their six scalars into two bounded local
records. The actual `main` calls the commit helper only at its final return,
after the selected raw setup operations finish. The helper invokes the existing
adoption selector for pending compute then GFX and prints their actual returns.
It rejects duplicate staging, copies inputs before later caller mutation and
returns 74 on an adoption error. It never retries, reopens raw admission or
undoes a successful first handoff when the second fails. No deferred request
means no adoption call. This ordering is necessary for this staged kernel;
the unchanged production bootstrap must not be paired with it.

The trace fixture uses the actual original/proposed `main`, scheduler tail,
adoption blocks and new helper, with explicitly stubbed raw initialization and
IOKit calls. It reproduces the previous raw-GFX-after-compute-adoption ordering
and checks the proposed two-queue, compute-only, GFX-only, no-adoption, duplicate,
copy, first/second-failure and repeated-finalization cases. Its raw trace is not
actual MES setup, GPU progress, bootstrap error propagation for all older void
helpers or native admission. Both complete original/proposed bootstrap sources
are separately compiled to host-SDK x86_64 objects without linking or executing
either tool. Initial external queue/hardware ownership remains unproved.

## Checked paired bootstrap

Deferral alone did not verify setup: `sched_test` ignored completion failures
for `SET_HW_RESOURCES` and `QUERY_SCHED_STATUS`, and the queue routines could
defer adoption after their compute or GFX sentinel polls expired. A failed
`ADD_QUEUE` could leave zero or one pending adoption while `main` returned zero.
The existing build34 layout wrappers already exit on IOKit errors or wrong
reply sizes; the missing checks concern device results after successful transport.

`tools/build34_exact_bootstrap_progress.py` derives the pinned deferred
bootstrap. In this stage, an adoption request must select `kiqsched` with
compute and GFX enabled, MC addressing, and normal clear state. It checks the
previous MES marker and cleared per-command writeback, or initial scratch and
test-buffer values for each queue, before publishing a write pointer that the
device can poll independently of the doorbell. Each MES command must produce
its query marker within the existing poll attempts and a nonzero command
completion writeback, retaining the v11 bootstrap's interpretation of that
writeback. Each queue must show both its scratch and distinct memory sentinel
within its poll attempts. Both six-scalar records must be present before the
first adoption. This does not make the two existing selector calls atomic:
if the second fails, the wrapper exits and the first remains adopted.

The transform also writes the MES completion payload by byte copy. The pinned
predecessor casts a field in a four-byte-aligned packet to `uint64_t *`; UBSan
reproduces its misaligned store. The old-flow CPU control disables alignment
instrumentation only in that predecessor function to expose the separate
control-flow failures. The checked form retains full ASan/UBSan coverage.
Ten predecessor checks, 14 checked cases and three existing wrapper exits per
form passed. The two complete bootstraps compiled to x86_64 MH_OBJECT, each
with the same existing warning. The first run stopped at the synthetic geometry
setup; the next reproduced the prior alignment failure. Neither used a GPU.

The [sanitized result](validation/build34-r3-bootstrap-progress-offline-20261121.json)
records the source pins and checks. Run the isolated check on x86_64 macOS:

```sh
nice -n 15 taskpolicy -b python3 -B tools/test_build34_exact_bootstrap_progress.py \
  --out build/build34-r3-bootstrap-progress-new-private
```

The fixture supplies synthetic geometry and replaces IOKit transport below the
real build34 wrappers. Poll counts are modeled, with no elapsed-time guarantee.
Marker readback is a bootstrap prerequisite, not proof of coherent retirement
or drain of prior external GPU/firmware writers. The production bootstrap,
driver and installed mapping observer are unaffected. Roll back the source-only
stage by ceasing to derive it; no runtime rollback is needed.

## Validation and remaining audit

The [sanitized result](validation/build34-r3-raw-handoff-offline-20261121.json)
records actual-method ASan/UBSan and TSan results, deliberate broken variants,
full native translation-unit compilation and existing-provider symbol checks.
Both sanitizers pass 1,063 driver checks in 75 groups/27 threaded scenarios.
The paired bootstrap passes 28 checks; all 35 broken driver variants and five
broken bootstrap variants are detected at runtime. The expanded succeeding
run freezes 93 inputs. Default `make test` passes, with its existing optional
missing-firmware-fixture skip. All 172 production files remain unchanged.
CPU mappings, locks, references, firmware transport helpers and raw setup are
test doubles; no IOKit, MMIO, kernel callback or GPU execution occurs. Threaded
cases use condition-variable handshakes rather than timing-based sleeps.

The full native class and access labels are compiled against the independent
pinned MacKernelSDK. Original/proposed PhxBringup and paired bootstrap outputs
must all be nonloadable x86_64 MH_OBJECT. The unchanged declared six KDK
providers are checked against the matching current-OS kernel; ordinary
implementations offer only defined externals, and symbol-only KPI interfaces
are structurally validated with kernel-defined reference/alias targets. No
private provider, dependency or unavailable symbol is admitted. Objects, SDK,
KDK material and raw output remain ignored/private; no bundle is created.
Both driver objects still have the identical 376-import set. The four prior
driver compiler warnings and one prior bootstrap unused-variable warning are
unchanged; no warning suppression is added to either native compilation.

The first private run passed its normal CPU sanitizer executions, then stopped
on a result-parser indexing error. The corrected second run passed the initial
driver-only scope; later alias and actual bootstrap review expanded that scope.
Those attempts are preserved and are not GPU failures or final evidence for
the expanded change.

This is a bounded raw-entrypoint audit, not a complete public/native lifecycle
audit. Platform `start`/unwind versus stop/publication, client factory and PCI
claim callbacks, inline readiness reads, native object/module lifetime and
healthy service teardown still require integration. Private low-level helpers
are not independently made safe when called outside their audited callers.
Initial MES/queue/firmware external writers, device mapping/cache coherency,
global-prefix/CPU visibility, native session/capability/Mesa binding and AMD
completion notification remain distinct requirements. Do not infer GPU drain
from the raw gate, a timer drain, a reserved layout or one-shot adoption.

Run only the source/CPU/object check:

```sh
nice -n 15 taskpolicy -b make -j1 test-build34-exact-raw-handoff \
  KERNEL_SDK="$KERNEL_SDK" KDK="$KDK" \
  EXACT_RAW_HANDOFF_OUT=build/build34-r3-raw-handoff-new-private
```

Rollback is to stop deriving this isolated transform and its paired bootstrap.
No installation, load, GPU probe, desktop takeover, recovery replay or power
action is part of this check. Continue the [R3 ledger](BUILD34-R3-PLAN.md);
actual correctness, FPS/CPU/latency and stated-duration stability acceptance
remain required before R3 completion.
