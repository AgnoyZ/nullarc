# Original build 34 desktop presentation measurement

On **2026-11-15, 22:08–22:10 +08:00**, the already active native-desktop
session completed three ordinary-window and three material-window measurements.
The ordinary window averaged **7.17 driver presentation transactions/s** and
the material window averaged **7.21 transactions/s**. Desktop presentation
throughput in these workloads is low; a 120 Hz display mode does not establish
120 FPS performance.

The machine was running **macOS 26.7.2, build 25G332, x86_64**, with Radeon 780M
(gfx1103), original kernel/runtime build **34** and the previously verified
VRAM-layout helper correction. The default-source checkpoint was
`90bb06f6f9255cb5a16cc5eb87e78032566b2000`; the downstream evidence checkpoint
before this measurement was `31c22b5a371948a037e4071a60170af44c58e99c`.
All six application logs also reported native ABI 1.12, build 34. Exact installed
image verification and the separate successful GPU-result probe are recorded in
[the preceding desktop trial](UPSTREAM34-DESKTOP-RETEST.md).

## Workload and collection

- Main display: **2560 × 1600 pixels**, scale **1**, reported mode **120 Hz**.
- Unmodified upstream `tools/anim/wintest.m`, also byte-identical to that path
  in upstream build-34 commit `9dd76b604fca5e0125bd3caa5723df0f611ff27f`.
- A **1200 × 800 point** window moves in a circle, requesting AppKit timer
  updates at 120 Hz. This request is not a measured application frame rate.
- `WT_MODE=plain` draws a checkerboard window. `WT_MODE=heavy` adds the upstream
  glass sidebar, unified toolbar, inspector and scroll content.
- Order: plain 1, heavy 1, plain 2, heavy 2, plain 3, heavy 3. Only the window
  mode changes between successive measurements. Background desktop activity
  and system load were not isolated.
- Each launch waits up to 12 seconds for its expected onscreen window, then
  warms up for 3 seconds. Visibility, expected dimensions, full-screen fit and
  a changed window position are checked before and after measurement.
- Each round targets 15 seconds and uses **observed monotonic elapsed time**.
  Read-only `sysctlbyname` calls sample approximately once per second, with
  boundary timestamps bracketing the presentation-counter read.
- The application retains a 40-second self-termination limit. After collecting
  the samples, the harness sends SIGTERM only to its own application process;
  all six returned the expected signal status and were reaped.

The measured quantity is:

```text
(final debug.nvaccel_iop_ok - initial debug.nvaccel_iop_ok)
----------------------------------------------------------------
             observed monotonic elapsed seconds
```

The original driver describes this counter as display-pipe transactions copied
to the panel. It is a **global driver presentation-transaction rate**, including
other desktop activity, rather than an application-rendered-frame counter or an
external measurement of distinct physical panel frames. No baseline subtraction
is applied. `debug.phxfb_vbl_n` counts the driver's **software VBL timer ticks**;
those values are retained separately and never treated as rendered FPS.

## Results

| Mode | Round | Measured seconds | Presentation transactions | Transactions/s |
| --- | ---: | ---: | ---: | ---: |
| Plain | 1 | 15.008779 | 91 | 6.06 |
| Plain | 2 | 15.168645 | 107 | 7.05 |
| Plain | 3 | 15.130459 | 127 | 8.39 |
| Heavy | 1 | 15.075979 | 95 | 6.30 |
| Heavy | 2 | 15.197425 | 118 | 7.76 |
| Heavy | 3 | 15.101335 | 114 | 7.55 |

| Mode | Total transactions | Total measured seconds | Time-weighted transactions/s | Round range |
| --- | ---: | ---: | ---: | ---: |
| Plain | 325 | 45.307884 | **7.17** | 6.06–8.39 |
| Heavy | 327 | 45.374738 | **7.21** | 6.30–7.76 |

A preceding five-second idle sample measured 8 transactions over 5.068462
seconds, or 1.58/s. It is context, not an estimate of the workload's background
contribution. The near-equal mode averages do not demonstrate a material-cost
advantage or identify the bottleneck. The approximately one-second bins in the
JSON are counter rates over observed sampling intervals, not frame times,
1% lows or physical scanout measurements.

Before the final series, a preflight guard initially misclassified the
`IOAccelerator` query because `ioreg -c IOAccelerator` returns its `NMXAccel`
subclass. Correcting the collector's presence matcher changed no driver state.
An initial fixed-warmup pilot then measured plain mode at 120 transactions in
15.085033 seconds (7.95/s), but stopped when the heavy window was not visible
after three seconds. That incomplete series is reported separately in the JSON
and excluded from the three-round summaries. The final series uses the same
readiness rule for both modes; observed window readiness took 1.95–5.13 seconds.

## Health observations and limits

The same single WindowServer remained throughout the final series. PhxAMDFB,
NMXAccel and an IOAccelerator-subclass service were present before and after;
IONDRVFramebuffer was absent. All rounds retained AGDC 1, framebuffer-armed
readback 1, IOP 1 and hold 0. The driver failed-transaction and copy-skip
counter deltas were **zero** for all six measured intervals. No new matching
WindowServer, wintest, kernel or panic report appeared in the checked system
and user diagnostic directories, including their Retired subdirectories.
These observations do not establish smooth delivery, absence of dropped frames,
or general stability.

This test uses the existing accelerated session. It performs **no driver
installation, initialization, sysctl write, counter reset, startup arming,
EFI/NVRAM/security change, extra Metal probe or reboot**. No performance fix or
root cause is established here. Game/3D FPS, renderer throughput, independent
physical scanout, compatibility and long-term stability remain unmeasured.
Original next-boot GPU-off behavior is retained. Cleanup is limited to the
test's own processes; no driver rollback is needed.

## Provenance and evidence

- Source SHA-256:
  `a0b771a34fd20d7c2d269d44b8896a29adc5e1784144cd96b63ac0b2da9f55aa`.
- Locally signed executable SHA-256:
  `3a1d7df0afccc945c14b5b4d47e383890715c90da81e15370e713b13e8bc9f18`.
- Apple clang 21.0.0 (`clang-2100.1.1.101`), `-O2 -arch x86_64 -fobjc-arc`,
  linking Cocoa and QuartzCore; ad-hoc strict signature verification passed.
- Root `LICENSE` assigns this tool **MIT OR GPL-2.0-only**; the file has no
  different notice. No component code was copied into a new public program.
- [Sanitized measurements](validation/upstream34-desktop-fps-20261115.json)
  retain per-round counters, elapsed times, interval rates and arithmetic.
  Raw logs, process identities, the collector and local executables remain in
  ignored private build storage. No binaries or diagnostic archives are uploaded.
- Automatic GitHub CI remains disabled; this measurement adds no workflow or
  automatic trigger. Existing public binary-publication limits remain intact.
