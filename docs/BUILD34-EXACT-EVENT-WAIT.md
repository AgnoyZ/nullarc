# Build34 R3 staged completion event wait

## NullMoth reference

The review pins `nullmoth/nvidia-macos-driver` at
`87e524ab36f12d17c04626d6cf7fc3bde1cc63e4`. The
[NVK patch](https://github.com/nullmoth/nvidia-macos-driver/blob/87e524ab36f12d17c04626d6cf7fc3bde1cc63e4/nvk/nvk-macos.patch)
registers one RM graphics non-stall event per device on a dedicated connection,
and frees the RM registration before closing that connection. The graphics
event is broader than an exact submission: NVK checks the pending channels'
slots, generations and semaphore values independently. It reads the event
count before rechecking those targets. The kernel
[event handler](https://github.com/nullmoth/nvidia-macos-driver/blob/87e524ab36f12d17c04626d6cf7fc3bde1cc63e4/kexts/NVRM/NVRM.cpp)
increases the connection counter on delivery, then wakes sleepers. Selector 6
uses a compare, enrollment and post-enrollment recheck, with a global sleeper
cap and a timeout. NVK requests 2 ms on that path and falls back to polling
without a supported graphics event. Its wait-block policy defaults to event
waits in WindowServer and polling in ordinary apps. The
[RTX 5060 results](https://github.com/nullmoth/nvidia-macos-driver/blob/87e524ab36f12d17c04626d6cf7fc3bde1cc63e4/docs/EVENT-WAIT.md)
showed lower CPU time from app opt-in and higher elapsed latency in the short
compute workload. They do not predict 780M FPS or latency.

The NVRM source declares PolyForm Noncommercial 1.0.0, also the reference
repository's default. The NVK patch edits Mesa and the repository separately
provides Mesa notices. This stage implements the ordering independently and
copies no source, binaries, selector, interrupt routing or hardware policy.

## Build34 experiment

Only the offline transform changes: the pinned exact receipt's wait can
snapshot a queue-specific notification counter before observing its fence.
The provider compares the same counter under `gpuLock` before atomically
enrolling with a backend that drops the lock while sleeping. If notification
arrived between observation and enrollment, it rechecks the fence without
sleeping. The client lock is released before sleep. The existing authenticated
ticket and wait pin remain held across retries. Only fence observation can
prove the requested sequence completed. Other-queue and old-generation
notifications cannot wake that wait as completion evidence, and the counter
cannot wrap into a previously observed value. No global retirement or resource
reclamation method is changed.

The sleep interval is at most 1 ms and clipped to the remainder of the
original monotonic request budget. Its absolute deadline must be anchored to
the timestamp passed to the backend. Timeout and wake both lead to another
observation. An early return with no notification change takes one polling
turn after that observation. If no backend is available, the existing 1 ms
polling path applies. Both paths can overshoot with scheduler delay; neither
promises a hard return deadline. Stop and queue invalidation wake affected
waiters; client close is noticed at recheck, within the requested slice plus
scheduling and lock delay if already asleep. A wake never grants device
visibility, successful completion, or queue drain.

## Verification and remaining work

The [offline runner](../tools/test_build34_exact_event_wait.py) exercises the actual staged receipt wait, event and
invalidation methods with CPU lock/clock/registration doubles. The tests
cover notification on both sides of enrollment, missing or spurious wakes,
old and wrong-queue notifications, two concurrent GFX waiters, stop and
generation invalidation, and GFX completion while earlier compute is pending.
It also checks the complete staged driver before and after with the pinned
SDK/KDK as nonloadable objects. ASan/UBSan and TSan each passed 481 checks;
five intentionally broken variants failed as expected. The 377 declared
imports and 172 production inputs are unchanged. See the
[sanitized results](validation/build34-r3-event-wait-offline-20261121.json).
Run sequentially at background priority:

```sh
nice -n 15 taskpolicy -b python3 -B tools/test_build34_exact_event_wait.py \
  --out build/build34-r3-event-wait-new-private --sdk "$KERNEL_SDK" --kdk "$KDK"
```

The event backend stays null. Before binding, establish the actual AMD event
source and deferred callback context, an admission limit for kernel sleepers,
the native atomic wait primitive and deadline conversion, and safe shutdown of
the source and all enrolled waiters. Prove BAR fence visibility and external
writer drain independently, then measure real wait/latency and FPS along with
dual-queue correctness and sustained desktop stability. No installation, GPU
submission or restart was performed. Rollback is to omit the offline transform.

## Follow-up: public IOKit sleep and AMD EOP routing

Linux v6.12 (`adc218676eef25575469234709c2d87185ca223a`),
[`gfx_v11_0_ring_emit_fence` and `gfx_v11_0_eop_irq`](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/gfx_v11_0.c#L5685),
separate the `RELEASE_MEM` writeback and interrupt controls. The handler
identifies a tagged MES queue through `src_data[0]` and the MES queue-ID
table; otherwise it decodes the IV ring ID and dispatches by CP engine and
pipe (also checking the compute queue). Linux's
[`amdgpu_ih_process`](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/amdgpu_ih.c#L208)
orders the write pointer against the 32-byte interrupt vectors and advances
the consumer pointer. The
[`ih_v6_0` implementation](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/ih_v6_0.c#L434)
handles overwrite, so a vector stream is not assumed complete. No Linux code,
register programming, or driver binaries are included in this MIT stage.

Build34 maps two `map_legacy_kq` queues; the adoption record provides ring,
writeback, doorbell and fence information, but no IH source or vector
ownership. Its fence packet requests no interrupt and has no MES queue tag.
The host has not established which CP EOP vectors are delivered for these
queues, that an IH consumer owns the ring across transitions, or that the
event orders the device's fence write to a CPU read through BAR0. A doorbell,
software generation, boot marker, or guessed IV cannot establish those facts.

The [separate offline transform](../tools/build34_exact_event_iokit.py) adds
unbound `IOLockSleepDeadline` and wake-all helpers. The sleep uses the original
monotonic sample plus the remaining slice, rejects expired, zero-tick or
overflowing deadlines, and uses `THREAD_ABORTSAFE`. The staged park counts
admitted sleepers under the GPU lock, including threads reacquiring it,
and caps them at 32 per service across both queues. A refusal re-observes
the target before polling. The return from the sleep primitive is never
completion evidence. Public XNU's
[`IOLocks.cpp`](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/iokit/Kernel/IOLocks.cpp#L90)
documents the underlying mutex sleep and wake path. At macOS 26.7.2
(`25G332`), static SDK/KDK checks accept exactly three additional imports
from the existing IOKit and Mach interfaces. No implementation from XNU
was copied.

ASan/UBSan and TSan each passed the original 481 checks and 113 additional
ones; four deliberately defective variants failed. The complete driver
compiled only to nonloadable objects (377 to 380 imports); all 172 production
inputs are unchanged. See the
[sanitized results](validation/build34-r3-event-iokit-offline-20261121.json).

```sh
nice -n 15 taskpolicy -b python3 -B tools/test_build34_exact_event_iokit.py \
  --out build/build34-r3-event-iokit-new-private --sdk "$KERNEL_SDK" --kdk "$KDK"
```

The source and ops pointer remain unbound. Matching exports establish static
availability, not live kernel enrollment or unload safety. The consumer's
ownership, deferred IRQ delivery and teardown, fence visibility, native
protocol, and GPU performance/stability acceptance remain open. No IRQ,
device packet, installed artifact, or runtime setting was changed.

## Passive PCI descriptor observation

On November 21, 2026, macOS 26.7.2 (`25G332`), the
[passive collector](../tools/build34_pci_irq_observation.py) matched the
PhxBringup build34 registry service to the direct PCI provider `1002:1900`.
Both provider snapshots contained two cached controller/specifier pairs,
one naming the PCI messaged interrupt controller and one other. Matching
entry identities and descriptor values were checked in memory around the
service read; only counts and fixed classifications were retained. Build34
here is the registry property, not loaded-image hash verification. The
[sanitized record](validation/build34-r3-pci-irq-observation-20261121.json)
retains the limits of this evidence.

Use bounded `ioreg -a` property snapshots. Apple's public
[`IOPCIDevice::getProperty`](https://github.com/apple-oss-distributions/IOPCIFamily/blob/4822b27a36e2de70e231ecf2bf3021384fab6ec2/IOPCIDevice.cpp#L1834)
calls the lazy interrupt resolver on named interrupt-property access. The
collector does not request a named property or `getInterruptType`.
Public XNU's
[`IORegistryEntry::serializeProperties`](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/iokit/Kernel/IORegistryEntry.cpp#L543)
serializes a copy of the property table. The source references describe the
API paths; they are not a claim that either source revision is the running
kernel or driver image. No device user client was opened. No configuration,
interrupt registration, packet, MMIO read/write, GPU or power operation was
requested by the collector.

```sh
python3 -B tests/test_build34_pci_irq_observation.py
python3 -B tools/build34_pci_irq_observation.py
```

The pairs show that descriptors are already published. They do not identify
which mode is active, who registered an ISR, the actual EOP vector for either
build34 queue, or whether a BAR0 read can see its fence after interrupt
delivery. Do not infer `MSI` versus `MSI-X` from the controller name. A later
finite route trial must correlate one protected GFX or Compute submission
with its actual EOP source and independently verified fence data, account
for overflow or dropped events, and prove exclusive IH ownership before
touching the ring or enabling interrupt generation. Keep the event backend
unbound until that evidence and its lifecycle checks are available.

The follow-up collector also checks `IOPCIMSIMode` and counts interrupt
accounting legend entries on the same PCI provider. Both fields are hints.
Public IOPCIFamily uses [one marker for both MSI and MSI-X](https://github.com/apple-oss-distributions/IOPCIFamily/blob/4822b27a36e2de70e231ecf2bf3021384fab6ec2/IOPCIMessagedInterruptController.cpp#L612-L638);
public XNU's [statistics removal](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/iokit/Kernel/IOService.cpp#L8524-L8564)
clears the live statistics pointer and keeps the reporter. An absent marker or
legend does not demonstrate that the device is idle or unclaimed. Two further
build34 reads on macOS 26.7.2 (`25G332`) matched: two descriptors, no MSI marker,
and zero matching legend entries. See the
[sanitized follow-up](validation/build34-r3-pci-irq-route-hints-20261121.json)
and the [proposed route trial](BUILD34-R3-IRQ-ROUTE-TRIAL.md).

## Deferred IH hint admission

The [staged ingress](../tools/build34_exact_ih_ingress.py) derives the complete
exact-open source and replaces its generic queue-number notification helper
with a deferred entry taking a route identity and a bounded batch of copied
32-byte vectors. The caller must retain the service, carry the identity
captured for that route, and own the validated delivery path. Reconstructing
the identity or batch ordinal from current state at delivery does not qualify.

Under `gpuLock`, publication and delivery check the current service, route
epoch and both queue generations. The decoder uses the existing provisional
legacy GFX11 signature; it filters out tagged MES and unrecognized vectors.
It maps ring `0x04` to build34 queue 0 (Compute) and ring `0x00` to queue 1
(GFX), not to the numerically different DRM IP types. A rejection is not an
acknowledgment or permission to drop traffic. The owning consumer must handle
all other vectors independently.

The route starts with an admitted ring size and read cursor. The entry checks
that the software capture ordinal is consecutive, including after cursor
wrap, and that the read cursor equals the previous accepted batch's end.
Producer writeback samples must match and describe an aligned in-range
cursor without status bits. The batch must contain the next contiguous
prefix of available entries, capped at 32 per call. A longer backlog can
span multiple batches without advancing past uncopied entries. Duplicate
EOPs coalesce to at most one hint per queue per batch. An invalid batch on
the current live route marks it lost before delivering any of that batch's
hints. A stale route is rejected before inspecting batch continuity and
cannot poison the current route.

These checks apply to immutable CPU-owned captures, not to DMA memory. The
owner must establish the starting cursor, actual complete ordered capture,
capture-time ordinals, buffer lifetime and overflow observation. Matching
writeback samples alone do not rule out an unobserved overwrite. The result
is a wake mask or a rejection, never an IH read-pointer acknowledgment or
permission to consume entries or reuse the ring.

The deferred entry admits one capture worker at a time under the route and
service gates. It keeps both leases across the bounded copy, which runs outside
`gpuLock` and must not hold a client lock, acknowledge IH or mutate the device.
It rechecks the route after the copy before accepting the bytes. Concurrent
entry returns busy without invoking the copier. A failed copy on a still-live
route declares stream loss; a late result after revocation is discarded.
Revocation closes the worker gate before signaling sleepers. While holding
`gpuLock`, a cleanup owner can check that the gate is closed and that the last
admitted worker has left for this exact retained route. It must not spin or
wait under the lock. A drained worker gate is not an ISR unregister receipt,
a queued-work cancellation fence, or an AMD device-write drain.

A recognized vector changes only the matching wake stamp. It cannot write a
fence, advance the prefix, or release resources. Queue invalidation revokes
delivery and wakes sleepers; instead of clearing the route, it preserves the
service, epoch and generations in `Retiring`. Fresh queue adoption does not
make that slot empty. A matching stream-loss report while the service gate is
open moves the arming, active or retiring route to `Lost`. Neither `Retiring`
nor `Lost` can deliver hints or rearm on this service instance. Unrelated or
relabeled reports cannot alter the retained route. The event path falls back to the existing
bounded polling for still-valid targets, while invalidated waits fail closed.

There is deliberately no transition from `Retiring` to `Empty`: software
invalidation, sleeper wakeup and PCI ISR removal are not an AMD IH device
write-drain acknowledgment. A future owning backend must prove both CPU
callback drain and device drain for this exact retained identity before it
can release the route or its storage. This source stage retains metadata
only and does not allocate or pin any IH hardware storage.

The CPU runner verifies the closed configuration and an explicitly modeled
positive route. It exercises wrong source and queue, tagged MES, stale
service and route, incorrect peer generation, wrong-queue wake, loss while
enrolled, sleep/stop wakeup, and refused rearm after modeled queue readoption.
It also tests partial processing of a 33-entry backlog, ring wrap, wrapped
replay, unstable or flagged writeback, cursor gaps, wrong counts and wake
coalescing. The [worker-drain record](validation/build34-r3-ih-worker-drain-offline-20261123.json)
adds a paused copy crossing revocation, copy failure, rejection of a second
worker and refusal to claim drain before the first worker exits. ASan/UBSan
and TSan each passed 33 closed and 756 modeled checks, and 23 broken variants
were rejected. Both complete native sources compile to nonloadable objects
with the same 381 imports; the 172 protected production inputs are unchanged.
Earlier CPU results are in the
[batch-ingress record](validation/build34-r3-ih-batch-ingress-offline-20261123.json),
[retirement-hold record](validation/build34-r3-ih-retirement-offline-20261123.json)
and the
[original ingress record](validation/build34-r3-ih-ingress-offline-20261123.json).

```sh
nice -n 15 taskpolicy -b python3 -B tools/test_build34_exact_ih_ingress.py \
  --out build/build34-r3-ih-worker-new-private --sdk "$KERNEL_SDK" --kdk "$KDK"
```

Native admission is hard false and no delivery operations are installed.
The entry does not poll or consume an IH ring, acknowledge a doorbell,
register an ISR, or prove the decoder against this APU. The owner, ordered
capture, loss detection and device-write drain must come from the separately
admitted hardware route. Omit the transform for offline rollback; no live
changes were made.

### Inline signal and deferred handoff

An admitted route first enters `Arming`. A release store publishes its
immutable identity before a future provider operation that can dispatch
inline. `signalExactIH` checks the captured identity after an acquire load,
takes no GPU or client lock, and latches one pending hint. It does not read
IH, wake a fence waiter or claim completion. Activation under `gpuLock` checks
the same identity and both queue generations. Its atomic enable transition
and the signal transition agree on which caller requests the first deferred
kick. This lockless identity read depends on never reusing the route slot.

Only the deferred collector can consume a hint, after acquiring the sole
worker lease. A worker that finds no hint returns idle without calling the
copier. An entry that finds the worker busy cannot clear the hint. Signals
while the worker copies are coalesced; the worker requests another deferred
kick if a signal arrived or the accepted batch left captured backlog. It
releases the copy lease before handing off and does not repost after observing
loss or revocation. Each invocation is still limited to 32 entries.

A kick is a request to an unimplemented asynchronous scheduler, not evidence
that the caller is still live or that work has been queued. Revocation can
win after any kick decision. A future adapter must retain the service and
immutable callback context before any provider operation that can dispatch,
and through late kicks and queued work. The collector rejects stale callbacks
at entry. Keep provider drain, queued-work drain, the admitted copy lease,
and device DMA drain as separate release prerequisites. A scheduler failure
must be handled fail closed; this step does not implement a scheduler.

The [signal-handoff record](validation/build34-r3-ih-signal-handoff-offline-20261123.json)
covers inline signals, activation racing signaling or invalidation, peer
generation rejection, busy-worker handoff without a fresh interrupt, and a
second capture for a partial batch. ASan/UBSan and TSan each passed 36 closed
and 972 modeled checks; 34 fault variants were rejected. The pinned SDK/KDK
comparison still has 381 imports, and all 172 production inputs are
unchanged. The staged admission remains false; no ISR, native scheduler,
paired RADV transport or live 780M completion route is established.

### Deferred scheduler ABI and detach review

The macOS `26.7.2 (25G332)` x86_64 KDK image and all six currently declared
providers match the pinned timer-review hashes. A symbol-table check resolved
the offered KPI references and aliases to definitions in that image. Four
ordinary thread-call operations are offered by `com.apple.kpi.mach`, but
neither `thread_call_isactive` nor `thread_call_cancel_wait` is offered. A
header declaration or a definition in the KDK kernel is not enough to import
either. The pinned [thread-call implementation](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/osfmk/kern/thread_call.c#L1086-L1137)
and the KDK `thread_call_free` body allow an ordinary running invocation to
keep the call's internal reference after a successful free. Cancel can also
remove a pending ONCE reschedule while the first invocation still runs. Do
not use either return value to release callback context.

Do not use a providerless `IOInterruptEventSource::interruptOccurred` as a
generic multi-producer kick. The [normal path](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/iokit/Kernel/IOInterruptEventSource.cpp#L448-L469)
increments its producer counter without atomic read-modify-write, matching
the KDK x86_64 instruction. The deferred [consumer](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/iokit/Kernel/IOInterruptEventSource.cpp#L317-L341)
uses the producer/consumer delta. The R3 kick can come from activation,
deferred continuation or interrupt context. Their decisions can be serialized
without serializing the ensuing calls to a second, non-atomic counter.

Use the existing route latch as the work predicate for the next offline
adapter: one providerless `IOEventSource` on a dedicated `IOWorkLoop`.
The checked IOKit KPI offers source wake, add and remove. The
[workloop wake](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/iokit/Kernel/IOWorkLoop.cpp#L489-L498)
uses a short interrupt-safe lock to set a work bit and wake the thread. It
does not call the consumer inline. `IOEventSource::signalWorkAvailable`
dereferences its attached loop, so retaining the source object alone is not
enough to make wake concurrent with detach. Keep the source attached and
all callback context pinned until kick admission is closed and all already
admitted callers, including provider entry and late continuations, have
left. The new adapter must demonstrate this boundary before trying removal.

The [worker loop](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/iokit/Kernel/IOWorkLoop.cpp#L375-L425)
holds its gate while checking active sources and can rescan under that gate
when a source returns `true`. Do not use an unconditional `true` return to
drain a continuing backlog. Invoke one bounded capture per check, schedule
further work outside that rescan mechanism, and recheck revocation before
copy and repost. The [remove command](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/iokit/Kernel/IOWorkLoop.cpp#L312-L316)
uses the same [recursive gate](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/iokit/Kernel/IOCommandGate.cpp#L196-L215)
and [unlinks and clears the source's workloop pointer](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/iokit/Kernel/IOWorkLoop.cpp#L623-L672).
Checked detach of the exact attached source by an independent cleanup worker
is a candidate queued-work boundary, not a deadline or an ISR drain receipt.
No self-detach from the active source or removal under the GPU/client locks.
A timeout observing removal must retain all callback context; it does not
cancel the removal or authorize freeing anything.

See the [sanitized scheduler review](validation/build34-r3-ih-scheduler-review-20261123.json).
This selects an adapter to model and compile next; it does not bind a live
scheduler, establish a native teardown deadline or change the IH ownership,
device-write drain, BAR0 visibility or native protocol gates.

### Staged providerless workloop

The [source-only adapter](../tools/build34_exact_ih_workloop.py) creates a
dedicated `IOWorkLoop` with one `IOEventSource` only after IH admission.
`prepare` retains the service and copy owner, opens the one-shot route, and
publishes an attached source only after successful add and pointer readback.
No production caller can reach it. A future provider must pin the returned
source before any register/enable operation that can call the target inline.
That provider pin is independent of the adapter's attachment pin.

The interrupt entry just latches a route hint and requests work. A single
atomic word holds a one-way close bit and the count of concurrent wake calls
(not the number of interrupts). Admission uses a fixed fetch-add/sub pair,
not a CAS retry, sleeping lock, or second interrupt counter. Every caller
already owns a lifetime reference; an admitted wake keeps the attachment
stable until `signalWorkAvailable` returns. A late wake that loses to closure
does not touch the workloop, even after detach. `checkForWork` tries one
bounded copy and posts a fresh work bit for a pending or partial batch; it
returns false so the workloop releases its gate between passes. A copied
vector only requests a validated fence recheck.

`closeKicks` never attempts removal. The external cleanup caller must hold
an independent source reference, hold no GPU or client locks, and wait or
reschedule at its own deadline. `detach` rejects self-removal and returns
busy while any wake is in flight. A single caller claims removal, revokes
the route, and requests checked removal of the exact source. Only success
with a null attachment readback releases the attachment pin. Failure or
contradiction retains the pin and refuses retry. There is no synchronous
stop/sleep callsite; the existing queue invalidation path makes queued work
inert. A cleanup timeout does not cancel removal, release the provider pin,
or establish DMA drain. A future adapter must also prove native gate
behavior, copy lifetime and bounded underlying scheduling.

Run the isolated checks with a fresh ignored output:

```sh
nice -n 15 taskpolicy -b python3 -B tools/test_build34_exact_ih_workloop.py \
  --out build/build34-r3-ih-workloop-new-private --sdk "$KERNEL_SDK" --kdk "$KDK"
```

The adapter remains staged. No IRQ provider, IH reader, MMIO, native event
backend, or Mesa transport binding is installed by this transform. Omit it
to roll back the experiment.

The [offline result](validation/build34-r3-ih-workloop-offline-20261123.json)
records 8 closed and 377 modeled checks under each of ASan/UBSan and TSan.
All nine injected defects failed. The fixture covers an inline hint during
arming, a 33-entry split, stale queued work after sleep or stop, wake versus
detach on both sides of admission, a held copy, self-removal, concurrent
removal and both error and misleading-success readbacks. The complete staged
x86_64 source compiles to a nonloadable object. Its 25 additional imports are
exactly the allowlisted IOKit/libkern symbols; all 406 resolve through the
existing declared KDK providers. The 172 production inputs remain unchanged.
