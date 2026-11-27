# Build34 video decode integration

This workstream is source-only on the default `upstream34/vram-layout-fix`
branch. The plugin bridge is opt-in; the RADV capability patch below fails
closed. Neither is an AMD decoder implementation or evidence of hardware
decode support.

## NullMoth reference

The public `nullmoth/nvidia-macos-driver` head reviewed for this change is
`45040e97f705e7de684f8dac45ff71ade72a31ba`. Its plugin describes an AMD/Intel
Vulkan Video provider named `libnmxvt.dylib`, gated by `NMXVT=1`, and calls its
`NMXVT_Register(int)` entry point after selecting an AMD/Intel Vulkan device.
The public plugin also keeps NVIDIA-specific NVDEC registration separate.

The public source tree does not contain `libnmxvt.dylib`, its source, a build
recipe, or a standalone license/provenance record. The public v3.1 Mac release
archive also contains no `libnmxvt.dylib`. The changelog and plugin comments do
not agree on the advertised codec set. This change therefore does not import,
build, distribute, or claim any functionality from that library.

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

The pinned Mesa source includes RADV's general VCN decoder implementation,
but its Darwin backend does not expose VCN queues: `AMDGPU_INFO_HW_IP_INFO`
fills only GFX and compute records. It also returns success for
`AMDGPU_INFO_VIDEO_CAPS` without writing result data. Mesa's shared capability
query treated those arrays as initialized, which could make advertised codec
support depend on uninitialized stack bytes. Patch
`mesa-patches-build34/0008-radv-zero-initialize-video-capabilities.patch`
initializes both result arrays to zero. On the Darwin no-data path this keeps
codec capabilities unsupported rather than inventing support. It does not
create a VCN queue, VCN firmware route, command submission path, VideoToolbox
provider, or hardware decode.

The AMD/Linux Vulkan profile records VCN 4.0.2 and video-decode extensions, but
that does not prove a macOS VCN route. Earlier local Zen observations used
software H.264/HEVC or FFVpx paths. Hardware decode stays unsupported and
unverified until a provenance-reviewed provider and a working Darwin VCN
submission path are available and a separate target-runtime decode test
demonstrates actual hardware acceleration.

The current source-only step adds a bounds-checked parser for the common AMD
VCN firmware container header. It accepts only the exact `vcn_4_0_2.bin`
profile/name pair, the expected 4.0 IP major/minor fields, a supported common
header revision, and an in-file nonempty payload range. Its synthetic CPU tests
cover valid and malformed metadata only. It neither validates firmware
provenance or CRC nor stages, loads, or executes the image. Firmware must not be
bundled or installed by this parser.

The current source-only step also adds a standalone VCN unified-ring encoder
for the `IB`, `FENCE`, `TRAP`, and `END` frame plus 64-dword ring alignment.
`place_unified_submission` checks ring geometry and free capacity before
writing, including wrap at the ring boundary. Like Linux's ring commit path, it
appends NOPs after the frame so the resulting write pointer obeys the VCN
ring's `align_mask = 0x3f` (64 dwords / 256 bytes); frame start itself need not
be aligned. Ring capacity is kept in dwords and one sentinel dword remains
unused. The command values/layout follow the Linux v6.16 VCN
encoder-ring ABI
(`amdgpu_vcn.h`, `vcn_v2_0_enc_ring_emit_ib`,
`vcn_v2_0_enc_ring_emit_fence`, and `amdgpu_ring_alloc`); no Linux driver
implementation was copied. CPU tests exercise encoding, alignment, validation,
wrap, capacity exhaustion, and no-write-on-rejection.

A further CPU-only helper encodes the zero-initialized VCN 4.0 shared structure
used by the Linux v6.16 VCN4 implementation. It lays out the unified-queue,
SMU DPM interface and VCN 4.0.2 DRM-key workaround fields at their reviewed
offsets, with compile-time size/offset assertions, an explicit APU/dGPU
selector and bounded output size. This is layout evidence only: it does not
allocate or map the shared buffer, attest firmware provenance, run the VCN
firmware initializer, write registers, or enable the queue. CPU tests validate
the expected fields, zeroed reserved bytes, and refusal without writes when the
output buffer is undersized. The separate RB_SETUP shared fields are only
initialized by Linux's VCN4 SR-IOV/VF startup path, so this native Radeon 780M
work does not emit or set those VF-only fields.

The unified submission encoder also supports up to a local safety cap of 64
indirect buffers in a single fence/trap/end frame, validates every IB before
writing any output, and retains ring wrap and capacity checks. This matches
the native ABI's repeated-IB packet shape, but does not prove RADV's IB chain
is semantically valid for VCN or that the kernel can execute it.

These helpers are not connected to an adopted VCN queue and do not implement
VCN VM flushes, firmware loading/validation, VCN startup and teardown, doorbell
routing, interrupt/fence retirement, or Vulkan decoded-picture/DPB ownership.
The CPU-only `encode_reg_wait` helper mirrors the four-dword Linux VCN
`REG_WAIT` encoding with output-capacity and register-shift bounds. In Linux
v6.16, `vcn_v2_0_enc_ring_emit_vm_flush` first calls
`amdgpu_gmc_emit_flush_gpu_tlb` and then emits a `REG_WAIT` for the VMID's
page-table-base register. Darwin currently has neither that GMC ring-emission
route nor an adopted VCN ring/VM-hub register mapping; emitting only the wait
would not invalidate translations. This helper does not complete a VM flush,
and no GFX/compute flush is treated as a substitute.

The pinned Mesa transport currently rejects non-GFX/compute IP submissions in
the exact-completion path, and the PhxBringup queue owner exposes only GFX and
compute rings. The Linux VCN 4.x reference uses a VCN unified queue; queue
startup requires VCN firmware/shared-state initialization, queue/ring setup and
VCN-specific register/doorbell state. Decode also needs a VCN completion source
and explicit decoded-surface/reference-picture lifetime management. The
existing PSP GFX firmware loader and GFX/compute ring path are not substitutes
for these VCN-specific operations. No VCN registers, firmware mailboxes, queue
state or GPU execution are changed by this step.

## Validation and next gate

The plugin CPU tests cover AMD-only, exact opt-in, WindowServer exclusion, and
process-name handling; source checks verify the loader boundary and that the
bridge does not claim hardware acceleration. The Mesa patch test applies the
one-line source patch to the exact pinned `ac_video.c` input and compiles the
actual initialized capability-array declaration as a CPU-only check. These
tests do not load a provider, initialize Vulkan, submit GPU work, or test a
VideoToolbox session. `test_rdna3_vcn_firmware` exercises synthetic valid and
malformed container headers only; it does not consume a real firmware image.
`test_phx_vcn_queue` exercises the standalone CPU IB/fence and `REG_WAIT`
encoders and shared-structure layout only; it does not flush a VM, adopt or
submit a queue, or execute GPU work.

The next implementation gate is a reviewed Darwin VCN route: connect the
exactly identified firmware through a provenance-reviewed load path, implement
VCN-specific unified-queue startup/submission/completion, and prove
synchronization plus decoded-surface/DPB ownership. Separately obtain provider
source and complete license/build provenance (or implement an independently
auditable VideoToolbox provider against the exact RADV runtime), then confirm
codec/profile support and the output-buffer contract. An isolated build34 VCN
candidate installation/load and finite GPU decode validation have since been
explicitly authorized in `BUILD34-SCOPE.md`; that authorization does not make
the current incomplete path deployable, authorize automatic deployment, or
count as decode evidence. No candidate has been installed or VCN decode task
submitted in this step.
