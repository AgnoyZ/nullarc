# Build34 UMA-backed buffer prerequisite

The firmware framebuffer extent is not a free-memory list. Build34's ordinary
`BO_CREATE` path allocates XNU system pages, even for BOs charged to a RADV VRAM
heap. This experiment implements an allocator for a **separately owned part of
the actual UMA carve-out**, not a larger reported budget. No NullMoth code was
copied. The production driver, plugin, ABI, admission rules and heap sizes
remain unchanged.

## Offline allocator

[The pool](../tools/build34_uma_vram.h) admits one page-aligned, exclusively
owned window, at most 64 MiB, outside build34's entire 256 MiB BAR0 region. The
lower aperture holds the GOP scanout and bring-up allocations such as rings,
writebacks, GART tables and PSP firmware. The caller must also supply checked
scanout, firmware and IP-discovery intervals and any additional claims; a
missing, malformed or overlapping reservation refuses admission. A geometrically
valid address is not proof that no other component owns or writes it.

The pool accounts for capacity, reserved bytes and quarantined bytes
independently of BAR0. It gives each allocation and mapping a monotonic identity
and keeps a range unavailable to all other clients until release. It returns
separate GPU MC and backing physical addresses. It encodes data-only local
PTEs for one GPU VA range per BO and refuses overlaps within the same owner's
address space. The local address convention follows the existing bring-up
encoding in `mesboot.c`; read-only and read/write leaf encodings in this stage
are not validated on the GPU. This stage grants no CPU BAR map, user mmap,
executable IB placement or scanout ownership.

A caller must serialize access and supply a non-reused owner identity for each
address space. The range cannot be mapped before confirmed zeroing. It cannot
be reclaimed while PTE installation, GPU retirement or PTE removal is pending.
Unknown zeroing, mapping, retirement or invalidation quarantines the allocation
and closes the pool until reset. The CPU tests supply these transitions as
inputs; they are not GPU receipts or a substitute for a checked TLB protocol.

## Verification and remaining work

Run `make test-build34-uma-vram` for the ASan/UBSan fixture and passive
observation tests. The allocator fixture exercises geometry, reservations,
rounding, overlap, stale handles, address encoding, the fault gate, slot
exhaustion and 8,000 allocation/free steps compared with an independent page
bitmap.

### Live preflight, November 27, 2026

Run `python3 -B tools/build34_uma_observation.py` on the target. It reads only
`ioreg` and `sw_vers`, checks geometry from a unique build34 service under the
unique `1002:1900` PCI provider, and classifies discovery and firmware HUBP
metadata from that provider's direct children. It does not save registry data
or emit addresses or firmware payloads. Exit zero means the geometry was
observed, not that the allocator may use it. Even both samples being present
would not prove a complete reservation map or exclusive ownership.

On macOS 26.7.2 (25G332), build34 reports 4096 MiB of firmware UMA and a
256 MiB BAR0. No `PhxProbe` child was present and `PhxAMDFB` did not publish a
firmware HUBP sample. The result was `geometry-observed-ownership-unproven`
with `pool_admission_permitted: false`. The boot framebuffer, bring-up tables,
and discovery contents are not a free-space map, and subtracting the BAR0
size is not a way to derive one. The existing RADV budgets remain 256 MiB
visible VRAM, 1536 MiB high VRAM and a separate 512 MiB GTT cap. These values
neither measure free memory at the reported refresh stall nor identify its
cause; see [the page-switch retest](BUILD34-REFRESH-STALL.md).

### Ownership audit and host exclusion

Two independent conditions are required: the target interval must be excluded
from host reuse, and the GPU/firmware owner must be able to grant it with no
other writer. Build34 only publishes the MMHUB framebuffer geometry and the
BAR0 mapping. Its `BO_CREATE` owns the pages returned by XNU, not a GPU-local
partition. The existing offsets used for GOP, bring-up, and queue adoption do
not implement a high-UMA ownership transfer. Do not map the published
backing address as a substitute for BAR0. The [historical bring-up
notes](stage3-acceleration-plan.md) describe an earlier attempt where the
apparent physical address reached live host RAM instead of the expected BAR0
contents. That is not a measurement of this boot, but it rules out assuming
the addresses are interchangeable.

- **Host side:** The pinned [XNU x86 reference](https://github.com/apple-oss-distributions/xnu/blob/xnu-12377.1.9/osfmk/i386/i386_vm_init.c#L448)
  initializes physical ranges from the EFI descriptors passed in `boot_args`.
  Unused loader, boot-services, and conventional memory may be reclaimed;
  merely making an EFI boot-services allocation does not secure it for this
  driver after boot. `EfiReservedMemoryType` is not a grant either; the
  [UEFI 2.11 specification](https://uefi.org/specs/UEFI/2.11/07_Services_Boot_Services.html#efi-boot-services-getmemorymap)
  says it describes memory the OS is not supposed to access. Local read-only
  inspection found `/memory` with `reg` and a `/chosen/memory-map` node, but
  did not establish either as the complete typed map passed to XNU.
  [XNU's platform expert](https://github.com/apple-oss-distributions/xnu/blob/xnu-12377.1.9/pexpert/i386/pe_init.c#L137)
  uses the latter node for named boot payloads such as `BootCLUT`.
- **Firmware side:** The existing PSP selector 103 submits a real command,
  modifies the ring and reads back transport status, not a complete reservation
  record. On the historical 13.0.4 bring-up the two query commands returned
  unknown-command status; this is not an empty reservation list. Linux v6.18
  [gates both commands](https://github.com/torvalds/linux/blob/v6.18/drivers/gpu/drm/amd/amdgpu/amdgpu_psp.c#L1040)
  to specific PSP 14.0.2/14.0.3 firmware versions. Its separate
  [TTM path](https://github.com/torvalds/linux/blob/v6.18/drivers/gpu/drm/amd/amdgpu/amdgpu_ttm.c#L1758)
  accounts for firmware/VBIOS and discovery exclusions in the Linux-owned
  VRAM allocator; that is not an ownership grant to macOS build34.

[The offline host-map check](../tools/build34_uma_host_map.py) validates the
descriptor encoding, complete interval coverage and overlap for one bounded
pilot window. Even `reserved-type-only` reports descriptor type, not
permission to touch the range. Missing coverage, other firmware types and
host-usable types are distinct. It has no collector or production caller;
tests feed synthetic descriptors only. No same-boot typed map or owner grant
was obtained, and no PSP command, physical map, EFI change, or reboot was
performed for this audit.

### Current-boot memory-map availability

On macOS 26.7.2 (25G332), `sysctl machdep.memmap` worked and reported about
4206 MiB under `Reserved`. The pinned [XNU sysctl definitions](https://github.com/apple-oss-distributions/xnu/blob/xnu-12377.1.9/bsd/dev/i386/sysctl.c#L817)
expose byte counters by type, not descriptor addresses, order, or attributes.
A reserved total close to 4096 MiB cannot establish any overlap with the
Radeon's UMA. The inspected `/efi`, `/memory`, and `/chosen/memory-map` nodes
did not publish the EFI descriptor fields checked here. A filtered current-boot
kernel log query returned no `EFI region` lines or memory-region truncation
warnings. The reference XNU per-region print is debug-only; zero matches
prove neither completeness nor absence of a reservation. No raw registry or
log records were retained.

The pinned OpenCore 1.0.8 reference can change the map at two points: its
[GetMemoryMap override](https://github.com/acidanthera/OpenCorePkg/blob/6fe4d15cb66596d99d8cfedce69d8fc6dad71886/Library/OcAfterBootCompatLib/ServiceOverrides.c#L575)
can protect, split, merge, or retype descriptors, and its
[normal-boot preparation](https://github.com/acidanthera/OpenCorePkg/blob/6fe4d15cb66596d99d8cfedce69d8fc6dad71886/Library/OcAfterBootCompatLib/KernelSupport.c#L326)
can still restore descriptor types in `boot_args` at the kernel boundary.
These are source capabilities, not a claim about which options ran on this
boot. A standalone EFI application's earlier snapshot, even if complete, is
not the final map handed to XNU.

For a future authorized observation, first identify a non-perturbing way to
classify the final `boot_args` descriptors after all loader fixups, bound to
that boot and the same independently identified Radeon range. Do not add
allocations, logging, or file writes between the final map acquisition and
`ExitBootServices`. Export only a sanitized classification, and keep the
host-side result separate from a firmware or driver grant for that interval.
No suitable live source was found through the interfaces checked here; no
capture candidate was prepared, and no EFI or boot setting was changed.

No file in the kernel build consumes this pool. Before wiring it to native BOs,
obtain an explicit per-boot reservation from an owner that can prevent both
host reuse and concurrent firmware or driver access. Check it against the
complete scanout, firmware and discovery reservations. If no owner can grant
that reservation, keep the pool disabled; do not probe for free space by
writing unknown pages. Once a range is owned, validate zeroing and the local
PTE with checked GPU readback, then check GPU drain and TLB retirement through
map/unmap, close and sleep. Only after bounded hardware validation should RADV
be told about any new allocatable heap. No installation, GPU submission or
reboot was performed for this preflight. There is no installed state to roll
back; reverting the source-only changes removes the experiment and its tests.
