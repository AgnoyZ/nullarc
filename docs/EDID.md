# Supplied-panel EDID support

2026-11-12: `PhxAMDFB` now implements `hasDDCConnect()`, `getDDCBlock()` and
the high-level DDC-sense query for a validated, boot-time EDID snapshot.
This is a candidate implementation; native CI and target acceptance are
recorded separately. No driver is installed by this change.

## What is implemented

- On the already-gated Darwin-25 / PCI `1002:1900` framebuffer, read an
  `OSData` property directly from **its own GPU provider**, in this order:
  `phx-edid`, `AAPL00,override-no-connect`, then `IODisplayEDID`.
- Missing properties fall through. The first **present** property is
  authoritative: wrong type, invalid bytes or a raster mismatch fail closed,
  without silently selecting a lower-priority source.
- Require EDID 1.0..1.4, the standard header, 1..32 complete 128-byte blocks,
  exact extension count, every block checksum, and a progressive base-block
  detailed timing with the same physical width/height as the boot raster.
  A timing described only in a CTA/DisplayID extension is conservatively
  rejected. The driver neither trims bytes nor repairs checksums.
- Copy accepted bytes into a bounded 4096-byte per-framebuffer cache **before**
  `IOFramebuffer::start()`. It is immutable once callbacks can run, including
  during stop. Provider changes cannot race a partially updated snapshot.
- Publish the exact `IODisplayEDID` on the framebuffer; return one unchanged
  128-byte block per native DDC callback for connection zero. Block numbers
  are one-based. IOGraphics can then build its native display information from
  that EDID rather than relying on a separate display-personality injector.
- Reject wrong connections, block zero/out-of-range/overflow, short buffers,
  null pointers, non-EDID requests and nonzero options. Failure leaves caller
  bytes and length unchanged. An unavailable/stopping cache reports unsupported.
- Expose only source/status/length diagnostics in the new log messages:
  `PhxFBEDIDSource`, `PhxFBEDIDStatus`, `PhxFBEDIDBytes`, `PhxFBEDIDValid`.

**This is not an AMD AUX/I2C hardware reader.** No NVKMS, register writes,
global registry searches, synthesized identities, fake EDID, DDC/CI controls,
new timings or mode/refresh programming are introduced. Existing display
gates, physical scan-out geometry and HiDPI policy remain unchanged.
Without a supplied property the previous no-EDID behavior remains. A property
called `IODisplayEDID` does not itself prove that firmware read the panel.
The operator must establish the data's origin and that it belongs to this panel;
matching raster geometry is not independent monitor identification.

## NullMoth reference and licence audit

Pinned reference: `nullmoth/nvidia-macos-driver`
`7412cdde81447f78da0ebb64216dc258d8beaedb`.

- `kexts/NVRMFB/fb/nvrm-fb.cpp`: `takeEdid()`, `hasDDCConnect()`,
  `getDDCBlock()`, and `kConnectionSupportsHLDDCSense` show IOGraphics' cached
  EDID interface. Its actual display discovery comes from NVIDIA NVKMS;
  that hardware transport is not portable to this AMD framebuffer.
- `kexts/NVRMFB/fb/nvrm-fb-safety.h`: reviewed the override checks for block
  length/header/count/checksums. Our checks and bounded cache are implemented
  here independently; no NVIDIA display, AUX or installation code is copied.
- The reference root `LICENSE` is PolyForm Noncommercial 1.0.0 with
  `Required Notice: Copyright (c) 2026 NullMoth Systems (https://nullmothsystems.com)`.
  Root `NOTICE` was reviewed for NVIDIA kernel interfaces/firmware,
  NMIntelFB's separate Intel display provenance and the EDID-override idea.
  None of those vendor components is imported. The new component header keeps
  the existing PhxAccel PolyForm terms and required notice. Root `LICENSE`,
  `LICENSES/` and `THIRD_PARTY_NOTICES.md` remain intact.
- Native SDK signatures are compiled against pinned MacKernelSDK
  `3f750085caa17ec3a7880f11c11bf4f48cd6a164`. Public CI does not upload binaries.

## Prepare private, real EDID data without installing

Read EDID from the **same physical panel** using Windows/Linux or a working
display driver. Keep raw data, personal EFI and any resulting fragments local
and ignored; do not commit them to this public repository. Do not use the
synthetic bytes from tests as a real monitor's identity.

```sh
python3 tools/phx_edid.py check /path/to/private-panel-edid.bin --native 2560x1600
python3 tools/phx_edid.py prepare /path/to/private-panel-edid.bin \
  --native 2560x1600 \
  --device-path 'PciRoot(0x0)/Pci(0x8,0x1)/Pci(0x0,0x0)' \
  --out build/edid-review
```

The dimensions and GPU path above are **syntax examples**. Verify both on the
target; the tool does not discover them or establish hardware ownership.
`prepare` writes `DeviceProperties.plist`, `edid.bin` and `plan.json` only to
a fresh directory under this repository's `build/`. It refuses existing
outputs, system/unrelated paths and build symlinks pointing outside the repo.
The plist is a **merge fragment**, never a replacement for `config.plist`.
It contains one `phx-edid` Data value under the supplied GPU path. The tool
does not edit an EFI or install anything; all deployment/test flags start false.

Some Windows registry exports append undeclared all-zero blocks. An explicit
`--trim-zero-padding` allows removing only those complete trailing blocks,
then runs all checks. Nonzero tails, truncated data, oversized input and bad
checksums are refused. Never silently fix a checksum or alter timing bytes.

## Tests and acceptance

```sh
python3 -m unittest discover -s tests -p 'test_edid_tools.py' -v
python3 tools/test_edid.py
python3 tools/test_hidpi.py
bash src/phxaccel/build.sh /path/to/pinned/MacKernelSDK
codesign --verify --strict src/phxaccel/build/PhxAccel.kext
```

`tools/test_edid.py` compiles the **actual** EDID loader and callbacks extracted
from `phxfb.cpp`, plus the real cache header, with ASan/UBSan and fake IOKit.
Synthetic fixtures cover source precedence, type/validation/publication
failure, reference balancing, private snapshot behavior, every single-byte
corruption of a base block, extension reads, bounds/overflow, preserved caller
guards/length and shutdown refusal. This is CPU evidence, not a kernel-load
or physical display test. The focused native workflow is
`.github/workflows/edid-validation.yml` on `macos-15-intel`.

The initial native run `43161244093` passed the synthetic tool/callback checks
but failed the real kext compilation: the pinned SDK's raw-data `setProperty`
overload takes `void *`, while the cache exposes `const uint8_t *`. The call now
uses an explicit const cast for that copying API, and the IOKit double takes
the exact non-const signature so it no longer hides the mismatch. Corrected
native results are recorded separately; the first run is not a build pass.

For a separately approved target test, preserve a working EFI, identified
driver/kernel-collection backups and recovery path. Deploy only a reviewed
candidate through the existing separate EFI procedure; add the verified
private property manually. Disable any earlier codeless display EDID injector
for this comparison so its child property cannot be mistaken for this driver.
Record the actual Tahoe OS build and candidate source/build identity.

1. Confirm the intended boot mode and an active PhxAMDFB. Inspect only the
   metadata publicly: `ioreg -r -c PhxAMDFB -d 1 -l | grep 'PhxFBEDID'`.
2. With the valid property, require `Status=valid`, the exact expected byte
   count and true validity. Privately compare framebuffer and native display
   `IODisplayEDID` byte-for-byte with the source; check that display vendor and
   product IDs now come from it. Do not publish the raw registry or EDID.
3. Verify visible desktop, unchanged physical mode/refresh and existing
   brightness/sleep/wake behavior. This does not establish HiDPI success.
4. In a separate controlled boot without the property, require the former
   no-EDID fallback and no fabricated monitor information. Do not test corrupt
   data on the live system just to repeat a host-fixture case.

Rollback: restore the previously identified driver/kernel collection and remove
only this added GPU property using the separate EFI procedure. Revert the
isolated source commit to remove this feature from a future build. This task
does not change installed EFI, NVRAM, security settings or the running driver.
