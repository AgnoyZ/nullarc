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
`43058241804` was cancelled after the focused run completed; it is
not counted as a full-stack validation pass. No binaries were uploaded.

These results check arithmetic, fault paths, lifetime regressions and native
compilation. They establish neither target hardware/IP discovery, independent
resource reservations, client-task allocation safety, kernel-VA pressure relief,
real GPU execution nor a migrated Tahoe installation.

## Metal optional declarations

Code `330b54dbe84d7fd7d5c7a68925736358279e9ebe`, focused run `43058841913`:
completed/success. Ubuntu ran all 337 Python tests and the lifetime/allocation
suites. Both Linux and macOS passed the 96-combination actual capability/dependency
body harness under ASan/UBSan. macOS 15.7.9 / 24G830, Apple Clang 17.0.0 also
compiled, linked, signed and strict-verified both kexts and the actual Metal plugin.
This is host compilation/dependency behavior, not whole-family Metal conformance,
target GPU execution or a Tahoe migration.

The separate full-stack run `43058841865` was cancelled after the
focused check passed; it is not counted as a full-stack pass.

## Shader caches

Code `373bb0ab10f5a90c2960b8aee715d203887415b4`, focused run `43060440232`:
completed/success. Ubuntu passed all 339 Python tests. Linux/macOS passed actual
cache I/O under ASan/UBSan, including 480 concurrent process/thread writes; macOS
passed 20000 Foundation LRU oracle operations and the actual-wrapper checks.
Both kexts and the actual plugin compiled/linked/signed/strict-verified on
macOS 15.7.9 / 24G830 with Apple Clang 17.0.0. A fresh Windows LF clone ran
339 tests with 26 platform skips and no failures. No shader execution or speedup
was measured. Separate full-stack run `43060440414` was cancelled
after focused success, not counted as a pass.

## Submission refusal

Code `e255533d67e8796e30d075558fdf2ebf1bb0af5e`, focused run `43061127998`:
completed/success. All 340 Python tests and existing host/lifetime suites passed.
Both Linux and macOS passed 33 actual begin/release-body fault cases under
ASan/UBSan, using explicit Vulkan, witness, retirement and timing fakes. Actual
kext/plugin builds and strict signing verification passed on the same macOS
15.7.9 / 24G830, Apple Clang 17.0.0 host. No real fence/reset/power behavior was
tested. Full-stack run `43061127991` was cancelled after focused
success and is not counted as a pass.

## Unsupported hardware color updates

Code `87c5042f6fa3ec7fed528d297ef2117752817d3f`, focused run `43061702640`:
completed/success, 341 Python tests and native checks passed. Independent HiDPI
run `43061702671` also completed/success, including actual framebuffer callback
tests, the read-only probe build and actual PhxAccel compilation/signature checks.
Both gamma overloads and CLUT explicitly return unsupported; actual callback
tests check refusal and unchanged input. No LUT programming or target color
verification is implied. Full-stack run `43061702814` was cancelled after
focused success and is not counted as a pass.

## Final downstream code and upstream matrix

Code `c59d49c9743015f537718370b95cc6f59b64f201`, focused run `43062395899`:
completed/success. Ubuntu ran 343 Python tests with one skip and no failures;
the skipped check needs the pinned upstream Git object absent from that shallow
checkout. Actual-method lifetime/allocation/capability/cache/submission and
framebuffer host suites passed, alongside actual kext/plugin compilation and
strict signature verification on macOS 15.7.9 / 24G830, Apple Clang 17.0.0.
The corresponding pinned-object restoration checks and wait-model execution
ran separately in the upstream matrix. A fresh disposable Windows LF clone
ran 343 tests with 26 platform skips and no failures. Windows skips are not
native execution passes. Full-stack run `43062275001` was cancelled and is not
counted as a pass; all six full-stack cancellations listed here were confirmed
as completed/cancelled.

Upstream matrix run `43062283194` completed/success for baseline, PRs 6, 7, 8
and 9 individually, and combinations 6+7, 6+7+8 and 6+7+8+9. Each passed its
modified wait-model suite, twenty deterministic repeats, relevant PR tests,
native compilation and signing/strict verification. All eight reports confirm
the test overlay was restored before native compilation. Export names, plugin
warning messages and firmware fixture hashes match baseline. Detailed pins,
hashes and reports are in `upstream-pr-native-20261112.md` and its JSON.
The prior failed run remains unchanged; no PR is merged by this validation.

No target GPU, kernel `doWaitSeq`, display scanout, reset/suspend/resume or
performance acceptance has been established. Native builds still emit
warnings. No drivers were deployed, no binaries were uploaded, and the target
Tahoe installation/build remains unverified. Raw logs and disposable clones
remain ignored; only structured validation metadata is published.
