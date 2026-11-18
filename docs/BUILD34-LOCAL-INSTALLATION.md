# Supervised local build34 installation

On 2026-11-18 the owner explicitly requested installation of the default branch,
hardware acceleration and desktop takeover on the local machine. The running OS
was read as macOS 26.7.2, build 25G332. This is an experimental owner opt-in;
long-term stability, background stutter, sleep/wake and physical scanout FPS are
not accepted by this request or by the bounded observations below. Build41 and
build42 remain withdrawn. PR28's default GPU-wait opt-in remains disabled.

The installation uses the already reviewed build34 ACQUIRE-prefix kernel and
the unchanged default-branch plugin, including A1/A2/corrected-A3. It retains
exact original kernel/plugin backups, a bounded first-boot guardian and separate
failure recovery. Raw manifests, startup logs and recovery packets remain local
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
