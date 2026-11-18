# Local S5 power-off/restart candidate

On 2026-11-18 the owner reported that macOS menu shutdown stops the power
indicator and fans, then the machine starts again without a power-button
press (symptom C). The local system was read as macOS 26.7.2, build 25G332.
A real shutdown request reached `halt by root`; the available logs alone
cannot distinguish a completed S5 transition followed by wake from a reset
during the final transition. This is an unaccepted local ACPI candidate, not
a proved cause or successful shutdown repair.

The accepted default-build34 installation remains the runtime baseline from
`1d4968fbc2ce988c77bdd85b2ec36f435b57f496`. No driver/plugin image, A1/A2/
corrected-A3, IB correction, native ABI or GPU wait implementation changed.
The owner's local PR28 daily configuration stays enabled, WindowServer remains
excluded, and resident installation/hang monitoring stays disabled. Build41
and build42 remain withdrawn.

## Diagnosis and one-variable hypothesis

The existing S5 `PWDE` patch was already enabled, matched once in the OpenCore
log, and was independently confirmed in the ACPI table loaded by this boot.
Re-enabling that patch would not be a new test. The conflicting ALIB stub was
already absent. Historical Ethernet-disable testing had not solved shutdown;
that configuration was restored. No such earlier unsuccessful intervention
was repeated.

The native firmware defines a separate `PEWD` field in the PM1 enable half,
bit 14, and its FADT advertises PCI Express wake support. The candidate tests
whether disabling that wake path after native S5 preparation prevents the
reported immediate restart. It does not establish that PCIe wake is the cause
or rule out a reset, another wake source, or firmware behavior after `_PTS`.

The local OpenCore change appends exactly two configuration entries:

1. A DSDT-only, table-identity/length-limited patch that renames the unique
   native `_PTS` method to `ZPTS` without changing its implementation.
2. One new `SSDT-S5-PCIe.aml` table. Its wrapper first calls native `ZPTS`
   with the original argument, then writes `PEWD = One` only for Darwin S5.

Native EC, SMI and other shutdown preparation remain reachable. Other sleep
states and the existing `PWDE` patch are preserved. The new table is locally
authored; no firmware implementation or third-party code was copied into it.
The personal configuration, firmware-derived patch bytes, ACPI dumps, DSL/AML
and raw logs remain private and ignored. This is not a generic SSDT intended
for installation on other machines.

## Exact startup-integrity compatibility

The existing local startup admission compares the entire EFI, so adding the
table without updating its expectations would fail admission. The pure
[`build34_acpi_scope.py`](../tools/build34_acpi_scope.py) helper derives new
expected manifests for only `OC/config.plist` and
`OC/ACPI/SSDT-S5-PCIe.aml`. The root-owned local policy pins their exact lengths
and hashes and the helper/entrypoint source. Original frozen contracts and
stage records are not rewritten; file hashing, full-manifest comparisons,
kernel admission, protected runtime files and recovery-image checks remain.

Three exact states are recognized: original configuration with no new table;
original configuration with the new table staged but inactive; or candidate
configuration with the exact new table. The state selector examines only
those two paths and does not replace the subsequent full EFI verifier.
Unknown combinations or unrelated changes still fail. The original state
remains valid for rollback. Existing mount locking serializes EFI observers.

The reviewed private installer compares the full manifest before writing,
copies the new table first and atomically replaces the configuration last.
Rollback restores the original configuration first, then removes only the
byte-checked new table. The local policy update is staged helper/source first,
policy last, with exact original backups and guarded exception rollback.
Multi-file deployment is not transactional under a power loss; retained
backups and the inactive/original states support manual recovery.

## Preparation and deployment verification

The following checks passed without executing AML, a power action or a new
GPU workload:

- 20 public pure-manifest tests, including rejected drift, historical-input
  changes, exact Windows/kernel preservation and all three allowed states.
- 20 private temporary-file tests of the actual installer: normal install,
  resume, rollback, unrelated/corrupt file refusal, missing table, and injected
  interruptions before/after table/configuration and startup-policy writes.
- The retained 11 PR28 exact-configuration tests and 25 startup-policy tests.
- Local AML compilation: 95 bytes, zero errors, warnings or remarks. A separate
  disassembly check confirmed native-call order and Darwin/S5 gating. This is
  compilation/static inspection, not an AML-interpreter execution test.
- Official `ocvalidate` 1.0.8 accepted both the prepared and deployed config.
- Actual updated owner-entrypoint readback, existing installed-runtime checks,
  full EFI/recovery checks, and independent post-deployment comparison of all
  358 EFI files. Only the configuration content and one new table differ.

The first post-deployment readback incorrectly compared the historical
policy-creation boot identifier with the current boot and stopped after the
EFI/runtime checks. It triggered no recovery or live-file change. The check
was corrected to the independently read current boot time and repeated
successfully; the initial refusal and correction remain in private evidence.

At the deployment readback, the candidate was installed on disk but not yet
loaded in that boot. Readback confirmed the same compositor, active acceleration/desktop controls,
zero copy failures/skips, unchanged security and no new matching reports.
Windows EFI, original recovery backups, accepted kernel/plugin images and
the PR28 daily setting are unchanged. The EFI was unmounted after checks.
There is no new monitoring job or automatic power action.

The sanitized record is
[`validation/build34-acpi-s5-candidate-20261118.json`](validation/build34-acpi-s5-candidate-20261118.json).

## Subsequent owner-initiated restart

The owner subsequently reported completing a restart on 2026-11-18. Independent
readback confirmed a new boot on the same macOS 26.7.2 build 25G332, rather than
reusing the deployment boot. The loaded ACPI property contained exactly one
byte-identical candidate SSDT with a valid checksum. The loaded DSDT matched
the prior boot's table with only the exact native `_PTS` rename and checksum
correction; the original method body, existing `PWDE` patch and FADT remained
unchanged. This verifies table loading, not execution of the S5-only write.

The actual owner policy, installed kernel/plugin checks, full candidate EFI
and original recovery-backup checks passed. Both startup completion and
supervision-ended receipts matched this boot, with accelerated desktop
admission complete and no startup-failure receipts or recovery intent. Passive
readback confirmed the same WindowServer as admission, active acceleration and
desktop controls, zero copy failures/skips, no new matching reports and
unchanged security. The PR28 daily configuration remains enabled; compiled
opt-in, the 250 ms budget and WindowServer exclusion are unchanged.

An extra observer initially required the completed startup services to remain
registered in launchd. That query stopped the observer because both configured
jobs use `LaunchOnlyOnce` and were already absent. Their current-boot completion
receipts and zero remaining monitor processes were verified, and the corrected
observer accepted the completed one-shot state. This was an observer assumption,
not a startup failure; no service was recreated, enabled or restarted, and no
recovery was triggered. The verifier changed no EFI/runtime configuration and
issued no GPU work or power action. The EFI was unmounted after verification.

Candidate loading and this bounded accelerated startup are accepted. Physical
S5 shutdown, the reported restart-after-power-off symptom, long-term stability
and FPS remain unaccepted. The original deployment record retains its earlier
pending-boot status as history. The subsequent result is recorded separately in
[`validation/build34-acpi-s5-reboot-20261118.json`](validation/build34-acpi-s5-reboot-20261118.json).

## Manual acceptance and rollback

The initial restart, loaded-table verification and bounded startup admission
have now completed. After saving work, the remaining owner action is to use
the macOS menu to shut down and observe whether the power indicator/fans stay
off for at least 30 seconds without touching the power button. If they remain
off, the owner can then press the power button to return and report the result.
Record failure details if it restarts by itself, stays powered, or hangs.
A repeated successful cycle is needed before treating this as a daily shutdown
repair; one cycle does not accept long-term stability, other sleep states or
FPS. For any future ACPI revision, repeat the restart and actual loaded-table
verification first. The verifier has not executed a restart or shutdown.

The private local rollback entry is retained at
`/private/var/db/nullarc-acpi-shutdown-20261118/install-s5-candidate.py rollback`.
It requires root and the exact recorded EFI state, restores the backed-up
configuration, then deletes the exact new AML. It refuses unrelated drift.
The compatible startup policy can admit that original state without changing
the frozen build34 contract or re-enabling monitoring. Offline recovery must
likewise restore the original macOS OpenCore configuration before deleting
the new table; do not change `EFI/Microsoft`. A subsequent restart is required
to replace ACPI tables already loaded in memory. These steps are a recovery
procedure, not an automatic scheduled rollback.
