# Single desktop trial of the upstream CP setup prefix

Status, 2026-11-15: **source and CPU preparation; no target result yet**. The
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

A separate root-owned packet will bind the new authorization, exact signed
trial helper, unchanged trusted runtime/firmware/installed drivers, current
preparation boot, a new empty scope and all six historical receipt sets. It
must use one ordinary fresh boot, one desktop attempt and at most one
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

The [validation record](validation/desktop-upstream-order-preparation-20261115.json)
pins the tested source and build configuration. Failure-first CPU checks reject
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
