# Internal-disk ring-padding comparison preparation

On 2026-11-17 the owner requested internal-disk testing and confirmed that the
existing Windows installation can be started directly from the firmware's
one-time menu, independently of OpenCore. This replaces the earlier
removable-medium prerequisite. It does not extend the experiment beyond the
default build34 baseline, the pinned derived ring-padding image or the
[fresh control/treatment ordering](BUILD34-RING-PADDING-PROPOSAL.md#proposed-comparison-and-ordering).

## Disk boundary and recovery

Only a new `EFI/OC/Nullarc34Rollback` directory was added. It holds the exact
unsigned original PhxBringup bundle, a private partition-pinned Windows
rollback script/manifest, instructions and existing component notices.
The original unsigned image was not re-signed. No OpenCore, unrelated kext,
firmware, BOOT or Microsoft binary was copied or changed. License/notice
review uses the existing PhxBringup MIT/GPL-2.0 component and build provenance;
the original and candidate artifacts themselves are unchanged and private.

The image transition algorithm was exercised in a separate inactive directory
on the actual internal EFI FAT volume: original to exact candidate to original,
then an intentionally interrupted staging operation followed by restoration.
Read-back passed. That temporary directory was removed after exact-original
verification. All 347 preexisting EFI files remain byte-identical. Nine recovery
files were added, the active PhxBringup remains the original, and EFI is
unmounted. The working config was not replaced with the earlier inactive
three-setting configuration proposal. No NVRAM or security-setting write was
requested, no partition was changed, and the Windows/fallback paths remain
unchanged.

A root-owned, frozen, restore-only launch job is installed and idle. It has no
GPU initializer or submission entrypoint. A later candidate activation may
change only the pinned PhxBringup executable and its additional signature
resource; Info.plist must remain identical. After the candidate's boot, this
job must restore and verify the exact original on disk **before** any GPU
initialization. A separate read-back must verify the loaded candidate identity,
the original on disk, backup integrity and GPU-off state before a treatment
scope can be prepared. A version string of 34 is never sufficient admission.

Startup restoration cannot run if the machine fails before macOS starts. In
that case the manual fallback is the owner-confirmed independent Windows
boot. The local script refuses a different EFI partition, unknown active image
or unrelated EFI drift and restores only the PhxBringup bundle. It requests no
boot configuration, partition, NVRAM or execution-policy change. **Its actual
Windows execution remains untested**; the FAT exercise and CPU state tests do
not establish Windows runtime compatibility or automatic pre-OS recovery.

## Scope preparation and checks

All 16 bundle-transition, 12 startup-state and 24 comparison-controller/parser
CPU test methods passed. Transition tests include every checkpoint prefix,
partial writes, recovery, exact metadata/images and refusal of links or
unrelated files. Startup tests require restoration before the loaded-image
query and retain HOLD on unknown identities. Controller tests use the actual
existing probe with fake IOKit, enforce inline `--run-single` admission without
an extra check client, and retain mismatch/held resources. They also cover
deadline failure, one recovery dispatch across concurrent requests, consumed
claim refusal, recovery-only boots and rejection of another exact image.

The first fresh-control preparation refused a runtime-generated log retained
inside a prior scope's private initializer home. This happened before creating
the new scope or performing GPU work. Preparation was corrected to select
only the 13 originally frozen initializer inputs and verify each hash; a
regression test confirms runtime logs are excluded and input drift is still
refused. No old consumed scope was replayed.

A new root-owned original-image control scope is now prepared, with an
independent observer handshake. Its execution job is not installed or armed
at this preparation checkpoint. It permits one initialization, one execution
client and at most two native submissions, using the existing signed probe:
`f89035937656ecc16cf6329a24801e29b8cd40d3c646e66d03628b358a9703a5`.
The independent deadline is 300 seconds, and recovery is limited to one
reboot without automatic retry. Held GPU processes must never be killed.

The control must reproduce pass 1's exact `0x2010` / `0xde` versus `0xdf`
failure after pass 0's whole-arena check, recover to original34/GPU-off, and
retire its consumed job before candidate activation. A treatment remains a
separate fresh scope requiring both whole-arena checks and native sequence/
fence validation, followed by exact-original recovery and retirement.

## Preparation result

Independent read-back on macOS 26.7.2 / 25G332 confirmed original34 loaded,
GPU-off/firmware framebuffer, unchanged 46 protected files, protected links,
security and kernel collections, exact recovery material, unchanged existing
EFI files and the inactive control scope. No new GPU initialization,
submission, candidate activation or reboot occurred in this preparation.
The IB wrong value remains unresolved; desktop, default-wait and FPS HOLDs
remain. See the [sanitized preparation record](validation/build34-ring-padding-internal-preparation-20261117.json).
