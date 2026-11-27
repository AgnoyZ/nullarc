# Build34 video decode integration

This is a source-only, opt-in registration bridge for the default
`upstream34/vram-layout-fix` branch. It is not an AMD decoder implementation
and does not establish hardware decode support.

## NullMoth reference

The public `nullmoth/nvidia-macos-driver` head reviewed for this change is
`45040e97f705e7de684f8dac45ff71ade72a31ba`. Its plugin describes an AMD/Intel
Vulkan Video provider named `libnmxvt.dylib`, gated by `NMXVT=1`, and calls its
`NMXVT_Register(int)` entry point after selecting an AMD/Intel Vulkan device.
The public plugin also keeps NVIDIA-specific NVDEC registration separate.

The public source tree does not contain `libnmxvt.dylib`, its source, a build
recipe, or a standalone license/provenance record. The changelog and plugin
comments do not agree on the advertised codec set. This change therefore does
not import, build, distribute, or claim any functionality from that library.

## Local bridge

`NVMTLDevice.m` can load a locally supplied `libnmxvt.dylib` beside the plugin
only when all of these conditions hold:

- `NMXVT=1` is present in the process environment; it is off by default.
- The selected Vulkan vendor is AMD (`1002`), and the process is not
  `WindowServer`.
- The library is a regular file owned by root, in a root-owned directory that
  is not group- or world-writable; symlinks are refused.
- The library exports `NMXVT_Register` and reports successful registration.

The bridge does not add `VTIsHardwareAccelerated`, register a decoder directly,
or change NVIDIA's existing registrations. The external provider owns codec
capability reporting and must itself fail safely so VideoToolbox can retain
its existing fallback.

The current AMD/Linux Vulkan profile records VCN 4.0.2 and video-decode
extensions, but it is not evidence that the exact macOS RADV runtime exposes
those extensions or that a VideoToolbox session decodes on VCN. Earlier local
Zen observations used software H.264/HEVC or FFVpx paths. Hardware decode stays
unsupported/unverified in the project status until a provenance-reviewed AMD
provider builds and a separate target-runtime decode test demonstrates actual
hardware acceleration.

## Validation and next gate

The CPU tests cover AMD-only, exact opt-in, WindowServer exclusion, and
process-name handling; a source check verifies the loader boundary and that
the bridge does not claim hardware acceleration. They do not load a provider,
initialize Vulkan, submit GPU work, or test a VideoToolbox session.

Before runtime testing, obtain the provider source and complete license/build
provenance (or implement an independently auditable provider against the exact
RADV runtime), confirm its codec/profile support and output-buffer contract,
then prepare a separate test scope. Do not install or auto-load a provider as
part of this source-only change.
