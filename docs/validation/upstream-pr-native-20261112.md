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

Run all eight existing variants with `pr-native-validation.yml`; record the new
run conclusion and structured reports after completion. Even a passing rerun is
modified-test-model plus native compiler evidence, not execution of kernel
`doWaitSeq`, target GPU evidence, Tahoe migration or acceptance/merge of PRs 6-9.
The pinned upstream candidates remain separate from downstream source changes.
No binaries or firmware are uploaded. Roll back by reverting this harness-only
commit; no deployed driver, EFI or OS configuration is changed.
