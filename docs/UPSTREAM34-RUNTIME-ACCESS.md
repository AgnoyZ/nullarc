# Original build 34 runtime access correction

Status on 2026-11-15: **a demonstrated WindowServer file-access defect is
repaired locally; a fresh bounded desktop test is prepared, not yet dispatched
at this checkpoint.** Desktop acceleration is not yet verified. The default
source remains original build 34 plus the existing VRAM/user-helper fixes.

## Consumed desktop attempt

The preceding [watchdog-correction trial](UPSTREAM34-DESKTOP-RETEST.md) booted
at **20:05:44 +08:00** on macOS **26.7.2 / 25G332**, x86_64. Original startup
observed the native panel, all 17 firmware loads returned zero transport/status,
and both compute and graphics queues produced their expected GPU-written
values. Both queue adoptions and the accelerator claim returned success.
This is actual queue execution evidence, not a successful accelerated desktop.

WindowServer then aborted during display-device creation. Three retained
crash reports match the trial's boot identity and incident interval. Each
CoreDisplay image matches the current framework, with symbol offset **2972**
and image offset **289801** at the same assertion return. Offline examination
identifies that assertion as **Failed to create MetalDevice**. Apple code,
framework images, disassembly and raw reports are retained privately.

The original startup requested its own fallback after detecting three reports;
the firmware-desktop boot began at **20:06:45 +08:00**. There is no independent
Metal-exit, desktop-complete or trial-success receipt. No external managed
recovery request was dispatched. The consumed witness exited, its exact plist
was archived and removed, and the trial cannot retry.

Historical unified-log reads were explicitly filtered by trial boot identity,
time interval and process. The first query retained **2,282** matching records
and excluded **2,494** records from another boot; a subsequent broader
info/debug loader query retained **2,563** incident records. A time-range
argument alone was insufficient to exclude unrelated boots. No device-denial
or Vulkan-initialization failure from the plugin was retained. The reports do
not list a plugin image, but that absence alone does not prove it never loaded.
The mode-zero warning remains a separate lead, not an established cause.

The initializer also emitted a fatal-style ERR-trap line during a handled
watchdog no-match substitution, then continued through successful queues.
That message does not identify a new terminal initializer failure. It is left
unchanged in this permission-only test to keep one behavioral variable.

## Reproduced access defect and exact local repair

The installed runtime parent `PhxGPU` was owned by `root:wheel` with mode
**0700**. Its plugin/runtime files were readable by root, but a child process
that dropped its supplementary groups, group and real/effective user to
`_windowserver` could not open **17 of 18** checked file paths. The readable
path was the allow-list outside that parent. The checks open ordinary files
only; they do not load a plugin, call Metal or open an IOKit/GPU client.

At **20:42:02 +08:00**, only that parent directory's mode was changed to
**0755**, retaining root ownership and denying group/other writes. Repeating
the same credential-dropped check passed **18 of 18** paths. All 13 installed
plugin/runtime file hashes remain unchanged, strict plugin signature
verification passes, and the original plugin contains its AMD-panel admission
check. The two existing mode-0700 symlinks required no modification: their
targets became readable after the single parent correction.

Earlier root-run Metal success could not detect this traversal defect. This
is a concrete deployment/readiness failure and a plausible explanation of the
Metal-device abort; only the next real desktop trial can establish whether it
was the sole cause. There is no allow-list bypass, process-environment bypass,
security-setting change, driver replacement or binary upload in this repair.

Six CPU/file-access regressions passed using the actual admission function:
root-readable files behind a root-only parent are refused; a parent-only mode
change permits the same bytes; protected leaf files and missing files still
fail; symlinks need no gratuitous change; and the admission function invokes
no loader, GPU or process-execution API. The inherited observer/trial suites
also passed **31 + 11** methods, for **48** checks total. The previously
documented unrelated scheduler-sensitive downstream CPU failures are not
reclassified as passing.

## Fresh test and rollback

A distinct root-owned packet pins **2,078** inputs. Its actual launchd
preparation role passed with all 18 WindowServer file-access checks, GPU-off
present, display unarmed and **zero GPU calls or reboot requests**. Directory
search modes are now checked in addition to file hashes. Arming repeats the
credential-dropped read check before consuming its exclusive intent.

The test permits one ordinary native-desktop boot, at most one unchanged Metal
probe after original startup succeeds, a 300-second independent observation
deadline and at most one managed recovery restart. Original startup and its
watchdogs remain unchanged. The independent witness never initializes the GPU,
restores next-boot GPU-off after original startup crosses its off gate, removes
persistent rearming, and will not compete immediately with an observed
original fallback. Software timers cannot guarantee recovery from a hard hang.

All installed kernel, accelerator, helper, plugin, runtime, firmware and startup
bytes remain as before this repair. The complete EFI manifest was verified
read-only and left unchanged/unmounted. Success still requires actual Metal
GPU output, native-frame progress, a stable single WindowServer and no new
WindowServer diagnostic report. No old packet is reopened.

Rollback retains the empty GPU-off marker, removes the M2 marker and only the
specific display-arming variable, then verifies the firmware desktop if a
recovery boot was required. The exact prior directory mode is recorded
privately for reversal if needed; no binary rollback is necessary. Future
installers must explicitly create the public runtime parent with mode 0755
even when private packet preparation uses umask 077, and verify access under
the actual consumer credentials before admission.

See the [sanitized validation record](validation/upstream34-runtime-access-20261115.json).

## Subsequent single dispatch

After the preparation record was committed, pushed and independently verified
at `d46367aabefd2c0337824a3b7043bc46749ce5d4`, the new exclusive arming
operator was consumed once. Shutdown returned zero without a caller timeout;
an independent read found one root-owned scheduled restart, matching arming
and all 2,078 pinned inputs. The restart is expected approximately
**20:50:04 +08:00 on 2026-11-15**. No ordinary reboot dispatches remain.
The next-boot desktop/Metal outcome has not yet been observed at this dispatch
checkpoint and must be read from the new packet before making a success claim.
