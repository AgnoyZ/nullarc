# Original build 34 with geometry-corrected user tools

2026-11-15: the owner corrected the baseline after the prior deployment
loaded downstream build 39. The requested candidate is **original upstream
build 34**, with a narrow correction for this machine's physical backing and
VRAM extent. Merely relabeling downstream build 39 would not satisfy that
request. The prior packet and its failed initial smoke remain consumed;
its corrected private probe has not been run live.

## Baseline and scope

The source recipe pins upstream v0.4.0-alpha commit
`9dd76b604fca5e0125bd3caa5723df0f611ff27f`. The retained original PhxBringup
binary has SHA-256
`4a88035fd2ead990b8c44b638c9283d579b14d6ba4f0b48d78d6435a3a44a412`.
Its kernel source, build label, selectors and binary are not modified by this
correction. The installed original accelerator, plugin, runtime and firmware
remain the retained release versions. The observed OS is macOS
**26.7.2 / 25G332**, x86_64.

Only two original user tools and two original shell scripts are patched:

- `mesboot` reads the published MC base, physical backing, VRAM size and BAR
  aperture. The first 128 MiB's PTEs and page-table base use that physical
  backing. The system aperture uses the actual VRAM extent. Both default-page
  registers use a zeroed page immediately after the PTE table and before the
  original KIQ region, rather than reference-machine addresses.
- `phxctl` supplies the geometry-derived TOC and TMR words to the script and
  refuses stale raw TOC/TMR words. The original script's TMR offset/capacity
  remain 128/64 MiB; replacing it with the original managed `tmr` command would
  silently select a different 20-MiB/16-MiB region and is not this correction.
- `bringup5.sh` retains destroy/create, TOC staging/submission, TMR submission,
  all 17 firmware segments, RLC autoload and SMU `0x3`, `0x2`, `0x16(1)` in
  the original successful order. Geometry admission precedes the first write.
- `full.sh` retains the original power, doorbell/CP, GART, MES and requested
  queue-step order. Both scripts now stop on a failing command/pipeline.
  The helper wrappers also stop on transport/size, ABI or firmware-status
  errors, and firmware staging refuses a short file before payload submission.

The scripts retain their original watchdogs by default. A separate test runner
may supply `PHX34_WATCHDOG_ACK` only after its independent deadline has actually
acknowledged. In that mode the scripts require the acknowledgement file and
skip their own shutdown/killall calls, leaving recovery to the single bounded
runner. The GPU-command order is unchanged in either mode. The acknowledgement
file alone is not a general safety credential; the root runner must verify its
current-boot identity, ownership, pins and live deadline process before use.

Both helpers require original build 34 and ABI 1.12, positive typed geometry,
16-MiB-aligned bases/extent, checked 48-bit intervals, the original MC base and
256-MiB CPU aperture, and space for the original regions. They do not use
selectors 114/116 or import the downstream managed bootstrap. These constraints
cover this original startup path, not every experimental environment override
or an arbitrary GPU model. Operational execution must use the pinned clean
environment, image and files.

On this target the derived backing is `0x780000000`, extent 4 GiB, GART table
physical address `0x782400000`, default page `0x782440000`, TMR physical address
`0x788000000`, and system-aperture upper value `0x203fff`. No target physical
literal is a mapping fallback. The unchanged original raw TMR words also
encoded an incompatible physical address; changing only `mesboot`'s base
would not fix that separate use.

## Offline checks

The [isolated recipe](../tools/upstream34_layout/README.md) never installs,
opens a target GPU service or runs its built executables. It materializes
only six pinned user-space inputs and applicable notices. A native x86_64
build of both helpers is ad-hoc signed and strictly verified. The original
unused-variable warning is retained. An initial offline compile found a missing
CoreFoundation include and an overly old deployment target; these were corrected
before the successful build. The failed attempt is retained privately.

Twelve focused methods passed. The regression compiles the actual original and patched C entrypoints under
ASan/UBSan, substitutes every IOKit function and does not link IOKit. It
reproduces the original wrong mapping and checks every patched PTE, its first
and last entries, table base, both aperture/default registers and zero-page
writes. Bad/missing metadata, build 39, ABI errors, transport/size failures,
stale raw TMR words, short firmware and firmware/SMU status errors are refused.
Synthetic shell fixtures verify original successful ordering and terminal
failure without invoking sudo, shutdown, firmware, MMIO or real GPU calls.
The baseline `make test` also ran: six binaries passed (firmware-fixture cases
were skipped), but the unchanged `test_wait_seq` short-wait timing assertion
failed. The full base suite is not recorded as passing and its unrelated source
was not changed.

## Deployment and test boundaries

At the source checkpoint, build 39 remains loaded, GPU-off is present, the
original installed system stack still matches its retained package, and the
prior smoke job is removed. Fresh source checks do not mean build 34 has
already been restored or that acceleration works.

A new bounded deployment must verify a fresh complete EFI backup/manifest,
restore only the active PhxBringup bundle to the retained original build 34,
retain the displaced image for rollback, and install only the four reviewed
user-space files with independent readback. Preserve Windows/OpenCore,
licences, firmware/runtime/plugin/accelerator, OS security and unrelated NVRAM.
Keep GPU-off and all display-arming flags absent for the first test.

Any new headless execution requires the exact original image after a fresh
boot, matching files and geometry, a single-use intent and an independent
deadline acknowledged before initialization. A real unchanged Metal verifier
must complete and observe GPU-written output before claiming GPU execution.
No desktop flag or automatic desktop-reboot transition is part of the first
headless test. Preserve all failed receipts and stop rather than replaying a
consumed operation. A software deadline cannot guarantee recovery from a hard
hardware hang.

Validated addresses are not proof that all chosen offsets are free of console
or firmware allocations. This correction does not establish region ownership,
fix the prior CoreDisplay assertion, or prove an accelerated desktop. No public
binary upload is added. The root MIT/GPL-2.0 terms for these tools and existing
per-file AMD headers/notices are preserved; no source from another licensed
runtime component is copied. Full-stack publication restrictions remain.

## Installed original baseline; first test pending

The original build-34 bundle has now been restored to the existing active
OpenCore entry. A separate read-only mount verified the entire resulting EFI
manifest: **345 files before, 347 after**, with all **342 unrelated files**,
OpenCore configuration and Windows unchanged. A fresh complete private backup
and both displaced/retained bundle identities were verified. EFI is unmounted.
Only the four reviewed user-space files were replaced; all other GPU files,
original firmware/runtime/plugin/accelerator, original startup/plist and
allowlist still match their retained inputs. GPU-off remains present and
display-arming/pending flags remain absent. The running kernel is still build
39 at this checkpoint; restoring EFI bytes is not a fresh-boot load result.

Preflight first refused strict signing checks on the retained original kernel
and, separately, the unchanged old Metal verifier. Independent inspection
confirmed both are the expected unsigned x86_64 originals with their exact
retained hashes. The first refusal preceded root-packet/EFI changes; the second
left only an inactive incomplete private preparation packet, before EFI mount
or installation. Those failures remain retained. The original kernel/verifier
were not re-signed or altered. Their admission uses exact manifests/hashes and
the specifically expected unsigned result, never arbitrary signature errors.
The two newly compiled helpers remain ad-hoc signed and strictly verified.
No security setting was changed to make unsigned code load.

The fresh test packet verifies 371 new immutable inputs, the prior packet's
454 pins and the separately frozen interpreter. Seven actual bundle-swap
fixture cases and eight helper/admission methods passed. Twenty final observer
methods cover headless success and terminal errors, acknowledgement identity,
duplicate intent, delayed/missing desktop readiness, wrong image, publication
timeout and incorrect Metal output. An initial CPU fixture omitted its fake
`DEVNULL` constant; it was corrected before the passing run. These are synthetic
checks, not GPU results.

The root LaunchDaemon executed its preparation role through the delivered
interpreter with zero target calls. Before any reboot intent, its future
observer was revised to wait at most 90 seconds for registry/firmware-desktop
and one WindowServer process; wrong build 39 is an immediate refusal. The
original plan/source/job are preserved, and the revised actual launchd
preparation role also passed. No installation or consumed GPU/reboot trial was
replayed to make that readiness change.

This packet allows one ordinary reboot, one headless initialization and one
unchanged Metal probe, with at most one separate recovery reboot after GPU
initialization begins. Its independent 300-second deadline must acknowledge
before the first write; the scripts then omit their own reboot/killall calls.
GPU-off stays present, no native framebuffer or desktop flag is armed, and
there is no automatic desktop-reboot transition. At this documentation
checkpoint no reboot or GPU initialization has been dispatched. Read the
exclusive restart intent and actual postboot result/error before reporting a
load, GPU-execution or desktop success.

Rollback restores the verified displaced bundle and the four exact backed-up
user files after current-state checks. Keep GPU-off, preserve unrelated files
and all consumed intents, and verify any restored image in a later bounded
ordinary boot. No runtime/plugin/accelerator/security rollback is needed.

## Single normal restart dispatched

The restart caller returned zero, without timeout, at **17:47:50 +08:00 on
2026-11-15**. An independent process verified exactly one corresponding
root-owned scheduler, reparented to launchd, with the preparation boot and
build 39 still running. The job/pins, installed files, unmounted EFI, GPU-off
and absent display flags were reverified. No second restart was sent.

The expected restart time is approximately **17:50:50 +08:00**. This scheduler
observation is not evidence that original build 34 has loaded or that the new
headless/Metal test passed. Preserve the consumed restart intent and read the
actual next-boot result/error; do not schedule again after a lost connection.

## Fresh-boot result read back: GPU execution passed

The actual postboot receipts were read on 2026-11-15 after the owner requested
a new acceleration reboot test. The earlier ordinary restart did occur: the
current boot began at **17:51:16 +08:00**, and the bounded headless attempt
completed at approximately **17:53:03 +08:00**. The exact original build-34
image and corrected helper identities passed admission. Compute and graphics
queues returned their expected GPU-written values and both adoptions succeeded.
The unchanged Metal verifier found the AMD device, completed a command and
observed its expected GPU-written output. WindowServer stayed stable. There was
no error or recovery intent, and the consumed observer retired its own job.

Independent current-state reads still show build 34, the target geometry,
the exact four corrected user files, NMXAccel/IOAccelerator and original Metal
publication. PhxAMDFB is absent and the firmware framebuffer remains present:
this is actual GPU/Metal execution evidence, **not accelerated desktop proof**.
The old intent and completed test are preserved and will not be replayed.

The owner's new reboot-test request creates a separate, single native-desktop
attempt, described in [the desktop retest record](UPSTREAM34-DESKTOP-RETEST.md).
Its preparation does not install a driver, modify the original startup or
convert its pending result into success.

The subsequent actual desktop attempt has now been read back: original startup
reported that the accelerator did not start and explicitly requested fallback.
The 18:31:05 +08:00 boot uses the firmware desktop with GPU-off restored and
no accelerator present. The successful headless result above remains historical
evidence for that earlier boot, not the current desktop. See the retest record
for the consumed reboot receipts and the source-only diagnostic correction;
that correction is not installed and does not constitute another GPU test.

After a further owner continuation, a new diagnostic-only deployment replaced
the four user files and passed independent readback. Original kernel/runtime,
firmware, plugin and startup are unchanged. Its fresh observer preparation
passed with no GPU call, while GPU-off remains present and display arming is
absent. The new preparation/next-boot status is recorded separately in the
desktop retest record; the preceding failed and successful attempts remain
consumed historical evidence.

The diagnostic trial was also consumed and returned to the firmware desktop
at 19:42:55 +08:00 on 2026-11-15. It now retains an initializer status-1 failure
before queue setup. Offline fixtures reproduce a strict-shell no-process
watchdog-cancellation defect; they do not identify the exact untraced command
on that boot. Both shell sites are corrected with narrow no-match handling,
while genuine cancellation failures remain terminal. The default source branch
has been synchronized at `90bb06f6f9255cb5a16cc5eb87e78032566b2000` with the
same correction and diagnostics; upstream kernel/install/licence trees remain
unchanged. A fresh separately bounded packet installed only the two scripts
and passed its no-GPU launchd preparation role. The newest checkpoint and
rollback are in the desktop retest record; no new reboot/result is claimed
at that preparation checkpoint.
