# Reject incomplete engine handoff before accelerator claim

Status, 2026-11-14: **build-38 source candidate; not installed or hardware
validated**. This corrects a reproducible admission defect on the desktop
startup path. It does not establish the cause of the earlier WindowServer
allocation failures or a working accelerated desktop.

## Defect and correction

`PhxBringup::gpuReady()` means at least one adopted queue is available. That
predicate is appropriate for single-engine native experiments and aggregate
activity reporting. The old `claimAccel()` also used it to publish
`nmxgpu-claimed` and request PhxAccel matching. Consequently, compute-only or
graphics-only initialization could publish the full accelerator even though
`gpuSubmit()` still refuses work for the missing engine. The
[queue-readiness characterization](ALLOCATION-QUEUE-READINESS.md) and
[two-engine helper review](ALLOCATION-QUEUE-HANDOFF.md) identified this gap;
neither establishes that it occurred on the failed target boot.

Build 38 retains PCI and aggregate readiness checks, requires `gpuLock`, and
checks both adopted queue bits while holding that lock. An incomplete or
stopping state returns `kIOReturnNotReady` before setting the PCI property or
requesting matching. Matching runs after releasing the lock, so the claim
does not call the matching machinery under the GPU lock. The existing
`gpuReady()`, bootstrap flags and single-engine native experiments retain
their previous meanings.

This is a coherent software readiness observation, not a transactional
claim/stop lifecycle or proof of device completion. Queue adoption still
relies on the initializer to establish hardware prerequisites and ownership;
two CPU-published ready bits alone cannot certify HQD, GART, MES, rendering
or safe display release. No ABI, queue layout, VM guard, allocation budget,
pin direction, cleanup rule or recovery threshold changes.

## Regression contract

The actual-method harness preserves the 73 adoption cases and eight
readiness cases. Its single-engine cases now require claim refusal while
still checking their unchanged activity exports. Seven additional claim
cases cover reverse adoption order, refusal of either second engine,
missing PCI or GPU lock, both queues retained while stopping, and an injected
stop at lock acquisition. Refusals must publish no claimed property and
request no matching. Cases compare queue records, framebuffer/doorbell
bytes, aperture accesses and flush counts before and after claim. Fake locks
also verify balanced locking and matching outside the GPU lock.

Before the correction, five selected regression cases failed against the
old actual methods: compute-only, graphics-only, refusal of either second
engine, and stop at claim lock acquisition. These are CPU assertions with
fake memory, locks and PCI publication, not reproductions of a GPU fault.

The historical build-37 source exporter keeps its original review pin and
version gate. Its temporary test repository supplies a synthetic review commit
and explicitly sets its positive fixture's build number to 37; this does not
review the current kernel or require historical Git objects in shallow CI
checkouts. A new negative test verifies that build 38 cannot reuse that review,
even when the synthetic fixture's review commit is changed. The production
exporter is unchanged. Retained build-37 packages and rollback inputs are not
updated or relabelled.

## Validation and target boundary

Source commit `33fafc26998a384e6c33170c8dd03ef12e076219` passed all **524 Python
tests in 305.083 seconds**, without skips, on Python 3.13.18. All **815 tracked
input hashes** matched before and after the run, and the checkout remained
clean. The full suite includes the actual-method queue harness; a separate
working-tree precheck passed all **88 ASan/UBSan queue/readiness/claim cases**
and all **17 source-exporter tests**. The precheck's kernel hash matches the
committed source.

An isolated clean source export compiled and linked PhxBringup on the local
Apple Clang 21.0.0 toolchain with host SDK 26.5. All 1,232 cached MacKernelSDK
files matched the official pinned Git tree, including its exact file set.
Six native build/verification commands passed, including strict ad-hoc
signature verification and the x86_64 architecture check. Compilation emitted
three shadow-declaration warnings at statements also present in the parent
source; those unrelated statements were not changed. The private build-38
executable is 116,080 bytes; its hash and sanitized results are retained in
[the validation record](validation/desktop-claim-fix-20261114.json). No binary
was uploaded.

The real build-37 exporter also refused this committed build-38 source before
creating output. The source push and its exact remote SHA/tree/parent were
independently verified. No hosted CI result is claimed.

CPU and native compile/link checks cannot establish a successful kernel load
or desktop takeover. The local host reports macOS 26.7.2 build 25G332. An
optional read-only registry archive query was not accepted because its output
could not be decoded as a plist; no current driver/display state is inferred
from it. No native user-client method, GPU workload, installed helper change,
EFI operation, M2 arming or reboot is part of this correction.

The [allocation execution plan](ALLOCATION-EXECUTION-PLAN.md) remains the
target validation path. Its passive snapshot, initializer compatibility,
resource ownership and independent recovery requirements remain open.
The old sampled Busy/raw-2 refusals still do not distinguish pending from
invalid retirement or establish the host-page preparation stage. This
correction does not justify another desktop attempt or an allocation-policy
change.

For source rollback, revert the build-38 claim correction and its associated
tests as a normal new commit. No installed rollback is needed for this
repository/build work; preserve the existing firmware-desktop fallback and exact
private rollback packet. A later deployment needs a separate build-38
package identity, reviewed rollback and scoped target validation.
