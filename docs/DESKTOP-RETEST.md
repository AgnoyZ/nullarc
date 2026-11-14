# Authorized single desktop retest

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
