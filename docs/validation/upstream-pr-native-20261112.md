# Upstream wait-model rerun: deterministic test overlay

The prior eight-variant run `42988239667` remains a failed run. Its build-only
passes and scheduling-sensitive wait assertions remain recorded in
`upstream-pr-native-20261111.md` and its JSON; they are not reclassified.

The new runner uses `tools/pr_wait_seq_overlay.py` only in the disposable pinned
upstream candidate. The original test's LF-normalized SHA-256 must be
`4839215157e2c904b0b27b75ef2f57c07b38db0cd680c4da580fca7fec45654d`; a changed
input is refused. The test comes from upstream baseline
`8aba872560a3c9b7dc7a0ddebfad001c6dddf315`. Its root licence was audited:
`tests/test_wait_seq.cpp` has no separate notice and is covered by the root
MIT-or-GPL-2.0-only rule for other nullarc code. Existing notices remain intact.
No NVIDIA hardware implementation or binary is copied.

The original model engine is byte-for-byte unchanged. The overlay replaces
wall-clock mock sleeps/worker scheduling with one virtual clock, scheduling
retirement at 200us and 3ms. Existing success, retirement and positive delay/sleep
assertions remain; added exact checks require four polls, or twenty polls plus
two sleeps. The timeout test now requests 100 seconds and checks the actual
`PHXN_WAIT_CAP_NS` value from that candidate's ABI (2 seconds), rather than
claiming a cap test while requesting only 2ms. There is no timeout increase,
assertion removal or production driver change.

The report records original/effective/helper hashes and explicitly labels
`kernel_method_executed: false`. After the sanitizer suite, the model binary is
run twenty times per variant to check the former scheduling sensitivity. The
overlay is restored byte-for-byte, including on test failure, before production
compilation; an external modification is refused rather than overwritten. A
separate git-integrity phase confirms restoration, and the existing final
source-integrity/signature/export/firmware checks remain. The untouched original
file and its old failed CI stay available as the comparison.

## Completed rerun

Workflow `pr-native-validation.yml`, run
[`43062283194`](https://github.com/AgnoyZ/nullarc/actions/runs/43062283194),
completed/success at harness commit
`c59d49c9743015f537718370b95cc6f59b64f201`. All eight jobs used
`macos-15-intel`: macOS 15.7.9 / 24G830, Apple Clang 17.0.0.

| Candidate | Modified model / sanitizer tests | Native components and strict signatures |
| --- | --- | --- |
| Baseline | passed | passed |
| PR 6 | passed, sampler-key tests passed | passed |
| PR 7 | passed, surface-key tests passed | passed |
| PR 8 | passed, descriptor-mask tests passed | passed |
| PR 9 | passed, panel-timing tests passed | passed |
| PR 6+7 | passed, both PR suites passed | passed |
| PR 6+7+8 | passed, all three PR suites passed | passed |
| PR 6+7+8+9 | passed, all four PR suites passed | passed |

All eight structured reports have empty `failed_tests`, `status: passed`,
`native_build_status: passed` and `test_overlay_restored: true`. Each includes
twenty successful deterministic model repeats. The restoration check ran before
compiling PhxBringup, PhxAccel and the Metal plugin; final tracked-source
integrity and strict signature checks also passed.

Across all variants, the 997 exported plugin symbol names have SHA-256
`ce01e4a9ecc5869a7c3680c1035c6be6014df86e6f41df0c7f2f681518d61a61`.
The 323 plugin warning messages have SHA-256
`b747ad39701776d1a48883052fa81dec8b151ec1b7296bb9eae7b3e8f4a9c68d`;
this checks equality with baseline, not warning elimination. All seven firmware
fixture hashes and original/effective/helper overlay hashes match baseline.
The complete curated reports, source/dependency pins, job metadata and checked
comparisons are in `upstream-pr-native-20261112.json`. Raw logs remain ignored.

This is modified-test-model plus native compiler evidence, not execution of
kernel `doWaitSeq`, target GPU evidence, Tahoe migration or acceptance/merge of
PRs 6-9. The pinned upstream candidates remain separate from downstream source
changes. The old failed run is preserved. No binaries or firmware are uploaded.
Roll back by reverting the harness-only commit; no deployed driver, EFI or OS
configuration is changed.
