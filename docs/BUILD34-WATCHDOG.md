# Build34 checked watchdog recovery

This source-only stage derives from [multi-pending CPU fences](BUILD34-CPU-FENCES.md)
on default `upstream34/vram-layout-fix`, PhxBringup build34. It changes neither
the 172 production inputs nor prior experiments, ABI/runtime recipes, installed
images or settings. The native reader remains null, exact-mode admission is
absent and service quarantine remains. **Do not build this stage as a kernel
candidate or deploy it.** R3 remains incomplete and R4–R6 stay held.

## Previous actual-method counterexample

The preceding stage still uses the original `hangCheck`: it reads a two-dword
fence and queue history without `gpuLock`, chooses a hardware VMID, then calls
`killWaves`, which acquires that lock later. Its selection can therefore become
stale across queue adoption or context/VMID reuse. The old recovery also sends
SQ_CMD after its bounded RLC wait even when every read reports not ready.

The new CPU runner executes those actual old methods with mapping/register/time
doubles. It observes the unlocked mapping access and exactly 1,000 not-ready
RLC reads followed by an SQ command. This is an actual-source CPU counterexample,
not an observed installed-driver failure or native hardware recovery evidence.

## Checked target ownership and timing

Actual staged `gpuSubmit` now records the context handle and its nonreused
allocation generation alongside the sequence and hardware VMID, before publishing
the history tail. A VMID alone cannot identify the original allocation. Queue
adoption initializes the watchdog clock, and a transition from no pending
history to new work restarts it under the same lock, after writing the doorbell.
Neither a long idle period nor CPU scheduling delay before that write counts
as the new job's hang interval; additional jobs behind pending work do not
continually reset that interval.

`hangCheck` holds one admitted service callback and `gpuLock` through observation,
target selection and the recovery command. It first requires the existing
checked genuine global snapshot, then validates both queues' bounded ordered
histories, ring/writeback/fence geometry and low-dword observations. Each pending
slot must still match a busy context, client, allocation generation, queue work
generation and reciprocal hardware VMID. Completed historical entries may
outlive a freed allocation; they are not incorrectly required to own a current
context. Unknown readers, corrupt histories and lost generations cannot issue
recovery or become completion.

Only a successfully checked observation updates the progress clock. Idle or
changed completion restarts it. The first targeted attempt requires the full
configured interval with pending work. This stage does not change production
`gHangMs` or any installed watchdog/monitor setting.

## One retained recovery episode

Recovery keeps a fixed service-owned episode outside resettable queue history.
It captures the target queue/slot/sequence, context/client/allocation and VMID,
both queue generations/history bounds, mapping object identities, addresses,
lengths, geometry and reader. It constructs a separate `FenceWindow32` using
the checked completion and submitted bound; copying the ordinary decoder is
forbidden. The diagnostic decoder never feeds receipts, global retirement,
CPU fence publication, VM cleanup or BO release.

Before any recovery register write, a sticky VM fault closes submit and VM
mutation/reuse, and both ordinary queue generations are invalidated. Adoption
now refuses that fault, so it cannot erase the captured history or reseed the
same fence while recovery is unresolved. All subsequent diagnostics require
the captured post-invalidation epoch/generations, history bounds, mappings,
reader, geometry and reciprocal allocation identity to remain unchanged.
Service close, stop/sleep, mapping/reader uncertainty or target identity loss
ends the episode; it does not authorize a blind global kill or resource release.

The first attempt targets only the captured VMID. A checked old-generation
diagnostic observation can stop escalation after target completion, but it
never clears the sticky fault or declares killed work successful. If that same
target remains valid and pending for a **second full threshold** after the
targeted attempt, one all-waves attempt is allowed. Although the old inner
condition mentions half a threshold, its outer gate required the full threshold;
the new path preserves that effective behavior. The episode is then terminal.
No repeated global writes or polling follow terminal status.

## RLC bounds and closure

The lock-held helper uses only build34's existing RLC safe-mode and SQ command
registers/values. It requires an observed ready bit before SQ, bounded by both
1,000 reads and one millisecond of actual monotonic elapsed time, including
delayed register reads and scheduler time. It rechecks current identity,
closure and pending target before entering safe mode and again before SQ.

Every performed safe-mode entry has exactly one exit, including observed close,
timeout and completion during the RLC wait. The caller retains the admitted
callback/mapping lifetime through that paired exit. A close observed before
SQ prevents it; a command already issued when close is observed still gets its
paired exit and terminates recovery. `gHangKills` counts SQ attempts, not
confirmed drain or successful work. Unknown/timeout results preserve ownership.

These CPU tests do **not** establish native RLC ACK freshness, effective device
read coherency, hardware recovery semantics, absence of external old writers,
or the native mapping lifetime needed to justify the paired exit. Existing
register values are preserved, not endorsed as sufficient by the CPU doubles.
Native admission must close those prerequisites under the R3 ledger.

## Validation and rollback

The [sanitized evidence](validation/build34-r3-watchdog-offline-20261121.json)
records ASan/UBSan, TSan, actual-method inherited regressions, bounded threaded
scenarios, detected runtime mutants and frozen input hashes. The runner uses
the actual queue layout, watchdog, submit, wait, close/reaper and VM methods.
The prior hang-check stub counter is removed only in its private derived legacy
fixture; original fixtures remain frozen. Only static zero-argument CPU scenario
functions receive separate frames, while native methods retain ordinary O1
compilation. Deliberate mutation assertion failures use `_Exit(86)`; compile
failures and timeouts never count as detected defects.

The final positive ASan/UBSan and TSan runs each pass **17,648 new checks in
110 groups, including five real-thread scenarios**, plus **8,407 derived legacy
checks / 31 groups / seven threads**, **17,233 exact-close checks / 42 groups /
four threads**, and **23,942 CPU-fence checks / 25 groups / two threads**. The
last three suites are inherited regressions, not new watchdog coverage.
All **31 runtime mutants** compile and are detected by scenario assertions;
their failed checks are excluded from the passing counts.

Private attempt evidence retains an unused-variable counterexample-fixture
compile rejection, an incorrect fixture expectation of more than 1,000 old
RLC reads, a fixture expecting NotReady where the existing exact BO quarantine
correctly returns Busy, and a nonunique mutation anchor refused by the source
guard. A subsequent run passed 30 runtime mutants before the final review
moved the new-work clock after the doorbell and added a CPU preemption case.
These were CPU fixture/runner corrections and source review, not native GPU
failures; no OS stack, crash-report or security configuration was changed.

```sh
nice -n 15 taskpolicy -b make -j1 test-build34-exact-watchdog \
  EXACT_WATCHDOG_OUT=build/build34-r3-watchdog-new-private
```

Rollback is to stop deriving `tools/build34_exact_watchdog.py` and use the prior
source-only stage; this command installs, loads and enables nothing. Keep the
accepted R1b/R2a/plugin/startup runtime, daily PR28 250 ms/WindowServer exclusion
and disabled resident monitors. Healthy native service/timer teardown,
reader/visibility, paired protocol, completion events, SDK compilation and
actual GPU/FPS/long-duration stability remain open in [the R3 ledger](BUILD34-R3-PLAN.md).
