# Original startup with publication-aware Metal observation

Execution assessed, 2026-11-15: **the publication-aware first boot passed the
unchanged real Metal compute verifier. The conditional desktop boot reached
PhxAMDFB but produced three WindowServer CoreDisplay assertion crashes and
recovered to the firmware desktop.** This packet is consumed and closed.
The [earlier exact-original trial](EXACT-ORIGINAL-TRIAL.md) remains consumed.
The successful basic compute workload applies to its first-stage boot; it is
not evidence of a working accelerated desktop or general stability.

The owner subsequently requested a [source correction for the known physical-layout
risk](VRAM-LAYOUT-SAFETY.md). It changes downstream safety paths only; it does
not change the original installation or the historical results below and does
not reopen this consumed trial.

## Single behavioral change

The installed upstream v0.4.0-alpha drivers, initialization helpers, firmware,
startup scripts/plist, watchdogs, Metal plugin and runtime remain byte-identical
to the retained release. The loaded PhxBringup image matches build 34. The
system remains x86_64 macOS **26.7.2 / 25G332**. The earlier reference physical
base and VRAM-extent conflict remains unresolved and explicitly accepted.

The original `PHX_FB` accelerator deliberately withholds `MetalPluginName`
until display arming or its 60-second headless callback. The prior kernel logs
confirmed this behavior, but the old external probe failed before the callback
could run. The fresh observer therefore waits for the original accelerator's
actual plugin-name and class properties before running the **same unchanged
Metal verifier once**. It does not restore the property itself or write a
display-arming sysctl. Absence alone cannot cause an early Metal probe.

The publication wait has a 120-second cap and reserves 45 seconds within the
existing independent 300-second boot deadline. Disappearance, a wrong plugin
name/class or the deadline causes the existing safe-state recovery. A probe
exit-code receipt is added for observation; the native executable and its
shader, zero-initialized output, completion limit and result requirement are
unchanged. A published plugin alone is never accepted as GPU execution.

## Preserved boot and recovery limits

The unchanged upstream LaunchDaemon still performs initialization. The external
observer invokes no initializer and requests the desktop boot only after
original startup, image identity and actual Metal execution all pass, with the
original one-shot flag present. Desktop acceptance still requires another real
Metal result, increasing frame counters, the expected display gates and a
stable WindowServer without a new diagnostic report.

There are at most two managed ordinary reboot requests and one managed recovery
request in this new packet. Exclusive intent receipts prevent retry; ambiguous
shutdown calls are never repeated. The original script's own watchdog/recovery
requests remain separate and unchanged. The independent initial-reboot timer
is 180 seconds and each observed trial boot has a 300-second deadline. The
unchanged original daemon can start before the observer ACK, and a hardware
hard hang can still prevent software recovery.

The trial is one-shot: restore GPU-off after the original off check, remove
persistent and one-shot display arming during the desktop stage, and keep the
next boot GPU-off even if the current desktop test succeeds. All consumed
installation and prior experiment packets remain closed. The old inactive
external witness plist was archived before installing this separate witness;
its original bytes, contract and receipts remain private and preserved.

## Preparation evidence

Thirty-one CPU-only methods passed. They retain the previous phase, refusal,
deadline and exclusive-reboot tests and add delayed/immediate publication,
missing/wrong publication, disappearance and deadline-reserve cases. The
waiter is tested with registry reads substituted and with command, probe and
marker operations forbidden. These methods run no real GPU or shutdown command.

The first staging comparison refused before any new packet/job or arming
write because the prior original startup created `fwaddr.log`. Independent
readback found that this generated diagnostic was the only extra file; no
release input was missing or changed. The revised preflight requires that
exact observed log metadata and retains the file. Only this output is excluded
from immutable input pins, because the unchanged upstream startup overwrites
it. Tests verify that changed/missing output and other unexpected files cannot
silently normalize away modified inputs. The raw log stays private.

Fresh full-file comparisons passed after that classification. The root-owned
packet pins **1,697 inputs**, including **1,656 frozen interpreter files**.
Its LaunchDaemon/interpreter path executed the unarmed preparation role and
exited with GPU-off retained and no display flags, GPU initialization or reboot
request. Those are preparation observations, not the final activation state.
The [sanitized record](validation/exact-original-readiness-20261115.json)
separates them from the actual execution below.

## Actual original Metal execution

The arming and initial managed reboot request were consumed at
**15:33:01 +08:00**. The initial caller returned zero without timing out. The
new boot began at **15:34:25 +08:00** and the original startup completed its
candidate initialization sequence. The external observer then waited
**54.14 seconds** for the original plugin-name/class publication, observing
the property at **15:35:38 +08:00**. This wait began after original startup;
it is not a measurement of the entire driver's 60-second timer.

At **15:35:41 +08:00**, the unchanged independent verifier returned zero and
reported an AMD device, a completed command and matching GPU-written output.
The pinned probe initializes its shared output to zero and requires its Metal
kernel's expected value. Its runtime diagnostic identifies the native backend,
ABI 1.12 and build 34. Original installed-input and loaded bring-up/accelerator
identity checks passed. This confirms one basic real Metal compute workload
in that boot, without certifying other workloads, scanout, frame pacing,
power, thermal behavior or long-term stability. It also confirms that the
previous premature no-device observation was not a valid post-publication
Metal failure report.

Only after this successful first-stage receipt and the original startup's
one-shot flag did the observer consume one desktop-reboot intent. That
caller's return-code receipt was not written; the subsequent desktop boot is
independently identified. No second dispatch was made.

## Actual desktop failure and evidence limits

The desktop boot began at **15:36:04 +08:00**. Original startup observed
PhxAMDFB on the panel, reported matching compute/graphics values and zero
adoption/claim results, set the display gates and released the framebuffer hold
at **15:36:16 +08:00**. The kernel records a normal sysctl hold release,
approximately seven seconds after the boot hold was established, rather than
a 120-second timeout release.

Before the original 90-second desktop observation completed, its monitor
reported three WindowServer crashes or hangs and invoked its existing M2
failure recovery. The external observer recorded phase-two failure at
**15:36:42 +08:00**. It never reached the second independent Metal probe or
the final frame-progress/WindowServer stability checks. There is no successful
desktop completion receipt.

Three private crash reports were independently verified against this failed
boot. All are `EXC_CRASH / SIGABRT` on the main thread through `__assert_rtn`
and `CoreDisplay_CreateDisplayForCGXDisplayDevice`, during CoreDisplay display
creation. Their assertion expression is not recovered. A time-range log query
also returned events from the subsequent boot; requiring the failed boot,
incident time window and kernel/WindowServer process leaves **2,427 records**
and excludes **3,819 records from another boot**. Those excluded events are
not used to diagnose this failure.

The filtered incident log records a request for display mode zero followed by
failure to obtain its mode information. The pinned original framebuffer only
advertises/accepts mode one in its display-mode, pixel-information and timing
methods. This is a display-mode compatibility lead, not a demonstrated cause
of the CoreDisplay abort. The framework's assertion text remains private/redacted;
neither accepting mode zero, changing timing answers nor extending the hold
has been validated as a fix. The trace does not establish the earlier RADV
cleanup/device-loss failure as the cause of this different incident. The
accepted reference-layout risk also remains unresolved despite basic compute
success.

## Recovery and closed state

The external observer consumed its single managed recovery intent after
recording failure. The original script also retained its own M2 recovery
request; these are accounted separately. The managed recovery caller's return
status is unobserved and was not retried. A new boot beginning at
**15:37:05 +08:00** matches the recovery-postboot receipt and skips original
initialization because GPU-off is present.

Independent readback verifies GPU-off with M2, one-shot and pending flags
absent, IONDRVFramebuffer present, no NMXAccel/PhxAMDFB/IOAccelerator and one
WindowServer stable across ten seconds. A fresh full release-file comparison
still passes. All 1,697 pinned inputs and symlinks matched before witness
retirement. The original bring-up image remains loaded; the unused accelerator
image was observed matching the package earlier in recovery and was absent at
the final read. Absence is not treated as a mismatched image.

Only the completed external witness plist was archived with its expected hash
and removed from its active LaunchDaemon path. Its contract, sources and
execution receipts remain intact. This intentional location change is the
sole retired input and is accounted for by the private closure receipt. No
installed original driver/runtime/helper, EFI, partition, BIOS/security setting
or unrelated NVRAM was changed. There is no initialization or recovery allowance
left in this packet, and the next boot remains GPU-off.

Read root-owned intent, publication, probe, stage and recovery receipts before
continuing. Never dispatch again after an existing arm/reboot intent. Do not
modify a consumed contract or observer, reinstall the fork, change EFI,
partitioning, BIOS/security settings or reset NVRAM. Only the scoped upstream
display flag is used and cleared by the bounded test.
