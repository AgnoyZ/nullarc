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

## Authorized single-boot M2 arming, 2026-11-13

After the separate proposal above, the owner explicitly allowed one M2 desktop
test and a normal restart three minutes after arming. A separate private
authorization receipt pins the reviewed plan, helper and fresh read-only
preflight. The earlier preparation records retain their original scopes.

Arming completed at 18:33:28 UTC+08:00. The existing one-shot
`phxfb-boot=1` value was written, its existing forced-commit trigger completed,
and the value was independently read back. The persistent M2 marker remains
absent. Exactly the recorded normal-restart scheduler was observed, with
restart expected approximately 18:36:29 UTC+08:00. The prepared cancel
command targets only that scheduler's matching process identity and the
expected one-shot flag; it was not executed.

Independent pre-restart checks retained the same loaded build-35 driver,
all 55 installed entries, 15 active plugin/runtime entries and 15 retained
original entries. NMXAccel and IONDRVFramebuffer remain present, PhxAMDFB
is absent, all three display switches are zero, and stop/pending/extra-probe
markers are absent. No new WindowServer report appeared since the accepted
Metal postcheck. No current-boot initializer, GPU probe or display takeover
was replayed, and no runtime pointer, driver, startup helper, EFI or security
setting was changed by arming.

The next boot is to use the unchanged initializer, one-shot consumption and
software fallback. There is no automatic failed-test retry or automatic
old-RADV-pointer restoration. Hard kernel/bus hangs and external recovery
remain unverified. This is an arming checkpoint before restart, not desktop
or postboot acceptance; it does not verify WindowServer's mapped RADV image
or correct physical display size. See the separate
[arming record](validation/radv-installed-default-m2-arming-20261113.json).

## Installed-candidate M2 result and fallback, 2026-11-13

The one authorized desktop test did not pass. The existing initializer
reported PhxAMDFB on the panel at 18:37:10 UTC+08:00 and released the armed
display path at 18:37:18. Three captured WindowServer reports then showed
`EXC_CRASH` / `SIGABRT` in `CoreDisplay::DisplayPipe::RunFullDisplayPipe`.
The unchanged early-failure monitor detected three reports, disabled M2 and
rebooted. The firmware-fallback boot began at 18:38:22 and its initializer
completed at 18:38:39. This observed software fallback does not validate
recovery from a hard kernel or bus hang.

All three crash reports contain the candidate RADV and installed plugin's
matching Mach-O image identities. Their candidate paths are redacted by the
reporter, so those fields alone cannot establish an exact path. Independent
same-process, same-boot loader logs corroborate the installed candidate's
resolved path and image identity, plus the installed plugin's path and image
identity, before each captured abort. Current file hashes still match the
pinned candidate and plugin. The failure therefore cannot be attributed to
WindowServer simply retaining the old RADV library.

Each of those three processes logged `vkAllocateCommandBuffers` returning
`-2`, followed by a nil command buffer, and later `vkAllocateMemory(image)`
returning `-2` and `newTextureWithDescriptor: FAILED`. Reporter logs immediately
after the corresponding fault captures identify the assertion as
`m_combinedLUTTexture - Failed to get a MTLTexture`. The observed failing
allocation and texture-creation paths are established; their underlying
kernel, winsys, resource-lifetime or memory-type cause is not. The plugin's
"VRAM full" diagnostic is not independent proof of global VRAM exhaustion.
The checked per-process log windows contain no spelled-out device-lost or
backend-disable marker; this does not exclude an unlogged GPU fault.

None of the three faulting threads has the prior `radv_destroy_cmd_buffer`
cleanup crash stack. This is a limited observation of this attempt, rather
than proof that every cleanup defect or the original allocation failure is
resolved. The earlier bounded compute pass remains a compute-only result.

Postboot readback found build 35 and NMXAccel present, PhxAMDFB absent,
IONDRVFramebuffer present, all three display switches zero, frame samples
remaining zero and one-shot/persistent/stop/pending markers absent. All 15
active and 15 retained-original plugin/runtime entries match. Among the 55
installed baseline entries, only the initializer-generated firmware-address
log changed; the other 54 entries match. The candidate runtime pointer remains
selected. Two shutdown-stall diagnostics were retained privately without
interpreting them as evidence of a hard GPU hang or guaranteed recovery.

Collection and analysis added no GPU submission, initialization replay,
arming, installation or reboot. No automatic retry is scheduled. Preserve
this firmware-fallback state and investigate the native command-stream and
image-memory allocation refusals before another hardware test. The complete
installed userspace provenance, desktop stability and physical display size
remain unresolved. See the separate
[desktop-result record](validation/radv-installed-default-m2-result-20261113.json).

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


## Native allocation investigation, 2026-11-13

After sudo-mcp authentication was restored, the completed failed-desktop boot
was queried again with administrator privileges. The bounded query returned
144 events, byte-for-byte identical to the earlier unprivileged query. Neither
query contains the transport's original allocation refusal. No new hardware
attempt was made. The privileged retry therefore establishes access to the
stored logs, not an allocation root cause.

The earliest saved command-buffer refusal is at 18:37:20.689257 UTC+08:00,
well before the three archived CoreDisplay aborts. The same WindowServer
process reports a non-nil 16384-by-1 texture object at 18:37:20.689593. This
is evidence of selective failure reporting, not proof of a fresh native BO
allocation after the refusal. It does not establish global exhaustion or a
particular pool limit.

Source review identifies three independent losses of diagnostic information:

- `acd_kr_to_errno` maps both `NoMemory` and `NoResources` to `-ENOMEM`.
- RADV buffer creation maps several VA reservation, BO allocation and GPU-map
  errors to `VK_ERROR_OUT_OF_DEVICE_MEMORY` (`-2`); command-stream CPU mapping
  failure can also become `-2`.
- Existing native transport tracing and RADV buffer-allocation messages use
  stderr. The saved unified-log window has no matching original refusal, so
  absence of those lines does not identify the failing branch.

Build 35 uses software budgets per native client: visible VRAM 256 MiB,
high-pool VRAM 1536 MiB, GTT 512 MiB with a 256 MiB single-BO limit, and host
imports 4096 MiB with a 1024 MiB single-import limit. The client has 4095
nonzero BO handles and 4096 map slots. These are source limits, not measured
failed-boot usage or evidence of global physical-memory exhaustion. In this
allocator a request containing VRAM and GTT still enters the VRAM branch;
GTT spill is not implemented merely by setting both domain bits. That is a
candidate budget mechanism, not a demonstrated explanation of this failure.

A third downstream RADV patch now records native BO creation, host import,
GPU map/unmap and CPU-map refusals before raw IOReturn information is lost.
Each record includes operation, direct/proxy route, actual wire selector,
original IOReturn, request size/alignment/domain/flags where available, BO
handle and a sample ordinal. It logs at most eight failures per operation per
process using a saturating atomic counter. Both stderr and `os_log_error`
receive the record; no environment override is required. CPU/GPU/host virtual
addresses and data contents are omitted. The diagnostic makes no extra IOKit
call, retry or GPU allocation, preserves errno, return status and output behavior,
and does not change memory budgets or fallback policy.

The pinned MIT Darwin transport is retained as a hash-verified test fixture.
CPU-only fault injection executes the actual patched transport with explicit
IOKit/logging doubles: 54 cases cover original return/output behavior,
direct/proxy selectors, five operation classes, four refusal codes, successes,
malformed and unrelated calls, privacy, saturation, and 1200 concurrent calls.
ASan/UBSan validation passed locally. All 414 source tests passed with Python
3.12, and the hosted source-test job passed. The existing manual RADV workflow
now accepts `retain_artifacts=false` to compile the real RADV with Apple logging
and run the four no-device refusals while skipping package creation and artifact
upload. Its default remains true for the separately authorized seven-day package;
the full-stack publication block is unchanged. The broader source build includes
an expensive LLVM rebuild, so the scoped RADV job is the native acceptance check
for this diagnostic.

The scoped run `43428606885` passed on `macos-15-intel` at commit
`cc6bae10cd84b576dfa43178df5d112127e6b8e5`: actual RADV compilation, ad-hoc
signing and signature/dependency checks, exact prepared-transport comparison,
and all four no-device refusals completed successfully. The 25 focused RADV
checks also passed after the retention-control change. Both package creation
and upload were independently verified skipped; the run has zero artifacts.
The earlier full-stack run's source job passed, and its long native/LLVM stage
was intentionally cancelled in favor of this scoped validation. This is not
an installed-library or target-GPU acceptance result.

Limits: the patch has not been installed or executed by WindowServer. Real
unified-log persistence and the underlying allocation cause remain unverified.
It cannot report failures confined to userspace VA reservation or host malloc,
and a raw `NoMemory` alone may still require deeper kernel diagnostics to
separate budget, descriptor and page-table failures. QueryInfo lacks a live
handle/map occupancy or host-import budget snapshot, and current-boot counters
cannot reconstruct a prior boot. Preserve the firmware fallback; deployment
and any future hardware reproduction need a separate bounded plan. A read-only
check at 20:29 UTC+08:00 found a later boot (19:13:32), still with build 35,
PhxAMDFB absent, firmware framebuffer present, all display gates and frame count
zero, M2 markers/NVRAM absent, and unchanged candidate/plugin hashes. It is not
the historical 18:38 boot and its counters were not used as failed-boot evidence.

For a later separately planned reproduction, retrieve the exact boot/process
window with a unified-log predicate matching the `radv-native-alloc:` prefix,
and preserve the raw capture only under ignored `build/`. The wire selectors
are 3/21 for direct create/import and 15/16 through the proxy; CPU-map records
use the non-selector sentinel. A saturated operation's later failures are
intentionally omitted. Correlate the first record with the plugin refusal,
not just with the later CoreDisplay assertion.

The final target readback at 20:58:34 UTC+08:00 confirmed the same investigation
boot, build 35, PhxAMDFB absent, firmware framebuffer present, all display gates
and frame count zero, no M2 NVRAM/markers or shutdown process, and unchanged
installed RADV/plugin hashes. The diagnostic is source-validated but remains
uninstalled. See `validation/radv-native-allocation-diagnostic-20261113.json`.

## Installed allocation diagnostic and bounded compute check, 2026-11-13

The owner's continuation of the proposed controlled diagnostic reproduction
was limited to a verified RADV pointer installation and one fresh independent
process check. The RADV artifact exception itself was not used as deployment
authorization. M2 desktop takeover, initializer replay and reboot were excluded
from this execution scope.

Manual run `43431292256`, job `131905168529`, passed on `macos-15-intel`
at source `8ba13b55bc7b19fa962f4673622c766f000910d4`. It compiled and
signed RADV, checked its dependencies and the four no-device refusals, and
published one seven-day RADV-only artifact (`14040835112`). Local static review
verified the Actions ZIP digest, outer archive checksum, all 66 inner manifest
files, the 19 ordered patches, corresponding sources and notices, x86_64 dylib
structure, required exports, strict signature, system-only dependencies, and
the allocation-diagnostic strings and Apple error-logging import. Unchanged
upstream source archives matched the previously verified pinned package. No
candidate code was loaded during this archive review.

The installed diagnostic library SHA256 is
`8ed4e8a6cf77e5cc0aedf9401f33f4aabe2808a7ce722e655b34b66feccfb45a`.
Installation created a fresh versioned runtime and atomically switched only
the existing runtime alias. All other runtime bytes and configuration were
copied identically from the previous candidate. The previous candidate,
protected original runtime and Metal plugin remain intact; no mapped library
was overwritten. An independent pointer/hash readback passed. Fourteen CPU/file
fixtures checked the preparation guards and exact pointer switch/rollback;
they do not prove recovery from a real hardware hang. The new rollback helper
can restore the exact predecessor after a changed boot when its integrity and
pointer checks pass; rollback still cannot replace existing process mappings.

On macOS 26.7.2 / 25G332 with build 35 and M2 off, a fresh ordinary-user
default-route enumeration verified the actual candidate and plugin image
identities. One subsequent Metal compute invocation completed in about two
seconds. All six cases (1, 63, 64, 257, 4097 and 65537 elements) passed exact
result, unchanged-input and output-guard checks, including alternating output
offsets. No driver-selection environment override, initialization, automatic
retry, desktop takeover or reboot was performed. The postcheck found the same
boot, unchanged retained components and no new WindowServer report.

This successful independent-process test did not reproduce the desktop refusal.
Its saved stderr contained zero `radv-native-alloc:` records, and the bounded
administrator unified-log query returned zero matching events. Consequently,
real refusal-log persistence and the original allocation cause remain
unverified; no budget change or allocation fix is justified by this result.

A fresh one-boot desktop plan and helper are prepared, pinned and separately
guarded. Administrator read-only preflight passed; the installed startup and
recovery inputs were checked against the prior reviewed attempt, with one
per-boot generated log pinned to its current value. An authorization-guard
check confirmed that desktop arming refuses without explicit new one-boot M2
and scheduled-restart authorization. At preparation, nothing was armed or
scheduled. The plan uses only one-shot NVRAM arming, keeps the persistent M2
marker absent, and schedules one normal restart after three minutes. It
preserves the existing software fallback and captures the first diagnostic
record grouped by boot and WindowServer process, together with crash/loader
evidence of the actual candidate image. The previous software fallback was
observed; recovery from a hard kernel or bus hang is not guaranteed. A desktop
failure or success must be investigated before any second attempt.

The 25 focused RADV checks passed again with Python 3.12. A final administrator
readback at 21:33:12 UTC+08:00 verified the diagnostic pointer and library,
unchanged retained candidates/plugin, the same boot and firmware framebuffer,
zero display gates/frame count, and absent M2 arming and shutdown state.

See `validation/radv-native-allocation-candidate-20261113.json`. All raw logs,
machine identities, helper programs and operational plans remain ignored and
private under `build/`.

## Authorized single diagnostic desktop boot scheduled, 2026-11-13

The owner separately and explicitly authorized one fresh M2 desktop boot, a
normal restart delayed three minutes, and the existing failure fallback
restart. A fresh administrator preflight passed before execution. The pinned
helper armed only the one-shot M2 NVRAM value at 21:42:19 UTC+08:00 and observed
the scheduled normal-restart process. Its expected restart time is approximately
2026-11-13 21:45:20 UTC+08:00. No persistent M2 marker was created.

Independent administrator readback at 21:42:35 UTC+08:00 confirmed the same
preparation boot, the one-shot arming value, the exact scheduled process
identity, all 52 installed startup/driver/recovery pins, the diagnostic runtime
pointer and library, and unchanged retained candidates, original runtime and
plugin. The current boot still used the firmware framebuffer, with PhxAMDFB
absent and all display gates zero. No initializer was replayed and no current
boot display takeover was performed.

At this checkpoint the attempt was scheduled, with no completed reboot or
desktop result yet. The existing software fallback remained unchanged; recovery
from a hard kernel or bus hang was not guaranteed. The next action is read-only postboot collection using the
pinned collector, then boot/process and actual loaded-image correlation. There
is no automatic second attempt. The original allocation cause remains unknown.

## Diagnostic desktop refusal captured and firmware fallback restored, 2026-11-13

The authorized one-shot completed. Startup recorded PhxAMDFB present at
21:45:52 UTC+08:00 and desktop release at 21:46:02. Four WindowServer processes
then produced crash reports. The installed software recovery detected four
reports, cleared M2 and restarted. The fallback boot started at 21:47:25 and
completed startup at 21:47:36. No second M2 attempt or additional GPU test was
performed during the postboot investigation.

The bounded administrator capture contains **44 actual native refusal records**
from the diagnostic RADV: 43 from four WindowServer processes and one from a
Dock helper, all in the failed boot. The initial collector's substring count
was 45 because it also matched the log command's own audit message in the
fallback boot. Analysis excluded that self-record by requiring the diagnostic
prefix and verified candidate sender image. There are five real boot/process
groups, rather than the initial six. These are bounded samples, not a complete
count of every failure after the per-operation logging cap.

| Operation | Sampled records | Original native result |
| --- | ---: | --- |
| GPU_MAP | 23 | `0xe00002d5`, `kIOReturnBusy` |
| GPU_UNMAP | 9 | `0xe00002d5`, `kIOReturnBusy` |
| BO_IMPORT_HOST | 12 | `0x00000002`, `KERN_PROTECTION_FAILURE` |

No BO_CREATE or CPU_MAP refusal record was found in this capture. The first
GPU_MAP refusal occurred at 21:46:06.420158 for an 81920-byte request. The
diagnostic's real unified-log persistence is now demonstrated. Every one of
the four WindowServer processes has matching same-process plugin/driver loader
records and crash-image identities for the installed diagnostic candidate.
The reports comprise one SIGSEGV with a stack-guard protection failure and
repeated SkyLight render/scissor frames, and three SIGABRT reports in
CoreDisplay paths. They must not all be described as the same assertion.

### Established error provenance

The current kernel source is byte-identical to the build-35 source at
`2a1c771d19893f20f53a54cb1566c376a4c5fbfb`. Nine relevant RADV source files were
reconstructed from the verified candidate's corresponding-source archive and
19 ordered patches; no native driver build was run. The installed SDK headers
confirm the two native error-code definitions above.

In `PhxBringup::vmIdleLocked`, `lastSeq` greater than the conservative
`gpuRetiredLocked()` observation returns Busy before editing GPU page tables.
Both `vmMap` and `vmUnmap` use that guard. For the observed UNMAP results this
is the only Busy return path in the reviewed source. MAP can also return Busy
when `doGemVa` finds an overlapping pending mapping, so the exact branch for
each MAP refusal is not yet recorded.

The exact Darwin call chain returns Busy as `-EBUSY`. Its `acd_cmd_gem_va`
wrapper immediately propagates the refusal; it does not wait for prior GPU
completion or retry Busy. For ordinary BO creation,
`radv_amdgpu_winsys_bo_create` converts a failed GPU map into
`VK_ERROR_OUT_OF_DEVICE_MEMORY`. This explains how a native synchronization
refusal can reach the plugin's generic allocation and "VRAM full" messages.
For example, the last WindowServer process logged two Busy maps at
21:46:50.756596 and 21:46:50.756980, followed by the colour-image `-2` message
at 21:46:50.757199. A request-size or budget increase is not justified by this
error label.

Host import is a separate refusal class. `doBoImportHost` requests
`kIODirectionInOut` and forwards an `IOMemoryDescriptor::prepare()` failure.
The observed raw Mach protection code is consistent with that path, but the
actual page permissions and origin are not captured. In the exact Darwin
transport raw 2 becomes `-EIO`; the host-import caller reports an invalid
external handle. An imported BO's later GPU_MAP failure is yet another path
and must not be confused with refusal of BO_IMPORT_HOST itself.

### Remaining uncertainty and current state

The evidence establishes native error provenance and a VM mutation/completion
contract mismatch. It does not establish whether the retirement guard saw
ordinary in-flight work, a stale or invalid queue-completion observation, or a
GPU hang. The conservative retirement function returns zero for some invalid
observations too. It also does not identify every MAP Busy branch or explain
the host pages' protection failure. A complete allocation/desktop root cause
and a working fix remain unproven.

The existing actual-source CPU harnesses passed 82 BO-retirement cases and
30 BO-create/import cases with address/undefined sanitizers. Their Busy and
cleanup checks confirm conservative refusal behavior with explicit OS/device
fakes; they do not validate desktop liveness or prove a repair.

Independent administrator readback at 21:52:20 UTC+08:00 verified macOS
26.7.2 / 25G332, build 35 and the same loaded kernel image as preparation. The
firmware framebuffer is present, PhxAMDFB absent, display gates zero, M2
NVRAM/markers absent, and no shutdown or GPU-helper process is running. The
diagnostic pointer/library and retained predecessor, protected original and
plugin are intact. Of the 52 startup/driver/recovery pins, only the expected
per-boot generated log changed. No runtime rollback, budget change or fix was
deployed. Current-boot counters reset on fallback and are not evidence of
failed-boot resource usage.

Further diagnosis should record the precise Busy branch, context last sequence,
conservative retirement and queue-observation validity, and the host-import
prepare result. Any correction needs bounded completion synchronization while
preserving the prohibition on editing live page tables and the host-page pin
protections. The one-shot authorization is spent; this result does not
authorize another desktop attempt. Raw captures, source reconstruction and
correlation remain private under ignored `build/`.

The next source-only kernel diagnostic is documented in
[Allocation refusal kernel diagnostic, build 36](ALLOCATION-KERNEL-DIAGNOSTIC.md).
It records the existing refusal branches and same-read queue observations;
it is not installed and does not constitute a fix or a second desktop test.
