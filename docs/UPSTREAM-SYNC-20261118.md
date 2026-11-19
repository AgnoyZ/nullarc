# Upstream history synchronization with the pinned build34 source

## Scope and exact inputs

On 2026-11-18 the owner requested resolving the default branch's **46 commits
behind** upstream `luuumi-dev/nullarc:main`. Fresh Git fetches confirmed the
remote default at `aa7ed621f1887b23f3cbbb2284334cc70da0332f` and upstream main at
`3497d87b229e4839d8d2a03ebe9127f2a30f332b`. The local parent is
`908bbd2e5b62785f1344ed493ca795cd87089f46`, which also preserves the previously
unpushed A14 desktop-tail refusal record. The common ancestor is
`9dd76b604fca5e0125bd3caa5723df0f611ff27f`. Before this merge, the local branch
is 78 ahead / 46 behind (the remote branch was 77 ahead / 46 behind).

This is an explicit two-parent compatibility merge. It preserves history;
there is no rebase, forced update, reset of the default branch or blanket
unreviewed `ours` strategy. Each of the 46 commits and 60 upstream-changed paths
has a disposition in the [machine-readable review](validation/build34-upstream-sync-20261118.json).
The upstream main commit becomes an ancestor, so the history's behind count is
zero at this pinned upstream tip. That ancestry **does not mean all 46 changes
are active in build34**. Most runtime changes are explicitly deferred below.

The [build34-only scope](BUILD34-SCOPE.md) still applies. The entire `src/`
subtree, native ABI, `tools/phxctl/`, A1/A2/corrected-A3, integrated compute
ACQUIRE fix, plugin backports and default-off publication wait are byte-for-byte
identical to the local parent. Build41/build42 remain withdrawn. The original
admission checks, 250-ms budget, existing failures, recovery records and
permanent desktop/default-wait HOLDs remain intact. This task changes repository
source/history only, with no deployment, driver build, device opening, GPU
submission, desktop takeover or reboot.

## Changes adopted in the working tree

- `27c741b`: add `release/` to `.gitignore`, preserving all existing local
  build, privacy and diagnostic exclusions.
- Package-check portion of `130bd0a`: retain upstream's exact
  `tools/release/check_pci_matches.py` and call it from the release script after
  collecting the two kext bundles. A mismatch with the checked-out source's
  PCI personalities fails the packaging script. Add upstream's exact CPU-only
  `tests/test_release_pci_matches.py` to the existing `make test` target.
- Keep the existing default-branch Makefile tests and all local-only files.
  Do not pull in tests that require the unadopted kernel/plugin/display code.

The other `130bd0a` install, uninstall and AuxKC publication changes are **not
adopted**: the boot/tool baseline remains pinned. This merge does not claim
that the pre-existing installer/collection failure risks are fixed. The release
checker validates PCI matching only; it is not a build34 admission, binary
identity, full provenance or permission-to-upload check. The full-stack binary
publication block and its narrowly documented historical exceptions remain.
The release/installer scripts themselves are not executed during validation.

## Runtime changes retained for separate review

Engineering review priority for a future authorized **minimal build34
backport**, not permission to build/install/test a new candidate:

1. Queue/VM/DMA ownership: `df56129`, `7017335`, `ce3f969`, `bfdedeb`,
   `cc70745`, `5fbc11a`, `67dce08`, `5ee5f23`, `b787e24`, plus the PTE portion
   of `b55302b`. These alter locks, teardown, retention, TLB error handling or
   blocking; they require dependency analysis and cannot replace the pinned
   kernel simply because both sources still advertise build 34.
2. Rendering correctness: `531bac3`, `10c9e65`, `e44deb7`, `9543d43` and
   `5c175e5`, together with their tests. Full-root preservation, format-view
   clears, unavailable LOAD passes and command-recording failures must be
   reviewed in coherent dependency groups against the local A1/PR28 code.
3. Sleep/power/HDMI, GL pacing, SSE scanout, capture and boot-script changes:
   keep separate from the IB/wait baseline. Reference-machine EC fan addresses,
   ACPI binaries/dumps and upstream deployment reports are not portable local
   fixes or local acceptance evidence and are not added to this tree.

These are correctness/dependency priorities, not measured performance rankings.
No FPS improvement, cursor fix, UI-stall fix or long-term stability acceptance
is produced by this source/history synchronization.

## Disposition of all 46 upstream commits

`deferred` means the relevant upstream working-tree delta is deliberately held
out by this merge; the commit remains visible through the second parent.

| Commit | Decision | Reason |
| --- | --- | --- |
| `e0ee87f` | deferred | Wait-sequence model test; keep the build34 production-function regressions and wait policy pinned. |
| `27c741b` | adopted | Ignore release/ output alongside the existing local privacy/build exclusions. |
| `8aba872` | deferred | Upstream release, multi-GPU and benchmark claims are not local build34 validation; preserve the fork status. |
| `6c19fcc` | deferred | Upstream resolved-bug status does not prove these fixes are present or accepted on pinned build34. |
| `7c22f1a` | deferred | Preserve local bug-status context rather than importing reference-machine acceptance. |
| `de42aed` | deferred | PANEL_BLON/display power sequencing changes runtime hardware behavior; needs an isolated build34 review. |
| `e31ad72` | deferred | Do not mark the upstream sleep/backlight fix accepted locally without adopting and validating its code. |
| `b55302b` | deferred | BO PTE teardown, vblank sleep accounting and power-tree direction alter the pinned kernel/framebuffer. |
| `a66fe08` | deferred | Keep the upstream audit in its original history; do not replace local bug-status context. |
| `08c5386` | partly-already-present | A1 sampler/surface keys are already locally backported; retain the tested local implementation. GL pacing and SSE changes are deferred. |
| `0f894c1` | deferred | Sleep/wake callback and ACPI changes require a separate hardware scope; do not import them for ancestry. |
| `1e0dbe9` | deferred | Reference-machine EC/fan/ACPI addresses and behavior are not portable build34 fixes. |
| `61ee3f9` | deferred | BAR0 SSE scanout and fan changes alter the display path and hardware policy; retain the accepted local path. |
| `b7c6d4a` | deferred | Dynamic HDMI head publication and multi-head modesetting are outside the accepted eDP build34 configuration. |
| `130bd0a` | partially-adopted | Adopt the source-versus-package PCI guard and its CPU test only. Keep install/uninstall and tools/phxctl/kinst.sh pinned; AuxKC failure-safety changes are not claimed adopted. |
| `df56129` | deferred | Queue retirement serialization and watchdog VMID generations need a minimal build34-specific backport, not a wholesale kernel replacement. |
| `7017335` | deferred | Pending-fence list and retained DMA destinations change client lifetime and retirement; review together with its dependency chain. |
| `ce3f969` | deferred | Waiting before BO unmap/free changes blocking and lifetime behavior; no new native wait is admitted here. |
| `bfdedeb` | deferred | Deferred client-close teardown depends on the new retirement/lifetime implementation. |
| `cc70745` | deferred | Service-stop DMA quarantine and lifecycle locks change unloading and resource ownership. |
| `5fbc11a` | deferred | Range/VM-map rollback safety is a high-priority future isolated backport; preserve the approved kernel for this sync. |
| `67dce08` | deferred | Serialized debug-DMA ownership and boot-lifetime page retention change original helper/kernel semantics. |
| `5ee5f23` | deferred | TLB failure propagation and resource retention depend on the newer VM/lifecycle implementation. |
| `212b448` | deferred | UE200 network recovery is unrelated to the selected GPU baseline; do not copy reference-machine interface configuration. |
| `b4cd872` | deferred | Boot hang-window/reboot behavior remains pinned; this repository sync does not change automatic recovery. |
| `b787e24` | deferred | Permanent VM-bind failure propagation belongs with the deferred VM/TLB changes. |
| `22efbe6` | deferred | The local 90bb06f helper correction already handles absent watchdogs/initializer errors narrowly; retain it rather than replacing boot/admission behavior. |
| `605be2e` | deferred | Scanout-dumper validation is separate from this package-only change; retain the current capture tool and local evidence. |
| `531bac3` | deferred | Render-clear preservation changes runtime synchronization and content transfer; requires isolated plugin validation. |
| `ffa4635` | deferred | Native Metal reproducer belongs with the deferred format-view fix; do not imply it was run locally. |
| `10c9e65` | deferred | Full format-view clear semantics affect rendering correctness and remain a separate plugin backport. |
| `87aa354` | deferred | Upstream hardware evidence is retained in upstream history, not adopted as evidence for this machine. |
| `fa09ff0` | deferred | sRGB/secondary-attachment cases depend on the deferred format-view change and its reproducer. |
| `e44deb7` | deferred | Refusing unavailable LOAD render passes changes runtime failure behavior; review with error propagation. |
| `9543d43` | deferred | Recording-failure propagation renames/extends command-buffer error state and must be integrated as a coherent plugin change. |
| `5fcbdd9` | deferred | Failed-render native test depends on that deferred plugin implementation; no GPU execution in this sync. |
| `5c175e5` | deferred | Empty-part optimization must preserve the deferred encoding_error state; do not import only one side. |
| `86111f2` | deferred | Reference-machine candidate/desktop-validation documentation is not local acceptance. |
| `f2e3cfb` | deferred | Upstream signed-bundle staging state is not a candidate on this build34 worktree. |
| `ee87ec7` | deferred | Upstream installation/backup/reboot records are not local deployment instructions or evidence. |
| `fa84e7d` | deferred | Reference-machine picker/cursor state must not replace local failure and recovery records. |
| `e63f194` | deferred | Upstream compositor-wait cursor workaround does not clear local default-wait/desktop HOLDs. |
| `93b5151` | deferred | HDMI mode validation changes the modeset header/path; review with the unadopted HDMI implementation. |
| `7d2b799` | deferred | DMUB readiness admission belongs with the deferred HDMI mode path. |
| `3f01d91` | deferred | Keep upstream HDMI firmware prerequisites as reference history; no local firmware/candidate claim. |
| `3497d87` | deferred | Zero-copy mapping/MPS planning and reference-machine records are retained upstream, not promoted as local fixes. |

## Licensing, privacy and validation

`LICENSE`, `LICENSES/` and `THIRD_PARTY_NOTICES.md` are unchanged in both the
upstream range and the local result. The copied release checker and CPU test
are nullarc tool/test code under the root MIT-or-GPL-2.0-only choice. No plugin,
firmware, ACPI binary, vendor runtime or additional external dependency is
copied into the resulting tree. In particular, upstream-only hardware dump
and ACPI additions are not materialized in the committed working tree.

Existing A14 evidence is retained verbatim, including the second desktop-tail
sample's `no measured frame progress` refusal. Upstream reference-machine
reports do not replace any local evidence. Raw merge/test/network logs and
private operational paths stay in ignored local build storage. Only reviewed
source, public commit/tree identities and sanitized validation summaries are
committed. Serial CPU test results and protected-subtree identities are recorded
in the linked JSON; CPU tests do not constitute new hardware acceptance.

The scoped CPU checks passed: baseline units and the new PCI test, 20 layout
methods, six integrated-submit source/refusal methods, the independent 36,111
actual-function scenarios, A1 keys/masks, A2 framebuffer/alias, corrected-A3
panel callbacks, existing plugin PRs, bounded surface-wait tests and four alias
mode fixtures. The real-firmware fixture cases are skipped because fixtures
are absent; synthetic parsing passes. The descriptor-mask test first lacked
its Vulkan include path and passed using the existing verified clean pinned
headers (`6802bb4733b63ed5efd3adb308a6c885ef180ea1`) through `CPPFLAGS`, with
no source change or new download. Shell syntax, staged whitespace, privacy
and protected-tree checks also pass. The separate old full-input target's
refusal below remains explicit.

## Existing strict CPU recipe refusal

The `test-upstream34-submit-memsync` source/refusal suite passes its six tests,
but its full-input exercise is not a passing target on the pre-merge default:

- The Makefile's fixed output directory already exists, so the first exercise
  invocation correctly refuses to reuse it.
- A fresh-directory invocation then refuses the existing
  `tools/phxctl/relocate_gpubundle.sh` change from `a613363`. The old recipe pins
  the earlier script; both the pre-merge parent and this merge have the same
  later script. This is a verified pre-existing incompatibility with that
  full-input recipe, not a source change introduced by upstream synchronization.

Neither the recipe nor its admission checks are changed or relaxed. The raw
refusals are retained privately and the full target is not reported as passing.
A separate CPU-only unit invocation extracts the exact hash-pinned production
`gpuSubmit` function into the unchanged existing fake-platform fixture and
checks its result under ASan/UBSan with no IOKit/CoreFoundation linkage. This
checks only the function; it does not substitute for full-input admission,
GPU execution or a new deployment. Its result and the other retained source
regressions are recorded in the validation JSON.

## Future merges and rollback

Git considers all 46 commits merged after this reconciliation. A future merge
will **not automatically offer the deferred patches again**. Use this explicit
commit/path review to select a future minimal backport, examine the original
patch and dependencies, and retain real-GPU admission/recovery requirements.
Do not use an ancestor check or a zero behind count as proof that a deferred
fix is present in the working tree. Update this disposition record when such a
patch is actually adopted.

A reviewed `git revert -m 1 <this-merge-commit>` reverses the adopted tree
changes without rewriting history. It does not remove upstream ancestry or
restore a behind count. This task makes no machine installation, so there is
no driver/system rollback action. `main` remains an exact upstream mirror;
only a normal fast-forward to the pinned upstream commit is appropriate there.


## Later isolated render-clear backport, 2026-11-19

The later owner report of pointer trails and gray squares prompted a separate
review of `531bac3`. Its two production render-clear preparation hunks are now
adopted on default build34, with an adapted actual-branch CPU regression and
native release compilation. The historical table above records the original
merge decision. The other rendering commits remain deferred.

This confirms a reproducible pixel-preservation source defect, not that the
reported desktop corruption has the same cause. No changed plugin is installed
or GPU-tested; the active VBL/AML treatment, PR28 daily policy and disabled
resident monitoring remain preserved. See the [backport and acceptance
record](BUILD34-RENDER-CLEAR-PRESERVATION.md).
