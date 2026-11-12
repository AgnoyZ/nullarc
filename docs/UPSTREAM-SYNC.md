# Upstream synchronization, 2026-11-12

The downstream branch merges `luuumi-dev/nullarc:main` at
`8aba872560a3c9b7dc7a0ddebfad001c6dddf315` into the previous downstream head
`bd01428a371b01911bcf497b24dcbf550509d4a3`. Before the merge, the actual Git
comparison was 96 downstream-only commits and 49 upstream-only commits; the
three EDID commits followed the earlier 93/49 comparison.

This is a two-parent merge, not a squash, reset or force-push. The fork's
`main`, the installed system and the separate EFI are not modified. A local
pre-merge reference is `backup/pre-upstream-sync-20261112-bd01428`.

## Integration decisions

- `Makefile` keeps downstream panel-timing tests and adds upstream topology
  and wait-model targets.
- `nvmtl_vk.c` keeps the plugin-relative ICD path and adds upstream effective-ID
  handling for Mesa's disk cache.
- `phxfb.cpp` keeps EDID validation/DDC, native HiDPI eligibility and bounded
  scan-out alias checks. Upstream backlight PWM and display-power handling are
  incorporated, including their start-failure cleanup. EDID is still loaded
  before `IOFramebuffer::start()`.
- Hardware gamma/CLUT remain explicitly unsupported. Upstream's gamma flag
  and gamma-table registry properties are deliberately omitted because the
  downstream callbacks do not program a hardware LUT. This retains the tested
  capability contract rather than advertising an unimplemented feature.
- `PhxBringup.cpp` adopts upstream build 34, topology transport, power-state
  notifications, adaptive waiting and hang detection. Existing BO diagnostics,
  checked submission/retirement and resource quarantine remain. The watchdog
  uses the same `gpuLock` and checked, bounded queue-progress snapshot as the
  downstream submission path; stop cancels its callback before teardown or
  quarantine. Host fakes test the decisions, not actual wave killing.
- Upstream's broader PCI personalities and profile definitions are imported;
  downstream runtime gating still requires Darwin 25, `1002:1900` and
  `phx780m=1`. This is not new target support or proof of hardware topology.
- Source exports now include the topology header required by `PhxNativeABI.h`.
  The RADV lock points to the merged upstream revision and includes Phoenix
  patch 0007. The downstream native-only patch still rejects mock/host-only
  devices.
- The upstream Mesa patch/generator comparison retains its CLI checks inside
  `main()`, so ordinary Python test discovery does not execute an integration
  command without its required Mesa checkout arguments.

## Validation and limits

Run the complete Python suite from a clean disposable LF checkout. The
upstream topology test and a deterministic test-only copy of its wait model
also run in priority CI. The original wait model is restored unchanged; its
modeled fallback is not evidence of the actual kernel's completion behavior.
The actual EDID, display, allocation and queue/VM callback harnesses and native
kext/plugin compile/sign jobs must pass at the merged source. Earlier EDID
passes at `0cd76fb` do not establish this merge's build status.

Before the merge commit, a clean disposable LF snapshot ran **376 Python
tests: 348 passed, 28 skipped, no failures or errors** on Windows. The snapshot
commit was `e7816f7c9485e999c9877f6ace7e599b9857dc83` (tree
`e67dcaa84321fc386c1116036cfe0976f7abb015`); its production code and tests are
the staged merge candidate. The documentation-only addition of these results
does not change the tested code. Windows is not a native kext build pass.

The only imported patch-byte cleanup removes an extra blank line at EOF from
Phoenix patch 0007 so `git diff --check` passes. The locked native RADV build
reads the original upstream patch bytes at `8aba872`; its hunks are unchanged.

At merge source `e5bef3c`, the focused native EDID workflow
`43163472573` passed. Priority run `43163472649` and broad run `43163472552`
initially failed because the old host doubles lacked the newly merged
render-pass-light barrier, watchdog cancellation, power-management teardown
and adaptive wait APIs. The test doubles are updated to assert those paths:
35 actual submit-begin cases, watchdog cancellation before stop/quarantine,
and actual wait timeout/cap behavior. These initial runs are not complete
native-component or full-build passes. Production sources are not changed
by this test compatibility follow-up.

No driver, OpenCore configuration, ACPI table or helper is installed by the
merge. Newly imported upstream tools may have deployment side effects if run
manually; synchronization does not execute them. Target display, sleep/wake,
backlight, hang recovery and GPU acceleration still require separately
controlled tests on the actual laptop. No experimental binaries are published.
