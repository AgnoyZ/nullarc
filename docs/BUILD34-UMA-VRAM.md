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
