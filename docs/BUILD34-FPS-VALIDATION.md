# Default build34 FPS validation

This follows the independently recovered [PR28 GPU-wait packet](BUILD34-PR28-WAIT-TIMING.md)
and [30-minute low-load desktop observation](BUILD34-DESKTOP-VALIDATION.md).
Only default `upstream34/vram-layout-fix`, PhxBringup build34, is in scope.
Build41/build42 remain withdrawn. The actual OS was 26.7.2, build 25G332.

## First bounded visible-window attempt: not accepted

The fresh single-use packet was derived from source
`a2e71f2e5e4cd83b8a1d45d3f7ba80c312ce3520`. It retained the exact previously
tested compute-sync kernel and PR28 release plugin; no production source,
display parameter or wait policy was changed. PR28 remained default-off and
WindowServer remained excluded. The frame application did not opt in.

Preparation passed 84 CPU/controller/parser methods, eight statistics cases,
the GUI-user CPU route and both wait-observer self-checks. The planned workload
was one visible 1280-by-800 Metal drawable, one command in flight, two seconds
of warmup and twenty seconds of measurement. Each completed frame had to verify
16 frame-dependent pixels before counting. Application completion intervals
used one host monotonic clock; separately reported presentation timestamps
required independent validation. Present/synthetic-VBL counters were not used
as FPS. An independent guardian bounded the trial and recovery.

On the trial boot, initialization, both queue adoptions and both full-arena
native dispatches passed. Independent reparsing also confirmed the normal
PR28 admission workload, its genuine buffer-only fast path and the controlled
timeout followed by verified real completion. The GUI application was then
launched once but exited unsuccessfully with empty standard output and error.
The controller retained the failure and requested recovery without retry.

**There are zero frame records and no accepted FPS result.** The first
controller did not preserve the application's exit code, and the probe had
early exits without diagnostics. The exit subtype and whether the application
had reached GPU/device calls therefore remain unestablished. A launcher,
device, renderer or driver cause must not be inferred from this absence of
evidence. The later desktop-tail observation was not reached. The earlier
accepted PR28 and 30-minute results remain separate records.

## Independent recovery and next prerequisite

Automatic recovery reported no restoration errors. Independent review
reparsed the native and both Metal admission outputs, checked the exact
failure and empty frame logs, and confirmed the original kernel and complete
original plugin. All 46 protected files and 347 original EFI files matched;
protected links, security state and kernel collections were unchanged. No new
matching diagnostic report or remaining GPU/test client was found.

Only the manifest-checked nine recovery files, restore-only job, exact plugin
stage and dedicated frame-application stage/cache were removed. Final
read-back confirmed GPU-off, firmware framebuffer only, EFI unmounted and no
pending test/reboot. The consumed scope must not be replayed. The independent
verifier performed no GPU execution.

A further attempt needs a new scope, explicit launch/exit diagnostics and
CPU-only checks of the actual GUI-user loader route before any GPU trial.
The frame/output/presentation admission checks must not be weakened to obtain
a number. FPS, game performance, physical scanout, input latency, background
stutter and persistent accelerated-desktop adoption are not accepted by this
failed attempt. Sanitized evidence is in
[`validation/build34-fps-20261117.json`](validation/build34-fps-20261117.json).

## Diagnostic follow-up: default Metal device absent

A separate packet based on `947d3479817ca289776183cb2403020b057e6d71`
kept the same kernel, plugin, frame workload and admission requirements. It
added explicit startup stages, distinct early-refusal messages and an exit
receipt. Its 87 CPU/controller/parser methods, eight statistics cases,
three early-refusal diagnostic cases and both wait-observer self-checks
passed. The actual GUI-user route also loaded both the original plugin and
an exact copy of the signed candidate without requesting a Metal device or
submitting GPU commands. The temporary loader input was removed by exact hash.

The fresh trial again passed initialization, both queue adoptions, both
full-arena native checks and both PR28 admission probes. Its one frame
application reached `main-entered`, `plugin-loaded` and `before-Metal-device`
as the expected GUI user. `MTLCreateSystemDefaultDevice()` returned nil; the
application recorded **exit 22 after 1.02195072 seconds**. It never reached
target-device verification, window setup or the frame worker. There are still
zero frame records and no FPS result. This establishes the observed refusal,
not the underlying reason or the first attempt's undocumented exit subtype.
No retry or alternate device-enumeration call was made.

Independent review reparsed the exact exit/stages, both CPU loader receipts,
native output and both PR28 outputs before verifying restoration and retiring
the second scope. The original kernel and plugin, all 46 protected files,
347 original EFI files and other protected state matched; no new matching
diagnostic report or test client remained. The exact nine-file recovery tree,
job, plugin stage and GUI stage/cache were removed. Final state was GPU-off,
firmware framebuffer only, EFI unmounted and no follow-up task armed.

Controller review found a readiness gap: the new FPS call had been inserted
before the existing compositor-image and first-present readiness checks. A
further isolated packet should require those existing checks before its one
application launch. This is a test-order correction to evaluate, **not a proven
cause or driver fix**. The driver, device identity, frame/pixel checks and
presentation requirements must remain unchanged. Both failed attempts remain
in the evidence, and neither accepts FPS or persistent desktop adoption.

## Readiness-order follow-up: insufficient to resolve the refusal

A third fresh packet, based on
`2988a8eb585daf37bbeb9cee73787811bce9f15a`, moved the existing desktop-progress
and compositor-image checks before its single FPS application launch. It
passed 94 CPU/controller/parser methods, including refusal and call-order
checks. The frame probe source/binary, frame workload, parser, kernel and
plugin were byte-identical to the second packet. Both GUI-user CPU loader
checks passed again. No device or output check was weakened.

The trial passed initialization, both native dispatches and both PR28
admission probes. Before launching the application, the new gate observed
**10 additional successful present transactions in 9.704926724 seconds**, the
same WindowServer, unchanged panel timing and mapped plugin/RADV images.
The readiness receipt was bound by hash to the subsequent application intent.
The application nevertheless reached the same three startup stages and
returned **exit 22 after 1.767093161 seconds** because the default Metal
device was nil. Window setup and the frame worker were not reached; there
were no frame records and no FPS result. Desktop readiness alone is therefore
insufficient to resolve this refusal. The underlying device-creation cause
remains unproved.

Independent review reparsed the readiness samples and compositor mappings,
the bound intent, exit/stages, native checks and both Metal admission outputs.
Recovery and exact retirement passed again: original kernel/plugin restored,
46 protected files and 347 original EFI files matched, protected state
unchanged, no new matching diagnostic, no remaining test client/job, exact
recovery/plugin/GUI stages removed, GPU-off and EFI unmounted. No next GPU
scope was armed at final read-back. Further diagnosis must inspect the device
creation path rather than treating another delay as a repair. All three
failed FPS attempts remain unaccepted.

## Device-initialization observation: no invocation observed

A fourth single-use packet, based on
`39c7330b0e1e8ca2bb322b84397c9c3068b2b66a`, retained the same production
kernel, plugin, frame workload and FPS parser. Its only new runtime diagnostic
was a process-local observer around the application's single
`MTLCreateSystemDefaultDevice()` call. It checked the actual method ABIs and
temporarily wrapped `NVMTLDevice` and its direct superclass
`MTLIOAccelDevice` at `initWithAcceleratorPort:`. The wrappers forwarded to
the original methods with unchanged return values and ownership; both
original implementations had to be restored before any frame work.

Preparation passed 100 CPU/controller/parser methods, eight statistics cases,
ten native observer cases under each of the root and actual GUI-user routes,
and both wait-observer self-checks. The native cases included nil returns,
ABI/class rejection, exclusive installation, restoration and balanced object
lifetimes. Both original and candidate plugins also passed the GUI-user
loader-only ABI/install/restore check, with no device initialization or GPU
calls during those CPU checks.

On the trial boot, initialization, both full-arena native checks and both PR28
admission probes passed again. Before the FPS application, readiness observed
**28 additional successful present transactions in 16.248535576 seconds**,
the same WindowServer, unchanged panel timing and mapped plugin/RADV images.
The application reached the observer-installed and observer-restored stages,
but returned **exit 22 after 0.592238663 seconds** with the default Metal
device still nil. Independent parsing found **zero invocations of either
observed initializer**, zero nil returns from those uninvoked methods and
successful restoration of both original implementations. Target-device
verification, window setup and the frame worker were not reached. There were
zero frame records and no FPS result.

This narrows the evidence: the observed call did not invoke those two
initializer implementations during the observation interval. It does not
establish why Metal returned nil, prove a specific discovery/cache/admission
failure, or establish how many other GPU/device calls occurred internally.
It provides no basis to bypass device admission or attribute the refusal to
the plugin's later initialization checks. Further diagnosis should examine
device discovery and selection before changing those checks.

Independent review reparsed the observer events/summary, exact startup
stages and exit, readiness and its intent binding, native output and both
PR28 outputs. Recovery and exact retirement passed: original kernel and
complete plugin restored; all 46 protected files and 347 original EFI files
matched; protected state unchanged; no new matching diagnostic or remaining
test process/job. The exact nine-file recovery tree, plugin stage and GUI
stage/cache were removed. Final read-back confirmed GPU-off, firmware
framebuffer only, EFI unmounted and no next GPU scope armed. No retry was
made. All four failed FPS attempts remain in the evidence and unaccepted.
