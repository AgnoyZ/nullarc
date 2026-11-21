# Build34 R3 client construction and configured-queue publication

This source-only step derives the [raw handoff](BUILD34-RAW-QUEUE-HANDOFF.md)
on default `upstream34/vram-layout-fix`, PhxBringup build34. It changes the
client factory, the inline configured-queue getter, and one successful-adoption
publication. It admits no kernel candidate, native reader/mode or healthy
service teardown. Permanent service/GPU quarantine remains. All 172 production
inputs, prior stages, ABI, dependencies and installed settings stay unchanged;
the preceding paired staged bootstrap is still required and byte-identical.

## Actual source counterexamples

The preceding factory has no service callback lease. Its old method still
registers sysctls, allocates and attaches a client after service closure, before
the checked client registration eventually refuses. If close occurs after
registration while `IOAccelPhxNativeClient::start` is completing, the old
factory can return that started client without observing provider closure.
Actual factory/start/registration method bodies reproduce both outcomes with
CPU object models and a condition-variable handshake. This is not a claim
that a physical GPU failure or installed IOKit failure was observed.

The preceding inline `gpuReady()` reads `gq[0/1].ready` outside the GPU lock,
whereas actual adoption writes that flag under the lock. A separate CPU TSan
run diagnoses a data race between the actual old getter and adoption body.
Per-client locks cannot serialize discovery by a different client with queue
adoption. The old global sysctl-once condition also mixes a plain read of its
flag with CAS updates; concurrent factory tests diagnose that deliberately
restored condition under TSan.

## Construction lease and observed-close refusal

`tools/build34_exact_factory.py` gives the whole factory a service callback
lease, before sysctl registration or allocation. A null output pointer or
wrong client type refuses, and a valid output slot is cleared before any
failure. Closed service admission or an unavailable timer refuses before
allocation. Sysctl-once uses the existing atomic CAS without its plain
precheck. The four existing global oid registrations are otherwise unchanged;
global sysctl unregister/module unload remains a separate requirement.

After init/attach, observed closure detaches and drops the initial client
reference without calling start. A failed start drops the same reference and
reports provider closure as NotReady rather than an exclusive-access conflict.
After successful start, observed closure calls the existing `clientClose`
before detach/release, returns no handler and preserves any authoritative
registration/provider pins if cleanup is uncertain. It never directly frees
a registered client's BO/VM resources, clears ownership metadata or mistakes
the factory's initial reference for the registration pin.

The unchanged service stop therefore sees an admitted construction as CPU
work still in flight. It closes admission and retains service/GPU quarantine
without treating that factory as drained. The timer cleanup behavior and
native healthy reclamation policy are not changed by this step.

These checks do not make stop atomic with the final handler pointer store.
An admitted operation can still straddle closure after its final check; the
lease is a lifetime prerequisite, not native IOKit connection/publication
serialization. Complete platform start/unwind, factory handoff, PCI claim/
matching and module lifetimes still need native integration and acceptance.

## Atomic configured discovery without mock fallback

The existing getter is used both outside and inside the GPU lock, so adding
an internal GPU lock would introduce recursive locking. Instead, a new atomic
two-bit mask is release-published only after successful adoption has seeded
the fence and published all queue readiness/live metadata. The getter performs
an acquire load; concurrent discovery no longer reads the mutable queue struct.
Adoption remains serialized by the existing GPU lock and preserves both bits.

The mask is monotonic for this service object. In this frozen preceding source
each queue's readiness changes only on its first successful adoption, because
the raw-handoff latch prohibits re-adoption. The runner checks that writer
contract and byte identity of all other source. Fault, sleep, stop or generation
invalidation does not erase knowledge that real queues were configured.
`gpuReady()` therefore means configured discovery, **not** live health, coherent
completion, global-prefix visibility, a new GPU admission decision or drain.

Preserving that distinction matters: clearing discovery on a fault could make
older callers enter the E1 mock/no-GPU branch. Real submit/map/retirement and
resource consumers must continue through their existing checked admission,
generation and completion paths. This change does not turn an unavailable
reader into success or remove a sticky fault. Those methods remain identical.

## Evidence and limits

The [sanitized result](validation/build34-r3-factory-offline-20261121.json)
contains the actual-method CPU suites, negative variants and complete-source
native object checks. It freezes all earlier source/evidence plus the new
transform, fixture, runner and helper. The scoped change is verified by
reverting its two methods, getter/comment and field in memory and requiring
byte equality with the preceding complete composed source. The earlier
ownership header and paired bootstrap hashes must also remain identical.
The succeeding expanded run passes 238 factory/discovery checks under each of
ASan/UBSan and TSan in 18 groups/nine threaded scenarios. All fourteen assertion
mutants and both deliberate TSan race regressions are detected. The unchanged
preceding raw-handoff fixture also runs against the actual new adoption body:
1,063 checks, 75 groups/27 threaded scenarios pass under each sanitizer, with
no prior assertions weakened or rewritten. Ninety-nine input hashes are frozen.

The CPU fixture executes actual factory, client start/registration, close
request, adoption, stop, invalidation and power methods. Object references,
init/attach, timer readiness, global sysctl registration and close finalization
are explicit models, not native OSObject/IOKit proofs. The prior actual VM/BO/
client-close suites remain frozen and are not replaced with the model close.
The new fixture does not contain or link an IOKit, Metal or Vulkan runtime.

Threaded cases pause sysctl registration, allocation, init, attach, base start
and post-registration session handling while the actual stop closes admission.
They inspect output refusal, lease drain, the unexposed client's closed gate,
its retained pins and pending registry entry. Eight concurrent factories check
one sysctl registration and distinct client slots. A reader/adopter scenario
exercises configured discovery; another pauses before the seed flush completes
and requires discovery to remain false. Subsequent invalidation, sleep/wake
and stop preserve configured discovery while ordinary queue-live state closes.

The complete original/proposed native class, actual access labels, ABI/topology
and owned headers compile against the independent pinned MacKernelSDK to
nonloadable x86_64 objects. `tools/build34_native_object_check.py` is a new
scoped helper for this check; earlier frozen runners are not refactored. It
freezes SDK and six existing KDK providers, checks kernel-resource reference/
alias interfaces against the matching KDK kernel and admits no new/private
dependency. Native compilation/provider resolution is not loading, actual
collection inclusion, native callback lifetime or a hardware readiness proof.
Both objects retain the same 376 imports and four existing compiler warnings.
No native warning suppression, dependency addition or private KPI bypass is
introduced. Default `make test` also passes with its existing optional
missing-firmware-fixture skip; no fixture firmware is downloaded or executed.

Private attempt 1 stopped on missing/mismatched declarations in the CPU model.
Attempt 2 reproduced the intended old-getter TSan report but the runner refused
the macOS sanitizer abort instead of its expected exit code. An isolated CPU
exit-policy check confirmed that explicitly setting `abort_on_error=0` gives
the requested code; the runner now fixes that option. Those attempts and raw
diagnostics remain private, and neither is called a GPU/installed-driver failure.
The initial corrected scope passed in attempt 3. Attempt 4 expanded the
raw-handoff regression scope but correctly stopped when the sysctl plain-read
mutant did not diagnose under that schedule. The fixture now uses a bounded
condition-variable barrier so all eight factory leases enter before the first
sysctl CAS. This prevents a later callback-gate acquire from serializing away
the intended counterexample. Attempt 5 passes the entire expanded suite;
passing by repeated scheduling retries is not the acceptance rule.

```sh
nice -n 15 taskpolicy -b make -j1 test-build34-exact-factory \
  KERNEL_SDK="$KERNEL_SDK" KDK="$KDK" \
  EXACT_FACTORY_OUT=build/build34-r3-factory-new-private
```

Rollback is to stop deriving this isolated step. No installation, load, IOKit
open, GPU probe, power action, monitoring or recovery replay occurs here.
Preserve accepted R1b/R2a/plugin/startup/recovery and PR28 250 ms with
WindowServer exclusion. Continue the [R3 ledger](BUILD34-R3-PLAN.md): native
reader/coherency, initial external-writer drain, complete capability/session/
Mesa/global-prefix/visibility/CPU-fence protocol, completion notification,
healthy reclamation and actual GPU/FPS/latency/stability acceptance remain.
