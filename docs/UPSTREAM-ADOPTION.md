# Downstream adoption of upstream PRs 6-9

Updated 2026-11-12. This tracks source adoption into
`downstream/780m-tahoe`, separately from the temporary pinned-candidate matrix
in `validation/upstream-pr-native-20261112.md`. Passing that older matrix does
not establish that the current downstream combination works on a GPU.

| PR | Reviewed upstream commit | Downstream source status |
| --- | --- | --- |
| 6, sampler slot keys | `55764a0b69658a92870fc2b75e0be3a695382e38` | Adopted in `4d09aa9`; downstream CI `43066219417` completed/success |
| 7, IOSurface keys | `394f162ae7bf5cc9d57bb673a9a6b326c46c325e` | Adopted in `8533c26`; downstream CI `43066748231` completed/success |
| 8, descriptor masks | `5a8a088011946c8089bb27e10d0dba117bf1b48e` | Adopted in `0c594e1`; downstream CI `43067411274` completed/success |
| 9, read-only panel timing | `c9da802a8dbf3753fa15b5cd903934712c3c80f6` | Adopted in `661fd3c`; downstream CI `43068258971` and independent HiDPI CI `43068258882` completed/success |

## PR 6

The five render/compute sampler-key sites use the upstream immutable decimal
keys for indices 0-15. Other `NSUInteger` values retain the original formatting
fallback. Binding validation, dictionary semantics and sampler state/lifetimes
are unchanged. The actual upstream helper and Foundation regression test are
included, with their PolyForm Noncommercial 1.0.0 SPDX notices preserved.
`NVMTLObjects.m` is covered by the existing component licence and required
NullMoth notice. No licence or notice file is changed.

The Makefile target is added to the existing downstream pinned-action native
workflow instead of copying upstream's floating-action/main-only CI job. The
sanitizer test checks 517 indices, immutable key identity, 262144 concurrent
lookups and interchange with legacy dictionary keys. A clean disposable Windows
LF snapshot ran 343 Python tests with 26 platform skips and no failures. The
initial uncommitted snapshot produced 13 clean-source fixture-setup errors;
the successful rerun used a committed disposable snapshot without weakening
those guards.
Downstream run `43066219417` passed both host/native jobs on macOS 15.7.9 /
24G830 with Apple Clang 17.0.0, including the 517-index/262144-lookup sanitizer
test and actual kext/plugin builds and strict signature checks. Ubuntu ran
343 tests with one skip and no failures. There is no measured
desktop latency/FPS claim and no target GPU execution.

## PR 7

The writer registry and synchronization monitor share the upstream integer key
for a 32-bit IOSurface ID and planes 0-255. Full-width string keys are retained
for larger planes, with a distinct key type preventing numeric/string aliasing.
The only integration conflict was adjacent sampler/surface header imports; both
are retained. Existing synchronization, seed/backing guards, weak references
and completion behavior are unchanged.

The component files and helper are covered by `src/nmplugin`'s existing
PolyForm Noncommercial 1.0.0 licence and required notice. The original PR's
tests and `tools/iosurf/surface_sync_probe.m` have no separate notice and fall
under the root MIT-or-GPL-2.0-only rule for other code. Existing licences and
notices are preserved. No external binary or firmware is copied.

The downstream native workflow executes the actual registry/monitor extraction
test under ASan/UBSan: 77 boundary identities and 16384 concurrent cycles,
including replacement, weak lifetime, large-plane identity and monitor release.
It also compiles the optional isolated GPU probe without executing it. Screenshot,
video, multi-window and real IOSurface/GPU acceptance remain pending on target;
the hosted CPU doubles do not establish those behaviors.
The clean Windows LF snapshot ran 343 tests with 26 platform skips and no
failures. Downstream run `43066748231` completed/success for host/native jobs,
including the actual registry/monitor sanitizer test, compile-only probe and
actual kext/plugin builds with strict signature verification.

## PR 8

Review confirmed that set 3 framebuffer-fetch descriptors are bound independently
by the current downstream draw path, as set 2 heap descriptors already are. The
new masks exclude both from ordinary stage snapshots. Invalid/unknown masks,
tessellation and disabled H3 retain their existing conservative fallbacks;
`NVMTL_DESC_MASK=0` selects the legacy mask logic in an isolated process that
preserves that diagnostic control. No shader semantics or synchronization policy
is changed. The original backport provenance comment and the component's
PolyForm notices remain intact. Plain test fixtures/runners without their own
notice use the root MIT-or-GPL-2.0-only rule; generated production harnesses are
not published. Existing licence files are unchanged.

Both Ubuntu and Intel macOS run the actual parser/initializer/snapshot/writer
test with Vulkan API doubles under ASan/UBSan, in unset/0/1 configurations,
using pinned Vulkan headers. Tests cover binding identities, descriptor reuse,
texel/storage buffers, malformed instructions and allocation/address failures.
The synthetic first-write reduction from 193 to 4 is not a measured GPU or
desktop performance result. Real framebuffer-fetch rendering remains pending.
The clean Windows LF snapshot ran 343 tests with 26 platform skips and no
failures. Downstream run `43067411274` completed/success for both host/native
jobs, with 321 descriptor cases per configuration on each host and zero legacy
mismatches. The synthetic first-write counts were 4/193/4 in unset/0/1 modes.
The prior sampler/IOSurface suites and actual kext/plugin compilation/signature
checks also passed; Ubuntu ran 343 tests with one skip and no failures.

## PR 9

The downstream now reads the existing OTG0 timing fields before/after the
existing refresh measurement. Only matching, bounded, progressive fixed-rate
snapshots whose active area matches the boot console produce detailed timing.
Unknown, changing, interlaced or variable modes retain the previous fallback.
The pixel clock is estimated from existing measured/snapped refresh; clock
min/max stay zero. This changes the information returned to IOFramebuffer,
but writes no display registers and changes neither VBL policy nor completion
waits. Native-2x HiDPI flags and physical geometry remain independent.

The only integration conflict was the header insertion; all existing platform,
hardware-policy and HiDPI includes are retained. Current gamma/CLUT refusal
and removal of unsupported gamma advertisements are preserved. All adopted
files are under `src/phxaccel`'s existing PolyForm Noncommercial licence; no
notices or licence files are replaced. The imported 11-field timing fixture is
an upstream test input, not a new observation of this downstream target.

The original decoder's 43 cases are included in the default unit target and an
independent sanitizer target on Ubuntu/macOS. The existing actual framebuffer
callback harness additionally checks detailed timing/fallback, invalid modes,
clock bounds, polarity, cleared reserved data and HiDPI independence. Native
SDK compilation verifies the real types separately from IOKit test doubles.
There is no new mode, higher refresh, EDID/DDC implementation or target display
acceptance claim.
The clean Windows LF snapshot ran 344 tests with 26 platform skips and no
failures. Downstream run `43068258971` completed/success for both host/native
jobs. Ubuntu ran 344 tests with one skip and no failures. Both hosts passed
the decoder's 43 cases, the actual mode/timing/color callback harness and
descriptor configurations. The native job also passed the adopted sampler/
IOSurface tests, compile-only optional probe, actual kext/plugin builds and
strict signature checks. Host macOS was 15.7.9 / 24G830 with Apple Clang 17.0.0;
this is not an installed target Tahoe build. Independent native HiDPI run
`43068258882` passed as well, including actual PhxAccel and the read-only probe.

## Final evidence

`validation/upstream-adoption-20261112.json` records each adopted upstream pin,
downstream source commit, successful focused run/job/step metadata, observed
test counts and the independent final HiDPI run. The earlier eight-candidate
matrix remains historical and is not substituted for these downstream results.
Each code revision's redundant full-stack run was confirmed cancelled and is
not counted as a pass. Native builds retain existing warnings. The one Ubuntu
skip needs an upstream Git object not present in its shallow checkout; Windows
platform skips are not native execution passes.

## Rollback and publication

Each PR is adopted in its own downstream commit so it can be reverted without
rewriting history. Revert dependent later adoptions first if their shared test
or documentation context conflicts. This work does not merge or close the
original GitHub PRs, change `main`, deploy drivers or alter EFI/OS settings.
Source and tests only are published; experimental binaries and raw logs are
not uploaded. The installed target Tahoe build remains unverified.
