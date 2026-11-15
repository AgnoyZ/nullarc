# Upstream acceleration and downstream startup comparison

Reviewed 2026-11-15. The working repository is `AgnoyZ/nullarc`, branch
`downstream/780m-tahoe`. The owner identifies the installed stack as the modified
fork and reports that the original enables acceleration. The pinned upstream
README at `8aba872560a3c9b7dc7a0ddebfad001c6dddf315` also reports working
WindowServer compositing, Metal graphics and Metal compute on its Firebat U6C
reference machine. The downstream failure does not invalidate those upstream
results. The inspected records do not establish an exact unmodified upstream
package/commit successfully tested on this laptop.

This review compares fixed source and existing sealed observations. It does
not run either installer, query the live kernel, initialize a GPU or establish
that the latest checkout is the loaded binary. The terminal [desktop retest](
DESKTOP-RETEST.md#target-result-and-recovery) is the historical input to this
comparison. The subsequent [upstream-order trial](
DESKTOP-UPSTREAM-ORDER-TRIAL.md#target-result-and-recovery) is now the latest
recorded physical result: its CP setup completed before the first selector,
which still returned two zeros. Source references are fixed pins, not claims
about the latest upstream release.

## Installation and initialization are separate comparisons

`install/install.sh` is byte-identical to that upstream pin, SHA-256
`7ac42efc1332958e32aeb6a027d6a6e5bbefb204563dd310a2acd96aead3887f`.
It copies a packaged stack, invokes kernel-collection installation and installs
the boot LaunchDaemon. A matching installer does not establish matching payload
binaries, startup configuration or GPU initialization. Its security/EFI
prerequisites and installation side effects are not executed by this review.

The reference `tools/phxctl/full.sh` and current explicit `desktop-init` source
have a concrete ordering difference:

| Point in the source path | Fixed upstream reference | Current downstream desktop entrypoint |
| --- | --- | --- |
| Firmware/power | `bringup5.sh` precedes the remainder of `full.sh` | Coordinator completes checked `gfx-power-sequence` first |
| Before doorbell/CP setup | No equivalent four-queue idle-selection preflight in `full.sh` | Reserve resources, then select/check KIQ, scheduler, compute and graphics queues |
| Doorbell/CP setup | Three register writes precede `mesboot gart` and `mesboot mes` | The corresponding setup writes follow the four idle checks |
| GART VMID selection | Follows that setup; selection replies are not checked | Follows setup; current source checks both selection replies |
| First recorded downstream refusal | No upstream execution was performed in this review | First KIQ selection, before the setup, GART, MES or claim stages |

The [retained native result](DESKTOP-RETEST.md#target-result-and-recovery) reports
a nonzero requested selection and two zero replies at this early check. This is
an initialization-order candidate to investigate, not proof that moving CP setup
fixes it. The upstream reference has machine-specific memory assumptions and
weaker completion/refusal checks; replaying it wholesale is not an equivalent
controlled test. Removing a refusal guard would only suppress the observation.
The [transport audit](REGISTER-TRANSPORT-AUDIT.md) and [GART guard repair](
GART-SELECTOR-GUARD.md) retain their separate evidence and limitations.

The owner subsequently requested a test of this ordering difference. The
[separate trial](DESKTOP-UPSTREAM-ORDER-TRIAL.md) preserves ordinary builds and
uses an explicit compile-time CP-before-selection candidate, a new request and
fresh-boot recovery; it does not reopen the historical desktop retest. That
single trial is now consumed, with finite-failure recovery and a subsequent boot
independently verified. The scoped order change did not resolve the failure;
the whole upstream stack was not replayed and no acceleration was established.

## What the historical power fields add

Two archived observations from the earlier dedicated GC phase experiment were
read as regular files and independently matched to their existing SHA-256
receipts. The original scope was unchanged. This was not a new collector run;
it was a different historical boot from the failed desktop retest. Raw files,
raw register values and administrator-read details remain private.

At the post-power sample, the named GFX power, clock and pipeline power status
fields were asserted. The power-gating error byte and sampled transition,
save/restore and aborted-power-down fields were zero. The reviewed power-gating
and CGCG/CGLS enable fields were zero. These are instantaneous bit observations;
they do not establish continuous state, GFXOFF exit, selector accessibility or
the cause of a failure on another boot.

`tools/gc_state_compare.py` now decodes 29 previously undecoded RLC fields:
all 25 `RLC_GPM_STAT` fields, the two power-gating enable fields in `RLC_PG_CNTL`,
and the two enable fields in `RLC_CGCG_CGLS_CTRL`. It retains original values and
all unreviewed control bits, keeps the existing schema and acceptance predicates,
and makes no new readiness, GFXOFF or causal classification. It reads files
only; the collector and target transport are unchanged.

## Phoenix GFXOFF query limitation

At Linux pin `7d0a66e4bb9081d75c82ec4957c50034cb0ea449`, the source dispatch is:

1. `amdgpu_get_gfx_off_status` calls `amdgpu_dpm_get_status_gfxoff`.
2. The SMU path calls `smu_get_status_gfxoff`.
3. That function returns `-EINVAL` without `ppt_funcs->get_gfx_off_status`.
4. Phoenix's assigned `smu_v13_0_4_ppt_funcs` has `gfx_off_control` but no
   `get_gfx_off_status` member initialization.

The control function includes MP1 13.0.4 and sends an Allow/Disallow mailbox
message when enabled by policy. Mailbox completion is not an independent
GFXOFF-state observation. This pinned generic query therefore does not supply
a Phoenix status result; another chip's status register cannot be substituted
without its own applicable evidence. This does not assert that all possible
Phoenix observation mechanisms are absent.

The earlier Linux-order comparison also needs a qualification: the optional
`gfx_v11_0_config_gfx_rs64` path selects pipes before constants initialization
sets `READ_TIMEOUT`, and before its own pipe reset writes. This review does not
determine the target's RS64 mode. Neither a different timeout value nor CP
halt/reset bits alone justify a hardware sequencing change.

## Provenance, checks and continuation

The [validation record](validation/upstream-startup-comparison-20261115.json)
pins the primary sources. The AMD MIT-style notices were inspected. Only factual
field names, shifts and masks were added to the independently written analyzer;
no Linux implementation body, whole header, binary or firmware was imported.
Existing component licences and the publication boundaries remain intact.

The decoder's new checks fail against the old analyzer because the RLC fields
are absent. After the change, **58 focused test methods pass without skips**:
11 file-analyzer, seven actual-collector/fake-IOKit, 33 desktop/fake-IOKit and
seven transport methods. Independent bit-position tests cover all 32 status
bits, a nonzero error byte, transitions and unreviewed-bit preservation. Real
collector source compiled with ASan/UBSan feeds the analyzer in both observation
modes using fake IOKit only. The full repository suite was not rerun.

The offline comparison itself left installed drivers/helpers, startup, EFI,
security, existing authorization objects and consumed experiments unchanged.
The separate trial's startup/one-shot activation and recovery safety-state
change are documented in its own result. Revert this source/test/documentation
change with a normal new commit if necessary; preserve original observations.
No acceleration fix or new target success is claimed. Any further physical test
must have a separate reviewed scope identifying the exact changed candidate,
one isolated variable, a fresh boot, independent recovery and rollback. It must
not replay a consumed request or treat this offline review as permission to
reorder register writes, install a stack or reboot.

The subsequent [allocation-snapshot omission source candidate](DESKTOP-SNAPSHOT-OMISSION-TRIAL.md)
isolates one observation-path variable and records the related public GFXOFF
and register-reading discussions. It changes no native initialization or power
sequence and does not reopen this review's or the upstream-order trial's scope.
