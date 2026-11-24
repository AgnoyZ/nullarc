# Build34 R2 display wait and CPU scanout copy

Current checkpoint: the packed-copy accelerator is loaded and its bounded
startup/display correctness trial and independent readback passed. The
comparison does **not** establish a performance improvement. The installation
remains active with R1b/VBL/optimized AML/accepted plugin. The earlier
offline/preparation statuses below describe their original checkpoints; the
latest new-boot result is recorded at the end of this document.

## Offline DCN zero-copy prerequisite, November 24

The [DMA page layout](../tools/build34_dcn_page_layout.h) stages one step
toward DCN scanout from the same pages that back a rendered IOSurface. The
boundaries follow the reviewed Linux v6.12
[`dcn20_vmid_setup`](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/display/dc/dcn20/dcn20_vmid.c)
and [DCN 3.1.4 field definitions](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/include/asic_reg/dcn/dcn_3_1_4_sh_mask.h):
4 KiB pages, 36-bit logical page numbers and an inclusive last page. The
planner uses a conservative 48-bit DMA address limit and a 64 MiB work cap.
This is new offline code, not a port of the Linux implementation.

Pass immutable device DMA segments for the exact, page-rounded backing slice
in logical offset order, with CPU-owned output storage disjoint from the
input. The planner refuses short, excess, overlapping or gapped logical
ranges, zero or misaligned DMA bases, and arithmetic or output-capacity
overruns before writing any page address. It emits the ordered DMA page
bases and the size of a flat table with 64-bit entries, **not** live PTEs:
the caller must still establish mapping identity, permissions and validity.
CPU physical addresses and the family VRAM pool are not substitutes for DMA
segments of the exact rendered IOSurface. The tests include a synthetic
2560x1600 frame with all 4,000 pages fragmented, the 48-bit boundary and
malformed inputs that must leave output untouched.

The same helper now has a separate surface-qualification gate. It accepts
only a retained, linear, directly host-imported `BGRA` IOSurface at byte
offset zero (a nonplanar surface or a single explicit plane)
whose dimensions exactly match the panel and whose byte pitch fits the full
image in its allocation. It emits the DCN pitch in pixels minus one and the
native `ARGB8888` surface-format value, matching the 8-bit framebuffer
layout and the pinned Linux [HUBP programming reference](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/display/dc/hubp/dcn20/dcn20_hubp.c);
10-bit `l10r`, private Vulkan images, family VRAM backing, multi-plane images,
unretained surfaces and unknown layouts are rejected for copy fallback.
Padded byte rows are allowed only when word-aligned and within the DCN
14-bit pitch field. The intended DMA slice is the page-rounded footprint
of the full pitched rows, not the entire IOSurface allocation. The caller
must separately prove the last rounded page belongs to the descriptor and
that this slice covers the actual HUBP fetch range.

The [bounded segment collector](../tools/build34_dcn_page_layout.h) models
the prepared-offset and returned-count semantics of the pinned XNU
[`genIOVMSegments`](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/iokit/Kernel/IODMACommand.cpp#L1272-L1314)
interface. The callback must represent a leased mapping prepared for exactly
that slice and return success only for a successful segment walk. The
collector checks every reported length and device address and requires the
next cursor to equal the accumulated length. It refuses errors, empty or
oversized batches, premature exhaustion and mismatched extents without
publishing any page addresses. The caller owns disposable run scratch and
disjoint page output. CPU fixtures exercise 4,000 fragmented pages, a short
last batch and errors injected after successful reads.

Before publishing the page list, the collector requires three physical-page
lookups to agree at every logical offset. The render lookup reads the backing
of the successful, active linear-image import. The present lookup reads the
original backing of the retained IOSurface descriptor. The DMA reverse
lookup uses the prepared mapping and a non-null mapper independently
attributed to the device. The caller must hold stable leases on both page
sources and the exact mapping. Both backing reads must be independent of
DMA preparation. Each callback must establish a whole, contiguous 4 KiB
physical page in the same address domain. Failed lookups, zero or unaligned
pages, and mismatches leave the page list untouched, even on the last page.
Scratch can change. The page list contains the original DMA addresses.

CPU fixtures cover non-identity DMA, one substituted page with an unchanged
mapping context and extent, reordered and repeated targets, missing/wrong
mapper identity, lookup failure, and coalesced DMA backed by noncontiguous
physical pages. A last-page render mismatch also refuses publication when
the present descriptor and DMA mapping agree with each other. The 4,000-page
test checks all three lookups and every emitted address.

The [descriptor adapter](../tools/build34_dcn_descriptor_backing.h) supplies
either original-backing callback for an already pinned descriptor slice.
It checks that the whole page-rounded slice fits the descriptor's length
and reads each requested page with `getPhysicalSegment` and
`kIOMemoryMapperNone`, following the pinned XNU
[descriptor implementation](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/iokit/Kernel/IOMemoryDescriptor.cpp#L3187-L3284).
A nonzero, page-aligned address is accepted only when
the returned contiguous length covers a full 4 KiB. The adapter neither
prepares the descriptor nor takes ownership of its wire or reference;
those must survive the lookup and any later use by the scanout transaction.
The option is not proof of a descriptor's provenance or address domain:
the cited XNU implementation may reverse-map physical descriptors through
the system mapper. Admit only concrete descriptors known to return the
original pages in the comparison's physical address domain. The adapter
does not derive DMA addresses. The page cap limits callback count, not the
runtime cost of a descriptor walk; a per-frame call needs a separate latency
and reuse bound. Fixtures cover nonzero slice offsets, a descriptor shorter
than the rounded extent, and a short physical segment despite sufficient
descriptor length.

The [render descriptor lease](../tools/build34_dcn_render_lease.h) stages an
independent retain and nested prepare for the task-backed host import. The
pinned XNU implementation [counts nested preparations](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/iokit/Kernel/IOMemoryDescriptor.cpp#L4439-L4475)
and [unwires on final completion](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/iokit/Kernel/IOMemoryDescriptor.cpp#L4494-L4577).
The lease checks the expected [preparation ID](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/iokit/Kernel/IOMemoryDescriptor.cpp#L2575-L2600)
before and after prepare. It exposes the render page reader only after
success. It applies the 64 MiB cap to the whole descriptor because a nested
prepare keeps the whole BO wired. A descriptor reference alone would not
keep its pages wired past BO cleanup. A preparation ID alone does not
establish render BO or surface identity and is never accepted from userspace
as such evidence.

Callers must resolve the actual bound host BO and acquire under the lock
that protects its original prepare against BO free and client close. The
concrete descriptor must be known to support nesting with the original
direction. Serialize all lease operations and descriptor prepare/complete
calls, including BO teardown, and keep the lease storage alive through its
last callback. The lease helper has no internal lock or implicit destructor
cleanup. Release only after the transaction never used the pages or has
proved old display/mapping use retired. Readers are withdrawn before complete;
a failing complete retains the descriptor reference and permanently refuses
reuse without claiming that the wire survived. Rollback after a changed
preparation ID follows the same rule. CPU fixtures exercise both ownership
release orders, stale IDs and callbacks, prepare failure, cleanup reentry and
unrecoverable complete failure. The three-way page fixture walks the render
lease after dropping the original BO's reference and preparation. Native
integration needs a bounded number of leases and a retirement owner that
survives the render client's close.

The [render binding gate](../tools/build34_dcn_render_binding.h) checks a
bound-image record against a live host-BO mapping snapshot before taking
that lease. It requires the retained IOSurface object from the current
presentation, the same client and non-reused mapping generation, and the
qualified BGRA geometry and pitch. The full page-rounded image must be
within one live GPU VA mapping, and its claimed BO offset must equal the
mapping's BO offset plus the image's displacement within that mapping.
The kernel's BO size must match the descriptor extent. The accepted slice
then passes the existing preparation-ID check. The fixtures include offsets
within both the BO and mapping, stale generations at the same VA, a different
surface or client, and a mapping that omits the rounded tail.

Both binding inputs are kernel-side contracts, not a wire format. A native
producer must associate the actual successful linear render binding with
the retained surface and hold the lifetime protection needed to validate
the snapshot through lease acquisition. Retain the client identity across
the comparison so a recycled client address cannot match a stale record.

The [isolated source stage](../tools/build34_dcn_render_map_stage.py) starts
from the pinned build34 driver and ABI without modifying either.
`doBoImportHost` records the original preparation ID after successful
prepare of a task-backed descriptor within the lease's wiring cap. `doGemVa`
assigns a fresh, per-client software generation only after `vmMap` succeeds
and every physical segment used for the PTEs covers a full 4 KiB page with
an address that survives the PTE mask unchanged. GPU-not-ready bookkeeping
maps, local BOs, inexact segments and failed GPUVM calls do not acquire a
generation. A short segment or truncated address changes only zero-copy
eligibility, not the legacy PTE or return value. VA and BO bounds use
subtraction before the call. A lock-held lookup requires the entire
page-aligned slice to fit one entry. Unmap, BO free and client close
withdraw the generations before forwarding to the existing cleanup; close
permanently disables new generations. Saturation disables new generations
without changing legacy map results. Tests extract the actual staged
methods and use CPU doubles. No selector, exported ABI, map call sequence,
or page-table programming sequence is added or replaced.

The staged client resolves the descriptor, preparation ID, BO size and
mapping offsets directly from the current BO table while protecting the
client and GPUVM state. It compares that snapshot to the bound image and
its ACK receipt before acquiring a lease. Nested `prepare` runs under the
client lock, without the GPUVM lock. The client rechecks the translation
after `prepare`; if it changed, the unused lease is released or retained
as uncertain if cleanup fails. The caller still must keep the client and
provider alive and serialize final lease release with BO teardown. A
successful lease pins backing pages, not the render VMID or future writes.
CPU tests exercise stale preparation/length, a table change during prepare,
BO handle reuse, and reading the original offset pages after BO free.

The software map generation identifies a completed software page-table
update. The legacy `vmMap` can return before the context has a hardware
VMID, and its TLB invalidation helper does not propagate timeout.

The isolated source stage also assigns GPUVM context, binding and table
generations at the original driver call sites under `gpuLock`. A snapshot
requires a live host-map slice under the client lock, the owning client
and reciprocal context-to-VMID ownership under `gpuLock`. Freeing the
context, evicting its VMID or changing its tables invalidates old identities.
A partial map failure disables snapshots for that allocation. Stop and the
first sleep close identity admission for the provider instance. The
generator's counter can saturate without changing the legacy return values.
A snapshot without a confirmed request carries an invalidation generation
of zero, so the legacy flush cannot satisfy the lease gate. Tests extract
the build34 allocation, bind, free, map, unmap, flush and power callback
for CPU-only execution.
They cover reused context slots and VMIDs, partial page-table writes and
counter saturation. A future caller must hold the provider lifetime through
the lock acquisition and snapshot use. The admission bit alone cannot
serialize teardown with a live consumer.

The offline render lease gate now requires a
[TLB observation](../tools/build34_dcn_render_tlb.h) for the exact client map,
provider, context allocation, VMID binding, page-table generation and
invalidation request. For a serialized GFXHUB invalidation, the sampler
starts after the request write and must observe the target VMID's ACK bit
clear and then set within 1 ms and 1,000 reads. A stale level, a different
VMID's bit, an all-ones read, a timeout or a changed identity fails closed.
The binding gate compares the observation with both the render binding and
the current mapping before retaining any pages. CPU fixtures verify stale
and late ACKs, request replacement, context and VMID reuse, a stopped clock,
and rejection at the lease boundary.

The isolated driver stage connects the sampler to the existing GFXHUB
register accessors and monotonic clock. With the client and GPUVM locks held,
it checks the live map and requires a one-way engine-17 handoff **before**
reading or writing ACK/request MMIO. With both existing queues adopted and
a proof provider installed, it closes all eleven raw debug writer paths
using the existing callback gate. An admitted writer may finish, but the
handoff refuses while it is active and does not wait under `gpuLock`.
Draining CPU callbacks does not drain MMIO already posted or queue and
firmware work already submitted. The handoff also needs a separate proof
that prior invalidations have drained and that other paths cannot write
engine 17, change its context programming or disturb ACK state while owned.
The proof hook is null in the staged driver, so ordinary queue adoption
does not close raw debug paths or enable any new writes. There is no
runtime caller. The caller must separately protect provider, power, and
MMIO lifetimes through sampling and lease acquisition.

The sampler preserves the original request word, which selects the render
VMID **and VMID 0**. Both ACK bits must be set in the pre-write sample.
After the write each selected bit must be observed clear, then both must
be set in the same sample within 1 ms and 1,000 post-write reads. It
rechecks the request identity before and after ACK reads. A failed issued
request disables further checked requests for that provider; a timeout or
a missed clear is not a drain proof and is never retried. A newer request
or any legacy flush withdraws the previous request identity. Once engine 17
is owned, every legacy flush is observed within its existing polling loop
for fresh transitions of both bits. It keeps the existing request word,
read/delay schedule and caller-visible behavior. If it exits without fresh
completion, the checked path stays disabled; a later high ACK cannot restore
it. Re-adoption and watchdog recovery also revoke the checked path. The
receipt must still match a freshly resolved live map at lease acquisition.

CPU fixtures exercise the actual staged methods with scripted MMIO and
clock reads, including an active raw writer during handoff, post-close raw
refusal, re-adoption, legacy ACK uncertainty, denied proof, a short register
aperture, incomplete pre-write ACKs, separate bit transitions, a stale VMID 0
ACK, power/table changes and late or invalid reads. Linux v6.12 documents the
[engine-17 request and ACK path](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/gmc_v11_0.c#L194-L277),
including the KIQ/MES path and power-gating considerations; no implementation
was imported. Neither adopted queue metadata nor the new CPU ownership bit
proves this platform's firmware/scheduler state. Native engine handoff,
ACK freshness, the actual render binding and frame
completion still require device-path evidence.

This XNU reference is APSL 2.0 and no code was imported. A segment walk or
matching descriptor cannot rule out per-page bounce buffering. A null mapper
does not establish identity, and the presence of `mapToPhysicalAddress()`
does not prove that the concrete implementation can resolve this live lease
without a fallback. The equality check is conditional on trusted callbacks;
it cannot independently attest a mapper or a DCN route. See
[device DMA backing](BUILD34-SYSTEM-WRITEBACK.md#device-dma-backing).
This stage does not encode PTE flags: the generic AMDGPU definitions alone
do not establish which permissions and cache attributes work on the live
DCN path.

There is no live binding caller, production MMIO or active page-table change. Keep
the AMD flip guard and the accepted R2a copy fallback unchanged. The
[plugin's linear alias](../src/nmplugin/NVMTLDevice.m#L915) uses a
[task-backed wired descriptor](../src/phxbringup/PhxBringup.cpp#L1674)
through the native host import. The
[alias builder](../src/nmplugin/nvmtl_vk.c#L7545) can drop color-attachment
usage when the linear format features do not support it and still create a
sampleable alias. Neither `_hostOn` nor a successful bind proves that the
frame was rendered into that alias. The
[present path](../src/phxaccel/accel/nvrm-accel.cpp#L1150) retrieves its
descriptor from the IOSurface. PhxAccel still lacks a native producer and
consumer for the binding record. An IOSurface ID or user property may locate
a candidate, but cannot substitute for the retained object and the live
mapping snapshot. Page comparison still requires live backing on both sides.

The [isolated plugin attachment observation](../tools/build34_dcn_render_write_stage.py)
derives from five pinned build34 plugin files without changing `src/`. It
records the actual `VkImage`, view, imported `VkDeviceMemory`, buffer, and
binding extent after successful bind and view creation. It checks reported
linear pitch, zero offset, and extent using the color aspect for linear
tiling or memory plane 0 for the explicit linear DRM modifier. Only a
nonplanar `BGRA` IOSurface with matching dimensions and pitch and enough
space for the page-rounded footprint can be associated with that record.
Sampleable-only aliases, private images, family VRAM, `l10r`, and sRGB views
do not qualify. None of these process-local handles identifies a kernel BO.

The staged recorder only records an attachment selected by the successful
Vulkan render-pass begin, with its exact view and memory, full-image area,
single sample, and mip and layer zero. Metal must have requested Clear and
Store, and the actual render pass must still clear rather than load. This
demonstrates a written color attachment in the recording, not draw coverage
or compositor frame intent. Open passes and conflicting candidates are
refused. Under the queue submit lock, only a successful submission receives
a serial and a copy of the recorded identity in its own in-flight object.
Successful fence completion and the existing completion-witness check, if
applicable, move that copy to the exact submission part. After successful
legacy publication the part checks its retained surface and unchanged
backing. Nothing publishes the observation beyond that part or modifies the
existing pending/ready mark, wait, or R2a copy behavior.

This is a historical write observation, not a latest-frame receipt. Split
parts keep separate identities; an out-of-order completion cannot use a
different part's attachment but can still describe an older write to those
pages. Before producing a frame receipt, account for all writers, including
ineligible/alternate backing, later split parts, overlapping command buffers,
GPU copy/compute operations, and external/CPU writes. Do not infer that
ordering from an IOSurface seed, ready mark, or observation serial. The
legacy imported-image alias lacks `VkExternalMemoryImageCreateInfo` and uses
`PREINITIALIZED`. It is not a valid template for a native render-only alias.
See the Vulkan valid-usage entries
[`vkBindImageMemory-memory-02989`](https://docs.vulkan.org/refpages/latest/refpages/source/vkBindImageMemory.html)
and [`VkImageCreateInfo-pNext-01443`](https://docs.vulkan.org/refpages/latest/refpages/source/VkImageCreateInfo.html).

The same isolated stage now includes a separate
[external render alias constructor](../tools/build34_dcn_external_alias.h).
It uses only memory from the successful host-allocation import, not the
generic `imported` flag shared by the family VRAM path. It queries the exact
BGRA attachment usage, tiling, and external handle type before creation.
Explicit linear DRM layout requires a reported single memory plane. The
constructor declares the host handle and starts in `UNDEFINED`, then checks
dedicated-allocation requirements, the actual memory type and extent, and
the reported zero-offset layout before binding the existing memory. Failure
leaves no alias and does not free the buffer's memory. Neither the staged
plugin nor production calls the new constructor. In particular, it must not
replace the legacy IOSurface image when the first consumer samples or loads
existing pixels. A future render caller must establish full Clear/Store on
first use, the required layout transitions, exclusive access, and a retained
IOSurface and import range through completion. The Vulkan declaration also
does not establish that the IOSurface's host pointer has the required native
allocation provenance or that other mappings can safely read the payload.
The ordinary render pass ends in `TRANSFER_SRC_OPTIMAL`, which does not
establish host-accessible alias contents. A later handoff must establish the
required layout, memory dependency, and native display visibility; see
[Vulkan memory aliasing](https://docs.vulkan.org/spec/latest/chapters/resources.html#resources-memory-aliasing)
and [host-pointer import](https://docs.vulkan.org/refpages/latest/refpages/source/VkImportMemoryHostPointerInfoEXT.html).

CPU tests compile the actual staged alias, render begin/end, submit and
completion blocks with doubles. They cover wrong backing/layout, unsupported
attachments, conflicting passes, rejected submissions, serial saturation and
out-of-order completion. Set `VULKAN_HEADERS` to the pinned checkout's
`include` directory to also compile the external-alias cases. These exercise
both tiling paths, exact query and create chains, refusals before binding, and
cleanup following bind or view failure. The complete staged plugin passes
x86_64 SDK syntax checking with the pinned Vulkan headers; no bundle was
built, loaded or run.
Rollback is to discard the temporary source stage. The accepted source and
installed images are unchanged.

The separate [RADV binding stage](../tools/build34_dcn_radv_binding_stage.py)
derives four pinned MIT Mesa inputs from the reviewed build34 RADV source.
After the actual host-import `GEM_VA` map succeeds, it compares the allocation
size recorded from Darwin's import result with the mapped extent and assigns
a process-local, non-reused generation. No generation is issued for local or
fd-backed BO creation. The image bind reads back the actual BO pointer,
memory address and range that RADV installed, not a plugin-supplied address.
It requires the same winsys, host pointer, handle, VA and range, a declared
host-allocation import, and an uncompressed single-plane linear BGRA color
attachment with a zero-offset slice covering the whole page-rounded frame.
The record preserves the original RADV VA for binding comparisons and keeps
the normalized 48-bit PhxBringup VA separately, including sign-extended
high addresses from RADV's VA allocator. A mismatched extent, layout or VA
leaves the record empty without changing the Vulkan bind result.

The RADV record is not exported or accepted by PhxBringup. Its generation
does not replace the kernel map/table generations, and a successful map
return does not prove native TLB completion. Retain the image, memory and
winsys during any future use and revalidate the matching live kernel map.

The separate [RADV load-clear stage](../tools/build34_dcn_radv_clear_stage.py)
extends that binding overlay with three pinned MIT Mesa inputs. It records
only the load clear that took the ordinary graphics draw path, after the
draw has been recorded without a command-buffer error. Fast clear,
explicit `vkCmdClearAttachments`, and render entry alone do not qualify.
It checks the actual view after RADV's substitutions and re-reads the BO
map generation from the installed binding. It requires a full-image
single-sample linear BGRA color attachment at mip and layer zero, with
Clear and Store, on a primary GFX stream. It does not qualify another view
used for a resolve or a render-to-single-sampled transient. It conservatively
rejects secondary execution, suspended/resumed rendering, multi-subpass
render passes, resolves, gang streams, and conflicting eligible clears.

The observation closes only at the corresponding rendering end with the
same stream, view, BO and map generation. Only successful command-stream
finalization and command-buffer end stamp a process-local recording serial;
reset or re-recording erases the observation. The serial identifies one
recording. The observation holds borrowed identities under normal Vulkan
object lifetimes.

The exact submission stage adds ten pinned MIT Mesa inputs. It observes a
single unprotected graphics command buffer and checks the actual winsys
request for its direct IB. The request may contain graphics preambles and
postambles. The record preserves the writer IB's ordinal, address and byte
length. The Darwin transport checks those fields again in the marshalled
native plan and requires a unique matching IB on GFX instance 0, ring 0.
Split requests, chained command streams, mixed engines and legacy
submission leave the observation empty.
[Exact submission stage](../tools/build34_dcn_radv_submit_stage.py)

The exact marshaller copies the complete native receipt at acceptance
while it holds the transport lock. The Darwin transport returns the
receipt only after all output syncobj attachments succeed. Its existing
handling of an allocation failure after dispatch prevents the RADV retry
from repeating that exact submit. The queue clears its previous
observation on entry and installs the new one only if the submission
succeeds. A missing observation can accompany a native dispatch after an
attachment failure. The queue snapshot holds historical write identity.

The [exact completion stage](../tools/build34_dcn_radv_complete_stage.py)
adds a private poll for one accepted writer in the active Darwin transport.
It requires a match on the full native receipt and submitted context;
the raw WaitCS rule that accepts anonymous sequence holes below the global
prefix is not used. An authenticated receipt can complete either through a
matching native WaitReceipt reply or a genuine global prefix covering its
sequence. Retaining that one local record does not block native ACK, and
does not retain the image or its pages. Starting another exact admission
on the same connection, including compute work or an ultimately refused
submission, invalidates the earlier observation. Failed syncobj attachment
discards only the matching record and leaves any newer one untouched.

The poll does not wait for the submit lock. It refuses lock contention,
stale identity and poisoned sessions; a pending record uses a zero-time
native query and the poll itself does not flush ACKs. Its result remains
historical after the lock is released. It does not exclude earlier
overlapping writes, another connection, CPU writes or a later remap, nor
does it grant ownership to scanout. A caller still needs live object
lifetimes, exclusion of other writers and a retained display lease, along
with visibility in the HUBP fetch domain.

The paired [plugin part](../tools/build34_dcn_plugin_part_stage.py) and
[RADV part](../tools/build34_dcn_radv_part_stage.py) overlays carry the exact
writer through one retained plugin submission part. The plugin prepares
both normal and ahead submissions only for a unique retained IOSurface
texture with an external host render alias. It uses the paired private
entrypoints only from a directly loaded AMD ICD, under the existing plugin
submit lock. A counter reset or upload prologue that adds a command buffer
leaves observation off; the original Vulkan submit is still made once.

RADV associates the writer inside the same synchronous submit call. It
requires one actual driver submit on the same queue and command buffer,
then checks the recorded view, image, imported memory, BO and live map
generation, address and extent. Deferred or threaded submissions do not
get an association. The paired stage removes the shared RADV queue
snapshot and copies only the matched receipt and numeric map identity to
that part's in-flight object. After successful Vulkan fence and existing
witness checks, it revalidates the live binding and polls the exact native
receipt before retiring the command. The part retains the result only
after successful legacy publication and a second retained-texture match.
Busy, stale or unobserved submits do not produce a completed writer record.

This stage does not activate the render-only alias constructor, export the
part record to PhxAccel, or treat a userspace address as page identity. It
does not change ready marks, fence behavior, or the R2a copy.

The isolated [present backing stage](../tools/build34_dcn_present_backing_stage.py)
observes the descriptor used by `performTransaction` after the existing
copy path has prepared it and matched the source to panel geometry. It
rechecks the transaction's plane-zero object, descriptor and geometry. It
uses the copy's zero-offset BGRA range, including the last rounded page,
not the IOSurface ID or allocation size. Resource-only and `l10r` paths are
excluded. An unsupported, unprepared or changed preparation ID does not
qualify. The descriptor and transaction are borrowed for one synchronous
call under the existing copy serialization; no new present pin or callback
registration is added, and the observer is null by default.

The staged native client now checks that the writer's BO handle names the
actual mapping entry and acquires the existing confirmed render lease. It
compares the two original backings at every page offset of the exact range,
including a nonzero render BO offset when applicable. The walk holds the
client lock but not the GPUVM lock. It rechecks the present preparation and
then resolves the native translation again under the GPUVM lock. Any
mismatch rejects the unused render lease through the existing cleanup path.
The comparison requires descriptors known to return original pages in the
same physical domain. It does not prove that domain for the actual
IOSurface descriptor or carry the present pin beyond the call. No page
addresses are exposed, and matching pages do not authorize DMA or scanout.

CPU tests exercise the extracted present probe and native method together,
including a short rounded tail, wrong surface or BO, a substituted last
page, a short physical segment and a translation change during the walk.
The original copy and flip paths are unchanged.

The separate [exact native writer stage](../tools/build34_dcn_exact_writer_stage.py)
derives the receipt-capacity and exact-open overlays, without stacking the
earlier render-map or TLB overlay onto their different VM implementation. It
accepts an optional sized extension on the existing exact submit selector.
The extension names one direct non-preamble GFX IB and a normalized host
BO range. The handler copies the wire once, rejects ambiguous IB addresses
for nomination, and checks that the same kernel map generation, prepared
descriptor and BO offset cover the range before and after the unchanged
typed submit. A missing or ineligible nomination does not change the normal
submit result. Neither the nomination nor a matched IB address proves what
memory the command stream actually wrote.

Each exact client keeps one numeric record outside the receipt registry. A
checked native WaitReceipt or ACK can mark it complete, and ACK can still
forget its slot. A later authenticated submit attempt, even if it fails or
encounters full receipts, invalidates the record. Mapping operations and
context free also invalidate it; close gates it out before the close reaper
clears it. The synchronous backing method refuses client or GPUVM lock
contention and checks the current VM allocation, owner and queue history
before and after comparing the borrowed, prepared descriptors. The page
walk includes the tail page and does not hold the GPUVM lock. No address
or descriptor leaves the method. Its result is historical, not a lease or
proof of DMA visibility; a caller needs the exact retained client and the
borrowed transaction backing throughout the call.

CPU tests run the extracted handler, typed submit, WaitReceipt, ACK and
backing method against doubles, including unaligned envelopes, forged and
stale receipts, ACK slot reuse, pending and out-of-order completion,
submission refusal, remapping, close, and generation loss during the page
walk. `BUILD34_KERNEL_HEADERS` enables a syntax-only check of the complete
staged kernel source against the pinned SDK headers. Discarding the overlay
is the rollback; no installation or runtime change is involved.

RADV does not yet send this extension, and no consumer is registered with
`performTransaction`. Before any copy bypass, the paired transport and
retained present handoff must establish earlier-writer drain, later writer
exclusion, actual native translation and HUBP visibility, and keep the
backing alive through flip latch and old-page retirement. The exact-open
gate, the R2a copy, and the `l10r` fallback remain unchanged.

ASan/UBSan tests cover binding bounds, generation reuse and the clear and
submission record lifecycles, plus the exact part's refusal paths and
out-of-order completion. Set `BUILD34_RADV_COMPILE_COMMANDS` to the
reviewed Darwin Meson recipe to check all 17 input digests, syntax-check
nine Mesa translation units, and run extracted Darwin submission and
exact completion logic against CPU doubles. Set `VULKAN_HEADERS` to also
syntax-check the paired plugin translation unit. Discarding the overlay
rolls back these stages. The installed R2a path, including `l10r`
conversion, remains unchanged.

Hardware acceptance requires proof of the actual device mapper,
lease/reverse-lookup semantics and HUBP fetch domain. It also requires
native invalidation, render completion and visibility, hardware latch
confirmation before retiring old pages, and bounded fallback/recovery.
Source-only rollback is a revert of this prerequisite.

## Accepted baseline measurement, November 20

[R1b's bounded pressure proof](BUILD34-RING-BACKPRESSURE.md) passed before
this R2 work began. The same accepted R1b/VBL/optimized-AML/accepted-plugin
installation remains active on macOS 26.7.2 build 25G332. No driver, startup
job, configuration, cache, EFI, ACPI or power change was made by profiling.
PR28 remains enabled at 250 ms with WindowServer excluded; resident monitors
remain disabled.

The finite [trace recipe and strict parser](../tools/build34_present_profile.py)
observe only PhxAccel's display transaction and its nested surface-wait and
copy-preparation methods. The admitted image is the existing
`a206d983fca62dd7959cc701fb9f95d5490da78986aac02dbb67ed00410325e7`
executable. Disassembly verified a single final `popq %rbp; retq` epilogue
per method. This host's FBT return offsets point to that final pop at
`0x7ac`, `0x162` and `0x405` respectively. These are actual method exits,
not a tail call to a still-running helper. The parser refuses other offsets,
failed/overlapping/unpaired transactions, diagnostics and empty samples.

The [12-second AppKit stimulus](../tools/anim/present_profile.m) is a small
CPU-drawn nonactivating panel, launched through Launch Services in the
console session. It ignores mouse input and closes automatically. Its source
does not explicitly create a Metal device; framework/compositor GPU use is
not excluded. All 23 onscreen checks passed, with 712 draw callbacks and
713 timer callbacks. The panel and its launcher exited normally. These
callback counts are not physical refresh or game FPS.

The eight-second trace contains 378 entries and 378 complete transactions,
all in kernel context, with no partial transaction at either boundary.

| Traced stage | Median | P95 | Maximum |
|---|---:|---:|---:|
| Entire display transaction | 3.457 ms | 5.932 ms | 9.522 ms |
| Nested GPU surface wait | 0.123 ms | 1.295 ms | 3.122 ms |
| Copy-readiness preparation | 0.004 ms | 0.009 ms | 0.049 ms |
| Remaining transaction work, including copy | 3.285 ms | 5.231 ms | 9.371 ms |

The residual is not an isolated copy timer and includes other work and trace
overhead. Do not add percentiles/maxima from different rows into a frame time.
The wider counter interval surrounds trace setup and the complete panel run:
667 successful surface-sourced transactions, zero flips, and 1,600,731 added
copy microseconds give a mean of about 2,399.90 us per copy in that interval.
That mean is not a distribution for the eight-second traced sample. This is
a bounded baseline observation, not a controlled FPS comparison.

The separate independent reader replayed the frozen trace parser and checked
the same boot, exact loaded/mapped images, full 358-file EFI, complete 416/29
cache metadata, loaded AML, startup receipts and exact recovery/jobs. The
same WindowServer survived, VBL/copy counters advanced, four checked errors
remained zero and no matching diagnostic report appeared. SSE and vsync were
both one before and after. No panel, trace, probe or pending power process
remains. See [sanitized evidence](validation/build34-r2-present-baseline-20261120.json).

## Preserved measurement refusals

The first idle trace ended cleanly but saw no new transaction. A panel trial
then produced 720 draws and passed 24 onscreen checks, but its first exit
implementation hid/closed the window without ending the app's run loop.
The completed hidden panel was identified by its exact executable/arguments
and terminated; this trial is not accepted. Its WindowServer-PID filter also
missed the actual kernel-context transactions.

A fresh panel with normal application termination captured 376 complete
transactions under the exact-module filter and exited. The first parser
expected `retq` offsets, but FBT reported the preceding final pop, so it
correctly refused its configured endpoints. Disassembly confirmed all three
actual epilogues before updating the parser. The final fresh trial above
passed the complete measurement and independent reader. Preserve all earlier
refusals; do not relabel them successful or replay their scopes.

Six CPU parser/program methods cover complete/boundary samples, empty runs,
unknown endpoints, failures, overlaps, diagnostics and finite module scope.
The default suite also exposed a pre-existing CPU trace-double scheduling
race: its short post-READY sleep could expire before the parent ran. That
success fixture now exits after an explicit fake-probe `G` acknowledgement;
production readiness/retirement limits and all refusal tests are unchanged.

## Isolated packed-stride candidate

`performTransaction` copies every row separately. Its inline SSE path saves
and restores ten XMM registers for every row. A candidate can combine rows
only when SSE is enabled, source/destination are aligned, both strides equal
the copied row length, and that length is a nonzero multiple of 64 bytes.
The source candidate implements just this selection and keeps the existing
row/tail path otherwise. It preserves l10r narrowing, surface readiness and
mapping ownership, the final store fence and transaction completion. A
2560-by-1600 packed frame can save/restore XMM state once rather than once
per row; that reduction is a code-path property, not a measured FPS gain.

[The production-code fixture](../tests/test_build34_present_copy.py) extracts
the actual copy block and SSE assembly. All 2,086 ASan/UBSan cases pass full
byte comparison against a scalar reference, including both formats, source
immutability, entire guard/padding regions, zero/short/full-size frames,
unequal pitches, alignment, scalar/SSE controls, tails and same-address copy.
The default suite, 25 complete-cache methods and 60 unchanged VBL CPU
assertions pass. One VBL test initially could not overwrite an older
root-owned ignored test binary; running that same CPU fixture with the
necessary file permissions passed. This was not a production/compiler or
hardware failure.

[The offline native recipe](../tools/build34_present_copy.py) freezes every
accepted accelerator source and licence input at `439f8a5`, requires the
exact complete old/new copy-source hashes, and uses audited MacKernelSDK
`3f750085caa17ec3a7880f11c11bf4f48cd6a164`. The unchanged baseline build
reproduces the installed executable exactly. The signed x86_64 candidate
passes architecture/signature checks with the same imports. Source, recipe
and frozen SDK readback pass. No kernel, plugin or native ABI change is made.

A fresh finite offline-cache scope links through the normal approved bundle
paths, with the same explicit-only bundle set and no authentication bypass.
A separately bounded guard protects the temporary executable staging. The
accepted disk executable was restored and its signature checked before the
guard ended; the installed auxiliary cache and startup jobs never changed.
The candidate cache's complete 416/29 metadata comparison admits only the
PhxAccel image change. All matching policy, paths, dependencies and
boot/system-collection links remain exact. Separate independent readback
reparsed this metadata, checked candidate/source signatures and the full
retained runtime/EFI/cache/AML/jobs, and observed desktop progress, zero
checked errors and no new report. No cache worker, guard, panel, trace,
native probe or power process remains. See
[offline evidence](validation/build34-r2-packed-copy-offline-20261120.json).

**This candidate is not installed or loaded.** A fresh R2a-compatible
controller must retain the current accepted R1b/VBL/AML/plugin as exact
recovery and preserve the 45/150/300-second startup bounds, daily PR28
250 ms/WindowServer exclusion and monitor-off policy. Do not use an old
controller that would roll the kernel, VBL or AML back further. A separate
new-boot loaded-image check and controlled display comparison remain required
before R2a hardware acceptance or R3.

The [separate R2a adapter](../tools/build34_present_copy_host.py) provides that
source/preparation path without changing historical hosts. Its distinct
sealed scope validates the exact two-image delta, retained EFI/kernel/AML
manifest and baseline jobs. Its final contract overlay changes only the
accelerator/cache hashes and accelerator image identity. Preparation uses
the still-loaded accepted accelerator identity for live checks while disk
and signature checks continue to require the candidate. Recovery checks
all inputs before the first mutation, restores only the accelerator/cache
pair and current retained jobs, and leaves EFI/kernel/plugin/AML untouched.
It verifies disk restoration without requiring the failed accelerator to
have started or treating a new diagnostic report as a failed disk restore.

Nine CPU fixture methods cover exact/unknown deltas, immutable derivation,
preserved kernel/ABI/EFI, daily configuration and current job accounting,
pre-restart identity separation, refusal before writes and two-image-only
recovery. The inherited bounded startup, finite watcher and no-daily-power
policy remain. This adapter is source-tested only; no new live scope,
candidate deployment or ordinary restart has occurred at this checkpoint.

The first inactive preparation then refused before any live image/job write:
the historical protected map gives `phxboot-off` an empty-file hash, while the
accepted accelerated installation intentionally has that disabling marker
absent. The new adapter originally tried to hash it as a required file. The
correction requires exact absence for that single historical switch and the
known empty-file hash; all other missing protected files and symlinks remain
refused. It does not create the marker or loosen a driver/image gate. Two
additional CPU methods cover that distinction. Keep the rejected private
packet and use a fresh scope after this source fix.

The next inactive preparation exposed another historical-map distinction:
the protected map still names an older plugin executable, while its
authoritative `plugin_after` manifest and independent readback identify the
accepted `c9dc00ce...` image. It refused before live writes. The adapter now
derives physical plugin expectations from that exact accepted manifest,
checks the manifest against the frozen runtime contract and pins the accepted
executable hash. No plugin binary, mapping or configuration is replaced. The
same delta fixtures also reject an unknown plugin manifest. Preserve this
second rejected packet and create another fresh scope.

## Fresh installation checkpoint

The third preparation passed exact retained-runtime checks, both contract
derivations and an inactive two-way native-file replacement test. Its sealed
packet retains the current R1b kernel and full EFI manifest, accepted plugin,
optimized AML, exact accelerator/cache recovery copies and the current
startup job backups. Neither rejected preparation is replayed.

The sole installer then replaced only the candidate accelerator/cache pair
and staged two startup jobs plus one finite watcher, without bootstrapping
any job. It exited successfully. Separate independent installed-state
readback passed complete 416-record/29-codeless candidate cache metadata,
all 358 unchanged EFI files, exact recovery and jobs, and the unchanged
**loaded accepted accelerator** with R1b/AML/plugin. The same WindowServer,
desktop progress, four zero error counters and no new matching report were
observed. Both fresh journals remain unconsumed. No explicit GPU workload,
ordinary restart or automatic recovery request occurred during installation.

The sequential trial next uses one ordinary restart from this fresh scope;
the existing panel flag must be force-synced and read back through both NVRAM
and IODeviceTree before the persisted single-use request. Preserve the
45/150/300-second limits, exact recovery, daily PR28 250 ms/WindowServer
exclusion and disabled resident monitors. Same-boot startup acceptance must
close automatic power recovery before any display measurement. Installed
state is not loaded-image or hardware acceptance; R3–R6 remain pending. See
[independent installation evidence](validation/build34-r2-packed-copy-installation-20261120.json).

This does not implement AMD asynchronous presentation or a DCN flip. Moving
the wait/copy to a worker still requires bounded ownership, cancellation,
stop/sleep handling and correct completion; removing the wait or NVIDIA vendor
check is not a safe optimization. R2 optimization acceptance and R3–R6 remain
pending. No FPS or long-term stability improvement has been demonstrated.

## Loaded trial and independent comparison, November 20

The single persisted ordinary restart completed at **20:45:23 Asia/Shanghai**
on macOS 26.7.2 build 25G332. The bounded watcher accepted the new boot,
closed its power recovery and retired its own job. No recovery restart was
requested. Independent readback passed fresh startup/desktop receipts, the
exact loaded R2a accelerator, retained R1b kernel/optimized AML/mapped accepted
plugin, all 358 EFI files, full 416-record/29-codeless cache metadata, exact
recovery/jobs, desktop progress, four zero error counters and no new report.

The first independent reader failed an additional accelerator assertion
because the legacy `support.loaded()` helper queries **only PhxBringup**.
The separate accelerator check already present in `live_identity` passed.
Preserving that failed reader and evidence, a new reader explicitly queried
`com.luuumi.PhxAccel`, required the exact candidate UUID and excluded the old
UUID. That reader passed without any driver/job/configuration change or
second restart. This does not relax loaded-image admission.

The fresh display profile used the exact baseline profiler and signed
Launch Services panel. Candidate executable `e5e91485...` was checked against
its full recorded hash; disassembly again verified final-pop FBT offsets
`0x7a3`, `0x162`, `0x405`, passed explicitly to the unchanged strict parser.
There were 398 kernel-context entries and **397 complete transactions**.
One entry at the trace-end boundary has no observed completion and is
excluded from all distributions. It is neither a failed transaction nor
accepted as a completed frame.

| Traced stage | Baseline median / P95 | R2a median / P95 | R2a maximum |
|---|---:|---:|---:|
| Entire display transaction | 3.457 / 5.932 ms | 3.471 / 6.308 ms | 21.029 ms |
| Nested GPU surface wait | 0.123 / 1.295 ms | 0.132 / 0.797 ms | 15.933 ms |
| Copy-readiness preparation | 0.004 / 0.009 ms | 0.004 / 0.008 ms | 0.024 ms |
| Remaining transaction work, including copy | 3.285 / 5.231 ms | 3.311 / 6.027 ms | 9.021 ms |

The wider complete-panel counter interval recorded 743 successful
surface-sourced copies and 1,811,762 added copy microseconds: **2,438.44 us
per copy**, versus baseline 2,399.90 us (**+1.61% observed**). These are
different-boot, single-run observations with different interval transaction
counts and unisolated desktop work; they neither establish a causal
regression nor prove an improvement. The largest observed transaction
includes a 15.933 ms surface wait. Stage percentiles cannot be added, and
the residual remains more than a pure copy timer. Packed-branch execution
was not directly counted. Saving per-row XMM operations alone is not an
established solution to the measured copy cost.

The panel ran for 12.001 seconds, with 719 timer/draw callbacks and 23/23
onscreen checks. SSE/vsync stayed enabled. There were zero flips, copy
failures/skips or surface timeouts. Independent replay checked the frozen
trace/parser and raw counter deltas, then repeated full disk/cache/EFI/AML,
exact loaded/mapped images, receipts, recovery/jobs and desktop-progress
checks. The same WindowServer survived, all four checked errors stayed zero
and no matching report appeared. No panel, trace, probe, scope worker or
power process remains.

This accepts **R2a's bounded functional trial only**, not optimization
efficacy, physical FPS, visual-artifact absence or long-term stability.
Keep the passed installation active and preserve consumed scopes. R2's
asynchronous wait/copy and DCN lifecycle work remain unresolved; do not
remove readiness/completion protection to make timings appear faster.
R3 source/measurement work can now proceed with the safe global reclamation
watermark retained. R3–R6 have no hardware acceptance. See
[sanitized loaded-trial evidence](validation/build34-r2-packed-copy-boot-20261120.json).
