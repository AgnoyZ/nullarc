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
| Native protocol and receipt lifetime | Internal wait-pinned ACK, actual-Mesa bounded completion cache, and staged complete-token structure submit/wait/ACK dispatch pass CPU sanitizers; experimental selectors 64/65/66 have no production mode/capability or Mesa wire binding | Complete native capability/session and production exact-submit admission, independent genuine global-prefix/visibility and CPU-fence protocol, paired binding and caller backpressure/error integration; caller-quiescent transport destroy is still required |
| Resource and object teardown | Source-only owned VM/BO cleanup and conditional legacy/exact close pass CPU tests; exact historical publication bounds survive ACK, admission pins precede slot publication, checked VM release precedes BO cleanup, and the actual timer dispatch serves a bounded shared reaper; service permanent quarantine remains | Prove native BO/object/callback/thread-call lifetimes, page walk/ACK and stop/unload; finish multi-pending CPU fences and healthy service drain; conditional exact-client reclamation still needs native/GPU evidence, while uncertain/lost work remains quarantined |
| Completion notification | No AMD completion event/interrupt route | Prove native wait registration/recheck/wakeup/lifetime, spurious/lost wakeup handling and bounded fallback; do not invent NVIDIA selectors or enable unknown IRQ bits |
| Frozen native integration | No R3 native candidate | Complete entrypoint/VM audit, actual SDK compile, exact build34 provenance and paired runtime/ABI validation without weakening existing build34 admission |
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
