# Display-failure follow-up, 2026-11-13

The existing startup monitor completed its fallback to IONDRVFramebuffer after
the failed desktop takeover. Keep that working fallback: do not rearm M2,
replay initialization or reboot to repeat the failure. The six earlier real
Metal compute cases apply only to their original boot and installed mixed
stack. Desktop acceleration and the incorrect 42-inch physical display size
remain unresolved.

This follow-up is read-only with respect to installed drivers, libraries,
helpers, startup switches and EFI. Raw logs, crash identities, addresses and
private diagnostic sources/binaries remain local. The sanitized observations
are in [the follow-up record](validation/display-followup-target-20261113.json);
the original incident and constructor fix remain in
[the initial record](validation/display-postboot-target-20261113.json).

## What the logs do and do not establish

The failed-boot kernel log was filtered by all three of: the bounded incident
time window, kernel process image, and the boot identity from the private
crashes. This matters because the raw time-range query also returned records
outside that interval and from the following boot. The final 1,533 records
contain no observed handle-exhaustion, kernel-map-space-failure or driver GPU
fault/timeout messages. Missing messages do not exclude those causes. Current
fallback-boot handle counters are separate and cannot reconstruct the failed
desktop boot's counters.

The WindowServer process that later aborted in CoreDisplay logged queue
submission returning `VK_ERROR_DEVICE_LOST`. That value alone does not
identify a hardware hang. In the current pinned source:

1. `acd_kr_to_errno()` in `ac_darwin_kext.c` maps recognized IOKit refusals to
   negative errno values, usually without a log unless opt-in trace is set.
2. `acd_cmd_cs()` can fail during plan preparation, dependency readiness,
   native submission or signal attachment. A failure is not necessarily an
   executed GPU command.
3. `radv_amdgpu_cs_submit()` preserves several distinctions internally:
   exhausted `-ENOMEM` retries become host-memory failure; `-ECANCELED`,
   `-ENODATA` and `-ETIME` become device loss; other errno values such as
   `-EBUSY` become `VK_ERROR_UNKNOWN`.
4. The outer `radv_queue_submit()` converts any non-success submission result
   to queue/device loss to prevent replay after uncertain state.

The Vulkan `vkQueueSubmit` specification likewise allows device loss when
submission failure cannot preserve the required resource/synchronization
state; it is not a hardware-cause report. The exact pre-conversion native
refusal for this incident has not been recovered.

`IOAccelPhxNativeClient::doSubmit()` refuses submission while deferred
resources remain pending, and `PhxBringup::gpuSubmit()` has additional queue,
progress and VMID guards. These are possible refusal sites, not established
causes of this incident. Do not remove them, blindly retry submissions, raise
budgets or change resource lifetime based on the high-level error alone.

## Memory metadata on the working fallback boot

A fresh private diagnostic directly loaded the unchanged installed RADV,
selected the sole PCI `1002:1900` physical device and queried memory metadata.
It created a Vulkan instance but no `VkDevice`, command pool or explicit
device-memory allocation, and submitted no GPU work. One bounded invocation
completed successfully; the boot and startup marker state were unchanged.

The native ABI query reports per-client software limits of 256 MiB visible
VRAM, 1,536 MiB hidden VRAM and 512 MiB GTT. The independent RADV metadata
query reports these application heaps:

| Heap | Size | Device local | Reported budget | Query-process usage |
| --- | --- | --- | --- | --- |
| 0 | 256 MiB | no | 256 MiB | 0 |
| 1 | 512 MiB | yes | 512 MiB | 0 |

This is consistent with `radv_physical_device_init_mem_types()` in the
reviewed pinned source: for an APU without the unified-heap option, it combines
visible VRAM and GTT (768 MiB), exposes two thirds as device local and the
remaining third as GTT, and does not expose the hidden pool as a separate
discrete-GPU heap. This arithmetic explains the observed 512 MiB heap without
establishing exact installed source identity. It is not evidence that all
device-local allocations use physical VRAM, that 512 MiB was consumed, or
that a WindowServer allocation can actually succeed.

The query process was fresh. Its zero usage does not describe WindowServer,
all clients, or the earlier failed boot. Memory-budget metadata is an
implementation estimate for the querying process, not a physical-VRAM test.

## Source and acceptance boundaries

Three relevant Mesa files were retrieved at the locked commit, their Git
blob identities and sizes verified, and applicable patches applied in an
isolated private repository with explicit per-file apply receipts. The Darwin
adapter was separately reconstructed from the locked nine Cobalt and seven
Phoenix patches plus the native-only downstream patch. These are partial
source reconstructions for audit, not a full native build or installed binary
source proof. An embedded Mesa version string is not that proof either.

The cleanup-order fix at source commit
`4f35a609331752d5e2dcac24f8b878d32aa6f309` passed source CI. At this follow-up
checkpoint, native run `43370193766` was still compiling/testing on
`macos-15-intel`; native completion is not yet accepted. No diagnostic logging
change, allocator change, userspace replacement or new kernel candidate was
installed. The constructor fix makes an allocation-failure cleanup path safe;
it does not resolve the original allocation refusal or device loss.

Before another hardware test, finish native build review, establish candidate
provenance, and prepare a narrowly scoped way to retain the pre-conversion
submission error. Existing opt-in `RADV_DARWIN_TRACE` is a source-audit lead,
not an enabled global setting or an accepted WindowServer capture method.
Keep recovery and uncertain in-flight resource retention intact.

Primary API sources consulted at Khronos Vulkan-Docs tag `v1.4.363` on
2026-11-13:

- Khronos, [command-buffer submission](https://github.com/KhronosGroup/Vulkan-Docs/blob/v1.4.363/chapters/cmdbuffers.adoc), `vkQueueSubmit` failure requirements.
- Khronos, [memory](https://github.com/KhronosGroup/Vulkan-Docs/blob/v1.4.363/chapters/memory.adoc), `VkPhysicalDeviceMemoryBudgetPropertiesEXT` process estimates.

## Later build-35 startup checkpoint

The separate first-native-submit diagnostic was subsequently built, staged
and verified loaded. Its first initialization attempt remained unfinished;
the owner reports manually restarting after observing the machine stuck.
The next boot then invoked the existing protective stop. This later event
must not be conflated with the earlier WindowServer-triggered display
fallback above. NMXAccel is absent on this protective boot. See
[the postboot record](validation/native-submit-build35-postboot-20261113.json)
and [the diagnostic follow-up](NATIVE-SUBMIT-DIAGNOSTIC.md#postboot-investigation-initialization-stopped).

## Later build-35 bounded desktop retry

After initialization recovered and a separately bounded real Metal compute
test passed, the owner continued one desktop startup test with only one-shot
NVRAM arming. The persistent M2 marker remained absent. That attempt reached
PhxAMDFB, consumed the arming and released the display, then generated three
WindowServer crashes in the same RADV command-buffer cleanup stack. The
existing monitor requested a reboot; the following 16:09 boot restored the
initialized firmware desktop. The cleanup-order userspace fix remained
undeployed. This new capture recovered neither a native refusal code nor
the earlier incident's device-loss message, so the earlier failure cause
must remain unassigned. See [the separate postboot record](validation/native-submit-build35-m2-postboot-20261113.json)
and [its analysis](NATIVE-SUBMIT-DIAGNOSTIC.md#single-boot-desktop-outcome-cleanup-crashes-and-fallback).
