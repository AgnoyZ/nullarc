# Isolated build-34 A1/A2/A3 backports

Latest hardware disposition, **2026-11-16 12:49 +08:00**: A1 and cumulative
A1+A2 passed their bounded real-GPU gates. A3 **failed** fresh-boot timing
admission before its Metal probe; it is not accepted for adoption. The exact
accepted A2 kext and AuxKC have been restored on disk. The current recovery
session uses the firmware framebuffer with PhxAccel not loaded and GPU-off
present; restoring disk files is not evidence of A2 being loaded again.
The consumed A3 witness is retired, with no automatic retry. The chronological
source/preparation checkpoints below retain their original scope.

Owner request: 2026-11-16. Candidate branch: `backport/upstream34-a1-a3`,
based on default checkpoint `90bb06f6f9255cb5a16cc5eb87e78032566b2000`.
The default branch itself is unchanged. Complete A1 tests before changing A2,
then complete A2 tests before changing A3. Each stage is a separate commit.

All three source/native gates passed in that order. A1 checkpoint: `11cb144`;
A2 checkpoint: `79c0a0f`; A3 is the final cumulative candidate. Reproduce A1/A2
on their respective checkpoints; use `--stage a3` on the final tree. A stage's
gate deliberately refuses source changes belonging to a later stage.

The original build-34 `src/phxbringup`, native ABI, user helpers, firmware
sequence and geometry correction stay byte-identical to the baseline.
Existing licence/notice files are preserved. No driver is installed, loaded,
or initialized by the tests, and no GPU submission or display takeover occurs.
Host-test success is not hardware acceptance or an FPS measurement.

## A1 — plugin keys and descriptor masks

Selected source and tests from downstream `4d09aa9`, `8533c26`, `0c594e1`.
Reviewed upstream origins: `55764a0b69658a92870fc2b75e0be3a695382e38`,
`394f162ae7bf5cc9d57bb673a9a6b326c46c325e`,
`5a8a088011946c8089bb27e10d0dba117bf1b48e`.

Sampler slots 0–15 share immutable decimal strings; other indices keep the
legacy formatting. Surface writer and monitor lookups use compact keys while
retaining distinct full-width large-plane identities. These are allocation/key
optimizations with equivalent identity semantics, not established rendering fixes.
Ordinary descriptor snapshots exclude independently bound framebuffer-fetch
set 3 as well as heap set 2. Existing conservative fallbacks remain.
The CPU fixtures cover `NVMTL_DESC_MASK=0` legacy behavior. The release plugin's
existing constructor clears inherited `NVMTL_*` variables, so setting a shell
variable alone is not a verified runtime rollback: an isolated diagnostic probe
would need to restore it after loading and before first use, or revert A1.

Source/helper files remain covered by `src/nmplugin`'s PolyForm Noncommercial
1.0.0 terms and required NullMoth notice. The sampler fixture retains its SPDX;
other test files use their existing root/component terms. No external binary,
firmware or runtime library is imported or published.

Reproduce on Intel macOS with the Vulkan-Headers checkout at
`6802bb4733b63ed5efd3adb308a6c885ef180ea1`:

```sh
python3 tools/test_upstream34_backport.py \
  --vulkan-headers /path/to/Vulkan-Headers --out build/backport-a1
```

The gate runs the baseline unit and geometry suites, actual Foundation sampler
and IOSurface registry/monitor bodies, and actual descriptor parsing/snapshot/
writer bodies in unset/0/1 modes under ASan/UBSan. The production plugin is
compiled and linked for x86_64, ad-hoc signed, checked for its device exports,
and signature/architecture verified without loading it. Raw logs/binaries stay
ignored under `build/`; only sanitized result summaries are committed.

2026-11-16 gate: **passed**, macOS 26.7.2 / 25G332, Apple Clang 21.0.0.
The original unit suite passed (firmware parser inputs absent: that portion
explicitly skipped); all 20 geometry/script tests passed. ASan/UBSan checked
517 sampler indices/262,144 lookups, 77 surface identities/16,384 concurrent
cycles, and 321 descriptor cases in each unset/0/1 mode with zero legacy
mismatches. Full plugin compilation/link/signature/export checks passed,
retaining 336 existing compiler warnings; this is not a warning-free build.
All 172 protected baseline files matched. Sanitized evidence:
`validation/upstream34-backport-a1-20261116.json`.

Rollback is a normal revert of the A1 commit after any later dependent stages.
The installed build-34 stack is unchanged, so this source work needs no runtime
rollback. Real Metal rendering, framebuffer fetch, display output, FPS and
long-duration stability remain untested for this candidate.

## A2 — framebuffer pool and alias retry

A1 passed and synchronized as `11cb1445b90dc3620afef313f1a811eb3b27e7d7`
before A2 edits began. Sources: downstream `bf7d37a` and `47faf8d`, limited to
framebuffer pool/alias behavior and the local accelerator policy header. There
is no copy of the downstream kernel policy/ABI or replacement bring-up binary.

Unpublished geometry consumes the bounded 3,600-present wait budget rather
than one of the three verification attempts. Actual mapping failures and pixel
mismatches still consume verification attempts. Acceptance still requires all
sampled pixels to match the BAR view with at least one nonzero sample; failure
keeps the BAR fallback. Pool frees validate integer, aligned, nonempty extents
before deallocation; range-allocator failure tries the next smaller pool.

```sh
python3 tools/test_upstream34_backport.py --stage a2 \
  --vulkan-headers /path/to/Vulkan-Headers --sdk /path/to/MacKernelSDK \
  --out build/backport-a2
```

MacKernelSDK is pinned to `3f750085caa17ec3a7880f11c11bf4f48cd6a164`.
The cumulative gate checks the unchanged A1 source against its successful
receipt, reruns baseline/A1 regressions and compiles the actual alias/pool
method bodies around CPU IOKit doubles under ASan/UBSan. It covers delayed
metadata, wait/verification exhaustion, all-zero and mismatched views, cached
acceptance, mapping failure, allocator fallback and invalid free ranges.
The complete three-translation-unit PhxAccel is compiled, linked and signed,
then its signature/architecture verified without loading it. Native firmware,
actual mapping attributes, copy latency, alias acceptance on this machine and
any FPS improvement remain untested. Normal source rollback: revert A2 after
any later dependent A3 commit; the installed stack needs no rollback.

2026-11-16 cumulative gate: **passed**. All 20 baseline geometry/script tests
and all A1 suites passed again. Pool/alias boundary policies and 3,646
assertions against the actual framebuffer methods passed under ASan/UBSan.
The complete PhxAccel native compile/link/signature/architecture checks passed
with zero compiler warnings; the unchanged A1 plugin also rebuilt successfully
with its 336 warnings. All 171 protected baseline files matched, and all A1
production source hashes still matched the A1 receipt. Sanitized evidence:
`validation/upstream34-backport-a2-20261116.json`. No hardware test or FPS
measurement was performed.

## A3 — read-only panel timing

A2 passed and synchronized as `79c0a0f486cc9e0e4bbbde80916cc495b9043127`
before A3 edits began. Source: downstream `661fd3c`, upstream PR9
`c9da802a8dbf3753fa15b5cd903934712c3c80f6`, limited to the timing helper,
before/after snapshots around the existing refresh measurement, validated
IOFramebuffer reporting and two registry properties. No HiDPI, EDID, gamma,
display programming, VBL scheduling or present-completion changes are included.
The existing native mode and all original backlight behavior are preserved.

Stable, bounded, fixed-rate progressive snapshots matching the existing
physical geometry yield detailed timing. Unknown/interlaced/variable/changed
snapshots retain the old empty detailed-timing fallback. Pixel clock is an
estimate derived from measured/snapped refresh; min/max remain zero. The
helper and imported 43-case decoder fixture retain their component provenance
under the existing PolyForm terms; that fixture is not a new observation of
this machine. No licence/notice files or third-party binaries are changed.

```sh
python3 tools/test_upstream34_backport.py --stage a3 \
  --vulkan-headers /path/to/Vulkan-Headers --sdk /path/to/MacKernelSDK \
  --out build/backport-a3
```

In addition to all cumulative baseline/A1/A2 tests and native plugin/accelerator
builds, the gate executes the decoder fixture and the actual `measureRefresh()`
and timing callback around CPU mapping/clock doubles with ASan/UBSan. Checks
include stable snapshots, frame-counter wrap, changed mode, missing/short map,
inactive/interlaced/variable mode, wrong active area, too few frames, invalid
rate, zero elapsed time, polarity, invalid output, zero clock bounds and cleared
reserved data. Comparing the full synthetic register array checks that the
measurement body adds no writes. Native SDK compilation validates real IOKit
types independently of the CPU double. Real display acceptance and FPS remain
unmeasured. Roll back by reverting A3 first, then A2 and A1 as needed; the
installed default build-34 stack is unchanged by this source-only work.

2026-11-16 final cumulative gate: **passed**, 15 checks on Intel macOS
26.7.2 / 25G332 with Apple Clang 21.0.0. All baseline/A1/A2 tests passed again,
as did 43 decoder cases and 59 actual refresh/timing callback assertions under
ASan/UBSan. The extracted A2 production-method harness hash is unchanged from
its successful checkpoint. Full native plugin and PhxAccel builds, signatures
and architectures passed; compiler warning counts were 336 and zero,
respectively. All 171 protected baseline files matched. Firmware fixture
parsing remains an explicit baseline skip because its input files are absent.
Evidence: `validation/upstream34-backport-a3-20261116.json`.

These are source and host/native-build results. They establish no installed
candidate acceptance, real Metal output, physical panel cadence, FPS increase
or long-running stability. No deployment, GPU initialization, restart, EFI,
NVRAM or OS-security change was performed.

## Subsequent explicitly requested installation and hardware testing

The owner requested installation/loading tests on 2026-11-16. The preceding
source-only results remain historical. Hardware stages also follow A1, A2, A3;
passing a source gate alone does not advance a hardware stage.

### A1: installed, loaded in a new process, bounded GPU regression passed

The running system remained macOS 26.7.2 / 25G332 in the previously accepted
original-build34 desktop session. Before changing the plugin, the same new
`tools/backport_gpu_smoke.m` executable passed against the original installed
plugin. It verifies PCI 1002:1900 and the actual dyld-loaded plugin image identity,
renders a 4-by-4 pattern into an IOSurface, then checks all 128 integer output
channels after sampling a second texture wrapper at sampler slots 0 and 15.
Each baseline/candidate run completed three real GPU commands. Each command has
a 15-second completion deadline and the process has a 55-second outer limit;
a timeout is failure, with no automatic GPU retry.

Only the A1 plugin was installed, through an atomic bundle exchange after a
complete original-bundle backup, strict signatures, unchanged runtime hashes
and 18 credential-dropped WindowServer file-access checks. The installed
candidate is derived from the exact successful A1 build artifact; bundle signing
changes its signature bytes, while its image identity remains the same. The
original bundle is also retained at the inactive exchange path for rollback.
Neither the kernel driver, AuxKC, runtime, firmware nor startup was replaced.

The installed A1 plugin then passed the identical GPU regression in a new
process, with its actual loaded image verified. Baseline and candidate both
retained the same WindowServer and display gates, continued panel transaction
progress, and had zero new failed transactions, copy skips or matching diagnostic
reports. No WindowServer restart, GPU reinitialization, reboot, EFI, NVRAM or
security-setting change occurred. Public sanitized evidence is
`validation/upstream34-backport-a1-hardware-20261116.json`; raw logs and exact
rollback manifests remain in ignored/private storage, with no binary upload.

This accepts a bounded new-process A1 regression only. WindowServer still uses
its previously loaded plugin. Framebuffer-fetch, cross-process IOSurface
synchronization, physical scanout, FPS, sleep/wake and long-duration stability
are not established by this test. A2 and A3 are not installed by this A1 stage.
On failure, restore the original bundle using the private verified atomic
exchange rollback, then recheck its exact manifest and signature; do not retry
GPU work automatically or advance to A2.

### A2: installed on disk; candidate kernel not yet loaded or hardware-accepted

After the successful A1 hardware receipt was synchronized, the exact A2 native
build artifact was installed through a verified atomic kext-bundle exchange.
The original bundle and original AuxKC both have independently checked private
backups. A matching 26.7.2 / 25G332 KDK produced a private auxiliary collection,
using the existing auxiliary identifiers and approval checks. No authorization
check was skipped. Inspection accepted all 416 cached extension records: only
the accelerator image changed, with all 415 unrelated records identical.
Only then was the candidate AuxKC atomically published with its original
ownership, permissions, flags and extended attributes.

An initial verification attempt refused trailing column-alignment whitespace
in an unchanged AppleMobileDevice path. It restored the original kext and never
published its cache. After an independent exact restoration check, the parser
was corrected to strip only trailing spaces/tabs from the path column. Tests
still reject real version, path and image changes. A distinct second scope
completed installation; the first receipt remains intact and was not replayed.

Post-installation and interruption readbacks verified the candidate bundle and
cache, both original backups and the inactive original exchange bundle. The
loaded accelerator is still the original image in the same accepted desktop
boot. GPU-off remains present, native-display arming and pending markers are
absent, and security settings, Boot/System KCs, startup and runtime inputs are
unchanged. The private root-owned disk rollback script passed a zero-write
preflight; it restores the exact original AuxKC and bundle, without live unload,
GPU commands or reboot. A changed/consumed state requires inspection before any
further write. Public evidence:
`validation/upstream34-backport-a2-install-20261116.json`.

This is **installed-awaiting-reboot**, not A2 hardware acceptance. No A2 GPU
test or reboot has occurred at this checkpoint, and A3 is not installed.
A separate one-use startup observation and an exact loaded-image check are
required before running the bounded GPU regression or advancing to A3.

### A2: fresh one-use boot observation prepared

A new root-owned external witness has passed its actual launchd preparation
role and independent readback. It verifies **2,137 pinned files**, including
2,079 inherited inputs after removing the independently archived, retired job.
Only the three authorized inherited file hashes differ: the A1 plugin image and
the A2 kext's image/Info.plist. The complete A1/A2 installed bundles, inactive
original bundles, original backups, candidate AuxKC, original helpers/firmware,
runtime, frozen interpreter and unchanged bring-up image are checked.
All **61 CPU/permission tests** and **18 WindowServer access checks** passed;
preparation has issued zero GPU commands and no reboot.

The initial unarmed preparation was retired with no reboot or GPU attempt:
its idle-only dispatch template did not admit the original startup's legitimate
long-running post-startup watchdog. A distinct new packet verifies that
watchdog's exact launchd PID/command, current accepted startup block, unchanged
WindowServer, no pending initialization and the existing successful boot
receipts. It preserves the watchdog. Unknown running jobs remain a refusal.
The full real arming admission was independently executed up to, but excluding,
its first mutation. No consumed prior trial is replayed.

The packet permits one ordinary reboot/native-desktop attempt, one GPU-probe
process (three commands, each with a 15-second completion deadline and a
55-second outer process limit), a 300-second independent observation deadline,
and at most one managed recovery reboot. It uses the existing startup and its
specific one-boot display arming; it never invokes an initializer in the
preparation boot, resets NVRAM, writes EFI or changes OS security. The witness
restores GPU-off and removes persistent display rearming after original startup
crosses its off-marker gate. Software deadlines cannot guarantee recovery from
a hard hardware hang.

Acceptance requires original queue/adoption evidence, the actual loaded A2
kernel identity, original Metal publication, the retained A1 plugin's actual
loaded identity and correct real GPU output, native framebuffer, increasing
present and VBL counters, no new failed/copy-skipped transactions during the
sample, one stable WindowServer and no new matching diagnostic reports. FPS
and physical panel cadence are not measured. Arming/dispatch receipts and the
actual next-boot result must be read before claiming a restart or A2 hardware
success. **At this preparation checkpoint the packet is not armed and A3 is
not installed.** Evidence:
`validation/upstream34-backport-a2-boot-preparation-20261116.json`.

### A2: fresh-boot loading and bounded real GPU/desktop regression passed

The one initial reboot was dispatched once and its daemonized root scheduler
was independently verified. The actual fresh boot began at **12:12:11 +08:00
on 2026-11-16**. The witness accepted the trial at 12:14:13; independent
readback completed at 12:15:44. Both the exact A2 accelerator image and the
unchanged original build-34 bring-up image/geometry were verified in the loaded
kernel. Original startup completed its expected compute/graphics results,
queue adoption and accelerator claim without fallback.

The retained A1 plugin passed the identical real GPU regression in a new
process: PCI 1002:1900 and the actual plugin image matched, three commands
completed, and all 128 channels from IOSurface sampler slots 0/15 matched.
The native framebuffer and accelerator were active, with the firmware
framebuffer absent. Across a 12.966-second observation interval, present
transactions increased from **3,810 to 4,691** and synthetic VBL ticks increased
by 1,553. Failed transaction and copy-skip counters were both zero, the same
single WindowServer remained active, and no new matching diagnostic report was
found. These counters are **not a physical scanout or game FPS measurement**.

Read-only current-boot kernel logs also show a 512 MB pool and an alias check
with **4,096/4,096 matching samples, 14 nonzero**. This satisfies the production
alias acceptance condition; no pool-release refusal was observed. It does not
exercise every allocator boundary or demonstrate a causal FPS improvement.

Independent readback checked all 2,137 contract pins before retiring only the
idle external witness. Both original rollback bundles/cache remain exact;
security settings and Boot/System KCs are unchanged. GPU-off is restored,
native-display arming and pending markers are absent, and no managed recovery
was requested. Readback itself performed no GPU submission or reboot. Public
evidence: `validation/upstream34-backport-a2-hardware-20261116.json`.

This passes the bounded cumulative A1+A2 fresh-boot regression, permitting A3
installation after this evidence is synchronized. Long-duration stability,
sleep/wake and FPS remain unmeasured. At this A2 acceptance checkpoint **A3 is
not installed**; no A3 hardware success is implied.

### A3: disk installation independently verified; loaded kernel still A2

A2 hardware evidence was synchronized as `fa14637` before A3 installation.
All 180 A3 source/protected hashes still match its successful 15-check native
gate, and eight focused installer admission/cache tests passed. The exact A3
artifact was installed by atomic bundle exchange with the accepted A2 bundle
and AuxKC backed up. A matching KDK built a separate private candidate cache
without an authorization-skip option; no GPU initialization or reboot occurred.

During that build the active AuxKC changed concurrently. The worker correctly
refused publication and refused to overwrite the then-unrecognized cache; its
failure/recovery-needed receipts remain unchanged. Independent readback found
the intended A3 image and all 415 unrelated cached records unchanged, with no
added or removed identifier. The active/private caches differ as binary files
but their complete 416-record inspections match. Metadata, security settings,
protected files and both A2 rollback backups also match. System logs contain
concurrent kernelmanagerd requests, including an initial approval refusal and a
later reboot-required response; the exact writer is not conclusively
attributed. No approval bypass or security-setting change was performed.

After freezing the active cache hash, rechecking every record, signature,
protected input and backup, independent installation acceptance retained that
verified cache without another cache write. A separate acceptance receipt
supersedes the interrupted worker outcome without rewriting it. The root-owned
A3 rollback helper passed its zero-write preflight against this exact state;
its target is the successfully tested A2 bundle/cache. A2's own original-build34
backups are preserved separately.

The disk state is **A3 installed-awaiting-reboot**. The active kernel remains
the exact accepted A2 image. GPU-off is present, display arming/pending markers
are absent, and no A3 startup observation has been armed. A separate fresh-boot
test must verify actual A3 loading, timing-property consistency and the retained
GPU/desktop regression before reporting A3 hardware success. Evidence:
`validation/upstream34-backport-a3-install-20261116.json`.

### A3: independent one-use fresh-boot observation prepared

The fresh A3 witness passed **68 CPU/permission tests**, its actual launchd
preparation role and a separate execution of all real arming admission checks
up to the first mutation. It checks **2,180 fixed inputs**, retaining 2,136
inherited pins after verified retirement of the A2 witness. Only two inherited
hashes differ: the installed accelerator image and the already-audited AuxKC.
All 18 WindowServer access checks pass and the original post-startup watchdog
is preserved. Preparation has performed zero GPU commands and no reboot.

In addition to the same loaded-image, startup/queues, real Metal, native
framebuffer, frame-progress, stable WindowServer and diagnostic checks used by
A2, this trial reads the new timing registry properties twice. It requires the
accepted **2560 by 1600 / 120,000 milliHz** geometry/refresh to stay unchanged.
A validated timing must have bounded totals and the matching estimated pixel
clock; a legacy fallback must have no estimated-clock property. The snapshots
must agree across the GPU/frame observation. This observer does not open an
exclusive framebuffer connection, directly call the timing callback, program
a display mode or write MMIO. The actual callback remains covered by the
separate 59-assertion production-method host test; the registry check must not
be presented as a direct live callback test or physical clock measurement.

Limits remain one ordinary/native-desktop reboot, one three-command Metal
probe with its 55-second process bound, a 300-second independent observation
deadline, and at most one managed recovery reboot. Original startup/watchdogs
remain in place; software timers cannot guarantee recovery from a hard hang.
GPU-off and persistent-display-arming cleanup remain mandatory. At this source
checkpoint the packet is **not armed**, the kernel still runs A2, and A3
hardware success is pending. Evidence:
`validation/upstream34-backport-a3-boot-preparation-20261116.json`.


### A3: single reboot dispatch independently verified; hardware result pending

After preparation evidence was synchronized as `ae962dc`, the one-use arming
role completed and requested one ordinary reboot. Independent same-boot readback
verified the exact daemonized root shutdown scheduler, its successful parent
exit, the specific native-display arming and the existing M2 marker. No GPU
initializer ran in the preparation boot, and no automatic retry is permitted.
The on-disk A3 candidate awaits actual fresh-boot loading; the running kernel
was still A2 at dispatch readback. The 300-second observation and at-most-one
managed recovery limits remain in force. This dispatch is **not A3 hardware
acceptance**; next-boot receipts must establish the outcome. Evidence:
`validation/upstream34-backport-a3-boot-dispatch-20261116.json`.

### A3: timing admission failed; accepted A2 restored on disk

The actual trial boot began at **12:35:46 +08:00 on 2026-11-16**. Original
startup reported the native panel, expected compute/graphics results, queue
adoption and accelerator claim. Its line-58 shell diagnostic also exists in
the accepted A2 startup log; it is retained rather than described as a clean
startup. The witness completed its exact loaded-A3/original-build34 identity
and geometry checks, then failed at **12:37:34** because
`PhxFBRefreshMilliHz` did not equal the accepted 120,000 milliHz baseline.
No A3 Metal-probe intent, process output or completion receipt exists. Startup
itself had already executed its original GPU work; this is not a zero-GPU
trial, nor a completed Metal/desktop regression.

Persisted trial-boot kernel logs report **25 frames in 200,965 microseconds**,
**124.399 Hz**, totals **2720 by 1694**, and detailed timing marked validated.
The existing approximately 200 ms, integer-frame refresh estimator and its
2-percent standard-rate snapping are unchanged by A3. At a nominal 120 Hz,
one frame in this short window represents roughly 4.2 percent; sampling phase
quantization is a plausible explanation, not an established hardware cause.
A3 newly uses the resulting refresh for an estimated detailed-timing pixel
clock. The evidence establishes inconsistent reported timing, not a physical
panel-rate change or a proven A3-induced estimator regression. The failed
contract was not relaxed and its receipts were not rewritten. No complete
timing-property snapshot survived the pre-snapshot assertion, so a validated
live callback or verified estimated pixel clock must not be claimed.

GPU-off and display-rearming cleanup were restored before the failure. One
managed recovery request was consumed; its shutdown output and a different
actual boot at **12:37:59** verify recovery. Its final dispatch-result receipt
remains absent; shutdown output and the changed boot carry the recovery
evidence, without establishing why that receipt was not saved. The recovery
witness recorded the new boot at 12:38:14 and did not retry. Independent
readback verified all **2,180** contract pins before rollback and found no new
matching diagnostic report. The recovery session had no native framebuffer or
accelerator nodes and retained the firmware framebuffer.

The frozen, one-use disk rollback then restored the exact previously accepted
A2 bundle and AuxKC. Independent verification at **12:49:11** checked their
hashes, signatures, cache metadata and all **416** cached extension records
against A2. All 2,180 witness inputs were checked with only the two exact
rollback substitutions (accelerator image and AuxKC), before retiring the
external job. Both stage/backups remain exact. Security settings, Boot/System
KCs, original startup and runtime inputs are unchanged. Of the installer's 44
older protected-file hashes, only the boot-generated `fwaddr.log` changed;
that private output is not treated as an immutable runtime input.

No live-unload command, GPU initializer, additional reboot or GPU retry was
issued by rollback/readback. A3 was observed loaded early in the recovery
boot; a later independent check found PhxAccel no longer loaded. The agent did
not request that unload, and disk restoration alone does not establish its
cause. The current state is **A2 installed on disk, firmware framebuffer,
GPU-off, accelerator not loaded**, not an active A2 accelerated desktop.
The already-unregistered external A3 job was archived and removed after its
processes exited; the original startup job remains intact.

Adoption recommendation: retain the tested **A1, then A2** changes; **hold A3**.
A3 needs a separate correction and host regression for short-window refresh
uncertainty before any newly scoped hardware experiment. Do not hard-code the
observed panel rate, widen admission after the fact, replay the consumed trial,
or promote this cumulative A3 source branch as hardware accepted. No FPS,
physical scanout cadence, sleep/wake or long-duration stability claim follows
from this attempt. Public sanitized evidence:
`validation/upstream34-backport-a3-hardware-20261116.json`.
