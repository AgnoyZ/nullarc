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

## Verification after migration

`python -m unittest discover -s tests -v` and the C++ policy assertions run in this repository; the macOS
job compiles and signs the patched kexts, plugin, translator, RADV and LLVM. The first push of this branch
produces that evidence; until it is recorded, no run in this repository should be cited as a build pass.
