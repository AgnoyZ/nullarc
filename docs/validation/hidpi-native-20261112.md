# Native 2x HiDPI candidate: host validation

Recorded 2026-11-12, Asia/Shanghai. Actions timestamps below use UTC; the final
native run ended at 2026-11-11 16:00:26 UTC (2026-11-12 00:00:26 locally).
The target Tahoe installation/build and actual 780M display behavior remain
unverified. This record establishes host compilation and CPU behavior only.

## Tested revisions and native results

Workflow: `.github/workflows/hidpi-validation.yml`, runner `macos-15-intel`.
Both runs reported macOS 15.7.9 (24G830), x86_64 and Apple Clang 17.0.0
(clang-1700.0.13.5), using MacKernelSDK
`3f750085caa17ec3a7880f11c11bf4f48cd6a164`.

| Source commit | Actions run | Conclusion | Scope |
| --- | --- | --- | --- |
| `c6d6372bc38df5ac62646853efe74af9f76e8ac0` | `43053132573` | success | Initial driver, generator, callback harness and probe build/run |
| `8f3f8240751874ac96ca4a95de14cfa599da44fb` | `43053858163` | success | Repeated all native checks after correcting probe JSON boolean types; added runtime schema/dimension assertions |

The final run passed all eight generator/source-contract tests, including the
symlink refusal case. The ASan/UBSan harness compiled and executed the actual
`PhxAMDFB::getInformationForDisplayMode()` callback extracted from the source.
It checked native/padded geometry and bounds, unchanged default behavior, only
the two intended flag changes, unchanged physical geometry/refresh, fractional
refresh and invalid-mode/null refusals. No sanitizer error was reported.

The complete PhxAccel build, including `PhxAMDFB`, compiled, linked and signed
ad hoc; `codesign --verify --strict` and `inspect_kext()` passed:

- Identifier: `com.luuumi.PhxAccel`; thin x86_64 Mach-O type 11.
- Executable bytes: 337648.
- Executable SHA-256: `7e97e3d08c18712dfd0a09ee3321c69e8e0c62e1c8752c1c9ced5a2bb41abfc9`.
- The linker emitted two deployment-version warnings for SDK libkmodc++ objects
  built for macOS 15.5 while the existing kext recipe targets 11.0. The recipe
  was not changed; this is not a warning-free build or a kernel-load test.

The read-only CoreGraphics probe compiled with `-Wall -Wextra -Werror` and ran.
The hosted display reported logical and backing dimensions both 1920x1080 at
30 Hz, with `hi_dpi_2x=false`. JSON boolean types and every enumerated mode's
dimension relationship passed runtime checks. This is a non-target 1x result,
not a demonstration of the candidate HiDPI mode. Tracked sources remained
unchanged after the native build/test run.

## Wider source checks

- A clean disposable LF checkout of `c6d6372` on Windows ran the full Python
  suite: 332 tests, 26 platform skips, remaining 306 passed. One of those skips
  was the new directory-symlink test because local Windows lacked symlink
  privileges; that case passed on the native macOS runner.
- Ubuntu run `43053132860`, job `source-tests` (`130635366548`), passed the
  full 332-test Python suite without skips and all its existing policy and
  fake-IOKit sanitizer stages. The overall workflow was then deliberately
  cancelled during its separate full-stack macOS build, which was redundant
  for this focused display/probe change. Its overall conclusion is cancelled,
  not success; only the completed source job is counted here.
- The corrected source `8f3f824` also passed Ubuntu `source-tests` in run
  `43053858104`, job `130637979330` (completed 2026-11-11 16:03:25 UTC). Its
  subsequent full-stack macOS job was likewise cancelled as a duplicate.
  Neither cancelled overall workflow is reported as a full-stack build pass.

The original upstream PR matrix's timing-sensitive `make test` failures are
documented separately in `upstream-pr-native-20261111.md`. This HiDPI workflow
does not rerun or resolve that unrelated baseline test. It also does not
rebuild the Metal plugin, translator, Mesa or LLVM runtime stack.

## Reproduction and remaining acceptance

```sh
gh workflow run hidpi-validation.yml --repo AgnoyZ/nullarc --ref downstream/780m-tahoe
```

Reference review, opt-in `phxfbhires=1`, offline generation, the actual display
ID requirement, A/B/C testing and rollback are in `docs/HIDPI.md`. Target
acceptance still requires the observed Tahoe build, current logical/backing
sizes at exactly 1:2 matching the physical GOP raster, visible text/cursor and
stable present, plus mode-return and sleep/wake checks. Arbitrary downsampling
is not implemented. No GPU execution, HiDPI display success, acceleration,
loadability or performance claim follows from these host checks.

No kext was loaded or deployed. No EFI/NVRAM/security changes, public binary
uploads, firmware copies or raw target diagnostics were made. Only sanitized
host test conclusions and build identity are recorded here.
