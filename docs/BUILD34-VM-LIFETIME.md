# Build34 R3 context identities and checked VM cleanup

November 21, 2026: a new source-only stage extends the
[checked global/VMID experiment](BUILD34-GLOBAL-VMID.md) with context allocation
identity and failure-preserving service VM cleanup. The installed build34,
172 protected production files, native ABI, prior experiments and runtime
recipes remain unchanged. Native exact mode and the device reader remain
unbound, and permanent exact-client/service retention remains in place.
**This is not an admitted kernel candidate; do not compile or deploy it.**

## Identity and entrypoints

The original MIT [transform](../tools/build34_exact_vm_lifetime.py) carries
the internal `(handle, allocation generation, client identity)` through actual
allocation, mapping, unmapping, binding, submission and VM release. The actual
client `ensureVmid` obtains the pair, and both actual submit variants pass it.
No pointer or generation is taken from userspace and the native ABI is unchanged.

Allocation generations live in the context slot, outside queue history. They
advance only on a successful allocation, persist across release and refuse
exhaustion. Allocation also rechecks the output pair after acquiring the lock
and refuses invalid cached root descriptors/addresses. All VM identity checks
occur under `gpuLock` and a service callback lease. A context pointer is never
carried across an unlocked wait or obtained
before the lock in map/unmap. Each actual submit records the context's newest
sequence and its separate sequence/generation pair for both queues.

Queue generation loss cannot be repaired by a new adoption's CPU fence seed.
Every busy context's recorded work must still belong to its actual live queue
generations before a valid global prefix can be published. VM lookup and
victim binding independently check that work identity. A newer GFX submission
does not erase older compute work. Lost/uncertain work consequently retains
its context and blocks the global retirement path until a separately proved
recovery exists; no old stamp is silently forgotten or reseeded.

## Mapping and release

Actual map/unmap validate nonempty aligned ranges and arithmetic bounds before
PTE access. Map also validates descriptor length and complete, representable,
aligned physical pages. Both require a checked global prefix covering this
context's newest actual submission before modifying its tables; pending work
returns Busy without a PTE write. This is conservative source-stage admission.
The paired RADV caller's retry/backpressure behavior and its performance cost
have not been accepted.

`vmidFree` now returns an explicit success result. Under the GPU lock it
validates ownership, marks the context closing and captures the authoritative
context newest sequence, never trusting the caller's smaller `lastSeq` alone.
Closing blocks subsequent map/unmap/bind/submit of that allocation. Pending
completion releases the GPU lock and yields within a real monotonic two-second
budget; every retry revalidates the complete identity. Unknown/lost completion
or timeout returns false with tables, hardware association, busy state and
allocation generation retained. A temporary failure leaves the context closing;
only a later call with the same valid identity can retry.

Before the first table clear, release validates every used chunk and the
reciprocal hardware allocation generation, if bound. It requires a checked
TLB result while the table bytes are still intact. Only after success does it
clear the used pages, remove the hardware association and make the slot free.
The allocation generation persists. This is service VM metadata/table cleanup,
not authorization to release client BOs or OSObjects.

## TLB failure propagation

The additional checked helper uses build34's existing engine-17 request and
ACK register/mask protocol. It bounds polling by both real monotonic elapsed
time and 1,000 requested microsecond delays, includes read/scheduler time and
does not delay again after expiry. It rechecks terminal gates after reading.
The old void helper stays unchanged but has no caller in this new stage.

Binding publishes the new reciprocal metadata only after this check succeeds.
If binding, mapping or release has an uncertain TLB result, a sticky service
VM-fault gate refuses subsequent VM allocation, mutation, submission and global
retirement; the experiment never guesses that rollback or retry repaired it.
Partial map/PTE failure also closes that gate, rather than making an untracked
partial mapping available to future submissions.

This propagates software-observed failure; **it does not establish hardware ACK
freshness, effective mapping attributes or the ordering of an actual invalidation**.
In particular, the old level-bit protocol's treatment of a bit already set
before a request still needs hardware/source admission. CPU ACK doubles do not
prove a new GPU acknowledgment, and the existing engine/register convention
is not being independently accepted by these tests.

## Test scope

The [runner](../tools/test_build34_exact_vm_lifetime.py) freezes prior input
digests and extracts the actual staged VM methods, actual context/hardware
layouts and actual client `ensureVmid`, submit and receipt-observation paths.
The fixtures use handwritten CPU IOKit, allocator, page-walker, descriptor,
register, clock and delay doubles. The actual native page walker and a complete
Kernel SDK translation unit are not compiled or exercised.

ASan/UBSan and TSan each pass **100,411 checks in 35 groups and six real-thread
scenarios**, with all **26 defective variants** detected at runtime. The
separate earlier global/VMID fixture is not included in that
count. The first development compile found a duplicate declaration and signed
fixture constant; the original failed records are preserved privately and are
not native SDK or driver failures.

Coverage includes ownership and generation exhaustion; repeated multi-chunk
cleanup/reuse; stale tokens even at the same client address; queued map/unmap
and unlocked-submit ABA; both queue work stamps across readoption; independent
GFX progress while a compute context waits for release; timeout preserving
every table byte; cached/victim hardware generations; partial physical-page
and PTE failures; wrong ACK bit, delayed ACK, stopped-clock cap and terminal
closure after reading. Faulty variants must fail at runtime rather than merely
failing compilation. Counts and the final mutant list are recorded in
[sanitized evidence](validation/build34-r3-vm-lifetime-offline-20261121.json).

```sh
nice -n 15 taskpolicy -b make -j1 test-build34-exact-vm-lifetime \
  EXACT_VM_OUT=build/build34-r3-vm-lifetime-new-private
```

## Remaining native/reclamation blockers

The old **legacy client** `freeAll`/BO-release ordering, ignored VM-release
return and finalization have not been repaired by this service layer. Exact
clients still take the earlier permanent retention path, so this stage does
not enable healthy client/service teardown, descriptor release, unload or a
reclaimer. Do not confuse a safe VM-slot return with a drained client, an empty
receipt table or a proved BO lifetime.

Full entrypoint/page-walker mutation coverage, watchdog observation, actual IOKit object lifetime,
queue ownership and old hardware-writer drain, coherent native fence reading,
TLB ACK admission, nonblocking map policy/real caller backpressure, negotiated
paired protocol/visibility, completion events and
fresh compatible SDK/GPU/FPS/stability acceptance remain open. Keep accepted
R1b/R2a/plugin/startup settings, daily PR28 policy and disabled resident monitors.
R3 remains active and R4–R6 do not advance; see the [ledger](BUILD34-R3-PLAN.md).

## Follow-up: post-clear invalidation

On November 22, 2026, a CPU fixture reproduced an ordering defect in the
staged `vmidFree`: its invalidation request was issued while the page tables
still contained the old entries. The [follow-up transform](../tools/build34_exact_vm_detach.py)
derives the frozen overlap-snapshot stage and changes only `vmidFree`. The
existing ownership, checked global retirement and chunk checks still precede
all writes. The bound path now clears and flushes the used page-table bytes,
then calls the same checked TLB helper before dropping reciprocal VMID
ownership. On timeout, the tables have already been cleared: keep the busy,
closing context, the VMID and all backing, set the sticky VM-fault gate, and
do not retry or release on a late ACK. A failed detach is not a rollback of
the table writes.

The [runner](../tools/test_build34_exact_vm_detach.py) substitutes only the
verified `vmidFree` body into the frozen legacy-close CPU fixture. The old
body fails at the request-before-clear assertion. The new body passes
**4,495 checks per sanitizer** (ASan/UBSan and TSan) across two cases: delayed
ACK before VMID and BO release, and missing ACK with backing still retained
after a later level bit and reaper attempt. It also checks stale-generation
refusal and bounds the clear at the used pages across two chunks. This is
not verification of the full newer native close path. The predecessor's
overlap snapshot separately passes its 240 checks per sanitizer. See the
[sanitized evidence](validation/build34-r3-vm-detach-offline-20261122.json).

Reproduce on the default build34 branch with a fresh ignored output path
and the `legacy-close.cpp` emitted by `test-build34-exact-legacy-close`
from its frozen inputs. If the matching fixture is already available, point
`EXACT_CLOSE_OUT` to its directory and skip the generation command:

```sh
EXACT_CLOSE_OUT=build/build34-r3-legacy-close-for-detach-private
nice -n 15 taskpolicy -b make -j1 test-build34-exact-legacy-close \
  EXACT_CLOSE_OUT="$EXACT_CLOSE_OUT"
nice -n 15 taskpolicy -b python3 -B tools/test_build34_exact_vm_detach.py \
  --out build/build34-r3-vm-detach-new-private \
  --legacy-fixture "$EXACT_CLOSE_OUT/legacy-close.cpp"
```

The CPU register model does not establish a fresh ACK, device visibility of
the cleared tables, actual page walk, external writer drain or native BO
release safety. All 172 production inputs are unchanged. This is a separate
source-only prerequisite, not an admitted kernel candidate. Rollback is to
leave this transform unapplied; nothing was installed or loaded.
