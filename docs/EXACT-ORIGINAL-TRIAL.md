# Exact-original startup and desktop trial

Preparation snapshot, 2026-11-15: **the owner explicitly accepted the known
reference-layout risk and requested an entirely original startup and desktop
reboot test. Postboot results remain pending.** This is a new operation; the
[earlier guarded attempt](UPSTREAM-DESKTOP-ACTIVATION.md) remains consumed.

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

Eighteen CPU-only methods exercise the actual observer's phase admission,
candidate-output refusal, stale-log rejection, exclusive receipts, off/arming
restoration, deadline closure and ambiguous shutdown handling. The fake process
tests execute no real shutdown or GPU command. The independent Metal verifier
compiles but has not executed during preparation. A metadata-parser error in
the first staging read was inspected before retry: no trial packet/job or
activation marker had been created; empty IORegistry output is now covered.

The root-owned packet pins **1,696 inputs**, including **1,656 frozen interpreter
files**. Its witness LaunchDaemon was loaded once in the preparation boot and
completed the unarmed role, leaving GPU-off state intact. Installed original
files are unchanged. The [sanitized preparation record](
validation/exact-original-trial-20261115.json) contains no raw metadata, private
paths, image identities, firmware or binaries. Actual boot outcomes are recorded
separately in private root-owned receipts and must be read before reporting success.

Before arming, rollback is to keep the off marker, retain absent display flags,
unload/remove only the scoped external witness job and preserve its packet.
After arming or failure, read the intent and boot receipts first; never repeat an
ambiguous shutdown or initialization. Restore off/arming state through the scoped
recovery, then verify the resulting boot. No driver reinstall, EFI write,
partition change, NVRAM reset or security weakening is part of this trial.
