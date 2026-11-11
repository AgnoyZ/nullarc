# Prioritized improvements: host evidence

## BO arithmetic / parameter provenance

Code `8a6cf01332b29b2b2705423c2ccfecc448cb7a78`, focused GitHub Actions
run `43058241429`: completed/success. Both jobs completed successfully.

- Ubuntu host contracts: all 335 Python tests passed; the actual BO allocation
  harness passed its 30 cases under ASan/UBSan. Existing BO retirement, context
  retirement and actual page-walk/BO cleanup sanitizer suites also passed.
- Native components: macOS 15.7.9 build 24G830, Apple Clang 17.0.0. The same
  30 allocation cases passed; actual PhxBringup and PhxAccel compiled/linked and
  passed ad-hoc signing/strict verification. The actual Metal plugin also
  compiled/linked and passed signing/strict verification.
- Windows disposable LF clone: 335 tests ran, 26 platform skips, all remaining
  tests passed. Those skips are not native execution passes.

Builds retain existing warnings, including kernel variable shadowing, SDK kmod
deployment versions, and deprecated/incomplete Metal protocol declarations. This
is not a warning-free build. The separate expensive full-stack automatic run
`43058241804` was cancellation-requested after the focused run completed; it is
not counted as a full-stack validation pass. No binaries were uploaded.

These results check arithmetic, fault paths, lifetime regressions and native
compilation. They establish neither target hardware/IP discovery, independent
resource reservations, client-task allocation safety, kernel-VA pressure relief,
real GPU execution nor a migrated Tahoe installation.

## Metal optional declarations

Implementation and dependency-matrix tests are added separately; native and
host CI results will be recorded after that revision finishes.
