# Firmware-framebuffer display capability limits

PhxAMDFB currently exposes one firmware-backed physical mode with software VBL
and CPU-copy presentation. The opt-in native-2x HiDPI candidate changes mode
flags only; it does not create extra timings or a downsampling engine. Its
read-only probe still needs actual target logical/backing observations.

Both `setGammaTable` overloads and `setCLUTWithEntries` used to return success
without applying a table. They now return `kIOReturnUnsupported`. No hardware LUT
programming path exists in this downstream framebuffer, and a successful color
update must not be reported when nothing changed. Input memory is untouched.
This is a reporting correction, not implementation of calibration, Night Shift,
HDR, EDID/DDC, backlight or external-output support. How CoreDisplay responds to
this refusal during target login/calibration remains unverified.

`tools/test_hidpi.py` compiles the actual mode callback and all three color
callbacks with IOKit fakes under ASan/UBSan. It retains native-2x geometry/refresh
and mode validation checks, and checks color refusal for null, zero, normal and
maximum counts without reading/writing caller buffers. The actual PhxAccel kext
is separately compiled and signed by focused CI. Neither is target display
validation; record the installed target OS build and physical observations
before accepting display behavior.

Rollback: revert the isolated reporting/test commit. This repository change
does not deploy a driver, change the boot mode or modify an installed override.
