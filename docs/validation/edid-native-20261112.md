# Supplied-panel EDID: host and native build validation

Recorded 2026-11-12, Asia/Shanghai. Tested source:
`0cd76fbc9434e8f990005580ce1be9361f9973d1` on `downstream/780m-tahoe`.
This establishes the supplied-data cache and actual callback CPU behavior plus
native compilation/signing. **No AMD AUX transaction, target kernel load or
physical display acceptance was performed.**

## Corrected native run

[Run 43161573108](https://github.com/AgnoyZ/nullarc/actions/runs/43161573108)
completed **success**, workflow `edid-validation.yml`, job `native-edid`.
The runner was `macos-15-intel`, macOS 15.7.9 / 24G830, x86_64,
Apple Clang 17.0.0 (`clang-1700.0.13.5`). MacKernelSDK was pinned at
`3f750085caa17ec3a7880f11c11bf4f48cd6a164`.

- All **11 Python EDID tool/source-contract tests passed**, including the
  directory-symlink refusal test skipped on Windows.
- ASan/UBSan executed **225 cases** using the actual `loadEdid()`,
  `hasDDCConnect()`, `getDDCBlock()` and `getAttributeForConnection()` bodies
  from `phxfb.cpp`, the actual cache header and explicit fake IOKit. Reported
  `hardware_executed=false`, `kernel_loaded=false`.
- Actual-method SHA-256:
  `a44a4190bccf316a99bf4e5a0aabe7ffd9e8176a8fa5c9771092e1416933b9e1`.
- The existing actual mode/timing/color callback harness also passed with
  ASan/UBSan. Source bytes remained unchanged by the native checks.
- The actual PhxAccel kext compiled, linked, was ad-hoc signed and passed
  `codesign --verify --strict` plus `inspect_kext()`:
  identifier `com.luuumi.PhxAccel`, thin x86_64 Mach-O type 11,
  executable **341920 bytes**, SHA-256
  `bb0455768b02b692334a82a0349b16b37d86d37e2359a6f9ca06047f49ea9c72`.
- The linker emitted the same two SDK `libkmodc++` deployment-version warnings
  (objects built for 15.5, existing recipe target 11.0). This is not a
  warning-free build. No kext was loaded and no binary was uploaded.

The independent existing HiDPI workflow also completed **success** at the same
source: [run 43161573182](https://github.com/AgnoyZ/nullarc/actions/runs/43161573182).
The existing priority workflow completed **success**, both host-contracts and
native-components: [run 43161573102](https://github.com/AgnoyZ/nullarc/actions/runs/43161573102).
These are host/native-build results, not target display or performance evidence.

The broader [build run 43161573238](https://github.com/AgnoyZ/nullarc/actions/runs/43161573238)
was checked at 2026-11-12 05:34 UTC: `source-tests` completed successfully,
including the actual EDID callbacks. Its `macos-kexts` job was still running;
this record does not claim that the complete broader workflow passed.

## Local Python regression and first failures

A clean disposable LF checkout of the tested source on Windows ran **371
tests, zero failures/errors, 28 skips**. Thus 343 tests passed; Windows/POSIX
and symlink limitations are not counted as passes. No Windows C++ or native
kext compilation is claimed.

The first disposable-clone attempt left `core.autocrlf` inherited for later
`git archive` invocations. Thirteen setup/source checks refused byte-different
header exports (289 tests counted, 28 skipped); this was not a passing run.
Setting `core.autocrlf=false` only in the disposable test clone made its
subsequent archive snapshots match committed LF bytes. Production tooling and
its clean/source guards were not relaxed. The corrected complete suite above
supersedes that attempt.

Initial source `e0bb6dd7ffa15859e88d93f1a7f30284cb03a052` passed its 225
actual-callback cases but failed native kext compilation in EDID run
`43161244093` and HiDPI run `43161244115`: the pinned SDK raw-data
`setProperty` overload takes `void *`, whereas the cache returns a const
pointer. Commit `0cd76fb` adds the explicit cast for the API that copies the
input and changes the fake overload to the SDK's exact non-const signature.
No cache bounds or test expectations were weakened. The initial runs remain
failures, not partial native-build acceptance.

## Evidence boundaries and target acceptance

The fixtures use synthetic EDIDs only. Real panel exports and property
fragments remain ignored local data, outside the public evidence. Root
licences/notices are unchanged. The NullMoth reference, data provenance,
validation rules, immutable lifetime and fail-closed source precedence are
documented in [EDID.md](../EDID.md).

Remaining: separately approved deployment of an identified candidate and a
verified same-panel GPU property; observed Tahoe OS build; byte-for-byte
private comparison of native display EDID with the source; correct display
IDs; unchanged physical mode/refresh; visible desktop and sleep/wake checks;
and a controlled no-property fallback comparison. HiDPI, AMD AUX/I2C hardware
acquisition and target loadability are not established by this record.

No EFI, NVRAM, BIOS, security setting or running driver was changed. Rollback
is the source revert described in EDID.md; no runtime rollback is required
for these repository-only changes.
