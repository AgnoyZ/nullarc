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
