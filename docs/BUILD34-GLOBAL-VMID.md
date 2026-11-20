# Build34 R3 checked global retirement and VMID admission

November 21, 2026: a separate source-only transform now carries the bounded
dword observation into the actual staged global-retirement and VMID-binding
methods. It derives from the [window callsites](BUILD34-WINDOW-CALLSITES.md).
The installed build34, all 172 protected production inputs, native ABI,
earlier experiments and runtime recipes are unchanged. The device reader is
still null; permanent client/service quarantine still retains resources.
**Do not compile or deploy this experiment as a kernel candidate.**

## Global snapshot

The original MIT [transform](../tools/build34_exact_global.py) introduces
`exactGlobalRetiredLocked(uint64_t &)`. Its caller holds both `gpuLock` and a
service callback lease. It validates both queues, never substituting the
completed exact target or one selected queue for the global prefix.

Each previously adopted queue must have a valid current dword observation,
live/ready generation and submitted bound no greater than `gSeq`; completion
cannot exceed that submitted bound. Queue history has at most 63 entries,
strictly increasing nonzero/nonterminal full-width sequences and a final
entry equal to the submitted bound. Empty history requires completion of
that bound. Unsigned head/tail wrapping is supported. The snapshot is the
sequence immediately before the earliest pending job across both queues,
or `gSeq` when all represented work has completed.

A never-adopted queue may be skipped only when its generation, readiness,
liveness, head, tail and submitted metadata are empty. This is a metadata
condition, not proof that an external or previous hardware writer drained.
Service terminal/sleep gates are checked before and after sampling. The sole
output write occurs after all checks; failure leaves the output unchanged.
Earlier valid observations can advance their internal decoder cache even
if a later check fails; no partially valid global prefix is published.

The staged `gpuRetired() const` now obtains a callback lease and GPU lock,
then calls this checked helper. Its old scalar ABI still reports zero on
failure. It does **not** transport explicit validity, a cache-visibility
guarantee, a CPU fence publication or an exact-mode negotiation to Mesa.

## Actual VMID binding and retry

The actual staged `vmBind(handle, retired)` takes the lock-held checked
snapshot as an argument. It performs one bounded scan, accepts a valid
cached reciprocal context/VMID association, otherwise uses a free slot or
the least-recently-used slot whose newest sequence is no greater than the
genuine global prefix. Invalid cached/victim associations refuse before
register writes or eviction. The original seven context register writes
and TLB flush call are preserved. This does not prove every possible
corrupt pool shape or context allocation/reuse is covered.

The former `vmBind` loop slept/spun while holding `gpuLock`. VMID admission
now occurs in the existing R1b submit retry loop. Sequence exhaustion,
window admission and the two-queue snapshot are checked under that same
lock before VMID binding. If no VMID is available, submission releases the
GPU lock and yields one millisecond within the original monotonic two-second
budget. A first failed VMID scan that already exhausted the budget does not
sleep again. Successful binding retains the lock through receipt/window
publication, packets and doorbell; publication can still fail after VM
register side effects, as previously documented.

An already admitted exact client submission keeps its lease after client
close, consistent with the existing retention contract. It may finish or
reach its bounded admission timeout; close is not a newly added immediate
cancellation signal. Service stop and queue-epoch invalidation abort the
retry, while existing receipts and resource references remain retained.

## CPU evidence and limits

The [runner](../tools/test_build34_exact_global.py) freezes all prior inputs
and extracts the actual staged global, submit, VMID-binding and context
lookup bodies/layout. IOKit objects, memory, register writes, clock, sleep
and TLB flushing are handwritten CPU doubles. The old binding fixture's
unrelated regression functions are compiled but not executed or included
in these counts. There is no native SDK or GPU runtime linkage.

ASan/UBSan and TSan each pass **87,821 checks in 630 groups and four
real-thread scenarios**. Fifteen defective variants are detected at runtime,
including target-to-global promotion, skipping a lost queue, malformed
history acceptance, pending VMID eviction, missing reciprocal checks,
recursive public `gpuRetired()` locking, holding the GPU lock across sleep
and an extra sleep after the first admission used up its budget.

The tests include an independent global job-list oracle with 576 completion
states, global sequence gaps, low-dword and history-index wraps; invalid
reader/mapping/lifecycle/history failure preservation; free/cached/LRU and
refused actual VMID scans; both exact and legacy submitters; and full-pool
timeout. A paused waiter releases `gpuLock`, another already bound GFX
client submits and completes, the global prefix stays behind compute, and
only after compute completes can the waiter reuse an eligible VMID.

Development failures are preserved privately. One extraction guard initially
used the wrong return type for `vmUnmap`; two fixture assumptions incorrectly
reseeded a generation and required close to cancel already admitted work.
The first oversized-history test was also independently invalid due to
duplicate entries, so it failed to detect removal of the capacity guard.
That case now has 64 otherwise valid increasing entries and isolates the
capacity defect. None of these observations is an installed-driver failure.

```sh
nice -n 15 taskpolicy -b make -j1 test-build34-exact-global \
  EXACT_GLOBAL_OUT=build/build34-r3-global-vmid-new-private
```

See [sanitized evidence](validation/build34-r3-global-vmid-offline-20261121.json).

## Remaining release blockers

The old `vmidFree` timeout path is deliberately unchanged: it can still
clear tables after its wait expires. Client legacy cleanup ordering,
`vmMap`/`vmUnmap` context identity and allocation ABA, full callback/entrypoint
fencing and watchdog consumers are not proved safe by this change. In
particular, the original void `vmFlushTlb` still does not propagate an ACK
timeout. The CPU TLB double cannot prove that hardware acknowledged it.

Healthy reclamation requires actual context identity and CPU/GPU drain, not
just a new scalar watermark or empty receipt metadata. Keep permanent
quarantine until that proof exists; it is not a deployable reclamation
strategy. Mapping coherency, exclusive queue ownership/old-writer drain,
native capability/session and paired Mesa prefix/visibility/CPU-fence wire,
completion events, complete SDK integration and real GPU/FPS/stability
acceptance remain open in the [R3 ledger](BUILD34-R3-PLAN.md). R3 stays active;
R4–R6 have not started.
