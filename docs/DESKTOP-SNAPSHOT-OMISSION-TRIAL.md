# Desktop allocation-snapshot omission trial

Status, 2026-11-15: **single target trial consumed and closed; first native
selector still dual-zero; independent recovery and subsequent boot verified**.
This isolates allocation-snapshot collection from the [consumed
CP-before-selection trial](DESKTOP-UPSTREAM-ORDER-TRIAL.md#target-result-and-recovery)
using the same signed native binary. It is not an acceleration fix, a
collector-free experiment or permission to replay either closed scope. No
driver, native initializer or power sequence changes here.

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

The physical comparison used a separate new scope, unchanged native candidate
and installed inputs, one fresh boot, at most one attempt and bounded
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

The historical preparation's validation results and source hashes are recorded in
[`validation/desktop-snapshot-omission-preparation-20261115.json`](validation/desktop-snapshot-omission-preparation-20261115.json).
Its source-only, unarmed status describes preparation, not the subsequent target
execution below.

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

## Target result and recovery

The [target record](validation/desktop-snapshot-omission-target-20261115.json)
documents execution from synchronized source commit
`22caaced08f8c30e70bcb6bf6d4d8d2f45af9862`. The signed native initializer is
byte-identical to the preceding CP-before-selection trial's candidate, whose
source reference is `594f6ad9c1acb757b8aa14954717733950ca4eb8`. The preparation,
attempt and subsequent recovery boot identities are all distinct. The target
reports macOS 26.7.2 / build 25G332 and bring-up build 39.

The admitted baseline is format 2, explicitly names the omission mode and has
no `snapshot` member. There are no baseline or failure snapshot invocation
receipts, and no report trigger was recorded before recovery. The report
observer acknowledged readiness before initialization; identity and framebuffer
history reads remained enabled. This confirms the scoped omission path ran,
not an absence of every possible observer or an empty allocation history.

Exactly one firmware/power command and one native desktop initialization are
recorded. Firmware/power returned zero. All three CP setup pairs completed
before selection, with immediate and subsequent readbacks matching their
requested values. The first KIQ selection still returned two zeros for a
nonzero request. Native stderr records the failure directly; the native process
exited 75 without timing out and its adapter returned 74. GART, MES, GPU workload,
claim, display, release and monitor were not reached. These counts describe
retained process/log observations, not independent hardware tracing.

The four linked journal records, baseline/observer digests and both recovery
claim hashes were checked independently. The metadata recovery worker handed
off to coordinator recovery with the original deadline preserved. Finite
initialization failure requested recovery about 0.38 seconds after the failed
stage returned. The configured 240-second watchdog did not expire. Disarming
completed; the one fallback reboot command returned zero, and a subsequent boot
was independently observed. This does not exercise recovery from a hard hang.

Display cleanup reported unknown OIDs for `nvaccel_iop` and `nvaccelfb`; AGDC and
framebuffer-hold cleanup returned zero. A zero exit status for the display
cleanup process does not establish that all four writes succeeded. Recovery
did not wait for display cleanup or the observer before requesting reboot.

After recovery there is one firmware framebuffer, no native framebuffer or
accelerator service, no one-shot display flag, no persistent activation markers
and no remaining initializer, startup job or reboot process. The off marker
was present and empty before activation, temporarily removed for this one
attempt and is now present and empty again. Startup remains the exact consumed
single-use packet, not the original pre-activation startup configuration.
There was no driver installation, kernel-collection rebuild or EFI, BIOS,
partition or security change.

All 185 new receipt files were stable across repeated reads and matched
byte-exact private copies and a separate root-owned receipt map. All seven
historical receipt sets, 43 execution pins, ten recovery pins, the complete
frozen runtime, native signature and six other installed inputs were reverified.
The preparation's 200 focused methods and 25 private activation methods are
historical checks; they were not rerun for this result-only documentation
change. Result inspection used retained files and boot/service metadata only,
with no new GPU command, arming or reboot request. Raw output and identities
remain private.

On this unchanged guarded initializer, omitting allocation snapshots did not
resolve the first selector failure. This weakens that particular collection
path as the explanation and rules out outer summary parsing as the source of
the recorded zeros. It does not establish a physical cause or exclude native
access defects, remaining observers, power-state dependencies or another
initialization prerequisite. Desktop takeover and acceleration remain unproven.

This request's attempt and both reboot allowances are consumed and closed.
Preserve the off marker, inactive packet and all receipts; never re-arm or
replay them. Further work under this request is offline investigation. Another
physical experiment needs a distinct reviewed scope, isolated change, fresh
boot and independent recovery plan. Source rollback uses a normal new commit
and does not reopen any consumed request.
