# One original-build34 desktop acceleration reboot test

Latest result, 2026-11-15: correcting the demonstrated runtime-directory
permission defect allowed original startup and the independent real Metal
probe to complete, without a fresh WindowServer report. The external observer
then rejected the original driver's boolean armed readback using an incorrect
command-value expectation and requested recovery. The corrected observer and
distinct next test are documented in
[runtime access correction](UPSTREAM34-RUNTIME-ACCESS.md); the preparation
checkpoints below are historical and do not claim fully accepted desktop
acceleration.

## Authorization and verified starting point

On 2026-11-15, after changing the default branch to original build 34 plus the
VRAM layout correction, the owner explicitly requested a reboot acceleration
test. This is a new bounded request; all prior consumed attempts remain closed.

Before preparing it, the completed original34-plus-correction headless receipts
were read and checked against the current boot. Both GPU queues wrote their
expected values and were adopted. The unchanged Metal probe completed on the
AMD GPU and verified a GPU-written value. Current loaded image, geometry and
the four corrected installed user files match their pinned identities. The
original kernel, accelerator, plugin, runtime, firmware and startup script are
unchanged. The complete EFI manifest was independently checked read-only and
left unchanged/unmounted. Observed OS: macOS **26.7.2 / 25G332**, x86_64.

The desktop is still using the firmware framebuffer at this checkpoint. The
earlier uncorrected original desktop attempt failed in CoreDisplay device
creation. The address correction does not establish that this separate display
failure is fixed; this trial measures that outcome once.

## Single new trial

The original startup daemon will execute on the next ordinary boot. The
one-boot `phxfb-boot` arming and original M2 marker select the original native
framebuffer. No kernel/runtime installation, EFI write, broad NVRAM reset,
security change, partition operation or same-boot reinitialization is included.
Only the specific original display-arming variable is set/cleared, with its
normal original commit operation.

A new external launchd witness observes the original startup. Its preparation
role has already run with zero target calls. It never invokes `full.sh`,
`bringup5.sh`, `mesboot` or `phxctl`; GPU initialization is performed only by the
unchanged original daemon, using the four corrected installed helpers/scripts.
The witness restores GPU-off after that daemon has crossed its kill-switch
gate, removes persistent rearming and does not retry a consumed desktop boot.

Limits are **one ordinary reboot/desktop attempt**, a **300-second independent
observation deadline**, one unchanged Metal probe, and at most **one managed
recovery reboot**. Upstream's own watchdogs/recovery behavior remain unchanged;
the external observer is not a prerequisite gate before upstream's first I/O,
and these software timers cannot guarantee recovery from a hard hardware hang.
An abandoned initial dispatch restores the safe flags rather than retrying.

Success requires the exact loaded build34 image, target geometry, successful
original queue/adoption/startup evidence, original Metal publication, real
GPU-written Metal output, the native framebuffer, increasing actual present
counter samples, correct display-arming state, a stable single WindowServer
and no new WindowServer diagnostic report. Startup text or device presence
alone cannot pass. Failure records its evidence, disables the next GPU/display
attempt and requests bounded recovery. A subsequent unexpected boot closes
the consumed scope instead of initializing again.

## Preparation evidence and status

The retained observer regression and new single-stage/admission/frame tests
passed **41 CPU methods**. They cover one-use transitions, stale or incomplete
prior evidence, exact watchdog ACK identity, output/publication failures,
restarted WindowServer, absent frame progress and recovery/expiry. These CPU
tests do not run GPU commands. A fresh root-owned packet verifies **417 inputs**,
and its actual launchd preparation role passed. The current four helper hashes
also match default source commit `5805c05bed6cf0ce1e3fc28f8d088f6e5e296993`'s
validation record.

At this public source checkpoint the trial is prepared but **not yet armed or
dispatched**. Exclusive private arming/reboot receipts and the actual next-boot
result must be read before reporting dispatch, desktop success or recovery.
The new authorization does not reopen any old packet.

Rollback is to preserve/restore the empty original GPU-off marker, remove the
original M2 marker and only the specific `phxfb-boot` display variable, then
verify a firmware-display boot if recovery was required. No driver replacement
is necessary. Raw logs, crash reports, identities and diagnostic archives remain
private; no binary publication is added.

## Consumed trial result: original startup requested fallback

The exclusive receipts and actual startup/kernel logs were read back on
2026-11-15. The single ordinary restart was dispatched successfully and
independently verified. Its native-desktop boot began at **18:29:35 +08:00**.
The observer recorded that original startup crossed its off-marker gate and
restored GPU-off while removing persistent display arming. There is no
desktop-complete, Metal-exit or trial-success receipt.

The original startup log reported `PhxAMDFB on the panel: 1`. Kernel logs also
show the native panel publication. All **17** fresh firmware load records have
zero transport and firmware statuses. However, startup retained no successful
compute/graphics queue or adoption output, then reported a selector **113**
transport/size failure and `M2 failed (NMXAccel did not start)`. The unchanged
upstream `m2_fail` path explicitly requested a fallback reboot. The external
witness did **not** dispatch a managed recovery reboot. Its next-boot closed
receipt preserves the consumed state and prevents retry.

The fallback boot began at **18:31:05 +08:00**. Independent reads confirmed
original build 34, the target geometry and all four installed corrected-helper
hashes. The firmware framebuffer is present; PhxAMDFB, NMXAccel and
IOAccelerator are absent. One WindowServer has remained on this boot. GPU-off
is an empty file, the M2 marker and pending marker are absent, and the specific
display-arming variable is absent. No new WindowServer/panic/kernel diagnostic
report was found in the checked system diagnostic directories after trial
start. That absence is not a general proof that no transient fault occurred.

Thus this attempt **did not establish accelerated desktop operation**, and
hardware acceleration is **not active on the fallback boot**. This does not
invalidate the separate 17:51 headless boot's real GPU/Metal execution success;
those successful consumed receipts remain unchanged.

Only the consumed external witness was retired: its exact plist was archived,
launchd confirmed the job had already exited/unregistered, its processes were
absent, and its auto-start plist was removed. Original startup and the installed
helpers were rehashed and left unchanged. All historical receipts remain
private and intact. No new GPU call, Metal probe or reboot was dispatched
during readback or retirement. The default source branch remains
`upstream34/vram-layout-fix` at
`5805c05bed6cf0ce1e3fc28f8d088f6e5e296993`.

## Diagnostic correction prepared offline; not deployed

The exact first post-firmware failure remains **unknown**. Original `full.sh`
discarded both streams from `bringup5.sh`, and the former wrapper omitted the
actual IOKit return code and returned lengths. Selector 113 invokes
`claimAccel`, which refuses a GPU that is not ready; its visible failure can
therefore be downstream of incomplete initialization. The retained data cannot
distinguish a power/autoload failure from another early initializer exit, and
does not establish a new CoreDisplay failure.

The downstream isolated build-34 recipe now preserves initializer stderr,
keeps PSP-destroy errors and firmware-load errors out of stdout suppression or
filtering, and propagates the exact initializer exit status before any later
queue commands. Transport diagnostics now include the actual return code and
expected/returned counts and byte lengths. Admission, GPU-command order,
fail-closed behavior, watchdog policy and original kernel/ABI remain unchanged.

Fourteen focused ASan/UBSan and synthetic-shell methods passed. They include
the retained geometry/order checks, error-versus-short-output diagnostics,
early initializer error retention, and no later queue operations after failure
in either watchdog mode. Native x86_64 helper compilation, ad-hoc signing and
strict verification also passed. These tests never link real IOKit into the
fixture or run a GPU command. The diagnostic candidate is source-only: it has
not replaced the installed four files or the default source branch, and no
new desktop attempt is armed. A future separately bounded trial must record
its exact inputs and retain these diagnostics from startup; consumed intents
must not be replayed.

## New diagnostic trial prepared after owner continuation

The owner's subsequent continuation requests the next deployment/test step.
A new isolated packet has been prepared; the failed 18:29 trial remains closed.
Its current-boot admission verifies that the earlier successful headless result
is historical evidence, and that the later failed desktop boot has a distinct,
closed fallback boot. It does not incorrectly require the accelerator to be
active on that fallback boot.

Only the four diagnostic user files have now been installed, backed up and
independently read back. Original build 34, accelerator, firmware, plugin,
runtime and startup remain unchanged. The complete EFI manifest was checked
read-only and left unchanged/unmounted. OS remains macOS 26.7.2 / 25G332.
The diagnostic wrappers additionally retain the command input and returned
status for ABI/firmware refusal, so a failing SMU message can be identified.
The successful GPU-command order and fail-closed rules are unchanged.

Preflight initially refused new Python bytecode caches created by a prior
inspection command that omitted its no-bytecode option. Exact comparison
found **53 added cache files**, zero removed files and zero modifications to
pre-existing pinned files. Only those exact additions were archived privately,
the original manifests were restored and independently rechecked, and all
subsequent frozen-interpreter commands use `-B -I -S`. No immutable manifest
was weakened or rewritten to admit the additions. Preflight completed before
the four-user-file installation.

Fourteen helper methods, native x86_64 compilation/signature checks and
**42** observer methods passed. The observer tests include saving the failing
startup block and declining a competing recovery request when upstream has
already requested fallback. The fresh actual launchd preparation role passed
with **zero GPU calls**; its contract verifies **2087** pinned inputs, including
the frozen interpreter files. This observer still does not gate upstream's
first hardware I/O.

At this source checkpoint the four diagnostic files are installed, GPU-off is
present, display arming is absent and **no reboot has been dispatched**. The
new packet permits one ordinary reboot/native-desktop attempt, a 300-second
independent observation deadline, at most one unchanged Metal probe after
startup succeeds, and at most one managed recovery reboot. Original startup
watchdogs remain unchanged. A detected original fallback is recorded without
immediately dispatching another shutdown; the independent deadline may still
recover the same boot if original recovery does not happen. Subsequent boots
close a consumed attempt instead of retrying. Software timers do not guarantee
recovery from a hard hardware hang.

Arming/dispatch and next-boot receipts must be independently read before
claiming that this new reboot happened or acceleration passed. The default
source branch remains pinned at `5805c05bed6cf0ce1e3fc28f8d088f6e5e296993`;
these diagnostic files are from the downstream isolated recipe. Rollback
restores only the four exact saved user files with GPU-off present and native
display arming absent. The prior root packets and their receipts remain intact.

## Diagnostic trial consumed: initializer exited before queue setup

The newly prepared diagnostic trial was subsequently dispatched exactly once;
its independent root-scheduler readback passed. The desktop boot began at
**19:41:23 +08:00 on 2026-11-15**. PhxAMDFB took the panel, and all **17** fresh
firmware loads returned zero transport and firmware status. The retained
diagnostic now identifies an earlier failure: `bringup5.sh` exited with status
**1**, and `full.sh` explicitly stopped before GPU queue initialization.
The following selector 113 refusal returned `0xe00002d8`; this does not locate
the earlier failing shell command. Original startup then reported that NMXAccel
did not start and requested its own fallback restart. The external witness did
not request managed recovery. No desktop-complete, Metal-exit or trial-success
receipt exists. The original restart occurred before the witness saved its final
failure block; the completed startup log was separately read back privately.

The fallback boot began at **19:42:55 +08:00**. Exact original build 34 and the
installed diagnostic stack passed readback. The firmware framebuffer is present;
PhxAMDFB, NMXAccel and IOAccelerator are absent. One WindowServer is running.
GPU-off is empty, and M2/pending markers and the specific display-arming variable
are absent. This boot has **no active hardware acceleration**. The consumed
scope's closed receipt prevents retry. Its idle, unregistered external witness
plist was archived and removed after verifying that its processes were absent;
original startup and all installed helpers stayed unchanged during retirement.
The successful 17:51 headless GPU/Metal evidence remains historical and intact.

## Narrow shell correction and fresh preparation

Offline stubs reproduce a real strict-shell regression in both scripts:
`killall shutdown` returning 1 for no matching process causes an otherwise
successful script to exit silently. This is consistent with the retained
status-1 failure but does **not** prove which command failed on that live boot.
The correction accepts only exit 1 with the exact C-locale no-process diagnostic.
Permission, empty, mixed and other errors remain terminal and are reported.
The inherited ERR trap also reports the initializer's failing line and status.
GPU-command order, metadata/ABI admission and watchdog arming are unchanged.

Nineteen downstream methods and **20** actual default-entrypoint methods pass,
including ASan/UBSan, both cancellation sites, nested initializer-to-queue order,
and terminal genuine cancellation errors. The five original CPU executables
also pass; external-firmware-dependent cases remain skipped. Native x86_64
helper builds and strict signatures pass. Both binaries have the exact same
hashes as the previously installed diagnostic binaries. These checks execute
no GPU work and do not establish desktop acceleration.

The broader downstream `make test` is **not fully green**: its separate,
unchanged `test_wait_seq` failed the 500-microsecond short-wait assertion;
a targeted rerun passed that case but failed the extended-wait sleep-count
assertion. These scheduler-sensitive CPU checks are outside the original34
helper path and were not modified or suppressed. This does not change the
passing original five-executable or focused helper/observer results above.

The default branch `upstream34/vram-layout-fix` now contains the same correction
and retained diagnostics at `90bb06f6f9255cb5a16cc5eb87e78032566b2000`;
its non-force remote update and independent unauthenticated SHA readback passed.
Its complete `src/`, `install/` and licence trees still match upstream build 34.
The branch name, public visibility, `main` and upstream history are preserved.

Under the owner's continuing deployment/test request, a distinct new packet
has now replaced **only two shell files**, with exact old-file backups and
independent installed readback. Helper binaries, original kernel, accelerator,
runtime, firmware, plugin and startup remain unchanged. EFI was verified
read-only and left unchanged/unmounted. The new actual launchd preparation
role passed with **zero GPU calls**, **42** CPU observer methods and **2087**
pinned inputs. OS remains macOS 26.7.2 / 25G332.

At this source checkpoint GPU-off is present, display is unarmed, and the new
test has **not** dispatched a reboot. It permits one native-desktop boot, one
unchanged Metal probe after startup evidence succeeds, a 300-second independent
observation deadline and at most one managed recovery restart. Original startup
watchdogs remain active. A detected original fallback does not immediately
dispatch competing recovery, and later boots close the consumed scope. There
is no automatic retry. Software timers cannot guarantee recovery from a hard
hardware hang. Rollback restores only the two backed-up scripts with GPU-off
present and display arming absent. Actual dispatch/next-boot receipts must be
read before claiming a reboot or acceleration result.

## Corrected observer trial dispatched once

The fresh external-observer packet from source checkpoint
`2fb9af0cafee446a9fae6402592cb3cb00672a4a` was armed once on
2026-11-15. Independent readback confirmed one root-owned restart scheduler,
all **2079** input pins, exact loaded build 34 and the one-shot display flags.
The scheduler estimates **21:09:16 +08:00**; this is a scheduled time, not an
observed next boot. No GPU initialization ran in the preparation boot.
Normal restart dispatches remaining are **zero** and this packet must not
be replayed. Installed driver, runtime and startup bytes remain unchanged.

The corrected observer requires original build 34's boolean armed readback
**1**, saves both frame samples before checking them, and retains all other
desktop, frame-progress, WindowServer and real Metal execution requirements.
One desktop attempt, one unchanged Metal probe, a 300-second observation limit
and at most one managed recovery remain the limits. Actual boot-bound receipts
must be read before claiming accelerated desktop success.

## Corrected armed-readback trial: startup completed, observer lost freshness

The actual native-panel boot began at **21:09:44 +08:00 on 2026-11-15**.
Original startup again produced correct compute/graphics GPU-written values,
successful queue adoptions and accelerator claim. It armed/released the panel,
completed its WindowServer monitor with PID unchanged in the retained startup
record, reported **666** panel transactions and wrote `done 21:11:32`. These
records alone do not establish the independent desktop acceptance conditions.

The external observer retained startup only through the arming line, then
reported `no complete original startup before observation limit`. Its one managed
recovery returned to a firmware-display boot at **21:14:35 +08:00**. No Metal
probe or final frame pair ran in this attempt. Exact build 34 and all installed
pins passed postboot readback; runtime consumer access still passed **18/18**.
PhxAMDFB, NMXAccel and IOAccelerator are absent on the fallback boot. GPU-off is
empty; M2/pending markers and the specific display variable are absent. Hardware
acceleration is currently inactive. The exited external witness was archived
and retired; its receipts remain consumed. The exact generated all-apps list
was archived and rolled back to the original apps-only list.

Private unified logs were filtered to the actual trial boot identity, time
interval and expected processes. At **21:10:10** `timed` recorded a successful
forward `settimeofday` adjustment of approximately **4.676 seconds**, followed
by a small correction in the other direction. The observer incorrectly
re-read `kern.boottime` on every poll: the moving cutoff could pass the fixed
startup header and discard the entire block, including its later completion.
Replaying the exact completed block against the first saved boot-time snapshot
returns a candidate; advancing that boundary four seconds reproduces rejection.
The historical per-poll cutoff values were not saved, so no unrecorded exact
post-adjustment cutoff is claimed. Raw logs and identities remain private.

`tools/upstream34_layout/startup_evidence.py` now captures one integer boot-time
boundary before polling. A fresh observer uses that same reader for every poll
and verifies the boot identity, while preserving stale-log refusal, original
startup checks, all frame/WindowServer gates, real Metal verification and bounded
recovery. This changes only external evidence collection; installed driver,
helper, plugin, runtime, firmware and startup bytes remain unchanged.

A distinct startup-clock packet passed its actual launchd preparation role with
**2080** pinned inputs, **67** observer/access/evidence CPU methods and no GPU
calls. The integrated target also passed **19** original helper methods under
its retained sanitizer checks. Existing unrelated scheduler-sensitive downstream
`make test` failures remain documented above; they were not suppressed. An early
preparation read-only gate refused a concurrently running synthetic helper from
the CPU suite; after that suite ended, preparation passed. No mutation occurred
before that refusal. Exact original34, all installed bytes, runtime consumer
access, and the complete read-only EFI manifest passed. At this checkpoint
GPU-off is present, display is unarmed and **no new reboot has been requested**.
The fresh packet retains one ordinary desktop boot, at most one unchanged Metal
probe, the 300-second limit and at most one managed recovery, with no retry.

## Fixed-cutoff observer dispatched once

Source checkpoint `c64cc4a5d8ed446b8575668f9a7ed30a0fb14100` was independently
verified on the public downstream remote before this fresh packet was armed.
Readback confirmed one root-owned restart scheduler, all **2080** fixed inputs,
exact original build 34, corrected helpers and one-shot native-display flags.
The scheduler estimates **21:35:03 +08:00 on 2026-11-15**. This is a scheduled
time; actual next-boot and desktop/Metal results remain pending. Normal restart
dispatches remaining are **zero**, and this consumed packet must not be replayed.
The same one-attempt, one-probe, 300-second observation and bounded-recovery
limits remain in force. No initialization occurred in the preparation boot.

## Fixed-cutoff trial passed independent desktop and GPU verification

The native-panel startup on **2026-11-15** logged its header at **21:35:33
+08:00** and completed at **21:37:15**. Its initial boot-time snapshot was
**21:35:29**; later `kern.boottime` readback was **21:35:31** for the same
privately verified boot identity. The fixed reader retained its original
boundary throughout, and the complete startup record remained visible.
Original compute/graphics outputs, queue adoptions and accelerator claim passed.

The unchanged Metal probe exited **0** with an AMD device, a completed command
and matching GPU-written output. Independent frame samples approximately
**10.286 seconds** apart increased from **717 to 740**. Both retained armed
readback 1, AGDC 1, IOP 1 and hold 0. The same single WindowServer remained
present, and its diagnostic-report set did not change. Native PhxAMDFB, NMXAccel
and IOAccelerator were present; the firmware framebuffer was absent. The
desktop-complete and trial-success receipts agree and were independently bound
to the actual trial boot. Acceptance completed at **21:37:30 +08:00**. No
managed recovery was requested.

A separate readback at **21:48:46 +08:00** verified exact original build 34,
image/geometry and all **2080** pinned inputs before retiring the idle external
witness. Native framebuffer and accelerator were still active, the same
WindowServer remained, the live present counter had reached **2156**, no new
WindowServer report was found, and runtime consumer reads still passed **18/18**.
Only the exact already-exited observer LaunchDaemon was archived and removed.
Original startup, helpers and installed driver/runtime bytes were unchanged.
This verification submitted no new GPU work, ran no additional Metal probe and
requested no reboot.

This establishes **one real accelerated native-desktop trial on this machine**,
not general application compatibility, performance, recovery or long-term
stability. The project remains experimental. GPU-off is retained for the next
boot, M2/pending markers and the specific persistent display variable are
absent, and the consumed packet cannot retry. Current-session acceleration
remains active; a subsequent boot is deliberately not persistently armed.
