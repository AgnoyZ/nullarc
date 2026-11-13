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

### Prepared runtime switch, not installed

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
NVRAM, alter security or reboot. Deployment still requires the owner's
separate authorization under the repository instructions; this preparation
does not extend the artifact publication exception to automatic installation.

## Verification and rollback requirements

For any later candidate, verify the exact workflow/source commit, archive
manifest and hashes, x86_64 Mach-O type, signature, required exports,
system-only dependencies, source/patch provenance and native ABI evidence.
Keep the original runtime and link intact until the deployment route and
rollback are separately reviewed; avoid overwriting a library mapped by
running processes. This checkpoint contains a verified baseline backup,
not a tested deployment or executable recovery mechanism.

The hosted no-device test refuses to run when the target services are
present. It must not be repurposed as a GPU validation pass on this laptop.
Any target test needs a separately bounded process and explicit selection
of the candidate library. Keep M2 off; neither a cleanup fix nor hosted CI
is permission to repeat desktop takeover automatically. The initial
command-stream failure, desktop stability and physical display size remain
unresolved.

Machine-readable observations are in [the preparation record](validation/radv-cleanup-candidate-preparation-20261113.json).
