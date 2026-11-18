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

## Ordinary-user path observation: no realpath call captured

A ninth fresh packet on 2026-11-18, based on
`2bca854911c64b246d04cf31845b3991b6af4611`, retained the eighth packet's
production binaries, frame probe, workload and existing observers. Its only
new runtime diagnostic interposed the `realpath$DARWIN_EXTSN` symbol imported
by the installed Metal framework, inside the final test process only. It
forwarded each original call once, preserved pointer ownership, caller-buffer
behavior and `errno`, and recorded only six fixed GPU-bundle path scopes. It
made no additional filesystem lookup and changed no symlink permissions,
bundle metadata or trust/admission policy.

Preparation passed **210 CPU/controller/parser methods**, including 37 new
path-parser methods, plus **11 new ASan/UBSan forwarding cases**. Actual root
and ordinary-user native checks produced identical results with and without
the observer. Those separate CPU checks found that root could canonicalize
both GPU-bundle aliases and the canonical bundle path; the ordinary user
received `EACCES` for both aliases but succeeded on the canonical path. The
ordinary user could separately read bundle files and create bundle metadata
objects. These differences alone do not prove a Metal discovery failure.

The hardware trial again passed initialization, both native full-arena checks
and both PR28 admission probes. Readiness observed **477 additional successful
present transactions in 7.893563125 seconds**, unchanged panel timing, the
same WindowServer and mapped plugin/RADV images. These counters are readiness
evidence, not FPS. The ordinary-user process then enumerated **zero Metal
devices** and returned **exit 22 after 0.951223997 seconds**. Neither observed
device initializer ran; no window setup, frame worker or frame record was
reached.

The matching/open observers reproduced the eighth packet's exact sequence,
including an `NMXAccel` iterator result with an unobserved matching source and
only one observed successful `IOSurfaceRoot` open. The new path observer
reported **zero scoped and zero unrelated calls**, with no dropped, inflight
or output-error events. Thus this trial captured no Metal `realpath` denial.
It does not prove that every internal lookup was intercepted, exclude a path
issue, or establish a permissions/filtering root cause. The offline alias
denial is not grounds to change production link permissions. Ordinary-user
FPS, background-stutter repair and persistent desktop adoption remain
unaccepted; all previous evidence and failures are retained.

A distinct ninth-packet verifier reparsed the actual path, matching, open,
startup, native, PR28 and readiness evidence before retirement. The original
kernel and complete plugin were restored; all 46 protected files and 347
original EFI files matched, with links/security/kernel collections unchanged
and zero new matching diagnostic reports. Only the exact nine recovery files,
restore-only job, plugin stage, FPS stage/cache and three observer stages were
removed. Final read-back confirmed GPU-off, firmware framebuffer only, EFI
unmounted, no remaining test client/held process and no next GPU/reboot task
armed. The scope is consumed; the independent verifier performed zero GPU
calls.

## Bundle class lookup: isolated symlink-mode repair, CPU verified

Subsequent CPU-only analysis on 2026-11-18, from
`7a7618078ab6412e45818a0526bb7ed562b0f5e8`, identified the installed Metal
framework's plugin-class lookup sequence: read `MetalPluginName`, query the
trusted GPU-bundle path, create an `NSBundle`, look up `MetalPluginClassName`
and require an appropriate device subclass. The framework code was read but
none of these Metal functions was executed; no Apple code or binary is
redistributed. This narrows the earlier diagnostic without treating the
ninth packet's absent `realpath` events as proof of complete interception.

A native CPU probe preloaded the unchanged original plugin, as the FPS probe
does, then performed the same trusted-path and bundle-class queries without
creating a device. Root and the ordinary GUI user both received a successful
trust result and the same bundle path. Root obtained the expected
`NVMTLDevice` class; the ordinary user obtained neither that class nor a
principal-class fallback. The actual initializer observers recorded zero
plugin and superclass calls and restored their original implementations.
The trust check is therefore not the reproduced CPU rejection point.

A separate temporary-alias comparison used the same binary, alias pathname
and target in fresh processes. With alias mode **0700**, root class lookup
passed and ordinary-user lookup failed. Changing **only that alias's mode
to 0755** made both pass. The target plugin's bytes and permissions were
unchanged, and the exact temporary stage was removed.

A further bounded CPU check reproduced this on the actual installed Metal
alias: ordinary-user lookup failed at 0700, passed at 0755 with the class
coming from the exact original plugin and satisfying the device-subclass
check, then failed again after rollback to 0700. Root passed both modes.
All five fresh processes passed the original trust query, invoked zero
device initializers and performed no device enumeration or GPU work. The
alias's original mode, inode, owner and target were verified after rollback;
the complete original plugin and GPU-off state were unchanged. The runtime
alias was not modified and no reboot was requested.

The minimal source repair in `tools/phxctl/relocate_gpubundle.sh` now gives
only the expected Metal alias mode 0755, using `chmod -h` so the target is
not followed. It applies to newly created and existing aliases and refuses
an unexpected Metal link target. It does not change the runtime alias,
driver/plugin sources, trust checks, OS security or build34 admission. Four
actual-shell filesystem tests passed, covering a restrictive creation
umask, existing-link repair with preserved target bytes/metadata, repeated
execution and rejection before unrelated relocation. Those tests use
temporary paths and a signature-command stub; the production relocation
script was not executed against the installed runtime.

This accepts the isolated CPU class-lookup repair only. An accelerator
enumeration and complete visible-frame trial with an independently armed
mode rollback are still required. Ordinary-user Metal/FPS, background-stutter
repair, permanent alias-mode adoption and persistent desktop acceleration
remain unaccepted. The installed alias is back at its original 0700 mode.

## Tenth packet: stopped by a boot-local identity check, independently recovered

A fresh one-use trial from `a61336393c8d1182af531abb8b544510a8a5765a`
retained the exact ninth-packet kernel, plugin, frame program, parsers and
observers. Only the Metal alias mode was temporarily changed from 0700 to
0755; its inode, owner, target and flags were unchanged. Preparation passed
**227 CPU/controller/parser methods**, including 12 alias-mode methods and
46 desktop-control methods. Failure-injection checks required controls,
alias mode, plugin and disk restoration to be attempted independently.

The first boot stopped before the initializer, native dispatches, PR28
admission processes or FPS application could run. The new alias guard had
incorrectly treated the filesystem's boot-local `st_dev` number as a stable
cross-boot identity. That number changed; the link's inode, owner, target
and flags did not. Placing this guard in the shared static check also blocked
the restore-only job before its independent restoration loop. The passing
same-boot CPU checks had not covered that cross-boot dependency. This is a
controller failure, not evidence that the alias-mode repair failed or that
ordinary-user Metal enumeration succeeded.

A separate restore-only script verified every frozen input, both full kernel
manifests, the exact post-boot link identity, original/candidate plugin
manifests, protected files and OS security before restoration. It retained
the failed controller and contract unchanged, restored the original controls,
0700 alias mode, complete plugin and on-disk kernel, and requested one recovery
boot. It performed no driver initialization, GPU submission or retry. The
candidate image's native framebuffer had loaded during the first boot;
this is not counted as execution of the planned GPU workload.

Independent final verification confirmed the original kernel loaded,
GPU-off, firmware framebuffer only, all **46 protected files** and **347
original EFI files** matching, the same alias inode/owner/target/flags at
0700, unchanged security/kernel collections and **zero new matching
diagnostic reports**. Only the exact nine recovery files, restore-only job,
candidate plugin stage, frame stage/cache and three observers were retired.
There is no remaining test client, held process, next GPU task or reboot
request. The tenth packet is consumed and cannot be replayed.

Cross-boot link validation needs a stable volume identity together with the
retained inode, ownership, target and flag checks, plus failure-independent
recovery. Removing identity checks or reusing this failed scope is not a fix.
Ordinary-user enumeration/FPS, background-stutter repair, permanent alias-mode
adoption and persistent desktop acceleration remain unaccepted.

## Eleventh packet: natural writer deadline expired before FPS admission

The next fresh scope used source
`82063cc550730f37e2f0103adae95675743365c0` and the same build34 kernel,
plugin, native/Metal probes, frame program and observers. Its private
controller validated the Metal alias across boots using the internal APFS
volume identity plus inode, ownership, target and flags, retaining the
device-number check within the same boot. Link validation remained a GPU
admission requirement but was removed from the shared EFI restoration guard.
Thus an alias check or volume query failure could not prevent restoring the
on-disk kernel. Preparation passed **234 CPU/controller/parser methods**,
including 18 alias-mode methods and an additional recovery-failure case.

This time startup and the stable-volume guard passed. The original kernel
was restored on disk before the planned GPU initializer, which passed both
queue/adoption checks. Both subsequent native dispatches passed the full
arena comparison with no IB mismatch. The Metal alias was temporarily 0755
and the runtime alias remained unchanged.

The first PR28 `ready` render then reached its unchanged **250 ms** natural
writer deadline with publication still unconfirmed. The actual group wait
lasted **250.851541 ms**, while commit took **251.000741 ms**. Exactly one
matching group wait was observed; both its return and the immediate group
query remained nonzero. Command status was **Scheduled (3)**, not Completed;
no command error was reported. The probe retained its command/resources for
recovery. There was no successful ready summary, second PR28 probe, FPS
application launch or frame record. This does not establish where execution
was waiting, whether it completed later, a permanent GPU hang or an accepted
ordinary-user enumeration result. The deadline was not raised and the
timeout was not counted as success.

The independent guardian restored controls, alias mode, plugin and EFI with
**zero restoration errors**, then requested its single recovery boot.
Independent reparse and retirement confirmed the original kernel loaded,
the complete original plugin, alias mode 0700 on the same APFS volume with
the same inode/owner/target/flags, all 46 protected files and 347 original
EFI files matching, unchanged security/kernel collections, GPU-off, firmware
framebuffer only and zero new matching diagnostic reports. Only the exact
nine recovery files and this scope's job, plugin stage, frame stage/cache
and observers were removed. No test client, held process or next reboot/GPU
task remains. The scope is consumed.

Earlier bounded PR28 wait evidence remains historical; this wider alias-mode
context failed its natural-wait admission. Ordinary-user FPS, background
stutter, permanent alias-mode adoption and persistent acceleration remain
unaccepted. A further diagnostic must distinguish execution, GPU retirement
and surface publication without changing the production wait or claiming
an expired wait completed successfully.

## Twelfth packet: GUI rendering reached, presentation coverage refused

A fresh one-use scope from `393c3e38fa5b4072df89233fb18e208c701fdc89`
kept the eleventh packet's production kernel, plugin, native probe, frame
workload, three FPS observers and original admission/recovery requirements.
The Metal alias again used temporary mode 0755, with independent restoration
to 0700. The only new execution variable was forwarding observation inside
the PR28 probe process, limited to the first natural writer. It recorded
entry/return of eight existing methods without adding GPU calls or changing
arguments, results, the 250 ms budget or failure/HOLD behavior.

The first CPU preparation stopped because the new packet's fallback script
still named the previous recovery directory. This was corrected before any
scope contract, installation or GPU execution. The corrected preparation and
independent admission passed **246 controller/parser methods**, six new
native phase cases, the same six cases under ASan/UBSan and both existing
observer routes per build variant. Missing methods, forwarding, arguments,
BOOL results, unrelated objects, bounded overflow, concurrent records and
restoration were checked. The frozen production images were unchanged.

Startup restoration, initialization, both queue adoptions and both full-arena
native dispatches passed without an IB mismatch. This scope's three natural
PR28 writer waits completed in **4.912839, 1.002408 and 0.742321 ms**; each
reported Completed (4), a retired group and no command error. The buffer-only
fast path also passed. The separate 1 ms controlled timeout remained pending
at its deadline and subsequently verified actual completion and output.

The first writer produced 18 balanced phase records on two threads, with no
dropped or open methods and the original implementations restored. From its
observation epoch, device-timing collection began at 1.884512 ms, surface
publication returned successfully at 5.294644 ms and callbacks returned at
5.823325 ms, all before the wait-return marker at 6.053436 ms. This describes
this successful command only. The added observation can affect scheduling;
it neither explains nor repairs the preceding scope's 250 ms failure. That
failure and the default-wait HOLD remain in force.

After compositor readiness, the application ran once as the ordinary GUI
user. Its single enumeration returned one uniquely verified target device;
the plugin and superclass initializer each ran once and neither returned nil.
The application exited zero after recording **1714 completed frames** over
**20.00567433 seconds**, with 16 sampled pixels / 64 checked channels per
frame and no sampled mismatch. However, only the first **568** presentation
callbacks had positive timestamps, covering **5.558318958 seconds**. All
remaining **1146** callbacks were received with timestamp zero. The unchanged
independent parser correctly refused `presentation span does not cover
measurement window` because the required 18-second presentation span was not
established. A zero exit and completed-frame statistics do not override this
refusal; **there is no accepted GUI FPS result**.

The completion intervals also include a maximum gap of 1022.53857 ms. This is
a diagnostic observation from the bounded workload, not proof of a background
stutter cause, physical scanout, game performance or repaired input latency.
The packet did not record window occlusion or visibility changes, so it cannot
distinguish those from a presentation-path cause of the zero timestamps.

Automatic recovery reported no restoration errors. Independent reparse
retained the presentation failure, verified both native dispatches, both PR28
probes and the phase/GUI observations, then retired the exact nine recovery
files, job, plugin stage, GUI stage/cache and three FPS observers. Final
read-back confirmed the original kernel loaded, complete original plugin,
0700 Metal alias on the same volume with the same link identity, all **46
protected files** and **347 original EFI files** matching, unchanged security
and kernel collections, zero new matching reports, GPU-off, firmware
framebuffer only and no remaining test client, held process or reboot request.
The scope is consumed. Further work needs presentation/visibility evidence
while retaining the original measurement and recovery gates; ordinary-user
FPS, background-stutter repair and persistent adoption remain unaccepted.

## Thirteenth packet: bounded GUI frame witness passed, desktop tail refused

The owner asked whether interaction with the test window could have affected
the preceding result and explicitly requested another test. A fresh scope
from `ee29d00a4f637e9c0d53fb79f1e3759f7708f429` repeated the exact same
production kernel/plugin, native and PR28 probes, phase observation, frame
program, parsers and three FPS observers. Only packet-local paths, the source
record and the prior-retirement prerequisite changed. All **246** CPU control
and parser methods passed again; independent admission verified byte identity
with the twelfth packet. The owner was asked to leave the automatically opened
test window visible. No programmatic change forced window visibility, and no
window-occlusion or user-action record was added.

Initialization and both full-arena native dispatches passed without an IB
mismatch. All three natural PR28 waits completed, taking **21.187530,
1.301631 and 1.020194 ms** within the original 250 ms budget. The first writer
again produced 18 balanced phase records, with successful publication and
callback return before its wait-return marker. The independent 1 ms timeout
observed the publication group still pending, then verified actual late
completion and output. In that induced timeout, status was already Completed
(4) while the publication group remained pending: the test's callback gate
had not yet released publication/completion signalling. This is not a natural
wait failure or a reason to treat command status alone as publication proof.

The ordinary GUI application enumerated one uniquely verified target device
and exited zero. The **unchanged frame parser passed** all **2385** completed
and sampled-pixel-verified frames over **20.006966069 seconds**. Every frame
had a received, positive, strictly ordered presentation timestamp, covering
**20.000096024 seconds**, above the retained 18-second coverage requirement.
The bounded application reported **119.208479 completed verified frames/s**
and **119.199428 reported presentations/s**. Completion intervals were
8.324423 ms at the median, 9.231074 ms at p95, 10.433690 ms at p99 and
42.469907 ms maximum. These are independently reparsed results for the
1280-by-800 test workload, one in-flight command and sampled pixels; they do
not measure physical scanout, full-frame pixel correctness, games or input
latency. PR28 opt-in remained off in the FPS application itself.

The **whole desktop trial still failed**. After the frame application exited,
the existing desktop-tail loop raised `no measured frame progress` rather
than producing its desktop result. Its starting snapshot was the readiness
snapshot collected before the application; the failure was recorded about
10.45 seconds after the tail began. The controller did not persist the
failing sample or its intermediate counter snapshots. The frozen control flow
and exact exception identify the failed progress requirement, but the missing
snapshots prevent distinguishing an idle desktop from a compositor stall.
The requirement was not weakened or retrospectively waived. Only the bounded
GUI application frame witness passes; the complete desktop scope, long-run
stability and background-stutter repair remain unaccepted.

This same-program repeat did not reproduce the previous short presentation
span. It does **not** establish that the owner's earlier window action caused
that failure, and it does not explain or fix the eleventh packet's natural
wait timeout. The visibility hypothesis remains unproven. Earlier failures
and the default-wait/persistent-adoption HOLDs are preserved.

Automatic restoration completed without errors. A new independent verifier
reparsed the native and both PR28 results, phase evidence, GUI enumeration and
complete frame/presentation output, retained the later desktop refusal, and
then retired this scope's exact nine recovery files, job, plugin stage, GUI
stage/cache and three observers. Final read-back confirmed the original
kernel loaded, complete original plugin and 0700 alias restored, unchanged
link identity, **46 protected files** and **347 original EFI files** matching,
unchanged security/kernel collections, zero new matching reports, GPU-off,
firmware framebuffer only, EFI unmounted and no remaining test/reboot task.
The scope is consumed and cannot be replayed. Further desktop work needs
persisted progress snapshots and a separately justified distinction between
idle observation and an active refresh test; it must retain the failed scope
and existing admission requirements.

## Fourteenth packet: persisted post-application desktop progress refusal

The owner's continuation authorized a new one-use diagnostic on 2026-11-18
from synchronized default-branch checkpoint
`aa7ed621f1887b23f3cbbb2284334cc70da0332f`. It kept the thirteenth packet's
exact kernel, plugin, native/PR28/frame programs, frame parser and observers.
Only the private controller's tail evidence collection changed: it saved an
actual post-application snapshot and each subsequent before/after snapshot
before running the original ordered checks, then saved the outcome or exact
exception. The original pre-application readiness baseline, five-second
sampling interval, ten-second tail, progress requirement, 250 ms natural-wait
budget and independent recovery remained. No active redraw stimulus or
programmatic visibility change was added. Fourteen new CPU cases checked
failure persistence, refusal propagation and preservation of the original
gate; all **260 controller/parser CPU methods** passed. Independent prearm
read-back verified **67 frozen inputs**, the unchanged production/probe
binaries and the recovery prerequisites. Build41/build42 were not used.

Initialization and both queue adoptions passed. Both native dispatches again
passed the full-arena checks without an IB mismatch. Three real PR28 natural
publication waits completed within the unchanged 250 ms budget, taking
90.306014 ms, 0.250320 ms and 0.327324 ms. The induced one-millisecond timeout
observed a pending publication group after 1.112829 ms, with command status
Scheduled (3), then verified actual late completion and output after releasing
the callback gate. The first-writer phase record again contained 18 balanced
events on two threads, with no open/dropped events or events after wait return.
This passing repeat does not explain or repair the eleventh packet's natural
250 ms failure, and it does not promote the default wait policy.

The ordinary GUI application enumerated the unique target, exited zero and
passed the unchanged strict frame parser. It completed and verified **2123
frames in 20.004846155 seconds**, or **106.124285 completed verified frames/s**.
All 2123 presentation callbacks had positive, strictly ordered timestamps,
covering 19.991555412 seconds and reporting **106.144817 presentations/s**;
the original 18-second coverage requirement passed. The 1280-by-800 workload
verified 135872 sampled pixel channels, with one in-flight command. Completion
intervals were 8.402358 ms at the median, 16.774650 ms at p95, 19.109392 ms
at p99 and 27.512582 ms maximum. These bounded application results measure
neither physical scanout nor full-frame pixels, games, input latency or
long-run stability. PR28 opt-in remained off in the FPS application. The
difference from the preceding 119.2 FPS run is not a controlled performance
comparison and is not attributed to a driver change or the owner's actions.

The **complete desktop scope failed again**, now with the previously missing
samples preserved:

| Snapshot | Successful display-pipe transactions | Synthetic VBL count |
| --- | ---: | ---: |
| Original readiness baseline before the application | 30 | 3236 |
| Actual snapshot after the application | 2908 | 8962 |
| First tail sample, 5.170308 seconds after that snapshot | 2954 | 9579 |
| Second tail sample, another 5.155347 seconds later | 2954 | 10203 |

The first tail check passed the original progress, compositor, panel and
report checks. Its baseline remained the original readiness sample; the
additional post-application sample was diagnostic only. Between the two
tail samples, the successful-transaction count did not increase while the
synthetic VBL count increased by **624**. The unchanged gate therefore raised
`no measured frame progress`. Both raw samples were saved before their
checks, and the refusal receipt records that the second sample's later panel
and report checks were not reached. Independent re-read of the captured
values found the same single WindowServer, unchanged control values, and zero
failure/copy-skip counts. The counter reads are sequential, not atomic.

The source's `gCntIopOk` advances on successful display-pipe transactions
in `NVDisplayPipe::performTransaction`; `gVblN` advances separately in
`PhxAMDFB::vblFire`. The observations establish a zero-transaction interval
with a continuing synthetic timer. They do not establish whether a new
desktop update was expected, whether the visible desktop froze, or whether
physical scanout continued. No active redraw or input-response witness was
collected. Idle observation and a compositor stall therefore remain
undistinguished. Neither the original failure nor its requirement was
waived. A further test must establish a bounded, independently observed
redraw demand and correlate it with the transaction samples; repeating a
static desktop interval alone cannot establish that distinction.

Automatic restoration and an independent evidence/recovery verification
completed without errors. The verifier reparsed native, PR28, phase,
enumeration and complete frame/presentation output, independently reproduced
the exact tail refusal from the saved samples, and retired this scope's
exact nine recovery files, job, plugin stage, GUI stage/cache and three
observers. Final read-back verified the original kernel loaded, original
plugin and 0700 alias restored with unchanged link identity, **46 protected
files** and **347 original EFI files** matching, unchanged security/kernel
collections, zero new matching reports, GPU-off, firmware framebuffer only,
EFI unmounted and no remaining test/reboot task. The scope is consumed and
cannot be replayed. Only the bounded GUI application witness passes; the
complete desktop trial, background-stutter repair, long-run stability and
persistent adoption remain unaccepted. No further GPU scope is armed.
