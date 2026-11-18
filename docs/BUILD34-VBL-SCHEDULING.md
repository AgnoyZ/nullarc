# Build34 VBL scheduling candidate

Status on 2026-11-18: **not installed or loaded; owner-authorized installation
preparation passed CPU, native and complete offline-cache checks.** The initial
direct-thread-call candidate failed target linking; a private-provider attempt
was also rejected. The selected implementation uses public IOKit timer APIs.
The accepted build34 acceleration and desktop remain active. The original-ACPI
restart baseline is still required before installing the scheduling treatment.
No on-device stutter repair or higher FPS has been demonstrated.

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
This exercised ordinary composition; it did not create a Metal device or submit
an explicit native/Metal test workload. Core Animation and WindowServer could
still use the existing accelerated compositor.

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

The machine is still in the failed ACPI candidate's 16:39 boot on 2026-11-18.
Its exact original EFI rollback is on disk, but loaded tables have not yet
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
