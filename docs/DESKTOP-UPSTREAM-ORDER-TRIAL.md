# Single desktop trial of the upstream CP setup prefix

Status, 2026-11-15: **single target attempt consumed; CP setup verified before
selection; first selector still dual-zero; recovery reboot verified**. The
owner requested an upstream-order test after the [startup comparison](
UPSTREAM-STARTUP-COMPARISON.md). This is a new, single-use experiment. All earlier
requests, target scopes and reboot allowances remain closed.

## One changed ordering decision

The fixed upstream reference is `8aba872560a3c9b7dc7a0ddebfad001c6dddf315`.
Its `full.sh` performs three doorbell/CP setup writes before GART/MES and the
queue selections inside those stages. The downstream desktop entrypoint checks
four queue selections before those setup writes. Its last retained failure
occurred at that early first selection.

The new **compile-time-only** switch
`PHX_DESKTOP_CP_SETUP_FIRST_TRIAL=1` moves the existing three setup write/readback
pairs before the four queue-idle checks for `desktop-init`. Every setup value,
the pair ordering and their refusal checks are retained. Invalid switch values
are rejected at compilation. A trial diagnostic identifies setup start, each
attempt/reply and successful completion before selection.

Without that explicit build switch, the old ordering remains. Both terminal
preflight commands and `desktop-claim` preserve their existing behavior even
in a trial build. This is a test of the **CP-before-selection prefix**, not a
wholesale replay of the upstream installer or machine-specific initialization
recipe. The checked downstream GART, MES, fences, queue adoption, ownership and
display boundaries remain in place. A positive first selection alone would
not establish acceleration or prove the historical cause.

The physical candidate is built from current guarded source. It includes the
later [desktop selector](DESKTOP-SELECTOR-GUARD.md) and [GART selector](
GART-SELECTOR-GUARD.md) checks absent from the last target helper. Those changes
do not explain the historical first dual-zero pair, and GART was not reached
then. They must still be recorded as candidate differences; a comparison with
that historical run is not an otherwise identical binary A/B experiment.

## Fresh preparation state and execution limits

Read-only admission found that the current boot and startup state differ from
the last recorded recovery. The installed startup now selects the stock shell
entrypoint and the off marker is absent. One accelerator service and one
firmware framebuffer are registered; the native framebuffer service and
matching initializer/reboot processes were absent. Provider metadata reports
build 39 and legacy startup enabled. These observations are not GPU execution
proof. The fresh metadata query reports macOS 26.7.2 / build 25G332. No GPU
command was issued by that inspection.

The old preparation's startup/off-marker hash predicate therefore refused.
No activation followed that refusal. Preserve the changed startup as the new
preparation baseline rather than silently repinning the old consumed request.
The other six installed-input hashes still match the retained record.

A separate root-owned packet bound the new authorization, exact signed
trial helper, unchanged trusted runtime/firmware/installed drivers, current
preparation boot, a new empty scope and all six historical receipt sets. It
was limited to one ordinary fresh boot, one desktop attempt and at most one
failure/timeout recovery reboot. There is no same-boot initialization,
automatic retry, persistent M2 flag or request replay.

Activation may select only the new startup packet and its targeted one-shot
display flag, with exact input/boot/process readback. It does not install a
kext, rebuild a collection or alter EFI, BIOS, partitioning or security. The
existing independent recovery worker must acknowledge a 240-second deadline
before metadata discovery and hand that deadline to the coordinator. Finite
failure or timeout disarms further attempts and requests the one recovery
reboot. This cannot guarantee recovery from a kernel or bus hard hang.

Before reboot dispatch, an activation failure restores the exact preparation
startup and original marker-presence state and removes only this trial's
arming. After a possibly dispatched reboot, preserve evidence and inspect
actual state before any further action. Failure recovery may leave the off
marker present to prevent a legacy automatic retry, even though it was absent
at preparation. The original startup and marker state are retained privately.

## Validation and reporting

The historical [preparation record](validation/desktop-upstream-order-preparation-20261115.json)
pins the tested source and build configuration; its unarmed/no-target status
describes preparation only. Failure-first CPU checks reject
the old ordering. The fake-IOKit entrypoint compares ordinary/trial successful
register traces with just the moved setup pairs omitted; counts and the
remaining transcript digest match. It independently checks the six setup
operations before the first selector, all 24 setup transport/reply failure
positions, the dual-zero refusal and every idle-selection immediate mismatch.
Admission failures still precede setup, and terminal probes/claim stay unchanged.

**135 focused test methods pass without skips**: 38 desktop, 30 startup adapter,
47 coordinator, six coordinator runner, seven transport and seven collector
methods. The full suite was not rerun.

The real x86_64 CLI is compiled and signed privately, without executing it
during preparation. Raw logs, installed metadata, boot identifiers, binary
artifacts and target register output are not published. Existing component
licences and publication restrictions are unchanged. Source rollback uses a
normal new commit and preserves all consumed evidence.

Only independently retained target status and native output can establish which
stage actually ran. A scheduled reboot or a successful packet check is not a
target execution, desktop success or acceleration result.

## Target result and recovery

The [target record](validation/desktop-upstream-order-target-20261115.json)
documents the completed attempt from synchronized source commit
`594f6ad9c1acb757b8aa14954717733950ca4eb8`, built with the explicit trial switch.
The preparation, test and subsequent recovery boot identities are distinct.
The target reports macOS 26.7.2 / build 25G332 and bring-up build 39.

Firmware/power returned zero. The native `desktop-init` stderr then records all
three CP setup pairs, with both the immediate and subsequent readbacks matching
each requested value, followed by the setup-complete marker. Only then does it
record the first queue selection. That selection still returns two zeros for
the nonzero request, and the native process exits 75 without timing out. The
initializer adapter returns 74. No GART, MES, GPU workload, claim, display,
release or monitor stage is reached. The single native initialization and
selector counts are process/log observations, not independent hardware tracing.

The four linked coordinator journal records, observer/baseline hashes, native
statuses and recovery claim hashes were independently checked against stable
private receipts. One baseline snapshot returned zero with `observed=0` before
initialization; no failure snapshot was recorded. The baseline collector ran
and the observer remained active, so this is not a collector-free experiment.

The independent metadata worker handed off to the coordinator's armed recovery
worker. Finite initialization failure requested recovery; the recovery record
follows the failed stage return by about 0.75 seconds. The 240-second watchdog
did not expire. Disarming completed, and the one recorded recovery reboot
command returned zero. The display cleanup process returned zero, but two of
its writes reported unknown OIDs; only AGDC and framebuffer-hold writes returned
zero. Do not treat that process status as four successful cleanup writes or as
a hardware-deadline recovery test.

Independent readback verified the subsequent boot, one firmware framebuffer,
no native framebuffer or accelerator service, an absent one-shot flag and no
persistent markers, initializer, startup job or reboot process. The off marker
was originally absent and is now present and empty, intentionally preventing
another automatic attempt. This is a recorded recovery safety-state change,
not restoration of the original marker absence. The selected startup remains
the exact consumed single-use packet. No driver, kernel collection, EFI, BIOS,
partition or security change was performed for this experiment.

All 188 new receipt files were stable and matched their private copies. All six
historical receipt sets, 41 execution pins, nine recovery pins, the complete
trusted runtime, signed candidate and six other installed inputs were
reverified. The private activation executor additionally passed 21 tempfile-only
methods under the exact Python 3.13 runtime before activation, including partial
writes, rollback and uncertain-dispatch handling. The preparation's 135 focused
methods are historical and were not rerun for this result-only documentation
change. Result verification used retained files and boot/service metadata only.

On this guarded candidate, moving the CP setup prefix earlier did not resolve
the first selector failure. Direct native stderr rules out outer summary
parsing as the source of the recorded zeros. It does not rule out a native
access-path defect, observer interference or another initialization prerequisite,
and it does not establish a physical cause or accelerated desktop. This remains
the scoped CP-before-selection test, not a full upstream-stack comparison or
an otherwise identical binary A/B against the historical helper.

This request and both reboot allowances are consumed and closed. Preserve the
inactive packet and all claims/receipts; never re-arm or replay them. Continue
with offline investigation under this request. Any further physical test needs
a distinct reviewed scope, fresh boot and independent recovery plan. The
ordinary build still defaults to the original ordering.
