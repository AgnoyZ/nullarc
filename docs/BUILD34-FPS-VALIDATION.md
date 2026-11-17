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
