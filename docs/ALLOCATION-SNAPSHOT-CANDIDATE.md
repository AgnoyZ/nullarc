# Allocation refusal software snapshot candidate, build 37

This uninstalled diagnostic candidate follows the [build-36 reproduction](ALLOCATION-KERNEL-DIAGNOSTIC.md).
That failed boot retained native refusals but no candidate `PhxAlloc` kernel
records. Its underlying retirement branch and host-import stage remain
unconfirmed. This change provides another evidence channel; it does not fix
allocation, prove a hang, or establish that video memory was exhausted.

The separate [pre-fallback capture source candidate](ALLOCATION-CAPTURE-CANDIDATE.md)
adds private baseline/failure persistence and same-boot identity checks. It is
not installed or connected to the existing monitor.

## Bounded service storage

`PhxBringup` owns one zero-initialized, 3,888-byte software history protected by
its existing GPU lock. Seven categories each retain their first four records:
MAP pending retirement, MAP invalid retirement, UNMAP pending retirement,
UNMAP invalid retirement, MAP pending overlap, host descriptor failure, and
host preparation failure. Each category and the aggregate have saturating
64-bit occurrence counters. Later refusals increment those counters without
overwriting the first records or allocating storage. These counters are
independent of the unchanged per-context/per-client IOLog sampling limits.

VM guards copy the exact observation already used to return Busy, under the
same lock. No additional fence read, retirement observation or MMIO is added.
An early invalid queue leaves later queues unobserved. The existing queue
reason numbers are explicitly fixed at 0..14 for this snapshot version.
Import records distinguish descriptor creation from `prepare()` and retain
the unmodified native status, including raw Mach 2. They do not identify page
origin or permissions. Import and overlap records carry size; guard records
carry sequence/queue observations. Reserved and inapplicable fields are zero.

History belongs to the service, not a native client or reusable VM context.
It survives WindowServer client closure while that service remains alive;
it does **not** survive a reboot, service replacement or fallback boot.
There is no reset control. The first records may predate a later reproduction;
future authorized collection must establish an initial snapshot and collect
again in the same boot, before fallback. Counts include internal reaper UNMAP
guard calls and repeated attempts, not unique API requests or RADV samples.
Only the listed refusal sites are counted. This is not an all-error census.

No pointers, task/PID/context/BO identifiers, virtual/physical addresses,
page contents or machine identifiers enter the wire structures. Ordinals
describe service-local recording order and saturate with the aggregate count.

## Passive export contract

Optional selector 31 uses an independent version handshake: one scalar input
equal to `PHXN_ALLOCATION_SNAPSHOT_VERSION` (1), no structure input or scalar
output, and exactly 3,888 bytes of direct structure output. Memory-descriptor
transport is rejected. Existing ABI 1.12 selectors and layouts are unchanged.

The dispatcher routes selector 31 before the normal Hello/reaping path,
including malformed and denied requests. It intentionally works before
Hello, requires the existing administrator privilege flag, rejects closed
clients and absent owners/locks, and copies only stored software data. It
does not call Hello, QueryInfo, `reapPending`, `vmUnmap`, retirement, GPU
initialization, queue adoption, submission, MMIO or a fence accessor. It does
not depend on the debug boot argument. Lock order remains client lock then
GPU lock; guard writers already hold the GPU lock, while import/overlap writers
acquire it through a small service wrapper. Export can wait behind another
GPU-lock holder, so it is not guaranteed to be nonblocking. Recording and
copying can perturb timing despite their fixed memory bounds.

`tools/allocation_snapshot.cpp` is a separate one-request reader. It opens the
existing native service, sends only selector 31, closes, validates the reply,
and emits JSON. It has no polling, reset or GPU operation mode. Opening and
closing still use the ordinary native-client lifecycle: software allocations,
session claiming/releasing and possible lazy sysctl registration. The reader
creates no VM context or BO, so its fresh-client close has no GPU resource to
reap. The new selector itself is passive; this is not a claim that all service
lifecycle bookkeeping is side-effect-free. The reader has not been run against
the target. An old driver may refuse the unsupported request; refusal is not
an empty snapshot or diagnostic evidence.

## Validation and execution boundary

`tools/test_allocation_snapshot.py` extracts the actual dispatcher, snapshot
handler, shape check, service record/copy wrappers, build constant and history
declaration. Its CPU harness uses explicit lock/lifecycle/privilege fakes and
ASan/UBSan. Thirty checks cover exact shapes, null arguments, descriptors,
unsupported versions, privilege, pre/post-Hello access, closed/absent owners,
absent service lock, independent category capacity, client turnover, stable
repeated reads, zeroed output and counter saturation. Seventeen additional
cases compile the actual reader against fake IOKit: exact one-selector calls,
JSON decoding, raw codes, unknown/unobserved queues, length/version/count and
record rejection, transport/close failures and argument rejection.

The allocation diagnostic harness now has 44 cases. It checks stored fields
at actual refusal branches, the same single fence observation, counters after
IOLog caps, first-record retention after context log-budget reuse, raw import
codes and unchanged success/cleanup paths. These are CPU contract tests, not
real kernel persistence, concurrency stress, page wiring or GPU validation.

On 2026-11-14 the local focused pass completed all 30 snapshot checks, 17 reader
cases, 44 allocation diagnostics, 72 dispatcher cases, 30 BO-create/import
cases, and seven allocation-runner unit tests. ASan/UBSan reported no failure.
This precedes the clean-commit regression and hosted native compile.

The manual `kernel-compile-check.yml` builds the reader without running it,
and compiles/links/signs PhxBringup only on hosted `macos-15-intel`. It publishes
no binaries. Local native driver builds, installation and target execution
are outside this source change. Hosted results are recorded separately after
the exact committed candidate is tested.

The first source commit, `925fd1d`, passed the scoped hosted kernel/reader
compile in run `43462656741`. Its automatically triggered priority workflow
`43462507687` passed the Ubuntu host-contract job but failed the Intel isolated
wait-model fixture: the new optional header had been included transitively by
the base ABI header, while that fixture copied only the old ABI dependencies.
The correction removes that unnecessary include and includes the optional
header directly in the dispatcher test. The base ABI header is byte-identical
to the pre-candidate version. This is an include-dependency repair, not a GPU
behavior change. The cancelled automatic full-stack run `43462507811` is not
a full-stack build pass. Corrected-commit results are recorded separately.

## Verified corrected source, 2026-11-14

Source commit **`1c17a1712cb3a64db31148cb33d0c2c9741e7e5d`** passed
all 421 local Python tests. A clean-commit replay also passed 30 snapshot
checks, 17 actual-reader cases against fake IOKit, 44 allocation diagnostics,
72 dispatcher cases, 30 BO-create/import cases, 82 BO-retirement cases,
112 context-retirement cases, 86 queue-retirement cases, 71 VM-binding cases,
98 page-table cases and 55 page-walk/cleanup cases. The isolated legacy wait
model also passed 20 CPU replays. These host harnesses use ASan/UBSan.

Corrected-source Priority run **`43463408809`** passed both Ubuntu host
contracts (job `132016047431`) and Intel native components (job
`132016046472`), including the previously failing isolated fixture and the
existing native component compilation. It uploaded no artifacts.

The corrected scoped run **`43463527011`, attempt 2**, passed on
`macos-15-intel` (job `132026834880`). It passed the 44 allocation diagnostics,
30 snapshot checks and 17 fake-reader cases, compiled the actual standalone
reader without opening a service, and compiled/linked/signed PhxBringup. Strict
signature verification, x86_64 verification and source integrity checks passed.
The hosted input hashes match the reviewed source; artifact count is zero.
Attempt 1 failed before any steps ran because GitHub could not acquire a
hosted runner. It was not a compiler failure, was not cancelled by this work,
and is not counted as a pass. The same job/source was rerun once. Automatic
full-stack run `43463409087` was cancelled and is not a full-stack pass.

The [machine-readable validation record](validation/allocation-snapshot-build37-20261114.json)
keeps the source identity, input hashes, test counts, run history and limits.
No candidate was installed or loaded on the target, no service snapshot was
collected from the target, and no GPU work, arming or reboot occurred in this
source-validation phase. The actual allocation root cause remains unresolved.

The consumed build-36 M2/reboot grants are not reusable. This candidate does
not authorize arming, startup changes, installation, initialization, GPU work,
desktop takeover or another reboot. Existing safety gates, budgets, pin
direction, cleanup, resource retention and native return codes are preserved.
