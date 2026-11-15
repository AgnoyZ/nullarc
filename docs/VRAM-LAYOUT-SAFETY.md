# Reject reference-machine physical mappings

2026-11-15: source correction for the owner's reported original-layout risk.
This is a downstream change, not a byte-identical upstream release. It has not
been installed or exercised on the GPU. The installed original stack and the
closed original-only trial remain unchanged; the recovered GPU-off state must
not be cleared by repository validation.

## Confirmed mismatch

The retained original-driver metadata reports this geometry:

| Quantity | Target | Pinned reference recipe |
| --- | --- | --- |
| GPU MC base | `0x8000000000` | `0x8000000000` |
| UMA backing physical base | `0x780000000` | `0x6A0000000` |
| VRAM extent | `0x100000000` (4 GiB) | `0x180000000` (6 GiB) |
| CPU-visible aperture | `0x10000000` (256 MiB) | Not a substitute for either backing base or VRAM extent |

The target backing interval is `[0x780000000, 0x880000000)`. Using the old
physical base for even the first 128 MiB of GART PTEs selects pages below this
interval. Independently, the old MC aperture upper register `0x205fff` describes
a 6-GiB range; a 4-GiB range at this MC base ends at register value `0x203fff`.
Changing just one base literal would leave the extent/default/TMR hazards.
These metadata values are geometry observations, not proof that every page in
the interval is free of console, firmware or other live allocations.

## Corrected paths

- `mesboot` starts with zero MC/backing variables. Only validated driver
  metadata populates them. Missing/wrong-type, zero, non-16-MiB-aligned,
  out-of-48-bit or overflowing geometry is refused. The 16-MiB granularity
  matches `PhxBringup::readFbLayout`'s hardware-register publication.
- `PHX_LAYOUT_REFERENCE` can no longer override the gate, including for legacy
  commands. Legacy commands require the complete reference base/base/extent
  tuple and remain unsupported on this target. They do not become portable
  merely because their MC base matches.
- The existing explicit GART path uses selector 116's validated snapshot for
  every PTE, page-table base, system aperture and both default-page registers.
  Table/default writes must fit both VRAM and the CPU aperture, remain within
  the write selector's width and avoid the PSP regions. No target physical
  literal is introduced as a fallback, and the bootstrap map remains explicitly
  bounded rather than mapping all 4 GiB through the CPU window.
- PSP selector 107 no longer forwards arbitrary caller words to firmware when
  compatibility is disabled. It returns unsupported without MMIO/frame writes.
  The explicit compatibility profile still translates only TOC/TMR through
  the managed validators. TMR backing is derived as `fbPhys + tmrOffset`;
  stale physical words from a legacy caller never reach firmware. The normal
  managed layout/TOC/TMR selectors and their wire sizes are unchanged.
- Repository `bringup5.sh` no longer carries raw PSP words, firmware offsets or
  reboot timers. It requires six explicit arguments and delegates to the
  existing `phxctl gfx-power-sequence` command, which authenticates the generated
  firmware profile and validates the relative PSP regions against kernel
  geometry. Missing arguments/helper are terminal; there is no old-recipe
  fallback. This uses the checked downstream power sequence and is not an
  assertion that the original startup order was preserved.

The old `full.sh` invocation supplies no explicit regions and therefore now
stops at this wrapper before its watchdog/CP/GART stages. It is still a retired
reference workflow, not a deployment recipe. A matching downstream helper and
kext, explicit reviewed regions and an independent bounded runner are required
for any separately staged hardware test. An original build-34 kernel does not
implement the newer managed selector contract; do not mix it with this wrapper
or treat this source correction as a live installation.

## Validation and limits

The layout regression failed against the previous source before the correction.
The working-tree tests use the actual C entrypoints and extracted kernel
methods with fake IOKit, MMIO, firmware, memory and locks under ASan/UBSan.
They include the target's 4-GiB/256-MiB geometry and independent literal checks
for its first/last PTE, page-table base, MC aperture end and both default pages.
PSP tests verify that a stale caller physical address is replaced by the target
backing address, and that the disabled raw path changes no memory/registers.
The shell wrapper is exercised only with a synthetic file-writing helper.
See [the sanitized validation record](validation/vram-layout-safety-20261115.json)
for the completed checks and source hashes.

These are source arithmetic, refusal and control-flow checks. They do not prove
exclusive VRAM ownership, real PSP/GPU execution, recovery from a bus hang or
a working accelerated desktop. In particular, they do not establish the cause
of the separately observed CoreDisplay assertion. No GPU service is opened by
these tests, and no driver/startup deployment, display arming, EFI/security
change or reboot is part of this correction.

Rollback is a normal follow-up revert of the source commit; it does not change
installed files or reactivate a consumed experiment. Keep the currently verified
original installation inactive until a separate reviewed deployment/test scope
selects the exact candidates and rollback procedure. No binary publication is
added by this change; existing component licences and artifact restrictions
remain in force.
