# Build34 R1a: real elapsed-time accounting for native waits

## State and scope

On November 19, 2026 the owner requested executing and testing the
[NullMoth comparison recommendations](BUILD34-NULLMOTH-SMOOTHNESS-REVIEW.md)
one at a time. This first candidate changes only the time accounting in
`IOAccelPhxNativeClient::doWaitSeq`, starting from default-branch commit
`4e9000e54447c7df2bc9482fa9863d3ef31df24c`.

**CPU regressions, separate source admission, native builds and local symbol
resolution pass. The candidate is not installed or loaded. Hardware wait,
correctness, stutter and FPS acceptance remain pending.** R1b (submission
backpressure), R2 and all subsequent recommendations have not been started.
Do not advance to them on the strength of these CPU results.

The complete driver source changes from SHA256
`fffd2bdfea25ca87312679e194949f2538807b43610d157f06c9dde0d33a70d0` to
`b4174f7f2498f8b3e1e7204059ef9c06041f30a808435cda703a34e0f9439267`.
Bytes outside the wait method are identical to the parent. Build34 identity,
the accepted ACQUIRE-prefix submission correction, native ABI and all other
production source inputs remain unchanged. No build41/build42 candidate is
prepared.

## Minimal change

The old loop accumulated the requested 50 us delay or 1 ms sleep. It did
not count initial fence-query cost, delayed dispatch or oversleep against
the caller's capped budget. Under delayed wakeups it could request further
waits after the real budget had elapsed.

The candidate snapshots `mach_absolute_time()` before the initial completion
query and converts the unsigned elapsed tick difference to nanoseconds
before each additional wait. Both budget expiry and the first-millisecond
poll/sleep choice use that elapsed time. It avoids adding a potentially
overflowing absolute deadline.

The unchanged behavior includes the two-second request cap, zero-time poll,
50 us short delay, 1 ms extended sleep, actual fence rereads, the global
retirement watermark, lock policy, BO cache maintenance, pending-fence
publication and scalar outputs. A delayed wait followed by an actually
completed fence still reports the observed completion. Timeout neither
publishes a fake completion nor frees pending work.

This cannot guarantee that the scheduler returns the caller within its
requested wall time. It prevents further waiting based on an undercounted
budget; one selected delay/sleep, preemption or a fence-query operation can
still cross the deadline. No claim of a measured frame-rate gain is made.

## CPU regression and admission checks

`tests/test_build34_wait_deadline.py` compiles the actual production method
into `test_build34_wait_deadline.cpp` with fake clocks, fence reads, delays,
locks and BOs. It uses the production ABI header, ASan/UBSan and strict
compiler warnings. It does not link IOKit or Metal or open a device.

- The unchanged baseline runs all 29 cases: 22 pass and seven fail at
  semantic assertions for delayed wakeups, initial poll cost, budget/cap
  boundaries, real-time phase selection and a non-unit timebase.
- The candidate passes all 29 cases. Other coverage includes unsigned clock
  wrap, zero and last-sequence waits, unavailable GPU behavior, late actual
  completion, pending retention, BO write bounds and exact fence publication.
- Ten separate source-gate methods reject unknown source, build41/build42
  markers, submission drift, changed ABI/metadata/other protected inputs,
  missing/extra inputs and baseline substitution. Historical original34
  admission remains byte-identical and correctly refuses this new candidate.
- `make test` passes, including the new 29-case suite. Existing firmware-file
  fixture tests skip because their optional files are absent. These are host
  tests, including the existing simulated queue/scanout tests, not GPU evidence.

Commands:

```sh
make test-build34-wait-deadline
python3 -B tests/test_build34_wait_deadline_build.py -v
make test
```

An initial test fixture conflicted with libc's `bcopy` declaration and ran
zero cases. Its CPU double was renamed before either semantic comparison;
that compile error is retained privately and is not baseline regression
evidence.

## Native build and actual local providers

`tools/build34_wait_deadline.py` is a separate offline gate for the exact
candidate. It checks the complete baseline/candidate source hashes, the
wait-only delta and all protected build inputs. It freezes source and the
audited MacKernelSDK at `3f750085caa17ec3a7880f11c11bf4f48cd6a164`, then builds
and signs both roles in fresh private directories. It never installs, loads,
submits work or modifies historical admission.

Both x86_64 kext builds and strict signatures pass. The same three existing
field-shadow warnings occur in both roles. Packaging retains the accepted
Radeon 780M-only PCI restriction; its Info.plist bytes match the actual EFI
kernel. No dependency or security setting is changed. Import comparison
finds one addition, `_absolutetime_to_nanoseconds`. Local `kmutil libraries`
against the matching KDK and current collections resolves all 375 candidate
imports; the new symbol is provided by the already-declared
`com.apple.kpi.mach`. No new private-KPI import is added.

An initial build gate incorrectly compared a signature-dependent binary
hash across signing. Its rejection is retained. The corrected check
preserves architecture, kext type and image identity across signing, checks
the strict signature and records the resulting signed hash. A fresh build
of both roles then passed without changing the driver candidate.

The kernel is injected from `OC/Kexts/PhxBringup.kext` in EFI; there is no
installed `/Library/Extensions/PhxBringup.kext`. No new Auxiliary Kernel
Collection was built or installed. Library lookup is not an actual kernel
load or a full AuxKC link test. Actual loadability remains part of the later
isolated hardware trial.

## Current runtime and a required baseline boot

A fresh read-only invocation of the currently installed owner `check`
entrypoint passed on macOS 26.7.2 build 25G332. It was not a replay of a
startup, guardian, installer or GPU scope. Exact backups of the current
three-file EFI kernel bundle and two startup jobs were then created and
independently hashed. The recompiled native control binary is byte-identical
to the current EFI kernel executable. Candidate and current bundle metadata
also match. All 358 EFI file contents and both live startup jobs remained
unchanged during backup.

There is an isolation prerequisite before installing R1a. The Weather trial
already put plugin source `87859b323267030afdfdcd9f4e52dc7168697686` on disk,
but the surviving WindowServer still maps the earlier accepted render-clear
plugin. That disk candidate has not been tested through its next boot.
Installing R1a and rebooting immediately would change both the kernel and
the compositor plugin at once.

The next separately authorized ordinary restart must therefore boot the
**existing disk configuration with the unchanged accepted kernel**. Require
fresh current-boot startup/admission receipts, exact loaded kernel and mapped
WindowServer plugin, complete runtime/cache/AML/EFI/recovery checks, finite
desktop progress and no new checked errors/reports. Collection or successful
boot alone is not visual/FPS acceptance. Do not replay a consumed observer
or use prior-boot receipts.

Only after that prerequisite passes may a fresh kernel-only installation,
recovery and hardware-validation scope be prepared from the same baseline.
It must retain the accepted VBL/AML/plugin/startup behavior, full serial
integrity checks, existing 45/150/300-second limits, daily PR28 250 ms with
WindowServer exclusion, disabled resident monitors and unchanged AuxKC.
Keep the global fence contract and queue lock unchanged for R1a.

No new reboot authorization has been consumed or power command sent by this
preparation. Earlier one-restart permissions remain consumed. Do not install
the candidate into EFI, alter live boot entrypoints or schedule a power action
under an old scope. The owner must authorize the new baseline restart before
that transition. No new next-boot observer/job has been staged by this patch.

## Rollback and record

No live candidate rollback is needed: the accepted kernel, cache, EFI,
settings and startup jobs are still installed. Fresh exact kernel/job copies
are retained privately for prospective validation; existing plugin and full
EFI recovery materials remain intact. A future kernel trial must restore only
its exact changed kernel/job allowance on failure, preserving the newer
accepted VBL/AML/plugin policy. Source rollback uses a new reverting commit,
never a history rewrite.

The sanitized evidence and acceptance boundaries are recorded in
[`validation/build34-wait-deadline-offline-20261119.json`](validation/build34-wait-deadline-offline-20261119.json).
Native binaries, private identities, full manifests and raw logs stay local
and ignored; no binary artifact is published.
