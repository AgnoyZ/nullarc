# Build34 render-clear preservation

## Problem and scope

On 2026-11-19 the owner reported intermittent duplicated pointer images and
gray squares during mouse movement. Duplicated pointers are an interpretation
of the report; this task has no photograph, video or simultaneous compositor
and scanout capture establishing where the corruption originates.

The default branch still contained a separately reproducible correctness bug:
render `MTLLoadActionClear` skipped importing the CPU backing. For an IOSurface
it also recorded the entire root texture in `_surfOverwrites`, suppressing
later imports in the same command buffer. A clear can cover only a texture
view or subresource of a larger root backing. Pixels outside the selected
attachment must retain their defined contents; they cannot inherit stale GPU
pixels. The earlier description also included a smaller render area as a
preservation boundary. That was too broad: a smaller draw area still clears
the whole selected attachment. The subsequent format-view correction is
documented in [the Weather follow-up](BUILD34-WEATHER-INTERNAL-TRAILS.md).

Upstream fixed this in
[`531bac34989f32b861c77f5788290b9b6615405d`](https://github.com/luuumi-dev/nullarc/commit/531bac34989f32b861c77f5788290b9b6615405d),
tracked there as B-60. Its audit explicitly leaves the relationship to B-58's
reported cursor trails unproved. The history reconciliation deliberately
deferred this runtime change; having the upstream commit in ancestry did not
adopt its source.

This backport starts from default-branch commit
`4c52280b1ae75602fadbc2992d020baeb2cf07a0`. Its entire runtime change is the
upstream production patch in `src/nmplugin/NVMTLObjects.m`: primary and
additional color attachments retain `nvmtl_surface_in_for_cb` for Clear, for
both IOSurface and buffer-backed textures. No render clear declares a full-root
overwrite. The existing full-blit/replace overwrite checks, pending-writer
handling and seed-based import avoidance are preserved.

The patch preserves the owner-selected build34 runtime lineage, A1/A2/corrected
A3, the ACQUIRE-prefix correction and PR28 policy. The source patch changes no
build41/build42 source, kernel, native ABI, framebuffer, VBL or ACPI. The
subsequent authorized plugin installation and next-boot admission update are
recorded below. The active VBL and local AML batch-copy treatment remain in use.

## Validation

The CPU regression adapts the upstream test and compiles the actual two
production preparation branches, with modeled CPU/GPU pixel arrays and a
one-pixel view/subresource clear. Each action runs through primary/additional attachment and
IOSurface/buffer-backed combinations under ASan/UBSan. Nonzero exit codes
report mismatched pixels without deliberately crashing a process.

- Unchanged baseline: all four Clear combinations fail on untouched pixel 1
  (`9` instead of `2`); all four Load combinations pass. The final test was
  rerun against the private baseline snapshot, with no compilation errors.
- Candidate: all eight combinations pass, including the cleared pixel and
  preservation of the other three pixels.
- Existing publication-wait suite: all 10 test methods pass, including the
  WindowServer exclusion, bounded timeout and preservation of pending work.
- Existing plugin integration suite: all four methods pass under ASan/UBSan.
- Existing surface-key fixture: 77 boundary keys and 16,384 concurrent
  registry/monitor cycles pass.
- Default-worktree `make test` passes. Firmware-file fixtures are absent and
  skipped; synthetic parsing runs. Its CPU models do not constitute native
  GPU execution. This does not change the previously recorded failure of the
  separate upstream `test_wait_seq.cpp` suite.
- Baseline and candidate both compile as x86_64 release plugins with the
  existing native recipe, `NVMTL_RELEASE=1`, macOS 15 minimum and availability
  errors enabled. Both have the same multiset of 336 existing warnings.
  Architecture, expected class exports and ad-hoc signatures pass.

Commands for the focused CPU checks:

```sh
make test-nmplugin-render-surface-clear
make test-nmplugin-surface-commit-wait
make test-upstream34-plugin-prs
make test-nmplugin-surface-key
make test
```

The native compile uses pinned Vulkan-Headers
`6802bb4733b63ed5efd3adb308a6c885ef180ea1`, Apple clang
`21.0.0 (clang-2100.1.1.101)`, and the existing framework list from
`src/nmplugin/build.sh`. Baseline and candidate source snapshots differ in
exactly one plugin file. The release artifacts, dependencies and logs stay
private and ignored. The candidate was subsequently installed under a fresh
plugin-only hardware scope; the baseline artifact was not installed.

One initial candidate-fixture compilation failed because the extracted
branches no longer use their fake descriptor parameters under `-Werror`.
The fixture now permits unused parameters and reports compiler diagnostics.
An unprivileged existing wait test also could not replace its root-owned
output; running the unchanged test with the existing artifact permissions
resolved that environmental failure. Neither failure is counted as a
successful regression check.

## Installed plugin and bounded hardware observations

The owner-authorized installation on November 19, 2026 uses source commit
`9f838846f6a8eeab80890014eace3a5de1b16067` on the default branch and macOS
26.7.2 build 25G332. An atomic bundle exchange retained the exact previous
plugin. Full manifest comparison found only the executable changed; the signed
resource file did not need to change. The installed ad-hoc signature passed.

The installation readback verifies the current build34/VBL installation,
loaded AML treatment, complete selected-cache metadata (416 records,
including 29 codeless entries), all 415 unrelated images, EFI/recovery,
bounded startup receipts, PR28 daily setting and disabled resident monitors.
That validator submits no GPU work. An initial validator selected the original,
already documented failed GUI-permission receipt; the corrected fresh validator uses
the existing successful replacement observation and separately checks the
failed original receipt and job retirement. The failed attempt is retained.
No guard was relaxed to accept a failing runtime.

A fresh process verified the target PCI device and loaded candidate identity,
then completed three real GPU commands and checked 32 IOSurface pixels / 128
channels. This is a smoke test, not proof of the partial-clear preservation
case. An attempted partial-render-area probe still cleared the whole
attachment in this implementation and is not a valid baseline-versus-candidate
discriminator. Exclude its results from repair acceptance; the eight-case CPU
model remains the discriminating regression evidence.

WindowServer was restarted once in the same OS boot so that it could load the
candidate. A later independent one-second process sample identified the exact
candidate image UUID. That new WindowServer survived both finite desktop
checks and the final readback; no further logout or power action was scheduled.

- A roughly 40-second animation observation collected 357 window samples,
  273 on-screen samples, 30.545 seconds of visible span and 269 position
  changes. The synthetic VBL counter increased by 4,811 and successful display
  copies by 2,815. The window observer deliberately sampled every 100 ms;
  its intervals do not measure GUI stalls or FPS.
- A fresh Launch Services application performed 1,440 cursor-warp calls in
  12.000244 seconds, all successful, and observed 1,440 position changes. It
  restored the original cursor position successfully and exited. During the
  enclosing observation the synthetic VBL counter increased by 1,615 and
  successful display copies by 1,199. Request frequency is not display FPS.
- Display submission failures, skipped copies, surface GPU timeouts and
  hang-kill counters stayed zero across these observations. The finite test
  applications and observers exited. These counters cannot identify every
  wrong pixel. Existing `Invalid window`, brightness and application ping
  messages were not established as effects of the patch; do not describe all
  system logs as clean.

An earlier automatic screenshot failed. The fresh cursor application returned
false from `CGPreflightScreenCaptureAccess()` and did not request permission or
capture pixels. This establishes lack of capture access for that application,
not the cause of every earlier capture failure. A scanout utility was compiled
privately but not executed; raw VRAM was not used to bypass capture access.
The initial window observer also crashed because it decoded a bounds
dictionary with the wrong API; that observer defect was corrected before the
reported collection and is not a driver crash.

## Restart admission and remaining acceptance

A fresh, separate plugin admission scope was installed and independently read
back. Both existing startup entrypoints now use its owner wrapper. Its
derivation retains the frozen AML/VBL contracts and changes only the exact
plugin manifest/image identity, input hash and related protected entries.
The bounded startup, AML selection and no-postboot-monitor implementations
remain byte-identical. The startup deadlines remain 45 / 150 / 300 seconds;
PR28 daily waiting remains enabled with 250 ms budget and WindowServer
excluded. Resident monitoring remains disabled.

Twenty CPU tests passed, including the real contract derivation, rejected
unknown manifests/UUIDs/permissions/jobs/policies and temporary-directory
atomic rollback using `renamex_np`. The first preparation attempt rejected an
incorrect assumption that CodeResources must change and did not change live
jobs. It was retained; the successful installation used a fresh scope. An
installation-tool timeout did not terminate its child; completion was checked
from the final receipt, followed by independent live-plugin, exact-recovery,
startup-job and historical-contract readback. The installer was not replayed.
A final full readback after the cursor test again verified complete cache
metadata, loaded AML, EFI/recovery, current-boot receipts and exact plugin
identity, with no new matching reports or driver error counters. It submitted
no GPU work and scheduled no power action.

At initial installation, the new plugin startup scope had not been tested
across an OS restart. Only next-boot entrypoints were installed; they were not
bootstrapped and no power action was scheduled at that stage. Earlier
successful AML/startup receipts were not counted as evidence for the future
plugin boot.

The owner subsequently authorized the test restart on November 19. A fresh
full preflight passed, and a separate next-boot-only read-only observer was
staged without bootstrap. Its ten CPU checks cover new-boot admission,
complete receipts, deadlines, recovery/failure refusal, driver counters,
WindowServer continuity and exact own-job removal. After current-boot startup
receipts appear, it independently checks the mapped candidate plugin,
complete cache metadata, loaded AML, EFI/recovery and owner policy, records a
finite progress observation and removes its own job. It has a 360-second
receipt wait and a 420-second total limit, submits no GPU test, performs no
recovery/power action and does not retry. This preparation is not a successful
restart result. See the separate
[reboot preparation record](validation/build34-render-clear-reboot-preparation-20261119.json).

**The authorized plugin restart subsequently passed on November 19, 2026.** A
new OS boot on macOS 26.7.2 build 25G332 produced fresh plugin-scope startup,
desktop-admission and supervision-completion receipts. Both the one-shot
observer and a separate independent full readback verified the exact mapped
candidate in WindowServer, both plugin signatures and recovery copies, all
416 cache records / 29 codeless entries / 415 unrelated images, loaded AML,
EFI/recovery, historical contracts and startup entrypoints. Recovery was not
triggered. The observer exited and removed its own job; startup supervision
also ended, leaving resident monitoring disabled.

The same WindowServer survived the observer and independent readback. The
observer's finite enclosure recorded 908 synthetic VBL increments and 577
successful display copies; the independent enclosure recorded 559 and 5.
All four driver error counters stayed zero and no matching crash reports were
added. PR28 daily waiting remains enabled at 250 ms with WindowServer excluded.
No explicit GPU test was submitted during these readbacks; the earlier GPU
smoke and animation/cursor observations were not replayed. These results
accept this plugin's bounded accelerated restart, not visual repair, physical
FPS or long-term stability. See the
[restart validation record](validation/build34-render-clear-reboot-20261119.json).

The delayed shutdown command's capture timed out while its root-owned shutdown
descendant continued. A separate readback confirmed that process and retained
the request receipt. No duplicate power command was issued; the new boot and
fresh receipts above establish that the restart actually completed.

**Hardware repair of the reported artifacts remains unaccepted.** The GPU smoke
and finite desktop progress checks passed, but there is no valid hardware
partial-clear discriminator or visual acceptance of pointer trails and gray
squares. Obtain visual evidence or owner observation in normal use; any later
instrumented GPU/startup trial needs a fresh compatible scope. Never replay
consumed hardware, GUI or startup jobs. Synthetic VBL, cursor-warp frequency
and CPU fixtures are not physical frame-rate measurements.

Preserving CPU content can add an import on a full clear after a changed CPU
seed. Existing seed/pending-write checks still avoid unnecessary imports;
no FPS or long-term stability improvement is claimed. Restoring the skipped
import optimization would require proof of successful whole-root coverage.

## Subsequent Weather trails report, November 19

The owner subsequently reported trails after opening Weather. This is a
concrete application trigger, but the report does not yet distinguish stale
content inside Weather from a trail left on the desktop after moving or
closing its window. It does not establish that this symptom and opaque
Liquid Glass have the same cause. The existing clear-preservation backport
must not be described as having visually repaired these trails.

A fresh scope first passed complete runtime/cache/loaded-AML/EFI/recovery
readback. Weather's main process was absent at the initial check. It was
launched once through Launch Services without activation, observed for
18 seconds, and only that exact launched process was terminated afterward.
Three metadata observations found no on-screen main window at two seconds
and an on-screen window at eight and 16 seconds, with normal nice priority
and the application inactive. These are sparse metadata observations, not
launch-latency, visibility-through-other-windows or FPS measurements. In
particular, a window's alpha metadata does not establish material transparency.

One one-second process sample confirmed that Weather mapped the current
installed plugin image; its image UUID matched the installed executable.
The sample is not a simultaneous compositor/scanout capture and does not rule
out an intermittent wait. Screen-capture preflight was false; no capture was
attempted or requested, no raw VRAM was read, and no visual reproduction or
pixel correctness is claimed. The inactive test also does not reproduce
every aspect of the owner's active Weather use.

Both independent full readbacks passed with the same boot and WindowServer,
zero in all four checked driver error counters, no new matching reports,
preserved accepted runtime and recovery, and unchanged daily wait/monitoring
policy. The release log remained at 49 entries. Source review then identified
a specific diagnostic gap: the installed release filter drops PR28's
publication-deadline message. A narrow source-only correction and CPU
regression are documented in
[the PR28 timing investigation](BUILD34-PR28-WAIT-TIMING.md#2026-11-19-weather-investigation-release-timeout-logging).
It has not been installed and is not a demonstrated trail repair.

**Weather trails remain unresolved.** First distinguish an internal animation
or content trail from desktop damage surviving a window move/close. Do not
replay this consumed observation or infer success from clean counters/logs.
No installed driver binary, cache, EFI, startup or security setting was
changed, and no WindowServer restart or power action ran. All finite observers exited. The
[sanitized record](validation/build34-weather-trails-20261119.json) keeps the
owner's report, observation and logging regression separate.

## License and rollback

The changed production file keeps its
`SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0` notice. Its upstream
patch, `LICENSES/PolyForm-Noncommercial-1.0.0.txt` and
`THIRD_PARTY_NOTICES.md` were reviewed. No new external component or binary is
copied into the public tree; license and notice files remain unchanged. The
plugin binary publication block remains in force.

For source rollback, review later dependencies and `git revert` this isolated
backport; never reset or rewrite default history. Reverting source alone does
not revert the installed plugin. The installed private scope retains an exact
full previous bundle and the sibling atomic-exchange recovery copy. Its
recovery restores only that plugin and the preceding AML startup entrypoints;
it does not restore the older accelerator, change the active VBL, undo the
loaded AML treatment or alter kernel/cache/EFI/security settings. Final
independent readback verified both recovery copies and that recovery had not
been triggered. Keep the running candidate pending visual acceptance rather
than silently reverting a completed finite observation.

The sanitized machine-readable record is
[validation/build34-render-clear-20261119.json](validation/build34-render-clear-20261119.json).
