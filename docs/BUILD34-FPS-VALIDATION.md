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

## Explicit device enumeration: empty device list

A fifth fresh packet, based on
`14d1474ae0827b92e953143a59b4ca8960a502a7`, changed only the test's device
selection and the diagnostics/checks needed to distinguish that path. The
production kernel/plugin, frame workload and FPS parser were unchanged.
It called `MTLCopyAllDevices()` once, required a unique device passing the
existing exact PCI and plugin-image checks, and made no default-device call
or fallback. This was a separate diagnostic path, not a repair of default
device creation. Upstream's `tools/mtlprobe/mtlprobe.m` at fixed commit
`8aba872560a3c9b7dc7a0ddebfad001c6dddf315` was reviewed through the GitHub
API and matched the local copy; it also starts with device enumeration. No
other upstream driver source or candidate build was prepared or used.

Preparation passed 106 CPU/controller/parser methods and eight statistics
cases. Ten native selection cases and ten native initialization-observer
cases passed under each of the root and actual GUI-user routes. Selection
checks rejected empty, ambiguous, wrong-identity, wrong-image and oversized
input arrays without calling Metal. Both GUI-user plugin-loader ABI and
observer install/restore checks passed again. Independent prearm review also
checked the one enumeration import, absence of a default-device import and
byte-identical frame workload/parser. These preparation checks made no GPU
calls.

The trial again passed initialization, both native full-arena checks and both
PR28 admission probes. Before the application, readiness observed **seven
additional successful present transactions in 9.569722126 seconds**, the
same WindowServer, unchanged panel timing and mapped plugin/RADV images.
The actual GUI-user application enumerated **zero Metal devices**, selected
none and returned **exit 22 after 1.756766328 seconds**. Neither observed
initializer was invoked; both original implementations were restored. The
application never reached window setup or the frame worker. There are zero
frame records and no FPS result. No default-device call, fallback or retry
was made.

Explicit enumeration alone therefore did not resolve the application's
device visibility problem. The cause remains unproved: these observations
do not distinguish user/session/launch conditions, framework loading or an
earlier device-discovery rejection. They do not justify changing the plugin's
later initialization checks or weakening device identity and FPS admission.

Independent review reparsed the enumeration summary, initialization events,
startup stages, exit, readiness/intent binding, native output and both PR28
outputs. Exact restoration and retirement passed again: original kernel and
full plugin restored; all 46 protected files and 347 original EFI files
matched; protected state unchanged; no new matching diagnostic or remaining
test client/job. Only the exact nine recovery files, job, plugin stage and
GUI stage/cache were removed. Final read-back confirmed GPU-off, firmware
framebuffer only, EFI unmounted and no next GPU scope armed. All five failed
FPS attempts remain preserved and unaccepted.

## Root execution control: bounded frame workload passed

A sixth fresh packet, based on
`276b10a4c39e6dd5146e4a9f4ce163cacf8015dd`, changed only the FPS application's
execution credentials to root while retaining the actual console user's
bootstrap. The probe source and binary, initialization observer, selection
parser, FPS parser, shaders, frame workload, kernel and plugin matched the
fifth packet byte for byte. No production source or admission policy changed.
The application still enumerated devices once, required the unique exact
target, and made no default-device call, fallback or retry.

Preparation retained the 106 CPU/controller/parser methods, statistics,
selection and observer checks under both identities, and the GUI-user
original/candidate plugin loader checks. Additional checks exercised the
actual root-control launch route: eight CPU statistics cases and both plugin
loader/ABI/observer checks passed with UID/EUID 0 and zero device initializer
or GPU calls. This did not execute another GPU workload before the trial.

On the trial boot, initialization, both native full-arena checks and both
PR28 admission probes passed. Before the FPS launch, readiness observed
**22 additional successful present transactions in 16.917906416 seconds**,
the same WindowServer, unchanged panel timing and mapped plugin/RADV images.
The application ran all eight startup stages with UID/EUID 0, enumerated
**one device with one exact target match**, and invoked both observed
initializers once without a nil return. Both original implementations were
restored before frame work. Target verification and visible-window setup
passed; the application exited 0 after 32.215373856 seconds.

Independent frame and presentation reparsing confirmed:

- 1280-by-800 visible drawable, display synchronization enabled, two maximum
  drawables and one command in flight; 227 warmup frames over 2.001434702 seconds.
- **2332 measured frames over 20.007381711 seconds**, with all commands
  successfully completed and all 149248 sampled pixel channels verified.
- **116.556980503 completed-and-verified frames/second**, measured with
  `CLOCK_UPTIME_RAW`; nearest-rank completion intervals p50 **8.343770 ms**,
  p95 **9.233229 ms**, p99 **16.777249 ms**, maximum **43.318042 ms**.
- **2332 positive, strictly increasing presentation timestamps**, spanning
  19.991754329 seconds and reporting **116.598071467 presentations/second**.
  These are independently checked callback timestamps, not physical scanout.

The separate desktop tail retained the same WindowServer across three
samples over 17.118938042 seconds, with no new matching diagnostic report.
Its present-counter progress was not used to calculate either frame rate.
PR28 remained default-off, WindowServer remained excluded, and the FPS
application did not opt in.

**Only this bounded root-context control workload is accepted.** Ordinary
GUI-user device visibility and FPS remain unaccepted; the fifth packet's
empty device list and all five earlier failures remain in the evidence.
The credential-sensitive difference directs the next diagnosis toward the
ordinary-user discovery/access path. It does not prove a particular
authorization, session, framework or driver root cause, repair default-device
creation, or justify running ordinary applications as root. No A/B speedup,
game FPS, physical scanout, input latency, background-stutter repair,
unrestricted long-term stability or persistent desktop adoption is claimed.

Independent review reparsed all native, PR28, readiness, startup, observer,
selection, frame and presentation evidence before checking exact recovery.
The original kernel and full plugin were restored; all 46 protected files
and 347 original EFI files matched, with protected links/security/kernel
collections unchanged. Only the exact nine recovery files, restore-only job,
plugin stage and FPS stage/cache were removed. Final read-back confirmed
GPU-off, firmware framebuffer only, EFI unmounted, no remaining test client
or held process, and no next GPU/reboot task armed. The scope is consumed;
the verifier performed zero GPU calls.

## Ordinary-user device-open observation: no accelerator open observed

On 2026-11-18, a seventh fresh packet based on
`87825b7ab2e172c68471a2b6541bce993993e6c3` returned to the fifth packet's
ordinary GUI-user route. Its probe source/binary, initialization observer,
selection/FPS parsers, shaders, frame workload, kernel and plugin were
byte-identical to that packet. The sole new runtime diagnostic was a bounded
`IOServiceOpen` interposer injected into the final test process. It forwarded
the original arguments and return value, preserved `errno`, read connection
outputs only on success, and queried service-class metadata after the real
open returned. It did not make any additional client-open call or modify
the production binaries, device admission or wait policy. Injection was
introduced after the protected launch/priority tools, solely for the probe.

Preparation passed 128 CPU/controller/parser methods and 11 ASan/UBSan
forwarding cases. Native null-service checks verified actual interposition
and unchanged returns without opening a valid device. The actual GUI-user
FPS launch route passed its injected CPU statistics check; both original
and candidate plugin loader/ABI/observer checks passed with the interposer
loaded and zero initializer or intercepted client-open calls. These checks
did not submit GPU work.

Initialization, both full-arena native checks and both PR28 admission probes
passed again on the trial boot. Before the FPS application, readiness observed
**127 additional successful present transactions in 10.648462243 seconds**,
the same WindowServer, unchanged panel timing and mapped plugin/RADV images.
The application then enumerated **zero devices**, invoked neither observed
initializer and returned **exit 22 after 1.083880789 seconds**. It did not
reach window setup or the frame worker. There were zero frame records and
no accepted ordinary-user FPS result.

Independent parsing found exactly one intercepted `IOServiceOpen`, occurring
between `before-Metal-device` and `device-observer-restored`: **`IOSurfaceRoot`,
connection type 0, return code 0, with a nonzero returned connection**. The
observer's beginning and summary both matched the expected GUI-user identity;
there were no suppressed, incomplete or output-error events. No accelerator
open or access-denied return was observed through this interposer.

This does **not** establish a permissions denial or prove that every possible
internal open path was intercepted. The evidence is limited to the observed
function calls and interval. The earlier root-only rendering control remains
separate, and the ordinary-user discovery failure remains unresolved. The next
diagnosis should inspect device matching/discovery before assuming that a
kernel access check or the plugin's later allow-list/Vulkan checks rejected
the application. No permission, identity or FPS requirement was relaxed.

Independent review reparsed the exact failure, stages, call/event ordering,
device observations, readiness/intent binding, native output and both PR28
outputs. Exact restoration and retirement passed: original kernel and complete
plugin restored, all 46 protected files and 347 original EFI files matched,
protected links/security/kernel collections unchanged, and no new matching
diagnostic or remaining test client/job. Only the exact nine recovery files,
job, plugin stage, FPS stage/cache and injected observer stage were removed.
Final read-back confirmed GPU-off, firmware framebuffer only, EFI unmounted
and no next GPU/reboot task armed. The scope is consumed and the verifier
performed zero GPU calls. All earlier failures and the limited root-control
acceptance remain preserved.

## Ordinary-user matching observation: accelerator returned, Metal list empty

An eighth fresh packet on 2026-11-18, based on
`5f6d9a03d2e5c250cee45df6816a4552a9a137da`, retained the seventh packet's
ordinary-user launch route, exact frame probe, initialization/open observers,
existing parsers, kernel, plugin and frame workload. Its only new runtime
diagnostic observed the test process's original `IOServiceGetMatchingServices`,
`IOServiceGetMatchingService` and `IOIteratorNext` calls. It copied only bounded
matching metadata before the consuming API received the dictionary, forwarded
each original call once, preserved its result and `errno`, and queried service
classes only after the original call returned. It made no additional matching,
iterator-consumption or client-open call and changed no admission policy.

Preparation passed **173 CPU/controller/parser methods**, including 45 new
matching-parser methods, plus **21 ASan/UBSan forwarding/ownership cases**.
Root and ordinary-user native checks preserved the results for a deliberately
nonexistent service class and one null-iterator call; non-null iterator
forwarding and correlation were separately CPU-fake tested. The exact FPS
launch route and original/candidate plugin loaders passed with both observation
libraries injected and no initializer or client-open calls during those checks.

The trial passed initialization, both native full-arena checks and both PR28
admission probes. Readiness observed **five additional successful present
transactions in 9.196628987 seconds**, unchanged panel timing, the same
WindowServer and mapped plugin/RADV images. The ordinary-user application
nevertheless enumerated **zero Metal devices**, invoked neither observed
initializer and returned **exit 22 after 9.426746181 seconds**. It reached no
window setup or frame worker and produced zero frame records; ordinary-user
FPS remains unaccepted.

All four matching-observer events occurred inside the Metal-enumeration
interval, in this order:

1. A successful matching-services call returned a nonzero iterator; its
   provider-class metadata was unknown.
2. The original next call on that observed iterator returned `IOSurfaceRoot`.
3. An original next call on an iterator whose matching source was **not
   observed** returned **`NMXAccel`**.
4. Another original next call returned no service.

The unchanged open observer separately recorded only the successful
`IOSurfaceRoot` open, between the second and third matching events. Both
observers completed without dropped, inflight or output-error events. The
matching observer also reported no iterator-map errors or additional calls.

This demonstrates that the ordinary-user process received an `NMXAccel`
service from an existing iterator. It does not establish that service's
matching dictionary, capture every internal discovery path, explain the later
empty Metal list, or prove a permissions denial. Diagnosis should now inspect
the filtering/plugin-discovery path after that service result and before the
uninvoked device initializer. The later allow-list/Vulkan initialization must
not be treated as an established rejection point. No production fix, game
FPS, background-stutter repair or persistent desktop adoption is accepted.

Independent review reparsed the original observations, exact event ordering,
startup/device summaries, readiness binding, native output and both PR28
outputs before retirement. The original kernel and complete plugin were
restored; all 46 protected files and 347 original EFI files matched, with
protected links/security/kernel collections unchanged and zero new matching
diagnostic reports. Only the exact nine recovery files, restore-only job,
plugin stage, FPS stage/cache and both observer stages were removed. Final
read-back confirmed GPU-off, firmware framebuffer only, EFI unmounted, no
remaining test client/held process and no next GPU/reboot task armed. The
scope is consumed; the independent verifier performed zero GPU calls. All
earlier failures and the bounded root-only control remain preserved.
