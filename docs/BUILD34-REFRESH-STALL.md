# Build34 page-switch refresh stall

On macOS 26.7.2 (25G332), the user reported that switching pages sometimes
left the previous image visible until moving the pointer refreshed a small
area. The running WindowServer's startup record identifies an older plugin
image than the later on-disk build. Its logs show that two descriptor pools
opened, that set allocations returned `VK_ERROR_OUT_OF_POOL_MEMORY`, and that
pool creation returned `VK_ERROR_OUT_OF_DEVICE_MEMORY`. One command buffer
reported 99 skipped draws or dispatches. The same log also records IOSurface
texture allocation and upload failures. These explain how compositor work can
be missed, but there is no timestamped reproduction tying these failures to
the reported page switch. A log throttle count is not an event count for a
specific call site.

The [source-only candidate](../tools/build34_refresh_descriptor.patch) is
separate from the production plugin and preserves the historical DCN source
pins. It changes only the normal stage descriptor snapshot allocator. It
tries a batch in existing pools, retries with a single set if
those pools are exhausted or fragmented, and only then tries opening one new
pool. Other allocation errors stop the attempt without requesting more pool
memory. If pool creation still fails, the draw remains skipped and the log
reports the actual creation error. Sets are already freed after command buffer
retirement; this change does not reclaim pools or increase a memory budget.

Run `make test-nmplugin-descriptor-mask` with Vulkan headers for the CPU
fault-injection checks. The runner checks the SHA-256 of the base source and
applies the patch in a temporary directory; it does not load the plugin or
execute on the GPU.

## Local installation, November 27, 2026

The owner requested installation and verification of this build34 plugin
candidate. It was rebuilt from `213dc68` to match the pre-installation disk
plugin, not from the newer VCN source. The control build matched the disk
image's text, string and constant sections and its import/export sets. The
candidate differed from that source only in `nvmtl_vk.c`. The descriptor CPU
test passed 324 cases in each of three configurations. The full `make test`
run stopped at the existing DCN source pin for `NVMTLDevice.m`; that check was
left unchanged.

Only the signed `NVMTLDriver` executable was atomically replaced. Independent
readback verified the installed hash, complete bundle signature, unchanged
bundle contents apart from the executable, and exact pre-installation backup.
The root-only, same-volume backup includes a separate rollback link. For manual
rollback, verify the installed candidate and exact backup hashes, atomically
replace only the executable using the rollback link, then recheck the original
hash and complete bundle signature. Already-mapped processes must be checked
separately after either disk change. No kernel, EFI, security setting or startup
policy was changed, and no logout or restart was requested.

The original disk plugin and staged candidate each passed a real Radeon 780M
IOSurface GPU readback and CPU-lock test in a separate process. A fresh process
then loaded the candidate directly from its installed path and again verified
557,056 pixels at ABI 1.12, build34. Four driver counters (zero-copy faults,
IOP failures, flips without VRAM and surface GPU timeouts) stayed at zero during
the installed test. The active mode remained 1280x800 logical, 2560x1600 backing,
120 Hz, native 2x. This finite test did not reproduce descriptor pool pressure.

The GPU's IORegistry property reports 4096 MiB, but the installed process's
RADV initialization reports 256 MiB of visible VRAM plus 1536 MiB of high VRAM
and a separate 512 MiB GTT cap. The 4096 MiB property is not the allocator's
available budget, and these heap sizes are not a measurement of free memory
at the stall. The patch does not change any heap size or budget.

## Desktop verification pending

At installation, WindowServer still mapped an older image. After the one
owner-requested reboot on November 27, 2026 at 18:12:57 local time (UTC+8),
WindowServer's mapped executable inode matched the exact signed installed
candidate. The original rollback backup remained intact. The native 2x mode
and zero-copy remained active, with present and zero-copy flip counts both
advancing during a 12-second observation of the same process. The four
checked error counters stayed at zero. A filtered boot-to-observation log
query contained plugin messages but found no matching failed descriptor
allocations, skipped submissions, pool ceiling, Vulkan out-of-memory or
IOSurface failure/timeout messages. There was no pending shutdown task.

This verifies desktop loading and brief present progress, not the reported
page-switch behavior. For the before/after comparison, use the same app and
native 2x mode, switch between visually distinct pages with the keyboard, and
hold the pointer still. Record
the elapsed time until the whole page refreshes, then whether pointer movement
only refreshes a small area. Compare the matching log intervals for allocation
errors, skipped draws and IOSurface publication or upload errors. If the
symptom persists without allocation errors, investigate IOSurface publication
separately: a host-backed texture currently does not advance the surface seed
in `nvmtlSurfaceOutDirtied:`. It is not yet known whether this affects compositor
invalidation in the failing case. This change neither tests nor modifies it.
