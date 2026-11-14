# Private PhxBringup-only install and rollback packet

On 2026-11-14, the operator confirmed having an independently usable boot and
EFI-restoration route. This is **operator attestation**, not a recovery-media
boot test performed by the agent. The earlier observation of no connected
external physical disk does not negate that confirmation.

This phase prepared and independently verified the exact private rollback
packet for the [retained build-37 candidate](ALLOCATION-LIVE-PREFLIGHT.md).
It did not install the candidate or issue a target snapshot request.

Later state: the [continuity/input revalidation](ALLOCATION-RESUME-REVALIDATION.md)
confirmed the same Goal active and reverified the original retained packets.
The activation refusal below is historical; do not repeat that consumed
request. Target execution scopes and the trusted capture runtime remain open.

## Current identity and exact change

The preparation observed the same build-36 PhxBringup service and loaded-image
identity before and after the read-only work. The firmware framebuffer remained
IONDRVFramebuffer; PhxAMDFB was absent. The available display gates read zero,
the selected display-arming value and named pending/M2/one-shot markers were
absent, and the bounded named-helper query found no competitor. Unavailable
gate values were preserved as unavailable. These observations do not establish
absence of all background GPU activity.

The current and candidate bundles each contain three files. Their exact
manifest comparison found one differing file: `Contents/MacOS/PhxBringup`.
The Info.plist and signature-resource bytes match. Candidate and current
strict signature checks passed; the candidate image identity was retained
privately. This establishes the proposed byte change, not kernel loadability
or successful snapshot transport.

The private plan identifies the exact source, candidate, reader, current image,
partition, current boot/service, active bundle, unique staging/retention names,
configuration hash, expected before/candidate manifests and rollback scope.
Rollback is confined to restoring the retained build-36 PhxBringup bundle;
configuration and unrelated EFI files are protected by the full manifest.
Installation and reboot claims have not been made.

## Fresh backup and independent read-back

The EFI partition was mounted read-only. Its complete EFI directory contained
**337 regular files, totaling 105,882,009 bytes**. All were copied into
root-owned private storage and matched the source hashes. A second source
manifest matched before unmounting. The preparation's before/after identity,
selected installed-input hashes and state comparison also matched.

A separate verification process independently hashed every retained backup
file, checked private ownership/permissions, reconstructed the current bundle
manifest and candidate difference, and checked the configuration identity.
It confirmed all 337 files, the one-file candidate difference and an unmounted
EFI partition. The private evidence inventory covers 436 retained files before
the inventory itself. No raw EFI, host identity or executable was published.

An initial parser error was retained: an absent PhxAMDFB query returned zero
bytes with successful exit status, and the preparation mistakenly attempted
to parse those bytes as a plist. Independent error-state inspection confirmed
that no EFI mount or backup had begun. The correction accepts empty output
only for that optional class, reuses the already recorded read outputs and
continues the same private packet. The original error, original program and
corrected program remain retained. This did not consume or replay a target
snapshot, installation, display or reboot attempt.

## Historical continuity refusal

The installed Codex app-server protocol exposes Goal lifecycle get/set
requests. A read through its standard-input/output transport successfully
returned the existing blocked Goal. The user's explicit continuation/Goal
instruction was then used for one status-only activation request, preserving
the existing objective and budget. The server rejected that request because
the thread already had an active writer. An independent Goal read afterward
still reported `blocked`. The unavailable default control socket and this
refusal were retained separately; neither was treated as a successful resume.

No Goal database was directly changed, no helper guard was bypassed and no
automatic status-change retry was scheduled. The existing login helper
requires an active Goal. At that point, the remaining prerequisite was
supported lifecycle restoration after the writer finished, followed by a
check against the actual saved session. That restoration has since succeeded,
as recorded in the follow-up above; do not replay the failed activation.
A real reboot/resume test remains outstanding.

The next target stage remains [Phase A](ALLOCATION-EXECUTION-PLAN.md#phase-a-prove-passive-read-feasibility-on-the-firmware-desktop).
Before installation/reboot, recheck live identities, the exact packet and
continuity admission, and claim the concrete one-use operations. A hard
kernel/bus hang still requires operator recovery; this packet provides no
agent-control guarantee under that condition. No install/load, native reader
execution, GPU workload, startup edit, arming or reboot occurred in this phase.
The allocation root cause remains unconfirmed.

The [sanitized validation record](validation/allocation-install-packet-20261114.json)
records these completed checks and unperformed steps.
