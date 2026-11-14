# Allocation queue-readiness evidence contract

Historical characterization of the pre-build-38 claim policy. The subsequent
[build-38 correction](DESKTOP-CLAIM-FIX.md) requires both adopted engines
before claim; the aggregate activity predicate and the evidence limitations
below are unchanged. The table's successful single-engine claims describe
the old source, not the corrected candidate.

Status, 2026-11-14: **actual-source CPU characterization with fake memory,
locks and PCI publication only**. The allocation root cause remains
unconfirmed. No production method, ABI, layout guard or claim policy changes
are proposed here. The [execution plan](ALLOCATION-EXECUTION-PLAN.md) and
[initializer interface review](ALLOCATION-INITIALIZER-CONTRACT.md) retain
their Phase A, independent-recovery and fresh-authorization requirements.

## Adoption establishes software state, not device completion

The current `PhxBringup::adoptQueue()` validates numeric queue geometry,
mapped resources, PSP-region separation and separation from the other ready
queue. It takes the GPU then SMU lock, initializes the selected queue, writes
the current `gSeq` into its fence through the CPU aperture, calls `hdpFlush()`
and sets `q.ready`. It does not itself initialize or read back HQD, GART or
MES state, nor submit and verify a GPU completion. The initializer must
establish the prerequisites of the queue it asks the kernel to adopt.

The new zero-submission fixture starts with `gSeq == 0`. Actual adoption
writes a zero fence, leaves the submission history empty and permits the
actual readiness/claim path under the fake resource setup. This is evidence
that these software results can exist without a supplied GPU completion;
it does not show that any real device is ready or that a real claim succeeds.

## Aggregate publication loses queue identity

The actual `gpuReady()` predicate is
`!stopping && (gq[0].ready || gq[1].ready)`. Actual `claimAccel()` requires PCI
and that predicate, then sets the claimed property and re-registers the
service. The guard must remain. It does not select a requested engine.

Actual `bootMemory()` uses the same predicate for `PHX_BOOT_GPU_ACTIVE` in
its 128-byte software snapshot. It carries no individual queue identity.
Using otherwise identical, valid synthetic bootstrap metadata produces:

| Adopted queue state | `gpuReady()` | Fake PCI claim | Bootstrap export |
| --- | --- | --- | --- |
| Neither | false | Not ready | GPU-active bit clear |
| Compute only | true | Success | GPU-active bit set |
| Graphics only | true | Success | GPU-active bit set |
| Both | true | Success | GPU-active bit set |

The compute-only, graphics-only and both-queue exports are byte-for-byte
identical in the fixture, despite different adopted queues. Missing PCI
still refuses claim even when the aggregate predicate is true.

The actual `phx780m::queueIndex()` header still refuses graphics selection
from a compute-only state and compute selection from a graphics-only state.
Static review of `gpuSubmit()` confirms it uses that selector under the GPU
lock and checks `stopping` before submission. The fixture executes the header,
not `gpuSubmit()` or GPU work. Static review of `doQueryInfo()` also finds the
aggregate predicate behind `PHXN_INFO_S1B_POSITIVE`; that flag is not an
independent per-engine readiness measurement.

## Bootstrap arithmetic and retained history are different evidence

`phxGartLayoutValid()` requires flags exactly equal to configured, ring-active
and TMR-active. The fixture verifies that otherwise-valid metadata with the
GPU-active bit is rejected. This is a pre-initialization arithmetic gate,
not a post-adoption verifier. Preserve its active-queue refusal; reusing or
weakening it cannot supply the missing queue evidence.

A separate fixture injects `stopping = true` while keeping an adopted
queue's ready bit. The actual predicate clears the aggregate activity and
claim refuses, while the bootstrap export can equal the pre-adoption export
and pass the arithmetic validator. This tests the injected predicate only.
It does not execute `stop()`, teardown or concurrency. Static `stop()` review
shows that active resources take the quarantine/retention path, so a clear
aggregate activity bit must not be treated as permission to reclaim them.

`copyAllocationSnapshot()` copies retained allocation history under the GPU
lock. Queue observations in a refusal record describe that recorded event;
they are not a fresh, atomic admission for a later claim. This source review
does not add a reader or change the allocation-history wire format.

## Reproduction and consequences for a replacement initializer

`tools/test_queue_adoption.py` extends the existing actual-method harness.
It exports a clean committed tree with the existing `prepare()` guard and
extracts the exact `GpuQueue`, `adoptQueue`, `gpuReady`, `claimAccel` and
`bootMemory` fragments. Missing or duplicate fragments are refused; the
report binds them and seven source/test inputs with SHA-256. The harness uses
the actual queue-selection and bootstrap arithmetic headers and compiles
with AddressSanitizer and UndefinedBehaviorSanitizer. It has 73 retained
adoption cases and eight new readiness cases. No kernel/framework link or
target service is used.

The first direct CPU precheck failed because the new bootstrap fixture used
a TMR offset that did not satisfy the existing 1 MiB base alignment. Only
the new readiness fixture was corrected; the original 73 fixtures and all
production checks were retained. The corrected direct precheck passed all
81 cases. That precheck is separate from the clean-export unit/full suite.

A concrete explicit-layout initialization/claim candidate needs evidence for
the selected engine, the initialized/adopted queue and its prerequisites,
with lifecycle and identity bound to the same attempt before display setup.
The current aggregate flag, fake PCI success, CPU-written fence, arithmetic
snapshot or retained refusal record cannot substitute for that evidence.
This review identifies the contract gap; it does not design a new ABI,
weaken readiness, authorize a probe or prove hardware idle.

Native candidate/reader delivery, two same-boot Phase A passive reads,
separately owned recovery and durable one-attempt admission remain open.
The installed mesboot's exact source/build remains unknown. No result here
distinguishes pending from invalid in the old failure or attributes raw-2 to
host preparation. No deployment, target service open, GPU execution, arming
or reboot occurred.

## Local verification, 2026-11-14

Source commit `fe2992f8a875204d30459227d5143b07fa7a9c8e` passed **516 Python tests**
in 285.129 seconds, with no skipped tests. The separate focused
file passed eight methods, including three new methods and all 81 internal
actual-method cases. Both runs began and ended with a clean checkout; HEAD
and all twelve recorded source/test input hashes remained unchanged.

The source commit's ref, commit/tree/parent and all five changed files were
independently verified after exact-object REST fast-forward with
`force=false`. Automatic full-stack run `43500555300` is
`completed/cancelled`, not a build pass. The
[validation record](validation/allocation-queue-readiness-20261114.json)
separates executed CPU fakes, static-only source findings and unproven
hardware, recovery and root-cause claims.
