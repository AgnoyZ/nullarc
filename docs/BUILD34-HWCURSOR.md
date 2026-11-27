# Build34 DCN 3.1.4 hardware cursor (opt-in)

This change adds an opt-in DCN 3.1.4 hardware cursor path to `PhxAMDFB`
(`src/phxaccel/accel/phxfb.cpp`) on `upstream34/vram-layout-fix`, backed by
pure-C++17 register/layout helpers in `src/phxaccel/accel/phx_dcn_cursor.h`.

## Status

- **Offline compile-verified**, **CPU unit-tested** under ASan/UBSan, and
  **live Radeon 780M hardware-tested** on macOS 26.7.2 (`25G332`) in native 2x
  HiDPI zero-copy mode (`debug.phxfb_hwcursor` remains default-off `0` until
  opted in).
- Visual inspection of cursor pixels on the physical panel is performed by the
  owner; automated verification confirms register programming, counters,
  zero-copy coexistence, hot-toggle fallback, and zero faults/crashes.

## Design

- **Zero-copy VMID sharing**: HUBP0 shares one `VMID_SETTINGS_0` between
  primary scanout and cursor fetches. `PhxAMDFB` allocates a single physically
  contiguous 128 KiB double-buffered (ping-pong) 128x128 32bpp cursor buffer
  (32 4 KiB pages) and maps those 32 PTEs into the top 32 entries
  (`8160..8191`) of every zero-copy VMID slot's 8192-PTE flat page table
  (`kReservedCursorPages = 32`, reducing `kMaxScanoutPages` to `8160`; a
  2560x1600x4 scanout uses `4000` pages).
- **Atomic VMID/flip synchronization**: Inside `zcFlipTo()`, under the same
  `OTG_MASTER_UPDATE_LOCK` window as `VMID_SETTINGS_0` and
  `PRIMARY_SURFACE_ADDRESS`, `PhxAMDFB` updates `CURSOR_SURFACE_ADDRESS` for
  the target zero-copy VMID slot (or disables the hardware cursor on return to
  VMID 0 / HOME).
- **`IOFramebuffer` integration**:
  - `getAttribute(kIOHardwareCursorAttribute)` reports capability when the
    cursor buffer and full DCN MMIO window are available and un-tripped.
  - `setCursorImage()` converts cursor bitmaps via `convertCursorImage()` to
    unpremultiplied 32bpp ARGB (`kCursorModeColorUnPreMultAlpha`), repacks to
    DCN pitch (64 or 128 pixels), flushes cachelines (`clflush` + `mfence`),
    and programs HUBP0/CNVC0 cursor registers under `OTG_MASTER_UPDATE_LOCK`.
    When disabled, tripped, or outside zero-copy, it disables the hardware
    cursor and returns `kIOReturnUnsupported` so `IOFramebuffer` falls back to
    software cursor rendering.
  - `setCursorState()` clamps negative top-left coordinates into DCN
    `CURSOR_HOT_SPOT`, hides completely offscreen cursors, computes
    `CURSOR_DST_OFFSET` from panel pixel clock when valid, and updates
    position/enable registers under `OTG_MASTER_UPDATE_LOCK`.
  - Power-off (`displayPower(false)`, `setPowerState(0)`), `zcHomeLocked()`,
    and `stop()` disable the hardware cursor before tearing down mappings.

## Controls and rollback

- **Default off**: `debug.phxfb_hwcursor` defaults to `0` (software cursor
  fallback). Enable at runtime with `sudo sysctl -w debug.phxfb_hwcursor=1`
  (once zero-copy is active) or at boot with `phxfbhwcursor=1`.
- **Immediate rollback**: `sudo sysctl -w debug.phxfb_hwcursor=0` immediately
  disables DCN hardware cursor registers and returns to software cursor
  fallback on the next cursor image update.
- **Diagnostics**: read-only sysctl counters `debug.phxfb_hwcur_images`,
  `debug.phxfb_hwcur_moves`, and `debug.phxfb_hwcur_errors`.

## Verification

- `build/tests/test_phx_dcn_cursor` (ASan/UBSan): DCN 3.1.4 register offsets,
  top-32-PTE VA slot layout, `kMaxScanoutPages` boundary, pitch and lines-per-
  chunk selection, control/CNVC bit encodings, offscreen/negative hotspot
  clamping, `dst_x_offset`, and 32bpp row repacking.
- `build/tests/test_phx_dcn_zerocopy`, `make test-upstream34-framebuffer`,
  `make test-upstream34-panel-timing` (including `kIOHardwareCursorAttribute`),
  and `tests/test_build34_dcn_firmware_observer_candidate.py`.
- Offline `src/phxaccel/build.sh` compile of `PhxAccel.kext`.

## Live Radeon 780M hardware test, November 27, 2026

- **Candidate**: `PhxAccel.kext` UUID `DD297165-F4C4-349E-B886-504B95617A4D`
  (SHA-256 `30ad3ec5aba8d78e0aaf274a7020a87dd3e427c9b12d6db92909f5f107baa58f`),
  AuxKC UUID `6EA2A13B-85B2-A931-F5B0-7C8E7B87ECAB` (SHA-256
  `d4f77d901683e993962fe4c0f03bec13c39415591f0b8751698c57bfbc6ba01a`), built
  from `3bc015862a0548db76ff5aab334aaf4d4e9ec93b` with pinned `MacKernelSDK`
  (`3f750085caa17ec3a7880f11c11bf4f48cd6a164`). `PhxBringup` remained build34
  (`2D6C39B3-1A0C-3E7F-979A-2821456A53B3`). Prior v10 `PhxAccel.kext` and AuxKC
  backed up locally for rollback.
- **Post-reboot baseline**: `1280x800` logical / `2560x1600` pixels / `120 Hz`
  / `2x` (`make check-build34-scanout-mode`), `IOFBCursorInfo` published as
  `128x128 32bpp` (104-byte descriptor), `debug.phxfb_zerocopy=1`,
  `debug.phxfb_hwcursor=0`, `zc_faults=0`, `zc_fallbacks=0`.
- **Opt-in activation and stress test (`debug.phxfb_hwcursor=1`)**:
  - Exercised cursor shape transitions (`arrow`, `iBeam`, `crosshair`,
    `pointingHand`, `openHand`, `closedHand`, `resizeLeftRight`,
    `resizeUpDown`), screen corner/edge positions (`(0,0)`, `(1279,0)`,
    `(0,799)`, `(1279,799)`), hide/unhide, and concurrent zero-copy flips.
  - Counters advanced cleanly: `phxfb_hwcur_images=0 -> 41`,
    `phxfb_hwcur_moves=0 -> 119`, `phxfb_zc_flips=506 -> 1178`
    (`nvaccel_iop_flips=1178`, 100% zero-copy), `phxfb_hwcur_errors=0`,
    `phxfb_zc_faults=0`, `phxfb_zc_fallbacks=0`, `phxfb_zc_tlb_flushes=3`
    (unchanged), `nvaccel_iop_fail=0`.
- **Runtime hot-toggle rollback and re-enable**:
  - Setting `debug.phxfb_hwcursor=0` immediately froze hardware cursor counters
    (`41` / `119`) with clean software-cursor fallback and zero errors.
  - Re-enabling `debug.phxfb_hwcursor=1` resumed hardware cursor updates
    (`41 -> 45` images, `119 -> 128` moves, `zc_flips=1483`, `0` errors/faults).
  - `WindowServer` remained on PID `204` with zero new crash/spin reports in
    `/Library/Logs/DiagnosticReports`.
