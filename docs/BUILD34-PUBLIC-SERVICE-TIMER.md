# Build34 public service timer and gated detachment

This source-only R3 prerequisite replaces the direct private cancellation
dependency found by the [complete-source SDK check](BUILD34-NATIVE-SDK.md).
Only default `upstream34/vram-layout-fix`, PhxBringup build34 is in scope.
It is not a kernel candidate, native lifecycle acceptance or R3 completion.
The device reader and exact mode remain unbound; service/GPU quarantine stays.
All 172 production inputs, prior experiments, ABI, dependency declarations and
installed runtime/settings remain unchanged. R4–R6 do not advance.

## Source and licence review

The [source manifest](validation/build34-r3-public-timer-sources-20261121.json)
pins Apple XNU commit `f6217f891ac0bb64f3d375211650a4c1ff8ca1ea`, digests of
`IOTimerEventSource.cpp`, `IOWorkLoop.cpp` and `IOEventSource.cpp`, three
matching local IOKit SDK header digests, and the SDK kernel-resource key and
Mach-O format headers. The reviewed XNU sources have APSL 2.0 headers.
This was read-only API/lifetime review: no Apple implementation text, binary
or SDK/KDK source is published or copied into the new implementation/model.
Existing repository licences/notices are unchanged. The accepted framebuffer
timer is only a local API reference; no PolyForm component code is copied
into the MIT/GPL PhxBringup component.

The pinned reference distinguishes passive KERNEL-priority timer delivery from
workloop-thread delivery, and uses ONCE when AllowReenter is absent. It retains
the timer/workloop for outstanding passive callouts and checks its callout
generation after acquiring the workloop gate, before invoking the owner action.
`runAction` acquires that same recursive gate. These reference semantics are
not proof of the installed kernel's implementation or native timing/lifetimes.

## Ownership and first publication

`tools/build34_exact_public_timer.py` derives the frozen native predecessor.
It replaces only the periodic timer fields/methods, adds the two public IOKit
includes and removes the unused raw periodic-call field. The source still
uses the exact prior `start`, `stop`, request-drain and stopped-queue sealing
methods, and leaves GPU/VM/receipt/client dispatch methods byte-identical.

The one-shot initializer claims state 1 under its existing callback lease and
retains the service **before** allocating/publishing callback producers. It
allocates a dedicated IOWorkLoop, an IOTimerEventSource explicitly using
`kIOTimerEventSourceOptionsPriorityKernel` without AllowReenter, and a separate
public KERNEL/ONCE drain thread call. The 500 ms interval and bounded reaper/
checked watchdog calls are preserved. No performance gain is claimed.

It attaches the event without holding the timer, GPU or client lock, then
performs the first arm under the workloop gate and timer lock. Only a successful
`wakeAtTime` publishes state 2. Closed/stopping or stale handles refuse. The
initializer owns any state-1 failure; stop never queues a drain worker for
partially initialized handles. Failure cleanup gates cancellation/detachment,
checks freeing the never-submitted raw worker, and releases the registration
reference only after both succeed. Uncertain cleanup preserves the actual
objects/failed handle and pin in terminal state 6, with no retry/rebind.

The complete IOService platform start/unwind is not tested by the CPU fixture.
Its existing mapped-resource failure quarantine remains. Neither an initial
timer failure nor a CPU-only successful cleanup admits a deployable kernel.

## Stop, concurrent arms and separate cleanup

The unchanged winning `stop` closes public admission, retains the existing
service/GPU quarantine, atomically forbids rearm and queues its distinct drain
worker. It does not wait for the workloop gate, including when called inside
the timer action while it holds the GPU lock. Repeated stop remains one-shot.

An arm snapshots and retains timer/workloop under the timer lock, releases that
lock **before** `runAction`, and rechecks state, identities, closed/stop flags,
attachment and enabled state inside the gate. Snapshot references keep an arm
safe even when it waits behind complete detachment. Both real arm callers hold
no client/GPU lock; the periodic action already owns the same recursive gate.
An unexpected rearm error closes service admission rather than silently losing
the periodic producer. A stale sender is rejected before reaper/watchdog work.

The separate worker holds no client, GPU or timer lock while acquiring the
workloop gate. Its action disables the timer, cancels its timeout, removes the
event source and checks both the removal return and resulting attachment.
An in-flight driver action must leave the gate before this succeeds. A wrapper
that has not entered the driver action can still finish later under the
reference's generation/retention contract; this does not require keeping the
driver's registration pin forever or calling private cancellation directly.

After gated detachment, the worker seals ordinary queue generations under the
GPU lock and checks freeing its own unqueued raw call. Only joint success
clears identities, releases timer/workloop ownership and consumes the timer's
registration reference. A closed worker gate remains busy until its admitted
worker leaves, preventing premature `hangTimerDrained` success. Detach/free
uncertainty retains resources and the pin. The service/GPU quarantine reference
is **never** consumed; no BO/VMID, mapping, PM or base-service cleanup is added.
This remains distinct from native module unload or complete service reclamation.

## Validation and its limits

The [sanitized evidence](validation/build34-r3-public-timer-offline-20261121.json)
records actual method-body ASan/UBSan and TSan runs and runtime mutation checks.
Both sanitizers pass 3,930 checks in 34 groups/nine threaded scenarios; all 21
deliberately defective variants are detected at runtime. The complete prior
and proposed objects each have 376 imports. The two added timer/workloop
factories resolve through the existing `com.apple.kpi.iokit` interface; direct
private cancellation and the raw periodic delayed-entry import disappear.
All 376 proposed imports have providers in the existing declared KDK set;
the prior object's sole missing import remains `_thread_call_cancel_wait`.
The independent CPU backend models references, gate serialization, passive
callout generations and the public API signatures. It executes no IOKit KPI,
MMIO, Metal or GPU work and copies no Apple implementation. Model reference
counts/finalization are not native OSObject/workloop-thread lifetime evidence.

Cases include every allocation failure, partial attachment, first-arm failure,
stop during initialization, stop inside GPU-locked watchdog work, repeated stop,
missing handles, stale senders, snapshot ownership, checked raw-free failure,
removal failure and false-success attachment checks. Injected partial-error
outcomes test conservative retention; they are not observed native API failures.
Nine threaded cases use explicit condition-variable handshakes, including
first publication racing stop, an arm captured before closure and delayed
until after detachment, an admitted driver action blocking cleanup, and old
wrappers paused before the gate or after returning from the driver action.

The runner independently compiles the entire prior and proposed source against
the pinned MacKernelSDK at `3f750085caa17ec3a7880f11c11bf4f48cd6a164`. Both use
the real ABI/topology/ownership headers and kernel C++17 flags, no fake IOKit
classes. Outputs must be nonloadable x86_64 MH_OBJECT. All source/header/recipe
dependencies are frozen, with SDK, KDK and compiler identities checked afterward.
The previous four compiler warnings remain recorded; no suppression is added.

The native provider audit distinguishes ordinary implementation binaries from
kernel-resource interfaces. Implementations contribute **defined externals
only**, never their own unresolved imports. For each of the five declared
`OSKernelResource` KPI interfaces it independently verifies the symbol-only
x86_64 Mach-O structure, external references/explicit aliases and each target's
actual definition in the supplied KDK kernel. It does not interpret an opaque
reserved header word as an address or capability. A normal implementation is
also tested and refused as an interface. Checking the kernel's symbols alone
cannot grant a name absent from the declared public interface.

The six existing declared providers are frozen from the current-OS-metadata-
matching KDK. Every proposed undefined import, including public timer/workloop
factories, is checked. No `com.apple.kpi.private` dependency is added. The prior
private cancellation refusal is independently reproduced. Static provider
resolution does not prove actual collection inclusion, loading, callback
lifetime or GPU readiness. No kernel bundle is linked, packaged or signed.

Initial private attempts preserve two CPU-runner setup failures: resolving
clang++ to its actual clang executable lost xcrun's host SDK setup and C++
driver selection. The runner now explicitly supplies the host SDK and C++
driver mode. The next native audit incorrectly applied a defined-symbol filter
to the actual KPI reference/alias interfaces; it refused rather than admitting
those imports. The corrected interface parser then exposed its initial opaque-
reserved-word and simple-reference-only assumptions. All five actual interface
tables and alias targets were independently inspected before the succeeding
audit. None of these verifier failures counts as a detected runtime mutation,
native driver failure or failed GPU test.

```sh
nice -n 15 taskpolicy -b make -j1 test-build34-exact-public-timer \
  KERNEL_SDK="$KERNEL_SDK" KDK="$KDK" \
  EXACT_PUBLIC_TIMER_OUT=build/build34-r3-public-timer-new-private
```

## Remaining R3 acceptance

The private timer-import obstacle is separate from the still-unproved native
reader/mapping coherency, queue/external-writer ownership, healthy service
reclaimer, complete native capability/session/global-prefix/visibility and
paired Mesa/CPU-fence protocol. This 500 ms watchdog/reaper timer is not an AMD
fence-completion event route. AMD completion notification/wakeup, native
callback/module lifecycle, actual GPU correctness, desktop behavior, FPS/CPU/
latency and stated-duration stability still require evidence in the
[R3 ledger](BUILD34-R3-PLAN.md). This stage admits neither a kernel candidate
nor R4–R6.

Rollback is to stop deriving this source-only public timer transform. No driver
installation, load, reboot, GPU probe, recovery replay or resident monitor is
part of this check. Preserve accepted R1b/R2a/plugin/startup/recovery settings,
daily PR28 250 ms/WindowServer exclusion and disabled resident monitoring.
