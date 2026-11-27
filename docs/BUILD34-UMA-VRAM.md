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

Run `make test-build34-uma-vram` for the ASan/UBSan fixture. It exercises
geometry, reservations, rounding, overlap, stale handles, address encoding,
the fault gate, slot exhaustion and 8,000 allocation/free steps compared with
an independent page bitmap.

No file in the kernel build consumes this pool. Before wiring it to native BOs,
identify a proven exclusive hardware range on the target boot, validate the
local PTE and zeroing path, then pair allocation with checked GPU drain and TLB
retirement through map/unmap, close and sleep. Only after bounded hardware
validation should RADV be told about any new allocatable heap. No installation,
GPU submission or reboot was performed. There is no installed state to roll
back; revert this source-only addition to remove the experiment and its tests.
