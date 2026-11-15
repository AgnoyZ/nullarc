# Desktop allocation-snapshot omission candidate

Status, 2026-11-15: **source candidate; target execution not performed**. This
isolates allocation-snapshot collection from the [consumed CP-before-selection
trial](DESKTOP-UPSTREAM-ORDER-TRIAL.md#target-result-and-recovery). It is not an
acceleration fix, a collector-free experiment or permission to replay that
closed scope. No driver, native initializer or power sequence changes here.

## What actually ran in the preceding attempt

The retained result records one allocation baseline with `observed=0`, no
failure snapshot and a live report observer during initialization. That reader
is `tools/allocation_snapshot.cpp`: it opens a fresh native client, sends only
selector 31, then closes it. The provider dispatches this selector before Hello
and the ordinary reaper, and `copyAllocationSnapshot()` copies stored software
history under the existing GPU lock. It does not sample GC registers or a GPU
fence. Its client lifecycle still allocates software storage, claims/releases a
session and can register sysctls, so timing and lifecycle interference are not
excluded by this source inspection.

The report observer inventories report names/identities and waits for vnode
notifications. It does not periodically poll GC registers. The separate
`gc_state_observe.c` utility is not the allocation reader. Its fixed 19-register
list excludes the index/debug and semaphore registers named in the upstream
report below. That fact alone proves neither hardware harmlessness nor whether
some other process accessed GC on the failed boot.

## Public research and applicability

The sources below were retrieved on 2026-11-15; reported hardware results belong
to their authors, not this target.

- [Upstream PR 25](https://github.com/luuumi-dev/nullarc/pull/25), head
  `433423eeaa61f73b9d90be4eb12afba56b4994b7`, was closed **without merging** on
  2026-11-14. It describes zero GC reads and lost writes during GFXOFF. The author
  closed it in favour of another contributor's wider access-bracketing mechanism.
  That mechanism is present in `senqaii-ce/nullarc`'s `gfxoff` branch at
  `43d59d19d74b2b390460024758f70c89b63e83dd`, and the author's combined test
  branch is pinned at `b19bb1e5e154598aae18a212d15116c4499d740b`.
- [PR 14](https://github.com/luuumi-dev/nullarc/pull/14) was still open at head
  `9f37791bb816092df580f3cb62a9db1e2357fb8f`. Its actual head does **not** contain
  the `GfxGuard` mechanism discussed in PR 25's comments. Its CP/doorbell fixes
  address a later, post-gfx-doorbell persistent-busy condition. They are not a
  demonstrated fix for this target's first selector refusal.
- [PR 24](https://github.com/luuumi-dev/nullarc/pull/24) was still open at head
  `0a3bd8aa63128ca8b152abf5b10e68ca41bc4ec9`, with SDMA opt-in. Its author
  reports GPU damage from broad GC reads including index/debug and semaphore
  registers. A tester subsequently withdrew the claim that SDMA alone caused
  resets, after resets also occurred with it halted. Neither report establishes
  a cause for this target or justifies changing SDMA during this experiment.
- Linux at `7d0a66e4bb9081d75c82ec4957c50034cb0ea449` implements reference-counted
  GFXOFF exclusion in `amdgpu_gfx_do_off_ctrl()` and a separate selector write in
  `soc21_grbm_select()`. Reading those functions is not hardware validation of a
  proposed macOS wake policy or of selector readback semantics.

No upstream implementation body or binary was copied. Existing licences,
notices and publication restrictions remain intact. The preceding target's
successful nonzero CP readbacks also prevent treating persistent whole-GC
power-off as an established explanation for its selector-specific zeros.

## One explicit observation-mode change

Ordinary desktop packets remain format 1 and require allocation snapshots. A
new **format 2** packet must explicitly name
`snapshot_mode: "omit-allocation-snapshots-trial"`; unknown modes, a missing mode
or that field in a format 1 packet are rejected. There is no environment or CLI
switch silently changing the normal capture policy.

In this mode, the baseline still checks the reader file's hash and permissions
and performs both sets of boot/OS/service/image identity queries. It never
executes the reader. Its format 2 baseline records the omission explicitly and
has **no** `snapshot` member; no empty history is fabricated. Ordinary admission
rejects that baseline, and omission admission rejects an ordinary baseline.
The explicit mode cannot certify remaining allocation-history detail capacity
or produce allocation-history deltas; the ordinary mode keeps those checks.

The report observer and its bounds remain. A new report publishes the existing
trigger and a distinct `report-observed-snapshot-omitted` result without a
failure-snapshot call. Before release that report or an ended observer still
refuses subsequent stages. After release the monitor's existing crash thresholds
remain authoritative. Identity, framebuffer history/hold, native selector
readback, stage status, command pins, deadline and independent recovery checks
remain in place. No GFXOFF, clock, register, guard or initialization-order change
is bundled with this mode.

## Execution and interpretation

A later physical comparison needs a separate new scope, unchanged native
candidate and installed inputs, one fresh boot, at most one attempt and bounded
independent recovery. Old authorization objects and receipts remain consumed.
Do not re-arm an old request or label a software-only baseline as a GPU snapshot.
There is no driver installation, EFI/security change or same-boot retry in this
candidate.

Even if the first selection changes, omission also changes elapsed time and
client/lock interactions, so it is evidence about this observation path rather
than proof of a particular hardware cause. If dual-zero persists it weakens
that path as an explanation; it does not exclude other observers, native access
defects or power-state dependencies. This mode retains the existing desktop
stages if earlier stages pass; it is not a selector-only terminal probe.

Rollback of source uses a new revert commit. An unarmed format 1 packet retains
normal behavior without this mode; consumed packets are never reused. Any
activated packet additionally needs its own exact startup/marker restoration
and subsequent boot verification. Private identities, diagnostic output,
binary candidates and root packets must remain outside public evidence.

Validation results and source hashes are recorded in
[`validation/desktop-snapshot-omission-preparation-20261115.json`](validation/desktop-snapshot-omission-preparation-20261115.json).

All **200 focused test methods** passed without skips, including the existing
native entrypoint, register-transport, fixed-GC collector and snapshot-lifecycle
CPU harnesses. The four changed Python suites also passed **137 methods** on
the exact Python 3.13.18 interpreter using a hash-verified root-owned source
copy. Four private mutations were detected: accidentally invoking the baseline
reader, invoking the failure reader, implicitly selecting omission admission,
and accepting omission in a format 1 desktop packet. An earlier parallel
process-fixture timeout and an ownership-refused root run are retained in the
validation history; deadlines and ownership checks were not relaxed. The full
repository suite was not rerun. No actual GPU command or recovery command ran
in these tests.
