# One original-build34 desktop acceleration reboot test

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
