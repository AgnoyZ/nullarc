# Upstream PR 6-9 native validation

This is a separate, manually dispatched compiler/test matrix for the current
upstream PRs. It does not replace the older pinned downstream build pipeline,
merge the PRs into the downstream driver, install a driver, or execute GPU work.

## Inputs and reproduction

Workflow: `.github/workflows/pr-native-validation.yml` on `downstream/780m-tahoe`.
Runner: `macos-15-intel`. Invoke with:

```sh
gh workflow run pr-native-validation.yml --repo AgnoyZ/nullarc --ref downstream/780m-tahoe
```

The runner pins upstream baseline `8aba872560a3c9b7dc7a0ddebfad001c6dddf315`
and the four reviewed PR heads in `tools/pr_native_validation.py`. It tests the
baseline, each individual PR, PRs 6+7, PRs 6+7+8, and PRs 6+7+8+9. The disposable
candidate checkout is independent of the validation harness and downstream
driver sources. Integration resolves only the reviewed additive conflicts in
the CI jobs, Makefile targets and the two key-header imports; an unexpected
conflict fails the run. The report records the resulting source tree hash.

Each variant downloads real Phoenix firmware fixtures (recording their hashes),
runs the original C++ suites with ASan/UBSan and the Phoenix profile tests, and
runs any PR-specific sanitizer tests. It natively compiles the Metal plugin,
PhxBringup and PhxAccel, checks x86_64 Mach-O types and kext identities, signs
the outputs ad hoc and verifies the signatures. Plugin export-name and warning
message hashes allow comparison with the unchanged baseline.

## Evidence boundaries

Reports appear in each Actions job summary and as `NULLARC_NATIVE_REPORT=`
records in the job logs. No experimental binary artifacts, firmware, raw
hardware logs or personal configuration are uploaded. Successful hosted tests
do not establish Tahoe/780M GPU correctness, WindowServer stability, panel
behavior, sleep/wake correctness, desktop FPS, or installation readiness.
The macOS runner is a build/test host, not the target machine.

No previous self-reported PR validation is counted as this workflow's result.
Structured evidence is in `upstream-pr-native-20261111.json` alongside this file.

## Completed results

Run `42988239667`, workflow commit
`7341c7816e71b5e805534b456752c1a534c6afb1`, completed on 2026-11-11.
Every job used `macos-15-intel`, reporting macOS 15.7.9 (24G830), x86_64 and
Apple Clang 17.0.0. The overall Actions conclusion is **failure**; it must not
be presented as a fully passing CI run.

| Variant | Plugin and two kexts: compile/sign/inspect | PR-specific ASan/UBSan checks | Original `make test` |
| --- | --- | --- | --- |
| Unmodified upstream baseline | Passed | Not applicable | Failed: existing wait-sequence assertion |
| PR 6 | Passed | Sampler keys passed | Same failure |
| PR 7 | Passed | Surface keys passed | Same failure |
| PR 8 | Passed | Descriptor masks passed | Same failure |
| PR 9 | Passed | All 43 panel-timing cases passed | Same failure |
| PRs 6+7 | Passed | Both key suites passed | Same failure |
| PRs 6+7+8 | Passed | All three plugin suites passed | Same failure |
| PRs 6+7+8+9 | Passed | All four PR suites passed | Same failure |

Across all eight variants, plugin export names were identical (997 symbols),
and the plugin compiler warning messages were identical (323 warnings). The
seven firmware fixture hashes also matched. Each job verified that its tracked
candidate source files were unchanged after compilation and testing. These are
native compiler, CPU correctness and structural/signature results, not runtime
GPU acceptance. The translator, Mesa and LLVM runtime stack was not rebuilt by
this focused PR matrix.

The existing downstream Python suite was also run in a disposable LF checkout:
324 tests, 25 platform skips, remaining tests passed. The initial Windows CRLF
checkout caused two byte/patch comparison failures; no production source was
changed to address them.

## First native attempt

Run `42987480599` exposed an unchanged baseline test failure in
`tests/test_wait_seq.cpp`: `test_extended_wait_adaptive_sleep` asserted
`g_sleep_calls > 0`. The test's mock 50-microsecond delay uses an actual host
sleep while the simulated wait engine advances a fixed 50 microseconds. On
this Intel macOS runner, real scheduling can let the 3-millisecond retirement
thread finish before the simulated counter reaches its sleep phase. The same
assertion failed in the unmodified baseline, so this is not evidence that a PR
introduced a regression. This original test is retained without modification.
The first attempt also saw the short-wait test's `!timed_out` assertion fail in
the all-four-PR variant. PR 9 and PRs 6+7 passed that first complete attempt,
consistent with the original test's scheduling sensitivity rather than a
repeatable difference introduced by these changes.

The harness now records test failures and continues through the independent
PR tests and native builds. A test failure still fails the job; a successful
native build is reported separately. The panel timing suite also runs directly
because `make test` would otherwise stop before reaching it.

The older downstream full-stack workflow was automatically triggered by each
validation-only push. Those duplicate push runs were deliberately cancelled;
the original full-stack pipeline and pinned downstream driver were left intact.
No target driver installation, reboot, EFI modification or public binary upload
was performed.
