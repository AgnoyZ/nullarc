# Build34 R3 interrupt route trial design

Status: startup observation passed in the
[corrected authorized trial](BUILD34-PCI-IRQ-TRIAL.md#corrected-trial-passed-startup-observation).
The exact build34 image produced `both-message-enables-clear`; this did not
identify an active PCI interrupt mode, an ISR or an IH ring consumer. The
ordinary restart grant is spent. Ownership and drain are the next gate.
The build34 AMD framebuffer's VBL callback is driven by `vblFire` on a timer;
it is not a CP end-of-pipe (EOP) interrupt source. The installed daily path
continues to use its existing waits. No event backend is bound.

## Admission gates, in order

1. **Observe PCI configuration without registration.** The
   [start observer](BUILD34-PCI-IRQ-CONFIG.md) passed its passive trial. It uses
   the already retained `IOPCIDevice` on the existing start-time config-read
   path, before this driver's power registration and enable writes; it does
   not power up the device. It brackets the message-control reads with D0 and
   identity checks and publishes only an allowed start-time classification.
   The exact loaded image and provider child matched the independent sample.
   Startup enable, mask state, later configuration and interrupt delivery are
   separate facts.
   Do not read a named interrupt property, call
   `getInterruptType`, or construct a provider-backed event source. Public XNU
   [registers the ISR during source initialization](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/iokit/Kernel/IOInterruptEventSource.cpp#L72-L144);
   the public PCI [registration path can enable MSI/MSI-X](https://github.com/apple-oss-distributions/IOPCIFamily/blob/4822b27a36e2de70e231ecf2bf3021384fab6ec2/IOPCIMessagedInterruptController.cpp#L98-L134)
   before the source itself is enabled. These public revisions describe the
   APIs and are not loaded-image attestations.
2. **Prove ownership separately.** Before changing any PCI interrupt or IH
   state, demonstrate exclusive control from the first device writer, including
   all potential display, other engine, firmware and host consumers of the
   chosen IH ring. Establish producer/consumer identities, storage and
   doorbell ownership, enable/mask semantics, DMA visibility, and a documented
   stop/drain boundary for inherited writers. Include other queues on the
   selected CP pipe: per-queue vector identity does not mean per-queue masking.
   Verify how unrelated events will be preserved. Even zero configuration
   enable bits, equal IH pointers, an empty queue or a successful bootstrap
   sentinel are insufficient. If an owner cannot provide a verified handoff
   or the existing display path cannot be preserved, stop before registration.
   This gate remains open after the [ownership review](#ih-ownership-review).
   See also [initial queue ownership](BUILD34-INITIAL-QUEUE-OWNERSHIP.md).
3. **Correlate one queue at a time.** After both gates pass and an exact
   isolated build is authorized, use private allocations outside daily
   queue, fence and IH storage. Admit one service, one route and one
   generation per queue for all four windows. Use a fresh fence seed and
   target for each case, without resetting the ring or the other queue's
   fence. With routing armed, run a no-interrupt control and one otherwise
   identical EOP-requesting submission on GFX, then the same pair on
   Compute. Check each window's completion before starting the next. Close
   and tear down the one-shot route once, after the last window or on the
   first failure. These are four submissions with one outstanding at a
   time and no retry. Seal finite observation and teardown deadlines before enabling it,
   independently of the GPU progress path. Keep desktop takeover off in the
   route trial and use an independent recovery path. Match the actual IH
   client/source and engine/pipe/queue against the admitted legacy queue, a
   current-window delivery and an independently validated fence/payload read.
   Check that the other queue does not advance. Reject a missing control
   writeback, a matched EOP in the no-interrupt control, ambiguous attribution,
   loss or overflow, or a mismatch between writeback, payload and the trial's
   queue. One CPU interrupt may cover multiple IH entries; it is not a
   submission ID. Linux v6.12 distinguishes the
   [legacy and MES-tagged paths](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/gfx_v11_0.c#L6231-L6259),
   [orders IH pointer and vector reads](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/amdgpu_ih.c#L208-L231),
   and handles [ring overwrite](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/ih_v6_0.c#L434-L471).
   These are reference semantics. No Linux or Apple implementation code is
   copied. Visibility of IH entries does not imply visibility through BAR0.

## Offline route and first-read evidence

Both build34 bootstrap queues request `map_legacy_kq` with pipe and queue 0.
The bootstrap selects ME 0 for GFX and ME 1 for Compute in its HQD checks.
The six-word adoption interface carries a software queue index and buffer
locations. Trial admission still needs an independent match to the live HQDs
and their storage. See [`mesboot.c`](../tools/phxctl/mesboot.c#L342) and
[`adoptQueue`](../src/phxbringup/PhxBringup.cpp#L739).

Linux v6.12 registers one CP EOP source for both queues. Its client ID is
`0x14` (`GRBM_CP`) and its source ID is `0xB5` (`CP_EOP_INTERRUPT`). For an
untagged legacy entry, ring ID bits 0–1 carry pipe, 2–3 carry ME and 4–6 carry
queue. The expected low seven bits are `0x00` for GFX `(0, 0, 0)` and `0x04`
for Compute `(1, 0, 0)`. MES-tagged entries use a different identity path.
These are source-derived expectations for the planned AMD trial. See the
pinned [client ID](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/include/soc15_ih_clientid.h#L100),
[source ID](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/include/ivsrcid/gfx/irqsrcs_gfx_11_0_0.h#L56),
[registration](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/gfx_v11_0.c#L1584)
and [legacy decoder](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/gfx_v11_0.c#L6232).

The original multi-route diagnostic checker requires GFX control/EOP
followed by Compute control/EOP, each with a fresh route epoch, active queue
generation and distinct seed and target fence values. It remains for
historical records, not admission of the current one-shot workloop. Each
pair must have the same independently derived
recipe hash, normalizing the intentional interrupt choice, per-case storage
and fresh sentinel values. The record must contain the pre-submit sample,
the first independent fence/payload read after the matching EOP (a scheduled
sample for the no-interrupt control), and a closing sample before the sealed
observation deadline. Both reads must show the exact target and correct
payload with the other queue's fence unchanged. A stale first read fails
even if a later read matches. Each sampled interval and the vector must
carry the same service, route and both queue identities. The checker rejects
unexpected traffic, loss, overflow, faults, and overlapping or overdue case
cleanup. See [`build34_r3_eop_evidence.py`](../tools/build34_r3_eop_evidence.py).

The collector must independently attest boot and loaded image, ownership and
drain, actual BAR0 reads and effective access ordering, fresh payload/guards,
complete IH delivery through cleanup, recipe identity, and the captured
monotonic times. Its first-read record must preserve a failed first attempt.
Record terminal errors privately and use the existing first-failure stop
rule. The pure checker returns record consistency with `hardware_attested`
set to false. `make test` runs 11 synthetic checks. Rollback is to omit the
checker and its test entry. See the
[offline record](validation/build34-r3-eop-evidence-offline-20261122.json).

### Private raw IH capture validation

The optional `check_ih_capture` path derives the vector fields instead of
trusting caller-classified client/source/ring and MES fields. It accepts
private snapshots of the primary ring in the same four cases. It reads
exactly 32 captured little-endian bytes per entry and derives the header
from dword 0 and the MES tag from dword 4, bit 24. See the pinned Linux
[vector layout](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/amdgpu_ih.c#L250-L286),
[tag](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/amdgpu_mes_ctx.h#L116-L117)
and [GFX11 dispatch](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/gfx_v11_0.c#L6231-L6259).
This uses reference field meanings, not imported driver code.

Each case has 2–64 bounded batches with independent times and the same
service, route and two queue identities. The first is empty before submit;
the last is empty during cleanup. Each batch must account for every entry
implied by the byte cursor movement, including ring wrap. It brackets the
captured bytes with equal producer writeback samples and rejects overflow,
full, may-overflow, unknown bits, skipped consumer cursors, unrelated entries
and extra EOPs. Unlike the Linux recovery path, the validator cannot clear
overflow or salvage a partially overwritten window. The first independent
BAR0 fence/payload gate is unchanged. Only this path reports
`raw_ih_capture_checked`; both report `hardware_attested: false`.
The [initial offline capture record](validation/build34-r3-ih-capture-offline-20261122.json)
covers 18 synthetic tests before the packet check below.

An empty ring or stable writeback bracket can neither detect every unobserved
overwrite nor prove device ordering. A separate collector must prove actual
matching storage, generation and ordered visibility, complete capture without
pointer reset or flag clear, and an independent first BAR0 read. This stage
does not provide a runtime collector, MMIO read, registration, doorbell write
or GPU submission. It returns no vector bytes, addresses or cursor values.
Rollback is to omit the raw capture entry and its tests; the normalized
checker remains unchanged.

### Bind the captured fence packet to each observation

The raw path also requires the exact eight little-endian `RELEASE_MEM`
dwords captured at submission and both actual BAR0 fence offsets in every
sample. It keeps build34's cache/event word and 64-bit data mode fixed.
The control must request no interrupt, and the EOP case must request an
interrupt after write confirmation. Both require an untagged legacy context.
The packet's full MC address must equal the admitted BAR0 MC base plus the
sampled fence offset, and its low dword must match the fresh trial target
with a zero high dword for this narrow trial. The peer slot cannot alias it;
both slots must be aligned, fit within the aperture and stay fixed within
each case. A matching `recipe_sha256` alone cannot satisfy these checks.

The pinned Linux [fence emitter](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/gfx_v11_0.c#L5685-L5717)
uses those two interrupt selections. AMD PAL's
[MIT-licensed packet layout](https://github.com/GPUOpen-Drivers/pal/blob/29f5d822b6d450dc669a47d2fa709c0b76dfff33/src/core/hw/gfxip/gfx9/chip/gfx9_plus_merged_f32_me_pm4_packets.h#L2636-L2733)
identifies the latter as interrupt after write confirmation. These field
meanings were reviewed without importing source or binaries. Confirmation
does not attest CPU-visible BAR0 data, payload coherence or a safe IH handoff.
The collector still has to prove the aperture, the captured packet and both
independent read addresses, ordered first-read visibility and the enclosing
ownership interval. It must keep raw bytes and addresses private. The
normalized checker remains useful for fixtures and cannot replace raw
capture. The follow-up [offline record](validation/build34-r3-eop-release-mem-offline-20261123.json)
covers 23 synthetic tests. Rollback is to omit the packet validation
follow-up; no live configuration was changed.

### One-shot route and actual ISR trace

The staged workloop does not rearm on the same service. The offline
`check_one_shot_irq_delivery` path instead binds four windows to one
independently supplied service/route/both-generations identity, IRQ source
token, initial IH cursor, and BAR0 aperture and fence slots. The two controls
must contain no ISR dispatches; each EOP arm must contain exactly one. The
collector must record the ISR entry, not synthesize it from a copied vector,
poll, or workloop wake. The dispatches must be consecutively numbered from
one on the registered source and ordered after the submit and no later than
the copy starts. The complete copy still precedes the first independent fence
read. The checked terminal counter must match these dispatches, on the same
source and route, after the last window but before the presealed deadline.
Supply it from separately verified CPU teardown, not by counting records.

Each next window starts at the previous IH bookend cursor, including across
ring wrap. Its packet and reads must match the two admitted slots, even if
substituted packet bytes and samples agree with each other. The peer fence
must be unchanged across windows except when that queue itself completes a
case. `close_ns` and `cleanup_end_ns` describe sealing an observation window,
not detaching the physical route. The collector must preserve the complete
trace across windows and teardown, including rejected or failed reads.

Passing the offline checker is not hardware attestation. Equal cursors,
matching ISR counts and timestamps cannot prove no unobserved DMA, exclusive
IH ownership, the true loaded images or cache visibility. Keep source tokens,
cursors, packet words and raw trace data private. No collection code, IRQ
provider or device access was added. See the original
[sanitized ISR test record](validation/build34-r3-one-shot-irq-evidence-offline-20261123.json).

### Check complete first-read BAR0 data

The one-shot path no longer takes a caller-supplied `payload_ok` or a
low-dword-only fence read. Each pre-submit, first-read and closing sample
records both raw eight-byte little-endian fence reads and the raw guarded
payload from its sealed BAR0 offset. The current fence starts with a nonzero
high dword and a fresh low-dword seed. The first and closing reads must
match the packet's full 64-bit result, including the zero high dword. The
peer's full 64-bit value must stay unchanged, also across windows when it
is not the submitting queue.

The guarded range covers all 256 payload dwords and two 64-byte guards. It
must fit the admitted aperture and not overlap either fence. Seal all four
seed/result byte pairs and both guard patterns before enabling the route.
The cases cannot reuse a seed or result, and every result dword must differ
from its seed. Verify the entire seeded region before submit and the entire
expected result and unchanged guards in both post-submit samples. Retain a
failed first read even if the closing sample succeeds. The historical
multi-route entries keep their old format; they cannot substitute for this
one-shot check.

The same-generation samples still need an independent collector that
establishes the effective BAR0 mapping/cache policy, the actual access order
and the absence of other writes to these test slots. A matching snapshot
does not prove that the GPU wrote it or that a sample was really the first
read. The [attempt trace below](#bind-every-bar0-read-attempt) replaces
combined sample records and checks the declared order and access identity.
The [NBIO/HDP source audit](BUILD34-FENCE-READER.md#interrupt-transport-does-not-synchronize-bar0)
does not support inserting a new flush or dummy read after the event to make
the first fence read pass. Keep any later diagnostic read separate.
`raw_bar0_samples_checked` reports only record consistency. Retain raw
data privately. This change installs no collector and does not prove cache
coherence, IH ownership or DMA drain. See the
[sanitized offline result](validation/build34-r3-one-shot-bar0-evidence-offline-20261123.json).

### Bind the submitted payload and fence commands

The old one-shot path could accept a matching caller-supplied recipe digest
and detached `RELEASE_MEM` packet without any record of the payload-writing
command. The current path takes `submitted_pm4` instead. For this isolated
route trial, require exactly one little-endian 256-dword `WRITE_DATA`
followed by the eight-dword `RELEASE_MEM`, with no extra commands inside the
recorded work. The [`WRITE_DATA` reference](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/soc15d.h)
and [build34's existing confirmed memory-write packet](../tools/phxctl/mesboot.c#L669)
are source references, not hardware qualification for this proposed recipe.
Require the sequential memory destination with write confirmation, the
admitted payload address past the leading guard, and every sealed result
dword in order. Decode the fence packet from that same stream and check its
cache/event control, destination, data and interrupt choice as before.
The two arms now have the same checked command shape, varying only the sealed
challenge data, fence target and requested interrupt. The older multi-route
formats are unchanged and remain historical checks.

A future collector must bind the bytes to the actual published work on the
admitted queue and generation, not a recipe buffer or concatenated excerpts
from different submissions. It must independently verify the queue context,
the effective GPU destination and that no extra work intervenes before the
fence. Any setup, ring publication or padding outside the two packets must
also be accounted for and kept equivalent. `submitted_pm4_checked` proves
only trace consistency. This is not a Mesa payload recipe or an authorization
to write hardware, and there is still no live collector. Rollback is to omit
this checker revision; do not use the older format to qualify the live route.
See the [sanitized offline result](validation/build34-r3-one-shot-pm4-evidence-offline-20261123.json).

### Bind every BAR0 read attempt

Matching bytes in a merged snapshot did not distinguish a fence-first read
from a payload-first read, a replacement mapping or a successful retry.
The one-shot checker now requires three ordered attempts per sample: the
submitting queue's full fence first, the peer fence next, then the complete
guarded payload. Each records byte offset, start and end times, result status,
raw bytes, both queue generations, service/route identity, and the token of the
one mapping and accessor sealed for all four windows. The EOP copy must
finish before the first fence attempt begins, not just before a sample ends.

Number attempts on entry, before touching BAR0, starting at one for the
trial. Count failures, short reads and accesses outside a sample as well.
Seal the counter after closing and draining the read side, and collect it
independently of the exported sample list. The checker requires consecutive
ordinals and a final count of 36, with no failed, extra or overlapping read.
A guarded-range attempt may include multiple loads; the admitted accessor
must not hide retries, dummy reads, remapping or cache operations inside an
attempt. Any failed first read remains a failed trial even if later diagnostics
see the target. Retain the old merged format only as historical evidence.

`bar0_attempt_trace_checked` proves consistency against a supplied trace and
counter, not that instrumentation covers the real accesses, that the cache
attributes are effective or that a GPU write was visible. There is no live
collector. Keep raw bytes, offsets and tokens private. Rollback is to omit
this offline checker revision; the prior format cannot qualify a new trial.
See the [sanitized offline result](validation/build34-r3-one-shot-bar0-attempts-offline-20261123.json).

## IH ownership review

On November 21, 2026, two passive registry snapshots of the running PCI
observer boot agreed on the direct children of the Radeon `1002:1900`
provider. `PhxBringup`, `PhxAMDFB` and `NMXAccel` each matched a direct
service query; two other direct children remained unattributed. The queries
did not identify all services, firmware or platform components that can
program the IH or consume its entries. The software VBL timer and startup
PCI message-enable result do not close that gap. No new MMIO, interrupt
registration, power action or GPU submission was performed for this review.

The pinned Linux v6.12 reference selects
[IH v6 for OSSSYS 6.0.1](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/amdgpu_discovery.c#L1917-L1921).
Its [APU path allocates the primary hardware ring only](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/ih_v6_0.c#L571-L614);
the separately initialized software ring is not an alternate hardware ring.
Do not presume an available private second hardware ring for EOP. The same
driver registers [VM fault sources](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/gmc_v11_0.c#L773-L784).
An EOP-only filter does not justify taking the primary ring or discarding
other vectors. These are Linux reference paths; they do not establish
routing on the running macOS stack.

The same [ring setup](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/ih_v6_0.c#L215-L235)
sets distinct address-space modes for bus and GPU virtual addresses, enables
writeback, requests snooping and clears relaxed ordering. Its APU sizing path
selects GPU virtual addresses when PSP loads firmware; the associated comment
ties the bus-address alternative to a PSP boot-loader permission. This makes
firmware provenance and translation part of the handoff, not a configuration
detail that a new BAR mapping can bypass. It is not evidence that the PSP is
currently programming the ring on this host, nor a definition of when old
ring or writeback writes have drained.

Linux's [ring disable clears the pointers](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/ih_v6_0.c#L127-L189);
the [IRQ shutdown](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/ih_v6_0.c#L412-L421)
uses a fixed delay. Its [IH idle and soft-reset callbacks](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/ih_v6_0.c#L661-L677)
are placeholders. None supplies a checked acknowledgment that old ring and
writeback DMA can no longer land. The public
[`IH_STATUS` field definitions](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/include/asic_reg/oss/osssys_6_0_0_sh_mask.h#L310-L350)
name input, buffer and memory-write idle and cleanup-pending states. They
do not specify read side effects, the required power/mapping state or when
the fields prove that already issued writes have finished.

Linux's [IH checkpoint wait](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/amdgpu_ih.c#L171-L197)
is a consumer progress check. It samples the producer cursor, orders the
read of the checkpoint vector, then waits for a processed timestamp or for
the consumer to catch the producer. It does not stop the producer or attest
that no already issued or later device write can land. The staged ingress
likewise tracks only accepted CPU copies; do not use its cursor or ordinal
as a device drain receipt.

An admitted handoff must account for the predecessor, every source that can
still target the selected ring and every consumer that can acknowledge it.
Bind the ring, pointer writeback storage, address translation and doorbell
range to that same ownership interval. Require a documented way to stop new
entries and confirm completion of old storage writes before clearing pointers,
moving mappings or freeing memory. Separately drain CPU callbacks and preserve
unrelated event delivery. If using a verified reset instead, establish its
coverage and prevent the platform or firmware from rearming inherited state
before the new owner takes control. Until either boundary is proven, keep IH
reads out of the startup observer and leave the live IRQ path untouched. Any
later diagnostic read needs its own verified address, side-effect and
power/mapping contract; a diagnostic idle sample cannot authorize a handoff.
The [target reset review](BUILD34-INITIAL-QUEUE-OWNERSHIP.md#reset-paths-on-the-target)
found no advertised standard PCIe FLR in cached metadata and no verified
GPU-only bridge reset or platform handoff. The current exposed ACPI table
review located explicit reset objects on other devices and resources; it
did not establish a GPU reset or complete runtime namespace. The ownership
and drain gate remains open. The [MP1 unload review](BUILD34-INITIAL-QUEUE-OWNERSHIP.md#pmfw-unload-is-not-an-ih-handoff)
also rules out inferring IH drain from the Linux GC power-down rationale or
from a successful higher-level finalizer result.

### Follow-up: ring-full handling and translated DMA drain

Linux sets [`RB_FULL_DRAIN_ENABLE`](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/ih_v6_0.c#L265-L306)
when configuring `ih1`, alongside disabling overflow on that ring.
The APU path does not allocate `ih1`. This is an initialization control,
not a checked stop or DMA completion result for the primary ring.
The [forced pointer update path](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/ih_v6_0.c#L77-L116)
configures when a self interrupt reports a write pointer. It does not
return a completed-write acknowledgment.

Account for three distinct paths. The IH produces vectors in the ring and
can DMA its write pointer to a separately programmed address; the CPU
consumer [stores the read-pointer shadow and rings the doorbell](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/ih_v6_0.c#L508-L524).
The [allocation reference](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/amdgpu_ih.c#L41-L101)
can put the ring and pointer shadows in different allocations. A receipt
for only the ring pages would not cover a separately mapped writeback
page or an already issued consumer doorbell. AMD specifies a conditional
[host-mapper page-reuse boundary](BUILD34-SYSTEM-WRITEBACK.md#amd-invalidation-completion-is-a-mapping-boundary)
for translated DMA. It supplies neither producer stop nor doorbell
ownership, and its coverage of either inherited IH write destination is
unverified here. This source review admits no live operation.

### Follow-up: direct child attribution

On November 22, two targeted IOKit IOService-plane enumerations matched the
same five direct children of the Radeon provider. The two previously
unattributed entries were `AMDSupport` and `PhxDeviceControl`. The check used
only the PCI vendor/device properties, class lookups and in-memory identity
comparison. It did not resolve an interrupt index or open a device client.

- `AMDSupport` matches the installed Apple bundle's PCI display-class
  personality for AMD devices. The loaded bundle and the x86_64 KDK reference
  for `25G332` reported the same image identifier. That reference contains
  interrupt registration imports and `AtiFbInterruptManager` entry points
  for installing and stopping PCI interrupts. This is a concrete competing
  path to account for. A loaded bundle and attached support service do not
  show that its interrupt manager was instantiated, that it accesses this
  APU's IH ring, or that it has released its old writes.
- [`PhxDeviceControl`](../src/phxaccel/accel/phxagdc.cpp#L43) is the
  PhxAccel display-capability shim. It attaches on the same PCI provider and
  calls the inherited `AppleGraphicsDeviceControl` start path. Its own vendor
  replies are not an EOP consumer; the subclass's visible code does not prove
  what its base class or another client has registered.

The [sanitized record](validation/build34-r3-ih-child-attribution-20261122.json)
separates registry facts from static capability. Resolving the AMDSupport
path now requires ring and PCI callback ownership for this particular
provider, not a bundle-wide search for interrupt methods. It still requires
the predecessor's documented or verified stop/drain boundary; neither a
negative instance lookup nor a dormant host callback excludes old firmware or
device writes. Leave the existing services attached and preserve the display
path while investigating. No candidate, device operation or rollback action
was needed for this read-only review.

### Follow-up: Apple manager stop is not an IH handoff

On November 22, 2026, two targeted `IOServiceMatching` samples found one
`AMDSupport`, one `PhxBringup` and no published `ATIController` service.
Two `ioclasscount` samples independently reported one `AMDSupport` and zero
instances counted for both `ATIController` and `AtiFbInterruptManager`.
The current loaded-kext inventory contained `AMDSupport` but no separate
Apple AMD controller kext. These are current snapshots, not history or a
complete census of other interrupt consumers and hardware writers.

The loaded AMDSupport and IOPCIFamily identifiers match the x86_64 references
from the OS-build-matching KDK. Offline disassembly, relocation and vtable
checks distinguish the two Apple paths:

- The direct `AMDSupport` service's `start` calls the `IOService` base start,
  then sets a version property and registers the service. That method does
  not instantiate `AtiFbInterruptManager`. The manager's separate `init`
  takes an `ATIController` and obtains its register service, interrupt list
  and PCI device. Its PCI installation path attempts registration and
  enablement on that device; the mere presence of the code in the loaded
  bundle is not evidence those calls occurred on the Radeon.
- `ATIController::stop` calls `AtiFbInterruptManager::stopInterrupts` when
  it has a manager. The reviewed manager method clears its software flags,
  disables and unregisters its remembered PCI source when present, and
  invalidates that source field. It does not check IH producer idle, ring
  writeback completion or memory visibility. The public
  [IOPCIFamily unregister reference](https://github.com/apple-oss-distributions/IOPCIFamily/blob/4822b27a36e2de70e231ecf2bf3021384fab6ec2/IOPCIMessagedInterruptController.cpp#L135-L172)
  describes PCI vector/MSI teardown, not AMD on-chip DMA drain. Neither
  method is an admitted stop/drain endpoint for build34.

This narrows the live competing-owner hypothesis without establishing that
no predecessor programmed the hardware. Do not detach the support service
or invoke the Apple stop path to simulate a handoff. The next evidence needed
is coverage of the firmware/platform writers and any other consumers, with
a device-side stop and completed-write boundary for the selected storage.
No device client, PCI interrupt query, MMIO access, registration or power
action was requested. See the
[sanitized record](validation/build34-r3-ih-apple-stop-review-20261122.json).

## Stop, rollback and later acceptance

Keep callbacks bounded: the interrupt context only signals deferred work.
Use the proved device ordering for the deferred reader. Missing wake or
overflow must never be used as completion evidence or to advance the global
retirement watermark. Publish only classified outcomes and counts. Do not
publish vector words, capability offsets/values, interrupt indices, addresses
or registry IDs.

The pinned XNU [interrupt-source unregistration and disable paths](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/iokit/Kernel/IOInterruptEventSource.cpp#L190-L269)
call the provider without retaining its unregister or disable result. The
public IOPCIFamily [MSI registration path](https://github.com/apple-oss-distributions/IOPCIFamily/blob/4822b27a36e2de70e231ecf2bf3021384fab6ec2/IOPCIMessagedInterruptController.cpp#L98-L134)
also enables device MSI during registration. Consequently the wrapper's
disabled state or destruction is not a checked receipt for an admitted PCI
vector. Resolve ownership before constructing a provider-backed source. For
cleanup, establish a checked unregister and source-specific no-future-callback
boundary separately from queued work, the admitted deferred worker and AMD
device DMA. The source-only worker gate verifies only admitted CPU copies;
it cannot cover an interrupt or work item that has not tried to enter it.

### Checked PCI teardown still needs a separate deadline

The macOS `26.7.2 (25G332)` x86_64 KDK IOPCIFamily reference matches the
loaded bundle identifier and image UUID, and its file hash matches the
previously pinned KPI provider. Matching metadata does not attest the live
Radeon controller dispatch or loaded executable bytes. Comparing five
controller routine bodies and their relevant virtual dispatch entries with
the pinned Apple source gives these constraints:

- [Disable](https://github.com/apple-oss-distributions/IOPCIFamily/blob/4822b27a36e2de70e231ecf2bf3021384fab6ec2/IOPCIMessagedInterruptController.cpp#L216-L231)
  sets a software flag and, outside interrupt context, can spin on the
  vector-active flag without a timeout. In interrupt context it skips that
  wait. The [dispatcher](https://github.com/apple-oss-distributions/IOPCIFamily/blob/4822b27a36e2de70e231ecf2bf3021384fab6ec2/IOPCIMessagedInterruptController.cpp#L848-L872)
  checks registration and hardware-disable state before calling the target;
  the software flag alone is not an admitted no-future-callback boundary.
- [Unregister](https://github.com/apple-oss-distributions/IOPCIFamily/blob/4822b27a36e2de70e231ecf2bf3021384fab6ec2/IOPCIMessagedInterruptController.cpp#L137-L173)
  can enter that same disable path while holding the vector lock. It also
  returns success if the vector was already unregistered. The
  [hardware mask helper](https://github.com/apple-oss-distributions/IOPCIFamily/blob/4822b27a36e2de70e231ecf2bf3021384fab6ec2/IOPCIMessagedInterruptController.cpp#L899-L910)
  conditionally writes the MSI-X table and has no checked readback there.
  None of these operations checks the AMD IH writeback or DMA engine.
- [Enable can synchronously call the target](https://github.com/apple-oss-distributions/IOPCIFamily/blob/4822b27a36e2de70e231ecf2bf3021384fab6ec2/IOPCIMessagedInterruptController.cpp#L912-L928)
  when the controller marked an interrupt pending while hard disabled. The
  future adapter must pin and initialize callback context before operations
  that can dispatch. The ISR may signal deferred work only; delivery still
  needs the independently admitted route, not merely a successful enable.

Do not invoke this disable/unregister path in the ISR or synchronously under
the GPU, client or deferred-work locks. A separately retained cleanup worker
can keep an unbounded provider call out of the synchronous stop path, but an
observer reaching its deadline does not cancel a stuck provider call or
prove the target can be freed. Keep callback context and affected resources
pinned when provider completion, queued work or device drain is uncertain.
Require an independently bounded, source-specific teardown contract before
admitting the live trial. See the
[sanitized static review](validation/build34-r3-ih-pci-teardown-review-20261123.json).

Stop on the first timeout, contradictory sample, unexpected traffic, GPU
fault, ownership loss or power/queue transition. Close trial admission first,
mask only the source the trial owns and stop generation, then verify pending
interrupt/worker/waiter drain and device DMA quiescence before detaching or
restoring state. Do not hold the GPU lock while blocking on callback drain.
If ownership or drain is uncertain, keep affected memory and objects pinned
and refuse rearm; use only the separately sealed rollback. It must preserve
the accepted build34/R2a artifacts, boot recovery and daily settings and
remain operable when the test desktop or driver is unavailable. No automatic
repeat boot or resident monitoring is part of this design.

A passing route trial would only establish the event route for the tested
queues and configuration. Native receipt/Mesa integration, trusted fence
visibility, and healthy resource reclamation still gate a paired candidate.
Then require the real overlapping GFX/Compute case (GFX returns while earlier
Compute is pending and the global watermark stays put), measured wait/CPU/FPS,
and sustained desktop stability before accepting R3.
