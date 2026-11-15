# Default branch: original build 34 plus the VRAM layout correction

## Source identity

The owner requested this default-branch baseline on 2026-11-15.
`upstream34/vram-layout-fix` starts directly at upstream `v0.4.0-alpha`, commit
`9dd76b604fca5e0125bd3caa5723df0f611ff27f`. Its entire `src/` tree is unchanged:
PhxBringup still declares `PHX_KEXT_BUILD 34u`, and the accelerator, Metal
plugin, kernel ABI and kernel build recipes retain their upstream sources.
This branch does not relabel downstream build 39.

The four-file user-tool correction and shared header come from the reviewed
source work recorded by downstream commit
`9c1c37200110a7ba3262c5d669224342c947ad4b`. They are now present in the normal
`tools/phxctl/` source paths, rather than available only as a separate recipe.
The development history remains on `downstream/780m-tahoe`; this operation
does not move that branch or `main`.

## Narrow behavior change

- `mesboot.c` derives the first 128 MiB of GART PTEs, page-table address and
  system-aperture bounds from validated driver metadata. Both default-address
  registers use a zeroed page at VRAM offset `0x2440000`, after the page table
  and before the original KIQ region.
- `phxctl.c` exposes the geometry-derived TOC/TMR words and refuses stale raw
  TOC/TMR values. It retains the original raw TMR offset/capacity of
  128/64 MiB. The different managed `tmr` command is not substituted.
- `bringup5.sh` and `full.sh` retain upstream's successful firmware/power,
  doorbell/CP, GART, MES and queue-step order. They stop on command/pipeline
  failures. The helper wrappers also reject ABI, transport, output-size and
  firmware-status errors, and short firmware files.
- `PhxUpstream34Layout.h` is the shared validator. Both tools require original
  build 34 / ABI 1.12, positive typed metadata, checked 48-bit intervals,
  16-MiB-aligned bases and extent, the original MC base, and a 256-MiB CPU
  aperture. An invalid or unsupported layout is refused before GPU writes.

On the target layout, physical backing is `0x780000000`, with 4 GiB of VRAM;
the upstream reference used `0x6A0000000` and a different extent. The corrected
table/default/TMR physical addresses are `0x782400000`, `0x782440000` and
`0x788000000`; the system-aperture upper register is `0x203fff`. These are
documented results, not literal fallback mappings in the tool.

Upstream watchdog behavior remains the default. The optional
`PHX34_WATCHDOG_ACK` mode is only for a separately verified runner whose
independent deadline has already acknowledged. A file alone does not prove a
live deadline or authorize GPU initialization. Existing experimental tool
overrides are not covered by a general safety claim.

## Checks on 2026-11-15

Observed build host: macOS **26.7.2 / 25G332**, x86_64. This observation is not
a claim about migration to another disk or a fresh hardware acceptance test.

- `make test`: all five original test executables passed. Firmware-dependent
  cases in `test_rdna3_ucode` were skipped because external firmware fixtures
  were absent; they are not recorded as passed.
- `make test-upstream34-layout`: **13 methods passed, zero skips**. The actual
  checked-in helpers are compiled with ASan/UBSan and without linking IOKit.
  The tests reproduce the original bad mapping, verify all 32,768 PTEs and
  relevant default/aperture/TMR registers, and cover admission/error cases.
  Fake shell commands check preserved success order and terminal failures.
- The isolated native build compiled both identical user helpers as x86_64,
  ad-hoc signed them, and verified signatures and architecture. The unchanged
  original unused-variable warning is retained.
- The recipe compares all six pinned/patched upstream inputs plus the shared
  header with the actual checked-in sources. The entire `src/` directory,
  `install/`, `LICENSE`, `LICENSES/` and `THIRD_PARTY_NOTICES.md` were compared
  with the upstream baseline and left unchanged.

The source-only CI runs the original tests plus a macOS helper regression and
native compilation on this branch. It contains no artifact upload or deployment
step. Local results do not establish that a remote Actions run has completed.
Machine-readable evidence is in
[the validation record](validation/upstream34-default-20261115.json).

## Limits, publication and rollback

No driver installation, GPU initialization, desktop takeover, restart, EFI,
NVRAM or OS-security operation is part of the default-branch change. This
source/CPU validation does not establish acceleration, display correctness or
ownership of the selected VRAM offsets. Earlier deployment receipts remain
separate; their uninspected postboot outcome is not converted into a success
claim here.

Root and per-component licences/notices retain upstream bytes: the corrected
bring-up tools use MIT OR GPL-2.0-only, while other unchanged components keep
their own terms, including PolyForm Noncommercial 1.0.0. No other component's
code is imported into this correction. Full-stack binary publication remains
blocked. The separately authorized two-kext and RADV-only manual artifact
policies remain scoped on `downstream/780m-tahoe`; no such workflow is copied
or expanded here.

Repository rollback is to set the GitHub default back to
`downstream/780m-tahoe`, without deleting or rewriting either branch. Preserve
`main`, all development history and the source-fix branch. Repository rollback
does not install or restore any system driver.
