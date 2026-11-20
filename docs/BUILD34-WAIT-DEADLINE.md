# Build34 R1a: real elapsed-time accounting for native waits

## November 20 loaded R1a and bounded hardware acceptance

The authorized single ordinary restart completed at **13:03:56 Asia/Shanghai**
on November 20, 2026, macOS 26.7.2 build 25G332. The new finite observer and
a separate independent readback both passed exact R1a kernel loading,
unchanged accelerator/mapped plugin, fresh startup/desktop/supervision-ended
receipts, all 357 EFI files, complete 416-record/29-codeless cache metadata,
original loaded ACPI, security and exact accepted recovery. The old accepted
kernel was no longer loaded, and R1a was left active after this successful test.
The restart command's 15-second wait timeout was not a reason to resend it:
only one ordinary restart request was sent and no recovery power action occurred.

The fresh pinned native fixture submitted exactly two compute dispatches,
rewrote the same IB between them and passed both full 16 KiB arena checks,
including code, IB, output and guard bytes. In each pass the zero-budget query
returned pending; the subsequent 50,000 ns-budget call observed real completion,
taking 20,248 ns and 13,185 ns respectively. Independent reparse agreed with the
observer's output and the probe exited with clean client teardown. Thus the
real pending-to-completed positive-budget path was exercised, rather than only
an already-completed zero poll. These two short waits do **not** demonstrate
timeout/oversleep behavior, a hard wall-time return bound, physical FPS or
long-term stability; the delayed-clock cases remain CPU evidence.

Independent finite readback retained the same WindowServer, advanced VBL by
819 and display-completion count by 299, kept all four checked error counters
at zero and found no new matching report. These counters are not physical FPS.
No probe, startup, guardian or observer worker remains running; the observer
removed its job and exited zero. Recovery was not triggered. Preserve daily
PR28 250 ms/WindowServer exclusion, disabled resident monitoring and the original
45/150/300-second startup policy. The one-restart authorization is consumed;
do not replay the probe or restart dispatcher. R1b source preparation may now
proceed separately, retaining this successful R1a installation while later
candidate installation/reboot requires its own compatible authorization/scope.

See the [sanitized hardware record](validation/build34-wait-boot-20261120.json).

The later [R1b trial](BUILD34-RING-BACKPRESSURE.md#november-20-startup-failure-and-r1a-disk-recovery)
did not reach its pressure probe. Independent readback matched the R1a EFI
and startup jobs on disk; the R1b kernel remains loaded in the failed
framebuffer-admission boot. R1a's earlier hardware acceptance stands, but
recovery of the live accelerated desktop requires a separately authorized
R1a boot with the existing one-use panel flag armed. That subsequent
[owner-authorized recovery boot](BUILD34-STARTUP-RECOVERY.md) restored the R1a
accelerated desktop; a later surface timeout prevents strict zero-error
acceptance of the recovery observation.

## Historical November 20 authorized isolated installation

The owner subsequently explicitly authorized R1a installation, one ordinary
restart and bounded GPU validation. This supersedes the authorization-pending
status below. A fresh exact controller installs only the frozen candidate
PhxBringup executable from source `568e80b205c10b00cba4f21c6d324d239d725bfd`;
the accepted runtime source remains `1d4968fbc2ce988c77bdd85b2ec36f435b57f496`
for the unchanged accelerator, plugin and other baseline components.

Installation readback verifies all 357 EFI files with exactly one executable
changed. The accepted kernel remains loaded until the authorized restart.
The entire 416-record/29-codeless cache, PhxAccel, plugin, loaded original ACPI,
configuration, driver flags and security settings are preserved. The three
external Microsoft records remain individually pinned and unchanged.
Both startup jobs and a fresh finite observer are staged without current-boot
bootstrap. Exact accepted kernel/job recovery is retained.

The new controller passes 31 CPU test methods, including receipt freshness,
single-use probe enforcement, atomic file transitions/refusals and preserving
a timed-out GPU client. An inactive FAT-file candidate/accepted round trip
passed and restored the complete active EFI manifest. The existing MIT native
fixture was frozen, compiled and signed without execution; `--run-single`
allows exactly two dispatches with an intervening rewrite of the same IB and
full 16 KiB arena verification. The new independent evidence parser passes
12 CPU methods; the nine artifact-gate methods and default tests also pass.
CPU tests and native compilation are not hardware acceptance.

Preserve 45/150/300-second startup gates and the finite 360/420-second observer
bounds. On successful new-boot admission the observer verifies exact loaded
kernel/accelerator/mapped plugin, cache/EFI/ACPI/recovery and fresh receipts
before running that one new probe. Failure restores only this scope's exact
kernel/jobs without automatic power actions or old recovery calls. An
uncertain probe remains alive with its client/BOs; do not kill or retry it.
After success the observer removes its own job and exits. Daily PR28 remains
250 ms with WindowServer excluded; resident monitoring remains disabled.

**At this installation checkpoint no reboot request or new GPU submission
has occurred. R1a is not loaded or hardware-accepted.** Independent installed
readback and repository synchronization precede the single ordinary restart.
After boot require separate independent readback and native-output reparse.
Record whether positive-budget/pending waits actually occurred: immediate
completion alone does not cover the pending-wait path. No hard wall-time
return guarantee, FPS gain or long-term acceptance is claimed. R1b and R2–R6
remain unstarted. Weather and build41/build42 remain excluded.

See the [sanitized installation record](validation/build34-wait-installation-20261120.json).

## Historical November 20 resumption on the recovered accepted baseline

After the isolated [desktop re-enablement](BUILD34-REENABLE-20261120.md)
passed, the owner requested resuming R1–R6 in order and explicitly excluding
Weather. R1a source preparation resumes on the recovered owner-accepted runtime
`1d4968fbc2ce988c77bdd85b2ec36f435b57f496`. **The earlier Weather baseline
boot is no longer a prerequisite and must not be replayed.** The later
VBL/AML/render-clear/Weather experiments are not part of this runtime.

A fresh read-only check found another boot, November 20 at **12:20:11
Asia/Shanghai**, later than the already recorded 12:05:04 acceptance. This
optimization task sent no power command and does not establish what caused
that intervening boot. It independently checked the actual new boot's
startup/desktop/supervision-ended receipts rather than reusing the earlier
observer or acceptance. Exact loaded kernel/accelerator and mapped plugin,
all 416 cache records including 29 codeless entries, original loaded ACPI,
the complete 357-file EFI and original recovery passed. The same WindowServer
survived the finite observation, completion/VBL counters progressed, all four
checked error counters stayed zero and no new matching report was found.
No startup controller or power process remained.

The existing R1a driver patch is unchanged. Its 29 production-method CPU
cases, ten source-admission methods, 25 complete-cache methods and default
tests pass again. A new offline artifact gate,
`tools/check_build34_wait_artifacts.py`, checks the exact frozen baseline and
candidate bundle bytes, signatures, source snapshots, original recipe,
pinned SDK snapshot and successful build-log digests. Nine new refusal-test
methods cover wrong build/source/recipe/SDK, substituted or extra bundle
members, missing/failed/duplicate checks, unsafe links and incomplete EFI.
It derives the prospective EFI manifest from a separately verified full
baseline: only the active kernel executable may differ. All three current
Microsoft boot-state records remain pinned exactly, without an exclusion.
Historical build34 admission and the original build recipe are unchanged.

A fresh inactive private packet holds root-owned exact accepted/candidate
kernel bundles, current OpenCore configuration, both current startup-job
backups and complete before/candidate EFI manifests. Both bundle signatures
and every packet input are rechecked. The native baseline remains byte-identical
to the actual accepted EFI kernel. No packet entrypoint is staged or loaded;
no live driver, plugin, cache, EFI, ACPI, job, driver flag or security setting
is changed. The new checker is an offline artifact check, not a claim to
have inspected the installed state or established GPU correctness.

**R1a remains uninstalled and has no hardware wait/correctness/FPS acceptance.**
The earlier restart authorization is consumed, and re-enablement explicitly
excluded candidate installation. The renewed source/preparation request does
not reuse those grants: obtain a fresh explicit R1a installation, one ordinary
test-restart and bounded GPU-validation authorization before activation.
Use a new exact candidate admission/recovery controller; the inactive packet
is not a ready-to-run installer or an old scope to replay. Preserve the
45/150/300-second startup gates, full cache/EFI checks, accepted kernel/job
recovery, PR28 daily 250 ms with WindowServer exclusion and disabled resident
monitoring. R1b and R2–R6 wait for actual R1a hardware acceptance.

Additional offline commands:

```sh
python3 -B tests/test_build34_wait_artifacts.py -v
python3 -B tools/check_build34_wait_artifacts.py --native "$R1A_NATIVE" --sdk "$MAC_KERNEL_SDK"
```

See the [sanitized resumption record](validation/build34-wait-resumption-20261120.json).

## Historical November 20 hold after the failed prerequisite boot

The owner reported repeated restarts and requested rollback. The plugin
baseline boot did not pass; installed recovery had already cascaded to the
older owner profile. Both exact fallback startup jobs are now archived and
removed, the baseline observer job is absent, and final readback found no
active startup/guardian/observer/power process. The loaded PhxBringup is the
pre-R1a control; the R1a kernel was never installed or loaded. PhxAccel is not
listed loaded. No new GPU work, WindowServer restart or power request was
made during containment.

At that containment checkpoint R1a hardware validation and all later
optimizations were on hold. Do not use
earlier restart/install permissions or the offline test results to resume
automatic startup or desktop takeover. A new boot has not been tested after
containment and no complete restart-cause repair is claimed. Details are in
[the Weather rollback](BUILD34-WEATHER-INTERNAL-TRAILS.md#november-20-rollback-and-hold)
and its [sanitized record](validation/build34-weather-boot-rollback-20261120.json).
The following sections retain the earlier source/preparation history.

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

## Historical November 19 runtime and plugin-baseline preparation

This section records the pre-rollback situation, not the recovered runtime.
Its Weather prerequisite and installation path were withdrawn after failure;
use the November 20 resumption above instead. Do not replay this path.

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

At the initial source-preparation checkpoint, no new reboot authorization had
been consumed or power command sent. Earlier one-restart permissions remain
consumed. Do not install
the candidate into EFI, alter live boot entrypoints or schedule a power action
under an old scope. A new authorization was required before that transition;
the following separate preparation records the owner's subsequent grant.
No next-boot observer/job was staged by the initial source patch.

## Authorized plugin baseline reboot preparation

The owner subsequently authorized one ordinary baseline restart on November
19, 2026, preserving the accepted kernel. A fresh private next-boot-only
observer has been prepared, CPU-tested, staged and independently read back.
It is not bootstrapped in the preparation boot. The full actual runtime,
cache, loaded AML, EFI and recovery check passed, including the unchanged
accepted kernel and all 358 EFI file contents. The surviving WindowServer
still maps the pretrial plugin, so the isolation prerequisite remains real.
Another actual owner check passed after observer staging. Only the new
observer job was added; both existing startup jobs remain exact.

The observer's 27 CPU methods and six separate staging methods pass. An
initial success-path CPU fixture attempted to inspect the protected real
journal because its path was not redirected to the temporary fixture;
that fixture was corrected before staging. It is not hardware-failure
evidence. The final checks cover new-boot enforcement, fresh receipts,
startup failure/recovery/deadlines, exact plugin identity, all EFI contents
and the accepted kernel, serial timing records, errors, desktop progress,
exact job retirement, no overwrite and no current-boot bootstrap.

On the next boot the observer waits at most 360 seconds for this installed
Weather scope's fresh startup/desktop/supervision-ended receipts, under a
420-second total limit. It then independently verifies the exact mapped
candidate plugin, unchanged accepted kernel, complete 416/29/415 cache
metadata, loaded AML, full EFI/recovery, current policy and finite desktop
progress. It collects the current startup/guardian timing records, removes
only its exact own job, and exits. It has no GPU-test, recovery, power or
automatic-retry capability. Existing startup recovery, 45/150/300-second
limits, serial hashing, daily PR28 250 ms/WindowServer exclusion and disabled
resident monitoring are unchanged.

At this documented preparation readback no reboot request has been sent;
cross-boot acceptance remains pending. The fresh owner authorization permits
exactly one ordinary baseline restart after repository synchronization,
without asking again. Inspect the new scope's persisted request intent and
actual state after any uncertain command; never duplicate a power request.
After boot, require both its fresh result and a separate current-boot
readback before preparing the kernel treatment. The R1a kernel remains
uninstalled, and no later recommendation has started. These preparation
checks do not establish visual repair, physical FPS or long-term stability.

The sanitized checkpoint is recorded in
[`validation/build34-wait-plugin-baseline-reboot-preparation-20261119.json`](validation/build34-wait-plugin-baseline-reboot-preparation-20261119.json).

## Historical preparation rollback and record

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
