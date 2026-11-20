# Build34 R3 exact completion and safe retirement

Current November 21 checkpoint: R1a/R1b and R2a's bounded functional trial
have passed. R2a's installed combination remains active; no speedup is
established. R3 has tested **source-only Mesa bookkeeping, multi-target
wait/query and conservative CS dependency prerequisites**, not an installed
exact-wait implementation.
An additional allocation-free ownership/queue-generation **state prototype**
and staged submit/lifecycle, callback/client quarantine, target-observer
embedded client/provider identity-binding and owned-ticket wait fallback
experiments have CPU evidence but no production caller. A further actual-Mesa
transport experiment retains completion across ACK and serves late queries;
its adapter is installed only by CPU fixtures, with no native wire binding.
Staged native receipt wait/ACK now also validate complete tokens through a
strict structure dispatcher, still with no mode/capability admission or
paired runtime binding; see [the wire contract](BUILD34-RECEIPT-WIRE.md).
The subsequent [staged submit receipt extension](BUILD34-SUBMIT-RECEIPT.md)
returns complete identities from the actual submit path and tests their
wait/ACK round trip with CPU objects. It refuses mixed-engine batches and
CPU user fences, preserves actual queue fallback and leaves uncertain work
retained. It adds no native capability/session or Mesa wire admission.
The proposed observer
has no admitted hardware fence reader and refuses completion without one.
A subsequent [staged dword-window integration](BUILD34-WINDOW-CALLSITES.md)
connects the previously separate primitive to adoption, invalidation, shared
legacy/exact submission, ring-space pruning and exact observation. Its raw
reader stays null. CPU callsite checks do not establish mapping coherency,
old-writer drain or the unchanged global-retirement/VM consumers' safety.
R4–R6 have not started.

## Why a kernel-only change is unsafe

The production build34 `gpuRetired()` is a conservative contiguous watermark
across the compute and GFX queues. Its consumers include `vmBind`,
`vmidFree`, QueryInfo, native wait results and CPU fence publication. A later
completed GFX fence cannot safely advance that global watermark past an
unfinished earlier compute submission. Keep these reclamation semantics.

There is a second, user-space contract to preserve. The pinned MIT Mesa
`ac_darwin_sync.c` calls `note_retired(s, seq)` after any successful nonbusy
backend wait, in addition to consuming the returned watermark. `fold()` then
marks **every** attached sequence at or below that value complete. Merely
changing the kernel's busy result to exact-target completion would therefore
falsely signal an unrelated lower-sequence syncobj, even if the kernel still
returned a conservative watermark in output slot 1.

The new [actual-source CPU fixture](../tests/test_build34_exact_completion.c)
demonstrates this transition hazard on the unchanged pinned provider: the
fake backend reports global watermark 9, exact sequence 20 complete and
sequence 10 pending. Waiting for 20 makes the old provider falsely report
10 complete. **This models a proposed exact backend; it is not evidence
that the installed conservative backend returned such a response.**

## Isolated prerequisite

[Patch 0003](../mesa-patches-build34/0003-radv-exact-completion-bookkeeping.patch)
changes only `ac_darwin_sync.c`. It retains `note_retired(s, retired)` for
the backend's safe prefix, but replaces the second prefix promotion with
`note_completed(s, seq)`. Under the provider mutex this folds only current
binary/timeline references to that exact sequence. A signaled timeline point
still implies lower points on that same timeline, as before. Unrelated
objects are not signaled. Cloned providers continue to share the same state.

The callback runs without the mutex, so completion must look up current
payload references after reacquiring it. Reset/destroy/handle reuse during
the callback must not signal a replacement sequence. No permanent set of
completed sequence numbers, new allocator or extra resource lifetime is
introduced. Late references can ask the backend again. Backend errors and
the legacy conservative-prefix response keep their existing behavior.
The exact-reference scan runs only when the completed target is above the
returned safe prefix; legacy prefix-covered completions incur no new scan.

The [offline runner](../tools/test_build34_exact_completion.py) requires all
30 source/dependency hashes in the existing reviewed Mesa manifest. It
freezes separate baseline/candidate closures, initializes a private source
repository for unambiguous patch application, requires exactly one changed
file and preserves the original MIT notice. It verifies inputs and all
tracked driver/plugin/native-ABI/phxctl bytes again afterwards. The old
original34 artifact admission tools are untouched.

Run with an explicitly selected matching source and a fresh ignored output:

```sh
nice -n 15 make test-build34-exact-completion \
  MESA_SOURCE="$MESA_SOURCE" \
  EXACT_COMPLETION_OUT=build/build34-r3-exact-bookkeeping-new-private
```

On November 20 both actual-source executables compiled under ASan/UBSan.
The unchanged baseline reproduced the counterexample. The candidate passed
**4,741 checks**, including 128 distinct sequence gaps, late attachment,
binary reset/signal, independent timelines, shared clones, transfers, safe
global-prefix folding even on busy replies, device-loss/error propagation,
and deterministic reset/destroy/reuse races while the callback is blocked.
The default `make test` suite also passed.
Linkage checks exclude IOKit, Metal and Vulkan device runtimes. No GPU code
was submitted or simulated, and no installation, load, configuration, job,
EFI/cache/ACPI or power operation occurred. See
[sanitized evidence](validation/build34-r3-bookkeeping-offline-20261120.json).

## Remaining admission work

These patches are prerequisites, not the complete R3 optimization. Do not enable
an exact kernel/backend response yet. Before a paired native candidate:

1. Add a separately negotiated exact-target operation while keeping legacy
   waits and the safe output/global reclamation watermark compatible. Bind
   targets to actual submission ownership, queue selection/generation and
   teardown; never infer completion from a missing/reused history slot.
2. Carry the separately tested multi-target prerequisite below into the future
   paired candidate only after capability negotiation and dependency work.
   Neither the installed runtime nor the old runtime recipes apply it.
3. Carry the separately tested conservative CS dependency guard below into
   the future paired candidate. It waits for completion on the CPU and refuses
   unsupported legacy dependency chunks in exact mode; it does not encode
   native GPU queue dependencies or resolve kernel submission ownership.
4. Separately validate AMD completion-event/interrupt routing and lifetime,
   lost-wakeup rechecks, bounded fallback, cancellation and stop/sleep.
   Existing RELEASE_MEM packets still request no interrupt. Do not copy
   NVIDIA event selectors or set interrupt bits without a working route.
5. Require byte-exact CPU regressions, frozen native provenance, a fresh
   compatible recovery scope, exact loaded images and bounded dual-queue
   full-arena hardware evidence before R3 acceptance or advancing to R4.

Current rollback is simply to leave these source patches unapplied to the
installed runtime; there is no deployed R3 state to undo. The accepted R2a
installation, R1b kernel, optimized AML, accepted plugin, daily PR28 250 ms
with WindowServer excluded, disabled resident monitors and 45/150/300-second
startup bounds remain intact. Neither FPS nor long-term stability is claimed.

## Multi-target wait and query prerequisite

After 0003 alone, three independent global-prefix assumptions remain unsafe
for the **proposed** exact backend:

- A zero-timeout wait-any on pending sequence 10 and completed sequence 20
  polls only 10, returning ETIME although the second payload is ready.
- Query of a completed sequence-20 timeline and pending sequence-30 timeline
  refreshes only 30, missing the completed timeline point.
- Waiting for point 3 attached to pending sequence 10 misses completed point 8
  attached to sequence 20 on the same timeline. Point 8 can satisfy point 3.

The [new actual-source fixture](../tests/test_build34_exact_multitarget.c)
reproduces all three with 0003 applied. This is a contract transition test,
not a reproduction against the installed conservative native backend.

[Patch 0004](../mesa-patches-build34/0004-radv-exact-multitarget-wait-query.patch)
changes the sync provider and its internal userspace backend header. The new
`exact_completion` capability defaults to false in the unchanged production
initializer. It is neither a native ABI extension nor an environment switch;
no production backend enables it. Legacy wait retains its single minimum
poll and query its single newest poll, with the same call budgets.

When the CPU fixture explicitly enables this capability, waits collect a
finite snapshot of every candidate able to satisfy the requested payloads,
including higher points on the same timeline. They sort/deduplicate sequence
numbers and poll with zero budget, even for an expired/zero deadline. State
is checked after each callback so wait-any can return without polling an
unrelated failing target. Wait-all retains its all-payload requirement and
`first_signaled` follows the input handle indices. Before a blocking callback,
the real production code rechecks its monotonic deadline, caps the slice at
20 ms and rotates the target. This is not a hard scheduler/return-time bound.

Query snapshots all outstanding timeline candidates, not just the largest
sequence. Exact-mode backend errors propagate with the existing device-loss
mapping; legacy query retains its existing previous-state-on-error behavior.
The safe global prefix is still folded separately from exact completion.

Snapshots contain sequence values only. No object pointers survive unlocking
the mutex, and current references are checked after callbacks. Reset,
destroy/reuse, object-table growth and concurrent attachments cannot signal
replacement payloads or enlarge an in-progress snapshot without bound.
Attachments after the snapshot can be observed by a later sweep/call. Temporary
allocation failures return ENOMEM before any callback and preserve payloads;
there is no persistent completed-sequence set. CPU signal/attach condition
checks and sleeps share the mutex. If an attach arrives after the initial
empty snapshot unlock, a second lock-held snapshot prevents sleeping after
its notification has already passed.

Run the [separate offline runner](../tools/test_build34_exact_multitarget.py)
against the same 30-file reviewed dependency closure and a fresh output:

```sh
nice -n 15 taskpolicy -b make test-build34-exact-multitarget \
  MESA_SOURCE="$MESA_SOURCE" \
  EXACT_MULTITARGET_OUT=build/build34-r3-multitarget-new-private
```

On November 20 the candidate passed **3,768 ASan/UBSan checks**, including
128 sequence gaps/permutations (also near UINT64_MAX), wait-any/all, multi-query,
timeline implication, alias deduplication, shared clones, transfers, deadline
expiry/final polling, rotating blocking targets, CPU signal/attach, backend
errors, initial/growing allocation failure and bounded snapshot mutation.
Six actual-thread wait/query cases pause inside the backend while another
thread resets/destroys/reuses a handle or expands the object table. The
deadline fixture redirects only the provider's monotonic clock for
deterministic passage during a callback; it does not measure native wait time.
An additional deterministic unlock/attach interleaving reproduced an avoidable
condition-wait delay in the pre-final source; its failed CPU assertion is
preserved privately. The final lock-held recheck passes with one zero-budget
backend poll and zero condition sleeps in this case.
The prior **4,741-check** bookkeeping suite passes on the combined sources,
and default `make -j1 test` passes (optional firmware fixtures remain absent).

The runner verifies unchanged source inputs, MIT notices, dependency closure,
production backend initializer and all tracked driver/plugin/native-ABI/tool
bytes. Neither executable links IOKit, Metal or Vulkan device runtimes. The
recipe is deliberately separate from the existing runtime/tail patch series.
See [sanitized evidence](validation/build34-r3-multitarget-offline-20261120.json).

A separate read-only check during this work again passed the same accepted
R2a boot, exact loaded R1b/R2a/mapped plugin, 358 EFI files, complete cache/ACPI/job
checks, advancing desktop and four zero error counters. Preserve its first
reader's bytes-versus-string TypeError at accelerator comparison and the
corrected successful readback; the first reader failure is not a driver-load
failure. There was no recovery or power request. The accepted R2a installation
remains active. R3 is still uninstalled and has no GPU/FPS/long-term acceptance;
native ownership/generation, cross-queue dependencies and AMD events remain
the next admission work before R4.

## Conservative CS dependency prerequisite

The pinned `acd_sync_cs_wait_ready` treats any attached sequence on the same
connection as already ordered before the next submission. The build34 native
submitter can select compute or GFX, including a readiness-dependent fallback,
so connection identity alone is not proof of queue ordering. A proposed exact
backend must not let a consumer overtake unfinished work on another queue.
The pinned CS planner also ignores nonempty `DEPENDENCIES` and
`SCHEDULED_DEPENDENCIES` chunks under its historical one-ring assumption.

The [actual CS fixture](../tests/test_build34_exact_cs_dependencies.c) runs
the real `acd_ioctl` → CS planner → sync provider → kext marshaller against
CPU platform callbacks. With only 0003/0004 applied and the proposed exact
capability injected, it reproduces compute-to-GFX and GFX-to-compute consumers
submitting before their dependency completes, and both kinds of dependency
chunk being ignored. These are contract-transition counterexamples, not an
observed failure of the installed conservative native backend.

[Patch 0005](../mesa-patches-build34/0005-radv-exact-cs-dependency-guard.patch)
applies after 0003 and 0004 and changes only the provider, its internal header
and CS wrapper. In exact mode it conservatively waits for actual payload
completion before submitting the consumer. Higher completed points on the
same timeline may satisfy lower requested points, while an unrelated pending
sequence still holds back the safe global reclamation watermark. Backend
errors and expired waits refuse the CS before submitting or attaching its
outputs. Nonempty unsupported legacy dependency chunks return `EOPNOTSUPP`
before any backend wait, consumer submission or output publication; empty
chunks carry no dependency and remain accepted.

The existing 60-second **per-dependency** relative budget is converted to a
monotonic absolute deadline with saturation below the infinity sentinel. This
does not bound total CS latency across multiple dependencies or scheduler
delays. It is a conservative CPU fallback, not an asynchronous GPU dependency
implementation or an FPS optimization. Legacy mode retains its existing
wait-for-attachment behavior and chunk handling. The production capability
still defaults false; no initializer, native ABI, driver, plugin or existing
runtime/tail recipe enables or applies these prerequisites.

Run the [separate CPU runner](../tools/test_build34_exact_cs_dependencies.py)
against the same reviewed 30-file closure and a fresh ignored output:

```sh
nice -n 15 taskpolicy -b make test-build34-exact-cs-dependencies \
  MESA_SOURCE="$MESA_SOURCE" \
  EXACT_CS_OUT=build/build34-r3-cs-dependency-new-private
```

On November 20 the strengthened candidate passed **4,552 ASan/UBSan checks**:
64 ordering cases cover both queue directions, same-engine use, binary and
timeline payloads and shared provider clones. Six additional CS cases exercise
multiple mixed/duplicate dependencies, higher-timeline implication, a later
dependency's error, timeout and early unsupported-chunk refusal. Real provider
transfers distinguish an unattached refused output from an attached pending
output. Actual-thread cases cover CPU signal, producer attachment and
reset/destroy/handle reuse while the backend callback is blocked. Zero/large
relative budgets, device-loss/error mapping, submit failure and legacy call
behavior also pass. The provider's deterministic CPU clock is not a measurement
of native GPU wait time. The earlier 3,768-check multi-target and 4,741-check
bookkeeping regressions pass on the combined sources, as does default
`make -j1 test`; optional firmware fixtures remain absent.

The runner preserves original MIT notices, freezes the source and test inputs,
checks the compiler dependency closure and excludes device runtimes from the
test linkage. It verifies all tracked driver/plugin/native-ABI/phxctl bytes
remain unchanged. See
[sanitized evidence](validation/build34-r3-cs-dependencies-offline-20261120.json).

A new separate read-only check passed the currently accepted R1b/R2a/mapped
plugin combination, all 358 EFI files, full cache/ACPI/startup-job checks, the
same WindowServer, desktop progress and four zero error counters in both
samples. No recovery, GPU probe or power request occurred. This check does
not run the R3 code on hardware. Keep the accepted installation active;
native exact-target negotiation, ownership/generation/history reuse, teardown,
GPU queue dependency support and AMD completion events remain unresolved.
R3 has no native acceptance, and R4–R6 have not started.

## Ownership and generation state prototype

Two legacy contracts constrain the next native implementation. `doWaitSeq`
checks an upper bound against the client's newest global sequence, not a set
of that client's successful submissions. Different clients' sequences can
interleave below this bound. Separately, `adoptQueue` zeroes the selected
queue's history and seeds its new fence with `gSeq`. An exact-target operation
must distinguish the previous queue generation from that newly seeded value.

The [native contract fixture](../tests/test_build34_exact_native_contract.cpp)
extracts the **unchanged accepted** `queueFence`, `gpuRetired`, `adoptQueue`
and `doWaitSeq` methods into CPU aperture/lock doubles. A constructed client
with emitted sequence 20 accepts target 15, for which it has no submission
record. A separate constructed pending compute-10/completed-GFX-20 case starts
with safe prefix 9; applying the actual adoption method clears the old compute
history, seeds its fence to 20 and changes the reported prefix to 20. These
demonstrate legacy contract boundaries for a proposed exact operation. They
are **not** GPU executions, live queue-adoption tests or evidence that the
installed driver improperly readopted a busy queue.

The new [ownership state prototype](../tools/build34_exact_ownership.h) is
unreferenced by production code and does not modify a driver or ABI. Its
bounded, allocation-free registry holds at most 64 receipts, independently of
the native queue's 64 reusable history slots. Each receipt binds a sequence
to the **actual** selected queue and its nonzero generation. Tickets bind a
slot to an owner epoch and a monotonically increasing lease serial. Unknown,
forgotten, foreign-owner and reused tickets cannot identify replacement work.
Owner epochs and lease serials reserve zero and the LAST sentinel; the small
counter refuses exhaustion instead of wrapping.

Reservations must precede dispatch admission. Publication validates the
receipt before a future doorbell; invalid receipt fields leave the reservation
intact. Only an unpublished reservation can be cancelled. Pending or lost
receipts cannot be evicted, cancelled or forgotten; a full registry refuses
new admission. A valid exact completion permits explicit **metadata-only**
forgetting. This never frees a BO, VMID, page table or any other GPU resource,
and does not advance the global retirement watermark. Uncertain submissions
and lost generations still require a separately proved native drain/teardown.

Observations check ownership and lifecycle before interpreting the selected
queue's fence. A changed generation, fault, unready queue or stopped service
makes the receipt permanently lost. Closing the registry refuses all later
operations while retaining its records. A fence beyond the queue's submitted
sequence, a submission high-water mark below the receipt or a backward value
after a proved completion is an invalid observation, not a new completion.
Keeping the receipt separate from ring history allows a same-generation later
fence to prove completion after history-slot reuse. Missing history alone
never does so.

These are conditional state rules, not native authentication or concurrency
guarantees. A future caller must allocate unique owner epochs, mint receipts
only inside the validated kernel submit path, supply coherent authenticated
queue observations and serialize every registry operation. The prototype has
no internal locks, hardware fence reader, capability negotiation, native
selector, native ownership allocation, queue-generation lifecycle or resource
drain. Its structs must not be trusted as userspace-supplied submission proof.
The source intentionally remains outside production `src/` until those
integration contracts and their actual call sites are separately tested.

Run the [isolated CPU runner](../tools/test_build34_exact_ownership.py):

```sh
nice -n 15 taskpolicy -b make test-build34-exact-ownership \
  EXACT_OWNERSHIP_OUT=build/build34-r3-ownership-new-private
```

On November 20 the strengthened prototype passed **321,712 ASan/UBSan checks**.
Coverage includes 128 sequence-gap cases (also near UINT64_MAX), 128 fixed-seed
reference rounds using independent owner maps and queue-prefix membership,
full pending/lost registries, validation failures, cancellation, client/lease
aliasing, counter exhaustion, generation/fault/close refusal and stale fence
observations. Three actual-thread interleavings use an explicit caller mutex:
a callback resumes after completed-receipt reuse, registry close or generation
change, then revalidates its copied ticket. They do not test native locking or
claim that ASan/UBSan detects data races. A separate C++14/no-exceptions/no-RTTI
header compile passes; it is not a Kernel SDK build.

The runner freezes the accepted build34 source, ABI, topology, new prototype,
fixtures, runner and license inputs; checks the non-system compiler dependency
closure; excludes IOKit/Metal/Vulkan runtimes; and verifies 172 tracked
production files remain unchanged. Default `make -j1 test` also passes, with
optional firmware fixtures still absent. See
[sanitized evidence](validation/build34-r3-ownership-offline-20261120.json).
A fresh independent read-only check again passed exact loaded R1b/R2a/mapped
plugin, all 358 EFI files, full cache/ACPI/startup-job checks, the same
WindowServer, desktop progress and four zero errors in each sample. No recovery,
GPU probe, installation or power request occurred; keep this accepted
installation active.

Next native work must pair capability negotiation with actual receipt/owner
allocation, sequence-overflow refusal, actual-queue capture after R1b retry
selection, queue-generation changes and an authenticated coherent fence read.
Reserve only receipt metadata before admission; preserve R1b's unlocked queue
backpressure and never publish GPU work before fallible ownership checks.
Stop/sleep/client-close and uncertain dispatch must retain resources until a
real drain, with exact completion still separate from global reclamation.
These native integration/event/fallback and hardware acceptance requirements
remain unresolved; this prototype does not admit an R3 installation or R4–R6.

## Actual native-submit admission source experiment

The next isolated step connects the existing ownership registry to the actual
`doSubmit` → `gpuSubmit` path in an **offline staged copy** of the accepted R1b
build34 source. The [source transform](../tools/build34_exact_submit.py) has
unique, pinned-input anchors; it is used only by the
[separate CPU runner](../tools/test_build34_exact_submit.py). No production
source, ABI, runtime recipe, installed image or startup job changes. The staged
client pointer remains null with no allocator or capability; only the CPU
fixture supplies a registry. This is not an enableable R3 driver candidate.

The staged actual client reserves a receipt before entering `gpuSubmit` and
retains its existing client lock and BO ownership. R1b's queue-space retry
continues releasing `gpuLock`; it reserves neither ring space nor a submission
sequence during sleep. Once space is available, the lock-held code captures
the **actual** selected queue after retry/fallback, checks exact sequence
exhaustion and binds the VM. Receipt publication then precedes the first ring
packet, writeback pointer and doorbell. Publication failure leaves these
submission outputs untouched; `vmBind` may already have changed VM registers,
and earlier client cache maintenance/VMID allocation can also have occurred.
This is not side-effect-free admission.

The global `gSeq` update stays at its existing packet-emission site; it is not
moved ahead of IB emission. The legacy global retirement function, fence
reader and WAITSEQ implementation remain byte-identical. Exact completion
therefore does not replace the safe global resource-reclamation prefix. Only
an unpublished reservation can cancel on an ordinary pre-dispatch error; no
failure return is introduced after successful publication. A published receipt
remains retained even if the caller never consumes the successful response.
Transport uncertainty and resource teardown still require separate native
work and are not validated by this CPU fixture.

An adoption counter lives outside the resettable ring/history struct. The
actual staged `adoptQueue` increments it under `gpuLock` before resetting
history and refuses exhaustion before reset. This prevents a receipt for an
old adoption from inheriting the newly seeded fence in the CPU contract. It
does **not** cover service restart, sleep/wake, faults, watchdog wave kills,
stop or client close; no trusted owner allocator or coherent hardware reader
has been added. Those missing lifetime rules still prohibit enabling exact
completion. The 64-record table also remains deliberately finite: the 65th
submission refuses even if CPU-injected fences have advanced, until a caller
explicitly observes completion and forgets metadata. There is no production
acknowledgement/reclamation protocol, no automatic eviction and no Unknown-to-
legacy-prefix fallback. No BO, VMID or page table is reclaimed by the registry.

Run with a fresh ignored output:

```sh
nice -n 15 taskpolicy -b make test-build34-exact-submit \
  EXACT_SUBMIT_OUT=build/build34-r3-native-submit-new-private
```

On November 20 the final [actual-method fixture](../tests/test_build34_exact_submit.cpp)
passed **30,605 ASan/UBSan checks across 80 scenario groups**. Five methods are
extracted directly from the staged source: submit client, GPU submit, queue
adoption, fence read and global retirement. Coverage includes compute/GFX,
preferred/fallback queues, one/two/64 IBs, client fences, full/closed registries,
invalid leases and inputs, failed VM binding, sequence limits, queue-space
sleep/reselection, adoption geometry changes, context/queue loss and real
monotonic-budget control flow with an injected CPU clock. One deterministic
two-client interleaving runs both actual submit paths: GFX submits while the
other client is blocked for compute space, and each registry owns only its
own sequence. This is not actual-thread/TSan or GPU concurrency evidence.
Two 130-submit runs reuse native history slots while retaining an older exact
receipt. The cross-queue case proves exact GFX completion can coexist with
the unchanged lower global prefix, using CPU-injected queue values only.

Five separate deliberately faulty callsite variants must fail the same suite:
requested instead of actual queue, omitted receipt publication, omitted exact
sequence guard, omitted adoption epoch and premature global-sequence update.
Their expected failed assertions are retained privately. The first fixture
compile's signedness error is also preserved and corrected to match the
native `int kMaxMaps`. A preliminary passing source variant was revised during
review to preserve the original global-sequence update site; it was never a
kernel build or installed candidate. The strengthened final suite catches
that premature-update variant.

The earlier **321,712-check** ownership suite and default `make -j1 test` pass
again; optional firmware fixtures remain absent. Compilation dependencies
are frozen and checked; device runtimes are excluded. All **172 tracked
production inputs** remain unchanged. No Kernel SDK build, service open,
installation, GPU probe, reboot or public binary upload occurred. See
[sanitized evidence](validation/build34-r3-native-submit-offline-20261120.json).
A separate independent read-only check passed exact loaded R1b/R2a/mapped
plugin, full EFI/cache/ACPI/startup jobs, the same WindowServer and advancing
desktop, without recovery or power requests. Keep that accepted installation
active. Next resolve native lifecycle/owner allocation, bounded receipt
acknowledgement, capability negotiation, coherent fence observation and safe
teardown before a paired native backend or hardware trial. AMD completion
events/fallback, R3 hardware/FPS/long-term acceptance and R4–R6 remain pending.

## Native lifecycle invalidation source experiment

The [next isolated transform](../tools/build34_exact_lifecycle.py) extends the
prior staged submit source without changing that experiment or any production
input. It adds conservative metadata invalidation to the **actual** power,
wave-kill and service-stop methods. The proposed exact pointer still has no
production allocator, selector or negotiation; no runtime recipe applies this
transform. Nothing here admits an R3 kernel build, deployment or GPU trial.

Queue validity is distinct from legacy hardware `ready`. The first sleep edge,
each forced wave recovery and service stop invalidate both exact queues and
advance their generations under the existing GPU lock when allocated. The
wave-kill method holds that lock across invalidation and the existing register
sequence, so no new exact submission or adoption can pass between these two
operations. A single-VMID kill conservatively invalidates both queues because
there is no authenticated per-VMID recovery/outcome accounting yet. Killing
waves can let a fence advance; that value must not be interpreted as successful
completion of the invalidated exact receipt.

Wake clears the existing sleep flag but does not reopen exact queues. Fresh
adoption, while awake and not terminally stopped, advances the selected queue
generation and publishes validity only after the existing fence seed/flush and
hardware-ready publication. Queue generations saturate and permanently refuse
adoption rather than wrap. Stop latches terminal state before the first old
release callback; wake and reentrant adoption cannot clear it, even while the
aperture and lock still exist.

A separate invalidation epoch binds an in-progress exact submit to its first
lock-held admission. Every queue-space retry checks that epoch as well as
current queue validity. Thus an **old waiting request** refuses after a sleep
or forced-recovery boundary even if wake and fresh adoption have already
completed before it resumes. A new request may use the freshly adopted queue.
Ordinary R1b queue reselection/adoption retries that have not crossed a sleep,
fault or stop boundary retain the earlier source experiment's behavior.
Invalidation-epoch exhaustion is terminal and cannot wrap back into a prior
request's identity. Failed unpublished admissions cancel only their reserved
metadata; already published pending/lost receipts remain retained.

The [CPU runner](../tools/test_build34_exact_lifecycle.py) freezes the accepted
driver/ABI/topology, earlier transform/fixture/header and all new inputs. It
extracts nine actual staged methods, including complete power, wave-kill and
stop bodies. The [additional fixture](../tests/test_build34_exact_lifecycle.cpp)
extends the earlier submit fixture with CPU register, PM, cancellation and
release callbacks; these are not real platform callbacks or hardware events.

```sh
nice -n 15 taskpolicy -b make test-build34-exact-lifecycle \
  EXACT_LIFECYCLE_OUT=build/build34-r3-lifecycle-new-private
```

On November 20 the strengthened suite passed **1,968 additional ASan/UBSan
checks in 18 lifecycle groups**, alongside all **80 inherited submit groups**
(30,606 counted checks including the new wrapper assertion). It covers both
queues, repeated sleep, wake without adoption, single/all-wave recovery,
post-recovery fence advancement, sticky lost receipts, partial readoption,
generation/epoch exhaustion, a stop-release reentry and six blocked-submit
interleavings, including invalidation plus readoption before resumption.
Seven deliberately defective actual callsite variants fail the suite:
missing sleep invalidation, wake reopening queues, late fault invalidation,
nonterminal stop, adoption after terminal stop, missing submission gate and
allowing an old request across invalidation. Expected failed assertions stay
private. Preserve the initial fixture compile errors (CPU type alias and mixed
`auto` declarations) and the earlier narrower passing suite as prior evidence;
neither was a kernel candidate or hardware attempt.

The unchanged earlier submit suite again passes its **30,605 checks**, the
ownership suite passes **321,712 checks**, and default `make -j1 test` passes;
optional firmware fixtures remain absent. All **172 tracked production inputs**,
native ABI and runtime recipes remain unchanged. Compilation dependency and
device-linkage checks pass. See
[sanitized evidence](validation/build34-r3-lifecycle-offline-20261120.json).

This establishes only serialized CPU metadata classification and callsite
ordering. `gpuRetired`, the old fence reader, WAITSEQ, client close/free and
VMID release remain byte-identical; stop's old release operations also remain
unchanged after the new metadata prefix. **Those old release paths are not
certified as safe GPU drain.** No native exact observer, coherent fence
snapshot, owner allocator, callback-lifetime fencing, resource quarantine,
client-close drain, receipt acknowledgement or AMD completion event path has
been added. In particular, a metadata latch does not prevent another callback
from retaining a pointer to a lock/aperture that stop subsequently frees, and
this fixture does not certify the watchdog's broader selection/adoption races.
Full resource/service lifetime coordination remains mandatory before enabling
the exact branch. There is no new actual-thread/TSan, GPU, FPS or long-term
acceptance. Keep the accepted R1b/R2a/plugin installation active; R3 remains
source-only and R4–R6 remain pending.

## Selected callback admission and resource quarantine experiment

The [next isolated transform](../tools/build34_exact_callbacks.py) adds an
[embedded atomic admission gate](../tools/build34_exact_callbacks.h) to seven
actual entrypoints: submit, adoption, power, global-retirement observation,
wave recovery, watchdog inspection and its timer callback. The gate uses a
single lock-free 32-bit word, refuses count overflow and cannot reopen. A
noncopyable stack lease covers the whole selected method, including unlocked
queue-space sleeps and accesses after saving a lock or aperture pointer.
Closing admission does not require the GPU lock that stop might otherwise
free. The next submit retry checks closure before selecting a queue or
dispatching; adoption, power and recovery also recheck after taking that lock.

This experiment **replaces the previous staged stop body**, rather than
certifying its old releases. Stop atomically closes admission and takes one
service self-reference. A busy stop returns without waiting, taking `gpuLock`
or modifying metadata protected by that lock; this also supports reentry from
a callback already holding the lock. If already drained, stop performs the
earlier terminal metadata invalidation under the still-retained lock. Either
way, **all resources and the self-reference remain deliberately retained**.
There is no last-exit release, deferred cleanup, repeated stop retry, PM/base
stop call or GPU-drain shortcut. A busy stop does not later finish the
metadata invalidation; the closed gate itself stays authoritative. Any future
exact observer must check service admission/lifetime as well as queue epochs.

This deliberate leak/quarantine makes the staged stop unsuitable for
deployment. CPU callback drain cannot authorize release of pending or lost GPU
work, and no authenticated GPU drain or safe unload/teardown has been added.
The enclosing service must already be alive when any callback first touches
its embedded gate; IOKit callback ownership and all other entrypoints still
need a native lifetime audit. Client close/free and VMID release remain
byte-identical and are **not accepted as safe**. In particular, their old
bounded waits and BO/page-table release behavior are not repaired here.

The [new CPU runner](../tools/test_build34_exact_callbacks.py) freezes the
accepted build34 source and earlier transforms, extracts ten actual methods
into a [two-thread fixture](../tests/test_build34_exact_callbacks.cpp), and
excludes device runtimes from linkage. The earlier experiments are unchanged.

```sh
nice -n 15 taskpolicy -b make test-build34-exact-callbacks \
  EXACT_CALLBACKS_OUT=build/build34-r3-callbacks-new-private
```

On November 20 the strengthened suite passed **92 scenario groups, including
76 real-thread scenarios**, under both **ASan/UBSan and TSan**. Its assertion
count can vary with the scheduling of the close/admission race. It pauses the
actual callbacks before entry, after saving a lock/aperture pointer, while
holding the GPU lock and after receipt publication at the first packet write.
It also covers closure during an unlocked submit sleep even when space becomes
available, reentrant/concurrent stops, 64 close-versus-power races, early
returns, count-capacity refusal and permanently closed admission. A submit
past publication may finish after stop; its receipt and resources stay
retained, and loss cannot become successful exact completion.

Eleven deliberately defective staged versions are detected: removing any of
the seven entry leases, ignoring closure on a submit retry, omitting the
service pin, releasing an aperture during a busy stop, and treating CPU drain
as permission to release GPU resources. A timer closing after its last
closure check may still enqueue **one** tick; that tick refuses admission and
cannot rearm itself. The handle remains retained throughout. No claim of
atomic timer cancellation is made. The header also compiles as C++14 without
exceptions or RTTI; its object imports no allocated lock or atomic helper.
This is not a Kernel SDK/KPI build or an IOKit scheduling/lifetime proof.

The initial narrower 77-group/75-thread-scenario passing run is retained
privately. The existing lifecycle, submit, ownership and default regressions
are run separately; see the
[sanitized evidence](validation/build34-r3-callbacks-offline-20261120.json)
for their final results. All **172 tracked production inputs**, native ABI,
earlier experiments and runtime build/install recipes remain unchanged.
No kernel image, installation, GPU workload, runtime reconfiguration or power
action is authorized or performed by these tests. The accepted R1b/R2a/plugin
installation is retained. Owner/capability negotiation, coherent native fence
observation, receipt acknowledgement, full client/service lifetime and GPU
drain, broader watchdog selection/adoption races and AMD completion events
remain unresolved; R3 hardware/FPS/long-term acceptance and R4–R6 are pending.

## Exact client admission and permanent retention experiment

The [next isolated transform](../tools/build34_exact_client_lifetime.py)
extends the callback experiment with a deliberately non-reclaiming exact
client protocol. It does not modify production sources or a runtime recipe.
The exact Registry is still bound only by the CPU fixture, before `start`,
and must remain immutable. There is no native owner allocator, negotiation,
selector, acknowledgement or exact wait implementation.

An extracted-method CPU counterexample keeps its fake backend pending and
shows the existing `clientClose` releasing BO descriptors before its VMID
wait, and `vmidFree` clearing page tables after exhausting 2,000 sleeps.
The existing `free` likewise releases BOs after that bounded wait. These
are source/backend-model counterexamples, not observed failures of the
installed driver. The legacy path and actual `vmidFree`/WAITSEQ/fence reader
remain unchanged; this experiment does not repair or certify legacy cleanup.

Only after base `start` succeeds does the proposed exact path pin both the
client and its provider, before admitting exact operations. It refuses
operations before that pin and refuses repeat start. This avoids attempting
to resurrect an object from `free`; its later defensive guard is not an
IOKit finalizer proof. The fixture counts retain/release calls with platform
doubles; it does not execute OSObject destruction or establish native callback
ownership. Registry allocation/lifetime is still a prerequisite.

The actual dispatcher, descriptor-export method and private submit each take
a whole-method client admission lease. This includes the WAITSEQ, topology
and surface-mark fastpaths that bypass the dispatcher's client lock. The
dispatcher and descriptor export recheck closure after acquiring that lock.
Exact `clientClose` closes admission and returns without waiting, taking the
client lock, terminating, freeing BOs, releasing the session/VMID, or dropping
either start-time reference. Concurrent/repeated closes remain terminal.
The Registry stays writable so a submit admitted before close can publish
its receipt afterward. Closing the Registry immediately would lose that
admitted-publication path.

Before the fallible receipt reservation/backend admission, a sticky bit marks
the client's resources as exposed. Once set, the actual BOFREE and UNMAP
methods refuse before modifying maps/accounting, and a defensive `boRelease`
guard refuses descriptor completion/release. The bit stays set after failed
submission, receipt-table exhaustion, completed-metadata forget and a safe
global completion prefix. That prefix is preserved for legacy reclamation;
it is not a new unpin/drain protocol for this staged exact experiment.
Before first exposure the existing BOFREE/UNMAP behavior remains available;
MAP and other dispatcher leaves have not received a complete VM safety audit.

All client/provider references, BOs, mappings, locks, session and VMID remain
**permanently retained** after exact close, including idle close. There is
no last-callback cleanup, unpin, deferred reclaimer, timeout release or native
GPU drain. This intentional leak/quarantine **must not be built or deployed**.
Complete native lifetime, coherent observation, resource ownership and safe
reclamation still need implementation before a usable R3 candidate exists.

The [CPU runner](../tools/test_build34_exact_client_lifetime.py) freezes the
accepted build34 and prior experiments, extracts **14 actual methods** into
the [fixture](../tests/test_build34_exact_client_lifetime.cpp), checks its
non-system compilation dependencies and excludes device runtimes from linkage.
Other dispatcher leaves and the service/GPU backend are explicit CPU doubles.

```sh
nice -n 15 taskpolicy -b make test-build34-exact-client-lifetime \
  EXACT_CLIENT_OUT=build/build34-r3-client-new-private
```

On November 21 the suite passed **2,578 checks in 17 groups, including eight
real-thread scenarios**, under both **ASan/UBSan and TSan**. It covers close
during backend submission, unlocked wait, topology/surface fastpaths and
saved-lock acquisition; descriptor export, queued callbacks, two simultaneous
closes, an independent client, idle/repeated close, pre-exposure release and
legacy behavior. Sixteen deliberately broken versions are detected: missing
start-time client/provider pins; any of three entry leases; either lock-held
closure recheck; fallthrough into legacy teardown; omitted free/freeAll/
boRelease or BOFREE/UNMAP guards; missing sticky exposure; premature Registry
close; and a global-prefix shortcut that violates this experiment's retention
policy. Expected assertion failures remain private. Preserve the initial
unused-fixture-counter compile failure as evidence; it was not a kernel build.

The separate unchanged callback, lifecycle, submit, ownership and default
regressions are recorded in the
[sanitized evidence](validation/build34-r3-client-lifetime-offline-20261121.json).
All **172 tracked production inputs**, ABI, earlier experiments and runtime
recipes remain unchanged. No installation, runtime reconfiguration, GPU work,
reboot or FPS/long-term acceptance occurred. Keep accepted R1b/R2a/plugin and
startup/recovery settings active. R3 remains source-only; R4–R6 have not begun.

## Target observation with a deliberately unbound device reader

The [next isolated transform](../tools/build34_exact_observer.py) adds two
proposed internal helpers: the client's `queryExact` and the service's
`observeExact`. Neither has a native selector or production caller. It also
stages a small `Registry::inspect` accessor into a private copy of the earlier
header; the original header and all earlier experiments remain unchanged.
Inspect validates owner/lease/slot and copies a receipt, never an entry pointer;
reserved, lost, closed, foreign and reused tickets refuse that copy.

The client helper takes a lifetime lease, requires its start-time pin and holds
the client lock across lookup, service observation and classification. The
service helper takes its own lifetime lease and then the GPU lock, preserving
submit's client-before-GPU lock order. The receipt chooses the actual queue;
an empty or reused transport-history slot never supplies ownership. Snapshot
metadata includes queue generation, readiness and a new per-queue submitted
upper bound. Actual staged submission updates that bound for both exact and
legacy work; adoption seeds it to the same `gSeq` written to its new fence.
This bound is validation metadata, not a retirement watermark.

Only the target queue is sampled. Cached and actual map bounds, pointer
overflow and eight-byte alignment are checked first. A generation/readiness
loss requires no fence read. The resulting sample cannot exceed that queue's
submitted bound; a lower sample after an earlier completion is refused. The
service classifies while both locks are still held and rechecks **both**
terminal gates after reading. Thus a busy stop that never finalized queue
metadata still prevents successful observation. Client/service closure during
the controlled reader marks the receipt lost; a later callback cannot revive
it. Sleep, wave recovery and readoption serialize on the GPU lock. An observer
can finish before a concurrent invalidator acquires that lock; the subsequent
query then reports loss. This is a serialized/linearized observation contract,
not a guarantee that a result cannot return after an overlapping close.

**No native hardware reader is implemented or admitted.** Its pointer defaults
to null, has no production assignment and is bound only by the CPU fixture.
Absent/failed sampling returns `InvalidObservation`, never a fallback to the
old two-word `queueFence` read. The fixture samples controlled CPU bytes under
its mutexes. It proves neither GPU write atomicity, CPU/device coherency,
BAR caching/flush rules nor a real reader's bounded/nonblocking behavior.
The source callback contract requires those properties before a future native
binding; holding locks across an unbounded reader would be unacceptable.
Registry allocation, lifetime and authentication to the provider also remain
fixture assumptions, not a native owner allocator or security boundary.
No new hardware fault detection or interrupt/event route is provided.

The old `queueFence`, global `gpuRetired`, WAITSEQ and VMID cleanup methods
are unchanged from the preceding source experiment. The legacy global prefix
retains its conservative resource-reclamation meaning; exact target success
does not advance it. This observer does not implement a blocking exact wait,
flush completed BOs, publish CPU fences, acknowledge receipts, unpin the client
or free any resource. The earlier permanent client/service quarantine remains
deliberate and **must not be built or deployed**.

The [runner](../tools/test_build34_exact_observer.py) freezes production and
prior experiment inputs and extracts **eight existing staged methods plus
the two new helpers** into the [CPU fixture](../tests/test_build34_exact_observer.cpp).
The generated registry header is checked separately; non-system compilation
dependencies and device-runtime linkage are verified. Only the new test target
uses these transforms; no runtime build/install recipe applies them.

```sh
nice -n 15 taskpolicy -b make test-build34-exact-observer \
  EXACT_OBSERVER_OUT=build/build34-r3-observer-new-private
```

On November 21 the strengthened suite passed **41,806 checks in 162 groups**,
including **128 independent model rounds and ten real-thread scenarios**, under
**ASan/UBSan and TSan**. In the CPU backend, GFX 101 completes while compute
100 remains pending and the legacy prefix stays 99. Coverage includes fallback
queue selection, legacy submissions, history reuse, metadata forget, unknown
ownership, unavailable/rejecting readers, future/stale samples, map/address
refusal, sleep/wave recovery/readoption, queued/overlapping close, and reader
serialization against adoption, sleep and recovery. Controlled CPU sequence
values cross the 32-bit boundary and approach 64-bit exhaustion; this is not a
hardware rollover/coherency test. A prior narrower 160-group passing run is
retained privately.

Sixteen deliberately defective versions fail: missing either lease or the
start pin, skipped client closure recheck, using global `gSeq` as the target's
upper bound, forged generation, wrong queue, ignoring either post-reader gate,
missing GPU lock, legacy-read fallback, omitted submit/adoption bound updates,
invented readiness and ignored cached/mapped bounds. Expected assertion failures
remain private. The staged inspect accessor also compiles as C++14 without
exceptions or RTTI; this is not Kernel SDK/KPI compilation.

Separate client-retention, callback, lifecycle, submit, ownership and
default regressions are recorded in the
[sanitized evidence](validation/build34-r3-observer-offline-20261121.json).
The first default run failed in an existing **CPU-only** trace test: its fake
trace exited after a fixed 0.2 seconds before the parent released its fake
probe, so the test never reached the intended post-release uncertainty case.
That one test now keeps the fake trace alive until the fake probe acknowledges
`G`, and exits the fake probe on EOF rather than sleeping. The real trace
controller, its admission/retention semantics and hardware scopes are unchanged.
The original failure stays private; the corrected eight-case trace suite and
full default suite are checked separately. No DTrace or GPU process ran.

All **172 tracked production inputs**, ABI, earlier R3 experiments and runtime
recipes remain unchanged. No installation, runtime configuration, GPU work,
reboot, physical FPS or long-term acceptance occurred. Keep the accepted
R1b/R2a/plugin installation and existing startup/recovery settings active.
Native reader/owner/capability/acknowledgement, safe reclamation, completion
events and paired hardware acceptance remain prerequisites; R4–R6 are pending.

## Embedded Registry and module-lifetime owner binding

The [next separate source transform](../tools/build34_exact_binding.py) replaces
the preceding experiment's externally supplied Registry pointer with storage
embedded in the client. It changes only newly generated private source/header
copies. Prior transforms, the original ownership header and production files
remain unchanged. `exactRequested` defaults false with no native assignment,
selector or negotiation; no real client can request this experiment.

After the actual base `start` succeeds, the proposed service helper admits the
embedded Registry under its callback lease and GPU lock. It checks the actual
client type, storage address, provider, requested/start-attempt state, existing
binding/pin and terminal gates. Closure is checked again after acquiring the
GPU lock. It binds identity and retains client/provider before publishing the
client's exact pointer. Failed exact start cannot retry or silently enter a
legacy close path. Successful binding cannot repeat, including after receipt
forget, close, queue adoption or all metadata becoming empty.

One module-lifetime `OwnerEpochs` counter is shared across service instances;
it is not a member reset by service start/stop or readoption. Its constant
initializer requires no dynamic global constructor. Lock-free 64-bit CAS
allocates nonzero IDs, reserves UINT64_MAX, refuses wrap and limits each call
to **32 attempts**. Contention can conservatively refuse admission without
changing the output; refusal is not a GPU fault or evidence of ID exhaustion.
This is a bounded attempt count, not a scheduler latency guarantee.

The client dispatcher, descriptor export, submit and query validate the exact
pointer against their embedded storage and immutable provider/client labels.
Service submit and observation independently check those labels, and the real
staged submit passes its client identity. The owning ticket still validates
owner/serial/slot within that Registry. Invalid query identity refuses before
the client lock; invalid submit identity refuses before IB validation or GPU
admission. Internal pointer labels are not a userspace credential or negotiated
capability. There is no claim of protection against arbitrary kernel memory
corruption or an untrusted native selector, which does not exist here.

The [CPU runner](../tools/test_build34_exact_binding.py) extracts **12 actual or
proposed staged methods** into a [new fixture](../tests/test_build34_exact_binding.cpp).
Its independent allocator test forces controlled CAS failures in the actual
generated header. The unchanged earlier ownership fixture is also compiled
against that generated header to check its full state model. Frozen dependency
and linkage checks exclude device runtimes. Framework casts, reference counts,
base start, locks and aperture/reader bytes are explicit CPU doubles, not
IOKit object destruction or device-coherency tests. The header separately
compiles as C++14 without exceptions or RTTI; native casts are not covered by
that header-only check.

```sh
nice -n 15 taskpolicy -b make test-build34-exact-binding \
  EXACT_BINDING_OUT=build/build34-r3-binding-new-private
```

On November 21 the suite passed **4,983 checks in 22 groups, including five
real-thread scenarios**, under both **ASan/UBSan and TSan**. Eight threads
exercise the real owner CAS; distinct clients bind concurrently across two
providers. Controlled threads also close client/service admission while start
is waiting for the GPU lock, and close a client during target observation.
Coverage includes cross-provider/client refusal, external/prebound storage,
failed/repeated starts, legacy admission, identity-preserving receipt forget,
slot reuse, readoption, stop and conservative global retirement. A separate
**73-check** controlled-CAS fixture proves the 32-attempt refusal/final-attempt
success and concurrent-exhaustion boundaries in that algorithm, without
claiming real scheduler bounds. The unchanged Registry state suite passes
**321,712 checks and 128 independent model rounds** against the new header.

All **27 deliberately defective versions** are detected: 25 source/header
identity, lifetime, pin, closure, locking, owner-exhaustion and callsite changes,
plus two retry/output-policy defects. Preserve the initial CPU fixture compile
failures (missing `mmio` double, uninitialized identity labels and an unused
delay stub), the first mutation-coverage gap and the discarded mutant's own
unused-variable compile error. The coverage gap occurred because the service
still refused a request after its client check was removed; the strengthened
fixture checks refusal before IB validation/query locking. These are CPU
fixture/coverage corrections, not kernel-build or installed-driver failures.
Expected assertion failures and all earlier logs remain private. See the
[sanitized evidence](validation/build34-r3-binding-offline-20261121.json).

Separate unchanged target-observer (**41,806 checks/162 groups/ten threaded
scenarios**) and client-retention (**2,578 checks/17 groups/eight threaded
scenarios**) regressions pass under ASan/UBSan and TSan. Default `make -j1 test`
also passes; optional firmware fixtures remain absent and are skipped by its
existing rule. All **172 tracked production inputs**, ABI, previous R3
experiments and runtime recipes remain unchanged. No live runtime readback,
installation, GPU work, reboot, physical FPS or long-term trial occurred.

The native factory must still serialize one client's start and publish the
client only after it succeeds. The CPU concurrent tests use distinct clients;
they do not prove arbitrary simultaneous `start` calls on one native object.
Module unload/reload, real OSObject/KPI behavior and a complete entrypoint/VM
audit remain unproved. The existing permanent client/service quarantine pins
the embedded Registry's containing object in this source protocol; it is not
a native unload proof, GPU drain or usable resource-lifetime solution.

No admitted hardware reader, exact selector/capability negotiation, blocking
wait, receipt acknowledgement, BO/VMID reclamation, completion interrupt/event
or installation recipe is added. The old fence reader, safe global retirement,
WAITSEQ, VMID cleanup and permanent quarantine remain unchanged. This experiment
**must not be built or deployed**. Keep accepted R1b/R2a/plugin/startup active;
R3 GPU/FPS/long-term acceptance and R4–R6 remain pending.

## Owned-ticket bounded polling fallback (November 21)

The source-only [wait transform](../tools/build34_exact_wait.py) now adds an
internal `waitExact(sequence, timeout)` after the embedded-binding experiment.
It obtains one owner/slot/serial ticket under the client lock and retains that
identity across every sleep. It never re-resolves a recycled sequence or slot.
A client callback lease spans the whole operation; each observation retains
the existing client-to-GPU lock order, and both locks are released before
`IOSleep(1)`. Closure, stop, invalidation and queue readoption refuse completion.

The budget starts at method entry, including lock contention, reader time and
scheduler delays, using the real monotonic-clock conversion. It retains the
existing two-second cap. Zero budget performs one observation. Every positive
pending wait yields for one millisecond, even for a sub-millisecond remainder.
An observation after wake may complete before the elapsed-time test, but an
expired pending result never sleeps again. This rounding and scheduling policy
is **not a hard return-time bound**, an AMD interrupt or an event wakeup path.

The frozen-source [CPU runner](../tools/test_build34_exact_wait.py) extracts
13 methods, retaining all twelve previous binding methods byte for byte.
ASan/UBSan and TSan each pass **22,000 additional checks**, **28 additional
groups** and **six additional real-thread scenarios**, plus the inherited
4,983-check binding suite. Thirteen deliberately broken waits are detected,
including no client lease, bad identity/pin, missing cap, late extra sleep,
false completion, lock-held/zero-length sleeps, omitted clock conversion,
budget reset after lock contention, ignored closure, global-prefix targeting
and requested-sleep accounting. A pending compute 100 with complete GFX 101
still leaves the safe global watermark at 99.

Preserve both initial fixture failures privately. The first incorrectly
expected the global watermark to remain 99 when the only queue's work had
completed. The second confused an open idle callback gate with a closed,
drained gate. The corrected fixture checks `active()==1` while sleeping and
`active()==0` on return, checking `drained()` only after closure. These were
CPU test expectations, not native-driver failures. The missing-lease broken
version is detected with the strengthened active-count assertion.

The separate unchanged binding suite also passes, including its 321,712
ownership checks/128 reference rounds and 73 controlled-CAS checks. Default
`make -j1 test` passes with the existing optional-firmware skip. See
[sanitized evidence](validation/build34-r3-wait-offline-20261121.json).
All 172 production inputs, prior transforms, old WAITSEQ/global retirement/
VMID paths, ABI and runtime recipes remain unchanged. The hardware reader
still defaults null, exact requests remain disabled, and permanent quarantine
remains deliberately unreclaimable. This is not a native SDK build, deployable
candidate, GPU wait test, FPS or long-term acceptance. No installation, live
runtime readback, GPU work or power action occurred. Continue with the
[R3 completion ledger](BUILD34-R3-PLAN.md); R3 remains incomplete.

## Device-read contract review and low-dword window (November 21)

[BUILD34-FENCE-READER.md](BUILD34-FENCE-READER.md) records primary-source
Linux GFX11/fence and Apple mapping-interface review with pinned revisions,
licence checks and digests. No implementation was copied. Linux's 32-bit
per-ring scheme does not automatically justify this project's global64 or
BAR0 mapping. Neither the old two-dword read nor packet width alone establishes
an atomic 64-bit device observation; actual effective cache attributes and
old-generation writers remain native prerequisites.

An original, unintegrated `FenceWindow32` primitive passes 189,198 ASan/UBSan
arithmetic/state checks, exhaustive small-width intervals and 20,000 sustained
steps across 32-bit wraps, with twelve defective versions detected. Its strict
less-than-`2^32` interval counts global sequence gaps and refuses ambiguity;
it never silently treats a modulo alias as completion. It has no device load
or production/staged-driver caller. The explicit stale-whole-wrap counterexample
shows why coherent non-regressing device samples remain an unproved input
condition. C++14/no-exceptions/no-RTTI compilation and default tests pass;
no thread-safety, native SDK, hardware coherency, installation, GPU or FPS
claim follows. All 172 production inputs, previous transforms, ABI and runtime
recipes remain unchanged. See [sanitized evidence](validation/build34-r3-fence32-offline-20261121.json).

## Wait-pinned receipt acknowledgement (November 21)

The next isolated [source transform](../tools/build34_exact_ack.py) adds an
internal `ackExact(sequence)` and per-receipt waiter counts. This is receipt
metadata lifetime, **not** a native ACK selector or BO/VMID reclamation.

An admitted wait pins its captured owner/slot/serial under the client lock
before releasing that lock. Every later result, including timeout, invalid
observation, close and queue loss, releases that pin under the same lock.
The fixed 16-bit count refuses saturation and underflow. A closed Registry
can release a previously admitted pin but cannot accept a new one. An old
ticket cannot decrement a reused slot's new serial. No dynamic allocation
is added, and total Registry storage still satisfies its existing size bound.

The new acknowledgement takes a whole-operation client lease, validates the
actual embedded Registry/provider/client binding, and looks up and observes
the target under the client-to-GPU lock order. Only proven completion can
reach `forget`. `forget` returns the new internal `Busy` status while any
admitted wait still pins that record. Pending, lost, unknown, unavailable
reader and closed-client paths retain the receipt. Forgetting does not clear
sticky GPU exposure or release any native resource/reference, and never
publishes a CPU fence or promotes the safe global watermark.

ASan/UBSan and TSan each pass **228,946 additional checks**, **19 additional
groups** and **five additional real-thread scenarios**. They exercise full
64-receipt admission refusal before packet writes, subsequent completed-slot
recovery, 2,000 alternating-queue submit/complete/acknowledge cycles, invalid
identity/readers, generation loss, stop/close and two independently paused
waiters. Completion cannot evict their ticket until both have returned.
The counter is tested to its actual 65,535-waiter saturation boundary and
back down, including stale tickets and close-time pin release.

All 28 earlier wait groups and six threaded cases also run on this **new**
staged wait under both sanitizers (**22,094 checks**), plus the unchanged
4,983-check binding suite. Only the earlier fixture's two deliberate forget
attempts are adapted in its generated private copy: they must now return
`Busy`, keep the ticket and let the wait complete, rather than evict the ticket
and return `Unknown`. Its original frozen file and every prior transform
remain unchanged. Twelve defective wait/pin/acknowledgement implementations
are detected. Default `make -j1 test` passes; optional firmware keeps its
existing skip. See [sanitized evidence](validation/build34-r3-ack-offline-20261121.json).

The native wire protocol, client mode/capability negotiation and paired Mesa
payload ownership remain absent. Userspace must eventually coordinate ACK
with every current and late payload reference; a local metadata-forget helper
does not solve that lifetime. Nor does a completed receipt or empty Registry
prove that resources from forgotten submissions can be freed. Permanent
client/service quarantine remains intact and undeployable, hardware reader
binding remains null, and the low-dword primitive is still unintegrated.
All 172 production inputs, original ABI, legacy WAITSEQ/global retirement/VMID
paths and runtime recipes remain unchanged. No native SDK build, installation,
live runtime change/readback, GPU execution or reboot occurred. R3 remains
active and incomplete; R4–R6 do not advance.

## Exact CS representation preflight (November 21)

Paired-ABI review found another boundary in the actual frozen Mesa transport.
`acd_kext_submit` splits plans larger than `N48N_MAX_IBS` (64) and returns only
the last native sequence. The planner also retains each IB's engine, while
one build34 native submission selects a single actual queue from its first
IB. Exact completion of only the final native call is not a proved aggregate
completion for a mixed-queue plan. Existing 0005 input-dependency waiting
does not order the internal fragments of one newly submitted plan.

The new [actual-source CPU fixture](../tests/test_build34_exact_cs_shape.c)
reproduces two **prospective exact-backend counterexamples** on 0003–0005:
a 65-IB compute/GFX plan emits two native calls and its final exact sequence
signals the output while the earlier sequence remains pending in the fake
backend; a two-IB mixed plan reaches one native packet batch despite its
different engine fields. This does not reproduce an installed legacy-kernel
failure, execute IBs or establish real GPU instruction behavior.

[Patch 0006](../mesa-patches-build34/0006-radv-exact-cs-shape-guard.patch)
changes only the exact-mode preflight in `ac_darwin_drm.c`, after 0003–0005.
It accepts a single native-size homogeneous GFX or compute batch, instance
and ring zero. Larger plans, mixed engines and unsupported engine/instance/
ring values refuse with `EOPNOTSUPP` **before** any dependency wait, native
submission or output-payload attachment. This is conservative refusal, not
an implemented aggregate fence, a GPU queue dependency or a performance
optimization. Homogeneous plans over 64 IBs also refuse rather than relying
on unproved fragmented receipt/lifecycle behavior. Legacy mode is unchanged.

The [frozen CPU runner](../tools/test_build34_exact_cs_shape.py) applies all
four patches to a fresh verified 30-file source closure and preserves the
original MIT notice. ASan/UBSan passes **1,901 checks**, including **8 accepted
and 80 refused shapes**, empty-plan rejection, provider clones, unchanged
byte-exact unchanged ioctl request/output on error, transfer-proven unattached
refused outputs and legacy splitting. Nine defective preflights are detected, including a
uniformly unknown engine (so the mixed-engine check cannot hide a missing
engine allow-list), an output write before refusal and a guard moved after
dependency waits. All **4,552**
previous actual-CS dependency checks pass on the changed wrapper. Default
tests pass with the existing optional-firmware skip. See
[sanitized evidence](validation/build34-r3-cs-shape-offline-20261121.json).

Review also confirms that raw `DRM_AMDGPU_WAIT_CS` queries go directly through
the transport, and the provider can attach a reference to an older sequence
after an earlier wait completed. The internal native ACK experiment makes a
forgotten receipt `Unknown`. Therefore, do **not** automatically wire ACK to
each positive backend wait: a paired design still needs bounded completion
ownership/cache or explicit payload lifetime that serves every later valid
query, plus race/backpressure/uncertain-transport handling. Do not replace the
safe global watermark with a target or confuse any future client-local
completion summary with global BO/VMID retirement. Raw LAST/BO-idle semantics
must continue to cover all relevant work rather than just the latest GFX
receipt. These are outstanding native/paired-runtime admission requirements.

Production exact capability remains false, all prior patches and the 172
driver/plugin/ABI/tool inputs remain unchanged, and old runtime recipes do
not apply 0006. No full RADV/native kernel build, installation, IOKit open,
GPU work, power action, physical FPS or long-term acceptance occurred.

## Paired Mesa completion and ACK lifetime (November 21)

The previous internal ACK alone could not be wired after every positive wait:
the actual provider permits late attachment, and raw WaitCS bypasses that
provider. A naive adapter that forgets native sequence 20 after its first
successful query leaves neither path able to answer a later valid reference.
The new fixture reproduces this **prospective auto-ACK counterexample** on
the actual 0003–0006 provider/transport with a controlled CPU backend. It is
not an installed-driver failure or a GPU reproduction.

[Patch 0007](../mesa-patches-build34/0007-radv-exact-receipt-lifetime.patch)
follows 0003–0006 and changes only `ac_darwin_kext.c` and its header, retaining
their MIT notices. A one-shot callback adapter can be configured only before
sequence traffic. Only the CPU fixture configures it; the production provider
capability stays false and existing runtime recipes apply none of this new
experiment. The callback table is **not** a native wire ABI, capability probe,
selector implementation or device reader.

The actual transport now has the following tested source-only behavior:

- Reserve one of **4096 bounded records before submission**. Exact mode
  independently enforces one homogeneous 1–64-IB GFX/compute packet, with
  instance/ring zero, including direct marshaller callers. A transport-local
  submit mutex serializes admission; no callback runs under the cache mutex.
  Configuration, callbacks and cached-query reentrance are exercised. This
  does not prove IOKit lock order or native callback lifetime.
- A successful receipt must have this immutable session owner, a new native
  sequence and native ticket serial, a valid slot/queue, and a nonzero,
  non-sentinel generation. Submission errors release their reservation only
  when the adapter explicitly certifies **no dispatch and no native receipt**.
  Uncertain errors or malformed successes poison the connection and retain
  uncertain metadata. No reset/rebind API can silently reuse that session.
- A pending query pins its record across the unlocked native callback.
  A trusted nonbusy reply is saved as an exact completed fact **before ACK**.
  Another pending/stale response cannot undo it. A pin prevents ACK/reuse;
  in-flight ACK also prevents reuse. ACK Busy preserves retryable ownership,
  with a nonrecursive service limited to 64 attempts per call. Other ACK
  errors poison the session rather than assuming an acknowledgement arrived.
- Completed/ACKed facts above the genuine safe global prefix remain available
  to late syncobj attachments and raw WaitCS. A record can be cleared only
  after that prefix covers it, ACK succeeded and all pins/callbacks left.
  Below the prefix, raw handles within this client's emitted bound preserve
  legacy completed-prefix readiness, including old raw sequence holes. This
  is a globally proved completion result, **not** evidence that an exact
  native receipt belonged to that client; no missing receipt above the prefix
  can imply completion. Global retirement is never advanced to an exact GFX
  target or to a client-local completion summary.
- Zero/snapshot and LAST use an independently specified prefix callback.
  **Legacy WAITSEQ(0,0) is not used as a pure snapshot:** the actual build34
  handler flushes BOs and may publish the pending CPU fence. LAST/BO-idle
  wait for the genuine global prefix through the captured client-emitted
  target, not just the last exact GFX receipt. An absolute LAST wait captures
  that target once rather than chasing concurrent new submissions.
- Raw native sequence values remain unchanged, including the value associated
  with a CPU user-fence request. The fixture checks marshalling/value identity;
  it does **not** prove native CPU-fence publication or memory visibility.
  Adapter observations must provide those real guarantees before integration.
  Snapshot owner/values are checked, older concurrent prefixes merge without
  regression, and observation errors poison the session except explicitly
  retryable EINTR/EAGAIN. A known terminal error cannot be masked by a cache hit.

When an earlier compute gap outlives all 4096 records, new submission returns
EAGAIN before dispatch; it neither evicts the pending compute nor forgets later
completed GFX. A fresh genuine prefix snapshot permits compaction/reuse after
the gap closes. This is bounded safety/backpressure, **not demonstrated RADV
retry behavior or long-running performance acceptance**. Real caller handling,
the storage/scan cost and ACK/prefix syscall latency still require integration
and measurement; the cache is not claimed to improve FPS.

The [runner](../tools/test_build34_exact_transport.py) freezes the same 30-file
reviewed Mesa closure, the earlier patches/tests and all 172 production inputs.
ASan/UBSan passes **112,869 checks** and TSan **112,867 checks**, including full
64-receipt refusal/recovery, all 4096 cache records with an earlier compute
pending, safe compaction and late queries, ACK Busy, uncertain dispatch,
twelve malformed receipts, session loss, direct shapes and raw sequence
identity. Counts include checked condition waits and can differ with thread
scheduling. Four real-thread scenarios cover two pinned readers, a late
pending reply, an in-flight ACK with concurrent prefix/query/submit, and an
older prefix reply arriving after a newer global snapshot. All **21 defective
variants** are detected. Previous actual-CS suites still pass **1,901** shape
checks and **4,552** dependency checks. See
[sanitized evidence](validation/build34-r3-transport-offline-20261121.json).

Run only with matching reviewed source and a fresh ignored output:

```sh
nice -n 15 taskpolicy -b make -j1 test-build34-exact-transport \
  MESA_SOURCE="$MESA_SOURCE" \
  EXACT_TRANSPORT_OUT=build/build34-r3-transport-new-private
```

Transport destruction still requires **caller quiescence**. This patch does
not reclaim native BOs/VMIDs, establish a device/session drain, bind the reader,
implement the independently required prefix/visibility protocol, add AMD
completion events, or make permanent native quarantine deployable. All earlier
transforms/patches, native ABI, protected production files and installed
configuration remain unchanged. No kernel SDK/full RADV build, IOKit open,
installation, GPU work, reboot, physical FPS or long-term acceptance occurred.
The accepted R1b/R2a/plugin/startup settings stay active; R3 remains incomplete
until its native and hardware ledger closes, and R4–R6 remain pending.

## Complete-token native receipt dispatch (November 21)

The earlier internal wait/ACK authenticate the client but resolve a sequence
to a ticket internally. The proposed Mesa adapter retains a full native
receipt, so the native request also needs to bind owner, slot, serial,
sequence, queue and generation rather than silently discarding those fields.
The new staged transform adds complete-token methods and an exact-size
64-byte wait/ACK structure route in the actual `externalMethod`, before its
legacy client lock. It leaves the old internal methods, native ABI, reader
binding, permanent quarantine and all protected production inputs unchanged.

The [new contract](BUILD34-RECEIPT-WIRE.md) documents experimental selectors
64/65, fixed C/C++ layout, strict format and synchronous-argument validation,
unchanged error output, copied-input lifetime, pinned waits, completion-only
ACK and terminal rechecks before reply. A pinned primary XNU interface review
is distinct from actual SDK or installed-kernel validation. The hand-authored
C peer is not a production Mesa adapter or IOKit/MIG execution test.

The handler carries its original monotonic timestamp through parsing and the
outer handshake lock into the typed wait; it must not restart that budget
after queueing. Pending-after-expiry and completed-after-queueing cases pass.
ASan/UBSan and TSan each pass **372,707 additional checks / 320 groups / five
real-thread scenarios**, with the complete earlier binding/wait/ACK regression
counts unchanged at **4,983 / 22,094 / 228,946**. Twenty deliberately faulty
implementations are detected, including stale/mixed identity, unpinned waits,
route-under-lock, input reread and 32-bit result truncation. See
[sanitized evidence](validation/build34-r3-receipt-offline-20261121.json).
Default tests also pass. No capability/mode request, exact-submit wire reply,
global-prefix or visibility/CPU-fence operation, healthy resource drain, AMD
event, Kernel SDK/full native compile, installation or GPU acceptance is
added. This adds source-level strict marshalling; R3's native and hardware
requirements remain open.
