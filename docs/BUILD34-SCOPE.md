# Default build34 only

The owner clarified the development scope on 2026-11-16: focus exclusively on
PhxBringup build34 on the default branch `upstream34/vram-layout-fix`. Its
approved source checkpoint is `64f3d991a4ddc3af5bbf30cbced9f11d3e7dd50c`,
including the already validated A1, A2 and corrected A3 changes. The later
[minimal compute-submit synchronization fix](BUILD34-SUBMIT-MEMSYNC.md) is
derived from that exact checkpoint. Original and equal-footprint NOP controls
failed; the exact ACQUIRE image passed both guarded native dispatches and
independent recovery. Its byte-identical source is integrated on this branch.
This is bounded compute acceptance, not desktop, stability or FPS acceptance.
The subsequent [fixed-image desktop trial](BUILD34-DESKTOP-VALIDATION.md)
passed bounded native/Metal output and about 151 seconds of desktop frame
observation with the retained installed runtime, then independently recovered.
It does not accept persistent adoption, the newer default-branch plugin sources,
PR28 GPU waits, long-run stability or FPS.

Build41 and build42 are withdrawn, not candidates. Do not continue preparing,
compiling, installing, loading or testing them as candidates. Do not rename a
downstream kernel to build34 or relax the original build34 admission checks.
The earlier instruction to do general development on downstream is superseded;
other branches, source experiments and validation records remain historical.

Continue IB wrong-value investigation only against default build34. A further
authorized fix must be a minimal isolated change, preserve the accepted A1/A2/
corrected-A3 changes and keep unrelated downstream wait, lifecycle, ABI and
initialization changes out. A subsequent item must not be promoted on the basis
of a host-only test or a simulated GPU result. The unmodified original34
image retains the native single-IB wrong value; the integrated fix has bounded
native single-IB evidence, while the explicit immutable-tail workaround has
separate transport and bounded complete-Vulkan evidence below. The recovered
machine still runs the original image with GPU off. Default-wait promotion and
persistent accelerated-desktop adoption remain on HOLD. The following records
retain the chronology and scope of earlier experiments, including their failures.

The interrupted build42 user-tool preparation was stopped, and its eight
uncommitted files were withdrawn. No driver was installed or loaded, no native
GPU test was executed and no reboot was requested during that preparation or
this scope correction. Old one-use hardware scopes remain consumed. Existing
installation, recovery, privacy, licensing and explicit-execution boundaries
continue to apply; this scope correction does not arm a new hardware trial.

The subsequent [MEC range diagnostic](BUILD34-MEC-RANGE-DIAGNOSTIC.md) keeps
one upstream initialization lead available as original34-only offline tooling
on this branch. It does not change the production helper/kernel, adopt a
hardware fix or restore either withdrawn candidate.

The subsequent [IB preamble diagnostic](BUILD34-IB-PREAMBLE-DIAGNOSTIC.md)
investigates reused command memory through the existing original34 multiple-IB
ABI. It adds isolated offline tooling and changes no kernel, production
helper, native ABI or default wait/desktop policy. Its two policies require
a fresh control before a separate treatment; CPU mocks are not GPU evidence.
The first bounded NOP-head control subsequently passed both guarded
dispatches and independent recovery. ACQUIRE_MEM was not run because that
control did not reproduce the wrong value. A follow-up single/head/tail
descriptor-order fixture keeps the arena identical and requires a new failing
single-IB control before any further comparison; the production IB fault and
all desktop/default-wait HOLDs remain unresolved.
The subsequent same-binary single-IB scope reproduced the exact fault and a
separate NOP-tail scope passed both whole-arena dispatch checks. Both recovered
and retired independently; see the linked diagnostic's hardware comparison.
This clears only that comparison's reproduction prerequisite. A lifetime-safe
change in the real RADV submission path and its own bounded native verification
are still required before claiming a production fix.

The subsequent [real RADV IB-tail source experiment](BUILD34-RADV-IB-TAIL.md)
adapts three pinned MIT Mesa transport/core files with a separately owned,
connection-lifetime immutable NOP BO. It is explicitly opt-in, compute-only and
excluded from WindowServer. Its CPU tests execute the actual marshaller,
shared core/VA allocator and native-probe control flow with fake platform ops;
native compilation does not execute the signed probe. This is an unpromoted
source workaround, not an installed runtime. Its subsequent fresh same-binary
hardware comparison reproduced the exact fault with the workaround disabled,
then passed both guarded compute dispatches with the immutable tail enabled.
Both scopes independently recovered and retired. This verifies only the bounded
real transport reproducer, not full RADV/Vulkan, graphics, desktop or FPS use.
Original34 kernel/helper/ABI and all desktop/default-wait HOLDs remain.
The subsequent complete RADV dylib compilation and guarded CPU-only load passed
with the same three transport source hashes. That private library has not been
installed or executed on the GPU; full-runtime Vulkan/graphics acceptance
remains separate from the bounded transport test.
The subsequent explicit-tail enumeration ownership patch changes only one
additional MIT Mesa Vulkan source file. It keeps profile/query/logical-device
use on one shared core when the tail is explicitly enabled, preserving the
single-client trial boundary and leaving the three hardware-tested transport
files unchanged. Its actual-function CPU tests do not constitute full Vulkan
or GPU acceptance. The baseline's orphaned profile sync clone is recorded and
unchanged; default/desktop/wait HOLDs remain.
The subsequent [complete-runtime probe preparation](BUILD34-RADV-RUNTIME-PROBE.md)
adds a separate IOKit guard and two-pass Vulkan program. Its 15 complete-program
and 25 guard CPU cases use fake platform ops; preparation ran only a no-client
native guard self-test. A subsequent fresh complete-Vulkan hardware scope
passed both guarded dispatches with actual same-address IB bytes changed,
native sequences 1/2 retired and the explicit immutable tail last. Recovery
returned to GPU-off and the scope was independently retired. A prior launcher
path error was separately recovered/retired before the original initializer
or Vulkan could start; it is not counted as acceptance. These records verify
bounded opt-in compute only. They do not install the runtime, repair the
unmodified native single-IB path, change default policy, clear desktop/wait
HOLDs or permit replay of any consumed scope.

The subsequent [mismatch observation](BUILD34-IB-MISMATCH-OBSERVATION.md) adds
only post-failure volatile reads and aggregate statistics to the original
single/head/tail diagnostic. Commands, descriptors, waits, original34 kernel
and the hardware-tested Mesa transport are unchanged. CPU-injected patterns
test classification, not GPU coherency. It cannot clear any existing HOLD
and requires its own fresh recovered/retired hardware scope. That subsequent
scope observed all 256 output words matching the previous pattern, with no
shader/command/guard mismatch or change across two immediate reads. The
controller's post-probe admission assertion failed, so the independently
parsed observation is not a successful trial or fix acceptance. Independent
recovery verification and consumed-job retirement passed. The original
single-IB fault and all existing HOLDs remain unresolved.

The subsequent [post-failure delayed observer](BUILD34-IB-LATE-OBSERVATION.md)
adds one explicitly selected 100-ms CPU resample after the original mismatch.
It changes no commands or native waits and never converts late-correct output
to success. Its offline verification is not GPU acceptance or permission to
replay a consumed scope; original34 and desktop/default-wait HOLDs remain.
Its subsequent fresh hardware scope still observed all 256 previous-pattern
words after a measured 101.637 ms. Observation collection, independent
recovery and retirement completed, while the original GPU mismatch remained
a failure. No wait-based repair, native single-IB fix or root cause is claimed.

The subsequent [output-target comparison](BUILD34-IB-TARGET-SWITCH.md) adds
two explicitly selected single-IB modes with identical dual-region poisoning.
Only the second rewritten command's destination changes from A to B. Full
arena checks and separate region counts require a fresh same-binary failing
control, independently recovered and retired before a separate treatment.
Offline preparation is not GPU evidence or permission to replay a consumed
scope. The unchanged original34 single-IB fault and existing HOLDs remain.
Its fresh target-control hardware scope subsequently reproduced the precise
second-pass wrong value, with 256 previous-pattern words in A and B remaining
poison. Independent recovery and retirement completed. This clears only the
fresh-control prerequisite for a separate same-binary destination comparison;
the original GPU failure is retained, not promoted to acceptance.
The subsequent separate same-binary target-switch scope found all 256
previous-pattern words at old destination A while new destination B remained
poison, despite the CPU-visible command page matching expected bytes.
Independent recovery and retirement completed. This records an old
destination/parameter combination, not a proved CP/cache root cause or a
native fix; all existing HOLDs remain.

The subsequent [outer-ring padding audit](BUILD34-RING-PADDING-AUDIT.md)
finds a pinned upstream GFX11 publication-framing difference and tests a
two-site compute-only padding idea in the actual extracted original34 submit
function with CPU fakes. It changes no production kernel/helper/ABI and
builds no kernel candidate. Source arithmetic and fake-platform checks are
not GPU acceptance; ring-size compatibility and a separately pinned strict
hardware proposal remain necessary. All existing HOLDs remain.
The subsequent CPU-only revision withdraws the initial after-fence padding
order and places padding before the final RELEASE_MEM, matching original34's
fence-based end-of-frame accounting. The revised actual-function tests also
cover the initializer's 1024-dword compute ring and successive history-slot
reuse. This detects a source-level ownership risk in the earlier experiment;
at that CPU-only stage neither version had become a kernel candidate or
GPU-validated repair.
Subsequent owner continuation separately authorized preparation of a
[privately built original34-derived ring-padding candidate](BUILD34-RING-PADDING-CANDIDATE.md).
Its two function edits are unchanged, and an explicitly reviewed output-only
PCI-match restriction makes bundle metadata identical to the original-image
control. Native compilation/signature/static identity checks do not install
or load it, change the production source or original admission, arm a hardware
scope, validate a repair or clear any existing HOLD.
The subsequent [read-only loading-route audit](BUILD34-RING-PADDING-LOAD-ROUTE.md)
confirmed that original34 is boot-injected. It established neither a live
replacement route nor candidate-to-original recovery, and made no deployment,
GPU attempt or reboot. The candidate remained uninstalled at that checkpoint.

The later owner-authorized [internal-disk ring-padding comparison](BUILD34-RING-PADDING-HARDWARE.md)
completed a fresh original control followed by the exact derived candidate.
Both failed the second single-IB dispatch at `0x2010` (`0xde` versus `0xdf`),
with all 256 output words retaining the previous pattern. This candidate is
rejected as a repair and not promoted. Independent recovery and retirement
verified original34 loaded, GPU-off, all 347 original EFI files and 46
protected files unchanged, no new matching reports and no remaining trial or
restore jobs. A mounted-EFI refusal by the candidate recovery observer was
retained and separately resolved through new-boot recovery-only verification;
no GPU work was replayed. Original kernel/helper/ABI and accepted A1/A2/
corrected-A3 source remain unchanged. The native defect and existing HOLDs
remain; no next GPU scope is armed.

The subsequent [outer-ring memory-sync preparation](BUILD34-OUTER-MEMSYNC.md)
derives equal-footprint NOP and ACQUIRE prefix experiments from original34,
preserving production source and all existing HOLDs. Three actual-function
CPU policies and both private native builds passed; neither changed image had
been installed, loaded or GPU-tested at the preparation checkpoint. The later
[fresh original/NOP hardware comparison](BUILD34-OUTER-NOP-HARDWARE.md)
reproduced the same `0x2010` (`0xde` versus `0xdf`) second-dispatch fault in
both scopes. Independent recovery, retirement and final original34/GPU-off
read-back passed, including the exact 347-file EFI baseline and 46 protected
files. Shared bounded EFI serialization avoided the earlier observer mount
race. NOP is rejected as a repair; this meets only the prerequisite for a
separate equal-footprint ACQUIRE comparison. ACQUIRE remained uninstalled and
GPU-untested at that checkpoint. Its subsequent
[independent ACQUIRE scope](BUILD34-SUBMIT-MEMSYNC.md) passed both guarded
native single-IB dispatches, recovered and retired; the exact two-site source
change is now integrated, with the original admission unchanged. No consumed
scope is replayed, hardware task armed or desktop/wait/FPS HOLD cleared.

The owner's subsequent request to test and integrate several PRs authorizes
the narrow [plugin source batch](BUILD34-PLUGIN-PR-INTEGRATION.md): upstream
PR16, PR19 with a tested zero-progress-write correction, PR15 and PR22. Each
stage passes CPU behavior tests and native compilation before the next is
applied. This extends only four nmplugin source files from the accepted
checkpoint; original34 kernel, ABI, production helper and A1/A2/corrected-A3
behavior remain preserved. It is source integration, not hardware promotion:
the IB result and existing GPU/desktop HOLDs remain unchanged.

The subsequent PR28 wait-timing request adds a separately tested,
[bounded publication-wait source adaptation](BUILD34-PR28-WAIT-TIMING.md).
It remains explicitly opt-in and always excludes WindowServer. Expiry is
reported as publication unconfirmed and does not retire pending work or forge
completion. This does not promote the default wait policy, change the native
fence timing, authorize deployment/GPU work or resolve the existing HOLDs.

The owner's later installation and desktop-test request was followed by a
[fresh installation/native prerequisite trial on 2026-11-17](BUILD34-PR28-WAIT-TIMING.md#subsequent-requested-installation-and-desktop-prerequisite-test).
The candidate plugin installed and loaded in a new process, but the unchanged
original34 native probe again failed its second guarded dispatch at `0x2010`
(`0xde` instead of `0xdf`). No desktop accelerator was claimed and no PR28 GPU
publication wait was exercised. The pre-test plugin was restored, one recovery
reboot returned to GPU-off/firmware framebuffer, and the consumed job was
removed. This does not clear any existing HOLD or authorize automatic retries.


## Upstream history reconciliation on 2026-11-18

The owner's request to resolve the 46-commit upstream history gap is recorded in
[the per-commit compatibility merge review](UPSTREAM-SYNC-20261118.md). The
merge retains the complete pre-merge `src/` and `tools/phxctl/` trees and all
existing hardware records, including A14's desktop-tail failure. Only the
release-package PCI guard, its CPU test and the output-ignore rule are adopted
from upstream; the other runtime changes are explicitly deferred. Ancestry is
not functional adoption or hardware acceptance. Future merges will not re-offer
the deferred patches automatically; use the disposition ledger for a separately
reviewed minimal build34 backport. All existing scope, publication and hardware
execution boundaries continue to apply.

## 2026-11-18 local installation clarification

The owner separately requested local installation, hardware acceleration and
desktop takeover on the default build34 branch. A fresh supervised activation
from source checkpoint `1d4968fbc2ce988c77bdd85b2ec36f435b57f496` passed bounded
native, Metal, GUI frame and active-demand compositor checks and remained
enabled after correcting an installation-monitor OFF-marker regression. This
is an experimental local opt-in, with exact backup and independent failure
recovery retained. It does not clear the unresolved long-term stability,
background-stutter, sleep/wake or default PR28 wait-policy holds. Build41/build42
remain withdrawn. See [the installation record](BUILD34-LOCAL-INSTALLATION.md)
for the earlier controller-triggered rollback, current live readback and limits.

## Owner-selected optimization baseline and monitoring policy

On 2026-11-18, after the successful local activation above, the owner requested
that monitoring be stopped and that this running installation become the
baseline for subsequent optimization. The runtime source checkpoint is
`1d4968fbc2ce988c77bdd85b2ec36f435b57f496`; its accepted bounded hardware results
were published in `d369e219f3986b82a9424cef315459a3c9e45a98`. Continue from the
default branch containing these commits. The earlier `64f3d991` checkpoint
remains A1/A2/corrected-A3 provenance, rather than a request to discard the
subsequently accepted minimal IB correction or plugin integrations. Build41
and build42 remain withdrawn.

The resident installation monitor was stopped and its launch service disabled
without changing the loaded kernel, plugin or active desktop controls. The
owner-selected startup policy retains bounded initialization/admission checks
and manual recovery backups, but ends supervision after startup completes and
does not invoke the continuous post-startup hang watcher. Its 25 CPU tests,
shell/plist syntax checks and installed-policy readback passed. No new GPU
workload or reboot was run for this policy change; its next-boot behavior is
not yet hardware-accepted. The original frozen trial evidence and protected
startup script remain intact. Do not silently restore resident monitoring or
post-startup automatic rollback during later optimization. OS watchdogs and
security settings are unchanged.

The local opt-in is still experimental. Existing limits on long-term stability,
background stutter, sleep/wake, physical scanout FPS and the disabled default
PR28 wait opt-in are unchanged. See the
[installation-policy update](BUILD34-LOCAL-INSTALLATION.md#owner-requested-monitor-shutdown-and-future-baseline)
and [sanitized baseline record](validation/build34-owner-baseline-20261118.json).

## Later local PR28 daily-wait selection

The owner's subsequent 2026-11-18 request enables PR28 waiting for newly
started ordinary applications through the installed plugin's existing
persistent configuration. This supersedes the prior local default-off setting;
the compiled policy still requires opt-in and WindowServer remains excluded.
The 250 ms budget, pending-work semantics, accepted build34 kernel/plugin
images and disabled resident monitoring are preserved. The exact configuration
allowance and startup-policy snapshots are recorded separately; the frozen
trial contract and historical evidence are unchanged. All 46 CPU methods,
fresh installed-plugin configuration checks and 18 runtime-access checks passed.
No new GPU workload or reboot was performed, and long-term stability, FPS and
next-boot behavior are not newly accepted. See the
[daily configuration record](BUILD34-PR28-WAIT-TIMING.md#2026-11-18-owner-selected-daily-configuration).

## Local ACPI shutdown candidate

The owner's subsequent shutdown request is isolated from driver development.
The [S5 candidate and rollback record](BUILD34-ACPI-S5-CANDIDATE.md) preserves
the accepted build34 runtime, enabled local PR28 daily setting and disabled
resident monitoring. It adds one local table, one exact native-method rename
and narrowly derived EFI expectations without rewriting historical contracts
or changing kernel/plugin images. Compilation, 76 CPU checks and independent
on-disk EFI verification passed. Loading the table on a new boot and physical
shutdown acceptance remain pending; this does not establish a root cause,
new GPU performance result or build41/build42 candidate.

The owner's subsequent restart passed independent verification of the exact
loaded candidate SSDT/native rename, full EFI/recovery checks and current-boot
bounded accelerated desktop admission. The one-shot startup supervision ended
and no resident monitor remained. Accepted kernel/plugin images, the local
PR28 daily setting and security are unchanged. This supersedes only the pending
table-load/next-boot status above; physical shutdown and long-term stability/FPS
remain pending. See the [separate reboot readback](validation/build34-acpi-s5-reboot-20261118.json).

The owner then reported unsuccessful shutdown with the candidate loaded.
The failed local ACPI candidate was withdrawn using its exact guarded rollback;
independent verification matched the original 357-file EFI manifest and
accepted build34 images. Acceleration/desktop takeover, daily PR28 waiting,
bounded startup admission and disabled resident monitoring are preserved.
The in-memory candidate remains until the owner's next restart; no power
action was executed or scheduled. Physical shutdown is not repaired and its
precise physical failure mode still requires confirmation. This supersedes
the candidate's pending-acceptance status, not its historical loading evidence.
See the [failure and rollback result](validation/build34-acpi-s5-failure-rollback-20261118.json).

## Native 2× HiDPI

Build34 adapts QiRanChenk's native panel capability hint from
[commit `5f6a231`](https://github.com/QiRanChenk/nullarc/commit/5f6a231d05bc8c502a2a23294d2469bdceae0f75).
The change belongs to the existing PolyForm Noncommercial PhxAccel component.
This adaptation defaults to off. With either the dedicated `phxfb-hidpi`
NVRAM variable set to the single ASCII byte `1` or the legacy boot argument
`phxfbhires=1`, mode 1 adds `kDisplayModeValidForHiResFlag` to its existing
flags for an eligible 32-bit GOP raster. The driver reads the dedicated key
without modifying it or changing the separate one-use `phxfb-boot` gate.
`PhxFBHiResModeFlag` reports the hint and CoreDisplay chooses the logical mode.
An eligible 2560×1600 scan-out can back a 1280×800 logical desktop on the same
physical raster, pitch and timing. The single-mode scan-out contract also
applies to future direct present work.

`make test-upstream34-panel-timing` checks that absent or malformed NVRAM data
does not opt in, the legacy boot argument still works, and mode information
differs only in the HiRes bit. The offline DCN firmware sample stage pins the
updated framebuffer source by exact SHA-256. Target acceptance requires checking
the current logical and backing dimensions and refresh in CoreGraphics on a
separately authorized boot. To disable the hint on the next start, remove both
opt-ins if present.

The [ThinkBook branch at `fe3ea7d`](https://github.com/dandingdjianjiao/nullarc/commit/fe3ea7de558803181d4983869aac60765b6eabc2)
applies the hint to the existing GOP output, while QiRanChenk limits it to
the panel head. Both advertise HiRes by default and provide `-phxhidpioff`.
Build34 keeps its existing mode flags, including the gamma flag, and makes
HiRes an explicit opt-in for a controlled test. No extra mode, scaler or
scan-out buffer is introduced, and the existing present copy remains.

### Local preflight, November 25, 2026

On macOS 26.7.2 (`25G332`), the signed x86_64 PhxAccel candidate changes only
the framebuffer source from the R2a recipe. The control build reproduces the
installed R2a executable byte for byte. An offline link from a private bundle
path returned success but dropped the sole PhxAccel record: boot/system/aux
record counts were `232/180/3` rather than `232/180/4`, with 29 codeless records
unchanged. The full [cache metadata check](../tools/check_build34_cache_metadata.py)
refused the candidate; neither the installed executable nor the AuxKC changed.

The two installed startup jobs still refer to the retained R2a scope, whose
daily journal records `daily-startup-failure` and a rollback decision. The
current boot loads the exact R1b PhxBringup but not PhxAccel. CoreGraphics
reports 2560x1600 logical and backing dimensions with no 2x mode exposed;
this is the firmware baseline, not a HiDPI candidate result. No candidate
was installed or loaded, no boot argument was changed, and no restart was
requested.

### Baseline restored; prior candidate not booted

The separate, owner-authorized baseline recovery boot completed on November
25, 2026 at 20:10:25 Asia/Shanghai. A fresh scope replaced only the two startup
job definitions and added a finite startup watcher. It retained the existing
45/150/300-second gates and permitted no automatic power recovery. The old
journals remain intact. Independent readback passed the exact loaded R1b/R2a
images, mapped WindowServer plugin, complete EFI and cache, loaded AML,
same-WindowServer progress and all four zero error counters. The watcher
retired. CoreGraphics reports the baseline's current 2560x1600 logical and
backing dimensions at 120 Hz, with no native 2x mode exposed.

After baseline admission, the [approved-path offline cache recipe](BUILD34-PRESENT-COPY.md)
produced a private HiDPI AuxKC with all 416 records and 29 codeless entries.
Only the PhxAccel image changed; the full metadata gate preserves bundle paths,
matching policies, dependencies and boot/system links. The independent guard
verified restoration of the signed R2a executable. The installed AuxKC and
startup jobs are unchanged from the recovered baseline, which passed readback
again. The HiDPI candidate remains uninstalled and unloaded.

Read-only inspection of the active OpenCore configuration found `boot-args`
in both NVRAM `Delete` and `Add`. A macOS-only write to `boot-args` would lose
the HiDPI opt-in at the next OpenCore boot. No EFI or boot-argument change was
made and the distinct HiDPI restart remains unused. Those preflight results
apply to the earlier boot-argument-only candidate, not to the dedicated-key
change. A fresh candidate and cache must pass full validation before any
separately authorized installation. Verify that OpenCore does not rewrite the
dedicated key and confirm its exact value before and after boot. Acceptance
then requires the exact loaded image, the HiRes property, and the **current**
1280x800 logical / 2560x1600 backing mode at the unchanged 120 Hz and physical
timing. Enumeration or the registry property alone is not a pass.

The dedicated-key candidate builds and passes x86_64 architecture and strict
signature checks using the same frozen R2a sources and SDK, with only the
framebuffer source replaced. The rebuilt control matches the accepted R2a
executable byte for byte; the candidate has the same undefined imports.
Offline checks passed 43 timing cases, 542 panel callback assertions, 3,646
framebuffer assertions and 25 cache metadata fixture tests. These checks do not
link a new AuxKC or exercise the physical panel. The dedicated key was absent
on readback; no NVRAM, EFI, installed driver or startup job change was made
and no restart was requested for this candidate.

Independent readback still accepts the running R1b/R2a baseline. The exact
active OpenCore configuration does not list `phxfb-hidpi` in `Add`, `Delete`
or `LegacySchema`, and does not enable `OpenVariableRuntimeDxe`. This static
check does not prove that a newly written variable survives a boot.
Two isolated-volume AuxKC attempts rejected the KDK even though the installed
KDK reports build `25G332`; neither produced an admitted candidate cache.
The standard-path input swap requires a fresh bounded guard and exact R2a
restoration before the complete 416-record/29-codeless comparison. It has not
been run for the dedicated-key candidate. No live inputs were changed.
