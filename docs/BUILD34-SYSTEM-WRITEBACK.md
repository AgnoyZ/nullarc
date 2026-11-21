# Build34 R3 system-memory writeback study

Status: the address-layout check is offline only. The installed build34 BAR0
path is unchanged. There is no reserved slot, DMA allocation, new mapping,
bound reader or tested GPU path in this stage.

## Addressing and the bootstrap conflict

Linux v6.12 uses a [GTT writeback buffer](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/amdgpu_device.c#L1442-L1472)
and derives per-ring GPU addresses and CPU pointers from that allocation in
[`amdgpu_ring_init`](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/amdgpu_ring.c#L274-L289).
The reference [GART bind](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/amdgpu_ttm.c#L956-L969)
takes device DMA addresses, not the CPU pointer or a presumed host physical
identity. The [GART map](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/amdgpu_gart.c#L347-L366)
uses those addresses when filling PTEs. This is a design reference, not a
verified recipe for the macOS mapper, gfx1103 cache policy or teardown.
The four Linux source files were reviewed under their MIT-style grants; no
source or binary was copied.

Build34 currently targets the framebuffer memory-controller address in its
top-level `RELEASE_MEM`, separate from the per-client VMID used by the IB.
Its `mesboot` context-0 startup path populates **all 32,768 PTEs** in the
128 MiB GART window with framebuffer backing. A new system page does not
give that window a free slot. An unused-looking framebuffer offset is still
mapped. Reserving a region would require a separately reviewed bootstrap
layout that excludes it before creating mappings, accounts for existing
consumers, and remains subject to the initial-owner and drain requirements.

The `MESBOOT_VMT` diagnostic overwrites existing GART entries and polls a
`WRITE_DATA` result after cache work and a delay. `VM8_SYS` changes the IB
payload destination, while its `RELEASE_MEM` still targets a framebuffer
address. Both call sites are useful for distinguishing the experiments;
neither establishes GFX and Compute system-memory `RELEASE_MEM` completion,
independent guard integrity, a live fence reader, or clean teardown. Do not
replay those debug paths to claim an R3 result.

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
   the DMA mapping and backing page. On uncertain publication, write drain,
   or invalidation, quarantine and keep the page and its mapping pinned.
   A completed fence or CPU callback alone cannot authorize that release.

Private allocations may isolate old **addresses** after these checks. They
do not remove the need to establish PSP, GART, IH and queue ownership or the
old DMA drain boundary. No production input or running setting was modified.
