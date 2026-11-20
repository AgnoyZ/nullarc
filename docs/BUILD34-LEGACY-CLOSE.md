# Build34 conditional legacy close and deferred reclamation

This is an isolated source-only continuation of the [BO lifetime stage](BUILD34-BO-LIFETIME.md).
`tools/build34_exact_legacy_close.py` derives a private staged source from the
same build34 production input. Production sources, earlier experiments,
ABI/runtime recipes and installed configuration remain unchanged. The native
reader and exact-mode binding are absent, and permanent exact-client/service
retention remains. **Do not build this stage as a kernel candidate or deploy it.**

## What changes in the staged source

The old legacy close called `freeAll` before `vmidFree`, discarded the VM
release result and continued to session release/termination. An ignored
failure could also reach `free` and destroy bookkeeping while GPU completion
or invalidation was uncertain. The new stage replaces those actual methods;
it does not use receipt removal or CPU callback drain as a GPU release proof.

Legacy start now makes a one-shot atomic transition through starting to live.
The service registers the actual client in a bounded 96-slot table under
`gpuLock`, takes a client reference and a provider reference, then publishes
the slot. Entry admission occurs only after those pins and fields are ready.
Failed/repeated/concurrent starts cannot replace a live registration. Full
capacity or a missing/stopped reaper callback refuses before either reference
is taken. Callback availability is rechecked under `gpuLock`, including a
start that queued behind that lock. This does not prove actual native timer
delivery. The earlier exact start and permanent retention path remain separate.

Actual `externalMethod`, `clientMemoryForType` and legacy submit honor their
callback lease in both modes, refuse unpublished legacy starts or service
closure, and recheck client closure under the client lock where relevant.
Cleanup faults also refuse resource dispatch. This includes queued methods
that acquired a lease before close but had not acquired the client lock.

Legacy `clientClose` closes admission and marks its service registration
pending. It holds a temporary reference and attempts conditional cleanup:

1. Require the closed CPU gate to be drained **before taking the client lock**.
   A one-reaper atomic claim also refuses concurrent/reentrant cleanup rather
   than taking that lock recursively from a descriptor/termination callback.
2. Obtain a genuine checked global/owned-context idle snapshot. Busy GPU work
   returns Busy without sleeping or changing BO/VM/session ownership.
3. Publish the completed pending CPU fence through the earlier shared helper.
4. Require `vmidFree` success before clearing the complete VM tuple and before
   releasing any descriptor. A failed VM release retains the tuple, BOs,
   accounting, maps, session and registration pins.
5. Issue one `freeAll` drain authorization. Preflight exact accounting totals
   before clearing maps/pools, then authorize each individual BO release.
6. Detach the registration, release the claimed session, mark reaped, unlock,
   terminate and drop its client reference. The close caller or reaper batch
   still owns a temporary client reference. The provider reference follows the
   client object until final free, protecting another already-entered close
   caller that still needs `owner` after registration detachment.

`free()` no longer retries VM cleanup or ignores its result. Successful close
has already drained/released GPU resources; failed/unstarted initialization
has admitted no GPU entries. Pinned, reaping or uncertain clients are refused
defensively, with no late retain/resurrection. Storage, locks and the base
object finalize only after the remaining references leave. Final free adopts
the already-owned provider reference into a scoped drop and releases it after
the base free; it does not acquire a new provider reference or use client
members after the base object is freed. A concurrent close that finds the
registration already removed rechecks the reaped state and returns success.

## Automatic pending-client progress

The actual existing `hangTick` calls the service reaper before its unchanged
hang check and retains its existing 500 ms rearm period. This does not enable
a userspace monitor or alter installed watchdog settings. Under one GPU-lock
scan, a rotating cursor selects at most four pending registrations and takes
temporary references while their registration references still exist. It then
unlocks before calling any client cleanup, host callback or reference release.
Sparse pending slots are found without requiring them to be in the first four
table entries. Busy clients stay pending for another callback; terminal errors
retain their pins and stop repeated cleanup polling.

A healthy client whose port reference has disappeared can therefore finish
after the CPU callbacks and GPU work complete. It does not depend on userspace
retrying `clientClose`. Batch and timer references protect code that continues
after a registration pin is dropped, and leave callback gates before the last
scoped object reference is released. This is a CPU-tested reference protocol,
not acceptance of actual IOKit finalization, thread-call delivery/cancellation,
service stop/unload or a healthy service reclaimer.

## Descriptor release admission and failure

Both actual descriptor callers are updated: BOFREE and authorized `freeAll`.
`boRelease` requires an exact `Bo *` permission, consumes it before callbacks,
moves the descriptor into a single `releaseHeld` record and clears the handle.
A reentrant callback has no permission to release either that slot or another
BO. Host `complete()` must return success before descriptor `release()`.
An uncertain complete keeps the exact descriptor in `releaseHeld`, closes
client resource dispatch and never retries complete or releases that descriptor.
Other still-owned BO records remain retained behind the registration pin.

The primary Apple source review uses the already pinned manifests for
[IOMemoryDescriptor](validation/build34-r3-fence-reader-sources-20261121.json)
and [IOUserClient](validation/build34-r3-receipt-interface-sources-20261121.json),
XNU commit `f6217f891ac0bb64f3d375211650a4c1ff8ca1ea`, separately reviewed as
APSL-2.0. `IOMemoryDescriptor.h:748–754` describes complete's paired operation
and return code; `IOUserClient.cpp:1980–1988,4613–4635` does not promise repeated
close calls after a Busy result. This was read-only interface/control-flow
review; no upstream implementation was copied. The source revision is not
claimed to match the installed kernel or the current SDK.

The previous BO-stage declaration placed `vmBoSnapshot` in the service's private
area while the client called it. Its all-public CPU fixture did not check that
access restriction. This stage moves the declaration to the actual public
service interface with the other client-callable VM methods. The new runner
checks the actual native access labels for each new cross-class helper; this
is not a full native translation-unit or SDK compile.

## Validation and remaining admission work

The runner freezes all earlier production/experiment inputs, tests the actual
new start/registration/close/reap/free/descriptor/entry methods, and executes
the actual `hangTick` dispatch/rearm body. The hang-check implementation and
unrelated external selectors are CPU stubs. OSObject references/finalization,
storage frees, host descriptors, allocator/page walker, registers, cache
visibility, clocks and timer scheduling are deliberately CPU doubles.
Earlier fixture helpers are reused without executing or counting their old
scenarios. Sanitizer counts and runtime mutants are in
[sanitized evidence](validation/build34-r3-legacy-close-offline-20261121.json).
Counts do not include earlier suites. The default `make -j1 test` regression
passes with its existing unavailable firmware-fixture cases skipped; the 172
production input hashes are unchanged. Deliberately broken children report an
assertion and exit nonzero through `_Exit(86)`; intended protocol failures do
not deliberately crash the process. No OS crash-handling setting is changed.
The final frozen ASan/UBSan and TSan runs each pass **8,325 checks in 31 groups,
including seven threaded scenarios**. All **28 runtime mutants** compile and
are detected by scenario assertions. These fault-injection results are recorded
separately in the evidence and are not counted as passing checks.
The initial green CPU runs were followed by a source review that found a
provider-reference gap between concurrent close calls. Those earlier results
remain private history. The final suite adds a second close paused after its
temporary reference, removes the original caller/provider references, then
proves the earlier close can still finish and both objects finalize in order.
That CPU object-reference test is not acceptance of native service/thread-call
unload semantics.

```sh
nice -n 15 taskpolicy -b make -j1 test-build34-exact-legacy-close \
  EXACT_CLOSE_OUT=build/build34-r3-legacy-close-new-private
```

This establishes conditional legacy cleanup/reference order only under the
tested CPU contracts. Native entry/callback coverage, actual OSObject/free and
thread-call cancellation, CPU mappings that outlive a client, sleep/stop/unload,
native page walking, ACK freshness, queue ownership/old-writer drain, coherent
device reads and visibility remain unaccepted. A four-client bound does not
bound the wall time of a native 4,096-BO sweep or a host callback; measure and
refine actual cleanup scheduling before making desktop/FPS claims.

Permanent exact-client and service retention still must become proved healthy
drain/reclaim paths. Multi-outstanding CPU user fences, paired capability/
session/global-prefix/visibility, completion events and actual SDK integration
are also pending. No GPU correctness, physical FPS or stated-duration stability
acceptance has been obtained. Preserve accepted R1b/R2a/plugin/startup, daily
PR28/WindowServer exclusion and disabled resident monitors. R3 stays active;
R4–R6 and consumed deployment/reboot scopes do not advance.
