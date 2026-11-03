# Migration to the fork as the single working repository (2026-11-02)

The Radeon 780M research project used to keep driver code as a pinned `upstream/nullarc` submodule plus
28 patch files, with the tooling and evidence in `AgnoyZ/radeon-780m-tahoe`. Since this commit the fork
`AgnoyZ/nullarc` is the only working repository: driver changes are ordinary commits on
`downstream/780m-tahoe`, and the tooling lives beside them.

## What moved

- `tools/` — staging, build, firmware manifest/profile, target inventory and preflight gates, boot gate,
  and the sanitizer/fake-IOKit runners.
- `tests/` — the Python suite, C++ policy assertions, runner tests and shell fixtures.
- `docs/` — design notes, audit records, `docs/validation/` evidence and the display-path notes.
- `patches/` — kept as the historical record of the reviewed series (and as fixtures for two tests that
  reconstruct the pre-0027 method). It is hashed into provenance but never applied.
- `firmware.lock.json`, `upstream.lock.json`, `.gitattributes`, `AGENTS.md`, `.github/workflows/build.yml`.
- Canonical headers under `src/`: `PhxHardwarePolicy.hpp`, `PhxPspLayout.h`, `PhxBootMemory.h`,
  `PhxGartLayout.h`, `PhxMesQueueLayout.h`, `PhxFirmwareProfile.h`, `PhxRuntimePath.h`. The build
  directories keep their copies, and staging refuses to proceed if a copy drifts from the canonical file.

## What changed in the model

- `tools/prepare_source.py` no longer exports a submodule and applies patches. It exports `HEAD` from Git
  objects into a fresh staging directory, requires a clean worktree, verifies the copied headers and the
  generated firmware profile, and records `source_commit` plus per-file hashes. The `patches_sha256`
  provenance key became `historical_patches_sha256`.
- `tools/prepare_radv.py` reads the Phoenix patch series from this repository (`upstream.lock.json` →
  `"nullarc": {"path": ".", "commit": <reviewed series commit>}`). The pinned commit must exist; it may be
  an ancestor of `HEAD`.
- `tools/build_radv.py` takes the shared ABI headers from `src/phxbringup` instead of a submodule path.
- The CI workflow no longer checks out submodules and triggers on `main` and `downstream/780m-tahoe`.
- `main` stays identical to upstream `luuumi-dev/nullarc`; rebase the branch rather than merging upstream.

## What did not move

Nothing relevant remains in `AgnoyZ/radeon-780m-tahoe`. That repository is frozen with a pointer to this
fork; its history keeps the earlier patch-based workflow. `docs/validation/*.json` here are historical
records of runs made before the migration (they name the old repository and patch revisions) and are not
current CI evidence.

## Files the first import missed (fixed)

The first import left out three test-only inputs, which made the fork's own CI fail at
`tools/test_bringup_transport.py` with `'IOKit/IOKitLib.h' file not found`:

- `tests/fake_iokit/{IOKit/IOKitLib.h,CommonCrypto/CommonDigest.h}` — the stub headers every
  `tools/test_*.py` supplies with `-I tests/fake_iokit` to compile the real `mesboot.c`/`phxctl.c`
  against a fake transport.
- `tests/fake_native_iokit/{IOKit/IOKitLib.h,CoreFoundation/CoreFoundation.h}` — the same idea for the
  native-shader-probe harness.
- `tests/fixtures/{compute_increment.ll,compute_increment.metal,packaging_only.c}` — synthetic IR/Metal
  sources used by the translator, AIR-runtime and plugin steps of the macOS job. They are not firmware,
  so `.gitignore` now ignores `tests/fixtures/*` but keeps these three tracked; `make fixtures` still
  downloads into the ignored `tests/fixtures/phoenix/`.

No other path in the old repository is absent here: its whole tree was compared against this branch, and
the only remaining difference is its `.gitmodules`, which no longer applies.

## Verification after migration

`python -m unittest discover -s tests -v` and the C++ policy assertions run in this repository; the macOS
job compiles and signs the patched kexts, plugin, translator, RADV and LLVM.

The first two pushes after the migration each showed a defect the old workflow had hidden, both fixed now:

- `41395590380` — source tests failed because the fake-IOKit headers and the three synthetic fixtures
  were missing (see above). Fixed in `19c4a73`: that run's `source-tests` job then passed all 21 steps,
  including every "without hardware" runner.
- `41593751055` — with source tests green, the macOS job reached the RADV stage and stopped with
  "Pinned RADV patch-series commit is missing from this repository": `tools/prepare_radv.py` reads the
  reviewed Phoenix series with `git show <pinned commit>:patches/...`, but CI checked out with the default
  depth of 1, so that ancestor object did not exist. The macOS job now checks out with `fetch-depth: 0`,
  and the error message names the cause.
- CI evidence only counts inside this repository. `docs/validation/*.json` are historical records of runs
  made in the old repository (they name it and its patch revisions); do not cite them as a build pass for
  this branch.
