# Build34 R3 completion plan

The owner requested the continuing goal **complete R3** on November 21, 2026.
The only baseline is default `upstream34/vram-layout-fix`, PhxBringup build34.
The accepted R1b/R2a/plugin and startup/recovery settings stay in place while
this work is developed. Build41/build42 remain withdrawn. R4–R6 do not advance
until R3 has its required paired native and hardware acceptance.

This goal does not turn earlier CPU experiments into deployable kernels or
replay consumed installation/reboot scopes. Build and deployment admission must
still prove the actual source, ABI, SDK, candidate and recovery identities.
In particular, the current permanent client/service quarantine experiments
must not be built as kernel candidates. A local commit is not synchronization;
each coherent change requires checks, staged privacy review, push and an
independent remote SHA check.

## Dependency and acceptance ledger

| Work | Evidence now | What must close it |
| --- | --- | --- |
| Preserve safe global retirement | Existing build34 path and CPU regressions | Keep legacy resource-reclamation/CPU-fence semantics while exact targets complete independently |
| Mesa exact bookkeeping, multi-target fairness, conservative CS ordering/shape | Five isolated reviewed patches with actual-source CPU tests, including single-native-batch preflight and a bounded completion/ACK cache | Carry into a paired negotiated backend, freeze dependencies, prove snapshot/visibility and caller backpressure/error behavior; an aggregate exact CS protocol is not implemented |
| Native target ownership and queue generation | Staged submit, invalidation, observer and embedded binding pass CPU/TSan tests | Actual SDK/KPI integration plus authenticated native admission and queue lifecycle evidence |
| Exact wait fallback | Original wait passes CPU/TSan; the later wait-pinned version re-runs all 28 groups/six threaded cases (22,094 checks) | Carry into the native negotiated path; real KPI/lifecycle and GPU timeout/wakeup evidence remain required |
| Trusted device fence observation | Primary-source packet/mapping review and 189,198-check low-dword window primitive; no reader admitted | Integrate the bounded window with all shared-queue submissions, establish actual mapping/device coherency and ownership/drain, then obtain native/GPU evidence; see `BUILD34-FENCE-READER.md` |
| Native protocol and receipt lifetime | Internal wait-pinned ACK plus a source-only actual-Mesa 4096-record completion cache; late provider/raw queries, bounded ACK Busy retries, full-cache refusal and four real-thread scenarios pass CPU sanitizers; no native selector or negotiation | Backward-compatible capability/session admission, strict wire marshalling, genuine global-prefix snapshot, native visibility/publication and error/backpressure integration; caller-quiescent transport destroy is still required |
| Resource and object teardown | Deliberate permanent retention only | Healthy completion can safely reclaim after CPU callbacks and actual GPU work drain; uncertain/lost work remains quarantined, never released by timeout alone |
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
4. Replace permanent healthy-client/service retention with proved callback/GPU
   drain and reclamation. Keep fault/uncertain-work quarantine distinct from
   successful completion; audit every VM mutation and native entrypoint.
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
