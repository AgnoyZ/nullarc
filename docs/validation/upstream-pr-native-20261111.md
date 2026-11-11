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
The actual run ID, source SHAs and results will be recorded after completion.
