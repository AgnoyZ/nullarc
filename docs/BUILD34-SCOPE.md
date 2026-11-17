# Default build34 only

The owner clarified the development scope on 2026-11-16: focus exclusively on
PhxBringup build34 on the default branch `upstream34/vram-layout-fix`. Its
approved source checkpoint is `64f3d991a4ddc3af5bbf30cbced9f11d3e7dd50c`,
including the already validated A1, A2 and corrected A3 changes. Documentation
commits may advance the branch without changing this driver-source baseline.

Build41 and build42 are withdrawn, not candidates. Do not continue preparing,
compiling, installing, loading or testing them as candidates. Do not rename a
downstream kernel to build34 or relax the original build34 admission checks.
The earlier instruction to do general development on downstream is superseded;
other branches, source experiments and validation records remain historical.

Continue IB wrong-value investigation only against default build34. A further
authorized fix must be a minimal isolated change, preserve the accepted A1/A2/
corrected-A3 changes and keep unrelated downstream wait, lifecycle, ABI and
initialization changes out. A subsequent item must not be promoted on the basis
of a host-only test or a simulated GPU result. The unmodified native single-IB
path's wrong value remains unresolved; the explicit immutable-tail compute
workaround now has separate transport and bounded complete-Vulkan hardware
evidence below. Default waits and accelerated desktop remain on HOLD.

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
