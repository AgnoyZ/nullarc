# Allocation initialization-to-adoption handoff review

Status, 2026-11-14: **source and fake-I/O control-flow evidence only**. This
review does not identify the old allocation failure's root cause or authorize
an initializer, target read, GPU workload or restart. The
[execution plan](ALLOCATION-EXECUTION-PLAN.md) and its native-delivery, Phase A,
independent-recovery and fresh-execution gates remain open.

## Actual caller inputs and prerequisites

`sched_test()` initializes the scheduler and sends its resource/query packets,
then calls compute followed by graphics when both environment switches are
enabled. Each selected helper checks its own execution markers before its
optional selector-112 adoption. These are legacy fixed-layout experiments;
the [entrypoint review](ALLOCATION-INITIALIZER-CONTRACT.md) already establishes
that they cannot simply follow a relocated explicit-layout bootstrap.

The new fixture calls the actual current `sched_test()` with both switches
and both adoption switches enabled. Fake IOKit records each six-scalar request
without replacing the helper's calculations:

| Queue | Ring offset / dwords | Writeback | Doorbell bytes | Initial write pointer | Fence offset with queue bit |
| --- | --- | --- | --- | --- | --- |
| Compute | `0x2540000` / 1024 | `0x2541000` | `0x18` | 8 | `0x2550000` |
| Graphics | `0x2570000` / 2048 | `0x2574000` | `0x458` | 968 | `0x2580001` |

The graphics pointer includes the current 960-dword clear-state preamble and
eight test-packet dwords. The fixture clears `NO_CSB`; its 968 value is not a
new kernel ABI requirement for other callers. The final scalar's low bit
selects graphics and is removed before interpreting the fence offset.

Compute requires both its expected scratch value and test-memory write;
graphics independently requires its scratch and memory values. MES submission
checks its full-width fence and completion token. The fixture injects those
observations; it does not emulate or verify packets, hardware retirement,
ownership or a real queue transfer. A successful fake adoption reply is a
transport result, not execution of `PhxBringup::adoptQueue()`.

## A concrete partial-initialization failure survives the old filters

The previous separate tests established checked helper failures, shell status
masking and aggregate kernel readiness. The new composition ties them to
the actual two-engine helper sequence, rather than inventing an initializer
that merely returns an arbitrary failure code.

After compute has received its fake successful adoption reply, an injected
graphics timeout, wrong scratch value or wrong memory value causes actual
`gfx_via_mes()` to exit 75. No graphics adoption follows and no later scalar
write occurs. A refused compute or graphics adoption reply causes the actual
checked transport to exit 74. A first adoption refusal prevents the later
graphics setup. These existing production failures are preserved.

The harness then separately runs the same fake-I/O helper through the exact
`tail -12` suffix extracted from `full.sh` and the exact
`grep -E "^compute:|^gfx:|adopt"` suffix extracted from `phxboot.sh`. It uses
ordinary Bash pipeline status, with inherited shell startup/options removed.
Neither startup script is executed. A file-free test hook records a claim
request only if the resulting pipeline status is zero:

| Injected helper outcome | Actual helper exit | Adoption requests / fake successes | Filter status | Claim hook |
| --- | --- | --- | --- | --- |
| Both queues pass | 0 | 2 / 2 | 0 | Requested |
| Any of three graphics execution failures | 75 | 1 / 1 | 0 | Requested |
| Compute adoption transport refuses | 74 | 1 / 0 | 0 | Requested |
| Graphics adoption transport refuses | 74 | 2 / 1 | 0 | Requested |

The retained compute/adoption output satisfies the filters even when the
graphics stage failed. The hook is deliberately conditional on a successful
filter; the actual boot source's later claim is not even guarded by that
condition. No kernel claim or display command is executed in this fixture.

The [actual-kernel-method CPU review](ALLOCATION-QUEUE-READINESS.md) separately
shows that the current claim guard permits a compute-only software state.
Together, these source results identify a route by which partial graphics
initialization is insufficiently excluded before claim. They do not prove
that this route occurred on the old boot. In particular, the no-successful-
adoption case would still face the unchanged kernel readiness guard; requesting
a claim is not proof that it would succeed.

## Resource lifetime still exceeds the six-scalar interface

The concrete helpers also use the compute MQD/EOP at `0x2542000`/`0x2543000`,
graphics MQD/clear-state storage at `0x2575000`/`0x2576000`, test storage at
`0x2520000`, the scheduler's four pages starting at `0x2510000`, KIQ storage
starting at `0x2500000`, and the legacy GART table starting at `0x2400000`.
These are source constants, not discovered target reservations.

The existing kernel adoption method checks ring/writeback/fence extents,
PSP regions and the peer queue's recorded extents/doorbell. Its queue record
does not own the MQD/EOP, GART, scheduler, clear-state or KIQ regions. It cannot
establish exclusive producer ownership or prevent independent raw-debug writes.
This audit introduces no new reservation or teardown policy and demonstrates
no actual collision between the listed default constants. The framebuffer's
system-memory descriptor pool is not a VRAM-offset allocator for these queue
constants; its name alone is not evidence that it allocates over them.

## Consequence for the candidate and evidence boundary

A replacement chain must preserve the actual initialization/adoption status
for every required engine before claim, and bind its selected queue and
associated resources to the same owned attempt. A text filter, aggregate
activity bit or successful compute stage cannot stand in for graphics success.
Merely adding `pipefail` would not establish that ownership or supply the
missing explicit-layout graphics/adoption interface and independent recovery.

`tests/test_bringup_transport.c` and `tools/test_bringup_transport.py` retain
the existing 52 transport, 20 completion and 16 submission cases and add six
two-engine cases plus six exact-filter compositions. The runner validates
request scalars, fake results, polling, terminal codes and absence of later
writes. Four unit methods add case/parser/filter checks and execution of the
actual C harness. Missing, duplicate or changed filter lines fail closed.
No generic readiness model, production source change or new ABI is added.

The installed mesboot's exact source/build remains unknown. These tests
cannot separate pending from invalid in the retained Busy observations or
assign the old raw-2 import result to preparation. Obtaining that evidence
still requires the reviewed build-37 kernel/reader delivery, a usable separate
recovery route and a newly authorized Phase A scope. Existing one-shot grants
remain consumed.
