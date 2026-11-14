# Authorized single desktop retest

Target follow-up, 2026-11-15: **the one-shot desktop test ran and failed at its
first native queue selection; failure recovery and a subsequent firmware-
framebuffer boot were observed**. Both native readbacks were zero again. See
the [target result](validation/desktop-retest-target-20261115.json) and
[interpretation below](#target-result-and-recovery). This request is consumed.

Status at preparation, 2026-11-15: **prepared and CPU-checked; activation and
reboot not yet dispatched**. The owner requested a new desktop takeover boot
test while questioning whether collection caused the earlier dual-zero result.
This is a distinct authorization for one ordinary reboot and one attempt on
the verified new boot, with at most one failure/timeout recovery reboot. All
earlier requests remain consumed. See the [preparation record](
validation/desktop-retest-preparation-20261115.json).

## What the retained output establishes

Read-only inspection of the preceding [terminal VMID experiment](
DESKTOP-VMID-PREFLIGHT.md#terminal-vmid-control-result) found the following in
the native process's retained stderr, before summary parsing:

```text
requested=0x00000010 write-readback=0x00000000 readback=0x00000000
```

The retained native status is exit 75 with no timeout. Therefore summary
parsing did not turn nonzero values into this pair of zero values. This does
not exclude a native read/write-path defect or an effect of observation on the
target. The [source/CPU transport audit](REGISTER-TRANSPORT-AUDIT.md) also does
not establish the physical cause.

The new test exercises the actual guarded desktop startup path. It retains
the reviewed observer, so it is not a collector-free comparison and cannot
by itself isolate observer interference. It preserves native stdout, stderr,
status and stage records independently of the final summary.

## Prepared delivery and execution boundary

The new private packet has its own authorization digest, empty target scope
and preparation-boot exclusion. It reuses the reviewed startup adapters,
trusted Python runtime, installed drivers and firmware. Its separate signed
native helper contains the current detailed selector diagnostics and the
desktop initialization implementation. Ten native source dependencies match
the checked repository source. No upstream code or additional binaries are
published by this record.

Preparation verified 39 execution pins, eight recovery pins, the complete
trusted interpreter closure and eight installed-input hashes. Five historical
receipt sets still contain exactly 188, 29, 97, 187 and 190 matching files.
The installed startup and off marker were unchanged at preparation; the new
scope was empty, display arming absent and no GPU command or reboot requested.
The actual metadata probe reported macOS 26.7.2 / build 25G332, bring-up build
39, no PhxAMDFB or NMXAccel, and one firmware framebuffer.

Activation is restricted to the new packet's startup selection, removal of the
checked off marker, the existing one-shot display flag and one scheduled
ordinary reboot. It neither replaces drivers nor changes EFI, kernel
collections, partitions, BIOS or security settings. Before dispatch, the
executor requires the same preparation boot, synchronized clean downstream
checkout, unchanged pinned inputs and historical receipts, absent competing
startup/helper/reboot processes, and the expected safe service state. An
exclusive activation claim and separate reboot claim prevent automatic replay.

On the new boot, an independent recovery worker owns a 240-second deadline
before metadata discovery. The coordinator takes over that original deadline
only after its own recovery worker acknowledges readiness. Firmware/power and
desktop initialization retain their original checks. A failed selection stops
before claim, display, release or monitoring. Successful prerequisites alone
permit those later stages and the 90-second monitor; they do not establish a
usable accelerated desktop. Initial and later recovery share one exclusive
reboot claim, with no persistent M2 marker or automatic rearming.

The recovery worker disarms the next boot and requests the single allowed
fallback reboot on finite failure or deadline expiry. It cannot guarantee
recovery from a kernel or bus hard hang. Spawned processes and scheduled
reboots require independent metadata readback; neither preparation nor a
dispatch receipt proves a reboot occurred or the desktop worked.

## Validation and rollback

The focused CPU/fake checks pass 120 methods: desktop startup 30, allocation
coordinator 47, native desktop handoff 31, register transport seven and private
arming admission contracts five. The last five check the admission predicate,
including missing, extra, false and non-boolean facts; they do not exercise
the complete activation mutation/rollback sequence. An empty test discovery
was excluded. The full suite was not rerun. The new hardware path has not run
at the creation of this record.

Before ordinary-reboot dispatch, a mutation failure attempts to restore the
exact previous startup and off-marker bytes and remove only this test's
one-shot flag, then records verification. If reboot dispatch may have happened,
preserve the evidence and read actual state before any action; never retry
automatically. On target failure, use the existing independent disarm/recovery
path. Preserve every consumed scope and native result. A later source rollback
uses a normal new commit. This record claims neither a collector root cause,
a desktop fix nor acceleration.

## Subsequent activation readback

The authorized one-shot activation was subsequently dispatched once. Independent
readback at **2026-11-15 00:46:48 +08:00** verified the exact root-owned startup,
new packet/runtime, one-shot display flag, absent off/persistent markers and
one matching root shutdown scheduler. Its approximate restart time is
**2026-11-15 00:48:39 +08:00**. The other six installed inputs and all five
historical receipt sets were unchanged. The new scope remained empty and no
GPU command had run on the preparation boot.

This is verified scheduling and arming, not an observed reboot or a desktop
result. Durable private continuation records were saved before the scheduled
restart. After the stable boot identity changes, inspect this new scope and
its native/recovery receipts first; never re-arm or replay the packet.

## Target result and recovery

The scheduled ordinary reboot completed, and the installed one-shot startup
automatically admitted the new request. Preparation, test and current boot
identities are all distinct. The target remained on macOS 26.7.2 / build 25G332
with bring-up build 39. The observer's one baseline snapshot returned zero,
with `observed=0`, before firmware/power and desktop initialization. No failure
snapshot was recorded. The baseline hash, observer-ready receipt and all four
hash-linked coordinator journal records were independently checked.

Firmware/power returned zero. The new detailed native helper then stopped at
the first selection in the actual `desktop-init` path:

```text
ME=3 pipe=1 queue=0 VMID=0
requested=0x0000000d write-readback=0x00000000 readback=0x00000000
native exit=75; timed_out=false
```

The initializer adapter returned 74 to the coordinator because its native
command failed. No later claim, display, release or monitor stage started.
The single selector trace and helper invocation counts come from retained
native/process records; they are not independent hardware request tracing.
Failure does not demonstrate a checked service close or successful GPU work.

The early metadata recovery worker handed off to the coordinator's armed
worker. The coordinator requested recovery after the finite initialization
failure, and recovery was recorded about 0.69 seconds after the failed stage
returned, about 6.60 seconds after boot-entry admission. The 240-second
watchdog did not expire, so this does not exercise hardware deadline recovery.
Disarming completed, and the one recorded fallback reboot command returned
zero. Two display cleanup writes reported unknown OIDs; AGDC and framebuffer-
hold writes returned zero. The display cleanup process returning zero must not
be interpreted as all four writes succeeding.

Independent postboot readback observed the subsequent boot, one firmware
framebuffer, no PhxAMDFB or accelerator instance, the exact restored off marker,
absent one-shot/persistent markers, and no remaining startup, native helper or
reboot job. The 188 new scope receipts were stable and their private copies
matched. All five earlier receipt sets, 39 execution pins, eight recovery pins,
the complete trusted runtime and six other installed inputs were unchanged.
The selected startup file also remained exact. No driver, collection or startup
change, extra GPU operation, rearming or reboot was performed during readback.

This actual desktop path reproduced dual-zero native readback on a separate
boot. Together with the earlier VMID result, it excludes summary parsing as
the source of those recorded zeros. It does not exclude a native access-path
defect, observer interference or an initialization prerequisite. The baseline
collector ran before initialization, and the observer remained active; this
was not a collector-free comparison. No physical cause, accelerated desktop
or fix is established.

Preserve this consumed request, its boot/stage/reboot claims and all receipts.
Do not re-arm or replay it. Continue with offline analysis; any further target
experiment needs its own reviewed authorization and fresh-boot/recovery plan.
The preparation's 120 passing CPU methods are historical and were not rerun
for this documentation-only result record. Result checks reparsed the retained
native statuses, trace, journal chain and recovery receipts without GPU calls.

The subsequent [collector causality review](COLLECTOR-CAUSALITY-REVIEW.md)
verifies that reported dual-zero behavior already appears in build-34 records,
before the allocation-snapshot mechanism existed, and adds integrated CPU
reader/client-lifecycle coverage. It retains the old CLI reply-count caveat
and the absence of a collector-free physical control. It does not change this
terminal result or authorize another target operation.
