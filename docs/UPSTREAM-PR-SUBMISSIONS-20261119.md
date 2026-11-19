# Default-branch changes submitted upstream on 2026-11-19

The owner requested submitting the remaining default-branch changes to the
official repository after the ACPI documentation PR #31. Eight focused source
ports were published from `AgnoyZ/nullarc` to `luuumi-dev/nullarc:main`, each
with one independent commit directly above official main
`3497d87b229e4839d8d2a03ebe9127f2a30f332b`. Remote branch SHAs and each PR's
base, head, draft/open state and exact changed-file set were independently
verified through Git and GitHub's API. Submission is not upstream acceptance.

| Official PR | Change | State at verification | Head commit |
| --- | --- | --- | --- |
| [#32](https://github.com/luuumi-dev/nullarc/pull/32) | PhxBringup: acquire compute memory before indirect buffers | Draft | `c4c15436cb1b` |
| [#33](https://github.com/luuumi-dev/nullarc/pull/33) | phxctl: preserve ordinary-user Metal bundle lookup | Open | `0d4267203954` |
| [#34](https://github.com/luuumi-dev/nullarc/pull/34) | phxfb: validate pool releases and retry unpublished scanout aliases | Open | `329b6682e291` |
| [#35](https://github.com/luuumi-dev/nullarc/pull/35) | phxfb: publish validated panel timings with bounded refresh sampling | Draft | `1e3b9e6f193d` |
| [#36](https://github.com/luuumi-dev/nullarc/pull/36) | phxfb: isolate VBL delivery using public IOKit timers | Draft | `2888e06d3732` |
| [#37](https://github.com/luuumi-dev/nullarc/pull/37) | nmplugin: exclude framebuffer-fetch bindings from descriptor masks | Open | `7cfbb30d984a` |
| [#38](https://github.com/luuumi-dev/nullarc/pull/38) | nmplugin: share compact IOSurface keys with synchronization monitors | Open | `0eebc59eb7f4` |
| [#39](https://github.com/luuumi-dev/nullarc/pull/39) | nmplugin: bound opt-in IOSurface publication waits | Draft | `41bf4ea2bc95` |

The earlier [ACPI log-buffer diagnosis/reference PR #31](https://github.com/luuumi-dev/nullarc/pull/31)
remains separate. The three old self-closed PRs #7/#8/#9 had no upstream
rejection comments in the reviewed API records; #38/#37/#35 respectively
submit the remaining applicable code against current main. No old PR branch
was force-pushed or rewritten. #39 is explicitly a policy alternative to
#28's unbounded wait, and credits its original author/classifier. The finite
wait can expire with publication unconfirmed; it must not be described as
preserving #28's unconditional commit-return guarantee.

## Validation and review limits

All eight focused CPU checks passed. This includes 20 actual compute-submit
scenarios, four Metal-link filesystem cases, actual pool/alias and corrected
panel callbacks with sanitizer doubles, 66 VBL callback/allocation/retirement
assertions (including display-dark behavior), 321 descriptor cases per
unset/0/1 mode, compact-key lifecycle/concurrency cases and ten publication-wait
test methods. The initial descriptor invocation lacked an include path; the
passing run used the existing clean Vulkan-Headers checkout pinned at
`6802bb4733b63ed5efd3adb308a6c885ef180ea1`. No new dependency was downloaded.

The full `make test` is **not reported green**. All 16 Python suites passed,
but unchanged upstream `test_wait_seq.cpp` aborted on scheduler-sensitive
wall-time assertions. A separately compiled byte-identical clean-main control
also aborted. The queue, pending-fence and HDMI binaries that follow it passed
separately. Real firmware file fixtures were absent; those cases skipped and
synthetic parsing passed. Assertions were not disabled and unrelated upstream
tests were not modified to conceal the failure.

#32 is a draft pending that full-suite issue and current-main native/hardware
validation. #35/#36 remain drafts for native/current-main display/lifecycle
validation, and #39 for its changed publication policy and GPU acceptance.
The other four PRs are open for review with the same explicit CPU-only port
limit. None of these official-main ports was compiled as a kext/plugin,
installed, booted or GPU-tested in this task. Historical downstream hardware
evidence is linked in each PR and does not validate newer upstream code.
No FPS or long-term stability acceptance is claimed.

## Other differences and why they are not duplicated

- A1 sampler decimal keys are already present in official main. Do not
  resubmit old #6. The remaining shared surface-key and descriptor-mask work
  is covered by #38 and #37.
- The four integrated plugin inputs already have other authors' open official
  PRs: Unknown usage #15, surface texture cache #16, cache store #19 and
  isDrawable #22. Their local integration is not a new independent upstream
  contribution. #28 remains open alongside the clearly labeled #39 alternative.
- The fork intentionally retained older build34 source in its compatibility
  history merge. Missing upstream VM/lifetime, render-error, HDMI, sleep, fan,
  pacing and installer changes are deferred upstream features/fixes, not
  downstream patches to propose in reverse. See `UPSTREAM-SYNC-20261118.md`.
- The narrowly pinned original34 VRAM geometry/admission tooling and recipes
  remain local compatibility support. Do not submit a wholesale tool replacement
  that would narrow current main's multi-device support, undo its error handling
  or weaken the local build34 admission checks.
- Failed/diagnostic MEC, ring-padding and explicit RADV-tail experiments remain
  evidence. They are not passing production fixes. Build41/build42 stay withdrawn.
- Local startup/recovery/monitor policy, historical validation and private
  ACPI/EFI deployment are machine-specific. Reviewed AML reference material is
  already in #31; personal tables/configuration are not published.

## Default branch and privacy

This submission record starts at default source
`b9b1ed5dd7b86f1bbffeadab832515ca6564332d`. Only this document and its sanitized JSON evidence are
added to the default branch. Runtime source, installed build34, active VBL/AML
treatment, acceleration/desktop takeover, daily PR28 configuration and disabled
resident monitoring are untouched. No power action is executed.

Licence and notice files remain unchanged. Public commits contain reviewed
source/tests/docs only; raw logs, authentication material, personal firmware/EFI,
diagnostic archives and binary output remain excluded. Exact operational logs
and failed attempts stay private. See
`validation/upstream-pr-submissions-20261119.json` for the public manifest.
