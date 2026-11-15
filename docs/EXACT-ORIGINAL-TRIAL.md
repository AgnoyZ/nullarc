# Exact-original startup and desktop trial

Execution assessed, 2026-11-15: **the original startup completed, but the external
Metal probe ran before the original driver's delayed Metal publication and
triggered recovery. A subsequent GPU-off boot is independently verified.**
This packet is consumed. Neither Metal execution nor desktop takeover was
verified. The [earlier guarded attempt](UPSTREAM-DESKTOP-ACTIVATION.md) also
remains consumed; the [publication-aware follow-up](EXACT-ORIGINAL-READINESS.md)
uses a separate packet.

## Original bytes and accepted risk

A fresh full-file comparison verifies the installed upstream v0.4.0-alpha
helpers, startup scripts/plist, firmware, PhxAccel bundle and Metal plugin/runtime
against the retained release package. The loaded PhxBringup image matches the
release and reports build 34. The system is x86_64 macOS **26.7.2 / 25G332**.
The original package and installed components were already reviewed during
[replacement](UPSTREAM-REPLACEMENT.md); no replacement install, component import,
binary upload or EFI change is needed for this request.

The reference physical base and VRAM extent in the original startup/helper
disagree with this target's reported layout. The owner explicitly accepted the
reported risk of out-of-carve-out mappings, memory corruption or a hang before
this new operation was prepared. This acceptance does not establish compatibility
or GPU execution. The experiment uses the original initialization helpers and
their unmodified checks, ordering and watchdog behavior. The private target-layout
initialization candidates from the earlier operation are not used or installed.

## Two-stage boot sequence

The arming operation makes only the upstream `--windowserver` marker changes:
create the M2 marker and remove the GPU-off marker, leaving the initial one-shot
display flag absent. It does not invoke GPU initialization in the preparation
boot. The first requested ordinary reboot runs the unchanged upstream startup
LaunchDaemon and its original initialization sequence.

An external witness observes this startup; it never invokes an initialization
helper or changes the original script's MMIO/firmware sequence. It restores the
off marker only after observing that the original script has passed its initial
off check, preventing later replay without interrupting the current script.
Printed compute/graphics tokens, claim success and `done` are only candidate
evidence. Loaded original image identities must still match, and a separate
native Metal compute verifier must return its GPU-written result from a buffer
initialized to zero. This verifier uses the public Metal API and is not an
initialization helper, replacement driver or modified runtime.

Only that successful first-stage receipt, plus the one-shot flag written by
the original startup itself, permits the witness to request the second ordinary
reboot. That boot runs the unchanged original desktop startup. It must finish
with PhxAMDFB, an original accelerator image, another successful Metal result,
increasing presented-frame counters, a stable WindowServer PID and no new
WindowServer diagnostic report during observation. A boot or service name alone
cannot satisfy these criteria.

The desktop test is deliberately one-shot. After the second startup has crossed
its off check, the witness restores the off marker and removes persistent and
one-shot rearming. The current successful desktop session may remain active;
the next boot falls back to GPU-off instead of silently repeating the experiment.
An unexpected subsequent boot is recorded and closed without a new initializer.

## Independent recovery and limits

There are at most two witness-managed ordinary reboot requests and one additional
witness-managed recovery request. The original helpers retain their own delayed
watchdogs, broad shutdown cancellation and failure recovery. These original
requests are not falsely counted as witness-managed requests. The witness uses
exclusive intent receipts before spawning shutdown, regular output files rather
than captured pipes, and an explicit unknown/no-retry result on caller timeout.

A separate process acknowledges a 180-second initial-reboot observation timer
before arming. If the preparation boot never changes, the timer restores GPU-off
state and closes the unused trial without retrying shutdown. Each observed trial
boot also gets a separate 300-second deadline process. Because the upstream
LaunchDaemon is unchanged, the witness cannot guarantee that its deadline ACK
precedes the original startup's first hardware command. A kernel or bus hard
hang can prevent all software observation and recovery.

Failure restores GPU-off state, removes display arming, preserves the original
pending marker/evidence and permits the single managed recovery request. Any
later boot records fallback state without replaying the attempt. Consumed old
experiments and installation allowances remain closed.

## Preparation evidence and rollback

Twenty CPU-only methods exercise the actual observer's phase admission,
candidate-output refusal, stale-log rejection, exclusive receipts, off/arming
restoration, deadline closure and ambiguous shutdown handling. The fake process
tests execute no real shutdown or GPU command. The independent Metal verifier
compiled without executing during preparation. A metadata-parser error in
the first staging read was inspected before retry: no trial packet/job or
activation marker had been created; empty IORegistry output is now covered.

The first pre-arming management check also stopped before creating any arming
intent: completed one-shot jobs were absent from the launchd service list. Fresh
readback verified no disabled override, no pending attempt and intact GPU-off
state. A versioned preparation-only revision now accepts that idle/absent state
while still rejecting a running or disabled job. Its two additional CPU checks
pass. The old contract and sources are retained; no GPU initializer, hardware
guard, installed original file or reboot allowance was changed by this revision.

The root-owned packet pins **1,696 inputs**, including **1,656 frozen interpreter
files**. Its witness LaunchDaemon was loaded once in the preparation boot and
completed the unarmed role, leaving GPU-off state intact. Installed original
files are unchanged. The [sanitized preparation record](
validation/exact-original-trial-20261115.json) contains no raw metadata, private
paths, image identities, firmware or binaries. Actual boot outcomes are recorded
separately in private root-owned receipts and must be read before reporting success.

## Actual execution and premature Metal observation

Arming was consumed at **15:10:02 +08:00**, followed by exactly one initial
managed reboot request. Its caller returned zero without timing out. The new
boot began at **15:11:27 +08:00**. The unchanged upstream startup reported the
expected compute and graphics scratch/buffer values, both queue adoptions and
claim returned zero, the next-boot display flag was armed, and startup printed
`done` at **15:11:37 +08:00**. Original loaded-image and installed-input checks
passed before the external Metal probe. These startup results are candidate
evidence, not an independent Metal workload result.

The external probe printed `No AMD Metal device`, with no success output. Its
source returns before compiling or submitting a shader in that case. The
observer recorded failure at **15:11:43 +08:00** and did not authorize the second
desktop boot. This is not the earlier GART refusal or a dual-zero readback.

The pinned original `PHX_FB` accelerator source withholds `MetalPluginName`
until display arming or a 60-second headless callback. Historical kernel logs
from this exact trial confirm that the name was withheld and the 60-second
timer started at **15:11:35 +08:00**. The callback-disabling boot argument was
absent. The probe therefore ran before that normal publication interval; its
failure does not establish that the original Metal stack would still fail
after publication. This is an external observer readiness defect. Actual
post-publication Metal execution remains untested by this consumed packet.

## Verified recovery and closure

The observer restored GPU-off state, removed persistent and one-shot display
arming, and consumed its single managed recovery intent at **15:11:43 +08:00**.
The machine rebooted before a recovery-caller return receipt was written; that
exit status is unobserved and was not retried. An independent read verified
the subsequent boot beginning at **15:12:08 +08:00** and its recovery-postboot
receipt. The current startup log says `kill switch present: nothing to do`.

GPU-off is present; M2, one-shot and pending markers are absent. The original
bring-up image still matches, and all 1,696 pinned inputs matched before
retiring the consumed external witness. PhxAccel, PhxAMDFB and NMXAccel are
absent; an IONDRVFramebuffer and one WindowServer remain. No initializer,
observer or shutdown/reboot scheduler remains running. No second desktop boot
was requested. Initialization and recovery allowances for this packet are zero.

For the separate readiness-aware follow-up, only this inactive external
witness plist was archived with a matching hash and removed from its active
LaunchDaemon path. Its receipts and original contract are preserved. That
intentional retirement changes the old plist location; it does not change a
driver or permit replaying the consumed packet.

Before arming, rollback is to keep the off marker, retain absent display flags,
unload/remove only the scoped external witness job and preserve its packet.
After arming or failure, read the intent and boot receipts first; never repeat an
ambiguous shutdown or initialization. Restore off/arming state through the scoped
recovery, then verify the resulting boot. No driver reinstall, EFI write,
partition change, NVRAM reset or security weakening is part of this trial.
