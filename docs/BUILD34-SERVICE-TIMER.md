# Build34 owned service timer and deferred cancellation

This is an isolated source-only prerequisite for R3 service/completion-producer
lifetime, derived from [checked watchdog recovery](BUILD34-WATCHDOG.md). Only
default `upstream34/vram-layout-fix`, PhxBringup build34 is in scope. All 172
production inputs, earlier stages, ABI/runtime recipes and installed settings
remain unchanged. No native reader or exact-mode binding exists. **Do not build
this stage as a kernel candidate or deploy it.** GPU/service quarantine remains;
CPU timer drain does not complete R3 or admit R4–R6.

The later [public service-timer stage](BUILD34-PUBLIC-SERVICE-TIMER.md) replaces
this stage's direct cancellation with public IOKit gated detachment after the
native SDK audit exposed a private-only import. This earlier CPU stage remains
frozen as prerequisite evidence, not the latest timer implementation.

## Reviewed native API contract

The [source manifest](validation/build34-r3-service-timer-sources-20261121.json)
pins Apple XNU commit `f6217f891ac0bb64f3d375211650a4c1ff8ca1ea`, the SHA256
of `thread_call.h` and `thread_call.c`, and the interface names/digests of two
existing local Kernel SDK headers. All four reviewed files have APSL 2.0
headers. This was read-only review, with no upstream implementation text copied
or raw source published. Local SDK name availability is not actual KPI linkage
or a match to the installed kernel. Repository licences/notices are unchanged.

The reviewed interface distinguishes default HIGH from normal KERNEL priority.
It also distinguishes enqueue's already-pending boolean, cancellation's boolean,
and checked free. The pinned implementation treats ONCE cancellation differently
from an ordinary call when another invocation is both pending and in flight;
it rejects waiting on the current call itself. These are review assumptions
for a CPU scheduler model, not observed native execution on this machine.

## Previous actual-method counterexample

The runner extracts the preceding actual `start` allocation/enqueue block into
its CPU service. Its only adaptations qualify the enclosing object and rename
the local deadline variable to avoid shadowing. The block publishes a default
HIGH timer without a separate owner-registration reference. The actual prior
`stop` closes admission and retains the service but leaves that timer pending,
without cancellation or freeing it.

This is a CPU reference/queue-state counterexample. It is not an observed native
use-after-free: the earlier stage deliberately retains the stopped service and
its resources permanently. The point is to supply the missing timer ownership
and cancellation prerequisites before eventual healthy service teardown.

## Ownership, publication and normal execution

`startHangTimer` is one-shot. Its callback lease and atomic fresh-to-initializing
claim precede allocation; a persistent service reference precedes publishing
either callback. It allocates separate periodic and drain thread calls, both
with KERNEL priority and ONCE, plus a dedicated timer lock. Handle publication
and clearing are atomic. Active/ready admission also requires the periodic
handle to remain present, preserving the prior missing-timer refusal.

The first delayed submission and every rearm occur under the timer lock. The
existing 500 ms interval, bounded client reaper and checked watchdog are retained.
Neither the source priority change nor CPU execution proves improved desktop
responsiveness, latency or FPS. The enqueue boolean is not treated as success
or failure: a newly scheduled call normally returns false.

Partial allocation and a stop racing initialization publish no timer. Every
unsubmitted handle is freed with its return checked; failure preserves that
exact handle and the registration reference. A failed native platform start
also retains its mapped-resource quarantine. Full platform start/unwind and
actual SDK/KPI execution are still outside this CPU evidence.

## Stop and the separate drain callback

The single winning `stop` first closes public callback admission and keeps the
existing service/GPU quarantine. It atomically forbids rearm and queues the
separate drain call under the timer lock. It never waits on its own periodic
callback, including stop requested inside the reaper/watchdog or during an RLC
safe-mode entry. Repeated stop does not add another quarantine reference or
queue another drain.

The drain worker captures its two handles under the timer lock, then releases
all timer, client and GPU locks before `thread_call_cancel_wait` on the periodic
handle. No later periodic enqueue can pass the serialized closed-state check.
ONCE plus that no-more-rearm rule is required; a cancellation boolean alone is
not a complete callback-drain proof. Both true and false cancellation results
continue to checked freeing.

The worker seals ordinary queue generations under `gpuLock`, also covering a
stop first observed while another callback was admitted. It checks freeing of
the periodic handle and its own unqueued drain handle. Only two successful frees
clear both identities and consume the timer's registration reference. An
uncertain free retains its handle/reference in a terminal fault state. There is
no blind retry or substitution of a resource-free success.

A separate worker callback gate prevents a handles-released state from claiming
CPU timer drain while the admitted worker is still leaving. The dedicated timer
lock remains with the service, like its GPU lock/mappings. Native object/module
unload and complete platform callback lifetimes are not proved by this gate.

## CPU validation scope

The [sanitized result](validation/build34-r3-service-timer-offline-20261121.json)
records positive ASan/UBSan and TSan runs, runtime mutation checks and frozen
input hashes. Both sanitizers pass 2,734 additional checks across 19 groups
and six threaded scenarios; all 21 deliberately defective variants are
detected at runtime. Default tests pass with the existing missing-firmware
fixture skip. New owned-timer cases execute actual allocation/arm/stop/drain
method bodies. The independent CPU scheduler models ONCE wait behavior,
before-entry and before-finish pauses, checked free failure and owner references;
it runs no native thread-call KPI, IOKit, MMIO or GPU operation.

New threaded cases cover callbacks paused before entry, rearmed callbacks paused
before kernel-model finish, rearm queued behind stop, concurrent stop winners,
initialization racing stop and stop inside an actual staged RLC path. These use
condition-variable handshakes rather than elapsed-time guesses. The last case
also retains the BO/VM/CPU-fence ownership despite later fence progress.

Inherited client/CPU-fence/watchdog regressions keep their private legacy timer
sentinel and original reference-count baseline. That unpublished CPU sentinel
is not owned-timer admission or native object-lifetime evidence. New timer cases
explicitly discard only that sentinel, then execute the real one-shot start and
its persistent reference accounting. Earlier fixtures and production remain
frozen; only their private derived copy uses the new timer lock/handle types.

Deliberately broken child assertions use `_Exit(86)`. Compile failures, timeouts
and sanitizer crashes do not count as detected mutations. Initial private
evidence preserves an enclosing-object/local-deadline name collision in the old
counterexample adapter. The next regression caught a real proposed-source
omission of the old missing-timer guard; the stage restored that guard and
atomic handle publication/clearing before the succeeding runs. These are source
and CPU fixture findings, not native driver or GPU failures. A subsequent
deliberately broken free variant initially failed to compile because it left
its local handle unused. The variant now explicitly consumes that handle;
only its detected runtime assertion counts as mutation coverage.

```sh
nice -n 15 taskpolicy -b make -j1 test-build34-exact-service-timer \
  EXACT_SERVICE_TIMER_OUT=build/build34-r3-service-timer-new-private
```

## Remaining service and R3 work

`hangTimerDrained` is a CPU timer prerequisite only. No BO, VM, framebuffer,
doorbell, MMIO, PCI, PM or base-service resource is released by this stage, and
the stopped service reference is not removed. Healthy service teardown still
requires authoritative queue/external-writer drain, all client and native entry
lifetimes, actual SDK/object/KPI/module evidence and a separate final reclaimer.
Native reader/coherency, paired protocol/visibility, completion registration and
wakeup, actual GPU correctness, measured FPS and stated-duration stability stay
open in [the R3 ledger](BUILD34-R3-PLAN.md).

Rollback is to stop deriving this extra source transform; no installation,
loading, power action or active monitor occurred. Preserve accepted R1b/R2a,
plugin/startup/recovery, daily PR28 250 ms/WindowServer exclusion and disabled
resident monitoring. Never interpret the CPU evidence as permission to deploy
an unbound or quarantining kernel stage.
