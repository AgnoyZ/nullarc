# Build34 R3 staged completion event wait

## NullMoth reference

The review pins `nullmoth/nvidia-macos-driver` at
`87e524ab36f12d17c04626d6cf7fc3bde1cc63e4`. The
[NVK patch](https://github.com/nullmoth/nvidia-macos-driver/blob/87e524ab36f12d17c04626d6cf7fc3bde1cc63e4/nvk/nvk-macos.patch)
registers one RM graphics non-stall event per device on a dedicated connection,
and frees the RM registration before closing that connection. The graphics
event is broader than an exact submission: NVK checks the pending channels'
slots, generations and semaphore values independently. It reads the event
count before rechecking those targets. The kernel
[event handler](https://github.com/nullmoth/nvidia-macos-driver/blob/87e524ab36f12d17c04626d6cf7fc3bde1cc63e4/kexts/NVRM/NVRM.cpp)
increases the connection counter on delivery, then wakes sleepers. Selector 6
uses a compare, enrollment and post-enrollment recheck, with a global sleeper
cap and a timeout. NVK requests 2 ms on that path and falls back to polling
without a supported graphics event. Its wait-block policy defaults to event
waits in WindowServer and polling in ordinary apps. The
[RTX 5060 results](https://github.com/nullmoth/nvidia-macos-driver/blob/87e524ab36f12d17c04626d6cf7fc3bde1cc63e4/docs/EVENT-WAIT.md)
showed lower CPU time from app opt-in and higher elapsed latency in the short
compute workload. They do not predict 780M FPS or latency.

The NVRM source declares PolyForm Noncommercial 1.0.0, also the reference
repository's default. The NVK patch edits Mesa and the repository separately
provides Mesa notices. This stage implements the ordering independently and
copies no source, binaries, selector, interrupt routing or hardware policy.

## Build34 experiment

Only the offline transform changes: the pinned exact receipt's wait can
snapshot a queue-specific notification counter before observing its fence.
The provider compares the same counter under `gpuLock` before atomically
enrolling with a backend that drops the lock while sleeping. If notification
arrived between observation and enrollment, it rechecks the fence without
sleeping. The client lock is released before sleep. The existing authenticated
ticket and wait pin remain held across retries. Only fence observation can
prove the requested sequence completed. Other-queue and old-generation
notifications cannot wake that wait as completion evidence, and the counter
cannot wrap into a previously observed value. No global retirement or resource
reclamation method is changed.

The sleep interval is at most 1 ms and clipped to the remainder of the
original monotonic request budget. Its absolute deadline must be anchored to
the timestamp passed to the backend. Timeout and wake both lead to another
observation. An early return with no notification change takes one polling
turn after that observation. If no backend is available, the existing 1 ms
polling path applies. Both paths can overshoot with scheduler delay; neither
promises a hard return deadline. Stop and queue invalidation wake affected
waiters; client close is noticed at recheck, within the requested slice plus
scheduling and lock delay if already asleep. A wake never grants device
visibility, successful completion, or queue drain.

## Verification and remaining work

The [offline runner](../tools/test_build34_exact_event_wait.py) exercises the actual staged receipt wait, event and
invalidation methods with CPU lock/clock/registration doubles. The tests
cover notification on both sides of enrollment, missing or spurious wakes,
old and wrong-queue notifications, two concurrent GFX waiters, stop and
generation invalidation, and GFX completion while earlier compute is pending.
It also checks the complete staged driver before and after with the pinned
SDK/KDK as nonloadable objects. ASan/UBSan and TSan each passed 481 checks;
five intentionally broken variants failed as expected. The 377 declared
imports and 172 production inputs are unchanged. See the
[sanitized results](validation/build34-r3-event-wait-offline-20261121.json).
Run sequentially at background priority:

```sh
nice -n 15 taskpolicy -b python3 -B tools/test_build34_exact_event_wait.py \
  --out build/build34-r3-event-wait-new-private --sdk "$KERNEL_SDK" --kdk "$KDK"
```

The event backend stays null. Before binding, establish the actual AMD event
source and deferred callback context, an admission limit for kernel sleepers,
the native atomic wait primitive and deadline conversion, and safe shutdown of
the source and all enrolled waiters. Prove BAR fence visibility and external
writer drain independently, then measure real wait/latency and FPS along with
dual-queue correctness and sustained desktop stability. No installation, GPU
submission or restart was performed. Rollback is to omit the offline transform.

## Follow-up: public IOKit sleep and AMD EOP routing

Linux v6.12 (`adc218676eef25575469234709c2d87185ca223a`),
[`gfx_v11_0_ring_emit_fence` and `gfx_v11_0_eop_irq`](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/gfx_v11_0.c#L5685),
separate the `RELEASE_MEM` writeback and interrupt controls. The handler
identifies a tagged MES queue through `src_data[0]` and the MES queue-ID
table; otherwise it decodes the IV ring ID and dispatches by CP engine and
pipe (also checking the compute queue). Linux's
[`amdgpu_ih_process`](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/amdgpu_ih.c#L208)
orders the write pointer against the 32-byte interrupt vectors and advances
the consumer pointer. The
[`ih_v6_0` implementation](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/ih_v6_0.c#L434)
handles overwrite, so a vector stream is not assumed complete. No Linux code,
register programming, or driver binaries are included in this MIT stage.

Build34 maps two `map_legacy_kq` queues; the adoption record provides ring,
writeback, doorbell and fence information, but no IH source or vector
ownership. Its fence packet requests no interrupt and has no MES queue tag.
The host has not established which CP EOP vectors are delivered for these
queues, that an IH consumer owns the ring across transitions, or that the
event orders the device's fence write to a CPU read through BAR0. A doorbell,
software generation, boot marker, or guessed IV cannot establish those facts.

The [separate offline transform](../tools/build34_exact_event_iokit.py) adds
unbound `IOLockSleepDeadline` and wake-all helpers. The sleep uses the original
monotonic sample plus the remaining slice, rejects expired, zero-tick or
overflowing deadlines, and uses `THREAD_ABORTSAFE`. The staged park counts
admitted sleepers under the GPU lock, including threads reacquiring it,
and caps them at 32 per service across both queues. A refusal re-observes
the target before polling. The return from the sleep primitive is never
completion evidence. Public XNU's
[`IOLocks.cpp`](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/iokit/Kernel/IOLocks.cpp#L90)
documents the underlying mutex sleep and wake path. At macOS 26.7.2
(`25G332`), static SDK/KDK checks accept exactly three additional imports
from the existing IOKit and Mach interfaces. No implementation from XNU
was copied.

ASan/UBSan and TSan each passed the original 481 checks and 113 additional
ones; four deliberately defective variants failed. The complete driver
compiled only to nonloadable objects (377 to 380 imports); all 172 production
inputs are unchanged. See the
[sanitized results](validation/build34-r3-event-iokit-offline-20261121.json).

```sh
nice -n 15 taskpolicy -b python3 -B tools/test_build34_exact_event_iokit.py \
  --out build/build34-r3-event-iokit-new-private --sdk "$KERNEL_SDK" --kdk "$KDK"
```

The source and ops pointer remain unbound. Matching exports establish static
availability, not live kernel enrollment or unload safety. The consumer's
ownership, deferred IRQ delivery and teardown, fence visibility, native
protocol, and GPU performance/stability acceptance remain open. No IRQ,
device packet, installed artifact, or runtime setting was changed.

## Passive PCI descriptor observation

On November 21, 2026, macOS 26.7.2 (`25G332`), the
[passive collector](../tools/build34_pci_irq_observation.py) matched the
PhxBringup build34 registry service to the direct PCI provider `1002:1900`.
Both provider snapshots contained two cached controller/specifier pairs,
one naming the PCI messaged interrupt controller and one other. Matching
entry identities and descriptor values were checked in memory around the
service read; only counts and fixed classifications were retained. Build34
here is the registry property, not loaded-image hash verification. The
[sanitized record](validation/build34-r3-pci-irq-observation-20261121.json)
retains the limits of this evidence.

Use bounded `ioreg -a` property snapshots. Apple's public
[`IOPCIDevice::getProperty`](https://github.com/apple-oss-distributions/IOPCIFamily/blob/4822b27a36e2de70e231ecf2bf3021384fab6ec2/IOPCIDevice.cpp#L1834)
calls the lazy interrupt resolver on named interrupt-property access. The
collector does not request a named property or `getInterruptType`.
Public XNU's
[`IORegistryEntry::serializeProperties`](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/iokit/Kernel/IORegistryEntry.cpp#L543)
serializes a copy of the property table. The source references describe the
API paths; they are not a claim that either source revision is the running
kernel or driver image. No device user client was opened. No configuration,
interrupt registration, packet, MMIO read/write, GPU or power operation was
requested by the collector.

```sh
python3 -B tests/test_build34_pci_irq_observation.py
python3 -B tools/build34_pci_irq_observation.py
```

The pairs show that descriptors are already published. They do not identify
which mode is active, who registered an ISR, the actual EOP vector for either
build34 queue, or whether a BAR0 read can see its fence after interrupt
delivery. Do not infer `MSI` versus `MSI-X` from the controller name. A later
finite route trial must correlate one protected GFX or Compute submission
with its actual EOP source and independently verified fence data, account
for overflow or dropped events, and prove exclusive IH ownership before
touching the ring or enabling interrupt generation. Keep the event backend
unbound until that evidence and its lifecycle checks are available.

The follow-up collector also checks `IOPCIMSIMode` and counts interrupt
accounting legend entries on the same PCI provider. Both fields are hints.
Public IOPCIFamily uses [one marker for both MSI and MSI-X](https://github.com/apple-oss-distributions/IOPCIFamily/blob/4822b27a36e2de70e231ecf2bf3021384fab6ec2/IOPCIMessagedInterruptController.cpp#L612-L638);
public XNU's [statistics removal](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/iokit/Kernel/IOService.cpp#L8524-L8564)
clears the live statistics pointer and keeps the reporter. An absent marker or
legend does not demonstrate that the device is idle or unclaimed. Two further
build34 reads on macOS 26.7.2 (`25G332`) matched: two descriptors, no MSI marker,
and zero matching legend entries. See the
[sanitized follow-up](validation/build34-r3-pci-irq-route-hints-20261121.json)
and the [proposed route trial](BUILD34-R3-IRQ-ROUTE-TRIAL.md).
