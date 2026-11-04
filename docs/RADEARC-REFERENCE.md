# RadeArc as a reference (`Kreytus/RadeArc`)

A second downstream of the same upstream this branch is built on, ported to a different Phoenix GPU. It is
recorded here because it answers questions this branch had left open, and because adopting anything from it
has to be deliberate: it ships things this repository must not copy.

Pinned for reading: `main` = `d8d8d18` (2026-11-03), 74 commits ahead of `luuumi-dev/nullarc` `cbb08dd` — the
same base as `downstream/780m-tahoe`. Everything below was read through the GitHub API at that commit; nothing
was copied into this tree.

## What it is

- `Radeon 740M` (Phoenix 2, `1002:15C8`, GC **11.0.4**, PSP/SMU **13.0.11**) in a **desktop** Hackintosh —
  Ryzen 5 8500G, Gigabyte B650M D3HP AX, **HDMI/DP only, no internal panel**.
- README status: "Phase 1 (PhxBringup on Phoenix 2) code complete, untested on hardware", Phoenix 2 bring-up
  opt-in behind `-phxp2`, and the upstream 780M/760M (Phoenix 1) patches kept working. Since then the commits
  go much further: DCN 3.1.4 display programming, measured tests, a package release.
- Their own documents: `docs/PORTING_AUDIT.md` (every Phoenix 1 / 780M / eDP assumption in upstream, with
  Linux `drivers/gpu/drm/amd` references), `docs/PHOENIX2_FACTS.md` (IP versions and bases read from their
  machine), `docs/PHASE0.md` + `tools/phase0/` (how the facts were collected), `docs/PHASE3B_PLAN.md`,
  `docs/TEST_PHOENIX2.md`.
- Evidence it is not just documents: 74 commits, three CI workflows (`CI`, `Build kexts`, `Build install
  package`) green on `d8d8d18`, a `package-latest` release, and raw hardware dumps plus test logs under
  `hardware/dumps/b650m_8500g/` (`testk.txt`, `testl.txt`, `testclk.txt`, `linux_drm_state.txt`, …).
- Licence composition is the same as this tree (own code MIT or GPL-2.0; `src/phxaccel` and `src/nmplugin`
  PolyForm Noncommercial 1.0.0; `mesa-patches-phoenix` MIT). GitHub reports `NOASSERTION` because it is
  multi-licence, so any adoption is per file with the notices.

## What matters for this branch, in order

### 1. Damage-only frame copy (`src/phxaccel/accel/nvrm-accel.cpp`)

They measured the problem this branch has only read in comments: on their machine the scan-out's CPU view
takes stores at ~190 MB/s whatever cache mode it asks for, a full 1920×1080 copy cost **44 ms (~21 fps)** and
the cursor lagged. Their fix keeps a cached shadow of what the scan-out holds, compares each frame in 64-byte
steps, and stores only the steps that changed (a moving cursor touches a few kB). It is switchable —
`debug.nvaccel_iop_damage` (default 1), `debug.nvaccel_iop_full=1` forces one full copy — and deliberately
avoids SSE so the XMM save/restore disappears with it.

This is the first external evidence for our own H1 (docs/analysis.md §5): on a 780M eDP panel the BAR copy is
quoted at ~110 ms/frame at 2560×1600, and a damage-only copy is the one optimisation that reduces stored bytes
rather than their cost. It collides with our `PhxCopyPath.hpp` refactor in the same function, so it has to be
re-implemented on top of ours, not merged — and it needs its own phase-1 A/B before it is adopted here.

### 2. Two base-code bugs found on hardware — checked against this tree

**BO handle ceiling: applies, and is not raised here.** They ran out of the per-client BO handle table —
`4095` usable handles — and every `MTLTexture` allocation failed, down to 64×64, until WindowServer crashed.
This tree has the same ceiling: `PHXN_MAX_BOS 4096u` (`src/phxbringup/PhxNativeABI.h:22`), a per-client
`PhxClientBo entries[PHXN_MAX_BOS]` array, a `kMaxMaps = 4096` mapping table, and a silent
`return kIOReturnNoResources` when no handle is free (`PhxBringup.cpp`).

Their fix raises **both** sides: the kext table and the user-space table in their Mesa ABI header and mock. Only
the first half is available here, and doing it alone would be worse than doing nothing: the kernel would hand
RADV handle 4096 and beyond while a 4096-entry user-space table indexes it. Our RADV side is the pinned Mesa +
Cobalt64 patch set, which this repository does not vendor, so the limit stays where it is and the failure is
made visible instead:

- `debug.phxbos_handles_high` — highest handle index handed out by any client (how close a session got);
- `debug.phxbos_handles_full` — BO creates refused for a full table;
- the first refusal logs one line naming `PHXN_MAX_BOS`, because from user space this failure looks like
  anything but "out of handles";
- both counters are in the phase-1 capture, so the first target session answers "are we near the cliff" with a
  number.

If a session does approach the limit, raising it becomes a two-sided change with the user-space table and it
should be done together.

**Host-import hang: does not apply.** Their hung GPU came from mapping **read-only IOSurface** imports without
GPU write permission; those pages are written anyway, and the GPU stalled. This tree has only
`PHXN_SEL_BOIMPORTHOST` (ABI 1.9): host imports of the caller's own writable pages, capped at 4 GiB per client
and 1 GiB per BO. The read-only-IOSurface variant does not exist here, so there is nothing to switch off. The
lesson is worth keeping: an import that the GPU may write must never be mapped as read-only, and their
`debug.phxbo_host_ro=1` escape hatch is the shape to use if that path is ever added.

### 3. The `mesboot` parameterisation this branch deferred (`tools/phxctl/mesboot.c`)

They replaced the reference-machine memory layout with a chip-gated read: `phx-chip` names the chip, and for
Phoenix 2 the values come from `PhxBringup`-published `phx-fb-mc-base` / `phx-fb-size` / `phx-fb-phys`; an
unknown chip prints `chip '<name>' not supported: nothing done` and touches nothing. The aperture, default and
fault-page registers are derived the way Linux's `gfxhub_v3_0_init_system_aperture_regs` does, with a VRAM
scratch page standing in for Linux's dummy page.

That is exactly the pattern `docs/BRINGUP-AUDIT.md` asks for and the one this branch declined to invent: the
values come from evidence the driver itself publishes, and the tool refuses when it has none. Adopting it here
means adding those properties to our `PhxBringup` first.

### 4. DCN 3.1.4 display programming (later, not now)

`src/amd/phx_dcn314_plan.h`, `phx_dcn314_prog_regs.h`, `phx_dcn_timing.h`, `phx_dcn_i2c.h`,
`phx_dml314_plans.h`, `phx_dmub_layout.h`, `phx_dmub_vbios_cmd.h`, plus `tools/dml/` which builds Linux's
DCN 3.1.4 DML (v6.17, unmodified) in userspace to generate the plans, and `tools/phxctl/`
`{dmcubload,clkinfo,modecheck,testl,testk,testclk,testd}`. Their tests K/L are real display-clock and
144 Hz-switch experiments.

This is the "program the display engine" project our docs keep deferring, at the same IP version. It is
**HDMI/DP on a desktop**: no eDP link training, no backlight, no panel power sequencing — the parts a laptop
panel needs. Useful as a map of what the work looks like, not as a drop-in.

### 5. Their audit of upstream's machine-specific constants

`docs/PORTING_AUDIT.md` catalogues the Firebat-derived constants we also carry — `VRAM_MC`/`FB_PA`, the
`bringup5.sh` firmware byte offsets and sizes, the TMR MC address (`0x6A0C000000` = Firebat `FB_OFFSET` +
0xC000000), the GC/MMHUB/OSSSYS base tables, PSP/SMU mailbox bases and the MMHUB `FB_LOCATION`/`FB_OFFSET`/
`FB_BASE` offsets (`0x1A8EC`/`0x1A8ED`/`0x1A8D7`, MMHUB 3.0.1). It also documents a live difference they found:
13.0.11 selects **BASE_IDX 0** for MP0/MP1, so the mailboxes move relative to Phoenix 1's 13.0.4.

Their `bringup5.sh` finding would apply to us as written — hardcoded firmware payload offsets load **garbage**
for a different firmware set — but it is not our path: the reference workflow is not run here, and the audited
loader derives its extents from the firmware headers (`tools/firmware_manifest.py` →
`PhxFirmwareProfile.h` → `phxctl firmware-sequence`). `tests/test_reference_scripts.py` keeps that substitution
from silently reversing.

## What this branch must not take from it

- `hardware/dumps/b650m_8500g/**` — `vbios.rom`, `VFCT.bin`, `ip_discovery.bin`, `edid_msi_g255f.bin`,
  `edid_ddc1_macos.txt`. AMD/OEM material, and this repository's rules forbid committing ROMs, firmware bytes
  and raw dumps of a machine that is not ours.
- Their CI packaging (`build-kexts.yml`, `build-package.yml`, the `package-latest` release). This repository
  publishes no binaries until the upstream licence/provenance audit is resolved and publication is approved.
- `install/install.sh` and `tools/phxctl/update.sh` — they install and update a running system. Ours writes a
  plan for a human (`tools/phx_install_plan.py`) and performs nothing.
- Their 780M/eDP claims. They ported *away* from Phoenix 1; nothing here is a re-test of our target, and the
  only 780M hardware evidence remains upstream's Firebat measurement.

## Open questions this leaves

- Whether the 190 MB/s store ceiling they measured is a property of their machine's carve-out mapping or of the
  path itself — our `copy_us` on the eDP target answers that, not their number.
- How close our target's WindowServer gets to `PHXN_MAX_BOS`. The counters answer it; nothing else can.
- Whether raising the handle ceiling is needed at all: if a capture shows `phxbos_handles_high` well below 4095
  and `phxbos_handles_full` at zero, the ceiling is not the problem on this machine.
- Which `PhxBringup` properties a Phoenix 1 target would need for the chip-gated layout, and whether `phx-fb-mc-base`
  is even obtainable there without the register reads we have postponed.

Recorded 2026-11-03 from `Kreytus/RadeArc@d8d8d18`; re-read before relying on any line above, the branch moves
several times a day.
