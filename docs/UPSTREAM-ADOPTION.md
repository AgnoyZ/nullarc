# Downstream adoption of upstream PRs 6-9

Updated 2026-11-12. This tracks source adoption into
`downstream/780m-tahoe`, separately from the temporary pinned-candidate matrix
in `validation/upstream-pr-native-20261112.md`. Passing that older matrix does
not establish that the current downstream combination works on a GPU.

| PR | Reviewed upstream commit | Downstream source status |
| --- | --- | --- |
| 6, sampler slot keys | `55764a0b69658a92870fc2b75e0be3a695382e38` | Adopted; downstream native CI pending for this revision |
| 7, IOSurface keys | `394f162ae7bf5cc9d57bb673a9a6b326c46c325e` | Next, separately reviewed and tested |
| 8, descriptor masks | `5a8a088011946c8089bb27e10d0dba117bf1b48e` | Awaiting downstream integration review |
| 9, read-only panel timing | `c9da802a8dbf3753fa15b5cd903934712c3c80f6` | Awaiting downstream integration review; does not set modes |

## PR 6

The five render/compute sampler-key sites use the upstream immutable decimal
keys for indices 0-15. Other `NSUInteger` values retain the original formatting
fallback. Binding validation, dictionary semantics and sampler state/lifetimes
are unchanged. The actual upstream helper and Foundation regression test are
included, with their PolyForm Noncommercial 1.0.0 SPDX notices preserved.
`NVMTLObjects.m` is covered by the existing component licence and required
NullMoth notice. No licence or notice file is changed.

The Makefile target is added to the existing downstream pinned-action native
workflow instead of copying upstream's floating-action/main-only CI job. The
sanitizer test checks 517 indices, immutable key identity, 262144 concurrent
lookups and interchange with legacy dictionary keys. A clean disposable Windows
LF snapshot ran 343 Python tests with 26 platform skips and no failures. The
first snapshot was refused by existing clean-source guards before testing;
the rerun used a committed disposable snapshot without weakening those guards.
Host native results must
be recorded after the current downstream CI finishes. There is no measured
desktop latency/FPS claim and no target GPU execution.

## Rollback and publication

Each PR is adopted in its own downstream commit so it can be reverted without
rewriting history. Revert dependent later adoptions first if their shared test
or documentation context conflicts. This work does not merge or close the
original GitHub PRs, change `main`, deploy drivers or alter EFI/OS settings.
Source and tests only are published; experimental binaries and raw logs are
not uploaded. The installed target Tahoe build remains unverified.
