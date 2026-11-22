# Build34 R3 staged submit receipts

November 21, 2026: the source-only R3 protocol now has an experimental submit
operation returning the same complete identity accepted by the earlier wait
and ACK operations. This is not native capability/session admission, a Mesa
wire adapter or a deployable kernel. The hardware reader stays null, all
permanent client/service retention remains, and all 172 protected production
inputs and the installed build34 configuration remain unchanged.

## Submit contract

The original MIT [wire header](../tools/build34_exact_submit_wire.h) reserves
selector **66** only in the staged experiment, after wait/ACK selectors 64/65.
It includes the existing native submission structures with their unchanged
provenance and layout; it does not change the production native ABI header.
Its fixed 2,112-byte little-endian inband request consists of:

| Offset | Field | Bytes |
| --- | --- | --- |
| 0 | wire version and full envelope size | 8 |
| 8 | owner epoch | 8 |
| 16 | two reserved zero words | 16 |
| 32 | existing `phxn_cs_in` header | 32 |
| 64 | 64 existing `phxn_cs_ib` records | 2,048 |

The declared IB count must be 1–64, and every unused IB record must be zero.
Scalar, descriptor, asynchronous and variable-output shapes are refused.
Input and output sizes must match exactly. The request is copied once before
the handler acquires the client lock, supporting unaligned and overlapping
inband buffers without re-reading mutable input after a queued lock.

Under that lock, the handler requires Hello, the pinned embedded registry's
client/provider identity, both terminal gates and a matching owner epoch.
The owner is an identity counter, not an authorization credential. An eventual
native session handshake must supply it; today only the CPU fixture requests
exact mode before start. Legacy clients cannot obtain this operation simply
by guessing an existing owner.

The [transform](../tools/build34_exact_submit_receipt.py) derives a separate
typed exact-submit helper from the actual already-tested staged `doSubmit`.
It preserves existing context/IB/address/mapping/flag validation and the
actual service submission, including R1b queue-space retries. The old submit
method is unchanged. Additional exact-only restrictions are:

- All IBs must request one engine. The service may still select its existing
  fallback queue; the reply records the **actual** queue and generation.
- CPU user-fence requests are refused. Their per-submission exact publication
  and visibility protocol is not implemented; the old pending-fence slot is
  not silently treated as an exact-fence solution.
- No GPU-ready path means refusal, never the legacy mock immediate success.

A successful submit publishes the owned reservation before the actual
ring/writeback/doorbell writes, then returns the registry's receipt, not a
reconstructed sequence-only identity. The 64-byte reply reuses the earlier
receipt layout with status **3 submitted**. It carries owner, serial, slot,
sequence, generation and queue; reserved bytes are zero. No global prefix
or completion/CPU-visibility guarantee accompanies submission.

Only a successful, terminal-gate-rechecked operation writes output. An error
after packet publication can therefore be uncertain: the published receipt
and all resources stay retained, and the caller must not retry as though
nothing was submitted. Cancellation can remove only an unpublished Reserved
entry. Full receipt capacity refuses before dispatch; as in the previous
typed submit, validation/cache flush/VM setup are not represented as a
transaction with no side effects.

## Validation and limits

The [CPU runner](../tools/test_build34_exact_submit_receipt.py) freezes and
hash-checks the previous experiments, native ABI and protected production
inputs. It extracts the actual staged submit, service, external dispatcher,
wait and ACK methods. Existing methods and legacy dispatch are checked
byte-for-byte, apart from the new route before the client lock. Unrelated
legacy handlers are stubs. A separately compiled C peer uses fixed offsets
to encode requests and validate replies; it is not the production Mesa client.

ASan/UBSan and TSan each pass **212,170 additional checks in 2,371 groups and
seven real-thread scenarios**, plus **4,983** inherited binding checks.
All **15 defective variants** are detected at runtime. The checks cover
submit → pending wait → completed wait → ACK → stale
token refusal, actual queue fallback and full-width sequence/generation,
all 128 homogeneous batch shapes, mixed-engine and user-fence refusal,
malformed shapes and length sweeps, a full 64-entry table and slot reuse.
Seven real-thread cases cover input modification after capture and client or
service closure before dispatch, during packet emission and before output.
Published work remains retained on uncertain failure. Deliberately defective
variants test the identity, copy, shape, queue, output and terminal checks.
See [sanitized evidence](validation/build34-r3-submit-receipt-offline-20261121.json)
for the final counts, frozen hashes and preserved CPU fixture failures.

```sh
nice -n 15 taskpolicy -b make -j1 test-build34-exact-submit-receipt \
  EXACT_SUBMIT_RECEIPT_OUT=build/build34-r3-submit-receipt-new-private
```

No complete native translation unit, actual Kernel SDK, MIG/IOKit path or GPU
is exercised. In particular, CPU byte doubles do not prove native kernel
stack use, inband transport delivery or final OSObject lifetime. Capability
and session admission, independent genuine global-prefix/visibility and CPU
fence publication, Mesa binding/backpressure integration, a trusted device
reader, healthy drain and native completion events remain outstanding.
The [R3 ledger](BUILD34-R3-PLAN.md) still requires native integration and real
GPU/FPS/stability acceptance. Do not build or deploy the quarantining staged
source. There is no changed installed state to roll back; keep accepted
R1b/R2a/plugin/startup settings and the R4–R6 hold.

## Mesa transport pairing

The follow-on adapter connects the actual Mesa 0007 completion cache to the
actual staged submit, wait and ACK handlers in the same process. It checks
the Mesa and Phx submit layouts at compile time, wraps the single batch in a
zero-initialized 2,112-byte envelope and checks the full 64-byte reply. Wait
and ACK require the exact echoed receipt. The returned queue is the native
queue chosen by the driver. The adapter rejects CPU user-fence requests
locally before entering the wire. See [`build34_r3_mesa_wire.c`](../tools/build34_r3_mesa_wire.c).

The adapter takes a connection-bound owner and an independent prefix
operation from its caller. A successful exact wait reads the same session's
prefix with a zero-time snapshot before returning both observations to Mesa.
This adds one prefix call to an uncached successful wait. A prefix read
failure delays completion publication and ACK. An owner mismatch or invalid
prefix fails the session. The pairing test supplies the prefix from the
staged retirement method operating on CPU-backed fences. Native prefix
transport, visibility and timing remain open.

For the reviewed selector-66 implementation, `Busy` and `NoResources` return
before submission publication and before a native receipt survives the
request. The adapter reports those statuses as retryable backpressure for
that implementation. It treats a lost or malformed reply after dispatch as
uncertain. Only ACK's specific `Busy` status retains retryable ACK ownership.
Binding requires the same checked protocol implementation and session for all
callbacks, plus caller quiescence before destruction.

The runner rechecks all 30 pinned Mesa inputs, reapplies 0003–0007 and runs
the staged native regression suite before pairing both sides. ASan/UBSan
and TSan each pass 5,674 paired checks. The test covers GFX completing while
an earlier Compute receipt holds the global prefix, late cache reads after
ACK, full 64-receipt admission and recovery, CPU-fence refusal, and corrupted
or lost replies. See the [validation record](validation/build34-r3-mesa-wire-offline-20261122.json).

```sh
make -j1 test-build34-r3-mesa-wire MESA_SOURCE="$MESA_SOURCE" \
  R3_MESA_WIRE_OUT=build/build34-r3-paired-mesa-wire-new-private
```

The stage runs through CPU call doubles. Production integration still
requires negotiated capability and immutable session identity, the actual
IOKit call and checked prefix path, CPU-fence publication, caller retry and
lifecycle handling, and hardware validation. Rollback is to omit the
isolated adapter and its test target.

### Separate sequence dispatch by mode

The earlier composed dispatch lets a bound exact client reach legacy
`Submit` and `WAITSEQ`. The old submit path returns only a sequence number,
even when it reserves receipt metadata internally. Reaching it from a
paired exact session would leave work without a receipt the Mesa cache can
authenticate. Legacy `WAITSEQ` also has CPU-fence side effects and cannot
implement the pure snapshot required by the cache.

The [isolated dispatch transform](../tools/build34_exact_dispatch_mode.py)
derives the latest mapping-admission stage. After the existing client and
provider checks, exact sessions refuse legacy `Submit` and `WAITSEQ`, and
legacy sessions refuse the three exact selectors. Other dispatch is unchanged.
No factory or Hello change binds an exact client in production.

The pairing runner composes and fingerprints the full source delta, then
places the new dispatch body into the CPU receipt fixture. Lifecycle fields
in that fixture are models, and the current legacy WAITSEQ body is a stub.
The exact path still exercises the actual staged receipt handlers. Tests
prove wrong-mode requests do not reach sequence handlers, and a legacy
client still reaches both legacy routes. ASan/UBSan and TSan each pass
5,765 checks. See the [dispatch pairing record](validation/build34-r3-mesa-dispatch-offline-20261122.json).
Omit the transform to roll it back.

### Bound-session query and checked prefix

The [progress wire stage](../tools/build34_exact_progress_wire.py) replaces
the injected prefix callback and owner value in the CPU pairing. The Mesa
adapter uses the same call interface for submit, wait, ACK, prefix (67) and
session query (68). Both new selectors require the exact-client dispatch
mode and use a 32-byte request and a 48-byte reply. The session query checks
that an already bound client can read progress, then returns its owner,
build and capability flags. It does not negotiate or admit an exact client.

The independent prefix path calls `exactGlobalRetiredLocked` under the
service callback lease and GPU lock. It requires valid fence observations
from both adopted queues. A valid zero prefix is a successful reply; an
invalid observation is an error, not a zero prefix. If a positive-budget
prefix wait has not reached its target, it checks elapsed time and retries
with neither the client nor GPU lock held during the polling sleep. A valid
below-target reply at the deadline means pending. The extra snapshot after
an exact wait is independent of that wait's receipt and can stay below an
unfinished earlier submission on the other queue.

The paired CPU run passes 7,886 checks each under ASan/UBSan and TSan, with
30 pinned Mesa inputs and all 172 protected production inputs unchanged.
It covers a legal zero prefix, failed reads, stale identity, malformed
progress replies, unlocked polling and queue loss during sleep. See the
[progress pairing record](validation/build34-r3-mesa-progress-offline-20261122.json).
The reader uses CPU storage and lifecycle state is modeled. No IOKit
connection, trusted BAR0 read, AMD event or production exact capability is
enabled. The CPU-fence refusal and legacy runtime behavior remain. Rollback
is to omit this isolated stage and use the preceding adapter and runner.

### Mesa IOKit connection adoption

The [IOKit source stage](../tools/build34_r3_mesa_iokit.py) extends the pinned
Mesa `ac_darwin_iokit.c`. The exact constructor takes an exclusively owned,
already-open direct connection and an empty output slot. Invalid arguments
leave both unchanged. After taking the connection it clears the caller's
handle, checks the ordinary Hello contract (ABI, build 34, batch capacity
and VMID), then queries the already-bound exact session on the same port.
The connection context owns the wire adapter. The constructor publishes
the transport only after the Mesa completion cache is configured, before
any sequence traffic. A failed attempt closes the consumed handle once
without publishing the transport, opening a different connection or
falling back to legacy submission. Legacy matching and proxy selection do
not invoke this constructor.

The fixed struct calls go through Mesa's existing `IOConnectCallMethod`
wrapper; none of the exact requests supply scalar arguments. The full
staged IOKit unit compiles with the macOS SDK. Both sanitizers pass 8,466
checks including the earlier wire suite, one full dual-queue round trip
through the IOKit call shape, and 11 failed adoption cases (Hello/session
refusal, malformed identity and allocation failures). The test executable
does not link IOKit: local doubles implement the OS symbols and abort on
device matching, opening or mapping. Hello and device state are modeled.
See the [IOKit pairing record](validation/build34-r3-mesa-iokit-offline-20261122.json).

```sh
make -j1 test-build34-r3-mesa-iokit MESA_SOURCE="$MESA_SOURCE" \
  R3_MESA_IOKIT_OUT=build/build34-r3-mesa-call-adopt-new-private
```

Use a fresh ignored directory as shown; the pinned predecessor's linkage
check also scans the executable path in `otool` output. This constructor
does not authorize opening a client or prove the identity of the loaded
driver. Kernel admission, real MIG delivery, DRM core publication and
quiescence of callers before closing remain required. The close callback
does not certify GPU/resource drain. The 172 production inputs, installed
state and production exact capability remain unchanged. Roll back this
source-only step by omitting the IOKit transform and optional test target.

### DRM publication and sync shutdown

The [DRM stage](../tools/build34_r3_mesa_drm.py) adds an explicit exact-only
initializer to the staged Mesa source. It consumes a supplied connection
only when no core is active or closing, completes IOKit adoption and the
existing DRM handshake, then publishes the core after the first sync clone
exists. Additional exact devices can deliberately join that core without a
new port. A second supplied port or a legacy client cannot silently take
over or share it. Failure after consuming the connection does not publish
the core or retry with the legacy backend.

The preceding core closed its transport when its last device went away,
even though independently held sync clones could still call the backend.
The staged last-device close removes the core from publication and closes
sync admission before releasing the transport. A sync waiter holds a
counted lease for the complete callback, with no sync lock held during the
transport call. Close wakes pending waiters, waits for admitted callbacks
to return, discards their late results, then clears the old context. It
refuses new core creation during this drain. Callers still must quiesce
direct device operations before freeing that device or its last provider
handle. A wedged OS call has no proven cancellation path; the user-space
drain is not a timeout guarantee, native queue drain or BO-release proof.

ASan/UBSan and TSan each pass 8,832 checks. The CPU pairing uses the actual
DRM ioctl path, sync-provider clones, Mesa IOKit wrapper and staged exact
handlers. It completes later GFX while earlier Compute remains pending,
holds a Compute callback across last-device close, verifies both an
unsubmitted wait and a late returned completion are canceled, and checks
single close and first-clone allocation failure. See the
[DRM pairing record](validation/build34-r3-mesa-drm-offline-20261122.json).

```sh
make -j1 test-build34-r3-mesa-drm MESA_SOURCE="$MESA_SOURCE" \
  R3_MESA_DRM_OUT=build/build34-r3-mesa-drm-drain-new-private
```

The OS symbols, Hello and device state are still test doubles. The normal
RADV path does not call the exact initializer, and no real connection,
production capability, kernel admission, GPU work or install is enabled.
No protected production input changes. Omit this stage and its target to
return to the preceding IOKit pairing.

### Exact user-client open admission

The [open stage](../tools/build34_exact_open.py) derives the full staged
receipt/progress driver. It assigns exact mode from a distinct build34-only
`N48R` user-client type, not from a selector, Hello/build field or queue-ready
bit. The factory checks the IOKit owning task's administrator privilege before
allocation; initialization rechecks it. Existing `N48N` startup still selects
legacy mode. A failed `N48R` open never falls back to `N48N`.

Exact open requires separate native completion admission, a bound reader,
an active service and both live queues in their expected roles. The factory
captures the invalidation epoch and both generations under `gpuLock`. The
embedded client binding and final handler publication revalidate the same
tuple. If binding fails, the client cannot return a handler or create a legacy
registration. If readiness is lost after binding, the factory closes the
unexposed client's callback admission before detaching and dropping its
initial reference. The existing close protocol retains uncertain registration,
provider and resource pins. No new teardown proof is inferred from a refused
open. The provider stop gate closes independently of `gpuLock`; the final
check does not prove an atomic native IOKit/MIG handoff with stop.

Native admission deliberately returns false. The device reader and event
adapter remain null. Tests separately exercise that refusal and an explicit
CPU-only positive model of the admission prerequisite. Each sanitizer passes
259 checks, including eight threaded stop, sleep and generation-change
cases. Seven broken variants are rejected. Two complete x86_64 nonloadable
`MH_OBJECT` files compile against the pinned SDK; all 381 unchanged imports
resolve through the six existing declared providers in the matching KDK.
Compared with the older 376-import factory stage, the five imports already
in the progress predecessor come from checked overlap identity, HQD sampling
and the unbound IOKit wait adapter. See the
[open evidence](validation/build34-r3-exact-open-offline-20261122.json).

```sh
make -j1 test-build34-exact-open KERNEL_SDK="$KERNEL_SDK" KDK="$KDK" \
  EXACT_OPEN_OUT=build/build34-r3-exact-open-new-private
```

No IOKit client was opened; no ISR, runtime entrypoint or GPU work was
enabled. The 172 production inputs remain unchanged. Omit the open transform
and optional test target to return to the prior staged driver. Before a
native session, prove external queue ownership/drain, coherent fence reads,
real caller privilege and MIG delivery, RADV pairing and teardown. The
offline administrator policy is not proof that the intended production RADV
callers qualify or should gain raw diagnostic privileges.

## Explicit Mesa exact service open

The [source-only open stage](../tools/build34_r3_mesa_open.py) derives the
reviewed IOKit, DRM and sync stages. The explicit Mesa DRM constructor opens
`PhxBringup` with the current owning task and the factory's shared `N48R` type.
It makes one open attempt, releases the service reference independently of
the connection and hands a valid connection to the existing Hello/session
adoption. No legacy `N48N`, proxy or mock is used on refusal. An adopted
connection is closed exactly once if negotiation or initialization fails.

The same constructor reuses a published exact core without opening another
client; it refuses a legacy core or an in-progress final close. It publishes
no core before the first sync clone succeeds. The CPU test doubles check
matching, absence, admission errors, invalid success ports, handshake/session
refusals, allocation failures and reuse. The staged DRM submit/wait/ACK test
now starts with the explicit open, completes the later GFX receipt while
Compute is pending, and observes transport close only after callback drain.

Both ASan/UBSan and TSan pass 9,559 checks. The fixture uses SDK signatures,
does not link a device runtime, and preserves all 172 production inputs.
See [sanitized evidence](validation/build34-r3-mesa-exact-service-open-offline-20261122.json).

```sh
make -j1 test-build34-r3-mesa-exact-open MESA_SOURCE="$MESA_SOURCE" \
  R3_MESA_EXACT_OPEN_OUT=build/build34-r3-mesa-exact-service-open-new-private
```

This stage alone leaves the normal RADV physical-device/profile and winsys
entrypoints unchanged. There was no real IOKit open, MIG exchange,
reader/event binding, load or GPU work.
Omit the open stage to retain the previous caller-supplied-connection stage.

## Isolated RADV entry pairing

The [next source stage](../tools/build34_r3_radv_entry.py) routes the existing
Darwin `ac_drm_device_initialize` entry to the exact-only constructor.
The pinned winsys query and logical-device creation both use that initializer;
there is no environment switch or legacy retry in this stage. Enumeration
holds that DRM device across physical-device construction, copies the profile
from the same negotiated core without a temporary device or sync clone, and
passes ownership to the physical device up to its existing destructor. A
construction failure releases the owner. If construction already holds an
owner, enumeration drops its extra reference. The production Mesa path and
the earlier IB-tail runtime recipe are not changed.

The actual staged enumeration function, wrapper, and DRM transport path pass
10,000 checks each under ASan/UBSan and TSan. The CPU model checks that a
non-canned profile reaches enumeration, that query and logical-device
acquisition reuse one exact connection, that either destruction order
closes it only at the last release, and that failed enumeration publishes no
device or fallback. Full staged wrapper and physical-device translation
units also pass syntax checks with the previous isolated Mesa configuration.
Physical-device construction and winsys operations are modeled, not a full
Vulkan runtime test. See the
[offline result](validation/build34-r3-radv-exact-entry-offline-20261122.json).

```sh
make -j1 test-build34-r3-radv-entry MESA_SOURCE="$MESA_SOURCE" \
  R3_RADV_ENTRY_OUT=build/build34-r3-radv-exact-entry-new-private
```

Use the pinned Mesa dependency closure plus the baseline wrapper, physical
device and winsys sources identified by the report. Omit this stage to keep
the previous explicit open without changing normal entrypoints. This CPU
fixture does not link or load the full R3 runtime.

## Private full RADV link

On November 23, 2026, the [compile-only recipe](../tools/build34_r3_radv_runtime.py)
verified the complete 12,969-entry Mesa baseline and overlaid only the hashed
R3 pairing outputs, frozen protocol sources and two Meson entries. It compiled
and linked the complete x86_64 RADV dylib in 775 steps. The final link checks
verify eight reviewed translation units, including the winsys query/create
unit and exact wire adapter, their required headers, the exact open/profile/
sync-drain and Vulkan entry symbols, and no strong dynamically looked-up
imports. The IOKit import set remains the same eight functions covered by
the earlier CPU fixture. The uninstalled result is 20,702,984 bytes. See the
[sanitized link record](validation/build34-r3-radv-full-link-offline-20261123.json).

```sh
python3 -B tools/build34_r3_radv_runtime.py \
  --mesa-source "$FULL_MESA_BASELINE" --entry-evidence "$R3_RADV_ENTRY_OUT" \
  --toolchain-bin "$MESA_TOOLS" --toolchain-bin "$GLSLANG_BIN" \
  --toolchain-bin "$PKG_CONFIG_BIN" --out build/build34-r3-radv-link-new-private
```

The isolated build retains the original source notices and checks that all
172 production inputs remain unchanged. Outputs stay in the ignored private
directory; the recipe never loads, installs, signs for deployment or uploads
the runtime. Reverting the optional recipe requires no live rollback. Next,
exercise Vulkan enumeration and logical-device teardown with the full linked
library under an IOKit substitute that refuses any real opens. Real
owning-task admission, MIG, IH ownership/drain, fence visibility and GPU
acceptance remain separate and unproven.
