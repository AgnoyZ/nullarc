# Build34 VBL scheduling candidate

Status on 2026-11-18: **CPU/static validation passed; not installed or loaded.**
The existing accepted build34 acceleration and desktop remain active. This
candidate has not demonstrated an on-device stutter repair or higher FPS.

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

Only `src/phxaccel/accel/phxfb.cpp` changes in the production source:

- Allocate VBL in `THREAD_CALL_PRIORITY_KERNEL` with `THREAD_CALL_OPTIONS_ONCE`.
  The group can make progress independently of HIGH work; ONCE prevents
  overlapping invocations of the same self-rearming callback.
- Publish/read the stop flag atomically. Drain current work and any single
  successor rearmed by a callback already past its stop check before freeing the
  timer or removing AGDC state. A second cancel/wait handles that successor;
  the free retry retains the previous defensive refusal handling.

The callback's staged deadlines, frame period, handler notifications, late-tick
accounting and missed-period behavior are unchanged. PhxBringup, native ABI,
phxctl, A1/A2/corrected-A3 logic, IB correction, plugin source, PR28's 250 ms
budget and WindowServer exclusion are preserved. No runtime knob, installed
binary, admission policy, EFI file or OS security setting is modified.

The API review used the existing audited MacKernelSDK at
`3f750085caa17ec3a7880f11c11bf4f48cd6a164` and Apple's published
`apple-oss-distributions/xnu` `osfmk/kern/thread_call.h` and `thread_call.c`
(reviewed 2026-11-18). These are API/source references, not a claim that public
XNU main is byte-identical to the running kernel. No Apple implementation code
or additional third-party component was copied into this candidate.

## Validation and remaining work

`make test-build34-vbl-scheduling` extracts the actual callback, allocation and
drain into a CPU-only harness. Its 44 assertions cover a modeled busy HIGH
group, ONCE reentry refusal, staged and unstaged delivery, late notification
without a catch-up burst, stopped callbacks, rearm during stop, and allocation
failure. Scheduler/clock doubles demonstrate the intended contract; they do
not test XNU's implementation or a physical GPU.

Existing checks passed: 43 panel-timing cases, 511 extracted refresh/timing
assertions, 3,646 extracted framebuffer assertions, alias/pool policies, PCI
matching and the baseline unit suite. Firmware fixture tests were skipped
because their optional fixtures were absent; no download was triggered. ASan
and UBSan reported no failures in the extracted-method harnesses.

The existing native PhxAccel build recipe also passed using the pinned, clean
SDK, in a new ignored staging directory. Signature and x86_64 architecture
checks passed; the expected allocation and cancel/wait imports were present.
No kext was installed, loaded or uploaded. The sanitized record is
[`validation/build34-vbl-scheduling-20261118.json`](validation/build34-vbl-scheduling-20261118.json).
Raw stacks, identifiers, process listings and diagnostic source/output stay
in local private storage.

Before hardware acceptance, prepare a separately authorized, exact-hash
installation/recovery packet based on the current accepted runtime source
`1d4968fbc2ce988c77bdd85b2ec36f435b57f496`. Do not weaken the existing build34
checks to admit a new binary. Preserve the original-ACPI restart prerequisite
and separate any scheduling treatment from the withdrawn S5 experiment.
Compare the same foreground-policy GUI/worker observations before and after,
then validate real GPU execution and desktop correctness under the unchanged
admission gates. Long-duration stability, interactive input latency and FPS
remain unaccepted.

Rollback currently requires no action: the candidate is not installed. The
running accepted kernel/plugin, enabled acceleration, daily PR28 wait and
disabled resident-monitor policy remain the baseline. A future installation
must retain the exact accepted binary/recovery manifests and return to those
hashes on failure; do not replay a consumed historical trial.
