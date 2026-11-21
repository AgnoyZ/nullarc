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
| Actual mapping observation prerequisite | Exact R1b and the full control bundle reproduce byte-for-byte; the minimal observer builds/signs with the same 375 imports, existing R1b boot route and R2a are independently confirmed, and 14 inactive artifact/recovery-reference files pass independent readback; prior CPU/native-object evidence stays frozen and live map metadata remains absent | Finish a fresh observer-compatible startup/recovery controller, source/ABI/boot-path-specific scope and required authorization, then obtain actual map options; generic public-KPI/AuxKC admission remains false and options alone still cannot prove effective cache/coherence or admit a reader; see `BUILD34-MAP-CANDIDATE.md` |
| Native protocol and receipt lifetime | Internal wait-pinned ACK, actual-Mesa bounded completion cache, and staged complete-token structure submit/wait/ACK dispatch pass CPU sanitizers; experimental selectors 64/65/66 have no production mode/capability or Mesa wire binding | Complete native capability/session and production exact-submit admission, independent genuine global-prefix/visibility and CPU-fence protocol, paired binding and caller backpressure/error integration; caller-quiescent transport destroy is still required |
| Resource and object teardown | Source-only owned VM/BO cleanup, conditional legacy/exact close and bounded CPU-fence publication pass CPU tests; the latest public IOKit timer/workloop stage retains registration/snapshot references, serializes gate-based detachment through a separate worker and preserves uncertain handles/pins; 3,930 ASan/UBSan and TSan checks pass across 34 groups/nine threaded cases; service/GPU permanent quarantine remains | Prove native BO/object/IOKit callback/thread-call/module lifetimes, authoritative queue/external-writer drain, cache/CPU visibility, page walk/ACK and stop/unload; finish healthy service reclamation and the paired exact CPU-fence protocol; CPU timer drain alone cannot grant either; see `BUILD34-PUBLIC-SERVICE-TIMER.md` |
| Watchdog and controlled recovery | Source-only actual watchdog/submit tests reproduce unlocked observation and SQ after RLC timeout in the preceding methods; the later checked stage binds pending context allocations, holds the GPU lock through recovery, invalidates normal completion, bounds ready-only RLC attempts and separates diagnostic old-generation observation | Prove native coherent reads, RLC ACK freshness/recovery semantics, external old-writer ownership and callback/mapping/timer/stop lifetimes; diagnostic completion cannot clear a fault, retire resources or turn a new adoption into old-work drain; see `BUILD34-WATCHDOG.md` |
| Completion notification | No AMD completion event/interrupt route | Prove native wait registration/recheck/wakeup/lifetime, spurious/lost wakeup handling and bounded fallback; do not invent NVIDIA selectors or enable unknown IRQ bits |
| Frozen native integration | The complete latest public-timer stage compiles to a nonloadable x86_64 object with the pinned SDK; all 376 imports resolve in the six existing declared KDK providers after kernel-resource interface/reference/alias validation, and the prior private cancellation import is removed; no R3 native candidate | Finish actual IOKit/platform/module lifecycle, entrypoint/VM audit, reader/protocol/drain integration, exact build34 provenance and paired runtime/ABI/collection inclusion without weakening admission; static compilation/provider resolution alone is insufficient; see `BUILD34-PUBLIC-SERVICE-TIMER.md` |
| Raw-debug/queue handoff and paired bootstrap | Latest source stage gives eleven raw mutators exclusive transactions/service leases and two readers service leases, latches one-shot disjoint queue adoption, and defers both existing bootstrap adoption calls until raw setup ends; 1,063 ASan/UBSan and TSan driver checks, 28 bootstrap checks, 40 rejected broken variants and complete original/proposed driver/bootstrap object compiles pass, with the same 376 driver imports | Establish initial external queue/firmware writer ownership/drain, actual mapping/visibility and bootstrap progress/errors; finish platform/factory/claim/native lifetimes and healthy service cleanup; the gate is not GPU drain and unchanged production bootstrap is incompatible with this staged handoff; see `BUILD34-RAW-QUEUE-HANDOFF.md` |
| Native factory and configured discovery | Latest composed stage leases construction, refuses observed closed starts without returning clients, retains uncertain pins, atomically publishes configured discovery and removes the sysctl flag's plain precheck; 238 ASan/UBSan and TSan checks/18 groups/nine threaded scenarios, 16 rejected broken variants, the preceding 1,063-check raw-handoff suite on new source and complete native object/provider checks pass | Finish native platform/factory final handoff, PCI claim/matching, sysctl/module teardown and healthy reclamation; configured discovery is not live health/drain, final check is not atomic with stop, and reader/protocol/event/hardware requirements remain; see `BUILD34-NATIVE-FACTORY.md` |
| Hardware acceptance | None for R3 | Fresh compatible finite recovery scope; exact loaded images, dual-queue/gap and full-arena correctness, timeout/lifecycle and desktop behavior, measured FPS/CPU/latency and stated-duration stability |

The ledger records evidence levels, not a count of tests as a substitute for
hardware correctness. CPU concurrency is not IOKit lifetime, BAR coherency,
GPU execution or FPS. A timeout, an empty transport history, completed receipt
metadata or a drained CPU gate never independently authorizes BO/VMID release.

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
   There is still no native exact mode request, capability negotiation,
   independent global prefix/visibility or Mesa wire binding.
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
5. Add a safe completion notification path and measured bounded fallback,
   preserving lock order, cancellation and shutdown safety.
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
