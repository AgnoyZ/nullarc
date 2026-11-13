# RADV cleanup candidate preparation

Preparation checkpoint, 2026-11-13. The build-35 desktop test reached
PhxAMDFB and then produced three WindowServer crashes in the RADV
command-buffer cleanup path. The initialized firmware desktop is retained;
this preparation performs no installation, GPU work, initialization, display
switch or reboot. See [the desktop outcome](validation/native-submit-build35-m2-postboot-20261113.json).

## Original preparation checkpoint

GitHub run `43370193766`, at source
`4f35a609331752d5e2dcac24f8b878d32aa6f309`, completed successfully. A fresh
API read verified both jobs and the native compile/test step. The retention
step was skipped, and the run's artifact API reports zero artifacts. There
was no retained candidate binary to download or verify at that checkpoint.
Build success is not an available installation package; the two-kext archive
contains no RADV.

Eight current RADV build/preparation/fetch, ABI-test/header, no-device-probe
and downstream-patch files match that successful source commit byte for
byte. The relevant Mesa, Cobalt, Phoenix, Vulkan-Headers and RADV-patch lock
sections also match. This is source/recipe continuity, not a hash or signature
check of a new binary. The cleanup patch initializes destructor-owned state
before command-stream creation can fail. It preserves the failure and does
not resolve its original cause or establish desktop correctness.

The current fallback baseline matched all 55 recorded entries and all 15
active plugin/runtime entries. Six entries in the existing standalone
runtime directory were backed up privately; file bytes and symlink targets
were verified. Original ownership/modes are recorded separately from the
restricted local-user backup. No private paths, logs, identities or backup
contents are included here. Complete source provenance for the installed
mixed userspace remains unestablished: a clean source build must not be
described as differing from the old library only by this cleanup patch.

## Authorized narrow retention scope

The [repository instructions](../AGENTS.md) permit the separately reviewed
two-kext artifact and explicitly exclude runtime libraries from that
exception. The current full-stack workflow rejects public artifact
retention. On 2026-11-13 the owner separately authorized the scope below,
subject to component-specific source/notice review before upload. The
[RADV provenance review](RADV-PROVENANCE.md) defines the independent manual
workflow; it preserves both existing guards. A public
repository's downloadable artifact is not a private transfer to this laptop.

The authorized scope is one manually dispatched, seven-day RADV
candidate package, built on `macos-15-intel`:

- The only runtime binary is `libvulkan_radeon.dylib` with the reviewed
  constructor cleanup patch and native-only Phoenix transport.
- Include its build report, source provenance, checksums, applicable notices
  and corresponding pinned source/patch/build inputs. Complete this package's
  source and notice review before allowing upload.
- Exclude kexts, Metal plugin, translator, LLVM, Vulkan loader, AMD firmware,
  EFI, personal configuration, raw diagnostics and installation scripts.
- Preserve the existing full-stack publication guard and two-kext workflow.
  No release creation, visibility change or automatic deployment is proposed.

Authorization is not a build result or a deployment decision. The original
machine-readable preparation record is a historical pre-authorization
checkpoint; it is not rewritten to imply that authorization existed then.
The following completed workflow result establishes that a downloadable
candidate now exists.

## Manual artifact result, 2026-11-13

Manual run `43399540297` at source
`94291c8a7bf759b91e393150bf79c15da7495b03` completed successfully on
`macos-15-intel`. Artifact `14024179574` contains the reviewed one-library
package and expires at `2026-11-20T09:25:59Z` (17:25:59 in Asia/Shanghai).
It was downloaded into private local staging and independently checked:

- GitHub ZIP digest and outer tarball SHA256SUMS matched.
- All 65 inner manifest entries and all 18 ordered patch hashes matched.
  Packaged project/Phoenix source was compared byte for byte with committed
  Git objects; pinned Mesa licensing and command-buffer source hashes matched
  the earlier independently fetched Git blobs. Five source archives passed
  path/link and normalized-owner/time checks.
- The only runtime binary is the 20,264,288-byte x86_64 Mach-O type-6
  `libvulkan_radeon.dylib`. Its strict signature, required exports and
  system-only dependencies passed local static inspection. The build report
  includes successful actual ABI and four hosted no-device checks.
- Library SHA-256:
  `a76ff2b7d3f88dc2b64222b9806300f81be41d04e474c5c763a73c3e36c3ad0c`.

The earlier manual attempt `43397975918` was cancelled during review, with
zero retained artifacts. The packaging comparison incorrectly depended on
JSON object key order; a regression test now accepts reordered object keys
while rejecting changed values or patch array order. The successful run uses
that correction. Runtime source, build options, ABI, lock and patch inputs
were unchanged between the attempts.

The candidate was not installed or executed locally. No driver, runtime,
initialization flag, M2 state or boot configuration was changed; no GPU test,
desktop takeover or reboot was performed. CI and static verification do not
establish hardware or desktop acceptance. The original stream-creation
failure, desktop stability and physical-size reporting remain unresolved.
See [the artifact verification record](validation/radv-cleanup-candidate-artifact-20261113.json).

## Isolated candidate Metal test, 2026-11-13

After the owner's continuation of acceleration troubleshooting, the verified
candidate passed one bounded Metal compute invocation at 17:43:25 UTC+08:00
on macOS 26.7.2, build 25G332. This was process-specific target validation;
the installed runtime alias and original library were not replaced.

Static inspection of the actual installed plugin established that it reads
`NVMTL_ICD_LIB` and passes the readable selected path to `dlopen`. This older
binary differs from the current source's plugin-relative runtime selection.
The test reused the exact previously reviewed Metal probe and selected the
candidate by its absolute private path. Dynamic-loader readback in both
the enumeration and compute processes verified the pinned installed plugin
and only the candidate RADV library, without another Vulkan library. Both
processes reported native ABI 1.12 and kernel build 35. The unique Metal
device was registry-verified as PCI `1002:1900`.

The single compute process returned zero without a timeout. All six counts
`1, 63, 64, 257, 4097, 65537` passed exact output, unchanged-input and guard
checks, with alternating output offsets of 0 and 256 bytes. The process
used a separate Mesa shader-cache directory. Its roughly one-second runtime
is not a performance benchmark. The local process logs contained no
`VK_ERROR_DEVICE_LOST`, command-buffer refusal or cleanup-crash marker;
this limited log observation does not exclude all kernel or hardware faults.

The postcheck verified the same boot and loaded driver, all 55 baseline
installed entries and all 15 resolved plugin/runtime entries. NMXAccel and
IONDRVFramebuffer remained present, PhxAMDFB remained absent, all three
display switches were zero, and M2 NVRAM/stop/pending markers were absent.
No new WindowServer report appeared in the checked report directories.
There was no local native build, system installation, firmware-initialization
replay, desktop takeover, automatic retry or reboot.

This accepts this candidate's bounded Metal compute result with the current
mixed installed plugin/compiler stack. It does not accept desktop rendering,
the original desktop failure path, hard-hang recovery, video, sleep, stability
or physical-size reporting. The source provenance of the installed plugin
and other compiler components is still incomplete. The earlier artifact
record remains the historical pre-execution checkpoint. See the separate
[target test record](validation/radv-cleanup-candidate-metal-20261113.json).

### Runtime-switch preparation checkpoint

A private manual installation/rollback helper has been prepared and checked
without performing a system write. The proposed installation creates a new
versioned runtime directory containing the candidate RADV plus identical
copies or symlinks of the five existing non-RADV runtime entries. It then
atomically replaces only the runtime alias. The protected original runtime,
plugin, kexts and startup helpers stay intact; no mapped library is overwritten.
Rollback restores the exact original alias target and retains both runtime
directories, so it also avoids overwriting existing process mappings.

Read-only status checks passed. An isolated filesystem fixture verified
switching and restoring the alias, preservation of an already-open original
file, unchanged library bytes and refusal of an unexpected alias target.
This is helper validation, not a root installation, live deployment rollback
or external recovery test. Neither action changes already-running process
mappings. The prepared helper does not initialize firmware, arm M2, modify
NVRAM, alter security or reboot. At that checkpoint, deployment still required
the owner's separate authorization under the repository instructions; the
preparation did not extend the artifact publication exception to automatic
installation. The subsequent authorization and installation are recorded below.

## Authorized runtime-pointer installation, 2026-11-13

After reviewing the bounded proposal, the owner explicitly allowed only the
system RADV runtime-pointer switch, retention of the original, M2 remaining
off and no firmware initialization or reboot. A separate private authorization
record pins the already-reviewed plan and helper; the historical preparation
plan and previous test records were not rewritten to imply earlier permission.

The single administrator installation completed successfully at
17:56:15 UTC+08:00. It created a fresh, versioned, root-owned runtime directory
with six entries and atomically switched the runtime alias. Only the RADV
library bytes differ from the retained original runtime. The other five
entries preserve their bytes or relative symlink targets, ownership and modes.
The original protected runtime and installed Metal plugin remain intact;
mapped library files were not overwritten or removed.

Independent post-install inspection at 17:57:07 UTC+08:00 verified the new
alias target, the installed candidate's full SHA-256 and strict signature,
directory ownership/mode and all six runtime entries. The original runtime
still matches its recorded state. The only changed entry among the original
55-entry installed baseline is the runtime alias; the other 54 entries and
all 15 original resolved plugin/runtime entries match. Temporary staging
and switch paths are absent.

The same boot and loaded build-35 identity were retained. NMXAccel and
IONDRVFramebuffer are present, PhxAMDFB is absent, all three display switches
remain zero, and M2 NVRAM/stop/pending markers remain absent. No initializer,
probe or shutdown process was found during postcheck. There was no additional
GPU probe or device-enumeration invocation, firmware-initialization replay,
desktop arming, reboot, EFI change or security change in this installation
phase. The alias switch does not force already-running clients to reload.

At this installation checkpoint, the earlier process-scoped Metal pass applied
to the exact installed candidate bytes, but the default global loading route
and desktop use had not been executed or accepted after the switch. The private
rollback helper restores the exact original alias target and leaves both
directories intact. It has passed an isolated alias/open-file fixture; live deployment rollback and
recovery from a hard hardware hang remain untested. No automatic rollback,
M2 test or reboot was armed. See the separate
[installation record](validation/radv-cleanup-candidate-runtime-install-20261113.json).

## Installed default-route Metal test, 2026-11-13

Following the owner's continuation of acceleration troubleshooting, one bounded
Metal compute invocation passed at 18:05:30 UTC+08:00 using the installed
candidate through the plugin's default loading route. The test did not use
`NVMTL_ICD_LIB`, Vulkan/RADV selection variables or DYLD library-selection
overrides. Diagnostic library logging and a separate shader-cache directory
were retained. No runtime pointer was changed during this test.

Both the single enumeration process and the single compute process were
checked against the actual resolved runtime path and the statically inspected
Mach-O image identities of the installed candidate and plugin. No other Vulkan
library was mapped. The unique Metal device was registry-verified as PCI
`1002:1900`; both processes reported native ABI 1.12 and kernel build 35.

The compute process returned zero without a timeout. All six counts
`1, 63, 64, 257, 4097, 65537`, with output offsets alternating between 0 and
256 bytes, passed exact-output, unchanged-input and prefix/suffix guard
checks. Its 1.779-second elapsed time is not a benchmark. The checked process
logs contained no device-lost, command-refusal or cleanup-crash marker;
that observation does not exclude every hardware or kernel fault. Six static
identity fixtures also checked the positive case and refusal of wrong or
missing image identities, an extra Vulkan loader and a wrong runtime path.

The 18:05:35 postcheck verified the same boot and loaded driver, all 55
installed baseline entries, all 15 active plugin/runtime entries and all 15
retained-original plugin/runtime entries. NMXAccel and IONDRVFramebuffer
remained present, PhxAMDFB remained absent, all three display switches were
zero, and M2 arming/stop/pending/extra-probe markers were absent. No new
WindowServer report appeared in the checked directories. There was no local
native build, additional installation, initialization replay, desktop
takeover, automatic retry or reboot.

This accepts bounded Metal compute through the installed default route with
the current mixed plugin/compiler stack. It does not establish desktop
rendering, sleep, video, stability, complete userspace provenance or corrected
physical display size. See the separate
[default-route test record](validation/radv-installed-default-metal-20261113.json).
The previous artifact, isolated test and installation records remain historical
checkpoints with their original scopes.

### Single-boot desktop-test preparation

A fresh private single-boot M2 plan and its arm/cancel commands were prepared,
but neither command was executed. The plan is pinned to the installed-default
Metal result, the same boot, build 35 and the unchanged installed stack.
Read-only preflight and mocked authorization/cancellation guards passed.
The NVRAM, arming and scheduler mutation functions remain unchanged from the
previous reviewed single-boot helper; startup readiness checks were added.

An initially missing `local.phxboot` registration required investigation.
The installed plist has both `RunAtLoad` and `LaunchOnlyOnce` enabled. On the
current boot, the initializer log ends with normal completion at 16:09:23;
same-boot launchd events then record the service becoming inactive and being
removed. The local manuals permit unprivileged system-domain queries and
describe this single-run setting. The observed absence is consistent with
that completed job, rather than establishing a missing startup installation.
The on-disk startup files still match the installed baseline. No task was
loaded, bootstrapped, enabled or restarted to make this determination.

The proposed later action requires separate owner approval for one M2 boot
and a normal restart three minutes after arming, because the explicit pointer
installation authorization retained M2 off and prohibited reboot. It would
set only the existing one-shot arming value and commit trigger, leave the
persistent M2 marker absent, and retain existing next-boot initialization and
fallback. It would not switch the current display or manually replay the
initializer. Failed desktop tests would not be automatically retried.

Earlier soft WindowServer-crash fallback was observed, but a hard kernel/bus
hang can defeat the software recovery path. External recovery and live
runtime-pointer rollback remain untested. Firmware fallback retains the
candidate runtime alias; it does not automatically restore the old RADV
pointer. A future read-only postboot collector is prepared, but neither its
file hashes nor its alias checks certify which library WindowServer mapped.
M2 remains off and no reboot is scheduled at this preparation checkpoint.

## Verification and rollback requirements

For any later candidate, verify the exact workflow/source commit, archive
manifest and hashes, x86_64 Mach-O type, signature, required exports,
system-only dependencies, source/patch provenance and native ABI evidence.
Keep the original runtime and its exact alias target recorded until the
deployment route and rollback are separately reviewed; avoid overwriting a
library mapped by running processes. The original preparation checkpoint
contained a verified baseline backup. The later authorized pointer installation
is recorded above; live rollback and hardware-hang recovery remain unverified.

The hosted no-device test refuses to run when the target services are
present. It must not be repurposed as a GPU validation pass on this laptop.
Any target test needs a separately bounded process and verification of the
actual candidate library mapped by that process. Keep M2 off; neither a cleanup
fix nor hosted CI is permission to repeat desktop takeover automatically. The
initial command-stream failure, desktop stability and physical display size remain
unresolved.

Machine-readable observations are in [the preparation record](validation/radv-cleanup-candidate-preparation-20261113.json).
