# Scope and notices for the two-kext test artifact

Review date: 2026-11-12. The owner explicitly requested CI uploads for these
two kexts. This scoped review covers the in-tree component build recipes,
source notices and pinned MacKernelSDK, not a full release or legal opinion.
The experimental, noncommercial artifact is separate from full-stack releases.

- PhxBringup: root LICENSE offers MIT or GPL-2.0-only, subject to file notices.
  The archive carries both complete texts and the exact component sources.
- PhxAccel, including reconstructed IOGraphics/IOAccelerator declarations:
  existing NullMoth-derived PolyForm Noncommercial 1.0.0 terms remain in force.
  The complete terms and required notice accompany the kext and its sources:

  Required Notice: Copyright (c) 2026 NullMoth Systems (https://nullmothsystems.com)

- `src/amd/phx_topology.h` declares MIT. `PhxNativeABI.h` attributes layout
  definitions to the Navi48 project under BSD-3-Clause and Linux/Mesa values
  under MIT, whereas root THIRD_PARTY_NOTICES calls the Cobalt64 contribution
  MIT. The pinned Cobalt64 root licence at
  `d6c9aedf8e6526a39e349b5886cbc8c7ddf77f65` is MIT; its referenced
  `src/navi48-bringup/src/Navi48NativeABI.h` has no overriding licence header.
  Preserve the downstream attribution and its BSD statement as well as the
  upstream MIT notice; do not silently relicense the ABI. The supplementary
  BSD text accompanies these artifacts. This review records the inconsistency
  rather than treating the root summary as a complete per-file licence map.
- MacKernelSDK is pinned to
  `3f750085caa17ec3a7880f11c11bf4f48cd6a164`. Its APSL-2.0 LICENSE.txt and
  original notices in Headers and Library/kmod are preserved in the source
  archive. The component recipes link its startup library and host compiler
  support libraries. The artifact includes the SDK header/startup sources;
  it does not redistribute macOS kernels, system kexts, Xcode, or the SDK's
  prebuilt library archives. Host compiler version and SDK pin are recorded.
  SDK and per-file terms remain distinct from PhxAccel's terms.

No Metal plugin, translator, Mesa, LLVM runtime, AMD firmware, AppleHDA,
OpenCore, other kexts or installation scripts are included. Source archives
are an allowlisted export of committed project files and SDK source, not
raw user material. Existing LICENSE, LICENSES and THIRD_PARTY_NOTICES texts
are retained unchanged. The full-stack publication audit remains open;
this manual two-kext artifact is the owner-authorized limited exception.

Sources reviewed: root LICENSE and THIRD_PARTY_NOTICES; both component build
scripts; in-tree source/header notices; pinned Cobalt64 LICENSE and ABI header;
pinned MacKernelSDK README, LICENSE.txt and Library/kmod source layout.
