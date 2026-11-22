# Build34 R3 completion plan

The owner requested the continuing goal **complete R3** on November 21, 2026.
The only baseline is default `upstream34/vram-layout-fix`, PhxBringup build34.
The accepted R1b/R2a/plugin and startup/recovery settings stay in place while
this work is developed. Build41/build42 remain withdrawn. R4–R6 do not advance
until R3 has its required paired native and hardware acceptance.

This goal does not turn earlier CPU experiments into deployable kernels or
replay consumed installation/reboot scopes. Build and deployment admission must
still prove the actual source, ABI, SDK, candidate and recovery identities.
In particular, the current source-only experiments with no admitted native
reader and permanent service quarantine must not become kernel candidates.
A local commit is not synchronization;
each coherent change requires checks, staged privacy review, push and an
independent remote SHA check.

## Dependency and acceptance ledger

| Work | Evidence now | What must close it |
| --- | --- | --- |
| Preserve safe global retirement | Build34 baseline plus source-only checked two-queue snapshot/VMID retries and per-context dual-queue generation checks; the 87,821-check global and 100,411-check VM suites each pass ASan/UBSan and TSan | Bind a trusted native reader and explicit prefix validity/visibility protocol; audit watchdog, actual page walker and full client/resource consumers without promoting exact targets or accepting a new adoption seed as old-work drain |
| Mesa exact bookkeeping, multi-target fairness, conservative CS ordering/shape | Five isolated reviewed patches with actual-source CPU tests, including single-native-batch preflight and a bounded completion/ACK cache | Carry into a paired negotiated backend, freeze dependencies, prove snapshot/visibility and caller backpressure/error behavior; an aggregate exact CS protocol is not implemented |
| Native target ownership and queue generation | Staged submit, invalidation, observer and embedded binding pass CPU/TSan tests | Actual SDK/KPI integration plus authenticated native admission and queue lifecycle evidence |
| Exact wait fallback | Original wait passes CPU/TSan; the later wait-pinned version re-runs all 28 groups/six threaded cases (22,094 checks) | Carry into the native negotiated path; real KPI/lifecycle and GPU timeout/wakeup evidence remain required |
| Trusted device fence observation | Primary-source review, 189,198-check window primitive and 43,251-check staged adoption/shared-submit/ring-space/observer integration; raw-dword reader is null | Establish actual mapping/device coherency and queue ownership/drain, audit global-retirement/watchdog/VM consumers, prove wide-gap recovery and obtain native/GPU evidence; see `BUILD34-FENCE-READER.md` |
| Actual mapping observation prerequisite | **Passed.** After one ordinary restart, the exact mapping-only observer loaded in the boot collection; bounded startup, desktop takeover, and independent passive readback passed. BAR0: 256 MiB, options `0x1`, default cache field `0`. R2a/cache/AML/plugin and all 172 production inputs were retained. No recovery restart or extra pressure test ran | Keep the ordinary restart grant consumed. Actual options alone do not prove effective cache/coherency or admit a reader, and the generic public-KPI/AuxKC gap remains; see `BUILD34-MAP-OBSERVER-TRIAL.md` |
| Native protocol and receipt lifetime | Native admission remains disabled. The [full RADV CPU comparison](BUILD34-SUBMIT-RECEIPT.md#full-vulkan-exact-submit-on-cpu) found a legacy user-fence chunk rejecting `vkQueueSubmit` before dispatch and verified its omission for negotiated exact sessions. The [full-library dual-queue trial](BUILD34-SUBMIT-RECEIPT.md#full-vulkan-dual-queue-overlap-on-cpu) verifies that simulated later GFX completion satisfies wait-any but not wait-all while earlier Compute is pending, including positive timeout and ordered ACK without legacy fallback | Prove actual native admission, MIG delivery and native teardown. Bind trusted fence visibility and CPU-fence publication, and verify caller backpressure, device lifetimes and old-writer drain |
| Resource and object teardown | Source-only owned VM/BO cleanup, conditional legacy/exact close and bounded CPU-fence publication pass CPU tests; the latest public IOKit timer/workloop stage retains registration/snapshot references, serializes gate-based detachment through a separate worker and preserves uncertain handles/pins; 3,930 ASan/UBSan and TSan checks pass across 34 groups/nine threaded cases; service/GPU permanent quarantine remains | Prove native BO/object/IOKit callback/thread-call/module lifetimes, authoritative queue/external-writer drain, cache/CPU visibility, page walk/ACK and stop/unload; finish healthy service reclamation and the paired exact CPU-fence protocol; CPU timer drain alone cannot grant either; see `BUILD34-PUBLIC-SERVICE-TIMER.md` |
| Watchdog and controlled recovery | Source-only actual watchdog/submit tests reproduce unlocked observation and SQ after RLC timeout in the preceding methods; the later checked stage binds pending context allocations, holds the GPU lock through recovery, invalidates normal completion, bounds ready-only RLC attempts and separates diagnostic old-generation observation | Prove native coherent reads, RLC ACK freshness/recovery semantics, external old-writer ownership and callback/mapping/timer/stop lifetimes; diagnostic completion cannot clear a fault, retire resources or turn a new adoption into old-work drain; see `BUILD34-WATCHDOG.md` |
| Completion notification | A [providerless staged workloop](BUILD34-EXACT-EVENT-WAIT.md#staged-providerless-workloop) services bounded IH hint copies and rejects late wakes in the CPU harness. The [one-shot trace checker](BUILD34-R3-IRQ-ROUTE-TRIAL.md#one-shot-route-and-actual-isr-trace) correlates ISR, IH copy and first BAR0 read records across no-interrupt/EOP controls for both queues, but does not attest live delivery. The [PCI observation boot](BUILD34-PCI-IRQ-TRIAL.md#corrected-trial-passed-startup-observation) verified `both-message-enables-clear`, not a live route | Establish exclusive IH ownership and old-writer drain before registration or programming. Bind an admitted IRQ source, prove per-queue EOP delivery, ordered IH snapshots and independent fence visibility, and verify checked ISR unregister, queued-work drain and device drain before releasing old storage or rearming; then measure CPU and latency |
| Frozen native integration | The complete latest public-timer stage compiles to a nonloadable x86_64 object with the pinned SDK; all 376 imports resolve in the six existing declared KDK providers after kernel-resource interface/reference/alias validation, and the prior private cancellation import is removed; no R3 native candidate | Finish actual IOKit/platform/module lifecycle, entrypoint/VM audit, reader/protocol/drain integration, exact build34 provenance and paired runtime/ABI/collection inclusion without weakening admission; static compilation/provider resolution alone is insufficient; see `BUILD34-PUBLIC-SERVICE-TIMER.md` |
| Raw-debug/queue handoff and paired bootstrap | The raw stage gives eleven mutators exclusive transactions/service leases and two readers service leases, latches one-shot disjoint adoption and defers both bootstrap calls; 1,063 driver and 28 bootstrap checks and full object compiles passed. The follow-on checked bootstrap gates the paired handoff on MES completion and both queue sentinels; 14 ASan/UBSan checks, preserved wrapper exits and complete bootstrap object compiles passed | Establish initial external queue/firmware ownership and drain, actual bootstrap progress and mapping/visibility; finish platform/factory/claim/native lifetimes and healthy service cleanup. The CPU gate is not GPU drain and the unchanged production bootstrap is incompatible with this staged handoff; see `BUILD34-RAW-QUEUE-HANDOFF.md` |
| Native factory and configured discovery | Latest composed stage leases construction, refuses observed closed starts without returning clients, retains uncertain pins, atomically publishes configured discovery and removes the sysctl flag's plain precheck; 238 ASan/UBSan and TSan checks/18 groups/nine threaded scenarios, 16 rejected broken variants, the preceding 1,063-check raw-handoff suite on new source and complete native object/provider checks pass | Finish native platform/factory final handoff, PCI claim/matching, sysctl/module teardown and healthy reclamation; configured discovery is not live health/drain, final check is not atomic with stop, and reader/protocol/event/hardware requirements remain; see `BUILD34-NATIVE-FACTORY.md` |
| Uncertain firmware work | The staged PSP and SMU paths close raw writes and veto adoption after an unacknowledged published operation; raw `writeReg` refuses eight known firmware mailbox registers. The follow-on passes 51 SMU/mailbox and 61 PSP checks under each sanitizer and both full object compiles retain the same 376 imports | Establish actual acknowledgment freshness, audit raw queue-engine writers, and prove hardware drain and fence visibility. A clear software latch does not grant either; see `BUILD34-RAW-QUEUE-HANDOFF.md` |
| MES command status freshness | The offline bootstrap assigns four one-use command status slots before the existing scheduler context. Three prior-command replay cases can no longer satisfy a later command with a fresh query fence; 31 ASan/UBSan checks and full before/after object compilation pass | Establish freshness across invocations, exclusive control of the initial hardware queues, old-writer drain and effective BAR visibility. Slot isolation within one invocation is not a drain proof; see `BUILD34-RAW-QUEUE-HANDOFF.md` |
| Startup failure propagation | Offline launcher derivation preserves checked bootstrap and claim failures; the old fall-through and the new refusal paths are covered by six shell tests with CPU process stubs | Bind the paired initializer, launcher and controller in a fresh scope. No installed launcher changed; see `BUILD34-RAW-QUEUE-HANDOFF.md` |
| Startup worker identity and replay | The staged root `full.sh` atomically reserves the boot before entering `bringup5.sh`; CPU shell tests cover concurrent entry, partial failure, interruption and recovery acknowledgment loss | Bind the staged entrypoint and acknowledgment to the sealed controller, exclude direct raw setup, and prove initial MES/CP/HQD and firmware writer drain independently of boot identity; see `BUILD34-RAW-QUEUE-HANDOFF.md` |
| Initial hardware ownership | Linux v6.12 separates queue removal, HQD dequeue and MES/CP shutdown. Build34 modifies PSP/GART and ring storage before the available HQD checks. Passive PCI/ACPI review found no admitted function-local reset; the UEFI/OpenCore review and live scanout evidence establish no fence, queue or IH handoff | Prove an exclusive first writer and a trustworthy old-writer boundary before reusing storage; neither boot-services exit, scanout progress nor a successful setup sentinel proves drain. See [initial queue ownership](BUILD34-INITIAL-QUEUE-OWNERSHIP.md) |
| Indexed HQD observation | An offline internal transaction holds the service/raw leases and GPU lock from selector save through verified restore; modeled selector uncertainty closes raw writes and vetoes adoption | Prove and bind the real device power, mapping, selector and readback semantics within exclusive boot ownership. A successful sample does not prove old-writer drain. See [initial queue ownership](BUILD34-INITIAL-QUEUE-OWNERSHIP.md) |
| Native claim admission | The latest paired source stage uses a separate matching key and one issued claim per PhxBringup instance. PhxAccel checks the exact PCI sibling, epoch and both queue generations before and after family start. The old stale-marker start is reproduced; 205 checks per sanitizer and complete nonloadable driver/accelerator objects pass | Prove native matching and family unwind, marker revocation, attached accelerator and proxy-client lifetime. Software readiness does not prove GPU drain or visibility; see `BUILD34-RAW-QUEUE-HANDOFF.md` |
| Hardware acceptance | Mapping-only observer boot/desktop prerequisite passed. The [offline overlap check](#controlled-dual-queue-evidence) rejects a CPU queue-space sleep as evidence of pending GPU work. No native R3 exact work was dispatched | Fresh compatible finite scope for the paired R3 candidate; exact loaded images, dual-queue/gap and full-arena correctness, timeout/lifecycle and desktop behavior, measured FPS/CPU/latency and stated-duration stability |

The ledger records evidence levels, not a count of tests as a substitute for
hardware correctness. CPU concurrency is not IOKit lifetime, BAR coherency,
GPU execution or FPS. A timeout, an empty transport history, completed receipt
metadata or a drained CPU gate never independently authorizes BO/VMID release.

The [IH ring-full and DMA review](BUILD34-R3-IRQ-ROUTE-TRIAL.md#follow-up-ring-full-handling-and-translated-dma-drain)
found a documented host-IOMMU page-reuse boundary, conditional on successful
revocation of all matching translations. It is not a primary IH producer
stop, an old-consumer doorbell drain, or proof of either route on the build34
host. The ownership gate stays open before any live event binding.

## Execution order

1. Finish the internal owned-ticket bounded polling fallback while leaving
   legacy WAITSEQ and installed runtime unchanged.
2. Establish the reader contract from primary hardware/kernel sources and
   the real build34 mapping/packet path. If a required property is unproved,
   continue refusing native exact success rather than fabricating completion.
   The [staged window integration](BUILD34-WINDOW-CALLSITES.md) now enforces
   global-distance bounds for legacy and exact shared submissions and uses
   decoded dwords for ring-space pruning. It binds no device reader and does
   not validate old global-retirement/VM/watchdog or timeout-release paths.
   A subsequent [checked-global/VMID stage](BUILD34-GLOBAL-VMID.md) now uses
   both queue histories, validates snapshot success explicitly and tests the
   actual one-pass VMID selection with unlocked admission retries. Its reader
   is still null, and old VMID timeout cleanup, TLB ACK failure propagation,
   context allocation/reuse, watchdog and native visibility remain unresolved.
3. Implement the strict native protocol/acknowledgement and paired Mesa path.
   Receipt and provider identity must survive wait/ack/close and slot reuse.
   The current raw WaitCS, split-plan and late-attach consumers must be audited;
   completed native receipts cannot be discarded after the first positive wait
   unless subsequent valid references can still resolve completion. Keep the
   tested exact-CS shape guard until an aggregate protocol is proved.
   The 0007 transport cache now tests that late-query prerequisite with CPU
   callbacks, preserving raw sequence numbers and the genuine global prefix.
   Its callback table is not native negotiation: do not bind it to old WAITSEQ,
   enable it in production, or assume RADV safely retries its EAGAIN admission
   refusal without testing the real caller. The independent snapshot/visibility,
   strict native error classification and SDK integration still have to exist.
   Staged receipt wait/ACK now validate complete owner/slot/serial/sequence/
   queue/generation requests at the actual pre-lock dispatch entry; see
   [the experimental wire contract](BUILD34-RECEIPT-WIRE.md). This is only
   part of the native protocol. A subsequent [staged submit extension](BUILD34-SUBMIT-RECEIPT.md)
   returns that complete identity through a fixed envelope while refusing
   mixed-engine batches and unimplemented CPU user fences. It preserves
   actual queue fallback and retains published work on uncertain errors.
   The [CPU wire pairing](BUILD34-SUBMIT-RECEIPT.md#mesa-transport-pairing)
   connects the staged handlers to the Mesa cache and tests separation of
   exact and legacy sequence dispatch. Native exact-mode request, capability
   negotiation, a checked global-prefix endpoint and live visibility are
   still required.
4. Replace permanent healthy-client/service retention with proved callback/GPU
   drain and reclamation. Keep fault/uncertain-work quarantine distinct from
   successful completion; audit every VM mutation and native entrypoint.
   The [context/service-VM stage](BUILD34-VM-LIFETIME.md) now carries owner and
   allocation generation through the actual VM calls, records both queue work
   generations, serializes lookup and rejects timeout/lost-work cleanup. Its
   checked TLB failure closes a sticky VM gate before further dispatch/reuse.
   Native ACK freshness/page walking and a healthy native client/service
   reclaimer are still unproved; permanent exact/service retention stays.
   The temporary idle-before-map gate is not accepted as the final mapping or
   performance policy: prove safe concurrent additions/removals and actual
   caller backpressure/progress before native admission.
   The subsequent [BO transaction stage](BUILD34-BO-LIFETIME.md) now checks an
   authoritative idle/global proof even for unmapped BOs, unmaps before release,
   preserves metadata on failure and closes client dispatch after uncertainty.
   Shared checked WAITSEQ/BOFREE publication prevents a delayed CPU fence store
   from following a freed handle into its replacement. These are CPU/source
   results only; native visibility, multiple outstanding CPU fences, legacy
   close ordering/pins/deferred drain and healthy finalization remain open.
   A later [conditional legacy close stage](BUILD34-LEGACY-CLOSE.md) now tests
   early client/provider registration pins, terminal entry admission, CPU drain
   before client locking, checked VM release before BO cleanup and per-BO release
   permission. Busy clients progress through the actual existing timer's bounded
   four-client batch; terminal VM/host-complete errors retain references and exact
   records. Healthy CPU-model clients can finalize after their caller references
   leave. This does not accept native object/thread-call/mapping lifetime or
   remove exact-client/service quarantine; native integration and actual GPU
   drain/latency/stability remain required.
   The next [conditional exact-close stage](BUILD34-EXACT-CLOSE.md) now shares
   the bounded registration/reaper and preserves publication history after ACK.
   Only after CPU drain does it seal Registry, require reciprocal authoritative
   VM ownership and both queues' generation-bound completion plus genuine
   global-prefix coverage, and permit checked VM-first/BO-second cleanup.
   An admitted submit may still publish after close and lose its reply without
   losing its receipt; wait pins and reservations prevent early retirement.
   Healthy exact clients can finalize in this CPU stage. Lost generations,
   unmatched publication, VM/descriptor uncertainty and service stop retain
   references/resources. Native SDK/object/reader/visibility/event validation,
   service healthy teardown and actual GPU/performance/stability remain open.
   A subsequent [multi-pending CPU-fence stage](BUILD34-CPU-FENCES.md) reproduces
   the previous single-triple overwrite using actual submit/WAITSEQ methods in
   a CPU backend, then uses 128 bounded records with descriptor/KVA/size identity,
   ordered prefix publication, pre-dispatch full-ledger backpressure and shared
   BO/close cleanup. WAITSEQ can publish older completed CPU fences before its
   newer requested target times out. Exact CPU requests still refuse because
   their native visibility protocol is unimplemented. This stage does not prove
   native cache visibility, actual caller retry progress or healthy service
   teardown; its audit also leaves checked watchdog/recovery integration open.
   A later [checked watchdog stage](BUILD34-WATCHDOG.md) now records pending
   allocation identity, serializes actual observation/selection/recovery and
   retains one bounded targeted-then-global episode. Ordinary queues are
   invalidated before recovery writes, adoption refuses sticky faults, and a
   separate checked old-generation diagnostic can only stop escalation. RLC
   timeout/observed close prevents SQ and every entered safe mode gets its
   paired exit. Native ACK freshness, mapping/old-writer ownership, recovery
   semantics and service/timer teardown still require independent evidence;
   CPU recovery never promotes receipts or authorizes resource reclamation.
   The next [owned service-timer stage](BUILD34-SERVICE-TIMER.md) now gives the
   periodic producer a persistent registration reference before first enqueue,
   uses KERNEL/ONCE for periodic and separate drain calls, serializes stop
   against rearm and checks both handle frees outside client/GPU/timer locks.
   Worker-gate drain is distinct from handles-released state. Failure preserves
   exact handles and the pin, and even successful CPU timer drain preserves
   all GPU/service resources and permanent service quarantine. Actual native
   KPI/module lifetime, queue/writer drain and a final healthy reclaimer remain
   required; the CPU model does not close those requirements.
   A subsequent [complete native translation-unit check](BUILD34-NATIVE-SDK.md)
   catches and corrects the missing client forward declaration that the CPU
   class double masked. Both control and corrected stage compile to nonloadable
   objects using the pinned SDK. The matching-build KDK symbolsets independently
   expose the inherited private-only `thread_call_cancel_wait` dependency;
   native admission remains refused. Public service-timer lifecycle integration
   is therefore required before any kernel candidate, alongside the unresolved
   reader/protocol/drain requirements. No private provider is added or bypassed.
   The subsequent [public service-timer stage](BUILD34-PUBLIC-SERVICE-TIMER.md)
   now replaces direct private cancellation with a dedicated public IOKit
   timer/workloop and a separate public KERNEL/ONCE cleanup worker. The worker
   holds no GPU/client/timer lock while waiting for gated cancellation and
   checked detachment; queued arms retain and recheck their objects, and
   uncertain cleanup preserves the registration pin. ASan/UBSan and TSan each
   pass 3,930 actual-method CPU checks/nine threaded cases, all 21 broken
   variants are detected, and the full native objects compile. Independent
   symbol-only kernel-interface/alias and ordinary-provider checks resolve all
   376 proposed imports with unchanged dependencies, removing the prior sole
   private-only import. This closes the static private-import obstacle, not
   native callback/module lifetime, service/GPU drain, a completion event route
   or any R3 hardware requirement. Permanent service/GPU quarantine stays.
   The subsequent [raw-debug/queue handoff stage](BUILD34-RAW-QUEUE-HANDOFF.md)
   derives that public timer without changing its methods. Eleven public raw
   mutators hold exclusive service-wide transactions plus service leases; two
   diagnostic readers also hold service leases. One-way raw closure/drain
   precedes adoption, queue latches prevent re-seeding known old work, and
   bounded/disjoint ring/writeback/fence ranges plus distinct doorbells prevent
   adoption aliasing. The paired staged bootstrap defers existing selectors
   until raw setup ends; the original compute-first adoption/GFX-raw sequence
   is incompatible and must not be paired with the new stage. This does not
   establish initial external-writer drain, complete platform/factory/claim
   lifecycle, native mapping/coherency, healthy service cleanup, protocol/events
   or GPU/performance/stability acceptance. See its sanitized evidence for the
   actual CPU, negative-variant and complete-object check results.
   The follow-on checked bootstrap stages both adoption records only after
   verified MES completion markers and compute/GFX scratch plus memory
   sentinels. It checks freshness before write-pointer publication and fixes
   a misaligned packed-field store reproduced by UBSan. The actual staged
   flow passes CPU checks, including ignored or late completions and missing
   queue progress, with no production or installed change. The two adoption
   calls are separate; device coherency and external writer drain remain open.
   The next [native factory/configured discovery stage](BUILD34-NATIVE-FACTORY.md)
   gives construction a service lease, refuses an observed closed start without
   returning its client and preserves uncertain registration/provider pins.
   Actual old getter/adoption methods reproduce a CPU TSan race; the proposed
   getter uses atomic configured-queue publication without clearing it on
   invalidation or allowing lost real work into E1 mock fallback. The factory's
   global sysctl-once precheck is also made atomic. All other native methods,
   the owned header, paired bootstrap and production inputs remain unchanged.
   CPU references, finalization and timer readiness are models. Final handler
   publication versus stop, full platform/PCI matching and native module/healthy
   reclamation remain unaccepted, alongside reader/protocol/event/GPU evidence.
   The subsequent PSP uncertainty stage prevents a completed CPU callback
   from allowing adoption after an unacknowledged published firmware request.
   The guard is sticky for that service instance and closes raw writer
   admission; it neither recovers a failed PSP transaction nor validates
   remaining firmware and GPU writer paths. No device reader is bound.
   The follow-on SMU stage shares that veto for a published message with no
   response and reserves the eight known PSP/SMU mailbox registers from raw
   writes. The offline launcher companion preserves checked-bootstrap failure
   before claim and claim failure before desktop configuration. The source-only
   native claim companion also refuses a partial or invalidated queue pair and
   a failed property write. The next staged revision checks validity around
   property publication, retracts a failed in-flight claim under its exclusive
   publisher lease, and tests actual staged sleep/wake invalidation.
   Asynchronous consumer admission, marker/attached accelerator lifetime,
   queue-engine drain and pairing with an authorized boot scope remain open.
   A separate [post-clear VM detach stage](BUILD34-VM-LIFETIME.md#follow-up-post-clear-invalidation)
   reproduces the old invalidation-before-clear order and tests that the
   cleared tables precede the modeled TLB request. An uncertain ACK retains
   the busy context, hardware owner and BO backing behind the sticky VM gate.
   This closes one CPU ordering prerequisite only; fresh native ACK, page
   walk, writer drain and hardware-safe release remain unproved.
   The [table-chunk allocation stage](BUILD34-VM-LIFETIME.md#follow-up-table-chunk-allocation)
   next tests the actual software walker with CPU allocator doubles and
   refuses invalid new chunk backing before clearing or publishing it.
   It does not establish live mapper identity or GPU page-walk visibility.
   The [checked unmap stage](BUILD34-VM-LIFETIME.md#follow-up-checked-unmap-walk)
   separates a missing branch from a failed software table lookup and
   retains BO backing on a late walk failure, even after a partial clear.
   The [native submit mapping admission stage](BUILD34-VM-LIFETIME.md#follow-up-native-submit-mapping-admission)
   next refuses an unmaterialized logical mapping before native dispatch.
   The actual caller tests use CPU doubles; no native release is admitted.
5. Add a safe completion notification path and measured bounded fallback,
   preserving lock order, cancellation and shutdown safety.
   The [offline EOP route checker](BUILD34-R3-IRQ-ROUTE-TRIAL.md#offline-route-and-first-read-evidence)
   records the expected legacy GFX and Compute identities, checks paired
   controls and requires fresh, same-generation fence and payload on the first
   independent post-event read. Its [raw packet check](BUILD34-R3-IRQ-ROUTE-TRIAL.md#bind-the-captured-fence-packet-to-each-observation)
   ties the captured `RELEASE_MEM` to the BAR0 slot, target and interrupt
   mode. Exclusive IH ownership and old-writer drain still gate live
   collection and event binding.
   The [direct-child follow-up](BUILD34-R3-IRQ-ROUTE-TRIAL.md#follow-up-direct-child-attribution)
   identifies `AMDSupport` and `PhxDeviceControl`. The attached AMD support
   service and its bundle's PCI IRQ code must be accounted for before claiming
   the route; they do not prove an active IH consumer or a handoff.
   The [provider review](BUILD34-R3-IRQ-ROUTE-TRIAL.md#checked-pci-teardown-still-needs-a-separate-deadline)
   shows that PCI enable can call the target inline and that unregister is
   not inherently bounded. The [offline signal handoff](BUILD34-EXACT-EVENT-WAIT.md#inline-signal-and-deferred-handoff)
   handles the inline hint and bounded copy continuation. It does not bind
   a real scheduler or solve provider or device teardown.
   The [scheduler ABI review](BUILD34-EXACT-EVENT-WAIT.md#deferred-scheduler-abi-and-detach-review)
   rules out using the private thread-call activity query or the non-atomic
   manual interrupt-source counter. The [staged workloop source](BUILD34-EXACT-EVENT-WAIT.md#staged-providerless-workloop)
   closes wake admission before an independent checked detach, keeps the
   context pinned on uncertainty and handles late kicks. This is not bound
   to a provider. Prove native scheduling and teardown, IH ownership, old
   device-writer drain, and order of event delivery versus the BAR0 read.
   The [one-shot evidence checker](BUILD34-R3-IRQ-ROUTE-TRIAL.md#one-shot-route-and-actual-isr-trace)
   matches the current non-rearming route: it rejects copied vectors without
   same-source ISR records and checks slot/peer and IH cursor continuity across
   the four windows. Real dispatch, first reads and terminal counts must still
   come from an independently admitted hardware capture.
6. Freeze and compile the complete native integration. Prepare a concrete
   source/ABI-matched candidate with fresh rollback/recovery controls before
   requesting any still-required installation/GPU/power authorization.
7. Test the paired candidate sequentially on the real GPU. Preserve failed
   evidence; do not roll back automatically after success or claim completion
   from a single short test. Record the actual OS build and the explicit
   correctness, desktop, performance and stability acceptance results.

R3 is complete only when the ledger's native and hardware requirements are
closed with evidence. Until then the continuing goal remains active. The
detailed history, CPU runners and frozen-input evidence are in
[BUILD34-EXACT-COMPLETION.md](BUILD34-EXACT-COMPLETION.md).

## Controlled dual-queue evidence

The accepted [R1b pressure test](BUILD34-RING-BACKPRESSURE.md#bounded-hardware-acceptance-on-november-20)
placed GFX submission and completion inside a Compute submitter's CPU
queue-space sleep. That thread can still be asleep after older GPU work has
finished. Its record does not bracket an exact GFX wait with independent
Compute and GFX fence observations and a checked global prefix.

The offline [overlap check](../tools/build34_r3_wait_overlap.py) expects
distinct native receipts (earlier Compute, later GFX), an exact GFX wait
response for the full receipt, and four independently acquired snapshots:
before the wait, during the wait, after it returns, and after both targets
drain. Each snapshot must carry the same service epoch, the original queue
generations, both submitted/completed bounds and the checked global prefix.
Each snapshot carries `begin_ns` and `end_ns` on the same monotonic clock as
the wait boundaries. The full sampling interval must fit inside its phase:
for example, the post-wait sample must start after the wait returns. Using
only the sample's end time could misclassify a Compute read made before the
wait returned. GFX must be pending before the wait; an independent GFX fence
read must cover the receipt before the wait returns. After the wait, Compute
must still be pending and the prefix must be strictly below Compute. The
prefix may make safe progress below that limit. A later sample must cover
both targets and advance the prefix through them. A trial that misses this
ordering has not measured the required overlap.

The checker only validates the normalized records; it does not read fences,
register interrupts or attest a trial. The collector must separately prove
coherent, non-regressing same-generation samples, and obtain the prefix from
the actual retirement path. It must not derive the fence sample from the wait
reply, infer pending GPU work from thread state, or reuse invalid samples
after fault, reset, sleep, stop or readoption. Successful records do not
establish EOP wakeup, payload/guard integrity, actual resource lifetime, FPS
or stability. `make test` includes CPU fixtures for the positive ordering and
refuses premature prefix advancement, stale identity, timing ambiguity and
missing drain.

The [source-only capture stage](../tools/build34_exact_overlap_snapshot.py)
extends the frozen public IOKit wait stage with a private observation. Under
one service callback lease and `gpuLock`, the existing global prefix scan
records each decoded fence alongside its queue generation and submitted
bound, without a second read of either fence or a second prefix calculation.
This is a serialized CPU observation of two sequential device reads. The
boot-local IORegistry entry ID identifies the retained service; it must stay
tied to the same admitted boot and wait provider. A missing or invalid queue,
failed read, bad clock interval or observed service closure discards the
output. The decoder may still cache a successful earlier read. Existing
prefix callers retain their prior handling of a never-adopted queue.

The CPU runner fed the staged methods' four samples to the checker; the wait
receipt and times were synthetic. With Compute 100 pending and GFX 101
complete, the checked prefix remains 99, then reaches 101 after Compute
completes. ASan/UBSan and TSan each passed 240 checks, including refusal of a
failed second read, stale generation and closure after the final fence read.
To reproduce with a fresh output path:

```sh
python3 -B tools/test_build34_exact_overlap_snapshot.py --out build/r3-overlap-snapshot-CPU-private
```

All 172 production inputs were unchanged. No runtime selector or collector
endpoint is exposed, and the native reader and event backend remain unbound.
Coherent device observation, exclusive queue ownership and old-writer drain
are still required before this evidence can be collected on the GPU.

## NullMoth comparison and performance gate

[NullMoth's NVK event path](BUILD34-EXACT-EVENT-WAIT.md#nullmoth-reference)
already has a live RM source, bounded sleep, exact channel/semaphore rechecks
and polling fallback. Build34 has source-only equivalents for the exact wait
and fallback, but no bound AMD source, independently validated BAR0 fence
reader or loaded Mesa/native receipt session. Its accepted desktop path still
uses legacy waits. The mapping and PCI observer boots do not change that.

On its RTX 5060 Laptop test, NullMoth reports short-compute process CPU time
falling from 0.612 to 0.286 ms with app event waits, while elapsed time rises
from 0.607 to 0.734 ms. Neither is a Radeon result or a desktop FPS result.
For the 780M, first qualify the exact loaded pair and lifecycle/correctness.
Then compare the same qualified exact path in bounded-poll and event-wait
modes, alternating the order of repeated runs on the same machine, OS build,
display mode, scene and load. Keep the completion contract, driver/runtime
images, workload and benchmark interval fixed. A separate legacy-to-exact
comparison measures the combined protocol change, not just notification.

Seal the finite performance and stability durations and acceptance limits
before execution. Record correctness, delivered frame rate and frame-time
tails, process and WindowServer CPU, submit-to-exact-wait latency, event and
fallback counts, timeouts and faults. Report each arm and its duration,
including interrupted runs. Complete the stated-duration desktop run and
the separately scoped teardown cases before accepting R3. No controlled
matching 780M A/B evidence is available yet.
