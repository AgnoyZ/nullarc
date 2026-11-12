# Explicit compatibility for legacy PhxBringup boot tools

Status: experimental source compatibility; no target GPU execution or memory
ownership proof. Never install a candidate over the working EFI as part of a
repository build. The opt-in below is deliberately absent from the kext plist.

## Why a kext-only replacement can fail

The old `bringup5.sh` creates a ring without selector 114, submits raw LOAD_TOC
and SETUP_TMR, then uses managed firmware loading and autoload. The newer driver
requires a configured layout before ring creation and TOC-observed TMR readiness
before engine loading. The old raw commands do not establish that readiness.
Old helpers can hide these failures and continue until queue adoption/claim fails.
The raw TMR physical address in the reference script is also machine-specific.

This revision adds an **explicit** startup profile and translates just these two
legacy raw commands into the same checked TOC/TMR methods as the managed API.
There are no new boot-arg address defaults, ABI selectors, watchdogs or restarts.
Without the profile, existing managed checks and raw research behavior remain.

## Startup property contract

`phx-legacy-boot` is a 128-byte Data property on the GPU's PCI provider. The
little-endian words, defined by `src/PhxLegacyBoot.h`, are:

| Word | Meaning |
| --- | --- |
| 0 | Version, exactly 1 |
| 1 | Flags, exactly 1 (legacy raw PSP translation) |
| 2–5 | Expected MC base, UMA backing physical base, VRAM bytes, BAR0 aperture bytes |
| 6–7 | Operator-declared console offset and span in VRAM |
| 8–15 | The existing 64-byte `PhxPspLayout` descriptor, version 1 and zero reserved words |

The profile is accepted before service publication only when `phxdebug=1` and
the existing Darwin 25 / PCI 1002:1900 / `phx780m=1` gate passes. All four geometry
words must match the driver's observations exactly. The PSP layout validator,
1 MiB MC **and** backing-physical TMR alignment, and disjoint console/PSP spans
are mandatory. A live ring, staging area, TMR, adopted queue or terminal PSP fault
prevents reconfiguration. Metadata configuration performs no hardware writes.
Invalid type/size/content leaves compatibility disabled at startup; no guessed
profile is substituted.

Console offset/span are operator assertions, not discovered or reserved memory.
The checks cannot detect an omitted/incorrect console span or other firmware
allocations. Independently establish ownership and exclude **all** live regions
before any ring creation or staging. This feature does not fill that allocation
gap and does not make the legacy scripts a checked initialization workflow.

Service diagnostics are `phx-legacy-boot-status` (present if a property was
supplied; zero means accepted) and `phx-legacy-boot-startup-enabled` (the startup
decision). A later successful selector 114 configuration disables translation
and returns to the managed workflow; the startup diagnostic remains historical.
Clearing/destroying the ring retains the profile and compatibility choice but
does not clear the existing terminal PSP fault latch.

Before issuing any GPU commands, verify the exact Data bytes on the GPU's live
PCI provider, status zero, and startup-enabled true. An absent status is different
from a nonzero rejection status: first check property delivery and the actual
provider. A property in the EFI device-properties blob or a correct on-disk
config does not prove that macOS attached it to that provider. Verify every PCI
path hop and the live ACPI root `_UID`; do not assume `PciRoot(0x0)` from an
existing example or an older EDID entry. Keep automatic initialization blocked
while these checks fail. The startup property is read only during driver start,
so correcting its routing requires another operator-controlled boot before
acceptance can be retested.

## Translation rules

- Raw LOAD_TOC (`0x20`) must point into the configured staging area, with zero
  unused words. The common locked TOC method checks bounds and alignment, waits
  for completion and records the nonzero firmware-reported required TMR size.
- Raw SETUP_TMR (`0x5`) must specify the configured TMR MC address, **exactly** its
  configured reserved capacity and flags `0x2`. The driver submits the observed
  required size only if it fits that capacity, and derives the backing address
  as `fbPhys + tmrOffset`. The two old physical-address words are ignored and
  never forwarded. Only successful completion establishes managed readiness.
- Other raw commands are rejected in compatibility mode, so they cannot bypass
  the managed TMR state. Managed firmware load/autoload still require readiness.
- The translation and managed operation share one SMU lock. No recursive lock,
  unlock/relock interval, fabricated completion, retry after timeout or disabled
  fence/status checks is introduced. Existing root, HELLO and debug RPC checks
  remain mandatory.

This is a bridge for the old PSP command sequence only. Firmware authentication,
MES/GART/queue reference constants, script error handling, installed PhxAccel,
Metal/runtime compatibility and real execution remain separate acceptance work.

## Offline preparation (no installation)

Place reviewed per-machine values in an ignored local JSON under `build/`.
Supply **all** these fields, as unsigned integers or decimal/hex strings; there
are intentionally no example target addresses:

```text
mc_base, physical_base, vram_bytes, aperture_bytes,
console_offset, console_bytes,
ring_offset, tmr_offset, tmr_capacity, staging_offset, staging_capacity
```

`physical_base` is the UMA backing base, never BAR0's CPU physical base. Console
and reserved spans must cover the full allocations, rounded out to pages. The
script checks numeric bounds, alignment, overlap, duplicate/unknown JSON fields
and the GPU PCI path. It does not read hardware or establish ownership.

```sh
python3 tools/phx_legacy_boot.py build/reviewed-layout.json \
  --gpu-path "$VERIFIED_GPU_PCI_PATH" --out build/legacy-review
```

This creates only `legacy-boot.bin`, a minimal `DeviceProperties.plist` fragment
and `plan.json`, in a fresh repository `build/` subdirectory. It refuses external,
symlink-escaped or existing output paths. It never reads/writes EFI, NVRAM,
installed tools or drivers, never starts the GPU, and never restarts the machine.
The fragment is **not a complete OpenCore config**. Keep it private. Reviewing
and merging it into an isolated test boot setup is a separate operator action.

For a test, retain the known working kext and config, preserve rollback access,
and verify the accepted profile, TOC size, TMR completion, firmware loads and
queue/claim results in order. The reference scripts can swallow errors and arm
reboots; do not infer success from their exit status. On a PSP timeout/error,
stop; the new instance remains faulted. Revert the candidate and its property
for rollback. Restart only by the operator's explicit action.

## CPU evidence and build limits

`tools/test_psp_submission.py` extracts the actual kernel bodies, including the
startup configurator, raw translator and common locked TOC/TMR helpers. Its
synthetic tests cover the old sequence (profile, destroy/create, stage, raw TOC,
raw TMR, firmware load, autoload), wrong geometry, spans/alignment, unchanged
memory on rejection, default behavior, derived physical address, TOC capacity,
exclusive access and terminal faults. ASan/UBSan and fake locks catch memory
errors and recursive locking. No actual firmware, panel data or personal layout
is a fixture. `test_legacy_boot_tools.py` checks generated bytes against the
shared C++ validator and tests offline-output confinement.

The manual two-kext artifact workflow runs these checks before native Intel
compilation and packaging. A passing test/build is not evidence of a working
GPU, accelerated desktop, correct EDID dimensions or a safe memory reservation.

For source `c5c22b420aa8990eff90df4cbddd29815793ecf6`, all 394 Python checks,
125 actual PSP-method cases, 73 queue-adoption cases and 114 firmware-sequence
cases passed locally. Manual Intel artifact run `43188218248` succeeded; both
downloaded kexts passed strict signature verification and all 24 inner package
checksums matched. The sanitized record is
[`validation/legacy-boot-20261112.json`](validation/legacy-boot-20261112.json).
These results cover the source revision named there, with no target deployment.

A later, separately authorized load-only target boot is recorded in
[`validation/legacy-boot-load-only-20261112.json`](validation/legacy-boot-load-only-20261112.json).
The candidate loaded, but the provider did not receive the profile: the EFI
property path used a different root UID from the live ACPI root. Only that
profile's path was corrected and read back; the corrected startup acceptance
still awaits another manual boot. No GPU initialization or acceleration test
was performed in this stage.
