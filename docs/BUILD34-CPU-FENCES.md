# Build34 multi-pending CPU fence publication

This isolated source-only stage derives from [conditional exact close](BUILD34-EXACT-CLOSE.md).
`tools/build34_exact_cpu_fences.py` preserves all 172 production inputs, earlier
experiments, native ABI/runtime recipes and installed settings. The reader is
still null, native exact-mode admission is absent and service quarantine stays.
**Do not build this stage as a kernel candidate or deploy it.** It supplies one
resource-publication prerequisite of R3, not native protocol or GPU acceptance.

## Actual previous-method counterexample

The earlier staged `doSubmit` accepts consecutive legacy CPU-fence requests but
stores each in the same `pendFenceHandle/Offset/Seq` triple. The next accepted
request overwrites the earlier target. Once the checked global prefix covers
both jobs, the old actual WAITSEQ publishes only the newest fence; the earlier
accepted target remains zero and can subsequently be released with its BO.

The new runner extracts the preceding stage's actual submit, WAITSEQ, cleanup
and service methods into a CPU backend and reproduces two accepted submissions
to different offsets followed by that loss. It is a software counterexample
in CPU doubles, not evidence of a newly observed installed-driver/GPU failure.

## Publication records and admission

The new client owns a fixed 128-record circular ledger under its existing client
lock. Each entry keeps the submitted sequence, target handle/offset and the
exact BO descriptor, KVA and size. The existing BO continues to own the memory
descriptor; this adds neither descriptor references nor allocations. BO release
is refused while records remain. The old single triple remains only as checked
mirrors of the newest pending record, so existing close/free preconditions cannot
silently overlook an inconsistent ledger.

The bound is an explicit backpressure policy, not a claim about maximum lifetime
GPU traffic. One earlier compute job can hold the safe global prefix behind many
already completed GFX jobs while queue history is pruned. At full capacity,
submission first obtains a checked genuine global snapshot and may publish its
completed prefix. If no space is recovered it returns Busy **before** VM binding,
packet/doorbell writes or scalar output. Reader/identity failure remains distinct
from Busy. The actual RADV caller's progress/retry behavior is still a native
admission requirement; the CPU test does not prove measured frame latency.

Successful actual GPU submit appends its fence before returning its sequence.
An unexpected post-dispatch record error faults client dispatch and retains BO,
VM and existing record ownership; it does not silently report CPU-fence success.
Rejected GPU admission appends no record for the failed request and preserves its
output. Any older records already collected by a separately checked prefix stay
published; they are not rolled back when a later new submission fails.

Both the dedicated exact-submit handler and now the scalar exact-mode path
refuse CPU user fences, because the paired native exact CPU visibility protocol
still does not exist. Legacy E1 immediate mock publication is retained only for
a client with no real VM/work or pending records. Lost real queues cannot switch
to synthetic CPU-fence success, and its counter cannot wrap into the sentinel.
These mock cases are explicitly CPU-only and are not acceleration evidence.

## Checked prefix publication and lifetime

Before any CPU store, the helper validates the entire ledger, including later
pending records: bounds, strict sequence order, authoritative client lastSeq,
exact descriptor/KVA/size, aligned overflow-safe ranges, empty unused slots and
the newest mirrors. A bad later record therefore cannot follow earlier writes
as a partially successful publication. Uncertainty preserves all records and
sets sticky `boCleanupFault` before any target store.

Publication preserves build34's existing `flushBos` operation, writes every
covered record in submission order, then consumes each record. Several records
for the same address therefore leave the latest covered sequence there, while
different BOs/offsets retain their individual values. The helper does not invent
completion, skip holes or promote a completed exact target to the global prefix.
Its checked-prefix caller contract remains essential.

WAITSEQ now publishes an older completed prefix while its requested newer target
is still pending, including a zero-budget poll or eventual timeout. It avoids
repeating the whole BO cache operation on each poll when neither a target nor a
pending CPU-fence record is newly eligible. Successful target waits preserve the
earlier cache-operation behavior. BOFREE and both conditional close paths use
the same helper before handle reuse/VM-first BO teardown; `freeAll` also rejects
nonempty or inconsistent records.

This fixes bookkeeping and publication order only in the staged source. It does
not prove effective cache attributes, GPU-to-CPU coherency, cross-process shared
backing ownership, native userspace visibility or a CPU/GPU release/acquire
protocol. The store/cache operations themselves are inherited from build34.

## Validation and remaining work

[Sanitized evidence](validation/build34-r3-cpu-fences-offline-20261121.json)
records the prior actual-method counterexample, new checks, derived legacy/exact
close regressions, frozen hashes and runtime mutants. Earlier fixtures remain
unchanged: two old direct single-triple setup cases are privately derived to
append real records instead. ASan/UBSan and TSan each pass **23,930 new checks in
25 groups, including two threaded scenarios**, plus **8,347 derived legacy
checks in 31 groups/seven threaded scenarios** and **17,209 exact-close checks
in 42 groups/four threaded scenarios**.
All **22 runtime mutants** compile and are detected by scenario assertions;
they are not included in the passing-check counts.

Initial private evidence preserves an unused-variable counterexample-fixture
compile failure, a host ASan stack overflow from nested large CPU scenarios and
a mutant-coverage gap where mirrored offsets independently rejected a corrupted
offset. The final runner gives only static scenario functions separate frames;
actual staged native methods keep ordinary O1 compilation. The offset fixture
now isolates alignment from its mirror check. No OS stack or crash configuration
was changed, and these failures are not reports of native GPU execution.

IOKit, mappings/page walking, registers, descriptors,
cache operations, clocks and timer delivery remain CPU doubles. Actual timer
dispatch/rearm is extracted but the hang-check body remains stubbed in this suite.
Deliberate child assertion failures use `_Exit(86)`; compilation failures and
timeouts do not count as detected mutants. No OS crash configuration changes.

```sh
nice -n 15 taskpolicy -b make -j1 test-build34-exact-cpu-fences \
  EXACT_CPU_FENCES_OUT=build/build34-r3-cpu-fences-new-private
```

The initial service-lifetime audit also found that the unchanged `hangCheck`
reads two-dword fences and queue histories outside `gpuLock`, while its recovery
helper reacquires that lock later. This leaves checked observation, target
identity/re-adoption and recovery-lifetime audit open. This stage does not modify
watchdog/recovery behavior or accept healthy service stop/unload.

Native reader/coherency, authenticated paired capability/session and exact CPU
visibility, event registration/recheck/wakeup, native SDK/full-TU compilation,
service drain, real GPU correctness, measured FPS/latency and long-duration
stability still require evidence under the [R3 ledger](BUILD34-R3-PLAN.md).
R4–R6 remain held. Rollback is to cease deriving this extra source stage; the
validation command installs, loads and enables nothing.
