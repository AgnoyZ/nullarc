# Build34 R3 interrupt route trial design

Status: preparation only. There is no admitted trial image or runtime grant.
The [registry observation](BUILD34-EXACT-EVENT-WAIT.md#passive-pci-descriptor-observation)
did not identify an active PCI interrupt mode, an ISR, or an IH ring consumer.
The build34 AMD framebuffer's VBL callback is driven by `vblFire` on a timer;
it is not a CP end-of-pipe (EOP) interrupt source. The installed daily path
continues to use its existing waits. No event backend is bound.

## Admission gates, in order

1. **Observe PCI configuration without registration.** The
   [offline start observer](BUILD34-PCI-IRQ-CONFIG.md) is prepared. It uses
   the already retained `IOPCIDevice` on the existing start-time config-read
   path, before this driver's power registration and enable writes; it does
   not power up the device. It brackets the message-control reads with D0 and
   identity checks and publishes only an allowed start-time classification.
   Before a meaningful live observation, establish the exact image, provider
   power/config access semantics and sealed rollback scope. Startup enable,
   mask state, later configuration and interrupt delivery are separate facts.
   Do not read a named interrupt property, call
   `getInterruptType`, or construct a provider-backed event source. Public XNU
   [registers the ISR during source initialization](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/iokit/Kernel/IOInterruptEventSource.cpp#L72-L144);
   the public PCI [registration path can enable MSI/MSI-X](https://github.com/apple-oss-distributions/IOPCIFamily/blob/4822b27a36e2de70e231ecf2bf3021384fab6ec2/IOPCIMessagedInterruptController.cpp#L104-L123)
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
   See [initial queue ownership](BUILD34-INITIAL-QUEUE-OWNERSHIP.md).
3. **Correlate one queue at a time.** After both gates pass and an exact
   isolated build is authorized, use private allocations outside daily
   queue, fence and IH storage with a fresh queue epoch and writeback value
   for each case. With routing armed, first run one no-interrupt control and
   one otherwise identical EOP-requesting submission on GFX. Verify teardown
   before doing the same on Compute. These are the proposed four submissions,
   with one outstanding at a time and no retry on a failed case. Seal finite
   observation and cleanup deadlines in the trial before enabling it,
   independently of the GPU progress path. Keep desktop takeover off in the
   route trial and use an independent recovery path. Match the actual IH
   client/source and engine/pipe/queue against the admitted legacy queue, a
   current-window delivery and an independently validated fence/payload read.
   Check that the other queue does not advance. Reject a missing control
   writeback, a matched EOP in the no-interrupt control, ambiguous attribution,
   loss or overflow, or a mismatch between writeback, payload and the trial's
   queue. One CPU interrupt may cover multiple IH entries; it is not a
   submission ID. Linux v6.12 distinguishes the
   [legacy and MES-tagged paths](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/gfx_v11_0.c#L5800-L5850),
   [orders IH pointer and vector reads](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/amdgpu_ih.c#L193-L223),
   and handles [ring overwrite](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/ih_v6_0.c#L407-L435).
   These are reference semantics. No Linux or Apple implementation code is
   copied. Visibility of IH entries does not imply visibility through BAR0.

## Stop, rollback and later acceptance

Keep callbacks bounded: the interrupt context only signals deferred work.
Use the proved device ordering for the deferred reader. Missing wake or
overflow must never be used as completion evidence or to advance the global
retirement watermark. Publish only classified outcomes and counts. Do not
publish vector words, capability offsets/values, interrupt indices, addresses
or registry IDs.

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
