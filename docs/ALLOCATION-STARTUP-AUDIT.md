# Reference startup failure propagation audit

Historical pre-fix audit on 2026-11-14: **additional source admission/recovery gaps confirmed;
no startup integration or target execution**. The [execution plan](ALLOCATION-EXECUTION-PLAN.md)
still requires native delivery, recovery review and Phase A before a display
attempt. These findings do not identify the allocation root cause.

The later [caller-status correction](ALLOCATION-STARTUP-STATUS-FIX.md) adds
explicit checks to the reference wrappers. The source pin and seven scenarios
below describe the pre-fix revision; its retained validation remains historical.
The current harness pins the corrected monitor and tests its failure exits.
The initializer-compatibility and recovery-independence gaps remain open.

## Pinned source and test boundary

The reference `tools/phxctl/phxboot.sh` has SHA-256
`6c0271c306b8edbe0bc5b294794a8f47480a6bd25eae9c0a9207471f8fd794d8`.
`tools/test_allocation_startup.py` extracts its actual initialization interval
and `m2_fail` function without changing their control flow. It refuses any
other whole-file hash before creating output or launching a child. The full
reference is only syntax checked with Bash `-n`, never launched.

The extracted intervals run in private fixture directories with shell functions
replacing initializer and system commands, a guarded newly written claim fake,
an empty PATH and a clean environment. The real grep filters fixture text only.
There is deliberately no `full.sh` file. Source outputs, marker operations,
sysctl, NVRAM, removal, synchronization and shutdown requests in the intervals
are fakes. A controlled open pipe can block the selected fake; it is not a
GPU, filesystem or kernel hang. Existing outputs cannot be reused or overwritten.

Six unit tests include seven subprocess scenarios, source-pin refusal, no
replay, extraction integrity, fixture guard refusal and whole-reference syntax.
This characterizes actual pinned source fragments with API fakes. It is not
a whole-script execution, an installed-launcher audit or a recovery integration
test. The harness uses default shell options; an external caller could supply
different options, which were not checked on the installed machine here.
The initialization interval ends before the later NMXAccel availability check.
That later branch can still request fallback. A fragment's zero exit does not
establish that the complete monitor would arm or release the display.

## Observed control flow

| Source-fragment scenario | Observed behavior | Supported finding |
| --- | --- | --- |
| Successful fixture commands | Initialization, claim and later setup execute in order | Harness reaches the normal fragment endpoint |
| Initializer exits 17 after matching output | grep succeeds; claim and later setup still run; fragment exits 0 | Filter success does not establish initializer success |
| Initializer exits 17 without matching output | grep returns nonzero; claim and later setup still run; fragment exits 0 | The reference interval does not act on pipeline failure |
| Claim exits 23 | Later setup still runs; fragment exits 0 | Claim status is not explicitly checked there |
| Initializer held on a fixture pipe | Claim and setup are absent until the pipe is released | This coordinator waits on initialization |
| Claim held on a fixture pipe | Later setup is absent until the pipe is released | This coordinator waits on claim |
| Recovery sysctl held on a fixture pipe | NVRAM and shutdown fakes are absent until release | Recovery's own serial sysctl precedes its shutdown request |

The reference defines and invokes `watch_hangs` only after startup. Its earlier
`m2_fail` definition is a callable function, not an independently running worker.
The reference source does not enable `errexit`/`pipefail` or explicitly check
the initialization/claim statuses at these lines. These facts describe this
coordinator; they do not exclude another external watchdog or establish the
installed monitor's current behavior.

Read-only review of `src/phxaccel/accel/phxagdc.cpp` also limits the recovery
interpretation: `phxagdc_sysctl` sets the requested state, allocates/schedules
`agdcWork` and returns; it does not explicitly wait for the worker's synchronous
service termination call. That termination appears in `agdcWork`, not in the
sysctl handler. The blocked-sysctl fixture therefore demonstrates a serial
shell dependency under injected non-return, **not** an observed AGDC teardown
deadlock or proof that this handler normally waits for teardown. No handler or
worker was executed, and no kernel latency bound was established.

## Initializer and helper compatibility

Read-only source review found that reference `full.sh` calls `mesboot gart`
and `mesboot mes` without layout arguments, whereas the current audited
`mesboot.c` requires explicit layout arguments for both. The wrapper has no
explicit `errexit`/`pipefail`, filters later output through tail, and finishes
with a global shutdown-process kill. It also schedules its own four-minute
reboot watchdog. These are further reasons not to reuse this legacy wrapper
as an initializer for a new independent-recovery experiment. A generic process
kill can conflict with another scheduled shutdown worker; no such conflict
was induced or observed on this machine.

A stable, read-only file inspection of the currently installed initializer
and mesboot helper confirmed that the initializer differs from the repository
reference, still has the bare GART/MES call forms and no explicit strict-shell
options, and contains the same watchdog/global-kill command forms. The helper
file lacks the current audited source's explicit-layout and checked-transport
diagnostic strings. Raw copies, exact paths, hashes and command lines remain
private. String absence does not establish source identity or execution
behavior; no helper was run, replaced or traced. This inspection does not prove
which bytes executed during the previous failed boot.

The current source's claim operation uses `checked_scalar`, which exits 74 on
a failed transport or reply count; its caller still needs to propagate that
failure. This is counterevidence to treating the C wrapper itself as silently
accepting a failed transport. The installed helper's corresponding source is
not established by this review. Neither a current source argument refusal nor
the injected statuses 17/23 can be assigned to the actual build-36 failure.
Preserve the explicit-layout and transport guards; do not weaken them to make
an inherited wrapper appear compatible. A zero exit alone is not GPU readiness.

## Consequences for a future admission candidate

The minimal source seam for a pre-initialization baseline is **before the
pending-marker/allowlist interval**, with recovery already available. The
existing observer's `observer.started` marker does not provide that seam:
it follows its own baseline, does not admit a workload and can be written
after its observation deadline has already elapsed. Calling the observer
synchronously at that point would add another blocking dependency.
The existing late-baseline observer unit test now explicitly checks this
counterexample: a hash-linked `observer.started` is present although its fake
monotonic deadline is past and the completed observer outcome is `window-expired`.
The actual observer runs with a fake collector/clock; no service or real report
directory is used. Marker existence and a correct baseline hash alone therefore
do not establish a timely admission decision.

Admission must validate the completed baseline and its identity/hash/capacity,
establish same-boot monotonic ordering, and refuse missing/late/changed evidence.
After admission, initialization and claim need explicit successful results
before display setup/release; neither matching output nor a successful final
shell command supplies those results. Failure must not automatically initialize
or arm again. The existing GPU behavior, VM guards and cleanup remain unchanged.
The initializer's own error propagation, explicit layout contract and watchdog
ownership must also be reviewed; fixing only its parent shell's exit checks
does not make the old nested wrapper suitable.

Recovery independence has two separate requirements: its decision maker cannot
wait on the observer/initializer/claim, and its actual recovery path needs a
reviewed response to helper non-return. Launching the current `m2_fail` in
another process alone does not prove both. Preserve the existing asynchronous
AGDC scheduling behavior and recovery thresholds; no recovery-policy change
is justified by the injected block alone. A future proposal must review its
exact permitted operations and failure cases, acknowledging that an OS unable
to schedule userspace cannot guarantee userspace recovery.

No handshake, additional observer, installed startup edit or replacement
recovery policy is introduced here. The next integration review must address
these concrete source findings together; the seven characterization cases do
not satisfy Phase B's real integration failure tests. Build-36 Busy/raw-2 data
still does not distinguish pending/invalid or confirm preparation-stage origin.

## Local verification, 2026-11-14

Source commit `de9051fa75385ef285654645999c8686b334b7a7` passed all **504
Python tests** in 217.994 seconds, including the six new startup-audit tests
and the strengthened late-baseline observer assertion. Recorded source hashes
and HEAD were unchanged; the checkout was clean before and after the run.
The seven source-fragment subprocess scenarios were also run directly from
that committed source and their private report read back. A passing harness
means the reference exhibits the characterized behavior, not startup acceptance.

The source commit's remote ref/tree/parent and all five changed files were
independently verified. Automatic full-stack run `43491822779` was cancelled
and is not a build pass. The [validation record](validation/allocation-startup-audit-20261114.json)
separates source characterization, static handler/argument review and installed
helper file observations. No native target binary was built locally or run,
and no target service, installed startup, GPU workload, arming or reboot was
used for this audit. Native delivery, target reads and the actual allocation
root cause remain unresolved.

## Retained helper identity follow-up, 2026-11-14

The private installed initializer copy is byte-identical to
`tools/phxctl/full.sh` at historical commit
`3f9a957b6f9abb8406d7ee3828551414e6a0143d`, Git blob
`5b660391e9a9765bdcaa36438667eb3c0aaaf9ad`. Both the local blob identity and
the remote file at that exact commit were independently checked. This supplies
matching historical source for the initializer. It does not establish how or
when that file was installed, which helper binary was built with it, or which
bytes executed during the failed boot.

A bounded read-only search inspected 16 named file candidates (seven retained
initializer source copies, seven guarded test fakes and two retained
compile-only binaries), the named regular members of 14 explicitly enumerated
archives, and ten initializer-history commits. No installed mesboot byte match
was found in that scope. Eleven external-dependency source archives and named
excluded directories were skipped; 18 nested archive members were not
recursively unpacked. This is a scoped negative result, not proof that no
matching package exists. Fifteen retained JSON records for each helper contain
its current hash; those are historical file observations, not build manifests
or execution attestations.

Static disassembly of the retained installed mesboot copy provides evidence
stronger than string absence for two specific paths: `_rd` initializes a read
output, calls `IOConnectCallMethod`, then returns the output without checking
the transport result or reply size; `_wr` calls `IOConnectCallScalarMethod`
without checking its transport result or reply count. The claim command prints
the returned status and then continues command dispatch without an immediate
status-dependent refusal. These are static control-flow observations only;
the binary was not executed, and its exact corresponding source/build remains
unestablished. They do not prove that a transport failure occurred or caused
the build-36 allocation refusals. The current source's checked transport and
explicit-layout protections must remain intact.

The [follow-up record](validation/allocation-helper-provenance-20261114.json)
keeps these evidence levels separate. No production source changed and the nine
recorded source hashes from the 504-test run still match; that suite was not
rerun for this documentation-only follow-up. Exact binary provenance, native
delivery, passive target evidence and independent recovery remain open gates.
