# Build34 render-clear preservation

## Problem and scope

On 2026-11-19 the owner reported intermittent duplicated pointer images and
gray squares during mouse movement. Duplicated pointers are an interpretation
of the report; this task has no photograph, video or simultaneous compositor
and scanout capture establishing where the corruption originates.

The default branch still contained a separately reproducible correctness bug:
render `MTLLoadActionClear` skipped importing the CPU backing. For an IOSurface
it also recorded the entire root texture in `_surfOverwrites`, suppressing
later imports in the same command buffer. A clear can cover only a texture
view, subresource or the pass's smaller render area. Pixels outside that area
must retain their defined contents; they cannot inherit stale GPU pixels.

Upstream fixed this in
[`531bac34989f32b861c77f5788290b9b6615405d`](https://github.com/luuumi-dev/nullarc/commit/531bac34989f32b861c77f5788290b9b6615405d),
tracked there as B-60. Its audit explicitly leaves the relationship to B-58's
reported cursor trails unproved. The history reconciliation deliberately
deferred this runtime change; having the upstream commit in ancestry did not
adopt its source.

This backport starts from default-branch commit
`4c52280b1ae75602fadbc2992d020baeb2cf07a0`. Its entire runtime change is the
upstream production patch in `src/nmplugin/NVMTLObjects.m`: primary and
additional color attachments retain `nvmtl_surface_in_for_cb` for Clear, for
both IOSurface and buffer-backed textures. No render clear declares a full-root
overwrite. The existing full-blit/replace overwrite checks, pending-writer
handling and seed-based import avoidance are preserved.

The patch preserves the owner-selected build34 runtime lineage, A1/A2/corrected
A3, the ACQUIRE-prefix correction and PR28 policy. No build41/build42 source,
kernel, native ABI, framebuffer, VBL, ACPI, installed runtime, startup job or
monitor policy changes are included. The active VBL and local AML batch-copy
treatment remain in use.

## Validation

The CPU regression adapts the upstream test and compiles the actual two
production preparation branches, with modeled CPU/GPU pixel arrays and a
one-pixel clear. Each action runs through primary/additional attachment and
IOSurface/buffer-backed combinations under ASan/UBSan. Nonzero exit codes
report mismatched pixels without deliberately crashing a process.

- Unchanged baseline: all four Clear combinations fail on untouched pixel 1
  (`9` instead of `2`); all four Load combinations pass. The final test was
  rerun against the private baseline snapshot, with no compilation errors.
- Candidate: all eight combinations pass, including the cleared pixel and
  preservation of the other three pixels.
- Existing publication-wait suite: all 10 test methods pass, including the
  WindowServer exclusion, bounded timeout and preservation of pending work.
- Existing plugin integration suite: all four methods pass under ASan/UBSan.
- Existing surface-key fixture: 77 boundary keys and 16,384 concurrent
  registry/monitor cycles pass.
- Default-worktree `make test` passes. Firmware-file fixtures are absent and
  skipped; synthetic parsing runs. Its CPU models do not constitute native
  GPU execution. This does not change the previously recorded failure of the
  separate upstream `test_wait_seq.cpp` suite.
- Baseline and candidate both compile as x86_64 release plugins with the
  existing native recipe, `NVMTL_RELEASE=1`, macOS 15 minimum and availability
  errors enabled. Both have the same multiset of 336 existing warnings.
  Architecture, expected class exports and ad-hoc signatures pass.

Commands for the focused CPU checks:

```sh
make test-nmplugin-render-surface-clear
make test-nmplugin-surface-commit-wait
make test-upstream34-plugin-prs
make test-nmplugin-surface-key
make test
```

The native compile uses pinned Vulkan-Headers
`6802bb4733b63ed5efd3adb308a6c885ef180ea1`, Apple clang
`21.0.0 (clang-2100.1.1.101)`, and the existing framework list from
`src/nmplugin/build.sh`. Baseline and candidate source snapshots differ in
exactly one plugin file. The release artifacts, dependencies and logs stay
private and ignored; neither artifact is installed or loaded.

One initial candidate-fixture compilation failed because the extracted
branches no longer use their fake descriptor parameters under `-Werror`.
The fixture now permits unused parameters and reports compiler diagnostics.
An unprivileged existing wait test also could not replace its root-owned
output; running the unchanged test with the existing artifact permissions
resolved that environmental failure. Neither failure is counted as a
successful regression check.

## Current machine and remaining acceptance

Read-only checks identify macOS 26.7.2 build 25G332 and the same current
WindowServer. Display submission failures, skipped copies, surface GPU
timeouts and hang-kill counters are zero. These counters cannot detect every
wrong pixel and do not disprove the owner's report.

A fresh read-only validator verifies the current build34/VBL installation,
loaded AML treatment, complete selected-cache metadata (416 records,
including 29 codeless entries), all 415 unrelated images, EFI/recovery,
bounded startup receipts, PR28 daily setting and disabled resident monitors.
It submits no GPU work. An initial validator selected the original, already
documented failed GUI-permission receipt; the corrected fresh validator uses
the existing successful replacement observation and separately checks the
failed original receipt and job retirement. The failed attempt is retained.
No guard was relaxed to accept a failing runtime.

The currently installed plugin executable, Info.plist and signed-resource
file have separate private, byte-verified backup copies. No installation,
restart, logout, new GUI/GPU workload or background observer was scheduled.

**Hardware repair of the reported artifacts remains unaccepted.** After owner
authorization, use a fresh candidate-compatible plugin installation and
bounded hardware scope, preserving the current kernel/cache, active VBL,
loaded AML, PR28 daily setting and startup-only policy. Validate partial-clear
pixels with actual GPU readback before judging pointer trails and gray squares
in normal desktop use. Capture compositor versus scanout evidence if the
visual symptom persists. Historical consumed hardware/GUI/startup jobs must
not be replayed. A CPU fixture is not a screenshot or Vulkan execution.

Preserving CPU content can add an import on a full clear after a changed CPU
seed. Existing seed/pending-write checks still avoid unnecessary imports;
no FPS or long-term stability improvement is claimed. Restoring the skipped
import optimization would require proof of successful whole-root coverage.

## License and rollback

The changed production file keeps its
`SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0` notice. Its upstream
patch, `LICENSES/PolyForm-Noncommercial-1.0.0.txt` and
`THIRD_PARTY_NOTICES.md` were reviewed. No new external component or binary is
copied into the public tree; license and notice files remain unchanged. The
plugin binary publication block remains in force.

For source rollback, review later dependencies and `git revert` this isolated
backport; never reset or rewrite default history. This source-only operation
needs no machine rollback. A later authorized installation must separately
freeze the exact current plugin/signature and compatible startup expectations
and define restoration of that current state. It must not restore the older
accelerator or original ACPI as a side effect of a plugin trial.

The sanitized machine-readable record is
[validation/build34-render-clear-20261119.json](validation/build34-render-clear-20261119.json).
