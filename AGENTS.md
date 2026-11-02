# Project instructions

- This repository is the downstream fork of `luuumi-dev/nullarc` for Radeon 780M (PCI `1002:1900`, gfx1103) on macOS Tahoe. It is the only working repository: the driver changes, tests, build recipes and validation evidence live here.
- Work on `downstream/780m-tahoe`; keep `main` identical to upstream so `git rebase upstream/main` stays possible. Do not rewrite upstream history.
- Target Radeon 780M on macOS Tahoe; record the actual OS build after migration. Do not claim Tahoe is already installed.
- The owner authorized public visibility on 2026-10-30. Keep this repository public unless the owner requests otherwise. Never commit credentials, serials, UUIDs, ROM values, raw IORegistry/ACPI/firmware dumps, diagnostic archives, photos, personal EFI configurations or OS images.
- Keep `LICENSE`, `LICENSES/` and `THIRD_PARTY_NOTICES.md` intact. Upstream components keep their own licences (MIT/GPL-2.0 for `src/phxbringup` and `tools/phxctl`; PolyForm Noncommercial 1.0.0 for `src/phxaccel` and `src/nmplugin`). `patches/` is a historical record, not an apply list.
- Preserve the working EFI in its separate repository. Do not auto-deploy drivers, alter internal Windows EFI, partition disks, reset NVRAM, change BIOS or weaken OS security as part of repository work.
- This is an experimental project, not a hardware-validated working driver. Label untested changes and require real GPU execution evidence for acceleration claims.
- Audit each upstream component and its license before copying code or binaries. Do not assume all components share one license.
- Keep experiments isolated, change one variable per test, and document rollback.
- After every coherent change: update relevant docs, run available checks and `git diff --check`, review privacy and the staged diff, commit, push, and verify the remote SHA.
- A local commit alone is not synchronized. Report push failures honestly. Never force-push, change visibility, rewrite history or overwrite unrelated work without explicit permission.
- Public CI must not upload experimental binaries until the upstream license/provenance audit is resolved and publication is explicitly approved. Keep raw logs and local caches ignored.
- Do not use Hindsight. Do not spawn subagents unless the user explicitly requests them.
