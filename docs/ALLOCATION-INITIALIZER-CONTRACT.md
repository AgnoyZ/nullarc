# Allocation initializer interface review

Status, 2026-11-14: **source and fake-I/O characterization only**. This is not
an installed initializer, a native binary delivery, startup acceptance or a
new target execution grant. The allocation root cause remains unconfirmed.
The [execution plan](ALLOCATION-EXECUTION-PLAN.md) and its Phase A, recovery and
fresh-authorization gates remain in force.

## Current entrypoints do not form a complete initialization chain

The current `tools/phxctl/mesboot.c` dispatches `gart` and `mes` to commands
requiring the same four explicit GART layout arguments. Each uses
`open_kext(1)`, which derives addresses from the published carve-out and
rejects the legacy reference override. The later command path containing
`claim` and `kiqsched` instead calls `open_kext(0)`: the published addresses
must match the compiled reference layout unless the old override is set.
Separate helper processes do not inherit the globals changed by an earlier
explicit command. A reviewed explicit GART/MES call therefore cannot make a
later legacy claim compatible with a different published layout.

The new full-entrypoint fake-I/O tests establish the following, without
changing any production code or weakening either layout gate:

| Invocation with synthetic registry/transport | Observed current-source result |
| --- | --- |
| Relocated layout, `claim` or `kiqsched` | Exit 1 after HELLO and close; no claim, bootstrap snapshot, register/memory operation or queue adoption |
| Missing layout, `claim` | Refusal before the claim selector |
| Relocated layout, explicit `gart` or `mes` | Reaches selector 116; the fixture deliberately refuses that read, producing exit 74 before register/memory activity |
| Bare `gart` or `mes` | Exit 64 before service lookup |
| Reference-layout fixture, failed claim transport | Exit 74 from the actual checked selector-113 call; no successful claim message |
| Failed/short/long HELLO or incompatible ABI | Stops before claim |

The reference-layout positive control returns a **fake** successful claim.
It tests current userspace dispatch and status propagation only. No kernel
claim or GPU readiness was exercised. In the actual kernel source,
`PhxBringup::claimAccel()` refuses when PCI or `gpuReady()` is absent before
publishing the claimed property and re-registering the service. That guard
must remain; neither a fake result nor a MES activation-register check proves
the queue/adoption prerequisites of a display attempt.

`sched-query`, `compute-probe` and `shader-probe` already use explicit layouts
and reject legacy experiment overrides. They are separate execution scopes:
their published success limitations do not establish a display-ready adopted
graphics queue or a complete replacement for the legacy initialization
chain. No such command was run on a target in this review.

## Actual stage executor: failure propagation and recovery limits

The tests also run the actual `tools/phx_boot_gate.sh` with synthetic
`uname`/`ioreg`, the compiled fake-I/O mesboot entrypoint as a claim stage, a
later file-writing sentinel and a file-writing release fake. There is no
firmware initializer, installed monitor, hold-release command or display
command in that fixture.

For the relocated-layout refusal and the checked claim transport failure,
the gate retains stage statuses 1 and 74 in `results.txt`, exits 77, skips
the later sentinel and runs its release fake. The positive control tests
that the same actual gate can reach the sentinel when the fake claim returns
zero; that is not admission or GPU readiness.

A separate process/FIFO case blocks inside the fake claim transport. With
the actual claim stage waiting, the pending marker exists and neither the
later sentinel nor the release fake has run. After the fixture FIFO is
released, the stage completes and those hooks run. An explicit FIFO is used
because a non-interactive shell background stage normally receives empty
standard input. This characterizes the actual executor's synchronous release
dependency, not a GPU/kernel hang or an independent recovery mechanism.

Source review confirms that this gate waits for its stage before cleanup
invokes the release hook. Its userspace timeout does not establish progress
for an uninterruptible kernel call. It also removes the pending marker after
a handled failure: that existing behavior must not be mistaken for durable
consumption of a single-use display grant. This review changes neither the
executor, its return codes, its timeout nor AGDC's asynchronous scheduling.

## Requirements for a concrete replacement candidate

Use the existing explicit-layout contracts for GART/MES; do not call bare
legacy bootstrap commands, add the reference override, suppress a refusal
or replace checked transport with filtered text. Every process must receive
the reviewed layout and preserve its own target/layout verification.

A complete candidate still needs a reviewed queue initialization/adoption
and claim interface for that layout, with explicit success and failure
propagation before display setup. Merely changing the claim call to use an
explicit open would not establish those prerequisites. Keep kernel readiness,
VM guards, budgets, pin direction, resource retention and cleanup intact.

The [queue-readiness evidence review](ALLOCATION-QUEUE-READINESS.md) now
exercises the actual adoption, aggregate readiness, claim and bootstrap
export methods with CPU-only fakes. It demonstrates that compute-only,
graphics-only and both-queue states can export identical activity metadata;
that aggregate result cannot certify a selected graphics queue. The review
preserves the existing claim guard and bootstrap active-queue refusal.

Recovery must already be available under a separate reviewed owner before
baseline or initialization, without depending on stage completion, observer
acknowledgement, kill/reap or this executor's release callback. The legacy
initializer's watchdog/global shutdown-process kill cannot own that recovery.
No new recovery threshold, reset, teardown policy or rearm is introduced here.

The outer admission still needs the actual same-boot completed baseline,
identity/hash and retained-capacity checks, a durable one-attempt decision,
and the exact skip/fallback path required by Phase B. These entrypoint and
executor tests cover a specific compatibility boundary; they do not satisfy
the remaining observer, service/boot replacement, deadline, exhaustion or
independent-recovery integration cases.

## Reproduction and evidence limits

`tests/test_mes_entrypoint.c` includes the complete current `mesboot.c` and
implements every IOKit entrypoint with test-only functions. The test is
compiled with fake headers and AddressSanitizer/UndefinedBehaviorSanitizer,
without an IOKit/CoreFoundation framework link. All non-HELLO/claim/snapshot
transport paths abort the fixture rather than performing target operations.
The explicit snapshot is an intentional terminal refusal, not fabricated
bootstrap completion.

`tests/test_mes_layout_gate.py` adds nine test methods: thirteen direct CLI
processes and four compositions with the actual shell gate. The existing
function-level twelve-case layout test is retained separately. Run this
focused file using Python unittest discovery; do not execute installed or
reference startup scripts. These offline results cannot identify which bytes
ran at the old failure, distinguish pending/invalid, or assign raw-2 to the
host preparation stage.

## Local verification, 2026-11-14

Source commit `da0e89ed312bc969db537e958a326a87b8ae01a8` passed all **513
Python tests** in 246.315 seconds, with no skipped tests. The checkout was
clean before and after the run, HEAD was unchanged, and all sixteen recorded
input hashes still matched. The focused file separately passed ten test
methods, including its nine new full-entrypoint/composition methods.

The source commit's remote ref, commit/tree/parent and all five changed files
were independently verified after exact-object REST fast-forward with
`force=false`. Automatic full-stack run `43496254644` is
`completed/cancelled`, not a build pass. The
[validation record](validation/allocation-initializer-contract-20261114.json)
separates actual userspace entrypoint/gate tests, static kernel review and
unproven target/recovery claims. No native target binary, installed startup,
target service, GPU workload, arming or reboot was used for this review.
