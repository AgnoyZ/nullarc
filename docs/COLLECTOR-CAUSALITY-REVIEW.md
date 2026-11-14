# Collector causality review

Status, 2026-11-15: **offline evidence and CPU tests only**. No production
driver change, target service call, initialization, arming or reboot occurred.
The [consumed desktop retest](DESKTOP-RETEST.md#target-result-and-recovery)
still failed at its first selection; desktop takeover and acceleration remain
unproven.

## What the old records establish

The 2026-11-13 [selector result](validation/gc-power-selector-target-20261113.json)
already reports an immediate zero and a subsequent zero for a requested
VMID-only selection of 16. This review independently reparses the retained
native CLI write/read outputs and terminal runtime state. All 13 files in
the original private session manifest still match their recorded sizes and
SHA-256 hashes; the plan, runtime and manifest share the same historical boot
identity. The observer diagnostic identifies bring-up build 34.

The source recorded for that deployed candidate,
`c5c22b420aa8990eff90df4cbddd29815793ecf6`, defines build 34 and contains neither
the allocation-snapshot handler nor its selector dispatch. The new software
history/export mechanism was added in build 37 at
`925fd1d1e4c8eca5bf7ad0dc2ad4dfe7424fc087`, a later descendant. Thus reported
dual-zero behavior predates that mechanism. Attribution of every historical
zero solely to the new allocation-snapshot collector is not supported.

This is chronology, **not a collector-free causal control**. The old installed
CLI did not check the returned scalar count, as the existing
[transport qualification](validation/gc-access-audit-20261113.json) discloses.
The old printed zero is not a new proof of a complete reply shape. Other
register observers were active, and the builds, boots, native clients and
power conditions differ. The source identity is the historically recorded
candidate identity; this review does not inspect live kernel memory. These
limits prevent excluding observer effects on either physical test.

In the latest build-39 retest, both zeros are already in native stderr before
summary processing. The allocation reader sends a separate software-history
request; it does not produce those register readbacks. Its successful empty
baseline means no listed allocation refusals were stored at that moment,
not that the selector or GPU was healthy. No failure snapshot was recorded.

## Full snapshot-client lifetime coverage

Earlier tests covered the real dispatcher/store and real reader separately,
with lifecycle flags or IOKit Open/Close faked. The new
`tools/test_snapshot_lifecycle.py` joins them in one CPU harness. It extracts
the actual provider `newUserClient`, session claim/release and snapshot-copy
methods, and the actual client init/start, default state, dispatcher, snapshot,
`freeAll`, resource close, client close and destructor methods. It also uses
the production BO/container/Map declarations and unmodified reader source.

Sixteen ASan/UBSan scenarios cover empty/populated histories, an already-open
session, a foreign desktop reservation, privilege refusal, missing service
lock, object/base-init/lock/storage/maps/attach/start failures, destructor-only
cleanup, repeated close and successive readers. They check balanced software
allocation/free, first-client sysctl registration, lock ordering, unchanged
history and foreign reservation, and preserved session ownership. Entering
GPU context allocation/retirement, BO cleanup, the normal pending reaper,
desktop abandonment or mutation locking aborts the harness.

All sixteen pass. Three temporary mutations also compile and are caught at
runtime: a fresh client starts with a VMID, close unconditionally abandons the
desktop, or snapshot routing falls through to the normal dispatcher. The
mutations change private extracted copies only. Existing snapshot tests now
run this integrated harness automatically, including existing workflow entry
points; the extraction checks also prevent single-line session functions
from accidentally consuming their following methods.

There are **49 passing focused Python test methods** across snapshot runners,
context runners, desktop handoff and register transport, plus 30 snapshot,
17 reader, 16 integrated-lifecycle and 115 actual context-retirement CPU cases.
These counts describe different test layers, not additional hardware tests.
The first context-runner setup correctly refused the dirty development
checkout. Its six methods and 115 cases then passed in a clean detached
worktree at the unchanged production baseline; the initial 43 passing methods
and the refused setup are retained separately. The full suite was not rerun.

These OS and locking fakes cannot validate kernel object lifetime, scheduling,
contention, timing, physical MMIO, installed binary identity or GPU acceptance.
They find no demonstrated fresh-client cleanup route that explains the zeros;
they do not prove the live observer cannot interfere. The
[validation record](validation/collector-causality-review-20261115.json)
contains hashes, exact scope and qualifications.

## Remaining boundary and rollback

The native access path, physical readback semantics, power/access state and
initialization prerequisites remain unresolved. This review supplies no basis
for bypassing the selector guard, treating it as write-only, changing register
bases or applying a speculative driver patch.

Installed drivers/helpers, startup, collections, EFI, security settings and
all consumed requests remain unchanged. Raw records, private paths/identities,
CPU binaries and mutation outputs stay ignored. Revert these tests/docs in a
normal new commit to roll back this change; preserve historical receipts.
Continue offline analysis under the closed request. A further physical
experiment requires a distinct reviewed request with a fresh boot and
independent recovery; this review does not create or arm one.
