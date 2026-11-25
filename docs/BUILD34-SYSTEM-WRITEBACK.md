# Build34 R3 system-memory writeback study

Status: the address-layout check is offline only. The installed build34 BAR0
path is unchanged. There is no reserved slot, DMA allocation, new mapping,
bound reader or tested GPU path in this stage.

## Addressing and the bootstrap conflict

Linux v6.12 uses a [GTT writeback buffer](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/amdgpu_device.c#L1442-L1472)
and derives GPU addresses and CPU pointers for ordinary rings through
[separate accessors](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/amdgpu_ring.c#L174-L182),
including for [the fence itself](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/amdgpu_ring.c#L284-L287).
The reference [GART bind](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/amdgpu_ttm.c#L956-L969)
takes device DMA addresses, not the CPU pointer or a presumed host physical
identity. The [GART map](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/amdgpu_gart.c#L347-L369)
uses those addresses when filling PTEs. This is a design reference, not a
verified recipe for the macOS mapper, gfx1103 cache policy or teardown.
[GMC11 sets different limits for the internal MC and device DMA address spaces](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/gmc_v11_0.c#L794-L806):
48 bits for MC addresses and 44 bits for DMA. The checker uses 44 bits as a
provisional ceiling for DMA. Neither that ceiling nor the 48-bit PTE field
establishes the actual macOS mapper limit. The Linux files were reviewed
under their MIT-style grants; no source or binary was copied.

Build34 currently targets the framebuffer memory-controller address in its
top-level `RELEASE_MEM`, separate from the per-client VMID used by the IB.
Its `mesboot` context-0 startup path populates **all 32,768 PTEs** in the
128 MiB GART window with framebuffer backing. A new system page does not
give that window a free slot. An unused-looking framebuffer offset is still
mapped. The flat table occupies 256 KiB (32,768 eight-byte entries) and ends
exactly where `PHX34_DEFAULT_OFFSET` starts. Appending two entries at the
current base would put both into the fault fallback page. Reserving a region
requires a separately reviewed bootstrap layout that excludes it before
creating mappings and accounts for both virtual references and physical
table storage. The ring, MQD, EOP and writeback references emitted through
`VA(off)` must retain their translations. A hole in a proposed layout does
not establish an old-writer drain.

The `MESBOOT_VMT` diagnostic overwrites existing GART entries and polls a
`WRITE_DATA` result after cache work and a delay. `VM8_SYS` changes the IB
payload destination, while its `RELEASE_MEM` still targets a framebuffer
address. Both call sites are useful for distinguishing the experiments;
neither establishes GFX and Compute system-memory `RELEASE_MEM` completion,
independent guard integrity, a live fence reader, or clean teardown. Do not
replay those debug paths to claim an R3 result.

The `sysMem` debug selector returns `getPhysicalAddress()` without proving
the device mapping. A subsequent allocation, explicit free, or service stop
can release its backing without this trial's drain and detach checks. Do not
reuse this selector as the persistent allocation for the reader.

## Device DMA backing

The pinned public XNU [`IODMACommand` contract](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/iokit/IOKit/IODMACommand.h#L322-L351)
allows bounce buffering even when `prepare()` succeeds. Its
[`getIOMemoryDescriptor()`](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/iokit/Kernel/IODMACommand.cpp#L480-L491)
returns the original descriptor if no full copy descriptor exists. The
[per-page copy path](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/iokit/Kernel/IODMACommand.cpp#L659-L701)
can still allocate substitute pages in this case. Descriptor equality
alone is therefore insufficient to prove that a generated DMA segment
targets the exact page the CPU polls. Require proof of that segment's
backing or a verified no-copy path for the matching runtime. Do not use
an unverified system-mapper fallback. The public XNU source is APSL 2.0
and does not attest the installed kernel's mapping; no code was copied.

### Host IOMMU and the release boundary

On November 22, 2026, two targeted registry samples on macOS 26.7.2
(25G332) found a valid `IVRS` table in the platform expert's exposed ACPI
property. Two reads of the `1002:1900` PCI provider of the
unique build34 service returned no value for `iommu-parent`. The table
describes firmware topology. The unavailable property leaves this GPU's
runtime mapper unresolved; it does not rule out a mapper or establish
identity addressing. Only classifications are retained in the
[sanitized record](validation/build34-r3-iommu-scope-20261122.json).

A bounded passive follow-up on November 26, 2026, again matched exactly one
`1002:1900` provider with one build34 child and classified its PCI
`iommu-parent` property as absent. The collector does not retain the registry
snapshot or emit property values. This confirms the currently exposed property
state only; it neither proves that no mapper exists nor qualifies identity
DMA. The reusable [filtered mapper observer](../tools/build34_dcn_mapper_observation.py)
and its [sanitized result](validation/build34-dcn-mapper-observation-20261126.json)
keep runtime mapper resolution and DMA-domain proof explicitly false.
Reproduce the parser and bounded live query with:

```sh
python3 -B tests/test_build34_dcn_mapper_observation.py
python3 -B tools/build34_dcn_mapper_observation.py
```

No mapper lookup API, DMA mapping, device register access, driver operation,
GPU submission, installation, or restart was performed.

- In [XNU's device mapper lookup](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/iokit/Kernel/IOMapper.cpp#L167-L207),
  `copyMapperForDevice()` resolves `iommu-parent`; the implementation can
  wait for a matching service. Do not call it under a GPU lock or infer
  that an arbitrary system mapper routes this device.
- In [Linux's AMD IOMMU reference](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/iommu/amd/iommu.c#L1219-L1263),
  the completion wait enqueues a command and waits for its own semaphore
  value, unlike a poll of an unqualified status bit. The outer domain flush
  helper discards its return value, so this is not a checked release receipt
  at every Linux call site. Neither source establishes macOS mapper behavior
  or covers on-chip GPU writers that never cross the host IOMMU. A
  destination restriction on one DMA path is not a handoff of PSP, IH,
  queue state or the GPU's separate GART translations.
- XNU's [`complete()`](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/iokit/Kernel/IODMACommand.cpp#L1057-L1118)
  can just drop a nested active reference. On the last reference it can
  assign the unmap result over an earlier buffer-walk result and clears
  local mapping bookkeeping even if the unmap fails.
  [`dmaUnmap()`](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/iokit/Kernel/IOMemoryDescriptor.cpp#L4627-L4667)
  delegates to the concrete mapper. These calls do not furnish separate
  proof of writer drain, successful synchronization and translation
  invalidation. Do not use a successful return as that proof or retry a
  failed `complete()` as if its original mapping were still tracked.

Before handing the descriptor to an operation that can unmap it, prove
the GPU-side stop and detach, and hold a separate backing reference.
Require a checked boundary for the actual mapper to reuse the physical
page or its DMA address. If that boundary is uncertain, keep the backing
pinned and the scope closed to reuse; do not claim the old API mapping
survived. No IOMMU commands, DMA operations or hardware state changes
were performed for this review. No Linux or XNU code was imported.

### AMD invalidation completion is a mapping boundary

AMD's [IOMMU specification 48882-PUB, revision 3.10 (PDF mirror)](https://kib.kiev.ua/x86docs/AMD/IOMMU/48882-3.10.pdf),
sections 2.4.1 and 2.4.11.2, defines a positive boundary for reclaiming
pages from translated DMA: make the entries non-present, invalidate the
applicable translations and observe completion of the matching
`COMPLETION_WAIT`. Invalidation does not complete while matching DMA that
used the old cached translations is still in flight. Where a remote IOTLB
is active, use the device-side invalidation and ordering rules in sections
2.4.4 and 2.4.11.1; a host cache-only result would omit that coverage.
`COMPLETION_WAIT` by itself is an IOMMU command boundary. It
does not stop a producer, invalidate unchanged mappings or cover traffic
that bypasses translation (section 2.1). Section 2.4.5 separately defines
interrupt remapping cache invalidation; the page-reuse result is not proof
that all previously issued MSI messages have been delivered.

Before crediting this boundary, require the actual mapper and requesters,
all ring/writeback destinations and aliases, and a checked result tied to
revocation of those mappings. Refuse if any path is untranslated or
unattributed, any alias stays live, or completion fails or cannot be tied to
the revocation. The mapper must account for `IOTLB_INV_TIMEOUT` (section
2.5.8), including when reset interrupts a remote invalidation (section
2.1.4.13). A command completion token does not substitute for that error
check. Even with coverage for the old pages, keep producer stop,
doorbell ownership and prevention of rearm as separate requirements. A late
request must not be able to hit a new mapping that reuses the old device
address. This is a source-derived requirement, not authority to edit the
running mapper, unmap the inherited ring or release its backing. No source
text, register sequence or binary was imported.

## TLB acknowledgement is not translation proof

Linux's [GART invalidation](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/amdgpu_gart.c#L397-L417)
orders table writes and targets VMID0 on each registered VM hub.
[GMC11](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/gmc_v11_0.c#L209-L293)
uses engine 17; its direct register path serializes invalidation and logs
ACK timeouts, while the active firmware path delegates a register write and
wait. The direct poll checks a VMID bit, without a request generation in
the observed value. This source does not establish what clears that bit on
gfx1103 or which hub must be included for build34's specific queue path.

`mesboot` writes engine 17 and prints ACK after a fixed delay. Production
`vmFlushTlb` also uses GFXHUB engine 17, sets the VMID0 bit even for a user
VMID request, and discards timeout. The staged `vmFlushTlbChecked` improves
timeout propagation for a user VMID, but reads the same kind of ACK and
does not admit VMID0. The existing desktop's VM operations therefore cannot
be assumed to leave engine 17 or VMID0's ACK exclusively attributed to a
trial. A set bit, elapsed delay, or successful register transport is not
proof that the new translation took effect. Do not write the ACK register
or require observing a transient clear without first establishing its
register semantics. A future trial needs exclusive request ownership,
proof that the response belongs to the issued request at every relevant
hub, and distinct old/new backing signatures to corroborate the page walk.
Retain all potentially reachable backing and DMA mappings if either
observation fails.

## Offline refusal check

[`build34_r3_writeback_layout.py`](../tools/build34_r3_writeback_layout.py)
checks one proposed pair of dedicated 4 KiB system pages. The caller supplies
an admissible lower-half VMID0 GART window and a list of occupied byte ranges
in each of three address spaces: GPU VA, device DMA address, and host
physical address. The whole page must be disjoint in each respective address
space; different VAs or DMA addresses can still alias the same host page.
Each aligned dword has room for guards on both sides. The checker refuses
wrapped or out-of-range extents and returns no raw address values. It cannot
prove the reserved inventory is complete or that a device translation
resolves to the supplied page. The normal test suite includes a refusal case
for the fully populated build34 window and synthetic aliases in each address
space. Removing the checker and its test reverts this offline step.

## Conditions for a separately scoped trial

1. Establish the prior writer boundary and a leased GPU/mapper identity
   before any hardware mapping change. Obtain the device bus segment from the
   actual mapper. The pinned SDK's `IODMACommand` interface can describe
   mapped or bypassed addressing, but also allows buffered copies. Verify
   exact backing, absence of bounce buffering, device address width, CPU
   mapping and cache/snoop policy; a host physical address is not a DMA
   address without an established identity path. Prepare outside GPU locks.
2. Use only reserved, never-reused GART slots while old references could
   exist. Verify the PTE configuration and a fresh TLB invalidation response.
   The production `vmFlushTlb` returns no timeout status; it cannot witness
   this transition. Verify the actual top-level packet's address and VMID
   on both queues before claiming system-memory equivalence.
3. Separately measure CPU seed visibility to the GPU and ordered GPU-to-CPU
   visibility of changing fence values and their preceding payload, with
   intact guards, on both queues. A separate cache flush or buffered copy on
   every poll would be a different observation path and needs its own proof
   and CPU/latency comparison. Feed only independently obtained, trusted
   fence observations to the dual-queue overlap test.
4. Once the backing is reachable from the GPU, stop new writers and prove
   already issued writes finished before removing the translation. Then
   prove the detach and TLB invalidation before completing and releasing
   the DMA mapping and backing page. Before DMA completion, quarantine and
   keep the page and mapping pinned on uncertain publication, drain, or
   GPU invalidation. After an uncertain mapper teardown keep a separate
   backing pin and do not reuse the address. A completed fence or CPU
   callback alone cannot authorize release.

Private allocations may isolate old **addresses** after these checks. They
do not remove the need to establish PSP, GART, IH and queue ownership or the
old DMA drain boundary. No production input or running setting was modified.
