# Isolated build-34 A1/A2/A3 backports

Owner request: 2026-11-16. Candidate branch: `backport/upstream34-a1-a3`,
based on default checkpoint `90bb06f6f9255cb5a16cc5eb87e78032566b2000`.
The default branch itself is unchanged. Complete A1 tests before changing A2,
then complete A2 tests before changing A3. Each stage is a separate commit.

The original build-34 `src/phxbringup`, native ABI, user helpers, firmware
sequence and geometry correction stay byte-identical to the baseline.
Existing licence/notice files are preserved. No driver is installed, loaded,
or initialized by the tests, and no GPU submission or display takeover occurs.
Host-test success is not hardware acceptance or an FPS measurement.

## A1 — plugin keys and descriptor masks

Selected source and tests from downstream `4d09aa9`, `8533c26`, `0c594e1`.
Reviewed upstream origins: `55764a0b69658a92870fc2b75e0be3a695382e38`,
`394f162ae7bf5cc9d57bb673a9a6b326c46c325e`,
`5a8a088011946c8089bb27e10d0dba117bf1b48e`.

Sampler slots 0–15 share immutable decimal strings; other indices keep the
legacy formatting. Surface writer and monitor lookups use compact keys while
retaining distinct full-width large-plane identities. These are allocation/key
optimizations with equivalent identity semantics, not established rendering fixes.
Ordinary descriptor snapshots exclude independently bound framebuffer-fetch
set 3 as well as heap set 2. Existing conservative fallbacks remain.
The CPU fixtures cover `NVMTL_DESC_MASK=0` legacy behavior. The release plugin's
existing constructor clears inherited `NVMTL_*` variables, so setting a shell
variable alone is not a verified runtime rollback: an isolated diagnostic probe
would need to restore it after loading and before first use, or revert A1.

Source/helper files remain covered by `src/nmplugin`'s PolyForm Noncommercial
1.0.0 terms and required NullMoth notice. The sampler fixture retains its SPDX;
other test files use their existing root/component terms. No external binary,
firmware or runtime library is imported or published.

Reproduce on Intel macOS with the Vulkan-Headers checkout at
`6802bb4733b63ed5efd3adb308a6c885ef180ea1`:

```sh
python3 tools/test_upstream34_backport.py \
  --vulkan-headers /path/to/Vulkan-Headers --out build/backport-a1
```

The gate runs the baseline unit and geometry suites, actual Foundation sampler
and IOSurface registry/monitor bodies, and actual descriptor parsing/snapshot/
writer bodies in unset/0/1 modes under ASan/UBSan. The production plugin is
compiled and linked for x86_64, ad-hoc signed, checked for its device exports,
and signature/architecture verified without loading it. Raw logs/binaries stay
ignored under `build/`; only sanitized result summaries are committed.

2026-11-16 gate: **passed**, macOS 26.7.2 / 25G332, Apple Clang 21.0.0.
The original unit suite passed (firmware parser inputs absent: that portion
explicitly skipped); all 20 geometry/script tests passed. ASan/UBSan checked
517 sampler indices/262,144 lookups, 77 surface identities/16,384 concurrent
cycles, and 321 descriptor cases in each unset/0/1 mode with zero legacy
mismatches. Full plugin compilation/link/signature/export checks passed,
retaining 336 existing compiler warnings; this is not a warning-free build.
All 172 protected baseline files matched. Sanitized evidence:
`validation/upstream34-backport-a1-20261116.json`.

Rollback is a normal revert of the A1 commit after any later dependent stages.
The installed build-34 stack is unchanged, so this source work needs no runtime
rollback. Real Metal rendering, framebuffer fetch, display output, FPS and
long-duration stability remain untested for this candidate.

## A2 — framebuffer pool and alias retry

A1 passed and synchronized as `11cb1445b90dc3620afef313f1a811eb3b27e7d7`
before A2 edits began. Sources: downstream `bf7d37a` and `47faf8d`, limited to
framebuffer pool/alias behavior and the local accelerator policy header. There
is no copy of the downstream kernel policy/ABI or replacement bring-up binary.

Unpublished geometry consumes the bounded 3,600-present wait budget rather
than one of the three verification attempts. Actual mapping failures and pixel
mismatches still consume verification attempts. Acceptance still requires all
sampled pixels to match the BAR view with at least one nonzero sample; failure
keeps the BAR fallback. Pool frees validate integer, aligned, nonempty extents
before deallocation; range-allocator failure tries the next smaller pool.

```sh
python3 tools/test_upstream34_backport.py --stage a2 \
  --vulkan-headers /path/to/Vulkan-Headers --sdk /path/to/MacKernelSDK \
  --out build/backport-a2
```

MacKernelSDK is pinned to `3f750085caa17ec3a7880f11c11bf4f48cd6a164`.
The cumulative gate checks the unchanged A1 source against its successful
receipt, reruns baseline/A1 regressions and compiles the actual alias/pool
method bodies around CPU IOKit doubles under ASan/UBSan. It covers delayed
metadata, wait/verification exhaustion, all-zero and mismatched views, cached
acceptance, mapping failure, allocator fallback and invalid free ranges.
The complete three-translation-unit PhxAccel is compiled, linked and signed,
then its signature/architecture verified without loading it. Native firmware,
actual mapping attributes, copy latency, alias acceptance on this machine and
any FPS improvement remain untested. Normal source rollback: revert A2 after
any later dependent A3 commit; the installed stack needs no rollback.

2026-11-16 cumulative gate: **passed**. All 20 baseline geometry/script tests
and all A1 suites passed again. Pool/alias boundary policies and 3,646
assertions against the actual framebuffer methods passed under ASan/UBSan.
The complete PhxAccel native compile/link/signature/architecture checks passed
with zero compiler warnings; the unchanged A1 plugin also rebuilt successfully
with its 336 warnings. All 171 protected baseline files matched, and all A1
production source hashes still matched the A1 receipt. Sanitized evidence:
`validation/upstream34-backport-a2-20261116.json`. No hardware test or FPS
measurement was performed.

## A3 — read-only panel timing

Pending A2's successful gate. Planned source: downstream `661fd3c`, limited to
validated timing readback and IOFramebuffer reporting; no HiDPI or display
programming is included.
