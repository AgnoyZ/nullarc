# Build34 smoothness comparison with NullMoth

The owner's renewed November 20 step-by-step request excludes Weather and
resumes with [R1a elapsed-time accounting](BUILD34-WAIT-DEADLINE.md) on the
recovered owner-accepted build34 runtime. A fresh independent readback of the
12:20:11 Asia/Shanghai boot passes. Source/CPU/native-artifact checks pass and
new exact private kernel/job backups are prepared, but R1a is not installed
or hardware-accepted. The former Weather prerequisite was withdrawn and must
not be replayed. The prior reboot grant is consumed; candidate activation
requires a fresh explicit installation/test-restart grant. R1b and R2–R6
remain pending until R1a hardware acceptance. This supersedes the execution
status only; the following November 19 comparison remains historical evidence.

## Scope and conclusion

This November 19, 2026 review compares default build34 source
`c575324bc1fdd3df87ed3994a4b0a3144cd50a85` on
`upstream34/vram-layout-fix` with the independently queried NullMoth
`nullmoth/nvidia-macos-driver` main head
`87e524ab36f12d17c04626d6cf7fc3bde1cc63e4`. The latter is the same revision
used in the earlier VBL review. The actual local OS readback is macOS 26.7.2,
build 25G332. Build41/build42 are excluded.

The strongest identified gaps are the AMD present path's synchronous surface
wait and CPU scanout copy, conservative cross-queue completion reporting,
global submission-lock contention, and polling-based native waits. These
are concrete implementation differences or risks, not proof that any one
explains all perceived stutter. No same-hardware, same-scene frame-time
comparison exists: NullMoth's README says its main development/test card is
an RTX 5060; this machine is a Radeon 780M. Its NVIDIA RM/NVKMS/NVK stack is
not an interchangeable AMD implementation.

This is a source review with a one-time read-only counter snapshot, not a
benchmark or an optimization deployment. No driver code/configuration,
installed image, startup policy, EFI/ACPI, cache, security setting or power
state was changed. No application or GPU test was launched and no resident
monitor was enabled. Only this report and its sanitized evidence record are
added. Existing ordinary applications and the desktop remained running.

## Evidence and interpretation

The snapshot contains boot-cumulative counters, a most-recent copy duration,
and cumulative maxima. They are not a controlled interval or a distribution.

| Read-only counter | Value | What it establishes |
|---|---:|---|
| `nvaccel_iop_flips` | 0 | No completed zero-copy flips recorded by this path. |
| `nvaccel_iop_ok` | 35,061 | Successful display transactions recorded; not physical refresh FPS. |
| `nvaccel_iop_copy_us` | 1,318 us | Most-recent timed copy, excluding the preceding surface wait. |
| `nvaccel_iop_copy_us_max` | 14,495 us | Cumulative maximum timed copy, not current typical latency. |
| `nvaccel_surface_gpu_waits` | 25,539 | Completed display-side surface waits recorded. |
| `nvaccel_surface_gpu_wait_max_us` | 55,497 us | Cumulative maximum surface wait; not necessarily the same frame as the copy maximum. |
| `nvaccel_surface_gpu_timeouts` / `nvaccel_iop_fail` / `phx_hang_kills` | 0 / 0 / 0 | These counters recorded no corresponding failure; this does not prove smoothness. |
| `nvaccel_iop_sse` / `nvaccel_iop_vsync` | 1 / 1 | The existing SSE-copy and transaction-vsync controls are already enabled. |
| `phxbos_flush` / `phxbos_flush_bytes` | 0 / 0 | The optional whole-BO CPU cache-flush walk is not an active measured expense in this snapshot. |

The two maxima must not be added into a claimed frame duration. For scale
only, a 60 Hz frame budget is about 16.7 ms; the 14.495 ms copy maximum is
large relative to that budget. This does not measure the panel's effective
FPS. The cumulative `phxfb_vbl_late_us_max=148099` may include startup and
does not demonstrate that the accepted VBL fix has regressed.

The running processes also do not all map the same plugin revision. The
previous authorized Weather trial mapped the full-view candidate from
`87859b323267030afdfdcd9f4e52dc7168697686` in the new Weather process, while
the surviving WindowServer retained the pretrial render-clear plugin from
`9f838846f6a8eeab80890014eace3a5de1b16067`. This review does not restart
either process. Source comparison of the default branch is not a claim
that every new source change is already active in WindowServer. See
[Weather trial](BUILD34-WEATHER-INTERNAL-TRAILS.md).

## Ranked work

The ordering combines user-visible relevance, available evidence and the
ability to isolate a correct change. R1's timing correction is the smallest
first source candidate; it is not a promise of the largest FPS gain. R2
has the clearest measured display-path expense. Each row needs separate
validation rather than one combined performance patch.

| Order | Area | Evidence | Recommended direction |
|---|---|---|---|
| R1 / high | Native wait accounting and submission backpressure | Static source: nominal-delay accounting; global lock held during ring-pressure polling. | First use real monotonic elapsed time for wait deadlines. Separately redesign ring-pressure waiting so it does not monopolize the device-wide lock. |
| R2 / high | AMD presentation: wait plus full-frame CPU copy | Static AMD path plus the local counters above. | Investigate a bounded, owned asynchronous present/copy path; longer term implement AMD-specific scanout/flip with real completion and buffer lifetime. |
| R3 / high | Exact completion and event wakeup | Static global retirement watermark; native completion packets request no interrupt. NullMoth has channel-target waits and a WindowServer event-sleep path. | Preserve safe global retirement for reclamation, add exact submission/queue waiting, then integrate supported AMD completion events with a bounded fallback. |
| R4 / medium | Surface publication policy | Static difference from NullMoth; local PR28 daily policy is enabled, but its current cost is unmeasured. | Measure actual publication waits and classify backing/handoff before reducing synchronization scope. Preserve publication correctness and the owner-selected daily policy. |
| R5 / medium | Broad Vulkan barriers/render-pass dependencies | Static all-command dependencies; NullMoth offers opt-in range hazard tracking. | Start with a bounded census, then narrow only proven redundant dependencies on RADV. |
| R6 / later | Import/backing/PSO cache costs | Existing caches already cover important paths; residual costs are not measured here. | Measure cold/warm compilation, import churn and cache-retirement cost before porting more cache machinery. |

### R1: fix time accounting before changing wait policy

`src/phxbringup/PhxBringup.cpp:2160` (`doWaitSeq`) checks completion after
`IODelay(50)` during the first nominal millisecond and `IOSleep(1)` later.
Its `waited` variable advances by the requested delay, not actual monotonic
elapsed time. Scheduler oversleep can therefore make elapsed wall time
exceed the requested budget. This is a source-level timing defect/risk;
this review did not measure its overshoot on hardware.

A minimal candidate should use a real bounded deadline, preserve zero-time
poll semantics and pending-work/error behavior, and avoid overflow. CPU
tests should cover delayed wakeups, completion at the boundary, zero and
capped budgets. The display-side `nvSurfWaitReady` already uses an absolute
deadline and sleeps on its pending-surface condition; do not misdescribe
all waits in the project as polling or apply the same rewrite there.

Separately, `gpuSubmit` at line 852 selects the global GFX or compute queue,
then holds `gpuLock` while polling for ring/history space in 50 us steps.
The source's approximate two-second bound is a nominal delay count, not
proof of a two-second real-time limit. Under pressure, that lock can block
the other queue's submission and other operations that require it. The
condition is not paid on every submission, and no pressure/lock histogram
was captured in this review. A later change must revalidate ring space,
VM binding and ownership after any unlock/relock; simply dropping the lock
inside the loop would be unsafe.

### R2: remove display-thread stalls without reading unfinished pixels

In `src/phxaccel/accel/nvrm-accel.cpp:2111`, `nvAccelIopFlip` rejects every
framebuffer that is not `NVRMNVDAFramebuffer`. The AMD `PhxAMDFB` therefore
does not reach the NVIDIA asynchronous flip worker even though
`gIopAsync=1` exists. `performTransaction` at line 1110 instead waits for the
surface, checks copy readiness, maps the surface, and copies its rows into
the fixed scanout; `l10r` frames are converted to 8-bit while copying.
Transaction completion subsequently observes the synthetic VBL sequence.

NullMoth's `kexts/NVRM/accel/nvrm-accel.cpp:2547` has the same vendor check,
but its eligible NVIDIA path reaches an asynchronous worker and
`nvFlipToSurfacePure`. NullMoth also has copy fallbacks; it is not universally
zero-copy, especially when displaying through another vendor's panel.

For AMD, moving wait/copy work off the display transaction caller is a
candidate to investigate, not an existing safe patch. It needs retained
surface/mapping ownership, bounded outstanding frames, cancellation and
stop/sleep handling, accurate completion notification and preservation of
the old frame when new pixels are not ready. With a fixed live scanout,
moving a CPU copy to a worker alone does not establish tear-free output or
save bandwidth. GPU copy, damage-limited copy, or a real AMD DCN page flip
needs independent coherency/format/scanout validation. Do not merely remove
the wait or vendor check. The family GPUVA mapping in
`src/phxaccel/accel/phxfb.cpp:225` is bookkeeping, not a complete scanout
mapping implementation.

`NVMTLDevice.m:915` already imports suitable IOSurface host pages and can
use a linear image alias or a host-buffer/GPU-copy fallback. Application
IOSurface import does not eliminate the final display copy identified here.

### R3: separate exact fence waiting from safe global retirement

`PhxBringup.cpp:834` (`gpuRetired`) returns a conservative global watermark
below the oldest outstanding sequence across both queues. Thus a later GFX
submission can have written its own queue fence while an earlier unfinished
compute submission still holds the global returned value below its target.
This is a credible mechanism for background work to delay desktop waiters;
the current user-visible symptom was not reproduced under controlled load
in this review.

Changing the minimum to a maximum would falsely retire unfinished work.
Retain the conservative watermark wherever resource reclamation/VM lifetime
depends on it. An exact-wait design must audit the native ABI, RADV transport,
sequence ownership, queue generation, cross-queue dependencies, teardown
and resource lifetime together.

The current `RELEASE_MEM` packet at line 908 requests 64-bit fence data
without an interrupt. `doWaitSeq` polls/yields as described above. NullMoth's
`nvk/nvk-macos.patch:9708` still contains polling/backoff, but
`nvkmd_nvrm_wait_block` at line 9748 defaults to completion-event sleeping
for WindowServer after a short spin. Its code snapshots the event count,
rechecks channel semaphores, and bounds event sleeps to 2 ms. Ordinary apps
default to polling there; missing/copy-only events fall back as well. This
is not evidence that every NullMoth wait is interrupt-only.

The useful pattern is race-free completion notification with an exact fence
recheck and bounded fallback. NVIDIA RM event selectors and packet fields
must not be copied into the AMD path. Validate AMD interrupt routing and
event lifetime before enabling it; an interrupt bit alone is insufficient.

### R4: make publication selective only after measuring the current wait

`src/nmplugin/NVMTLEventSync.m:312` implements the local PR28 opt-in. On this
machine the owner selected `NVMTL_SURFACE_COMMIT_WAIT=1`, with the unchanged
250 ms budget, execution-worker deadlock exclusion and WindowServer
exclusion. It waits for relevant ordinary-application surface writers;
250 ms is a ceiling, not a fixed per-frame delay. Timeout does not retire
or discard pending work.

NullMoth's `plugin/nvmtl_schedule_policy.h` and `NVMTLEventSync.m:392` instead
offer four scheduled/publication modes: all non-drawable surface writes for
Chromium by default, and private two-plane surfaces for other processes by
default (also excluding the drawable).
The local scheduled-after-publication switch at line 380 only recognizes
the earlier boolean mode. These callbacks are not a drop-in equivalent of
the local blocking commit wait. AMD host aliasing, private-image copyout
and interprocess visibility must be classified first. Do not automatically
turn PR28 off, shorten its budget, or reinclude WindowServer for speed.

### R5 and R6: profile optional policies before importing them

`src/nmplugin/nvmtl_vk.c:6675` uses an all-commands memory read/write barrier;
render-pass shape dependencies at line 5230 are also broad. NullMoth's
`plugin/nvmtl_hazard.h` tracks memory/range conflicts and supports a census
that leaves barriers intact. Acting mode requires `NVMTL_HAZARD=1` and is
off by default in the pinned source. Its NVK-specific drain/flush rationale
does not prove the same gain on RADV. The existing local
`NVMTL_RP_LIGHT=1` policy is also opt-in and WindowServer-only; it is not
enabled by the reviewed configuration. Evaluate it as a separate candidate,
not as a proven default fix. Keep full-view CLEAR, required LOAD refusal,
sticky encoding-error rejection and all required interprocess dependencies.

The local surface cache already has A1's corrected keys and strong backing
retention (`NVMTLDevice.m:985`). Its insertion-time `keep.allKeys` scan at
line 997 is a later measurement candidate, not a demonstrated leak or main
stutter cause. NullMoth's cross-wrapper host-page leases require
`NVMTL_HOST_PAGES_SHARE=1`; its shared-buffer VRAM working-copy feature
requires `NVMTL_SHARED_VRAM=1`. Neither is a demonstrated default explanation
of NullMoth's smoothness. PCIe-oriented shadow copies may be counterproductive
on a 780M UMA system. Count imports, bytes, cache hits/retirements and PSO
compile time before changing either policy. Do not start by replacing the
whole Mesa backend or changing power/clock policy without measurements.

## Preserve accepted fixes and require comparable acceptance

Async commit, G-SUB submit-ahead (default cap 16) and event folding already
exist locally (`NVMTLEventSync.m:294,541,552`, `NVMTLObjects.m:4218`). A missing
NVK-specific statistics symbol in RADV does not by itself disable them.
SSE and vsync were already enabled in the snapshot; optional BO flushing
was not. Recommending these as newly missing features would duplicate work
or diagnose an inactive path.

The accepted VBL/AML changes must also be retained. The newer
[AML batch-copy results](BUILD34-AML-BUFFER-COPY.md) supersede an inference
from the earlier delayed VBL-only stutter sample: the paired recorded GUI
maximum fell from 512.552 ms to 21.895/33.099 ms in two candidate samples,
and the separate Mach-timer maximum from 521.591 ms to 11.458 ms. These
were bounded cross-boot observations, not long-term stability or physical
FPS acceptance. Do not return to the old HIGH timer group to imitate
NullMoth or label the old contention symptom as currently reproduced.

For any later authorized candidate, first pass focused source/CPU checks,
then use a fresh compatible exact-image/recovery scope. Test one variable
at a time, under the same resolution/refresh/window scene and normal GUI
scheduling. Separate cold compilation from warm interaction and distinguish
idle desktop from bounded background GPU load. Record frame-interval
p50/p95/p99/max, missed budgets, actual wait/copy/lock durations and error
counters. Physical presentation/FPS, direct input latency and visual
correctness require suitable observations; VBL or submission counts alone
are insufficient. Keep resident monitors off and do not replay consumed
observers, installers or restart authorizations. Weather trails and Liquid
Glass remain visually unaccepted, so a faster path must not conceal stale
pixels or failed work.

The review's pins, key source hashes, full counter subset and claim limits
are in
[`validation/build34-nullmoth-smoothness-review-20261119.json`](validation/build34-nullmoth-smoothness-review-20261119.json).
Reference downloads remain ignored/private; no third-party source or binary
was incorporated by this documentation change. Any later port requires its
own component license/provenance review. Existing license files and upload
restrictions remain unchanged.
