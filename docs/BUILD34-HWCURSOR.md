# Build34 DCN 3.1.4 hardware cursor (opt-in)

This change adds an opt-in DCN 3.1.4 hardware cursor path to `PhxAMDFB`
(`src/phxaccel/accel/phxfb.cpp`) on `upstream34/vram-layout-fix`, backed by
pure-C++17 register/layout helpers in `src/phxaccel/accel/phx_dcn_cursor.h`.

## Status

- **Offline compile-verified** (`PhxAccel.kext` built cleanly against pinned
  `MacKernelSDK`) and **CPU unit-tested** under ASan/UBSan.
- **Not yet installed or hardware-validated on live Radeon 780M silicon.** Do
  not claim live cursor rendering, latency, or glitch-free behavior until
  explicitly tested on hardware.

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
