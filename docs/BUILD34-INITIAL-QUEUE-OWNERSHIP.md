# Build34 R3 initial queue ownership

Status: source review and passive registry evidence. No old-writer drain is
proved on gfx1103/macOS, no new MMIO or firmware operations were run, and the
native reader remains unbound. This is a prerequisite to reusing bootstrap
and fence storage.

## What Linux establishes

The reference is Linux v6.12 at
`adc218676eef25575469234709c2d87185ca223a`, also used by the
[fence reader review](BUILD34-FENCE-READER.md). This is a read-only review of
the linked Linux driver code; no source or binaries were imported.

| Pinned reference | Relevant behavior | Limit for build34 |
| --- | --- | --- |
| [`mes_v11_0_unmap_legacy_queue`](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/mes_v11_0.c#L446-L474) | The queue removal request identifies the legacy queue and waits for MES command completion. The preempt-without-unmap action is separate and supplies a trailing fence. | Needs a functioning scheduler the driver already owns and a known queue identity. Do not submit this through an unknown inherited scheduler or treat the preempt-only action as removal. |
| [`mes_v11_0_kiq_dequeue` and `mes_v11_0_kiq_hw_fini`](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/mes_v11_0.c#L1310-L1425) | The driver holds `srbm_mutex` over the indexed register sequence and restores selection. For an active HQD it requests dequeue and polls the active bit before clearing doorbell and pointer state. The teardown wrapper separately disables MES. | The dequeue helper returns `void`; on poll exhaustion it still clears control/pointer state. That sequence does not provide build34 with a positive drain acknowledgment. |
| [`mes_v11_0_reset_queue_mmio`](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/mes_v11_0.c#L337-L400) | The targeted reset has separate GFX and Compute sequences and returns a timeout if the selected HQD does not deactivate. | This is a better model for timeout propagation, but it still acts on a known queue and checks deactivation only. It does not prove PSP/SMU or already issued GPU writeback has drained. |
| [`mes_v11_0_enable`](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/mes_v11_0.c#L813-L860) and [`gfx_v11_0_hw_fini`](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/gfx_v11_0.c#L4343-L4378) | MES halt/reset is separate from disabling the managed GFX/Compute queues, stopping CP, and disabling GART. The non-VF teardown logs some failures and continues. | A control write or successful top-level teardown return does not certify that all prior DMA/writebacks are visible or finished. Linux's teardown and allocation lifecycle are not build34's initial ownership contract. |
| [`soc21_asic_reset_method`](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/soc21.c#L371-L399), [`soc21_need_reset_on_init`](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/soc21.c#L468-L483), and [SMU 13.0.4 Mode 2](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/pm/swsmu/smu13/smu_v13_0_4_ppt.c#L1075-L1079) | The default reset selector uses Mode 2 for MP1 13.0.4. Its SMU callback returns the mailbox command result. The separate SOC21 init predicate returns false for APUs. | Neither the recovery selector nor the init predicate establishes that a normal macOS restart reset the APU, that the firmware can safely take this command at startup, or what old writers are covered. |

### What the Mode 2 recovery path can establish

- **Mailbox result:** the pinned [common SMU wrapper](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/pm/swsmu/smu_cmn.c#L407-L478)
  serializes normal requests and interprets a reply. It can also return
  success without publishing a message when hardware access is disabled
  or a VF is not allowed the message. Even a verified fresh response on
  the native path provides no per-engine or write-visibility result.
- **Cancellation:** the [pre-ASIC reset phase](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/amdgpu_device.c#L5244-L5282)
  clears job fence slots and forces completion on scheduler-ready rings
  before the later ASIC reset. The [force-completion helper](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/amdgpu_fence.c#L760-L765)
  sets cancellation errors on the remaining fences and uses a
  [CPU store](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/amdgpu_fence.c#L99-L105)
  to write the last sequence if the ring has a CPU fence address. A fence
  reaching the submitted sequence after cancellation is therefore not proof
  of a GPU write or old work drain.
- **Recovery:** after the [reset call and ASIC init](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/amdgpu_device.c#L5350-L5408),
  the driver can report that reset succeeded before IP resume and
  [the new IB ring tests](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/amdgpu_device.c#L5479-L5487).
  Those tests check new work after reinitialization. They do not sample
  the old PSP/GART/IH storage at the proposed handoff boundary.

Linux's [S4 workaround](https://github.com/torvalds/linux/commit/fedb6ae49758658bd4a90689c26dc3c3a3f9c3cd)
uses the same Mode 2 command before unloading MP1. A [November 7, 2026 UTC mailing-list patch](https://lore-kernel.gnuweeb.org/amd-gfx/20261107204801.624322-1-raymondjup46%40gmail.com/T/)
reports that the command stopped replying on a Ryzen 7 7840HS after S0i3
and that issuing it during subsequent hibernation hung the system. The
proposal skips the sequence in that power state; it does not add a drain
receipt. This is a report from a different platform and sequence, not a
reproduction of the build34 host's startup behavior.

For R3, keep a verified firmware response, cancellation of software waits,
new work progress, and authorization to reuse old storage separate. The last
still requires identified writers, a documented stop and visibility boundary,
and proof that no owner rearms them before takeover. The reviewed Linux files
carry MIT-style grants; no source was imported and no reset was issued.

## Ordering gap in build34

The production `PhxBringup::start()` enables PCI bus mastering and memory
decoding before it maps the BARs and publishes the service. The shell can
therefore guard its own work only; it cannot establish the device state before
those PCI changes. The production `full.sh` calls `bringup5.sh` before
unhalting CP, running GART and starting MES. That script destroys and recreates
the PSP ring and stages firmware. `mesboot gart` writes page tables before
queue adoption.
`mes_start()` then writes MES reset and active controls. `kiq_init_only()` and
`sched_init()` clear fixed ring/writeback storage before `hqd_program()` writes
`ACTIVE=0` and reprograms the queue. `compute_via_mes()` and `gfx_via_mes()`
also clear ring, MQD or writeback storage before issuing `ADD_QUEUE`. Thus a
check at `hqd_program()`, a fresh sentinel after queue setup, or an adoption
check cannot protect the earlier writes to those regions. A successful new
command can coexist with an outstanding old write to a different location.

`mesboot` uses the build34 layout wrappers: a failed transport or wrong reply
size exits before a register value is returned. This still does not identify
which indexed register bank supplied a successful read. `grbm_select()` and
the later reads/writes are separate IOKit calls. The staged raw gate serializes
individual mutators, so other admitted writers can intervene between calls;
the shell reservation covers only the paired `full.sh` entrypoint. Writing
the selector to sample HQDs is itself a device write. Do not add that sequence
to the accepted passive BAR observer or run it on the active desktop.

## Interrupt ring ownership at startup

The [corrected PCI observer](BUILD34-PCI-IRQ-TRIAL.md#corrected-trial-passed-startup-observation)
samples before build34 enables PCI bus mastering and memory decoding, but it
does not prove what ran before `PhxBringup::start()`. A later passive topology
check still leaves the inherited IH owner and pending writes unknown. During
bootstrap, `mesboot` also supplies an OSSSYS base and queue resource data to
MES. That does not establish whether the firmware accesses IH and cannot
exclude it from the ownership review. A gate added in the startup shell or
at queue adoption is too late to establish an exclusive first device writer.

The [IH review](BUILD34-R3-IRQ-ROUTE-TRIAL.md#ih-ownership-review) found no
verified drain boundary for the primary ring. Include the IH ring, pointer
writeback and read-pointer doorbell in the first-writer review alongside
PSP, GART and the command queues. Prove either a handoff from the identified
predecessor or a reset whose documented scope covers those writers and their
outstanding writes. Fresh fence storage, a new boot ID or a masked PCI route
cannot prove that inherited writes to ring storage have stopped. Keep the
native reader and event backend unbound while these conditions remain open.

## Reset paths on the target

On November 21, 2026, two stable `ioreg` samples on the running build34 PCI
observer boot matched the exact Radeon provider, PhxBringup child and PCI
bridge service. A second read-only implementation using targeted IOKit
property and parent/child lookups reproduced all three classifications:

- The cached PCIe Device Capabilities did not advertise standard PCIe
  function-level reset (FLR).
- PhxBringup's existing `phx-pci-cmd-before` sample, taken after its power
  registration and before its own enable writes, had bus mastering and
  memory decoding set. Neither bit identifies the previous owner or says
  whether it left work pending.
- The detected bridge service had seven other direct PCI children. The
  service topology is not a verified electrical reset-domain map; it is
  enough to reject assuming a bridge reset would affect only the GPU.

See the [sanitized results](validation/build34-r3-reset-path-review-20261121.json).
The [public IOPCIFamily bridge code](https://github.com/apple-oss-distributions/IOPCIFamily/blob/4822b27a36e2de70e231ecf2bf3021384fab6ec2/IOPCIBridge.cpp#L3005-L3010)
publishes Device Capabilities via `kIOPCIExpressDeviceCapabilitiesKey`;
[`supportsFLR()`](https://github.com/apple-oss-distributions/IOPCIFamily/blob/4822b27a36e2de70e231ecf2bf3021384fab6ec2/IOPCIDevice.cpp#L3655-L3658)
uses the standard capability bit. The public source describes that path
without attesting the running IOPCIFamily image. No direct PCI configuration
access was requested. A broad registry dump can invoke property serializers;
the targeted verification did not request link status or other unrelated
properties. The result does not rule out a vendor-specific reset.

| Path | Disposition for R3 |
| --- | --- |
| Standard PCIe FLR | Do not plan around an unadvertised function reset. In the [reference Linux PCI code](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/pci/pci.c#L4541-L4580), `pcie_reset_flr()` rejects missing capability; `pcie_flr()` can proceed after a Transactions Pending timeout. Reset return or transaction status alone is not proof of old IH, queue or firmware write drain. |
| PCI PM D3hot to D0 | Linux's [`pci_pm_reset()`](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/pci/pci.c#L4643-L4671) requires a PM capability and a clear `No_Soft_Reset` bit, checks D0, then waits for config-space readiness after the transition. This bit was not sampled on the build34 host; config readiness would not prove on-chip writer drain. The reviewed IOPCIFamily [`hasPCIPowerManagement()`](https://github.com/apple-oss-distributions/IOPCIFamily/blob/4822b27a36e2de70e231ecf2bf3021384fab6ec2/IOPCIDevice.cpp#L1461-L1469) changes sleep-control bookkeeping and reads PCI config; it is not a passive substitute. |
| Secondary-bus/hot reset | No display-safe or GPU-only scope established. The same reference's [function-level fallback](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/pci/pci.c#L4993-L5009), `pci_parent_bus_reset()`, refuses when another device shares the secondary bus. Do not issue a bridge reset on the current stack. |
| ACPI device/power-resource reset | The current table review below found no `_RST` or `_PRR` under the matching graphics device or directly on its bridge. The explicit reset objects found belong to other devices or their power resources. Full runtime namespace resolution is still unproved. Do not evaluate AML methods to discover whether they are safe. |
| SMU Mode 2, power transition or normal restart | No verified coverage or completed-write boundary for PSP, MES, IH and outstanding memory writes. A mailbox response, PCI configuration readiness or new boot identity is insufficient. |
| GFX11 engine soft reset | AMD's [November 5, 2026 UTC v4 patch](https://www.mail-archive.com/amd-gfx%40lists.freedesktop.org/msg154925.html) covers a GFX-only recovery with an owned MES and saved queue state. Its two CP memory-busy polls can exhaust their budgets without aborting recovery. Compute and MES are outside the reset pulse, and the patch does not reset IH or verify IH drain. This is a reference for later recovery review, not an inherited-writer drain protocol. No code was imported. |

Host-side DMA isolation is a separate question from device reset. The
[IOMMU review](BUILD34-SYSTEM-WRITEBACK.md#host-iommu-and-the-release-boundary)
found a valid exposed `IVRS` table, but no verified runtime mapper for
this GPU and no evidence covering on-chip writers.

### Current ACPI table review

Two targeted IOKit reads of the running platform expert's `ACPI Tables`
property matched. All 41 exposed AML tables (one DSDT and 40 SSDTs, no
PSDTs) passed header-length and checksum validation. The DSDT's graphics
device and parent `_ADR` matched the registry path for the sole `1002:1900`
provider. The [sanitized record](validation/build34-r3-acpi-reset-scope-20261121.json)
records the following offline disassembly results:

- Four `_RST` definitions: two on power resources referenced by WLAN and
  a USB hub port, and two on USB4 host interfaces. Both `_PRR` definitions
  are conditional and locate those WLAN and USB-port resources, not a GPU
  reset resource. The USB-port scope shares the GPU's upstream bridge but
  is not the graphics function. An alternate hub-port package named `YPRR`
  refers to the same USB-port resource; it is not `_PRR`.
- No other exposed table contains either identified reset-resource name,
  and no alias or reference was found that assigns either resource to the
  graphics function. The GPU and bridge do have `_PR0`/`_PR3` packages
  and `_PS0`/`_PS3` methods. Their power methods use conditional hooks;
  the declarations establish neither a GPU-only electrical reset nor an
  acknowledgment of completed writes. See the
  [ACPI Specification 6.6](https://uefi.org/sites/default/files/resources/ACPI_Spec_6.6.pdf),
  sections 7.3.25-26, for the separate `_RST` and `_PRR` contracts.

[MaciASL iASL 20200925](https://github.com/acidanthera/MaciASL/blob/97ed950d2811b0b4cc802abc337316e16dd6aeeb/Dist/iasl-stable)
produced all 41 tables individually. The reset definitions and scopes agree
with [ACPICA iASL 20260930](https://github.com/open-acpica/acpica/releases/tag/20260930)
targeted passes using the DSDT for external symbols. Both releases failed full joint
disassembly on duplicate namespace objects (`AE_ALREADY_EXISTS`); the
targeted DSDT pass also still reported unresolved methods. The registry
property is an exposed table set, not an attested live namespace. Runtime
definitions and vendor-specific power/reset paths are not excluded. No AML
was executed, and no raw tables or disassemblies are in the repository.

Continue from a documented platform/firmware handoff for the identified
predecessor, or resolve a specific candidate reset path and its runtime
scope before considering it. A usable mechanism must account for IH, queues,
firmware, address translation and outstanding writes, and exclude firmware
rearming before takeover. Until then, do not reset the running GPU, program
IH, register a new ISR or admit exact completion on build34.

## Offline indexed observation transaction

`tools/build34_exact_hqd_observation.py` derives an internal method from the
paired claim stage. The method holds the service lease, exclusive raw-writer
lease and GPU lock across selector save, bank selection, sample and verified
restore. It refuses immediately on contention, sleep, service closure,
VM fault, prior adoption or an unbound backend. It requests only one of four
named banks and leaves the caller's output unchanged on refusal. Once selection
is attempted, it attempts one restoration even if the selection reported an
error. A failed bank check or unconfirmed restoration permanently closes raw
writes and vetoes both adoption requests for that service instance.

The CPU fixtures use the staged method, actual raw register write/adoption
method bodies and synthetic register storage. ASan/UBSan and TSan each pass
229 checks, including an interfering raw caller, service closure during a
sample, and faults at save, select, sample, verification or restore. Four
broken variants are detected. The complete before/after driver compiles as
nonloadable x86_64 objects with the same 377 KDK-resolved imports and four
existing warnings. All 172 production inputs are unchanged. Run it via:

```sh
nice -n 15 taskpolicy -b python3 -B tools/test_build34_exact_hqd_observation.py \
  --out build/build34-r3-hqd-observation-new-private --sdk "$KERNEL_SDK" --kdk "$KDK"
```

The native backend is null. There is no user selector, public entrypoint,
startup change or new MMIO operation. Reverting the offline stage means
omitting the transform. A future backend must verify the real selector and
readback semantics and hold power/mapping ownership even through restoration
after an observed stop. The final closure check is not atomic with stop;
the diagnostic result cannot be used as a persistent admission credential.
The staged gate excludes local raw calls, not external
writers or a different hardware owner. A successful inactive sample is
diagnostic; no queue, firmware writer or storage is declared safe on its basis.

## Firmware-to-driver boundary

On November 21, 2026, the running host reported an OpenCore 1.0.8 version
marker. The public tag resolves to
`6fe4d15cb66596d99d8cfedce69d8fc6dad71886`; the marker identifies a version
for source review and does not attest the installed loader, configuration,
vendor GOP, or callbacks provided by firmware and other drivers.

- [UEFI 2.11, section 7.4.6](https://uefi.org/specs/UEFI/2.11/07_Services_Boot_Services.html#efi-boot-services-exitbootservices)
  defines the end of boot services and the exit notifications. It does not
  provide a Phoenix-specific completion or write-visibility acknowledgment.
  [GOP, section 12.9](https://uefi.org/specs/UEFI/2.11/12_Protocols_Console_Support.html#graphics-output-protocol)
  exposes the display mode and framebuffer for OS startup. A successor able
  to use that framebuffer has no proof from GOP that other engines are idle.
- The pinned OpenCore
  [exit handler](https://github.com/acidanthera/OpenCorePkg/blob/6fe4d15cb66596d99d8cfedce69d8fc6dad71886/Library/OcMainLib/OpenCoreUefi.c#L348-L383)
  can release USB ownership and insert a delay. Its
  [boot-compatibility wrapper](https://github.com/acidanthera/OpenCorePkg/blob/6fe4d15cb66596d99d8cfedce69d8fc6dad71886/Library/OcAfterBootCompatLib/ServiceOverrides.c#L1380-L1457)
  calls scheduled handlers, hands off runtime services and prepares the
  kernel jump after successful firmware exit. Neither source path returns a
  Radeon queue or IH drain acknowledgment. Do not use a longer exit delay
  as a substitute for one.
- The first five minutes of the current macOS `26.7.2 (25G332)` boot showed
  the PhxFB boot-console marker followed by a successful UMA scanout alias
  check. All 4,096 sampled words matched, with nonzero pixels present.
  A same-boot registry read found `PhxAMDFB` and build34 `PhxBringup` on the
  same `1002:1900` provider. PCI bus mastering and memory decoding were
  already enabled in PhxBringup's pre-enable sample. The sample is taken
  after power registration, so it cannot attribute those bits to UEFI.

This is positive evidence for inheriting a display surface, not for inheriting
exclusive ownership of GFX, Compute, PSP, SMU, MES, GART or IH. The scanout
alias is not fence writeback memory; its pixel comparison cannot substitute
for a native fence visibility test. No EFI, NVRAM, driver or power changes,
new GPU submissions, or device operations were performed for this review.
See the [sanitized record](validation/build34-r3-firmware-handoff-20261121.json).

## Evidence required before reusing storage

1. Identify the current device, service, boot and first writer before *any*
   reused bootstrap storage is changed, including the PSP and GART paths.
   Bind all initial setup writers to the same exclusive scope. Make any
   index/select/read/restore observation an indivisible driver transaction
   with the required device power and mapping lifetime held. Reject an
   unknown owner, failed access or conflicting queue identity.
2. For an owned predecessor, establish the completion boundary for stopping
   new work and draining already issued work on each relevant device writer.
   For an unowned predecessor, require independently verified cold/reset
   semantics or disjoint, independently reserved storage with old mappings
   and global engine state protected. Separating the fence pages alone does
   not prevent interference through GART, queue control, or firmware memory.
   Do not infer either route from a new boot ID or a local process exit.
3. Validate the refusal path offline first: failed or short transport, index
   interference, dequeue timeout, and a delayed old write after an inactive
   sample or after fresh new work. Require that uncertainty prevents touching
   the affected storage, adopting queues or releasing old resources. A stale
   completion after publication must keep the scope quarantined.
4. Establish the mapping/writeback visibility contract separately before
   binding the exact reader. Any later hardware observation needs its own
   admitted scope and independent rollback; the previous mapping-only boot
   cannot establish initial queue state or drain.

No reset, unmap, dequeue, or new register test is proposed for the installed
build34 stack. Continue with exclusive boot-time ownership and a verified
mechanism for the unknown-predecessor case before enabling exact completion.
