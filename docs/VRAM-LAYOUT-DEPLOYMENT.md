# Matched VRAM-layout deployment and load smoke

Status update, 2026-11-15: **downstream build 39 loaded after the restart, but
was the wrong baseline for the owner's requested original-build-34 correction**.
The automatic smoke failed at its initial snapshot check with no completed
cases; its job is retired and no corrected live probe was run. Continue with
the [original-build-34 correction](UPSTREAM34-LAYOUT-CORRECTION.md), not another
build-39 trial. The installation/restart checkpoints below are retained history.

The downstream PhxBringup was installed and independently read back. This follows the
owner's explicit deployment/test request after the [source correction](
VRAM-LAYOUT-SAFETY.md). It is a new, bounded operation. All earlier desktop,
original-only and selector trial packets remain closed.

## Installed candidate

The candidate comes from clean downstream commit
`6ed22ce2038946ac800e13cee47364ffcae74e45`. Its full PhxBringup bundle and
matching `mesboot` and `phxctl` were compiled and linked natively for x86_64,
ad-hoc signed and strictly verified. The kernel retains the build-39 label;
exact executable hashes and private image identity distinguish it from earlier
build-39 images. No additional compile-time ordering experiment is enabled.
All 1,232 MacKernelSDK files were independently compared after the build with
the retained pinned archive. The native build retained existing compiler
warnings and returned no build errors. The independent read-only smoke probe
also compiled with warnings treated as errors.

Fresh admission observed macOS **26.7.2 / 25G332**, the original build-34 image,
one firmware framebuffer and no native framebuffer or accelerator service.
GPU-off was present, display arming/pending markers were absent, and no competing
initializer or reboot process was found. The live metadata still reports
`0x780000000` physical backing and 4 GiB VRAM; it does not establish exclusive
ownership of any proposed initialization region.

A fresh complete private backup matched all **342** live EFI files before
installation. Only the existing enabled OpenCore PhxBringup bundle was replaced;
the original bundle is retained under a unique inactive rollback name. A separate
process remounted EFI read-only and verified the exact resulting **345-file**
manifest, candidate, retained original and complete backup. All **340 unrelated
EFI files**, OpenCore configuration and Windows boot files remain unchanged.
EFI was unmounted after each operation.

Matching tools are delivered in a separate root-owned private packet. The
original PhxAccel, Metal plugin, runtime, firmware, installed GPU scripts,
startup plist and allowlist remain unchanged and independently match their
retained inputs. The existing GPU-off marker remains empty. The unchanged
original `full.sh` is not used: it continues after initializer failure and is
not a checked runner for the new interface.

## One ordinary reboot and one smoke attempt

At this documentation checkpoint the running image is still original build 34.
Installing bytes does not establish that the new kernel has loaded. One normal
firmware-desktop restart is prepared separately; no reboot had yet been
dispatched at this checkpoint. The root-owned one-use postboot LaunchDaemon
has executed its preparation role through the actual delivered interpreter,
without opening a target GPU service or changing any activation flag.

The fresh-boot role first verifies the exact loaded image, OS, signatures,
454 pinned inputs, trusted interpreter and unchanged original system stack.
It permits these six narrowly scoped checks once:

1. ABI 1.12 handshake and an unconfigured selector-116 refusal.
2. Rejection of the legacy claim path on the non-reference geometry.
3. Rejection of the retired reference-address override.
4. Numeric PSP-layout configuration through selector 114 only.
5. Selector-116 readback of the exact target geometry and configured metadata,
   with no active ring, TMR or queues.
6. Rejection of GART before initialization because the required active PSP/TMR
   state is absent.

The numeric descriptor is test metadata, not an ownership grant. Selector 114
stores it without creating a ring, writing VRAM/MMIO or submitting firmware.
The probe itself only calls selectors 0 and 116. The GART refusal must occur
before register reads or memory writes. No power/firmware sequence, queue
initialization, GPU shader, display flag or desktop takeover is dispatched by
this first-stage packet. GPU-off remains present throughout; subsequent GPU
testing still requires actual region-ownership and initialization admission.

An exclusive reboot intent precedes the single normal shutdown dispatch.
An ambiguous dispatch, mismatched image or failed check is terminal; there is
no retry or automatic initialization escalation. The postboot job records its
result privately and retires only its own expected LaunchDaemon file. Actual
postboot receipts must be read before reporting a load or smoke pass. This
packet has no recovery-reboot loop and cannot guarantee recovery from an
unbootable kernel or hard hardware hang.

## Validation and rollback

Seven temporary-filesystem cases exercise the actual retained bundle-swap
function, including byte/signature refusals, activation-rename failure and
unrelated-file drift. Six CPU-only postboot-runner methods cover success,
preparation without target calls, consumed-scope refusal, wrong image,
unexpected legacy success and configuration failure. An initial fixture run
failed because a temporary path used the `/var` alias instead of its canonical
path; the fixture was corrected before all six methods passed. These are
synthetic file/process checks, not GPU execution evidence. The source layout
and wrapper regression files were also rerun. The full repository suite was
not rerun for this deployment record.

Rollback is confined to restoring the exact retained original PhxBringup bundle
after fresh partition/manifest checks, followed by an ordinary firmware-desktop
load verification. Preserve all unrelated EFI files and GPU-off. The independent
tool packet can remain inactive with its evidence; do not replay a consumed
postboot request. No runtime, plugin, accelerator, Auxiliary KC, security,
partitioning, BIOS or unrelated NVRAM rollback is needed for this installation.

The [sanitized record](validation/vram-layout-deployment-20261115.json) separates
build/installation/readback results from pending postboot observations. Raw
manifests, machine identities, firmware, binaries and logs remain private. No
new binary publication is authorized, and the existing licences and artifact
restrictions are unchanged. Neither hardware acceleration nor the prior
CoreDisplay failure is established as fixed by this deployment.

## Normal restart requested; fresh-boot result still pending

The single restart intent was consumed at **17:01:22 +08:00 on 2026-11-15**,
with a three-minute delay. The shutdown caller timed out after 15 seconds;
its return code is unobserved. An independent process at **17:02:31 +08:00**
verified exactly one matching root-owned shutdown scheduler, reparented to
launchd, with the preparation boot unchanged. It also reverified all pinned
inputs, the postboot job, GPU-off, absent display arming and unmounted EFI.
No second shutdown request was sent.

The expected restart time is approximately **17:04:22 +08:00**. A retained
scheduler is not proof that the restart occurred or that the candidate loaded.
Read the one-use postboot result/error and actual loaded image before claiming
any smoke pass or continuing to GPU initialization. Preserve the consumed
restart intent even if the connection disappears.

## Actual fresh-boot observation and baseline correction

Read-only postboot inspection verified a fresh boot, the exact deployed image,
build 39, the target 4-GiB geometry, GPU-off, one firmware framebuffer and no
native framebuffer/accelerator. All 454 pinned inputs and the retained
original system stack still matched. The one-use job removed its own plist.
Its error receipt records initial probe exit 75 and zero completed smoke cases.

The probe assumed selector 116 must start unconfigured. The driver may accept
the retained legacy-layout device property at startup without initializing the
GPU; that property and accepted metadata were observed. An offline corrected
probe passed 16 fake-IOKit cases, but its actual selector-116 result was not
obtained live. The initial exit cause therefore remains an expectation-mismatch
lead, not a demonstrated hardware result or a smoke pass.

The owner then identified the more fundamental baseline error: upstream is
build 34; the selected candidate was existing downstream build 39 with many
additional changes. Its further testing is suspended. The new correction
preserves the unchanged original build-34 kernel and adjusts its user-space
address consumers; no version-label substitution is used.
