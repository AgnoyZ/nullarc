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
The candidate has not been installed and the current display path is unchanged.

For a future authorized comparison, first reproduce by switching between two
visually distinct pages with the keyboard and leaving the pointer stationary.
Record the app and elapsed time until the whole page refreshes, then whether
moving the pointer updates only a small area. Compare before/after log intervals
for allocation errors, skipped draws and IOSurface publication or upload
errors. Verify the exact plugin mapped by each WindowServer process, hold the
native 2x mode and the rest of the build34 stack fixed, and retain an exact
copy of the previous plugin for manual rollback. If the symptom persists
without allocation errors, investigate IOSurface publication separately: a
host-backed texture currently does not advance the surface seed in
`nvmtlSurfaceOutDirtied:`. It is not yet known whether this affects compositor
invalidation in the failing case. This change neither tests nor modifies it.
