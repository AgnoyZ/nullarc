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
submit GPU work. Its CPU/filesystem tests cover the observed missing-marker
regression and refusal paths. A fresh activation packet is required to validate
the corrected controller; no successful continued installation is claimed here.
