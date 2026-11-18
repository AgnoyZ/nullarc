# Build34 VBL scheduling candidate

Status on 2026-11-18: **the third, corrected-cache candidate boot passed exact
loaded-image admission, bounded accelerated startup and independent readback.
The initial finite GUI comparison improved, but a fresh same-boot check after
about 15 minutes reproduced 15 GUI intervals over 100 ms while VBL plateaus
over 80 ms remained zero. Residual GUI stutter is unresolved. The candidate
remains active.**
An independent CPU-only timer program subsequently reproduced delayed Mach
timer messages under normal application scheduling while its direct-wait
worker remained responsive; see the timer-delivery investigation below.
CPU, native, complete-cache and independent installed-state checks passed. The initial
direct-thread-call candidate failed target linking; a private-provider attempt
was also rejected. The selected implementation uses public IOKit timer APIs.
The accepted build34 acceleration and desktop remain active. The original-ACPI
restart baseline subsequently passed the independent readback recorded below.
This demonstrates an improvement in the bounded GUI/VBL comparison, not a
general stutter repair, physical scanout FPS or long-term stability result.

## Unattended reproduction

The owner reported that macOS was initially smooth after login and later became
sluggish, including the pointer, and asked for help while away from the machine.
The running OS was macOS 26.7.2, build 25G332. Bounded diagnostics used the
existing default-build34 installation; no bring-up, historical admission trial,
GPU benchmark, power action or resident monitor was started.

An initial CLI-launched Cocoa panel inherited the remote runner's background
scheduling policy. Its large timer delays, including a second run with an App
Nap assertion, are **not normal-GUI latency evidence**. They are excluded from
the diagnosis and from any performance comparison below.

A fresh accessory application was instead launched through Launch Services in
the unlocked console session. Its small, nonactivating panel ignored mouse
events, requested a simple CPU-drawn update at 60 Hz, independently checked its
own window was onscreen, and closed automatically after a nominal 15-second
run-loop interval. A separate supervisor enforced a finite process deadline.
This exercised ordinary composition; the application source did not explicitly
create a Metal device or submit a native/Metal test workload. AppKit/Core
Animation can still discover Metal devices internally, and WindowServer uses
the existing accelerated compositor.

The useful final run also sampled an independent, user-initiated worker that
waited approximately 10 ms using `mach_wait_until`, then read the synthetic VBL
counter. It recorded both absolute-clock and wall-clock timestamps. A bounded
three-second stackshot targeted only that app, WindowServer and kernel_task.
The app's main thread was sampled at base priority 46, rather than the invalid
CLI run's base priority 4.

| Observation | Final run |
| --- | ---: |
| Reported elapsed time, including initialization and delayed delivery | 16.876863 s |
| Actual view draw callbacks | 618 |
| Main timer intervals | 625 |
| Main timer median / p95 | 16.693 / 18.440 ms |
| Main timer p99 / maximum | 304.943 / 519.117 ms |
| Main timer intervals over 100 ms | 17 |
| Independent worker intervals | 1,488 |
| Independent worker maximum, absolute / wall clock | 15.351 / 15.214 ms |
| Independent worker intervals over 33.34 ms | 0 |
| Onscreen checks passed | 10 of 10 |
| VBL plateaus over 80 ms | 19 |
| Longest sampled VBL plateau | 514.871 ms |
| Main intervals over 100 ms overlapping a VBL plateau | 17 of 17 |
| Compositor present-counter increase across the supervised run | 586 |
| Display-completion late-counter increase | 4 |
| Copy failure / copy skip / surface GPU timeout / hang-kill increases | 0 / 0 / 0 / 0 |

The worker remained responsive during the GUI/VBL pauses. Its timestamp and
counter reads are sequential, with roughly 10–15 ms observation resolution;
plateau boundaries are sampled estimates, not hardware interrupt timestamps.
The overlaps establish correlation, not proof of a particular blocking call.
Draw callbacks, compositor presents and synthetic VBL counts are distinct;
none is a physical scanout FPS measurement. Driver surface-wait counters also
do not measure the ordinary-app PR28 publication-wait budget.

WindowServer stayed alive. Kernel stacks repeatedly showed an AppleACPIEC /
AppleACPIPlatform callback in `thread call high #9`; one bounded stackshot
reported about 0.750 CPU seconds for that thread. This is the leading source-
supported contention hypothesis, **not proof that ACPI/EC caused each pause**.
The failed S5 candidate still loaded from the current boot is a confounder for
later ACPI experiments; its verified on-disk rollback remains intact. No
specific AML, wake source or shutdown repair is established by this check.

## Narrow source candidate

The accepted framebuffer uses `thread_call_allocate`, whose default role is
`THREAD_CALL_PRIORITY_HIGH`. Apple's API describes HIGH callbacks as generally
serialized; its published implementation uses a non-parallel HIGH group and a
parallel KERNEL group. A long active HIGH callback can therefore delay unrelated
work in that group even while normal threads can run. This supports testing
isolation of VBL delivery from that group; it does not establish runtime success.

The scheduling implementation changes only `src/phxaccel/accel/phxfb.cpp`:

- Create a dedicated `IOWorkLoop` and attach an `IOTimerEventSource` using
  `kIOTimerEventSourceOptionsPriorityKernel`, without `AllowReenter`. Apple's
  published implementation maps these options to the parallel KERNEL group
  and ONCE serialization. Absolute `wakeAtTime` deadlines preserve the existing
  staged timer arithmetic.
- Publish/read the stop flag atomically. `runAction` takes the same dedicated
  workloop gate as the timer action, waiting for any in-flight driver action
  before disabling, canceling and detaching its timer. This also cancels a
  successor rearmed by an action that passed the earlier stop check. Release
  the timer and workloop before removing AGDC state. Apple's wrapper retains
  timer/workloop references for an in-flight callout and checks its generation
  after acquiring the gate; the driver does not implement a separate drain
  flag or import private thread-call symbols.
- If workloop allocation, timer allocation or event-source attachment fails,
  release the partial resources and leave no armed VBL timer, preserving the
  existing allocation-failure behavior.

`src/phxaccel/Info.plist` is byte-identical to the accepted installation.
`com.apple.kpi.private` is not a usable dependency for this third-party kext;
the failed attempt described below is not part of the selected implementation.

The callback's staged deadlines, frame period, handler notifications, late-tick
accounting and missed-period behavior are unchanged. PhxBringup, native ABI,
phxctl, A1/A2/corrected-A3 logic, IB correction, plugin source, PR28's 250 ms
budget and WindowServer exclusion are preserved. No runtime knob, installed
binary, admission policy, EFI file or OS security setting is modified.

The API review used the audited MacKernelSDK at
`3f750085caa17ec3a7880f11c11bf4f48cd6a164`, the matching local
`KDK_26.7.2_25G332.kdk`, and Apple's published XNU. The timer wrapper reference
is `apple-oss-distributions/xnu` commit
`f6217f891ac0bb64f3d375211650a4c1ff8ca1ea`,
`iokit/Kernel/IOTimerEventSource.cpp`, SHA256
`97ddf1e91351f4e034250412c81e8e6541c95a64435ef28a2529c316492b1141`.
These are API/source references, not a claim that public XNU is byte-identical
to the running kernel. No Apple implementation code was copied.

## NullMoth comparison requested by the owner

The review on 2026-11-18 pinned `nullmoth/nvidia-macos-driver` main at
`87e524ab36f12d17c04626d6cf7fc3bde1cc63e4` (commit date
2026-11-14 UTC). The two framebuffer implementations have different designs:

- `kexts/NMIntelFB/intelfb.cpp` uses a plain thread-call VBL timer and explicitly
  notes that cancel/wait is not exported to kexts. Its teardown cancels and
  retries freeing the callout. Its separate virtual-panel sampling timer uses
  an IOKit event source; that sampler is not its VBL implementation.
- `kexts/NVRMFB/fb/nvrm-fb.cpp` allocates callbacks in HIGH with ONCE. Its source
  records a callback reentry/thread-exhaustion failure and serializes scheduling
  against stop while retaining each scheduled owner reference. Stop cancels
  and retries freeing callbacks before releasing their related state. This
  reinforces the need for nonreentry, lifecycle safety and late-rearm cleanup.
- NVRMFB also attempts real vblank through NVIDIA's NVKMS callback interface,
  retaining a synthetic-timer fallback. That NVIDIA interface cannot be moved
  directly to Radeon 780M. The reviewed HIGH-group timers likewise do not
  isolate this machine's suspected HIGH-group contention.

The current public IOKit design retains these safety requirements while using
the Apple timer wrapper and a dedicated gate. The reference review required no
further production-code change. No claim is made that NullMoth already fixes
this machine's pauses or that the synthetic timer measures physical scanout.

The reviewed repository root LICENSE is PolyForm Noncommercial 1.0.0;
NVRMFB also carries that SPDX identifier. Existing PhxAccel terms and NullMoth's
required copyright notice are preserved. No additional implementation or
binary was imported. The pinned file hashes are in the new preparation record;
source snapshots and raw responses remain private.

## Validation and remaining work

`make test-build34-vbl-scheduling` extracts the selected callback, allocation,
retirement and stop sequence into a CPU-only harness. Its **60 assertions**
cover a modeled busy HIGH group, ONCE reentry refusal, staged and unstaged
delivery, late notification without a catch-up burst, stopped callbacks and
all three allocation/attachment failures. A real host thread is held inside
the modeled gate while another invokes stop; stop must wait, then cancel the
first action's late self-rearm before release. This tests the extracted driver
sequence with modeled IOKit, not the XNU timer implementation or a physical GPU.
The source check also rejects a direct cancel/wait call or private-KPI
dependency.

The selected implementation also passed 43 panel-timing cases, 511 extracted
refresh/timing assertions and 3,646 extracted framebuffer assertions. ASan and
UBSan reported no failures in the extracted-method harnesses. Earlier
alias/pool, PCI matching and baseline unit checks passed as recorded in the
original validation; optional firmware fixtures were absent and no download
was triggered.

The native PhxAccel build recipe passed using the pinned, clean SDK in private
staging. Signature and x86_64 architecture checks passed. A real offline AuxKC
build using the matching KDK passed without approval or missing-KDK overrides;
independent readback verified that the exact candidate image is present.
All **416 combined cached records**, including 29 codeless entries, remain;
only PhxAccel's image UUID changed and all 415 unrelated records match. Staged
third-party companion bundles were separately byte-checked against the live
ones, so temporary path differences do not hide content changes.

The new sanitized result is
[`validation/build34-vbl-install-preparation-20261118.json`](validation/build34-vbl-install-preparation-20261118.json).
The historical **44-assertion direct-thread-call** record is retained unchanged:
[`validation/build34-vbl-scheduling-20261118.json`](validation/build34-vbl-scheduling-20261118.json).
Its initial native/static success did not establish target linkability; it is
superseded as an install candidate. No kext was installed, loaded or uploaded.
Raw stacks, identifiers, process listings and diagnostic source/output stay
in private storage.

Private exact-hash candidate/recovery preparation is complete against the
accepted runtime source `1d4968fbc2ce988c77bdd85b2ec36f435b57f496`.
This is not an activated installation scope. After the original-ACPI restart
baseline passes, complete the candidate-specific installation/admission
contract under the existing owner authorization; do not edit or replay the
frozen historical packet or weaken its checks to admit a new binary.
Separate the scheduling treatment from the withdrawn S5 experiment.
Compare the same foreground-policy GUI/worker observations before and after,
then validate real GPU execution and desktop correctness under the unchanged
admission gates. Long-duration stability, interactive input latency and FPS
remain unaccepted.

Rollback currently requires no action: the candidate is not installed. The
running accepted kernel/plugin, enabled acceleration, daily PR28 wait and
disabled resident-monitor policy remain the baseline. A future installation
must retain the exact accepted binary/recovery manifests and return to those
hashes on failure; do not replay a consumed historical trial.

## Owner-authorized installation preparation

The owner subsequently requested installation and validation. The existing
read-only owner startup-integrity check passed against the accepted runtime.
Private recovery copies retain its exact PhxAccel bundle, AuxKC and owner
startup-policy/job bytes; the frozen earlier installation packet is unchanged.
No live accelerator, kernel collection, EFI file or startup policy was written.

The offline preparation preserved each failed attempt rather than treating a
successful native compile or command exit status as installation readiness:

1. A broad cache build encountered an unselected Apple component's unavailable
   dependency. Subsequent builds explicitly selected the same four components
   as the accepted AuxKC and the x86_64 architecture.
2. The initial direct-thread-call candidate failed to bind
   `_thread_call_cancel_wait`. The matching KDK exposes it only through the
   private KPI; SDK declarations and monolithic-kernel symbols are insufficient.
3. Adding that provider made `kmutil create` return zero, but complete cache
   inspection found PhxAccel missing. The bounded system log explicitly
   reported the Apple-only private-KPI restriction. That candidate/cache is
   rejected; the dependency addition was fully withdrawn.
4. The selected public IOKit timer implementation passed the actual offline
   build, candidate-inclusion and complete-record/recovery readback described
   above. The Info.plist remains unchanged. No Apple bundle spoof, security
   change or approval bypass was used.

Accepted PhxAccel/AuxKC, Boot/System collections, owner policy/job files,
daily wait configuration and their exact recovery copies were independently
rechecked. The loaded accelerator is still the accepted original image and
the candidate is not loaded. Failed intermediate caches remain private and
must not be selected for installation.

At that preparation stage, the machine was still in the failed ACPI candidate's
16:39 boot on 2026-11-18. Its exact original EFI rollback was on disk, but loaded tables had not yet
changed. **First perform the owner's ordinary restart and independently
verify original ACPI and the accepted accelerated runtime.** Installing a VBL
treatment before that baseline would combine ACPI removal and scheduling
changes in one boot. This prerequisite was retained; no power action or
next-boot candidate activation was scheduled. Subsequent installation must
retain the exact recovery images and all existing GPU/desktop admission
checks, including the disabled resident-monitor policy. Source/CPU/cache
validation alone does not establish a hardware repair, stability or FPS.

## Subsequent agent-reboot authorization

The owner subsequently authorized the agent to perform the ordinary restart
for the pending original-ACPI baseline. This changes who may request that
restart; it does not remove the baseline prerequisite or combine it with a
VBL installation.

Preflight rechecked original-ACPI EFI and recovery, accepted build34 kernel,
plugin and AuxKC, exact accepted accelerator/cache recovery copies, current
startup/admission receipts and the unchanged daily PR28 configuration. The
withdrawn SSDT is still present in the current boot's dynamic ACPI property;
the already restored disk configuration will take effect at the next boot.

A private read-only next-boot observer passed nine CPU tests, including stale
receipt, withdrawn-table, altered-table and monitor-policy refusal. Its job
was staged on disk without bootstrap/kickstart in the current boot. It waits
for the existing startup/admission tasks to finish, independently verifies
original loaded DSDT/FADT, absence of the withdrawn SSDT, full EFI/recovery,
accepted runtime and brief passive desktop/VBL progress. Its worker has a
420-second limit, it never retries, and it removes its own job file after its
run. It does not install the VBL candidate, launch a GPU test, alter existing
startup policy or enable a resident monitor.

The [preparation record](validation/build34-original-acpi-reboot-preparation-20261118.json)
records staging only. A reboot request and post-reboot verification must be
observed separately; neither original-ACPI baseline success nor a VBL repair
is claimed by this preparation. Private receipts survive a disconnected
agent session so the subsequent result can be independently read before any
candidate treatment.

## Original-ACPI restart baseline passed

The owner-authorized ordinary restart completed on 2026-11-18. The next-boot
observer passed, and a separate read-only check independently reparsed its
current-boot receipts and rechecked the machine. Both verified exact original
loaded DSDT/FACP with valid checksums, absence of the withdrawn SSDT, full
original EFI/recovery identity, the accepted build34 kernel/plugin/accelerator
and current-boot bounded accelerated desktop admission. The same compositor
survived the passive check; synthetic VBL advanced without increases in copy
failures, skipped copies, surface GPU timeouts or hang kills.

Startup supervision ended, the observer removed its own job, and no resident
monitor was enabled. Daily PR28 waiting remains configured. These read-only
checks submitted no additional GPU workload. The new boot satisfies the ACPI
prerequisite; it does not establish VBL treatment success, physical scanout FPS
or long-term stability. The VBL candidate was not installed by this check.

The sanitized result is
[`validation/build34-original-acpi-reboot-20261118.json`](validation/build34-original-acpi-reboot-20261118.json).
The earlier preparation record remains unchanged. Do not replay the consumed
observer or historical GPU trial.

## Current-ACPI control and candidate installation

The same Launch-Services-launched GUI/worker diagnostic was rebuilt from its
exact preserved source and run on this original-ACPI boot before changing the
accelerator. The first diagnostic ended normally, but its supervisor raced a
process exit while querying process state; that incomplete run is retained and
excluded. The corrected supervisor accepted a fresh bounded run:

| Original-ACPI control | Result |
| --- | ---: |
| Elapsed time | 16.009806 s |
| GUI timer intervals over 100 ms | 22 |
| GUI timer p99 / maximum | 308.118 / 528.692 ms |
| Independent worker maximum interval | 16.179 ms |
| Sampled VBL plateaus over 80 ms | 22 |
| Longest sampled VBL plateau | 528.282 ms |
| Large GUI gaps overlapping sampled VBL plateaus | 22 of 22 |
| Window visibility checks passed | 9 of 9 |
| Copy failure / skip / GPU timeout / hang-kill increases | 0 / 0 / 0 / 0 |

The recurring GUI/VBL symptom remains after removing the failed ACPI candidate.
This is a current control observation, not proof of the contention hypothesis.

A new private activation scope preserves the frozen historical packet and the
owner's existing policy files. Its only protected-image substitutions are the
exact selected PhxAccel executable and AuxKC hashes; the kernel, plugin, daily
PR28 configuration and EFI remain unchanged. A derived contract also pins the
new loaded accelerator identity. The existing startup implementation changes
only its journal location, with all 45/150/300-second admission limits and the
initial 90-second shell observation retained. No resident monitor is enabled.

All 26 scope/refusal/filesystem recovery tests, 25 actual startup-policy tests,
and nine observer tests passed. An inactive same-directory atomic replacement
also preserved the live cache's permission and protection-flag convention.
Installation replaced the two exact image files and two startup job entrypoints;
independent readback passed signature, 416 combined cache records, unchanged
415 unrelated records, candidate disk hashes, original EFI/recovery and exact
accepted recovery copies. The accepted accelerator remains loaded in this boot;
the candidate has not yet been loaded or hardware-accepted.

Both next-boot observation jobs are one-shot, finite and staged without starting
them in the current boot. A second nine-test gate requires successful
current-boot candidate admission before the ordinary GUI/worker comparison.
It performs no explicit GPU submission, power action, policy change or retry,
and removes its own job. Its overall limit is 520 seconds; the GUI subprocess
limit is 55 seconds. Startup failure recovery restores the exact accepted
accelerator/cache and original owner job bytes before at most one recovery
restart; it does not modify EFI, security settings or the frozen contract.
After successful startup there is no resident periodic rollback controller.

The new installation record is
[`validation/build34-vbl-installation-20261118.json`](validation/build34-vbl-installation-20261118.json).
The owner's reboot-test authorization covers the next ordinary restart.
Candidate loading, the post-boot GUI result, real workload correctness, physical
scanout FPS and long-term stability remain unaccepted at this installation stage.

## First activation failed; accepted baseline restored

The first authorized candidate restart failed before the wrapper created its
current-boot startup journal. Its guarded recovery restored the exact accepted
PhxAccel executable, AuxKC and both original startup-job files without errors,
then performed its single recovery restart. Independent readback of the
recovery boot verified the accepted loaded image, successful bounded
accelerated startup, original loaded ACPI and full EFI/recovery identity.
The same WindowServer survived the passive check, VBL advanced, and no matching
diagnostic report or copy/skip/timeout/hang counter increase appeared. PR28
daily waiting remains enabled and resident monitoring remains disabled.
The unexecuted GUI job was retired without replaying the diagnostic.

The first wrapper failed to persist its original exception before requesting
recovery. A later read-only reproduction with modeled candidate identities
passed, but does not establish what happened in that boot. Targeted historical
logs show the intended auxiliary collection was selected; they do not prove
successful accelerator loading or identify the failing startup step. Neither
a driver defect nor a controller-only cause is established. The original
installation-stage record is retained unchanged as chronology.

A new scope keeps the exact same candidate binary/cache and unchanged
admission deadlines. It records the wrapper phase, original exception and
traceback, then five bounded read-only state snapshots before recovery. Private
startup stdout/stderr paths preserve early failures. A consumed GUI job on a
recovery boot now removes only its exact job bytes without starting the GUI.
All 69 prior scope/startup/observer/admission tests and five added evidence
tests pass. The inactive same-directory atomic replacement again preserved
permissions and cache protection flags; the live cache stayed unchanged.

A fresh accepted-image control in the recovery boot reproduced the symptom:

| Recovery-boot original-image control | Result |
| --- | ---: |
| Elapsed time | 17.163928 s |
| GUI timer intervals over 100 ms | 18 |
| GUI timer p99 / maximum | 315.333 / 539.601 ms |
| Independent worker maximum interval | 15.177 ms |
| Sampled VBL plateaus over 80 ms | 20 |
| Longest sampled VBL plateau | 522.394 ms |
| Large GUI gaps overlapping sampled VBL plateaus | 18 of 18 |
| Window visibility checks passed | 9 of 9 |
| Copy failure / skip / GPU timeout / hang-kill increases | 0 / 0 / 0 / 0 |

At this preparation readback the accepted accelerator/cache and owner jobs
remain installed; the second candidate is not installed and no new reboot is
scheduled. Installation and its independent readback must precede a separately
recorded authorized test restart. No hardware repair, workload correctness,
physical FPS or long-term stability acceptance is claimed. See the sanitized
[failure/recovery record](validation/build34-vbl-first-activation-recovery-20261118.json).

## Second exact-image installation

The second scope subsequently passed its actual preflight and installation.
A separate readback rechecked exact installed and recovery hashes, public
signature, all 416 combined cache records with the same 415 unrelated records,
original loaded ACPI and full EFI/recovery identity. The still-running image
is the accepted original accelerator; this installation did not load the
candidate or submit a new GPU workload. Acceleration, desktop takeover, daily
PR28 waiting and the disabled resident-monitor policy remain intact.

The new one-shot observer and post-admission GUI jobs are staged without
bootstrap in the current boot. They require successful current-boot candidate
loading, bounded accelerated startup and observer acceptance before the finite
GUI comparison. An original exception is now recorded before recovery; the
same exact accepted-image recovery and unchanged admission deadlines apply.
This is a separate consumed-once scope, not a replay of the failed activation.

At the independent installation readback no reboot had yet been requested.
The existing owner authorization covers its test restart. Candidate hardware
repair, GPU workload correctness, physical scanout FPS and long-term stability
remain unaccepted. See the new
[second-installation record](validation/build34-vbl-second-installation-20261118.json).

## Second failure isolated a cache-packaging regression

The second restart recorded the original exception before recovery. The
wrapper failed its exact PhxAccel loaded-image assertion, before a startup
journal or GPU/GUI test was created. Its five bounded snapshots showed
PhxBringup loaded, no loaded PhxAccel record, no published PhxAMDFB and absent
accelerator sysctls. This establishes the failing admission step; it does not
establish that the VBL callback ran or that its implementation caused a crash.

Exact executable/cache/job restoration completed without errors, followed by
one recovery restart. An independent readback verified the accepted image,
current-boot bounded accelerated startup, original loaded ACPI and full
EFI/recovery identity. VBL advanced with the same WindowServer, no matching
report or error-counter increase appeared, and both failed-trial observation
jobs were retired. The GUI was not replayed. Resident monitoring remains
disabled, daily PR28 waiting remains enabled, and no additional restart was
scheduled by that recovery readback.

Complete prelink comparison found a real difference missed by the earlier
416-record/image-UUID check: the private-repository cache added
`OSBundleRequireExplicitLoad=true` and private staging bundle paths to
PhxAccel and two companion components. Their accepted metadata had no such
explicit-load field and used the standard installed paths. Source Info.plist
bytes and personalities were unchanged. The package therefore failed to
preserve boot-matching policy despite containing the intended executable.
This is a supported explanation for the missing automatic load, pending a
new boot with corrected packaging; it is not a proved VBL-code defect.

Three further offline results were rejected: two synthetic target directories
failed matching-KDK discovery, and a filtered private-repository build returned
zero but omitted three expected records while retaining the explicit-load
marker. None was installed. No missing-KDK or authorization override was used.

An accepted-image control built from the standard installed paths passed a
full metadata comparison with the original 416 records, including 29 codeless
entries. A separate finite operation then temporarily published the already
authorized candidate executable at that same standard path, generated only
a private output cache, and restored the accepted executable in `finally`.
A separate bounded exact-file guard covered interruption; it exited after
restoration without any power action. The live cache and startup jobs stayed
unchanged, and no new driver was loaded or explicit GPU workload submitted.

The resulting private candidate cache contains the same exact accelerator
binary as the two failed trials. Its complete metadata comparison passed:
only PhxAccel's image identity/size and permitted relocation addresses differ;
bundle paths, explicit-load presence/value, personalities, dependencies,
Info.plist digests and boot/system links match the accepted baseline. All
415 unrelated images remain unchanged. No production VBL source or admission
deadline was changed to obtain this result.

`tools/check_build34_cache_metadata.py` now provides that read-only gate for
complete three-collection `kmutil inspect --show-prelink-info` captures. It
requires 416 unique records and 29 codeless records, rejects missing/extra or
moved bundles, preserves all policy fields and accepts only the explicitly
named image change plus relocation fields. It prints no raw identifiers or
metadata. Its 25 CPU regression tests pass, the actual rejected cache is
refused, and both the actual accepted-image control and corrected candidate
pass. The existing 60 production VBL assertions also pass. Run:

```sh
make test-build34-cache-metadata test-build34-vbl-scheduling
python3 -B tools/check_build34_cache_metadata.py BASELINE_CAPTURE CANDIDATE_CAPTURE \
  --allow-image-change com.luuumi.PhxAccel
```

Captures and raw loading logs remain private. A subsequent installation must
use a new scope, pin this exact corrected cache, run both UUID and complete
metadata checks against the actual selected cache, and preserve the accepted
recovery copies and unchanged startup gates. It must not retry either consumed
activation scope. The corrected cache is offline-only at this record; real
loading, stutter repair, workload correctness, physical FPS and long-term
stability remain unaccepted. See the sanitized
[failure and metadata-repair record](validation/build34-vbl-cache-metadata-20261118.json).

## Corrected-cache installation under a fresh scope

A third private scope pins the exact corrected cache and the unchanged
candidate accelerator binary. It preserves both consumed activation scopes,
the frozen historical packet, accepted recovery copies, original owner policy
files and all existing startup deadlines. Its preflight and install paths now
check the actual selected cache's full prelink metadata as well as its image
identities. This adds a refusal condition; it does not replace or bypass the
exact loaded-image startup gate with an explicit driver load.

All 99 scoped CPU tests passed: the 74 scope/startup/observer/failure-evidence
checks plus 25 complete-cache metadata cases. An inactive same-directory
atomic transition preserved the existing cache permission/flag convention.
Before installation a fresh Launch Services control in the recovered boot
again recorded 23 GUI intervals over 100 ms, all overlapping sampled VBL
plateaus; GUI p99/maximum were 312.362/532.714 ms, while the independent worker
maximum was 15.016 ms. The same WindowServer survived, all nine onscreen checks
passed, and no copy/skip/timeout/hang counter increased. This remains a sampled
GUI/VBL observation, not physical scanout FPS or a root-cause proof.

Actual installation and separate independent readback passed. The disk
candidate/cache and exact accepted recovery hashes match, all 416 combined
records and their full policy metadata pass, and all 415 unrelated images are
preserved. Original loaded ACPI/full EFI recovery and the active accepted
accelerator identity were rechecked. The candidate is still not loaded in this
boot. Two finite next-boot jobs are staged without bootstrap; the GUI comparison
requires successful exact candidate admission and observer acceptance first.

At that installation readback no new reboot had been requested. The existing
owner authorization covers the test restart. Daily PR28 waiting remains on,
resident monitoring remains off, and startup failure retains exact accepted
recovery with at most one recovery restart. Actual candidate loading, stutter
repair, workload correctness, physical FPS and long-term stability await new
evidence. See the
[corrected-cache installation record](validation/build34-vbl-metadata-installation-20261118.json).

## Corrected-cache boot and bounded GUI comparison passed

The authorized third restart entered a new boot at 21:32:27 +0800 on
2026-11-18, running macOS 26.7.2 build 25G332. The unchanged candidate
accelerator loaded automatically from the corrected cache. Exact loaded-image
admission, the existing bounded accelerated startup and the finite read-only
observer all passed. The GUI comparison ran only after those gates completed.
Neither failed activation scope was replayed, and no recovery was triggered.

The same Launch Services diagnostic and preserved application source were used
for the accepted-image control immediately before installation and the
candidate after restart:

| Observation | Accepted-image control | VBL candidate |
| --- | ---: | ---: |
| Elapsed time | 16.450 s | 16.939 s |
| GUI timer intervals | 562 | 938 |
| GUI median / p95 | 16.681 / 41.681 ms | 16.659 / 17.309 ms |
| GUI p99 / maximum | 312.362 / 532.714 ms | 17.599 / 26.169 ms |
| GUI intervals over 33.34 / 100 ms | 30 / 23 | 0 / 0 |
| Independent worker maximum | 15.016 ms | 12.578 ms |
| Sampled VBL plateaus over 80 ms | 24 | 0 |
| Large GUI gaps overlapping VBL plateaus | 23 | 0 |
| Onscreen checks passed | 9 of 9 | 15 of 15 |
| Copy failure / skip / GPU timeout / hang-kill increases | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 |

WindowServer remained the same within each run. These are separate boots, not
a same-boot reversal, and the comparison contains one selected control and one
candidate run. It supports the scheduling treatment for the reproduced
GUI/VBL symptom, but does not prove a particular AppleACPIEC callback caused
the original delays. GUI timer intervals, draw callbacks, compositor presents
and synthetic VBL counters must not be reported as physical FPS or direct
mouse-input latency. The GUI diagnostic submitted no explicit native/Metal
test workload; it used the existing accelerated desktop compositor.

A separate read-only post-boot verification reparsed all current-boot startup,
observer and GUI receipts, independently checked the actual loaded candidate,
disk/cache/job hashes and exact accepted recovery copies, and repeated both
the 416-record image check and full three-collection metadata comparison.
The 25 metadata regression tests and 60 production VBL CPU assertions passed
again; these CPU checks do not add hardware coverage.
All 29 codeless records, 415 unrelated images, matching policies, standard
paths, dependencies and collection links remain preserved. Original loaded
DSDT/FACP, absence of the withdrawn SSDT and full original EFI/recovery
identity passed again. No EFI or security setting changed.

During an additional passive five-second readback, the same compositor
survived, VBL advanced, and copy failures, skips, surface GPU timeouts and hang
kills remained zero. No new matching diagnostic report appeared. Startup
supervision ended, both one-shot observer/GUI job files were removed, and no
resident installation/hang monitor or pending reboot remained. Daily PR28
waiting remains enabled with its unchanged 250 ms budget and WindowServer
exclusion. The verification submitted no GPU work or power action.

The successful candidate stays active; no post-startup automatic rollback was
enabled. Exact accepted-image recovery remains available for the unchanged
bounded startup-failure path. The owner-selected accepted source checkpoint
remains `1d4968fbc2ce988c77bdd85b2ec36f435b57f496`; this is a minimal default-build34
treatment from that baseline, not build41/build42 or a new baseline selection.
Long-duration stability, physical scanout FPS, interactive pointer latency,
sleep/wake and a separate fresh explicit GPU-workload comparison remain
unaccepted. See the sanitized
[post-boot result](validation/build34-vbl-corrected-cache-boot-20261118.json).
Earlier installation and failed-trial records remain unchanged.

## Delayed same-boot GUI stutter remains

To check the owner's original initially-smooth-then-sluggish symptom, a new
finite observation scope ran in the same candidate boot after 880.444 seconds
of uptime at validation entry. It reused the exact immutable diagnostic
executable and Launch Services method, with new output paths and no replay of
startup, observer, historical GPU or earlier GUI jobs. Before the observation,
exact candidate identity, installed-state checks, original EFI/recovery and
the successful current-boot receipts passed again. No driver, configuration,
power state or resident-monitor setting was changed.

| Delayed candidate observation | Result |
| --- | ---: |
| Elapsed time | 16.336 s |
| GUI timer intervals | 708 |
| GUI median / p95 | 16.673 / 18.199 ms |
| GUI p99 / maximum | 304.781 / 309.691 ms |
| GUI intervals over 33.34 / 100 ms | 23 / 15 |
| Independent worker maximum | 15.050 ms |
| Independent worker intervals over 33.34 ms | 0 |
| Sampled VBL plateaus over 80 ms | 0 |
| Onscreen checks passed | 11 of 11 |
| Copy failure / skip / GPU timeout / hang-kill increases | 0 / 0 / 0 / 0 |

WindowServer remained the same, the diagnostic had normal GUI scheduling,
and no new matching report appeared. The private observation receipt's
`status=passed` means collection and its integrity/counter checks completed;
it does **not** mean the latency result passed. This later result prevents
promoting the initial smooth run to a general stutter repair.

The synthetic VBL counter continued progressing during this observation while
the GUI main loop paused. The scheduling candidate therefore has not removed
all of the owner's symptom, and the residual delays cannot be attributed to
the previous sampled VBL plateaus. A subsequent passive memory readback showed
76% available by `memory_pressure -Q`, no compressed pages and no pageouts or
swap traffic; that readback is not a continuous memory-pressure trace or proof
of another cause. A first new short stack-sampling scope timed out before
producing a usable call graph. Its evidence is retained and is not a driver
failure or a successful stack diagnosis. Further diagnosis must keep fresh
finite scopes, separate sampling overhead from performance comparisons and
preserve the current acceleration, daily PR28 wait and monitor-off policy.

A second fresh sampling attempt returned zero only after the diagnostic had
exited and produced an empty call graph; that is also rejected as usable stack
evidence. A third fresh attempt explicitly required a nonempty graph and
obtained one, but its GUI run contained no intervals over 100 ms. It sampled a
responsive period, so its ordinary run-loop and initialization stacks do not
identify the residual stall. Neither an empty report nor an instrumented
smooth run clears the reproduced delayed-stutter result.
The usable graph also showed AppKit's window/context initialization reaching
`MTLCopyAllDevices` and `NVMTLDevice` initialization. The source's CPU-drawn
view and lack of explicit Metal test commands therefore do not establish an
absence of framework-internal Metal discovery or work. No PR28 wait call was
identified as the residual cause by this nonstalling sample.

A fresh trigger-based diagnostic then retained the same drawing/worker logic
but extended its nominal lifetime to 45 seconds. A worker emitted a one-time
signal when the main timer was more than 80 ms late, triggering two-second
application and WindowServer samples. An initial attempt was refused before
GUI launch because the newly created shared directory was not traversable by
the console user. It is preserved; a new scope with verified console access,
signature and identical diagnostic code ran successfully.

The trigger fired at 8.828 seconds with an observed 89.717 ms main-loop gap.
The run lasted 47.705 seconds and recorded 60 GUI intervals over 100 ms, a
311.400 ms p99 and a 538.836 ms maximum. Sampled VBL plateaus over 80 ms stayed
at zero; all 31 visibility checks passed, the same WindowServer survived and
the four error-counter increases remained zero. The independent worker's
maximum interval was 56.757 ms with three intervals over 33.34 ms, so this
instrumented run is not interchangeable with the uninstrumented comparison.

Both triggered samples had nonempty call graphs. The application's main
thread was in its ordinary run-loop Mach-message wait in 31 of 33 recorded
stack samples. WindowServer's main thread was in message wait in 30 of 44,
with other samples in display composition, surface transfer and retirement.
These aggregate samples were collected after the trigger, rather than being
an exact per-gap trace. They did not identify a PR28 wait or prove a specific
driver call, EC callback or lock as the residual cause.

## CPU-only timer-delivery investigation

A separate original diagnostic uses the userspace `mk_timer` ABI to request
10 ms critical, zero-leeway timer messages while another thread waits
directly with `mach_wait_until` at approximately 10 ms intervals. Both paths
run in one process and sample the existing read-only VBL counter. This tool
links only the system C runtime; it creates no IOKit client or explicit GPU
work. Its native build used warnings as errors and a symbol-presence-only
preflight before timer creation. Every completed run destroyed its timer port.

The first root-CLI run inherited background task policy. Its direct-wait
control also suffered long delays, so it is excluded from normal-application
timer-delivery evidence. The next scope used the same source and identical
executable text in a signed application bundle launched through Launch
Services. Process readback showed nice 0 and priority 37. It changed only the
launch route; no driver, wait budget, framebuffer control or owner policy was
changed, and the first scope was not replayed.

| Normal-application CPU timer observation | Result |
| --- | ---: |
| Elapsed time | 20.057 s |
| Requested Mach timer period / explicit leeway | 10 / 0 ms |
| Mach timer messages / API errors | 1,149 / 0 |
| Mach timer lateness median / p99 / maximum | 0.023 / 291.284 / 521.591 ms |
| Mach timer deliveries over 80 ms late | 31 |
| Direct-wait worker intervals | 1,804 |
| Direct-wait interval median / p99 / maximum | 10.689 / 14.725 / 14.995 ms |
| Direct-wait intervals over 80 ms | 0 |
| Sampled VBL plateaus over 80 ms | 0 |

This reproduces a timer-message delivery delay in an independent program
without an explicit GPU workload while a same-process direct-wait control
remains responsive. It narrows the investigation beyond the original VBL
timer; it does not prove all interactive stutter shares one cause.

Apple's public XNU at `f6217f891ac0bb64f3d375211650a4c1ff8ca1ea`
initializes the Mach timer's callout with `thread_call_setup`; that helper
assigns `THREAD_CALL_PRIORITY_HIGH`. A critical timer's zero-leeway arm does
not change that group. This makes shared HIGH-callout contention a supported
hypothesis for the observation, not proof of the running kernel's exact
implementation or of which callback blocked a particular expiry. The three
official source files were actually downloaded and checked before this CPU
run; source snapshots remain private, no implementation was copied, and their
APSL-2.0 reference terms do not replace any project component's licence.

| Pinned Apple source path | SHA256 |
| --- | --- |
| `osfmk/mach/mk_timer.h` | `f261b01daccc068d710ca87699545d0525f50bd32b80b5302bd9a14e0bf23f7d` |
| `osfmk/kern/mk_timer.c` | `aa73f8976c8be7e2dbb89bedee9de7d245eb67fa5f29de3b05ee7c3083ea22ff` |
| `osfmk/kern/thread_call.c` | `c14d9956890389097874811695ce90d436da9a39957124be4a79b4d6a426c876` |

The attempted kernel-only captures did not resolve a `kernel_task` target and
produced no usable kernel call graph. They do not establish permission denial,
absence of kernel contention or a new EC diagnosis. No security setting was
changed to obtain a capture. In particular, the earlier AppleACPIEC contention
hypothesis remains unproved by these new samples.

Final independent readback again passed exact loaded candidate/disk/cache/job
identity, all 416 records and full metadata, accepted recovery, original loaded
ACPI/full EFI recovery, current-boot startup receipts and a passive five-second
desktop check. No matching report or error counter increased. The candidate
remains active with daily PR28 waiting on, startup supervision ended and
resident monitors off. This round adds diagnosis, not a second production
patch, kernel timer modification, ACPI repair or general-stutter acceptance.
See the sanitized
[CPU timer record](validation/build34-timer-delivery-20261118.json).

See the sanitized
[delayed observation](validation/build34-vbl-delayed-gui-20261118.json).

## Synchronized kernel and EC-query investigation

A later fresh, bounded CPU timer scope obtained a usable kernel call graph
by selecting the live diagnostic process and including PID zero as an
additional spindump process. This supersedes the earlier target-lookup limit;
no permission or security setting was changed. The Launch Services application
kept nice 0 / priority 37. The original timer algorithm was unchanged; the only
native diagnostic addition reports its existing absolute-clock start value
for private timestamp comparison.

The 20.016-second run recorded 29 Mach timer deliveries more than 80 ms late,
with a 298.258 ms p99 and 521.681 ms maximum. Its same-process direct-wait
worker maximum was 14.924 ms with no interval over 80 ms, and sampled VBL
plateaus over 80 ms stayed at zero. Timer APIs succeeded and the timer port
was destroyed. These are timer-delivery measurements, not physical FPS.

The kernel capture covered 3.204 seconds and contained 72 samples. One HIGH
thread contained AppleACPIEC in 52 samples; another contained it in seven
already overlapping sample indices, so their counts must not be added.
All five long timer windows overlapping the capture had explicit EC HIGH
leaf timestamps inside them; four windows were fully contained and one
extended past the captured interval. The association uses actual reported
leaf endpoints without inventing timestamps between samples.

The capture also reported approximately 210, 214 and 210 ms gaps with no
samples, and spindump emitted a processing-stuck warning before producing
the nonempty report and returning zero. The raw warning and additional
private capture are retained. This instrumented, incomplete timeline cannot
prove uninterrupted EC execution through a gap or assign every timer delay
to a particular callback.

The installed KDK matches the OS build. Private image-identifier comparison
matched the loaded stack images, selected BootKC images and KDK images for
the kernel, AppleACPIEC, AppleACPIPlatform and IOACPIFamily. KDK DWARF and
native symbol readback confirmed the following sampled path:

```text
thread_call_thread -> thread_call_invoke
  -> AppleACPIEC::handleQuery
  -> IOACPIPlatformDevice / AppleACPIPlatformExpert::evaluateObject
  -> AcpiEvaluateObject -> AcpiPsExecuteMethod -> AcpiDsExecEndOp
  -> AcpiExOpcode_1A_0T_0R -> AcpiExSystemDoSleep
```

Other sampled branches reached `AcpiExEnterInterpreter`,
`AcpiUtAcquireMutex` and `AcpiOsWaitSemaphore`. These observations identify
native EC-query AML execution and sleep/interpreter-wait paths. They do not
identify the actual `_Qxx` method, its sleep operand or the initiating EC
event. No Apple implementation, binary, KDK material or firmware-derived
code is copied into this repository.

A separate fresh 20.022-second timer/property observation happened to show
no long timer delay (1.435 ms maximum). Independent accessor validation then
proved that EC single-property reads can return a stale statistics dictionary:
full property serialization refreshed the command count, and a subsequent
single-property read returned the refreshed value. The earlier zero EC delta
is therefore excluded from activity and causal conclusions. The smooth timer
interval remains an intermittent observation, not a repair or evidence that
EC work was absent.

A new finite scope changed only the counter accessor to independently
validated full property serialization, preserving identical TimerProbe
executable text and normal Launch Services scheduling. It reproduced the
problem without kernel stack sampling:

| Corrected counter observation | Result |
| --- | ---: |
| Elapsed time | 20.229 s |
| Mach timer deliveries over 80 ms late | 27 |
| Timer lateness p99 / maximum | 288.252 / 516.392 ms |
| Direct-wait worker maximum / intervals over 80 ms | 14.976 ms / 0 |
| Sampled VBL plateaus over 80 ms | 0 |
| GPE / SCI counter increases | 60 / 60 |
| AML method / EC command counter increases | 958 / 30 |
| Registry property samples | 217 |
| Maximum property-read duration / observer poll interval | 9.920 / 275.105 ms |

All 27 long windows overlapped coarse observer intervals containing method
count increases; 12 overlapped intervals containing GPE count increases.
These intervals are not exact event timestamps. The last sampled GPE value
matches the EC declaration in the retained DSDT, whose binary was independently
matched to the currently loaded dynamic table. A last-GPE value does not
identify each event or the `_Qxx` query code, and unchanged retry/timeout
counters do not exclude lengthy AML. A separate bounded four-minute kernel
ACPI-log query returned no messages; this is not proof of inactivity.

Both the property observation and kernel capture are finite diagnostics, not
resident monitoring. All diagnostic applications and supervisors exited;
there was no new driver, policy, EFI, ACPI or power change and no explicit GPU
test submission. Final independent readback passed exact candidate/disk/cache/
job and accepted-recovery identities, full metadata for all 416 records and
29 codeless records with 415 unrelated images preserved, original loaded
ACPI/full EFI recovery, current-boot accelerated startup and ended supervision.
No matching report or error counter increased. Keep the running VBL candidate,
owner-selected baseline, daily PR28 waiting, 250 ms budget, WindowServer
exclusion and disabled resident monitors unchanged. The next missing causal
fact is the executing query method; these observations do not justify a
speculative EC disable, AML rewrite, timer-budget change or rollback.

See the sanitized
[kernel and ACPI timing record](validation/build34-timer-acpi-correlation-20261118.json).


## Executing EC query and power handshake identified

A subsequent fresh native trace identifies the actual EC-query names. The
original CPU timer application kept its exact executable text and normal
Launch Services scheduling. The finite diagnostic observes existing kernel
function entries; it does not request AML evaluation, submit GPU work or
change ACPI debug flags. The system's existing ktrace owner/configuration is
identical before and after the capture.

The exact current KDK/report images were matched privately. Generic system
symbol/sleep probes were restricted to the ACPI wrappers' actual callsites.
An initial address-based filter missed those callsites because its live
address origin was wrong; zero hits are not evidence of zero EC work. A short
broader control exposed that origin difference consistently in two modules,
but also reported 28 unaligned string-read errors. That control is retained
and excluded from quantitative attribution. A new scope uses byte reads and
the independently matched live callsites; it reports no probe errors or
buffer drops and pairs all 26 query entries with their post-evaluation exits.

| Corrected, instrumented observation | Result |
| --- | ---: |
| Native trace / CPU timer elapsed | 24 / 20.328 s |
| Complete `_Q48` / `_Q47` calls | 13 / 13 |
| `_Q48` outer-call duration minimum / maximum | 473.805 / 1,318.067 ms |
| `_Q48` sleep requests / operand | 407 / 10 ms |
| Sleep requests per complete `_Q48` call | 21–35 |
| `_Q47` observed direct AML sleep requests | 0 |
| Mach timer deliveries / deliveries over 80 ms late | 1,155 / 27 |
| Timer lateness p99 / maximum | 271.008 / 478.853 ms |
| Direct-wait maximum / intervals over 80 ms | 15.861 ms / 0 |
| Sampled VBL plateaus over 80 ms | 0 |
| Long timer windows overlapping `_Q48` | 27 of 27 |
| Windows contained in one `_Q48`, before clock uncertainty | 14 of 27 |

DTrace's raw clock origin was not assumed equal to the application's Mach
clock. Wall timestamps were aligned with tight before/after wall-to-Mach
brackets; their offset differed by 0.048 ms. Clipped `_Q48` interval unions
cover at least 99.928% of each long timer window, with a median of 100%.
Overlapping queries and different threads are not added twice. This is
specific temporal association, not a controlled causal intervention or proof
that all GUI pauses share one cause. Method duration includes sleeping and
other waits; it does not mean continuous CPU execution. A paired outer exit
also does not establish the AML return status.

The matching KDK shows `IOSleep` tail-jumping into `delay_for_interval`.
Earlier generic return-probe records are therefore not used as actual wake
or sleep-duration measurements. The durations above instead bracket the
outer ACPI evaluation wrapper using its symbol creation and post-evaluation
release callsites.

Private offline disassembly found `_Q47` and `_Q48` in a previously
undisassembled SSDT. Its saved binary was independently byte-matched to one
currently loaded dynamic table. `_Q48` conditionally updates power-limit
fields and calls `VPC0.NEUP` up to twice. That helper writes a firmware
handshake field in a `SystemMemory` operation region, then polls up to 25
times with a 10 ms sleep per poll. Its nominal requested-sleep budget is
250 ms per invocation, or 500 ms for two; these are not hard execution
limits. Runtime firmware acknowledgment values were not read, so the trace
does not establish whether a particular poll completed or exhausted its
counter. Ordinary EC command/timeout counters cannot describe each of these
memory-region accesses.

The offline tool was obtained from a pinned MaciASL repository blob after
separate review of the application's GPL-3.0 notice and the ACPICA component's
own alternative notices. Its build recipe names ACPICA `R09_25_20`, and the
binary reports version `20200925`; Git blob verification is not a claim of a
reproduced source build. All tool bytes, notices, raw tables, disassembly,
addresses and reports remain private. No third-party implementation or
firmware excerpt is added to this repository.

This narrows the residual investigation to a real power-update/polling path.
Do not disable `_Q48`, shorten its polling, force acknowledgment, change OS
identity or bypass the power-limit writes merely to remove the observed
wait. Next review the firmware acknowledgment contract and native callback
scheduling while preserving those semantics. PR28's unrelated 250 ms budget
is not changed by this result.

Final independent readback passed the exact active candidate/cache and
accepted recovery, full metadata for 416 records/29 codeless records with
415 unrelated images preserved, original loaded ACPI/full EFI recovery and
current-boot accelerated startup. The same WindowServer survived; no error
counter or matching report increased. All finite applications, tracers and
supervisors exited. Keep daily PR28 waiting and desktop acceleration active,
the owner-selected baseline unchanged and resident monitors disabled. There
is no new production patch, restart, physical-FPS result or general-stutter
repair acceptance. See the sanitized
[query-identification record](validation/build34-ec-query-identification-20261118.json).


## Native sleep compensation and runnable AML work

Two further fresh finite observations crossed midnight on November 18–19,
2026, in the same candidate boot. They add scheduler evidence, not a new
latency/FPS benchmark or a production repair. No diagnostic application or
explicit GPU workload was launched. Each native trace requested 12 seconds,
exited normally under an independent timeout, and reported zero probe errors,
zero drops and empty stderr.

Private review of the matching KDK resolves an important limitation of the
HIGH-group hypothesis. AppleACPIEC allocates its query callback through the
default `thread_call_allocate`; the reviewed start path does not expose a
priority configuration branch. However, the native scheduler callback also
contains blocked-worker compensation: a BLOCK transition reduces the group's
active count, and pending work can wake another worker. UNBLOCK restores that
count. The previously downloaded pinned Apple XNU `thread_call.c` snapshot was
hash-verified again and describes the same accounting. Further source-download
attempts were incomplete; this is not a claim to have reviewed a newer Apple
implementation. No Apple code, KDK material or firmware excerpt is published.

The first observation directly confirms compensation during the real queries:

| Scheduler-only observation | Result |
| --- | ---: |
| Complete `_Q47` / `_Q48` calls | 8 / 8 |
| `_Q48` outer duration minimum / maximum | 584.407 / 1,310.926 ms |
| `_Q48` direct 10 ms sleep requests | 247 |
| Paired `_Q48` scheduler BLOCK / UNBLOCK transitions | 259 / 259 |
| Same-group Mach timer starts inside complete `_Q48` calls | 21 |
| Those starts inside observed `_Q48` blocked intervals | 21 |

All 247 sleep requests were followed by a same-thread scheduler BLOCK event
within 0.053 ms. All completed queries have alternating, paired BLOCK/UNBLOCK
records. Therefore a long `_Q48` outer duration does **not** mean that its sleep
period continuously excludes other callbacks from the group. Conversely,
observing other timer callbacks start does not establish that they met their
deadlines. The earlier calibrated query/timer overlap remains a correlation;
it is not evidence that sleep compensation failed.

Across the eight complete `_Q48` calls, per-call outer durations sum to
7,889.322 ms, of which scheduler-blocked intervals sum to 2,976.937 ms.
The remaining 4,912.385 ms includes running and runnable time. These are sums
over calls, not interval-union fractions of the trace, and the complement is
not an exact CPU-time measurement. They motivate examining work outside the
recorded blocking intervals rather than shortening the firmware poll.

The second fresh observation added only 99 Hz native on-CPU sampling. It
collected 623 nonempty query stacks: 79 for `_Q47` and 544 for `_Q48`; 72
contained namespace search. Samples are distributed across AML parsing,
namespace lookup, allocation and support routines, without an established
single repair target. Per-CPU sample totals were 1,184–1,185 across 16 CPUs.
On-CPU samples cannot exclude waiting or interrupt-masked access paths, and
sample counts are not exact CPU time. Do not infer that acknowledgment or
interpreter waits were absent merely because a particular frame was not
sampled.

This second finite cutoff contains 19 query entries and 18 exits, plus one
unfinished callback entry. Those right-censored operations are excluded from
complete-duration accounting; trace exit does not mean firmware execution was
stopped. The 18 complete queries comprise nine of each method. Same-group Mach
timers started 24 times inside complete `_Q48` calls, 23 during recorded query
blocking. All completed queries again have paired scheduler transitions.
No new Mach-timer delivery deadline or normal GUI latency comparison was run.

Native SystemMemory handling and its physical-access wrappers were inspected
privately. Candidate physical/helper probes are unavailable, and the wrappers
tail-jump; an entry or tail-call return must not be presented as an observed
acknowledgment value. No new physical-memory read, write or explicit AML
evaluation was requested. The hardware acknowledgment contract remains
unverified. Do not disable queries, shorten polling, force completion, change
OS identity or alter power-limit updates to suppress the symptom.

Final independent readback passed the exact active candidate/cache, complete
metadata and image gate for 416 records/29 codeless records, all 415 unrelated
images, exact accepted recovery, original loaded ACPI/full EFI recovery and
current-boot accelerated startup. The same WindowServer survived; no error
counter or matching diagnostic report increased. Both tracers/supervisors
exited, ACPI debug flags and the existing ktrace owner/configuration were
preserved, daily PR28 waiting remains on and resident monitors remain off.
Keep the active candidate and accepted owner baseline distinct. The residual
stutter is unresolved. Next distinguish pending-to-dispatch delay and runnable
interpreter work from acknowledgment latency before selecting a minimal
semantics-preserving intervention. See the sanitized
[scheduler compensation record](validation/build34-ec-scheduler-compensation-20261119.json).
