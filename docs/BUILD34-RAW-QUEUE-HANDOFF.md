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

## Published PSP work without an acknowledgment

In the later native factory stage, `pspRunCmd` can return a timeout in its
output scalars after publishing a command. The raw callback lease then ends.
`pspRing` also used to discard software ring state after an unacknowledged
create or destroy. Neither callback return nor `clearRing()` cancels a
published firmware request. The predecessor's actual methods allow adoption
after all three failures in the CPU fixture.

`tools/build34_exact_psp_uncertainty.py` derives the factory stage. An
unacknowledged published create, destroy or command latches uncertainty and
permanently closes raw writer admission for that service instance. An adoption
that races the active raw callback still returns Busy without waiting under
the GPU lock. After CPU drain, it checks the latch before setting either queue
ready, advancing its generation or changing its fence bytes. Late readback
does not clear the latch. The first command timeout still reports the existing
sentinel in the scalar reply without reading unconfirmed PSP response fields;
failed ring-control calls keep the ring address/metadata already recorded.
An error status with a matching command fence remains distinct from a timeout.
Failure of the readiness precheck before a create is not publication by that
call and does not set the timeout latch.

The [sanitized result](validation/build34-r3-psp-uncertainty-offline-20261121.json)
records 10 predecessor checks, 61 checks each under ASan/UBSan and TSan,
two synchronized adoption races and five detected deliberately broken
variants. The entire old and new driver translation units compile to x86_64
MH_OBJECT with the same 376 imports resolved against the existing KDK
providers. All 172 production input files remain unchanged.

```sh
nice -n 15 taskpolicy -b python3 -B tools/test_build34_exact_psp_uncertainty.py \
  --out build/build34-r3-psp-uncertainty-new-private --sdk "$KERNEL_SDK" --kdk "$KDK"
```

This guard excludes one known uncertain path; a clear latch is not an
affirmative hardware drain proof. The tested PSP response and MMIO behavior
are CPU doubles. Actual response freshness/coherency, SMU and raw mailbox
writers, queue-engine work, service lifetime and the checked bootstrap's
launcher-to-claim status propagation still require review. The reader remains
unbound and no installed change was made. Roll back by ceasing to derive this
isolated stage; do not clear the latch or retry the unknown firmware work.

## SMU and direct mailbox access

The follow-on `tools/build34_exact_smu_uncertainty.py` shares the PSP latch
with the actual `smuMessage` method. A response timeout after publication closes
raw writer admission before returning, preserves the timeout result and does
not read a firmware output argument without an observed reply. A nonzero
response is still returned to the caller to classify; it is not necessarily
success. The pre-poll Busy path publishes nothing and is unchanged.

The raw `writeReg` method now refuses the five PSP ring-control, pointer and
setup registers used by the driver, plus the three SMU mailbox registers.
Dedicated PSP and SMU paths retain access through their internal writer.
The checked-in `bringup5.sh`, `full.sh` and `mesboot.c` paths do not require any
of the eight via raw `writeReg`. This is a reservation of known direct writes,
not a complete MMIO allowlist or a bound on what other engines may still write.

The [sanitized result](validation/build34-r3-smu-uncertainty-offline-20261121.json)
records the predecessor counterexamples, 51 SMU/mailbox and 61 PSP checks
under each sanitizer configuration, three detected broken variants, and both
complete x86_64 object compiles with the same 376 KDK-resolved imports.
The race fixture pauses a published SMU call before returning a response or
timing out. Adoption first returns Busy; after CPU drain, only the modeled
response path permits adoption. No driver, ABI, runtime or boot script was
changed. Omit this isolated transform for source rollback.

```sh
nice -n 15 taskpolicy -b python3 -B tools/test_build34_exact_smu_uncertainty.py \
  --out build/build34-r3-smu-uncertainty-new-private --sdk "$KERNEL_SDK" --kdk "$KDK"
```

Actual firmware response freshness remains unproved. Remaining writer paths
include GPU work published through raw doorbells or queue-control registers.
The staged bootstrap's result must also survive the launcher-to-claim path;
the kernel guard and shell status are separate prerequisites.

## Propagating bootstrap and accelerator claim failures

The installed mapping observer's startup controller runs a sealed copy of the
same two launcher commands as `tools/phxctl/phxboot.sh`, without the resident
watcher. The outer controller checks the shell's exit status. However, the
shell ignores `full.sh` failure after filtering its output and then ignores
the status from `mesboot claim`. In the staged bootstrap, second-adoption
failure can leave one queue configured. That suffices for the existing
native `gpuReady()` claim condition. The existing build34 scalar wrapper
already returns process status 74 for a failed claim selector.

`tools/build34_exact_bootstrap_launcher.py` derives the source-only companion
to the checked bootstrap. It preserves `full.sh`'s status independently of
whether `grep` finds a diagnostic line and does not call `mesboot claim` on
initializer failure. A failed claim returns its status before any subsequent
desktop configuration. The derived script leaves the recovery marker and
controller policy intact and introduces no power action. Neither installed
launchers nor production source under `src/` or `tools/phxctl/` are edited.

Six CPU tests reproduce the old fall-through and exercise the actual replaced
fragment with process stubs for initializer and claim. Cases include status
74/75/127, absent or nonmatching diagnostic output, claim refusal and valid
success. Both the complete shell and its watcher-free form pass Bash syntax
checks. These tests join `make test`; omit the transform to roll it back.
Direct/manual claim bypasses the launcher and needs the separate guard
below. A successful shell exit does not prove hardware drain or coherent
fence visibility.

## Native admission for direct accelerator claim

The follow-on `tools/build34_exact_claim.py` changes only the staged
`PhxBringup::claimAccel()` body. Its predecessor uses the monotonic configured
mask, so one successfully adopted queue is enough to publish the matching
property even after the second adoption fails. The predecessor also returns
success and requests matching when `setProperty` refuses the write.

The new claim holds a service callback lease and snapshots both queues under
`gpuLock`: both must be ready and live, with no observed closure, stop, sleep,
or VM fault. The monotonic discovery flag remains unchanged for fallback
decisions elsewhere. Claim retains the selected PCI device, unlocks, and
checks for observed closure again before property publication. It requests
matching without holding `gpuLock` and only when `setProperty` succeeds.
All paths release the temporary reference and lease. The selector and its
existing privilege and argument checks are unchanged.

The [sanitized result](validation/build34-r3-claim-offline-20261121.json)
records the predecessor counterexamples, 103 claim checks, two synchronized
closure cases, and 51 SMU plus 61 PSP checks under each of ASan/UBSan and TSan.
Three deliberately broken variants fail the checks. The runner confirms that
only `claimAccel()` differs from the preceding full source, compiles both
complete translation units as nonloadable objects, and checks their identical
376 native imports. The PCI matching and reference behavior in the fixture
are CPU models. No production file or installed image changes.

```sh
nice -n 15 taskpolicy -b python3 -B tools/test_build34_exact_claim.py \
  --out build/build34-r3-claim-new-private --sdk "$KERNEL_SDK" --kdk "$KDK"
```

The final closure check is not atomic with registry publication or matching.
A stop, sleep, watchdog invalidation, or external property change after
the readiness snapshot still needs a native publication/lifetime protocol.
The snapshot is software readiness, not an old-writer drain or a device
fence visibility proof. Roll back by omitting this isolated transform.

## Rechecking claim across registry publication

The prior stage can still return success and request matching if closure
occurs while its registry write is in flight. The follow-on
`tools/build34_exact_claim_lifecycle.py` changes only the staged claim method
and adds an exclusive publisher lease and a request flag. Concurrent or
reentrant claims return Busy. Claim compares the captured PCI identity and
invalidation epoch with the two live queues before setting the property,
after setting it, and after requesting matching. All registry operations stay
outside `gpuLock`. A preexisting marker is refused; a successful request is
idempotent while the marker and queue state remain current.

If invalidation is observed after writing the marker, claim refuses success
and removes the observed true marker from the initially empty slot. It leaves
an observed different value in place. This retraction assumes this staged
producer is the only writer of the slot during removal: IOKit property
lookup and removal are separate, and the shared boolean cannot identify a
writer. It also cannot undo an already queued asynchronous match. The
current PhxAccel personality and `start()` consult only that boolean. Closing
the remaining gap requires paired consumer-side admission against the same
provider/lifecycle; an existing successful marker is not proactively revoked
by this stage on later stop or fault. No cleanup of an attached accelerator,
GPU drain, or fence visibility is established.

The [sanitized result](validation/build34-r3-claim-lifecycle-offline-20261121.json)
records the old in-flight failure and 126 checks in each sanitizer, including
six synchronized interleavings, actual staged sleep/wake invalidation,
prior claim and firmware regressions, and three rejected broken variants.
Both complete driver sources compile as nonloadable x86_64 objects with the
same 376 KDK-resolved imports. All 172 production inputs and the installed
stack remain unchanged. Omit this transform to roll it back.

```sh
nice -n 15 taskpolicy -b python3 -B tools/test_build34_exact_claim_lifecycle.py \
  --out build/build34-r3-claim-lifecycle-new-private --sdk "$KERNEL_SDK" --kdk "$KDK"
```

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
