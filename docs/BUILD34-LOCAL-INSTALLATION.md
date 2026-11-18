# Supervised local build34 installation

The subsequent [unattended stutter investigation](BUILD34-VBL-SCHEDULING.md)
records correlated GUI/VBL pauses and a CPU/static-validated scheduling
candidate subsequently corrected to use public IOKit timers. Its native build
and complete offline AuxKC/readback checks passed; the initial private-KPI
attempts were rejected. It is not installed or loaded and has not demonstrated
a runtime repair. The owner's ordinary restart and original-ACPI baseline
readback are required before that separate treatment. The accepted
acceleration/desktop installation below remains active.

The subsequent [Apple-progress-bar latency investigation](BUILD34-BOOT-LATENCY.md)
records actual display-hold timing and an isolated CPU-validated hashing
candidate. It has not changed this installation or demonstrated faster boot;
the pending original-ACPI restart baseline comes before a separate treatment.

On 2026-11-18 the owner explicitly requested installation of the default branch,
hardware acceleration and desktop takeover on the local machine. The running OS
was read as macOS 26.7.2, build 25G332. This is an experimental owner opt-in;
long-term stability, background stutter, sleep/wake and physical scanout FPS are
not accepted by this request or by the bounded observations below. Build41 and
build42 remain withdrawn. The original activation kept the PR28 daily wait
off; the owner's later persistent daily setting is recorded below.

The installation uses the already reviewed build34 ACQUIRE-prefix kernel and
the unchanged default-branch plugin, including A1/A2/corrected-A3. Its activation
retained exact original kernel/plugin backups, a bounded first-boot guardian
and separate failure recovery. The owner's subsequent monitor shutdown is
recorded below. Raw manifests, startup logs and recovery packets remain local
and ignored. No Windows EFI files, partitions, firmware settings or OS security
configuration are changed.

## First activation: no GPU execution

The first installation packet booted the exact candidate kernel before its
desktop-arm record existed. No GPU initialization, native submission, Metal
probe or FPS application started. The independent guardian reached the original
105-second pre-release deadline and recovered. Independent readback verified
the original loaded kernel, all 347 baseline EFI files and 46 protected files,
the original plugin and alias mode, GPU-off/firmware framebuffer state and zero
new matching diagnostic reports. The packet was retired without replay.

## Second activation: GPU and desktop passed; monitor regression recovered

The second packet passed compute/graphics initialization and both queue
adoptions. Both native submissions verified the complete arena with no IB
mismatch. Three natural writer waits completed within the unchanged 250 ms
budget, with completed command state and no GPU error. The deliberate 1 ms
timeout case retained its pending result and subsequently verified real late
completion.

The ordinary GUI frame application exited successfully. Its strict parser
accepted 2,063 verified frames over approximately 20 seconds, or about 103.10
completed verified frames per second, with 132,032 sampled channels. This is a
bounded application result, not a game benchmark or a physical panel FPS claim.

A separate 160-by-80-point, nonactivating Cocoa panel requested redraws at 4 Hz
for at most 30 seconds. An independent window-list observation verified the
expected process/window was onscreen before and after each sample. Both desktop
tail samples passed the original progress, panel timing and diagnostic gates;
the second interval had 22 draw callbacks and 23 additional compositor presents.
The same WindowServer remained alive, with no copy failures or skipped copies.

After these checks and independent reparsing, installation handoff removed the
OFF marker as intended. The new installation monitor then incorrectly reused
the GPU-off protected-file check and tried to hash that absent marker. Its
`FileNotFoundError` triggered automatic recovery. **This rollback was caused by
the installation controller, not by a failed GPU or desktop test.** The original
failure and successful GPU evidence are retained; the packet is not replayed.

## Narrow controller correction

`tools/build34_install_state.py` checks the OFF marker against the explicit
installation state. Before acceptance and during recovery, the original marker
must exist with exact content and safe metadata. Only an owner-requested,
started and accepted installation expects it to be absent. A recreated kill
switch, a dangling symlink or inconsistent acceptance state is an error.

This helper changes no driver, ABI, wait budget, native/FPS acceptance gate or
recovery deadline. It does not perform installation, initialize a device or
submit GPU work. Its 19 CPU/filesystem tests cover the observed missing-marker
regression and refusal paths. Another 11 private integration tests exercise the
actual controller's protected-file loop, including an accepted installation
with the marker absent, restored markers during recovery, unauthorized
acceptance, and unrelated missing or changed protected files.

## Third activation: corrected handoff passed and acceleration remains enabled

A fresh packet pinned the pushed default-branch source checkpoint
`1d4968fbc2ce988c77bdd85b2ec36f435b57f496`. All 311 CPU controller/parser checks
passed, including the 30 new marker regression and integration checks. The
production driver and probe binaries were unchanged from the preceding packet.

The new boot passed initialization, both queue adoptions, both native full-arena
checks and the original Metal admission tests. All three natural writer waits
completed within the unchanged 250 ms budget; the longest was about 121.96 ms.
The intentional timeout retained its pending state and later completion proof.

The ordinary GUI application passed 2,146 verified frames and 137,344 sampled
channels, reporting about 107.30 completed verified FPS over its 20-second
measurement. Both active-demand tail intervals passed the original desktop
gates. Each contained 21 draw callbacks; the second interval had 29 additional
compositor presents. The panel timing remained 2560 by 1600 at the reported
120,000 mHz setting, without treating its synthetic VBL counter as measured FPS.

After independent reparsing, installation handoff completed. A separate live
readback verified the exact loaded build34 kernel, candidate plugin and readable
alias, WindowServer's plugin/RADV mappings, the same compositor process,
enabled desktop controls, zero copy failures/skips, no new matching diagnostic
reports, and a live installation guardian. The expected missing OFF marker no
longer triggered rollback. The EFI candidate and original recovery backup were
read back exactly, unrelated EFI files matched, and the volume was unmounted.
No test clients or pending reboot remained. OS security settings were unchanged.

At that readback, hardware acceleration and desktop takeover were **active**,
and supervised persistent startup was configured. A subsequent accelerated
restart has not been tested by this packet. Original kernel/plugin backups,
failure recovery, and the owner's kill switch remain available; this successful
local opt-in does not establish long-term stability, sleep/wake behavior,
background-stutter repair, universal workload compatibility or a general release
recommendation. PR28's default wait opt-in remains disabled.

The sanitized result is recorded in
[`validation/build34-local-installation-20261118.json`](validation/build34-local-installation-20261118.json).

## Owner-requested monitor shutdown and future baseline

After acceptance, on 2026-11-18 the owner requested closing monitoring and using
the current installation as the baseline for later optimization. The accepted
runtime source remains `1d4968fbc2ce988c77bdd85b2ec36f435b57f496`; the successful
GPU/desktop observations above are recorded by result commit
`d369e219f3986b82a9424cef315459a3c9e45a98`. Later documentation commits do not
change the running driver. All future optimizations must build on this accepted
default-build34 state, preserving A1/A2/corrected-A3 and the validated minimal
IB correction and plugin integrations. The older source checkpoints remain
provenance and comparison controls, not replacement candidates.

The exact live installation guardian was stopped and its old launch service
disabled and unloaded. Acceleration and desktop takeover remained enabled;
the same WindowServer stayed alive. No recovery was triggered. This disables
the added installation monitor, not macOS's own watchdog or security services.

A separate root-owned startup-only policy preserves the frozen installation
packet and the protected original startup script. It verifies the same runtime
identity, plugin, layout, original recovery backup and original admission
conditions. The existing 45-second guardian readiness and 150-second desktop
admission limits remain; incomplete overall startup is capped at 300 seconds.
Only after both the startup command and desktop admission succeed does the
startup supervisor exit. A private byte-checked copy of the original startup
script omits only its final invocation of the continuous hang watcher; its
pending-boot protection and initial 90-second desktop checks are retained.
There is no resident periodic installation/hang monitor or its post-startup
automatic rollback after successful startup. The new boot jobs were configured
without starting them in the current boot.

All 25 CPU tests of the actual generated policy passed, covering completion
ordering, refusal of stale/wrong completion records, startup failures, guardian
identity, retained deadlines and controls, and refusal to replay this boot.
The shell and launchd plist syntax checks and installed-policy readback passed.
An initial CPU fixture incorrectly reported a firmware framebuffer and was
corrected; the failed test output is retained privately. No GPU workload was
run for this monitoring change. Another accelerated boot with the new startup
policy has not yet been tested.

Original kernel/plugin backups and the prior startup-job bytes remain available
for an explicitly requested manual recovery. Reverting this policy requires
disabling its new startup-admission job and restoring the saved startup job
before re-enabling the appropriate supervised boot route; do not replay a
consumed trial or launch startup work in this already-admitted boot. Do not
silently re-enable resident monitoring during later optimization.

The independent baseline readback and owner policy are summarized in
[`validation/build34-owner-baseline-20261118.json`](validation/build34-owner-baseline-20261118.json).
The earlier supervised-installation JSON is retained as historical evidence;
its live-guardian observation describes that earlier readback. Long-term
stability, sleep/wake, background stutter and physical scanout FPS remain
unaccepted, and PR28's default wait opt-in remains disabled.

The later [local ACPI S5 candidate](BUILD34-ACPI-S5-CANDIDATE.md) addresses the
owner-reported shutdown/restart symptom through two exact OpenCore paths and
a matching startup-expectation extension. It preserves this accepted runtime,
recovery images and disabled resident monitoring. Its on-disk deployment,
76 CPU checks and full EFI readback do not accept a new accelerated boot or
successful physical shutdown; both were pending owner validation at deployment.
The subsequent [owner-initiated reboot readback](validation/build34-acpi-s5-reboot-20261118.json)
passed actual ACPI loading and bounded accelerated startup with the daily PR28
setting. Physical shutdown remains pending. The startup tasks completed as
one-shot jobs and no resident monitoring was re-enabled.

The subsequent owner shutdown trial failed. The local S5 ACPI candidate has
now been removed from disk by its exact rollback, with independent readback
of the original full EFI manifest, official configuration validation and
unchanged accepted kernel/plugin images. Acceleration, desktop takeover,
daily PR28 waiting and the disabled resident-monitor policy remain in place.
Loaded ACPI tables will change only after the owner's next restart; no power
action was executed. Shutdown success is still unaccepted. See the
[failure/rollback record](validation/build34-acpi-s5-failure-rollback-20261118.json).

## Subsequent owner-selected PR28 daily wait

Later on 2026-11-18 the owner requested PR28 waiting by default for daily
applications. The installed release plugin's supported persistent configuration
now supplies `NVMTL_SURFACE_COMMIT_WAIT=1` to newly started processes. The
compiled policy, accepted kernel and plugin binaries remain unchanged;
WindowServer is still excluded and the default budget is still 250 ms.
This supersedes the earlier local default-off setting in this installation
record and its historical JSON, not the original recorded observations.

Fresh administrator and ordinary desktop-user loader checks observed the
setting after release-constructor environment cleanup. All 18 file-access
checks and 46 CPU methods passed. The startup-integrity policy allows only
the exact authorized configuration change, retaining all other checks and
the owner's disabled resident-monitor policy. The same compositor and active
acceleration remained healthy. Existing applications were not restarted and
need reopening to adopt the setting. No new GPU workload or reboot was run;
next-boot and long-term behavior remain unaccepted. See
[the policy, validation and rollback record](BUILD34-PR28-WAIT-TIMING.md#2026-11-18-owner-selected-daily-configuration)
and [sanitized result](validation/build34-pr28-daily-config-20261118.json).
