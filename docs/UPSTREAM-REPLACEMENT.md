# Local upstream-release replacement

Status, 2026-11-15: **upstream v0.4.0-alpha installed on disk and independently
verified; original-driver loading still requires the completion reboot**.
GPU startup is disabled. This is an explicitly requested replacement of the
local modified installation, not an acceleration result or another desktop
experiment. The downstream source repository and historical evidence remain.

## Package and installation

The package is `nullarc-0.4.0-alpha.zip` from `luuumi-dev/nullarc`'s
[v0.4.0-alpha release](https://github.com/luuumi-dev/nullarc/releases/tag/v0.4.0-alpha),
published on 2026-11-09. GitHub's SHA-256 digest and the downloaded archive both
equal `dcfeaa04917719683487b24259933b6ea84513a840cc862a68cd91205af47bbb`.
The release tag resolved to commit
`9dd76b604fca5e0125bd3caa5723df0f611ff27f` at inspection. This identifies the
published artifact; the binaries were not independently rebuilt from that tag.
Archive paths and its two internal relative symlinks were checked before
extraction. The package's licences, notices, installer, uninstaller and startup
scripts were reviewed; no implementation or binary was imported into this
repository or republished.

Before replacement, eight system-component backup targets, about 886 MB of
regular-file data, and a complete 343-file EFI backup were independently
compared with their sources. All backups remain private. The upstream
installer's check passed on macOS 26.7.2 / build 25G332. Thirteen modified
components were moved out of active discovery paths, including the modified
startup adapter, experimental plugin/RADV variants and hidden accelerator
backup. This preserves rollback material without exposing it to normal driver
discovery.

The original installer ran once, without `--windowserver`. Its kernel-collection
build returned zero. The installed PhxAccel, plugin, runtime, firmware and scripts
match the release bytes; the original installer re-signed the plugin, and its
bytes still match the package. Independent signature checks passed for the
plugin and PhxAccel. A separate Auxiliary KC inspection found the release
accelerator's image identity. No driver was unloaded live and no GPU initializer
or desktop claim was run.

Only the existing OpenCore `OC/Kexts/PhxBringup.kext` bundle was replaced. Its
enabled configuration entry was already present. The complete resulting EFI
was read back twice after remounting read-only: the release bundle matches,
all 340 non-target files match the backup, and OpenCore configuration and Windows
boot files are unchanged. The EFI now has 342 files because the original bundle
has two files where the modified bundle had three. The EFI was unmounted after
verification. No partition, BIOS, security-policy or NVRAM-reset operation ran.

## Activation boundary and completion reboot

The original startup LaunchDaemon is installed but was not started in the
installation boot. The empty `phxboot-off` marker was restored after the original
installer removed it. There is no `phxboot-m2`, pending attempt or one-shot display
flag. Original startup scripts contain reference-machine fixed memory values
that have not been validated for this target; earlier target layout records
differ. Installing their bytes is not permission to execute that initialization
or proof that the reference recipe is compatible.

The independent readback still observes the preparation boot and modified
bring-up build 39 loaded in memory. Disk replacement alone cannot unload that
kernel image. A separate completion phase permits one ordinary reboot to load
the newly installed original bundle, retaining the GPU-off marker. It does not
reuse a desktop-test reboot allowance or enable GPU initialization. The installer
phase itself requested no reboot.

A separate one-use metadata-only LaunchDaemon is staged for that fresh boot. It
compares the loaded bring-up image identity with the release, checks any loaded
accelerator identity, records framebuffer/service metadata and the off/arming
state, then removes its own LaunchDaemon file. It never sends GPU initialization
commands, changes display flags, retries a test or requests a reboot. A staged
job or scheduled restart is not evidence that the original driver loaded; retain
that distinction until its actual fresh-boot receipt is inspected.

The eight old experiment receipt sets remain unchanged. Their installed-input
pins describe the historical modified stack and have been superseded by this
new explicit replacement request; they must not be treated as current-stack
verification or re-armed. Desktop takeover and acceleration remain unproven.

## Verification and rollback

The [sanitized installation record](validation/upstream-replacement-20261115.json)
records the artifact, backup, byte-comparison and kernel-collection checks.
Private raw output, image identities, firmware, binaries, EFI and rollback
packets were not published. Existing repository licences and binary-publication
limits are unchanged.

Rollback requires a fresh, bounded operation that restores the retained modified
system components and prior Auxiliary KC, then only the saved PhxBringup bundle
in OpenCore. Verify every non-target EFI file remains unchanged and retain the
GPU-off state. Remove the separate metadata job if it has not yet run. Never
restore the whole EFI over unrelated changes or replay a consumed installation
or desktop experiment. Neither a backup nor metadata verification guarantees
recovery from an unbootable kernel.
