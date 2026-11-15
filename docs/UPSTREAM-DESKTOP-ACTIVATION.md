# Original-kernel desktop activation

Status, 2026-11-15: **one original-kernel initialization was attempted and
stopped at the GART selector-readback guard; the subsequent GPU-off boot is
independently verified. Desktop takeover and hardware acceleration remain
unverified**.

The owner requested desktop takeover and hardware acceleration after the
[original-release replacement](UPSTREAM-REPLACEMENT.md) completed. This is a new
operation on upstream v0.4.0-alpha, with original PhxBringup build 34 loaded and
its image identity verified. The installation completion reboot and all older
downstream experiments remain consumed and closed.

## Target-layout prerequisite

A fresh read of the original driver's published metadata confirms that this
machine's system-physical framebuffer base and VRAM extent differ from the
reference constants in the release's helpers. The MC base matches. Removing the
off marker and running the release startup unchanged would therefore use
reference-machine addresses on a different layout. No such bypass was run.

There is no target-layout argument in the pinned release `mesboot` source at
`9dd76b604fca5e0125bd3caa5723df0f611ff27f`. A private helper candidate was built
from that exact upstream source, with the component's MIT/GPL choice and the
AMD header notices retained. The installed release kexts, plugin, runtime,
firmware, startup scripts and helpers remain unchanged.

The candidate substitutes the observed target addresses and aperture extent,
uses a zero, disjoint default page, and checks the live metadata before opening
the user client. It adds transport/shape, selector-readback and GPU-token refusal
checks before queue adoption; it does not remove a downstream refusal guard or
enable a reference-layout override. The accompanying coordinator derives the
PSP physical address from the original driver's published base rather than the
shell's fixed reference value. This is an experimental target-profile helper,
not a byte-identical upstream binary or a validated acceleration fix.

## Bounded activation sequence

The first phase retained the off marker and left persistent and one-shot
display arming absent. It permitted one GPU initialization in the verified
original-kernel boot, which had not initialized the GPU since boot. It followed
the original firmware/power, CP setup, GART and MES order. Queue adoption and
claim require completion evidence; a separate bounded Metal compute probe must
then return its GPU-written value. A driver name, a claim return or a printed
expected value alone cannot establish hardware execution.

An independent process must acknowledge its absolute 240-second deadline before
the first hardware command. Failure or timeout restores GPU-off state, removes
display arming and permits one recovery reboot, with no automatic retry. The
original shell watchdogs and their broad `killall shutdown` cancellation are not
run. The active startup files and EFI are not changed in this phase. A kernel or
bus hard hang can still prevent software recovery.

Only a successful first-phase receipt permits proceeding to the separately
recorded display phase under the owner's new request. It must verify original
PhxAMDFB/accelerator identities, initialization before releasing the display
hold, actual frame progress and the absence of a WindowServer failure loop.
No desktop flag was armed during this operation.

## Actual attempt and recovery

The initializer executed once in the verified original build-34 boot. The
independent watcher acknowledged its deadline before the first native command.
Thirty native CLI invocations ran in the recorded firmware/power, CP setup and
GART order. This counts process invocations, not MMIO operations or user-client
calls inside those processes. The firmware/SMU parser checks and three CP setup
readbacks passed; these are not GPU execution evidence.

The thirtieth invocation, `GART`, returned **75**, without a command timeout,
and printed `target profile refused: selector readback mismatch`. The refusal
originates in the native candidate, before the coordinator parses its output.
The guard checks the provider's immediate write reply and, only if that matches,
a separate register read. It did not log the requested value, selector ordinal
or either observed value. Consequently this attempt cannot be described as a
dual-zero result, nor can the exact failed VMID transition be inferred. The
coordinator did not invoke MES, compute/graphics, queue adoption/claim or the
Metal probe after this failure. The display phase was not entered.

The watcher restored the GPU-off state and called its single permitted delayed
recovery reboot. Its `capture_output=True` subprocess call timed out after
15 seconds and no return-code receipt was written. That is an ambiguous caller
result, not evidence that the reboot was not scheduled; no second reboot call
was made. An independent inspection verified a different boot beginning at
**2026-11-15 14:25:50 +08:00**, after the recovery request. This is consistent
with the requested delayed recovery; the shutdown caller's exit status remains
unobserved.

In this subsequent boot, macOS remains **26.7.2 / build 25G332**. The loaded
PhxBringup image still matches the original release and reports build 34. All
59 pinned input hashes match. The empty off marker is present; persistent,
one-shot and pending activation flags are absent. PhxAccel is not loaded,
PhxAMDFB and accelerator services are absent, and there is one firmware
framebuffer. The current boot's startup log says `kill switch present: nothing
to do`. No initializer, watcher or shutdown/reboot scheduler remains running.
EFI was not mounted or changed by these inspections. The consumed packet and
its evidence remain immutable; initialization and recovery allowances are zero.

## Offline diagnostic follow-up

Two private, uninstalled candidates address demonstrated evidence/recovery
limitations without changing the consumed packet or installed original stack:

- Selector diagnostics record the ordinal, requested value and immediate reply.
  They explicitly record `readback=not-attempted` if the immediate reply fails;
  they log the separate value only when that read actually occurs. They preserve
  the original short-circuit IO sequence and exit-75 refusal. Under ASan/UBSan,
  98 injected mismatch cases, 13 other refusal cases and one successful case
  have matching old/new fake IO traces and counts. The fake executables do not
  link IOKit. The new native candidate compiles/links but was not run.
- The recovery candidate uses exclusive regular files for shutdown output,
  records consumption before spawning, and preserves an explicit unknown/no-retry
  state on caller timeout. Fourteen CPU-only recovery/parser methods pass. A
  harmless Python descendant reproduces a captured-pipe timeout after its parent
  exits; the candidate observes the parent exit with direct output files. This
  supports an inherited-pipe explanation for the caller timeout, but does not
  prove the actual shutdown descendant's behavior. No real shutdown command was
  executed by these tests. Direct execution of the candidate worker is disabled.

These candidates improve future diagnosis and recovery accounting; neither
repairs or explains the physical selector failure. No new GPU experiment or
display arming was performed during this follow-up.

## Subsequent request for an entirely original test

The owner subsequently requested an entirely original stack, desktop takeover
and a reboot test. A fresh full-file comparison confirms that the active GPU
directory, helpers, firmware, accelerator bundle, Metal plugin/runtime and
startup plist already match the original release, apart from the deliberately
retained empty off marker. Neither private candidate is in an active path.
The loaded original bring-up identity is also reverified. Another replacement
installation is unnecessary.

The original installer's `--windowserver` option creates the persistent M2
marker. Its documented sequence first boots GPU initialization and, after a
successful startup, arms the next boot for desktop takeover. It does not promise
desktop takeover on the first boot from the current unarmed state. Both the
startup script and the original native helper still contain reference-machine
physical addresses and extents that disagree with the live target metadata;
the release helper offers no target-layout argument. An entirely unchanged
recipe would therefore program mappings outside the target's reported carve-out
and may corrupt memory or hang the machine. The earlier guarded candidate's
failure does not validate removing its checks and running those addresses.

At the pre-acceptance inspection, no new initialization, arming or reboot had
been dispatched for this subsequent request. The owner then explicitly accepted
the reported address-conflict risk. A [new exact-original trial](
EXACT-ORIGINAL-TRIAL.md) records that acceptance and its separate boot/recovery
limits. It does not reopen the failed guarded packet or validate the layout.

## Preparation checks and rollback

Seventeen CPU-only native cases pass under ASan/UBSan, using stub IOKit calls
with no IOKit imports in the test executable. They cover metadata refusal before
open, greeting/transport shape failures, selector mismatches, VRAM/doorbell
errors, target page-table endpoints, default-page zeroing and aperture bounds.
Eight separate recovery/parser cases check finite failure, deadline expiry,
single-dispatch recovery, no reboot on success, off/arming restoration and PSP
error refusal. These checks do not validate real MMIO, firmware or GPU execution.

The private root-owned packet pins 59 inputs and the existing frozen interpreter
closure. The [sanitized record](validation/upstream-desktop-activation-20261115.json)
distinguishes preparation, the failed execution, recovery, and the unexecuted
follow-up candidates. Sources, binaries, raw metadata and logs remain private;
no full-stack artifact was uploaded.

The attempted packet is consumed and must stay inactive. Retain the failure
and independent recovery evidence and the verified GPU-off state; do not replay
the attempt. The new offline candidates have not been installed. Do not weaken
security, alter EFI, reinstall the modified fork or turn a failed check into an
acceleration claim. Revert documentation with a new commit if necessary; that
does not reactivate a consumed operation.
