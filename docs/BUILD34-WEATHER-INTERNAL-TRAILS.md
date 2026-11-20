# Build34 Weather internal trails: render-pass candidate and local trial

## November 20 rollback and hold

The owner reported repeated restarts after the authorized baseline boot and
requested rollback on November 20, 2026. The boot trial is not accepted.
Readback found existing recovery markers in six successive installed scopes,
and disk plugin/jobs had already fallen back past the Weather trial's exact
before state to the older owner baseline. The first inspected Weather failure
is a framebuffer startup-admission assertion; the specific panic/restart
cause is not proved, and the markers are not a measured reboot count.

Under the rollback request, both exact older-owner startup jobs were archived
with verified recovery copies and removed from the launch directory. Both
services were already unloaded. The new baseline observer job was absent;
final readback found no startup, guardian, observer, shutdown or reboot
process. Seven older-owner policy files match with no mismatches; only the
two deliberately archived jobs are missing. The live plugin matches that
older fallback. The loaded PhxBringup matches the pre-R1a control image;
R1a was never installed or loaded. PhxAccel is not listed loaded and its
debug counters are unavailable, so no accelerated-desktop success is claimed.

Containment did not change driver images, kernel/cache, EFI/ACPI, security or
PR28 configuration, launch a GPU test, restart WindowServer or request power.
The boot stayed unchanged through the final checks on macOS 26.7.2 build
25G332. This confirms containment readback, not a successful fresh recovery
boot or proof that every restart cause is fixed. Keep automatic startup and
desktop takeover disabled, preserve all failed evidence and backups, and do
not reinstall this candidate, resume optimizations or replay consumed scopes
without new explicit owner authorization. See the
[sanitized rollback record](validation/build34-weather-boot-rollback-20261120.json).

## Symptom and evidence boundary

On November 19, 2026 the owner clarified that clouds and text accumulate
inside the Weather window. This is not a report of a moved or closed window
leaving damage on the desktop. The previous inactive application observation
did not capture pixels or identify Weather's render-pass descriptors; it
cannot prove which rendering path causes this symptom.

The source investigation started at default-branch checkpoint
`12dff42be81a796e2ded987ed9684388690c40ec`. The accepted installed build34,
VBL, AML, render-clear plugin and startup-order baseline are retained.
The OS was read again as macOS 26.7.2 build 25G332. No application was
launched, GPU workload submitted, driver installed/loaded, WindowServer
restarted or power action requested during that source investigation. The
subsequently authorized local trial is recorded separately below.

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

## Authorized same-boot local trial

After the owner authorized installation, a fresh private scope admitted
source `87859b323267030afdfdcd9f4e52dc7168697686`. A complete current-runtime
readback passed before preparation. The full installed bundle was copied;
only its `NVMTLDriver` executable was replaced, with its metadata retained,
and the bundle was signed and verified. The exact before/after manifest
comparison found no other changed path. Runtime libraries, resources,
kernel images, the complete cache and EFI/ACPI were retained.

Twenty-four CPU tests covered exact contract derivation, rejection of
unexpected bundle/library/metadata changes, one-shot installation, partial
transition readback, exact rollback and refusal of power requests. They
passed before the one installation. An actual invocation of the new owner
`check` entrypoint and independent installed-state readback then passed.
The new two startup jobs retain the accepted startup-order implementation,
serial checks, timing support and 45/150/300-second limits. Their exact
plugin expectation now matches the candidate on disk; a future boot with
this candidate has not been tested. No startup job was replayed or
bootstrapped in the current boot.

Weather was launched once through Launch Services in the foreground. A
one-second sample of the exact new process confirmed the candidate plugin
UUID was mapped. The original WindowServer continued using its previously
accepted plugin, and its process identity was preserved. This is a
Weather-only process-loading result, not candidate compositor acceptance.

The finite observation sampled Weather at 2, 10, 30 and 60 seconds. It was
active, unhidden and normal priority at all four samples. There was no
Weather window in the 2-second startup sample; the same on-screen main
window was present at 10, 30 and 60 seconds. The strict collector therefore
refused its all-four-samples visibility condition. That refusal is retained
unchanged. A separate qualification records only the three settled visible
samples spanning 50 seconds; it does not retroactively pass the original
collector or prove continuous rendering between samples.

Four driver error counters remained zero, the same WindowServer survived,
and desktop counters progressed. The bounded Weather log interval contained
no `NullMoth:` records for the exact new process, including no publication
deadline messages. The candidate includes `12dff42`'s release-time timeout
logging correction, but zero observed messages do not prove that Weather
exercised the corrected path or that every publication succeeded.

Screen-capture permission preflight was false. No permission was requested,
capture attempted or pixel output measured. Weather remains open for owner
visual inspection. These results and the preserved initial collector
refusal are recorded in
`docs/validation/build34-weather-internal-trial-20261119.json`.

A fresh full runtime readback after Weather observation also passed. The
repository's `make test` passed again; unavailable firmware-file fixtures
were skipped under the existing test policy. These CPU checks and runtime
identity checks do not replace visual acceptance.

## Acceptance and rollback

The candidate is installed and loaded in Weather, but its clouds/text
trails remain pending visual acceptance. Its actual render-pass descriptors
have not been captured. Liquid Glass opacity, a shared cause of both
symptoms, real FPS and long-term stability remain unproved.

The new scope preserves an exact complete pretrial plugin bundle, an atomic
rollback bundle and both original startup jobs. Scoped rollback restores
only the recognized plugin and those two jobs. It has no reboot path and
refuses power requests; an unknown live state must be inspected rather than
overwritten. Existing processes do not change their mapped plugin merely
because the disk bundle changes. Do not run an old exact-plugin readback or
installer against this new candidate and interpret its expected identity
mismatch as a GPU failure.

The trial requested no system/WindowServer restart or power action. Keep
daily PR28 waiting at 250 ms, the WindowServer exclusion and disabled
resident monitors. Earlier installers, observers and restart scopes remain
consumed. Source rollback must use a new reverting commit, never reset or
rewrite history. Do not call this trial an accepted repair until the owner
verifies the internal Weather animation and text visually.
