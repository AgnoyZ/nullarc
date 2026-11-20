# Build34 transactional BO cleanup experiment

This is a source-only continuation of the [VM lifetime experiment](BUILD34-VM-LIFETIME.md).
`tools/build34_exact_bo_lifetime.py` derives from that transform without changing
production sources, the native ABI, installed binaries or earlier experiments.
It has no native reader or mode binding. The permanent exposed-exact-client and
service retention paths remain. **Do not compile this stage as a kernel candidate,
install it or infer acceleration/performance acceptance from its CPU tests.**

## Source counterexamples

The previous staged `doBoFree` erased matching map records and released the
descriptor without calling `vmUnmap`. A client could map a BO, free it before
its first submission and leave a PTE referencing released storage. The previous
`doGemVa` UNMAP erased its record before calling the backend, ignored the
return value and reported success on Busy, lost identity or uncertain TLB
invalidation. These are source/CPU counterexamples, not reproduced failures of
the installed driver.

A second boundary is the delayed CPU user-fence store. Old WAITSEQ looked up
`pendFenceHandle` when a global prefix completed. If BOFREE allowed that handle
to be reused first, WAITSEQ could store an old sequence into the replacement
BO. Queue completion alone does not authorize handle reuse while that store
is still pending.

## Transaction and refusal behavior

The service's new `vmBoSnapshot` holds its callback lease and GPU lock, validates
the allocation's complete client/generation tuple and obtains a checked genuine
global prefix. Release requests additionally require that prefix to cover the
context's authoritative newest submission, including work not reflected by the
client's `lastSeq`. Errors and Busy preserve the caller's output. An independent
completed GFX target cannot skip an earlier pending compute submission. A zero
VM tuple proves only that this client has no allocated VM; the client must also
have no recorded GPU work. This is not a hardware reader/coherency proof.

Actual BOFREE now performs the following transaction with the client lock held:

1. Validate the full-width handle, pool accounting and every matching map range
   before the first PTE mutation or CPU fence store. Use subtraction-based bounds.
2. Obtain the idle-context global proof, including for BOs without map records.
3. Flush the existing CPU-visible BO cache path and publish any completed pending
   CPU user fence before releasing a handle. Validate its destination first.
4. Successfully unmap every matching GPU range before clearing any map record,
   decrementing accounting or releasing the descriptor.
5. Consume the BO slot before host `complete` and descriptor `release` callbacks.
   A callback observing the same slot cannot consume that descriptor twice.

Busy before mutation is retryable. A partial cleanup or uncertain backend
failure retains the BO, accounting and all map records, then sets a sticky
client cleanup fault. Both actual submit helpers, mapping handlers, BOFREE and
the descriptor primitive refuse further mutation/release under that fault.
Retained records after partial unmap are recovery evidence, not permission to
resubmit through old mappings. The service's separate sticky VM fault remains.

Actual GEMVA copies its request once, validates overflow-safe ranges and
publishes MAP metadata only after backend success. UNMAP clears its record only
on success and propagates failures. A VM already allocated is checked even if
`gpuReady()` later becomes false; that transition cannot turn its map operation
into a fake metadata-only success. Exposed exact-client BOFREE/UNMAP remain Busy.

The staged legacy WAITSEQ now samples the checked global snapshot with the
client lock held, publishes CPU fences through the shared helper and releases
locks between polls. Its real monotonic budget includes queued locks and keeps
the existing cap and bounded yielding. Zero budget samples once, completed work
wins, and error paths do not publish outputs. A zero-allocation E1 client retains
mock completion; a lost real VM cannot fall back to mock success. This staged
change is not installed and is not a negotiated exact-target visibility protocol.

## CPU validation

The runner freezes prior inputs and production hashes, extracts the actual
new BO/snapshot/WAITSEQ/descriptor methods and uses actual Bo/Map layouts,
`findBo`, shape checks and `PHXN_MAX_BOS`-sized storage. It also executes the
actual earlier staged VM and submit methods. Earlier VM fixture scenarios are
not run or added to the new suite's counts. IOKit, allocator, page walker,
registers, cache flushing and clocks remain CPU doubles.

Coverage includes all four accounting pools, multi-map release and partial
failure, unmapped pending BOs, global compute/GFX ordering, Busy retries,
uncertain TLB retention, overflow, immutable caller input, handle reuse, host
complete/release order, same-slot reentry, independent client faults, E1 and
permanent exact retention. Four threaded scenarios cover queued cleanup versus
close/stop, a queued mapping after a fault, and late WAITSEQ after handle reuse.
Runtime mutants must compile and fail an assertion; compile failures do not
count as detected defects. Sanitizer counts and final mutations are recorded in
[sanitized evidence](validation/build34-r3-bo-lifetime-offline-20261121.json).
The frozen final ASan/UBSan and TSan runs each pass **10,699 checks in 27 groups,
including four threaded scenarios**; all **22 runtime mutants** are detected.
`make -j1 test` passes, with unavailable firmware-fixture cases skipped under
the existing configuration. All 172 production inputs and frozen prior
experiments retain their hashes. These counts do not include earlier suites.

The first development run passed its original ASan/UBSan and TSan scenarios,
but the runner correctly refused final acceptance after test inputs were edited
during fault injection. Its frozen-input failure is preserved privately; only
the subsequent frozen final run supplies accepted evidence.

```sh
nice -n 15 taskpolicy -b make -j1 test-build34-exact-bo-lifetime \
  EXACT_BO_OUT=build/build34-r3-bo-lifetime-new-private
```

## Still required for R3

Legacy `clientClose` and `free` still use the old BO/VM cleanup order and ignore
VM-release failure. Their native object pins, callback drain, deferred cleanup
and healthy finalization remain unproved; this stage does not authorize those
paths or turn descriptor idempotence into a lifetime/reclaimer proof. A healthy
BOFREE transaction is not a healthy client/service teardown.

Legacy submit still has only one pending CPU user-fence record; acceptance of
multiple outstanding user-fence submissions and their publication/lifetime
protocol must be addressed before native integration. Exact typed submit still
refuses user-fence flags. Actual cache coherency/visibility, page walking,
device ACK freshness, queue ownership/old-writer drain and a trusted native
reader are not established by these doubles.

The temporary global-idle-before-map/unmap policy remains conservative and
unaccepted as the final RADV backpressure/performance policy. Native paired
capability/session/visibility, completion events, compatible SDK integration and
actual GPU correctness/FPS/stated-duration stability are still required.
Keep accepted build34 R1b/R2a/plugin/startup, daily PR28, WindowServer exclusion
and disabled resident monitors. R3 remains active; do not advance R4–R6 or
replay consumed installation/reboot scopes. See the [R3 ledger](BUILD34-R3-PLAN.md).
