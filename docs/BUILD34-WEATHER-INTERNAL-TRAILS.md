# Build34 Weather internal trails: render-pass candidate

## Symptom and evidence boundary

On November 19, 2026 the owner clarified that clouds and text accumulate
inside the Weather window. This is not a report of a moved or closed window
leaving damage on the desktop. The previous inactive application observation
did not capture pixels or identify Weather's render-pass descriptors; it
cannot prove which rendering path causes this symptom.

This source-only change starts at default-branch checkpoint
`12dff42be81a796e2ded987ed9684388690c40ec`. The accepted installed build34,
VBL, AML, render-clear plugin and startup-order baseline are retained.
The OS was read again as macOS 26.7.2 build 25G332. No application was
launched, GPU workload submitted, driver installed/loaded, WindowServer
restarted or power action requested during this source investigation.

## Audited upstream changes, in application/test order

Git independently reported upstream `main` as
`3497d87b229e4839d8d2a03ebe9127f2a30f332b`. Its locally available history
contains these three corrections, whose production source was still absent
from the default build34 tree:

1. `10c9e6560cd283cefeb9918b24d1e61b41b3f173`: clear the entire selected
   format-view attachment before a smaller draw area. Previously the
   format-view exception cleared only the area, retaining older content
   outside it. The backport uses the original view, level, layer range,
   format and clear value in a full-sized empty render pass, then loads it
   for the original draw. It does not enlarge the original draw area.
2. `e44deb7ab3c9029e69a3b4d2fb0bce324f8999ba`: refuse an unavailable required
   LOAD variant rather than silently substituting a CLEAR render pass.
   Selection now precedes the outer pass's image-layout bookkeeping and
   framebuffer creation. This is not a promise that earlier preparatory
   operations cannot already have been recorded.
3. `9543d435d7a12f8c60d3eedc6ee00c2ad12e6308`: latch a failed render-pass begin
   in the command buffer's encoding-error flag, retaining it across later
   successful begin calls and refusing submission through the existing
   retirement path. Counter-recording failures use the same flag. The field
   rename preserves its type and layout; no kernel/native user ABI changes.

Each patch was applied separately and its focused tests passed before the
next patch. The three production patches match the upstream changes. Two
comments also adopt the upstream wording: clearing a selected attachment
does not establish a full-root overwrite. The earlier surface-import fix is
retained. No speculative alpha-factor, shader, sampler, DontCare, scanout or
timing change is included.

Source headers and `LICENSE` were audited before copying. The affected
plugin files remain PolyForm Noncommercial 1.0.0 with their existing NullMoth
notice. Regression scaffolding adapts upstream tests under the repository's
default MIT/GPL-2.0 option. `LICENSE`, `LICENSES/` and
`THIRD_PARTY_NOTICES.md` match the checked upstream and remain unchanged.
No binary or third-party runtime is uploaded.

## CPU and native-build validation

`tests/test_nmplugin_render_pass_integrity.py` compiles the production
full-color-clear loop, render-pass selection and encoding-error/submit guard
with the actual public plugin structures. Fake Vulkan callbacks only record
operations; ASan/UBSan are enabled and every compiler/process has a timeout.
The previous-frame pixel history is explicitly a model. It does not prove
Weather uses this path, emulate sRGB conversion or replay actual GPU pixels.

- Baseline: four full-view-clear cases and the missing-LOAD fallback fail
  semantically, with ordinary nonzero exits; selection-order checking and
  three missing-error-latch checks also fail. Four unaffected cases pass.
  All 13 methods run without fixture compilation errors in the final
  baseline replay. An earlier harness compile needed the native Mach port
  declaration and an allowance for an existing C aggregate initializer;
  that failed harness run is not regression evidence.
- Candidate: all 13 methods pass. Coverage includes a nonzero attachment
  slot, view format/level/layers, multisampling, failed preclear, old-frame
  contents outside the draw area, unaffected LOAD/equal-area/3D/open-pass/
  transfer paths, successful LOAD and resolve selection, sticky refusal,
  successful submission and the preserved counter-flush refusal.
- The focused command is `make test-nmplugin-render-pass-integrity`; the
  same suite is also included in `make test`.

The baseline/candidate native release build, compatibility regressions and
their final results are recorded in
`docs/validation/build34-weather-internal-clear-20261119.json`.
These checks do not install or load the artifacts.

## Acceptance and rollback

This fixes reproducible source defects, not an accepted Weather visual
repair. The installed plugin still predates these corrections and the
publication-timeout logging correction at `12dff42`. Liquid Glass opacity,
the shared cause of either symptom, real FPS and long-term stability remain
unproved.

There is no live rollback to perform because deployment has not occurred.
Source rollback must use a new reverting commit, never reset or rewrite
history. A prospective hardware trial needs a new compatible plugin scope,
complete current-runtime admission and exact accepted-bundle/startup
recovery before installation authorization is exercised. Old installers,
observers and restart authorizations are consumed. Keep the daily PR28
250 ms setting, WindowServer exclusion and disabled resident monitors.
