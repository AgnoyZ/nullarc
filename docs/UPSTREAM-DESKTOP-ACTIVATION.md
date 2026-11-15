# Original-kernel desktop activation

Status, 2026-11-15: **a new, explicitly requested activation is prepared;
hardware execution and desktop takeover have not yet been attempted**.

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

The first phase retains the off marker and leaves persistent and one-shot
display arming absent. It permits one GPU initialization in the verified
original-kernel boot, which has not initialized the GPU since boot. It follows
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
No desktop flag has been armed by preparation.

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
keeps preparation distinct from execution. Sources, binaries, raw metadata and
logs remain private; no full-stack artifact was uploaded.

Before hardware execution, rollback simply means leaving the unexecuted packet
inactive. After a failed initialization, retain the recovery receipt and GPU-off
state, verify the subsequent boot, and do not replay the attempt. Do not weaken
security, alter EFI, reinstall the modified fork or turn a failed check into an
acceleration claim. Revert documentation with a new commit if necessary; that
does not reactivate a consumed operation.
