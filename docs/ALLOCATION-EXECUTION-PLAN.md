# Allocation snapshot execution plan: review before target use

Latest target update, 2026-11-14: the owner-authorized
[build-37 installation](ALLOCATION-BUILD37-DEPLOYMENT.md), actual normal
restart, exact loaded-image verification and
[two same-boot passive reads](ALLOCATION-PHASE-A.md) are complete. **Phase A
passed** on macOS 26.7.2 build 25G332. Both snapshots had zero observed
refusals. They followed inherited initialization; they do not establish a
pre-initializer baseline or reproduce desktop takeover. Phase B remains
the next integration boundary. The new [startup coordinator source candidate](
ALLOCATION-STARTUP-COORDINATOR.md) implements completed-baseline admission and
a separate recovery dispatcher with multiprocess tests. It is not installed
and still requires native delivery, display adapters and
historical hold/panel-order evidence before the requested desktop attempt.
The later [build-39 native handoff candidate](DESKTOP-NATIVE-HANDOFF.md)
implements an explicit-layout initializer, complete arena reservation and
checked two-engine adoption/claim. It remains uninstalled and unvalidated on
hardware; it does not make the outstanding desktop attempt ready to run.

Historical status before installation on 2026-11-14 after fresh live-execution permission: **private native
build-37 delivery and an exact rollback packet are retained; the operator
confirms an independent recovery route; Phase A remains unperformed**.
The [live preflight and native-build record](ALLOCATION-LIVE-PREFLIGHT.md)
supplies actual current OS/build metadata and private candidate identities.
The [install-packet record](ALLOCATION-INSTALL-PACKET.md) adds the verified
fresh EFI backup. The later [continuity and input revalidation](ALLOCATION-RESUME-REVALIDATION.md)
confirmed the same Goal was active and the retained inputs matched at that
earlier point. The completed restart and Phase A evidence above supersede its
then-unverified reboot/read status.
This plan is not an installer, launcher, arming receipt or hardware result.
The later [capture-runtime delivery](ALLOCATION-CAPTURE-RUNTIME.md) supplies
root-owned tested helpers and an isolated system-interpreter entrypoint; it
did not itself supply a loaded build-37 kernel or startup integration. The
later installation and passive reads supply the loaded-kernel/read evidence.
The consumed build-36 M2/reboot grants remain spent. No installation, target
service open, GPU work, startup edit, arming or reboot was performed in the
preflight/build phase.

The passive-read objective is complete. The immediate objective is now a
concrete reviewed startup chain capable of retaining refusal history from
the requested display attempt before independent recovery. Neither result
would establish acceleration or the allocation root cause in advance.

## Reviewed inputs and present gaps

| Input | Reviewed identity or evidence | What it does not supply |
| --- | --- | --- |
| Build-37 kernel and standalone reader | Reviewed snapshot source `1c17a1712cb3a64db31148cb33d0c2c9741e7e5d`; private native build from `2c26f4deffc4940c1a0a69d9b36c6770191ee0a8`; [installed and passive-read evidence](ALLOCATION-PHASE-A.md) | A pre-initializer baseline, display acceptance or a failed-boot capture |
| Capture helper | `e2cb77bc7b1d0ff058744e1b7a1746da32e2a45e`; [capture contract](ALLOCATION-CAPTURE-CANDIDATE.md) | A supervisor, startup sequencing or recovery integration |
| Independent observer | `25510a8321d45b8223883987c9145652517b4939`; [observer validation](validation/allocation-observer-20261114.json) | Workload admission, proof of report causation or guaranteed completion before recovery |
| Historical combined source/documentation checkpoint | `f3ff243da716ff755433fdb01ac8bb91183682a4` | Later installation, passive-read or integration results |
| Installed monitor | Read-only control-point review; its privately retained hash is unchanged | An approved startup modification or a complete execution audit |

The corrected hosted kernel/reader compile retained zero artifacts; that
historical success is still not a package receipt. The new private local
build separately retains exact kernel/reader bytes, corresponding source,
SDK, signatures and command records in root-owned storage. It does not expand
the two-kext/RADV public publication exceptions to a full stack or the reader.
The earlier [retained-package review](ALLOCATION-PACKAGE-REVIEW.md) remains an
historical inventory of the old build-36 archive and offline build-35 backup.
The operator subsequently confirmed a separately usable recovery route; the
agent has not boot-tested it. A fresh full EFI backup and exact PhxBringup-only
rollback packet passed independent read-back. The fresh preflight observed
macOS 26.7.2 build 25G332 with build 36 loaded; identities must be checked
again immediately before any install/load/read operation.

## Startup ordering found in source

The [reference monitor](../tools/phxctl/phxboot.sh) checks its off/pending
paths, waits for services/framebuffer, invokes the inherited initialization
script, claims the accelerator, enables display gates, then calls `release`.
Its `m2_fail` path performs fallback; `watch_hangs` runs only after the initial
startup path completes. Reading the installed monitor confirmed these control
points and initialization/claim before display release. It has no allocation
observer/capture integration. This is a control-flow finding, not permission
to execute the reference script or proof that its inherited initialization is
audited.

There are two distinct baseline boundaries:

1. **Before explicit startup initialization.** PhxBringup must already exist,
   but the reviewed startup initialization/claim sequence must not yet have
   begun. A baseline here can separate later retained refusals from earlier
   service history. It is not a claim that driver loading did no GPU work.
2. **Before display release.** A baseline after initialization but before
   `release` excludes neither initialization nor claim. It cannot be described
   as preceding all GPU workload, and relevant first-four slots may be full.

The [framebuffer](../src/phxaccel/accel/phxfb.cpp) requests a 120-second boot
hold. The [hold implementation](../src/phxaccel/accel/phxagdc.cpp) also releases
it on timer expiry, independently of the script. The timer starts at hold
initialization, not observer startup. A baseline before the script's explicit
release therefore does not prove the panel was still held. Do not extend or
rearm this safety timer to accommodate collection.

Starting two LaunchDaemons together, a successful process spawn,
`observer.started`, a wall-clock filename, or the existing second-resolution
release log cannot by themselves prove either strict boundary. The observer
publishes its marker after baseline and immediately scans for reports; a
report can already have appeared during baseline. The optional callback in
the new coordinator candidate follows its first post-baseline scan; the
installed startup still has no such handshake. The generic [boot gate](BOOT-GATE.md) is not a drop-in solution:
it executes stages serially and runs a release hook on exit. Placing a
potentially kernel-blocked collector in that stage chain would not establish
independent recovery.

The [reference startup audit](ALLOCATION-STARTUP-AUDIT.md) found a further
admission gap in pinned source fragments: failed initialization or claim can
still reach later setup, because their statuses are not explicitly checked.
The subsequent [source caller-status fix](ALLOCATION-STARTUP-STATUS-FIX.md)
adds those checks and preserves helper failures through the nested wrapper.
It does not supply a compatible initializer, baseline admission, transactional
queue handoff or independent recovery; the reference scripts remain unapproved
for execution.
The later [build-38 claim correction](DESKTOP-CLAIM-FIX.md) rejects a partial
engine handoff in the kernel as well. It remains an uninstalled source
candidate and does not satisfy those other admission or hardware gates.
The recovery function also has serial helper dependencies, although its AGDC
handler schedules teardown work without explicitly waiting for that worker.
The audit's command fakes characterize source control flow; they do not prove
an installed integration or an actual kernel/AGDC hang.

**Current decision: complete the native startup adapters before attaching the
observer or running the outstanding M2 attempt.** The passive-read gate has
passed. The coordinator source and its tests close part of the implementation
gap, while compatible initialization, native acceptance and historical hold
ordering remain unresolved. This plan is not a runnable integration.

## Required private execution packet

Before any target mutation, a separately reviewed packet must contain actual
values for each item; an empty field or example value is a refusal condition:

- Exact source/commit identities and retained kernel/reader package hashes,
  architectures, signatures, build provenance and expected loaded image.
  Loaded-image UUID matching is additional evidence, not a substitute for
  package integrity or full installed-source provenance.
- Pinned capture/observer bytes, Python interpreter and import locations,
  ownership, permissions and trusted parent paths. The live helpers require
  administrator x86_64 macOS. Symlink-containing paths are not acceptable.
- Current boot/service/build/OS identities, installed stack and startup hashes,
  firmware-framebuffer state, display gates, existing off/pending/M2 markers,
  one-shot arming state and competing GPU/reboot activity. Historical build-36
  fallback readbacks must not be substituted for this live preflight.
- A fresh private evidence parent, a nonexistent per-phase output directory,
  space/permission checks, the selected report directory and a finite scope.
  Preserve root-owned 0700 directories and 0600 evidence. Never clear an old
  attempt or select a new directory to replay a consumed grant.
- An exact backup/restore manifest for each proposed installed change, a
  reviewed firmware-desktop return path and an operator recovery procedure.
  An external recovery route must be verified rather than assumed. Record
  whether its availability is operator-attested or agent boot-tested, and
  what remains unrecoverable under a hard kernel/bus hang.
- Separate authorization for the particular package/install/load operation,
  passive reader invocations and any normal reboot required for that load.
  GPU initialization, M2 arming and a display attempt are separate scopes.
  Record a durable one-use grant claim before the first authorized mutation.

Keep machine identities, absolute installed paths, loaded UUIDs, raw reports,
report names and raw I/O/log output in ignored private storage. A future
sanitized public result should contain only reviewed aggregate facts and
source/provenance references.

## Phase A recipe: passive firmware-desktop read, completed 2026-11-14

The following recipe was completed in the separately recorded
[Phase A scope](ALLOCATION-PHASE-A.md). Its baseline and second-read claims are
consumed; do not replay them. The recipe describes the evidence boundary.

1. Review the exact package and rollback first. If installing/loading build 37
   requires a reboot, scope that normal firmware-desktop boot separately.
   Keep M2 and persistent/one-shot display arming absent. Do not manually
   replay inherited GPU initialization or change runtime/plugin/EFI/security.
2. Perform the live preflight from the packet. Refuse on an unexpected loaded
   build/image, service ambiguity, unfinished attempt, competing activity or
   uncertain recovery state. The capture helper's own identity brackets do
   not replace these deployment checks.
3. Use the existing capture helper for exactly one baseline and, only after
   its completed result validates, exactly one failure-phase read in the
   **same boot and service**, with no added GPU workload between them. The
   phase name `failure` does not mean that a failure was induced. Do not run
   the observer or create synthetic reports in the system diagnostic folder.
4. Review phase status files, reader output, full schema, baseline hash and
   all identity brackets. A published valid baseline plus a matching completed
   second read proves readable software history and comparison on that boot.
   Background activity may change counters; it must be reported, not forced
   to zero or automatically classified as corruption.
5. Read back framebuffer/gates/arming and installed inputs against preflight.
   Apply only the separately authorized restoration procedure if needed.
   Preserve raw evidence, even on refusal. No automatic escalation to M2.

An unsupported selector, identity mismatch, timeout, interruption, malformed
result or blocked reader ends the phase. Its attempt marker stays consumed;
there is no retry or automatic new directory. A timeout bounds child waits,
not uninterruptible IOKit or filesystem work. Do not treat process termination
as cancellation of an in-flight kernel method. If a collector remains blocked,
do not start another reader or GPU test to work around it.

Passing Phase A would **not** prove that the refusal writers populate the
history during a failure, that a baseline preceded initialization, or that
recovery remains available under a GPU hang.

## Phase B: review startup admission and recovery before a display attempt

This phase is source/design work until a specific integration is reviewed.
Keep one candidate and one variable: retain existing driver behavior, VM
guards, budgets, pin direction, cleanup, userspace and recovery thresholds.
Do not introduce a reset, reaper request, polling reader or retry.

The integration must demonstrate all of these properties before installation:

- One observer owns one baseline and at most one failure read. Do not call
  standalone `baseline` first and then point the observer at that directory:
  the observer creates its own fresh baseline and refuses directory reuse.
  Phase A output cannot serve as the next display boot's baseline.
- The workload admission decision occurs before the selected explicit
  initialization boundary. It verifies a completed baseline's identity/hash
  and retained capacity, not merely process existence or an observer marker.
  A missing, late, refused or changed baseline prevents the new workload;
  there is no automatic rearm or second initialization attempt.
- After admission, require explicit success from the reviewed initialization
  and claim steps before display setup/release. Matching filtered output or
  the final shell command's success is insufficient. A failure takes only
  the separately reviewed skip/recovery path, without another initialization.
  Review the initializer's own argument/error contract and watchdog ownership;
  the legacy wrapper's bare GART/MES calls, private-helper provenance gap and
  global shutdown-process kill cannot be treated as an audited initializer.
- An already available recovery path remains independent throughout watch
  setup, baseline, admission and failure collection. It never waits for an
  observer acknowledgement, result, kill or reap. The current monolithic
  monitor has no such baseline admission point; a wrapper or arbitrary shell
  hook is not evidence that this requirement has been met. Review the exact
  change and its skip/fallback path, including recovery helper non-return,
  before proposing deployment. Preserve the existing asynchronous AGDC work
  scheduling and recovery thresholds; an injected blocked helper is not an
  observed kernel deadlock or permission to change that policy.
- Use a same-boot monotonic event trail for completed baseline, admission,
  explicit initialization/release and recovery decision, with private boot
  identity and integrity links. Record the baseline-file hash at admission.
  Evidence must also account for automatic hold expiry or earlier panel open;
  a late state read alone cannot establish historical ordering. Ambiguous
  ordering means the requested boundary is unproven, not a successful run.
- Verify the real integration with fake identities/I/O and separate processes:
  blocked/dead observer, missing/invalid/late baseline, early report, deadline
  crossing, service/boot replacement, first-four exhaustion, early pending
  recovery and competing attempts. Prove the actual proposed fallback path
  proceeds under those failures. Existing stub-recovery tests are insufficient.

A proposed observer window is **180 seconds**, within its 1–300-second input
contract. It begins before watch setup and baseline, not at display release;
it does not cover indefinite later `watch_hangs` activity. Pin the selected
value and workload scope in the final packet. Existing limits remain 64
notifications, at most 66 scans and at most 4,096 entries per scan. Expiry or
an event/entry limit terminates collection without retry; it never extends
the hold, delays fallback or creates another observer.

## Phase C: one display attempt, only after all earlier gates

The final packet must identify exactly one initialization/display attempt,
its consumed grant, permitted one-shot state change, explicit observation
window and existing automatic fallback. Any preparation reboot and a possible
fallback reboot must be described separately; a generic reboot grant is not
an unlimited restart budget. Do not persistently rearm M2 or suppress recovery
to obtain a snapshot. Do not execute the old reference script by this document.

At execution, validate the completed baseline and admission evidence, then
permit only the reviewed workload sequence once. The observer reacts to a
new report discovery; the existing recovery path acts independently. A report
arrival is not a guaranteed first crash and does not prove capture preceded
fallback. If the snapshot finishes too late or the service/boot changes, keep
the partial evidence and classify the failed-boot capture as unavailable.
Never substitute a firmware-fallback boot's history for the failed boot.

After recovery, use a bounded separately reviewed collection scope. Separate
preparation, attempted-display and fallback boots; validate report headers,
capture times, PIDs and loaded images privately. Verify actual firmware
framebuffer, gates, consumed arming/markers, absence of pending competing work
and unchanged installed/EFI manifests. An automatic restart alone does not
prove the machine returned to a usable firmware desktop. Do not mount or
modify EFI just to perform these checks.

## Evidence required for each conclusion

| Observation | Supported conclusion | Still unproven |
| --- | --- | --- |
| Valid Phase A baseline and matching second read | Snapshot transport/schema and same-boot comparison worked there | Refusal population, failed-boot capture, GPU correctness |
| Valid `failure.json`, linked baseline, same identities and ordering trail | A completed comparison for the identified observation interval | Correlation to any particular external request or crash |
| Unsaturated category counter increases | That retained refusal category occurred after baseline | One-to-one correspondence with RADV samples or unique requests |
| New retained retirement/overlap records | The recorded branch and its stored queue/sequence observations | A hang, stall duration or whether progress would later occur |
| New `host-prepare` record retaining raw 2 | The preparation stage returned that native code | Host-page origin, permissions or the deeper reason for refusal |
| Only trigger marker, raw stdout, `.incomplete`, or timed-out attempt | A trigger or partial attempt, depending on the file | A completed or durable failure snapshot |
| New crash report plus matching private boot/process/image evidence | A correlated failure consequence | GPU causation or the allocation root cause |

First-four slots belong to the service and are never reset. A full relevant
category at baseline can still yield a counter increase but no new details;
if the experiment requires those details, that is a no-go for this scope.
Saturated counters supply lower bounds. Counts include repeated/internal
cleanup attempts and cannot be equated with sampled RADV refusals. The wire
format has no task/context/BO identifiers or page contents, so this plan cannot
add request-level or page-permission evidence by interpretation.

A valid-but-pending observation is not a hang diagnosis. Establishing lack of
progress would require a separately scoped observation design, not an
unapproved retry loop around this two-read candidate. Existing real build-36
Busy/raw-2 samples still do not identify the pending/invalid branch or confirm
the host preparation stage. No policy/budget/pinning change is justified by
the current missing evidence.

## Present go/no-go decision

| Gate | Current status | Required before proceeding |
| --- | --- | --- |
| Reviewed source and offline contracts | Complete; [observer record](validation/allocation-observer-20261114.json) | Preserve the pinned input identities |
| Retained target package and rollback packet | Prepared and independently read back; recovery route operator-attested | Recheck exact bytes and live identity before any mutation |
| Goal continuity admission | Normal restart, resumed session and same-boot exact-image readback recorded | Preserve active-state and consumed-claim guards for the next scope |
| Trusted capture runtime | Root-owned helper/interpreter/import closure delivered and verified; used for Phase A | Deliver and pin any changed observer/coordinator and native adapters separately |
| Passive firmware-desktop read | Phase A passed: two same-boot build-37 reads, all reason counts/deltas zero | Claims consumed; these post-inherited-initialization reads cannot be the next startup baseline |
| Ordered startup integration with independent recovery | Source candidate and fake-process integration tests implemented; not installed | Compatible native initializer/claim/display/monitor/recovery adapters, input delivery, historical hold ordering and rollback review |
| One display/M2 attempt | Owner requested; outstanding attempt remains unconsumed and unexecuted | Complete preceding technical gates and bind the exact one-use packet to that request |
| Allocation root cause | Unconfirmed | Captured target evidence within its stated limits |

The original [machine-readable plan](validation/allocation-execution-plan-20261114.json)
records its source boundaries, unresolved gates and plan-only validation.
The later [startup source audit](ALLOCATION-STARTUP-AUDIT.md) adds failure
propagation evidence and requirements. Neither supplies an installed observer,
startup integration or a target execution grant.

The [initializer interface review](ALLOCATION-INITIALIZER-CONTRACT.md) exercises
the complete current mesboot entrypoint and the existing stage executor with
fake I/O. It identifies the legacy claim/layout boundary and the executor's
synchronous release dependency; neither is a complete initialization chain
or independent recovery implementation.

The [queue handoff review](ALLOCATION-QUEUE-HANDOFF.md) adds actual two-engine
helper evidence: a graphics failure after a fake successful compute adoption
still lets the old output filters return zero and request a claim hook. It
preserves raw failures 74/75 and distinguishes fake transport acceptance from
kernel adoption or claim. A complete candidate must carry every required
engine's status and owned resource lifetime through the handoff; aggregate
readiness and filtered output are insufficient.
