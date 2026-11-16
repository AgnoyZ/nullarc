# Upstream solution review, 2026-11-16

**No reviewed upstream change is an established fix for this machine's native
second-dispatch output mismatch.** The strongest new initialization lead is
the MEC doorbell-range subset of PR #14. It merits an isolated source candidate,
not promotion of the whole PR or a claim that the IB problem is solved.

This review changes documentation only. Default remains
`upstream34/vram-layout-fix` at `64f3d991a4ddc3af5bbf30cbced9f11d3e7dd50c`,
with A1/A2/corrected-A3 present. The elapsed-time wait candidate and accelerated
desktop remain on HOLD. No driver, startup job or new hardware trial is added.

## Scope and fixed references

GitHub's API was queried on 2026-11-16 at 20:00:11 +08:00. The review inspected
all 19 current/closed PR records, all 10 non-PR issue records, releases/tags and
the newest 100 main commits. Each list except the commit history fit on one
100-item page. This is not a review of every historical commit or every fork.
Relevant PR file diffs and issue comments were read separately, including
corrections to earlier comments. A second API read at 20:09:52 +08:00 confirmed
the same main SHA and all 19 PR heads/states/merge statuses. The sanitized
[source record](validation/upstream-solution-audit-20261116.json) binds the
versions and comparison hashes.

- [Upstream main](https://github.com/luuumi-dev/nullarc/commit/8aba872560a3c9b7dc7a0ddebfad001c6dddf315)
  is still `8aba872560a3c9b7dc7a0ddebfad001c6dddf315`, committed
  2026-11-09 at 00:59:45 UTC. The repository's later `updated_at` is not a code
  update. Latest published release in this query is `v0.4.0-alpha` (November 9).
- Default build34's `src/phxbringup/PhxBringup.cpp` is byte-identical to this
  main: Git blob `c8631642f1272ec0aec77b2c72422c4f79cc86a2`, SHA256
  `beffab5dc13e4018ff2ab9f90c82d85c0982ce7e3563e3175999399c7bc083e5`.
  Updating to main therefore supplies no new kernel fix. Default's validated
  helper/VRAM-layout changes must not be overwritten by upstream helpers.
- The adaptive `doWaitSeq` polling change in upstream commit
  `4459c4084f47fd3fd8409f046c27d0f7268e0111` is already present. It still
  accumulates requested delay durations; it is not a new elapsed-time fix.
- Downstream was inspected at `6c531d94744f88488fe13da61cdcf8971ad59b95`.
  This source comparison does not mean its build40 kernel is installed.

## Match the reported fault before adopting a patch

On this machine (macOS 26.7.2 / `25G332`), original build34's rewritten/reused
IB policy failed pass 1 after positive retirement: first mismatch at BO offset
`0x2010`, actual `0xde`, expected `0xdf`. The separate immutable fresh-slot
policy passed both full 16-KiB comparisons. The later IB-only CPU publication
control and treatment both reproduced the mismatch. These are four consumed,
bounded policy scopes, not permission to replay them or proof of a particular
cache defect. See the [freshness comparison](NATIVE-IB-FRESHNESS-DIAGNOSTIC.md)
and [publication comparison](NATIVE-IB-PUBLICATION-DIAGNOSTIC.md).

The BO stays allocated/mapped and the client stays open between dispatches.
The native probe bypasses the Metal plugin, IOSurface and application shader
caches. BO destruction fixes and plugin fixes consequently do not directly
match that trigger. None of the reviewed PRs reports this exact two-dispatch
signature. This conclusion is limited to the sources reviewed, not a proof
that no upstream solution could exist.

## Priority and adoption decisions

| Priority | Upstream candidate | Relevance and decision |
| --- | --- | --- |
| 1 | [PR #14](https://github.com/luuumi-dev/nullarc/pull/14), MEC doorbell-range initialization only | Missing in both local branches. Two 780M reports support a CP-idle initialization defect; one says the range writes alone suffice. First source candidate to isolate; no evidence yet that it repairs this IB mismatch, GUI stutter or FPS. |
| 2 | [PR #18](https://github.com/luuumi-dev/nullarc/pull/18), BO lifetime | Important general corruption risk in build34, but no free/unmap/close occurs between this probe's dispatches. Downstream already has stricter pending-free/context quarantine. Do not cherry-pick this PR over it or promote the PR's timeout-release behavior to default. |
| 3 | [PR #17](https://github.com/luuumi-dev/nullarc/pull/17), memory budgets/accounting | Conditional on allocation-pressure evidence. Neither inspected local kernel has this global wired-byte cap or its larger budgets. Raising per-client limits is not an IB fix and can increase pressure; redesign the global reservation before considering adoption. |
| 4 | [PR #16](https://github.com/luuumi-dev/nullarc/pull/16), surface-texture cache keys | Relevant if camera/video slows as fresh IOSurfaces accumulate. Both local branches still use the seven-element array key. App-specific performance candidate after native correctness is resolved; no desktop FPS claim. |
| 5 | [PR #19](https://github.com/luuumi-dev/nullarc/pull/19), sandbox-compatible shader-cache writes | Relevant if Safari repeatedly recompiles and logs failed cache stores. Default lacks the helper; downstream already has separate atomic, integrity-checked persistence for base SPIR-V/index/key records, but other cache families still use Foundation writes. Review uncovered paths instead of replacing that implementation. |
| 6 | [PR #28](https://github.com/luuumi-dev/nullarc/pull/28), IOSurface copy-out completion | Correctness lead for private-image surface handoff in non-WindowServer apps. It blocks the committing thread; it is not a general latency/FPS optimization and does not run on the native probe's path. No current adoption. |

All six PRs above were open and unmerged at their reviewed heads.

### First candidate: separate the doorbell range from power management

PR #14 puts `linux_cp_init()` at the start of `sched_test()`, before scheduler
resource setup and user compute/graphics queue creation. The narrow candidate
sets `CP_MEC_DOORBELL_RANGE_LOWER/UPPER` to `0 / 0x450`. The existing GFX
doorbell index is `0x116` dwords, or `0x458` bytes; do not confuse the two units.
The upstream reports say the reset compute range overlaps that GFX offset.
Those reset-register observations are from other machines, not a register
capture of this machine.

Neither default nor downstream writes those range registers in the inspected
`src/` and `tools/` source. Separate `gfx_test.sh`/`rb0.sh` scripts already write
`CP_MAX_CONTEXT` and `CP_DEVICE_ID`; that is not the missing range setup in
`mesboot`'s scheduler path. The independent PR comment says changing the range
after the queue is active does not release its stuck CP.

Keep the prospective range change separate from PR #14's context/device writes,
VMID/HQD masks, oversubscription timer, new sleeps/status logging, build36/37
SMU telemetry, frequency policy and clock gating. It must preserve local
validated VRAM geometry and transport refusal. An offline candidate needs
ordering/error-path tests first; a later separately bounded hardware scope
would need both output integrity and a CP-idle observation before any desktop
or load/FPS gate. No such candidate or scope is created by this review.

### Why the memory PRs cannot be taken unchanged

PR #18 reaps all deferred BOs if its zombie list remains full after a bounded
wait, even without positive retirement; its comment treats page-table removal
as sufficient. Previously fetched accesses/cache writebacks are not proven
quiescent by that condition. Downstream's `reapPending()` retains descriptors,
pins, handles and budget charges until mapping/reclaim checks succeed, and
`reapContextsLocked()` retains uncertain resources. Preserve those properties.
Default's older kernel does not have that downstream protection, so any later
default lifetime backport must be reviewed independently.

PR #17 checks the global byte count and increments it in separate operations.
The increment is atomic, but the check-and-reserve as a whole is not; concurrent
clients can both pass the check. A hard cap needs a serialized or compare-and-
swap reservation plus rollback and correct charging of retained resources.
Downstream allocation diagnostics are observations, not an existing global cap.

### Evidence limits for application fixes

PR #16's author reports progressive camera slowdown resolved; a second user
reports no regressions in several apps but explicitly cannot reproduce/confirm
that speed-up. PR #19's report is from a combined plugin build. Neither is a
controlled measurement of this machine's background-load GUI problem.

PR #28's reported working build also contains other plugin changes and a
multi-plane experiment. The exact PR branch built but had not been run, as its
author explicitly states. Its added wait is for GPU completion plus CPU
surface copy-out; it excludes WindowServer and avoids waiting on the execution
worker. Keep its potential blocking cost and integration-only evidence visible.

## Hold unrelated or insufficiently isolated changes

- [PR #24](https://github.com/luuumi-dev/nullarc/pull/24) now leaves SDMA unhalt
  opt-in. A report of three resets with it enabled was followed by more resets
  with SDMA halted; the reporter withdrew the causal conclusion on November 14.
  The author also reports a stable machine. The evidence is unresolved: neither
  blame SDMA as proven nor enable it as a stability fix.
- [PR #25](https://github.com/luuumi-dev/nullarc/pull/25) was closed **unmerged**
  in favor of a single power-management mechanism. Its discussion warns that
  two GFXOFF state machines can conflict and that a zero register read while
  powered off can mislead wake detection. It is not an IB fix.
- PR #20's hibernation/boot integration and PR #21's CPPC/MSR CPU controls add
  separate power/boot variables. They are outside this investigation; no EFI,
  NVRAM, boot-policy or CPU-performance settings are changed.
- [Issue #13](https://github.com/luuumi-dev/nullarc/issues/13) contains mouse
  delay/USB interrupt workarounds from other machines. Input delay there also
  occurs outside the accelerated desktop; it does not establish that this
  machine's background-load GUI hang is USB-related. Do not apply its EFI or
  third-party-kext suggestions on that basis.
- [Issue #10](https://github.com/luuumi-dev/nullarc/issues/10) requests GPU-backed
  framebuffer/full WindowServer performance; it provides no implemented fix.
  Other screened plugin key/descriptor, camera-orientation, display and device-
  support PRs do not change this probe's native IB submission path.

## Licensing, validation and rollback

The reviewed main `LICENSE` and component notices distinguish phxbringup/phxctl
(MIT or GPL-2.0-only) from nmplugin/phxaccel (PolyForm Noncommercial 1.0.0).
The selected PR file lists do not modify those license files. No implementation
or binary is imported by this documentation review. Existing license/provenance
requirements and public binary-upload restrictions remain in force.

Validation checks source blobs, fixed PR heads, list coverage, local claims,
historical evidence hashes, Markdown links, JSON parsing and `git diff --check`.
No production code changed, so GPU or prior A1/A2/A3 tests are not rerun. Raw API
responses remain ignored and private. Documentation rollback is a normal revert
of this review commit; there is no installed or default-branch change to undo.

## Subsequent source preparation

The later [range-only build34 candidate](MEC-DOORBELL-RANGE-TRIAL.md) isolates
priority 1 in generated control/trial user helpers. Its source preparation and
offline results are separate from this audit; it does not adopt the whole PR,
promote default or establish a hardware fix.
