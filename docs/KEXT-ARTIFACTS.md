# Manual downloadable kext builds

The owner requested downloadable CI kexts on 2026-11-12. This is a narrow
exception to compile-only CI: `.github/workflows/kext-artifacts.yml` can
publish **PhxBringup.kext and PhxAccel.kext only**, for experimental
noncommercial testing. It is manual, limited to this repository and
`downstream/780m-tahoe`, and retains the artifact for seven days.
Push/PR validation and full Metal-stack publication policy are unchanged.

```sh
gh workflow run kext-artifacts.yml --repo AgnoyZ/nullarc --ref downstream/780m-tahoe
gh run list --repo AgnoyZ/nullarc --workflow kext-artifacts.yml --limit 3
gh run watch RUN_ID --repo AgnoyZ/nullarc --exit-status
gh run download RUN_ID --repo AgnoyZ/nullarc --dir kext-download
```

Replace RUN_ID with the exact completed run. The artifact name contains its
full source SHA. The download contains a `.tar.gz` plus an outer SHA256SUMS;
the archive preserves executable permissions which the Actions ZIP wrapper
does not preserve for individual uploaded files.

On macOS, inside the download directory:

```sh
shasum -a 256 -c SHA256SUMS
tar -xzf nullarc-kexts-SHORT_SHA.tar.gz
cd nullarc-kexts-SHORT_SHA
shasum -a 256 -c SHA256SUMS
codesign --verify --strict PhxBringup.kext
codesign --verify --strict PhxAccel.kext
```

Use the actual archive/directory name. Read `build-report.json`,
`KEXT-PROVENANCE.md`, licences and `INSTALL-zh.md` before an operator decides
to deploy. No installer, firmware, plugin, userspace runtime, personal EFI,
raw logs, raw EDID or hardware dumps are packaged. Both kexts are built from
the same clean commit using the pinned SDK; they are ad-hoc signed, not
notarized or target-tested. Source archives contain committed allowlisted
blobs, never the developer's working tree. Unexpected kext files and symlinks
are refused before upload. Missing artifacts, storage-quota errors or failed
signature/structural checks fail the run, rather than reporting success.

The narrow provenance review is in `KEXT-PROVENANCE.md`. It does not clear
the translator/Mesa/LLVM/firmware stack for binary publication. A successful
CI job is neither permission to alter the user's OS nor evidence of stable
120 Hz, Metal performance or safe loading on the target laptop.
