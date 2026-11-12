# Firmware-framebuffer display capability limits

PhxAMDFB currently exposes one firmware-backed physical mode with software VBL
and CPU-copy presentation. The opt-in native-2x HiDPI candidate changes mode
flags only; it does not create extra timings or a downsampling engine. Its
read-only probe still needs actual target logical/backing observations.

The adopted read-only panel-timing path validates stable OTG0 snapshots against
the boot raster and reports detailed timing only for supported fixed-rate,
progressive modes. Otherwise it keeps the previous fallback. Its pixel clock is
estimated from measured/snapped refresh, with unknown min/max bounds left zero.
This supplies metadata for the existing physical mode; it does not program a
new mode, increase refresh, implement hardware EDID/DDC or change HiDPI geometry. Current
downstream test status and licence/provenance are in `UPSTREAM-ADOPTION.md`.

Both `setGammaTable` overloads and `setCLUTWithEntries` used to return success
without applying a table. They now return `kIOReturnUnsupported`. No hardware LUT
programming path exists in this downstream framebuffer, and a successful color
update must not be reported when nothing changed. Input memory is untouched.
This is a reporting correction, not implementation of calibration, Night Shift,
HDR, hardware EDID/DDC, backlight or external-output support. How CoreDisplay responds to
this refusal during target login/calibration remains unverified.

`tools/test_hidpi.py` compiles the actual mode/timing callbacks and all three color
callbacks with IOKit fakes under ASan/UBSan. It retains native-2x geometry/refresh
and mode validation checks, and checks color refusal for null, zero, normal and
maximum counts without reading/writing caller buffers. The actual PhxAccel kext
is separately compiled and signed by focused CI. Neither is target display
validation; record the installed target OS build and physical observations
before accepting display behavior.

Separately, `PhxAMDFB` implements native cached EDID/DDC callbacks from a
validated GPU-local bootloader/firmware property; see `EDID.md`. This does not
read AMD AUX/I2C or discover a panel without supplied data. It preserves the
existing mode and no-data fallback. Native CI/target acceptance are tracked
separately from the older timing and gamma work above.

Rollback: revert the isolated reporting/test commit. This repository change
does not deploy a driver, change the boot mode or modify an installed override.
