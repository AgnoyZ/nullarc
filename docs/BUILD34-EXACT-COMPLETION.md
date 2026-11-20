# Build34 R3 exact completion and safe retirement

Current November 20 checkpoint: R1a/R1b and R2a's bounded functional trial
have passed. R2a's installed combination remains active; no speedup is
established. R3 has tested **source-only Mesa bookkeeping, multi-target
wait/query and conservative CS dependency prerequisites**, not an installed
exact-wait implementation.
An additional allocation-free ownership/queue-generation **state prototype**
has CPU evidence but no production caller or native integration. R4–R6 have
not started.

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
