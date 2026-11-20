# Owner-authorized build34 desktop re-enablement

On November 20, 2026 the owner explicitly requested enabling hardware
acceleration and desktop takeover and performing a restart test. This releases
the rollback hold only for this fresh test. It does not resume R1a, the Weather
plugin candidate, withdrawn build41/build42, or later optimization work.

## Observed starting state

The machine remained in the contained rollback boot on macOS 26.7.2, build
25G332. Both startup jobs were absent and unloaded. PhxBringup's loaded image
matched the pre-R1a control; PhxAccel was not listed loaded. The current EFI
configuration and NVRAM boot arguments contained three driver disable flags:
`-phxbringupoff -phxacceloff -phxfboff`. The boot log also recorded those flags.
The selected AuxKC nevertheless contained the accepted automatic-loading
metadata. Do not mistake this deliberately disabled boot for proof that the
accepted cache cannot load, or infer the earlier reboot-loop root cause.

The recovered kernel, accelerator, plugin and selected cache match the older
owner-accepted build34 runtime, source
`1d4968fbc2ce988c77bdd85b2ec36f435b57f496`. No new kernel, accelerator, plugin or
cache was built or installed. This preserves A1/A2/corrected-A3 and the accepted
ACQUIRE-prefix IB correction. It uses the recovered older owner baseline,
without reinstalling the later VBL/AML/render-clear/Weather experiments or R1a.

The first exact EFI comparison refused four pre-existing differences. Semantic
comparison established that `OC/config.plist` differs from the accepted original
only by the three disable flags. Three Microsoft boot-state files also differ
from the historical manifest. Their current exact hashes were captured in the
new contract; those files were not changed or restored. All other EFI files,
including the accepted driver and original recovery copy, matched. This is a
fresh exact snapshot of those three external files, not a wildcard exclusion
from subsequent complete-manifest checks. SIP and authenticated-root settings
match the accepted baseline; only the driver disable arguments account for the
boot-argument security-fingerprint difference.

## Fresh bounded startup scope

A new independent root-owned scope restores only the accepted OpenCore
configuration, removes exactly the three disable arguments from NVRAM, arms
the driver's existing `phxfb-boot` flag, and stages two startup jobs plus one
finite read-only next-boot observer. No startup job is bootstrapped in the
preparation boot. No NVRAM reset, partition operation, firmware-setting change,
OS security relaxation, Windows EFI write or binary upload is involved.

The original bounded startup implementation retains its 45-second guardian,
150-second desktop and 300-second completion limits, full serial file hashes,
loaded-image/geometry/framebuffer/hold conditions, protected initialization
shell, panel timing and compositor admission. Journals belong to the new scope
and boot. The original accepted installation records remain immutable. The
existing daily PR28 configuration remains enabled at 250 ms, with WindowServer
excluded. Continuous installation and hang monitors remain disabled.

Failure handling is independent of all six consumed recovery scopes. It
removes only this scope's exact jobs, restores the captured disabled OpenCore
configuration and the two driver-specific NVRAM settings, clears only an exact
empty pending marker, and releases the framebuffer hold. It makes **zero
automatic power requests** and never invokes an older scope's recovery. Unknown
files or processes are refused rather than overwritten or killed. Recovery
does not terminate its own process group. The unused continuous hang-watcher
function is omitted from the copied shell; both executable shell reboot paths
are redirected to this no-power failure handler. This prevents this controller
from cascading through the previous automatic recovery/restart chain; it does
not prove the driver or operating system cannot panic or restart independently.

Two inactive preparation attempts were retained. The first stopped at an
overbroad shell-text assertion before live changes; the second was superseded
after review corrected recovery's own-process-group handling. Neither had live
jobs, an activation intent, GPU execution or a power request. Only the third
fresh scope is staged. No consumed installer or observer was replayed.

## Verification and pending reboot

All 22 new receipt/progress/manifest/process-safety CPU methods, all 25 complete
cache-metadata regressions and `make test` pass. The shell/plist/source syntax
checks and actual root-owned contract checks pass. Actual complete cache
readback preserves all 416 records and 29 codeless records, with no changed
image or loading-policy allowance. Original loaded ACPI checks pass.

After activation, a separate process repeated the actual runtime construction,
complete cache, full 357-file EFI/recovery, signatures, security, flag, exact-job
hash/permission, one-shot policy and unloaded-service checks. It passed. The
older installation-restore service remains disabled. These are preparation and
installed-state results, **not accelerated-boot acceptance**. No current-boot
GPU initialization, takeover, WindowServer restart or benchmark was executed.

The owner has authorized one ordinary test restart; do not ask for the same
authorization again. Its dispatcher must persist a one-use intent and verify
actual state before sending the request. After uncertainty inspect that intent
and the real boot before considering another command. No automatic recovery
restart is authorized by this scope. After boot, require fresh successful
startup/desktop/supervision-ended receipts, exact loaded kernel/accelerator and
mapped plugin, complete cache/EFI/recovery/original ACPI, stable WindowServer,
zero checked errors and finite completion/framebuffer progress. The observer
has 360-second receipt and 420-second total limits and removes only its own job.
A separate independent readback remains necessary before declaring success.
Physical FPS, visual repair and long-term stability remain unaccepted.

See the [sanitized preparation record](validation/build34-reenable-preparation-20261120.json)
and the earlier [rollback record](validation/build34-weather-boot-rollback-20261120.json).

## Authorized restart and independent acceptance

The machine completed the authorized restart on November 20, 2026 at 12:05:04
Asia/Shanghai, on macOS 26.7.2 build 25G332. Only one restart request was sent.
The dispatcher's command wait timed out after 15 seconds; its persisted intent
was inspected instead of retrying. The later actual boot and fresh receipts
establish that the restart occurred despite that command-wait error. Retain
the timeout record; do not rewrite it as a successful command return or replay
the dispatcher.

The finite observer passed fresh bounded startup, desktop and supervision-ended
receipts, followed by a separate independent new-boot readback. Both verified
the exact accepted loaded PhxBringup and PhxAccel images and WindowServer's
mapped plugin, all 416 cache records/29 codeless records, full 357-file EFI,
original loaded ACPI, signatures and exact original recovery. The same
WindowServer survived each observation, GPU copy completions and framebuffer
VBL counts progressed, all four checked error counters remained zero and no
new matching diagnostic report appeared. No recovery was triggered.

A final separate status check confirmed acceleration/display controls all at
one, display hold at zero, all four error counters still zero, no active new
startup-controller process and no pending shutdown/reboot process. Both startup
workers had ended. The finite observer removed its own exact job and exited
with status zero. The two bounded startup job files remain configured for later
boots; no continuous installation or hang monitor was enabled.

**Hardware acceleration and desktop takeover are active and this bounded
restart test passed.** Keep the recovered owner-accepted build34 runtime active
under the new scope. Daily PR28 waiting remains enabled at 250 ms with
WindowServer excluded. This supersedes the preparation record's pending-boot
status; it does not install R1a, the Weather candidate or withdrawn builds.
The test used startup initialization and normal desktop progress observations;
it did not submit a dedicated GPU correctness/FPS benchmark. Weather trails,
Liquid Glass appearance, the earlier restart-loop root cause, physical FPS,
sleep/wake and long-term stability remain unaccepted. No additional restart or
later optimization is implied by this acceptance.

See the [sanitized new-boot acceptance record](validation/build34-reenable-boot-20261120.json).
