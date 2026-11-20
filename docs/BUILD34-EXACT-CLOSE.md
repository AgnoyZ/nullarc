# Build34 conditional exact-client close and deferred reclamation

This source-only stage derives from [conditional legacy close](BUILD34-LEGACY-CLOSE.md).
`tools/build34_exact_close.py` leaves production sources, all earlier experiments,
the native ABI, runtime recipes and installed configuration unchanged. It binds
neither a device fence reader nor a native exact-mode selector. Service teardown
still retains its permanent quarantine. **Do not build this stage as a kernel
candidate, deploy it, or infer native reclamation or R3 acceptance from it.**

## Admission and shared reference lifetime

Exact and legacy starts now share the one-shot atomic lifecycle. Exact binding
checks service admission, VM health, timer availability and a free registration
slot under `gpuLock` before allocating its Registry owner. It takes one client
and one provider reference, publishes the embedded Registry identity and then
publishes the shared slot. These are the same two registration references used
by cleanup, not an additional pair layered over the old exact retention pins.
The existing 96-slot table and bounded four-client timer batch serve both modes.
Their older `legacy` field/helper names remain to keep this change localized.

Live entry admission requires the release/acquire lifecycle publication in both
modes. Query/wait/ACK also check a failed callback lease before reading identity
or pin fields that successful cleanup can change. The provider reference follows
the client object through final free, including a concurrent close caller that
outlives registration detachment. There is no retain/resurrection in `free()`.

## What authorizes an exact close

The common close first closes client admission and marks the registration
pending. The exact cleanup helper holds a temporary client reference and uses
the existing one-reaper claim. Its order is:

1. Require closed **and drained CPU admission before taking the client lock**.
   Until then the Registry remains open so an already admitted submit can still
   publish its irrevocable receipt, even if close prevents the reply reaching
   userspace. Admitted waits must leave their metadata pins before cleanup.
2. Seal the Registry under the client lock. Obtain a checked service snapshot
   under `gpuLock` using the real owned allocation generation and a reciprocal
   scan that rejects missing, mismatched or duplicate client allocations.
3. Require the genuine global prefix to cover authoritative context `newest`
   and the client's last sequence. Independently check both queue observations
   and all historical publication bounds against that context's actual queue
   sequences and generations. An exact GFX completion cannot substitute for
   the global prefix while earlier compute remains pending.
4. Reject reserved/unpublished entries, Lost entries, remaining wait pins,
   invalid accounting/identity, generation uncertainty and invalid observations.
   A pending valid GPU target returns Busy and leaves cleanup for a later batch.
5. Publish any completed legacy CPU fence and require checked `vmidFree` success
   before clearing the VM tuple. Only then issue the temporary exact cleanup
   permission and the one-shot `freeAll` permission. Every descriptor still
   needs its individual `Bo *` release permission.
6. After BO cleanup succeeds, retire the closed receipt metadata, detach the
   registration, release its session, clear client pins and mark reaped. Unlock,
   terminate and drop the registration client reference. Final free occurs when
   the remaining caller/batch references leave; its existing provider reference
   is adopted and released after base finalization.

The Registry now retains the highest published receipt per queue independently
of ACK and slot reuse. Its historical maximum and owner identity are not reset
by retirement. A publication across generations sets a sticky close fault;
this stage does not attempt to prove an old generation's hardware drain.
An empty receipt table, prior Complete status or drained CPU gate alone never
grants BO/VM release. In particular a receipt published before the service's
authoritative context submission record cannot be covered merely by a later
completion value from some other client.

Failed drain proofs clear no entries. VM failures retain the VM tuple and BOs.
Uncertain host `complete()` retains its exact descriptor in `releaseHeld` and
does not retry or release it. Terminal errors retain client/provider references
and stop repeated cleanup polling. A later successful new queue adoption is
not used to recover an uncertain old generation.

## Evidence and limits

The runner freezes all 172 production inputs and prior experiment inputs, then
extracts actual staged registration, submit, query/wait/ACK, close, VM, BO,
descriptor, external entry and timer-dispatch methods. It runs the previous
legacy scenarios on the new source, with only the old idle-exact-quarantine
scenario derived to expect conditional healthy cleanup. The old fixture and
its original evidence remain unchanged; those inherited checks are reported
separately from new exact cases.

New scenarios include full-64 receipt retirement, completion history after ACK,
remaining reservations/pins, lost generations, pending GPU cleanup, earlier
compute versus completed exact GFX, service/VM/reader/descriptor failures,
authoritative work missing from client bookkeeping, pre-reference publication,
capacity, concurrent start/close/provider lifetime and close during an admitted
submit or wait. The deliberately injected published-before-VM-newest and
reserved-entry boundaries model retained metadata; they are not reports of an
installed driver or real GPU failure.

See [sanitized validation](validation/build34-r3-exact-close-offline-20261121.json)
for sanitizer results, runtime mutants, frozen hashes and explicit acceptance
flags. Final ASan/UBSan and TSan each pass **17,209 new checks in 42 groups,
including four threaded scenarios**, plus **8,345 derived legacy checks in 31
groups with seven threaded scenarios**. All **26 runtime mutants** compile and
are detected. The first validation run exposed a test-classification gap: a
removed generation check was still rejected by an independent ownership check,
while the original test asserted only refusal. The final fixture separately
requires Lost, Pending and invalid-observation outcomes and tests independent
context/publication ownership. Initial evidence remains private history; it
was not a real driver/GPU failure. Broken children use `_Exit(86)` after a scenario assertion; compilation
errors and timeouts do not count as detected mutants. No OS crash settings are
changed. Runs are serial and use background/low CPU priority:

```sh
nice -n 15 taskpolicy -b make -j1 test-build34-exact-close \
  EXACT_CLIENT_CLOSE_OUT=build/build34-r3-exact-close-new-private
```

IOKit object/reference behavior, storage frees, descriptors, mapping/page walk,
registers, cache visibility, clocks and timer delivery remain CPU doubles. The
actual timer dispatch/rearm body is exercised with `hangCheck` stubbed; this is
not native watchdog acceptance. This is not a native SDK/full-translation-unit
compile, authenticated native capability/session, admitted coherent reader,
CPU/GPU visibility proof, completion-event route, healthy service stop/unload,
real GPU execution, FPS measurement or long-duration stability evidence. The
[R3 acceptance ledger](BUILD34-R3-PLAN.md) therefore remains open; R4–R6 stay held.

Rollback of this experiment means ceasing to derive/use this additional source
stage. Nothing has been installed or enabled by the CPU validation command.
