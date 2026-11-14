# Owner-authorized build-37 deployment

On 2026-11-14, the owner approved proceeding with the previously proposed
PhxBringup-only installation and normal firmware-desktop restart. A fresh
private operation record covers one installation and one restart with a
three-minute delay. It does not replay a historical grant, arm M2 or launch
the legacy initializer manually.

## Installation and independent verification

The preflight completed at **11:05:07 +0800** on macOS **26.7.2, build
25G332**. It verified the existing loaded build-36 image, firmware
framebuffer, absent display arming and startup markers, completed inherited
startup, unchanged runtime/plugin/startup/recovery inputs, exact build-37
candidate and retained rollback backup. The complete live EFI manifest
matched the reviewed 337-file backup. The read-only mount was unmounted
before installation.

Installation completed at **11:05:39 +0800**. Only the active
`PhxBringup.kext` was replaced. The old build-36 bundle was retained under
its unique rollback name on the same EFI. The complete resulting manifest
contains **340 files**, including those three retained rollback files.
All **334 unrelated EFI files** and the OpenCore configuration matched their
original hashes. No PhxAccel, runtime, plugin, firmware, startup or recovery
file was replaced. The partition was synced and unmounted.

A separate verification process completed at **11:06:00 +0800**. It
rechecked live metadata and installed inputs, mounted EFI read-only, hashed
the entire resulting file set, verified the candidate and retained build 36,
checked the candidate's strict signature and configuration, and unmounted
EFI again. It did not infer installation from the copy command's exit status.

The installed candidate is the original diagnostic build from source commit
`2c26f4deffc4940c1a0a69d9b36c6770191ee0a8`, not the separate build-38 claim
correction. Its executable SHA-256 is
`6e59fe0d3a1247b70eae7b1953268a1239c5b5524870fbb9cdfc3e80783203a1`.
The [native package record](ALLOCATION-LIVE-PREFLIGHT.md) supplies its source,
SDK and build provenance. Installation preserves its VM guards, budgets,
pin direction, cleanup, uncertain-resource retention and diagnostic behavior.

## Installer checks and rollback

Seven isolated file-operation cases exercised the actual replacement function
used by this new executor: success, retention-name collision, staged byte
mismatch, staged signature refusal, active signature refusal, failed
activation rename and unrelated-file drift. All passed. Failure fixtures
preserved the old active bundle and original unrelated file. These tests use
temporary directories and injected file/signature failures; they do not test
the real firmware filesystem's crash consistency or GPU recovery.

The exclusive installation-start record was persisted before mounting EFI
writable. Candidate bytes and signature were checked in staging before the
old bundle was renamed. The exact complete manifest was checked again after
activation. The fresh installation receipt is consumed; a later continuation
must inspect it rather than rerun the deployment action.

Rollback remains confined to the retained build-36 PhxBringup bundle after
the exact partition and bundle checks in the
[install/rollback packet](ALLOCATION-INSTALL-PACKET.md). Do not replace
configuration or unrelated EFI content. The full original 337-file backup
remains verified. Independent recovery is operator-attested, not boot-tested
by the agent; a hard kernel/bus hang still requires operator recovery.

## Load and collection are subsequent evidence

The running kernel remained **build 36** during installation and independent
read-back. Writing build 37 to EFI is not evidence that it has loaded.
The normal firmware-desktop restart is the next authorized operation; at
this deployment checkpoint it had not yet been scheduled. M2 remained off,
and zero snapshot-reader requests or manual GPU/initialization calls occurred.

A root-owned postboot metadata verifier and private handoff are retained.
They identify the candidate image, complete new inherited startup, firmware
framebuffer, unchanged runtime/plugin/recovery inputs, and the installed and
retained EFI bundles before any passive reader call. The trusted
[capture runtime](ALLOCATION-CAPTURE-RUNTIME.md) was reverified. No new
LaunchDaemon, startup edit or automatic continuation was installed or assumed.

After the new load is verified, [Phase A](ALLOCATION-EXECUTION-PLAN.md#phase-a-prove-passive-read-feasibility-on-the-firmware-desktop)
still requires one valid baseline and at most one matching same-boot second
passive read. No automatic escalation to desktop takeover is scheduled.
The observer/startup and independent-recovery integration review remains
necessary before a display attempt. This installation does not establish
snapshot transport, allocation correctness, desktop liveness or acceleration.

The [sanitized deployment record](validation/allocation-build37-deployment-20261114.json)
separates the installed bytes and read-back from the still-unperformed load,
passive-read and desktop steps. Raw plans, file manifests, paths, identities
and command receipts remain in private storage.
