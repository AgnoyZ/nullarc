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

### Offline final-boot-args classifier

[The freestanding C core](../tools/build34_uma_boot_map.c) accepts immutable
views of the supplied x86 `boot_args` and its memory map. It checks version 2,
revision 0/1, EFI64, and the exact map physical base and byte count against
the supplied map view. It never converts the physical pointer into a host
pointer. Those checks reject mismatched views; they do not establish that
the caller's bytes are genuine, final, stable, or from the target boot.

The core reads little-endian fields, checks descriptor stride, overflow,
overlap and complete coverage, and accepts at most 256 descriptors and 1 MiB
of map data. It requires no allocation, boot service, file, or register I/O
and returns only the classification. `RESERVED_TYPE_ONLY` still describes
the host map, not GPU ownership or permission to access it. The command line
and unrelated boot-argument fields are neither parsed nor returned.

`make test-build34-uma-vram` passes the synthetic handoff fixtures under
ASan/UBSan, plus the existing allocator and observation suites. The offsets
and descriptor types were independently checked against the pinned XNU x86
`boot.h`, and a freestanding x86-64 COFF compile produced an unlinked object
with no unresolved symbols. No loader hook, EFI image, capture, or deployment
was made. A later caller would still need to prove the final handoff point,
immutable view lifetime, and same-boot binding to the independently checked
Radeon physical interval before the result could be used as host evidence.

### Handoff placement and guarded replay

The pinned OpenCore [x86-64 worker](https://github.com/acidanthera/OpenCorePkg/blob/6fe4d15cb66596d99d8cfedce69d8fc6dad71886/Library/OcAfterBootCompatLib/X64/KernelSupport64.c#L90)
invokes normal boot preparation before forwarding to the original call gate;
it handles hibernate separately. Immediately after normal preparation, on
the no-relocation path, is the first point in that worker after its known
type restorations. It is only a candidate observation point: the original
gate has not executed, and the worker may not run at all when its hook is
disabled or absent. A version marker does not show that the physical boot
used it. Do not enable boot quirks simply to reach it.

The [relocation path](https://github.com/acidanthera/OpenCorePkg/blob/6fe4d15cb66596d99d8cfedce69d8fc6dad71886/Library/OcAfterBootCompatLib/RelocationBlock.c#L367)
rebases the map address before the separate call gate moves the payload.
The rebased address must not be read as though its destination already holds
the map. Leave relocation and hibernate out of any first observation scope.

The synthetic fixture seals the argument and map views in read-only pages
with inaccessible guard pages. It observes an intentionally changed map
type only after the simulated fixup, refuses the stale map view without
reading it, then accepts the supplied immutable view after a modeled copy.
This tests the actual classifier without writing the inputs. It does not
execute OpenCore or demonstrate that a live observation preserves the call
gate, paging state, boot timing, or kernel inputs. A real trial still needs
evidence that the exact boot reaches the candidate point, a verified mapping
with a stable lifetime, and a boot-bound result channel that does not change
the memory map. No hook or output transport is implemented or installed.

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

## Staged Phase 1 + Phase 2 Opt-In Candidate

To test real BIOS UMA carve-out high-VRAM without altering the pinned stock
`src/phxbringup/PhxBringup.cpp` baseline (SHA-256
`81f45aa2e8166bc6ebed4106129bebebfd70f9b4bbea6dbe389be46263e3c699`), the
clean-room MIT/GPL-2.0 allocator and staging pipeline live in:

- `src/phxbringup/PhxUmaPool.h`: freestanding geometry validator, IP Discovery
  register/signature classifier, high-UMA window planner (`pilotWindow`
  `[256 MiB, 320 MiB)` and `fullHighWindow` `[256 MiB, fbSize - 64 MiB)`
  clamped below IP Discovery), read-only BAR0-vs-`phx-fb-phys` alias matcher,
  x86_64 `boot_args` EFI memory-map classifier, local VRAM PTE encoder
  (`0x31`/`0x71 | (4 << 48)` — `VALID|EXEC|READ(|WRITE)`, `SYSTEM=0`, `SNOOPED=0`,
  `MTYPE=4`, the same local-FB leaf flags as `mesboot.c`'s GART table), and
  fixed-capacity `HighUmaAllocator` with quarantine
  and fault latch.
- `tools/build34_uma_stage.py`: stages Phase 1 + Phase 2 onto exact build34
  `PhxBringup.cpp` and builds a signed `PhxBringup.kext` in a fresh
  `build/*-private` directory using `MacKernelSDK`.
- `tests/test_phx_uma_pool.cpp` and `tests/test_build34_uma_stage.py`: ASan/UBSan
  unit tests (`7562` checks) and staging invariant tests, wired into `make test`
  and `make test-build34-uma-vram`.

### Phase 1 (Read-Only Probe on Start)

On `PhxBringup::start()`, `probeUmaReadOnly()` performs only read-only checks
and publishes `phx-uma-*` properties on the `PhxBringup` IORegistry entry:

1. Reads `RCC_CONFIG_MEMSIZE`, `IP_DISCOVERY_VERSION`, `DRIVER_SCRATCH_0..2`,
   and verifies the IP Discovery signature (`0x282114`) via `MM_INDEX`/`MM_DATA`.
2. Samples 4096 stride-spaced dwords across the first 16 MiB of `phx-fb-phys` vs BAR0
   (`kIOMapWriteCombineCache`, read-only) to confirm `phx-fb-phys` aliases VRAM.
3. Maps the EFI memory map pointed to by `PE_state.bootArgs` read-only and
   classifies both the 64 MiB pilot window and the full high-UMA window with
   `phx::uma::classifyBootMap()`.

Default runtime behavior is completely unchanged (`debug.phx_uma_vram = 0`).

### Phase 2 (Opt-In `debug.phx_uma_vram` High-VRAM Pool)

Controlled at runtime via `sysctl debug.phx_uma_vram` (or at boot via optional
boot-arg `phx_uma_vram=1` or `phx_uma_vram=2`; default remains `0`):

- `0` (default): off; stock build34 system-memory BO path unchanged.
- `1`: admits the 64 MiB pilot window `[256 MiB, 320 MiB)` only if Phase 1
  proved geometry, discovery signature, alias match, and `ReservedTypeOnly`
  host exclusion.
- `2`: admits the full verified high-UMA window `[256 MiB, fbSize - 64 MiB)`
  (~3776 MiB on a 4 GiB carve-out, yielding ~4032 MiB total VRAM when combined
  with 256 MiB visible VRAM) only if Phase 1 proved full-window coverage. Because
  RADV on Phoenix APU (`has_dedicated_vram == 0`) discards `vram_hi_total` and
  computes `DEVICE_LOCAL = 2/3 * (vram_vis_total + gtt_cap)` and
  `GTT = 1/3 * (vram_vis_total + gtt_cap)`, mode `2` reports the combined
  visible + verified high-UMA pool (`4032 MiB`) in `vram_vis_*` together with a
  `2048 MiB` `gtt_cap` so Vulkan/Metal see a `~4053 MiB` `DEVICE_LOCAL` heap
  and `~2026 MiB` GTT heap, while `doBoCreate()` keeps CPU-mappable VRAM BOs
  strictly bounded to `kVisTotal` (`256 MiB`) and places `NO_CPU_ACCESS` VRAM
  BOs in the real high-UMA pool (`kMaxAllocs = 2048`, `kPtChunks = 192` for
  ~6 GiB mappable GPU VA per VMID).

Safety invariants enforced by the staged kext:

- High-UMA BOs are admitted only for `VRAM | NO_CPU_ACCESS` requests without
  `CPU_ACCESS_REQUIRED`.
- `clientMemoryForType()` refuses CPU mmap (`kIOReturnUnsupported`) on UMA BOs.
- `doGemVa()` accepts `PHX_AMDGPU_VM_PAGE_EXECUTABLE` on UMA BOs (RADV maps
  every VRAM BO EXECUTABLE; refusing it made `vkQueueSubmit` fail with
  `VK_ERROR_OUT_OF_DEVICE_MEMORY` in the first live run) and decodes
  `AMDGPU_VM_PAGE_WRITEABLE` (`1u << 2`) for read-only vs read-write local
  PTEs.
- `doSubmit()` refuses an IB whose VA lands on a UMA BO mapping (`ibCovered`
  treats UMA-backed EXEC maps as non-covering). Live bisect on 2026-11-28:
  GPU `WRITE_DATA`/`COPY_DATA` to, from and within the high UMA window all
  pass, an IB copied into the window reads back verbatim, but the CP faulting
  on instruction fetch from it trips a GPUVM fault that hangs the queue until
  the hang killer recovers it. RADV keeps every IB in GTT, so this is a
  safety net, not a restriction.
- Each UMA allocation is zeroed via write-combining alias mapping + `sfence` +
  `hdpFlush()` before handoff; zeroing failure quarantines the slot.
- `doBoFree()` unmaps PTEs and waits for GPU retirement outside `lock` before
  returning pages to the pool (quarantining on timeout).
- `clientClose()` calls `vmidFree()` before `freeAll()` so page tables and GPU
  waves drain before UMA ranges can be reused.
- Sleep (`powerStateWillChangeTo(0)`) trips the UMA fault latch.

### Building and Checking the Staged Kext Offline

```sh
make test-build34-uma-vram
python3 -B tools/build34_uma_stage.py \
  --sdk /Users/zhazhatao/nullarc/build/allocation-live-20261114-072303-private/MacKernelSDK \
  --out build/uma-vram-candidate-private
```

Against `KDK_26.7.2_25G332.kdk`, the staged `PhxBringup` binary adds only three
undefined KPI symbols over stock build34: `_PE_state` (`com.apple.kpi.unsupported`),
`IODeviceMemory::withRange` (`com.apple.kpi.iokit`), and `_OSAddAtomic`
(`com.apple.kpi.libkern`) — all already declared in `src/phxbringup/Info.plist`.

### Controlled Live Test Procedure (Requires Explicit User Approval)

`PhxBringup.kext` is loaded by OpenCore from EFI (`OC/Kexts/PhxBringup.kext`).
No EFI/kext installation or reboot is performed automatically. When approved:

1. Back up the current EFI `OC/Kexts/PhxBringup.kext` and install the staged
   candidate; reboot with default `debug.phx_uma_vram = 0`.
2. Verify Phase 1 read-only evidence via `ioreg -rn PhxBringup`: confirm
   `phx-uma-discovery-valid = Yes`, `phx-uma-alias-matched = Yes`,
   `phx-uma-pilot-host-status = 7` (`ReservedTypeOnly`), and
   `phx-uma-full-host-status = 7`.
3. Only if Phase 1 checks pass, opt in to the 64 MiB pilot:
   `sudo sysctl -w debug.phx_uma_vram=1`, run a Vulkan/Metal client, and check
   `sysctl debug.phx_uma_vram_allocs debug.phx_uma_vram_frees debug.phx_uma_vram_bytes debug.phx_uma_vram_faults`.
4. If the 64 MiB pilot succeeds with zero faults/artifacts, reboot or test
   mode `2` (`sudo sysctl -w debug.phx_uma_vram=2`) to expose the full verified
   high-UMA heap to RADV/Metal.

### Live Hardware Verification (2026-11-28, Radeon 780M / macOS 26.7.2 25G332)

Candidate v5 (`PhxBringup.kext`, UUID `FDB05A5C-EFBF-3341-887C-550F27B7F8AC`,
SHA-256 `9beca4446c8c010643598e7b464d884ba7c554e295d0cfc82ed0fb917b49b58f`) was
installed to EFI and verified on real hardware:

- **Phase 1 read-only probe**: `phx-fb-size = 4 GiB`, `phx-fb-aper-len = 256 MiB`,
  `phx-uma-rcc-memsize-mb = 4096`, `phx-uma-discovery-valid = Yes` (`0x28211407`),
  `phx-uma-alias-matched = Yes` (`4096/4096`, `73` non-zero samples),
  `phx-uma-pilot-host-status = 7` (`ReservedTypeOnly`),
  `phx-uma-full-host-status = 7` (`ReservedTypeOnly`),
  `phx-uma-full-bytes = 3776 MiB`.
- **Vulkan (`debug.phx_uma_vram = 2`)**: RADV reports
  `VRAM 4032 MiB visible + 0 MiB hi, GTT cap 2048 MiB`, exposing
  `heap[1]` (`VK_MEMORY_HEAP_DEVICE_LOCAL_BIT`): **4053 MiB** (budget **4053 MiB**)
  and `heap[0]` (GTT): **2026 MiB** (budget **2026 MiB**).
- **Large BO + IB-in-UMA guard**: `BOCREATE` + `GEMVA` of a single `2048 MiB`
  high-UMA BO succeeds (`kPtChunks = 192`); CPU mmap is refused (`0xe00002c2`);
  submitting an IB whose VA lands in high UMA is cleanly refused (`0xe00002c2`)
  with zero GPUVM faults and zero hangs; GPU `WRITE_DATA` and `COPY_DATA`
  readbacks pass verbatim.
- **Metal end-to-end stress**: `128 MiB` Private buffer blit roundtrip passes
  directly on UMA (`allocs=2, frees=2, fallbacks=0, faults=0`);
  `10 × 256 MiB` (`2561 MiB` peak, default NVMTL headroom) and
  `14 × 256 MiB` (`3585 MiB` peak with `NVMTL_VRAM_HEADROOM_MB=128`) live
  `MTLResourceStorageModePrivate` buffers all allocate in real UMA VRAM, pass
  GPU blit readback, and release cleanly on exit with `fallbacks = 0`,
  `faults = 0`, and `debug.phx_hang_kills = 0`.
