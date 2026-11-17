/* SPDX-License-Identifier: MIT */
#include "radv_ib_tail_runtime_guard.h"
#include "navi48_native_abi.h"
#include <CoreFoundation/CoreFoundation.h>
#include <IOKit/IOKitLib.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static pthread_mutex_t mutex = PTHREAD_MUTEX_INITIALIZER;
static struct phx34_runtime_counts counts;
static bool armed, matched, hello_ok, info_ok, uncertain, arena_bound;
static io_service_t chosen;
static io_connect_t client;
static unsigned creates, native_calls, hello_calls;
static uint64_t total_bytes;
struct BO { uint64_t size; uintptr_t cpu; unsigned cpu_maps; bool live; };
static BO bos[N48N_MAX_BOS];
struct Mapping { uint64_t va, size, offset; unsigned handle, flags; bool live; };
static Mapping mappings[N48N_MAX_BOS];
static bool contexts[N48N_MAX_CTX + 1];
static uint32_t tail_handle;
static uint64_t tail_va;
static bool tail_unmapped;
struct SavedIB { uint64_t va; uint32_t bytes; uint8_t *data; };
static SavedIB saved[N48N_MAX_IBS];
static unsigned saved_count;
static constexpr uint64_t va_mask = (1ull << 48) - 1;
static bool canonical(uint64_t va) { return (va >> 47) == 0 || (va >> 47) == 0x1ffff; }

extern "C" __attribute__((noreturn)) void phx34_runtime_hold(const char *reason)
{
    fprintf(stderr, "FAIL: full RADV runtime %s\nHOLD: retain process, connection and BOs for independent recovery\n", reason);
#ifdef PHX34_RUNTIME_GUARD_CPU
    fprintf(stderr, "CPU-FIXTURE-HOLD: opens=%u closes=%u fake_submits=%u arena_passes=%u\n",
            counts.opens, counts.closes, counts.submits, counts.arena_passes);
#endif
    fflush(nullptr);
    for (;;) pause();
}
static void require(bool okay, const char *why) { if (!okay) phx34_runtime_hold(why); }
struct Lock {
    Lock() { require(!pthread_mutex_lock(&mutex), "guard mutex acquisition"); }
    ~Lock() { require(!pthread_mutex_unlock(&mutex), "guard mutex release"); }
};

#ifdef PHX34_RUNTIME_GUARD_CPU
extern "C" io_service_t phx34_cpu_match(void);
extern "C" kern_return_t phx34_cpu_open(io_service_t, task_port_t, uint32_t, io_connect_t *);
extern "C" kern_return_t phx34_cpu_close(io_connect_t);
extern "C" kern_return_t phx34_cpu_map(io_connect_t, uint32_t, task_port_t, mach_vm_address_t *, mach_vm_size_t *, IOOptionBits);
extern "C" kern_return_t phx34_cpu_unmap(io_connect_t, uint32_t, task_port_t, mach_vm_address_t);
extern "C" kern_return_t phx34_cpu_call(mach_port_t, uint32_t, const uint64_t *, uint32_t, const void *, size_t,
                                        uint64_t *, uint32_t *, void *, size_t *);
extern "C" void phx34_cpu_arena(void *, size_t);
#define platform_match phx34_cpu_match
#define platform_open phx34_cpu_open
#define platform_close phx34_cpu_close
#define platform_map phx34_cpu_map
#define platform_unmap phx34_cpu_unmap
#define platform_call phx34_cpu_call
#else
static bool pci_value(io_registry_entry_t entry, CFStringRef key, uint32_t *out)
{
    CFTypeRef v = IORegistryEntryCreateCFProperty(entry, key, kCFAllocatorDefault, 0);
    if (!v) return false;
    bool okay = false;
    if (CFGetTypeID(v) == CFDataGetTypeID() && CFDataGetLength((CFDataRef)v) == 4) {
        const UInt8 *p = CFDataGetBytePtr((CFDataRef)v);
        if (p) { *out = p[0] | uint32_t(p[1]) << 8 | uint32_t(p[2]) << 16 | uint32_t(p[3]) << 24; okay = true; }
    } else if (CFGetTypeID(v) == CFNumberGetTypeID()) {
        int64_t n = -1;
        if (CFNumberGetValue((CFNumberRef)v, kCFNumberSInt64Type, &n) && n >= 0 && n <= UINT32_MAX) { *out = uint32_t(n); okay = true; }
    }
    CFRelease(v); return okay;
}
static io_service_t platform_match(void)
{
    CFMutableDictionaryRef dict = IOServiceMatching("PhxBringup");
    require(dict != nullptr, "matching dictionary");
    io_iterator_t iterator = 0;
    require(IOServiceGetMatchingServices(kIOMainPortDefault, dict, &iterator) == KERN_SUCCESS && iterator,
            "direct service enumeration");
    io_service_t selected = 0; unsigned targets = 0;
    for (io_service_t service; (service = IOIteratorNext(iterator));) {
        io_registry_entry_t parent = 0; uint32_t vendor = 0, product = 0; bool target = false;
        if (IORegistryEntryGetParentEntry(service, kIOServicePlane, &parent) == KERN_SUCCESS) {
            target = IOObjectConformsTo(parent, "IOPCIDevice") && pci_value(parent, CFSTR("vendor-id"), &vendor) &&
                     pci_value(parent, CFSTR("device-id"), &product) && vendor == 0x1002 && product == 0x1900;
            require(IOObjectRelease(parent) == KERN_SUCCESS, "PCI parent release");
        }
        if (target && ++targets == 1) selected = service;
        else require(IOObjectRelease(service) == KERN_SUCCESS, "unselected service release");
    }
    require(IOObjectRelease(iterator) == KERN_SUCCESS && targets == 1 && selected, "exact one PCI 1002:1900 service");
    return selected;
}
#define platform_open IOServiceOpen
#define platform_close IOServiceClose
#define platform_map IOConnectMapMemory64
#define platform_unmap IOConnectUnmapMemory64
#define platform_call IOConnectCallMethod
#endif

extern "C" void phx34_runtime_counts(struct phx34_runtime_counts *out)
{
    Lock lock; require(out != nullptr, "counts destination"); *out = counts;
#ifdef PHX34_RUNTIME_GUARD_CPU
    out->CPU_platform = 1;
#endif
}
extern "C" int phx34_runtime_platform_selftest(void)
{
    Lock lock;
    require(!armed && counts.blocked == 1 && !counts.opens, "platform self-test phase");
#ifdef PHX34_RUNTIME_GUARD_CPU
    return 1;
#else
    io_connect_t invalid = 0;
    kern_return_t r = IOServiceOpen(IO_OBJECT_NULL, mach_task_self(), 0, &invalid);
    return r != KERN_SUCCESS && !invalid && counts.blocked == 1;
#endif
}
extern "C" void phx34_runtime_arm(void)
{
    Lock lock; const char *tail = getenv("RADV_DARWIN_BUILD34_IB_TAIL");
    require(!armed && counts.blocked == 1 && !counts.opens && tail && !strcmp(tail, "1"), "one-use explicit tail arming");
    counts.blocked = 0; armed = true;
}
static io_service_t guard_match(mach_port_t port, CFDictionaryRef dict)
{
    Lock lock; (void)port;
    if (!armed) { ++counts.blocked; if (dict) CFRelease(dict); return 0; }
    require(dict && !matched && !counts.opens, "no matching retry or proxy fallback");
    CFTypeRef name = CFDictionaryGetValue(dict, CFSTR("IOProviderClass"));
    require(name && CFGetTypeID(name) == CFStringGetTypeID() && CFEqual(name, CFSTR("PhxBringup")), "direct Phoenix service only");
    CFRelease(dict); matched = true; chosen = platform_match();
    require(chosen != 0, "one direct target service"); return chosen;
}
static kern_return_t guard_matches(mach_port_t port, CFDictionaryRef dict, io_iterator_t *out)
{
    Lock lock; (void)port;
    if (!armed) { ++counts.blocked; if (dict) CFRelease(dict); if (out) *out = 0; return kIOReturnNotPermitted; }
    phx34_runtime_hold("unexpected alternate service enumeration");
}
static kern_return_t guard_open(io_service_t service, task_port_t task, uint32_t type, io_connect_t *out)
{
    Lock lock;
    if (!armed) { ++counts.blocked; if (out) *out = 0; return kIOReturnNotPermitted; }
    require(matched && service == chosen && task == mach_task_self() && type == N48N_UC_TYPE && out &&
            !counts.opens && !counts.closes && !client, "one direct client opening; no retry");
    ++counts.opens;
    kern_return_t r = platform_open(service, task, type, out);
    require(r == KERN_SUCCESS && *out, "direct open failed; no retry"); client = *out; return r;
}
static void ready(io_connect_t connection)
{
    require(armed && counts.opens == 1 && !counts.closes && connection == client && client, "live single client");
}
static void retired(void)
{
    require(!uncertain && (!counts.submits || (counts.last_sequence && counts.retired_sequence >= counts.last_sequence)),
            "positive retirement before resource changes");
}
static kern_return_t guard_map(io_connect_t connection, uint32_t h, task_port_t task,
                              mach_vm_address_t *address, mach_vm_size_t *size, IOOptionBits options)
{
    Lock lock;
    if (!armed) { ++counts.blocked; return kIOReturnNotPermitted; }
    ready(connection); require(info_ok && task == mach_task_self() && options == kIOMapAnywhere && address && size &&
            h && h < N48N_MAX_BOS && bos[h].live && !bos[h].cpu_maps && h != (tail_unmapped ? tail_handle : 0), "CPU map bounds/no tail remapping");
    kern_return_t r = platform_map(connection, h, task, address, size, options);
    require(r == KERN_SUCCESS && *address && !(*address & 4095) && *size == bos[h].size && *address <= UINTPTR_MAX - *size,
            "CPU map response geometry");
    bos[h].cpu = *address; bos[h].cpu_maps = 1; return r;
}
static kern_return_t guard_unmap(io_connect_t connection, uint32_t h, task_port_t task, mach_vm_address_t address)
{
    Lock lock;
    if (!armed) { ++counts.blocked; return kIOReturnNotPermitted; }
    ready(connection); retired();
    require(task == mach_task_self() && h && h < N48N_MAX_BOS && bos[h].live && bos[h].cpu_maps == 1 &&
            address == bos[h].cpu, "CPU unmap identity");
    if (h == tail_handle) {
        const uint32_t nop[8] = {0xc0061000u,0,0,0,0,0,0,0};
        require(!tail_unmapped && !counts.submits && bos[h].size == 4096 && !memcmp((void *)address, nop, sizeof(nop)), "immutable tail bytes");
        const uint8_t *p = (const uint8_t *)address;
        for (size_t i = sizeof(nop); i < 4096; ++i) require(!p[i], "immutable tail zero padding");
        tail_unmapped = true;
    }
    kern_return_t r = platform_unmap(connection, h, task, address);
    require(r == KERN_SUCCESS, "CPU unmap result"); bos[h].cpu = 0; bos[h].cpu_maps = 0; return r;
}
static const uint8_t *payload_bytes(const n48n_cs_ib &ib)
{
    const uint64_t va = ib.va_start & va_mask;
    for (const Mapping &m : mappings) if (m.live && va >= m.va && ib.ib_bytes <= m.size && va - m.va <= m.size - ib.ib_bytes) {
        const BO &b = bos[m.handle];
        require((m.flags & N48N_VM_PAGE_EXECUTABLE) && b.live && b.cpu_maps && b.cpu && m.offset <= b.size && va - m.va <= b.size - m.offset &&
                ib.ib_bytes <= b.size - m.offset - (va - m.va), "submitted IB readable executable backing");
        return (const uint8_t *)b.cpu + m.offset + va - m.va;
    }
    phx34_runtime_hold("submitted IB has no tracked GPU mapping");
}
static void inspect_submit(const void *structure, size_t bytes)
{
    require(info_ok && arena_bound && counts.submits < 2 && !uncertain && structure && bytes >= sizeof(n48n_cs_in), "two-submit bound/admission");
    retired(); const n48n_cs_in *h = (const n48n_cs_in *)structure;
    require(h->abi == 1 && h->ctx_id && h->ctx_id <= N48N_MAX_CTX && contexts[h->ctx_id] && h->num_ibs >= 2 &&
            h->num_ibs <= N48N_MAX_IBS && bytes == sizeof(*h) + h->num_ibs * sizeof(n48n_cs_ib) && !h->reserved &&
            !(h->flags & ~N48N_CS_HAS_FENCE), "native submit shape");
    if (h->flags & N48N_CS_HAS_FENCE)
        require(h->fence_handle && h->fence_handle < N48N_MAX_BOS && bos[h->fence_handle].live &&
                !(h->fence_offset & 7) && h->fence_offset <= bos[h->fence_handle].size - 8, "user-fence geometry");
    else require(!h->fence_handle && !h->fence_offset, "absent user fence");
    const n48n_cs_ib *ibs = (const n48n_cs_ib *)((const uint8_t *)structure + sizeof(*h));
    require(counts.tail_published && tail_va && tail_unmapped, "published immutable tail");
    for (unsigned i = 0; i < h->num_ibs; ++i) {
        const n48n_cs_ib &ib = ibs[i];
        require(!ib._pad && !(ib.flags & ~(N48N_IB_FLAG_PREAMBLE | N48N_IB_FLAG_PREEMPT | N48N_IB_FLAG_TC_WB_NOT_INVALIDATE)) &&
                ib.ip_type == 1 && !ib.ip_instance && !ib.ring && ib.ib_bytes && !(ib.ib_bytes & 3) && !(ib.va_start & 3) &&
                canonical(ib.va_start) && ib.ib_bytes <= (1ull << 48) - (ib.va_start & va_mask), "compute-only descriptors");
        if (i + 1 == h->num_ibs) {
            require(!ib.flags && ib.va_start == tail_va && ib.ib_bytes == 32, "last descriptor is the private tail");
            continue;
        }
        require(ib.ib_bytes <= (1u << 20) && ib.va_start != tail_va, "bounded payload distinct from tail");
        const uint8_t *data = payload_bytes(ib);
        if (!counts.submits) {
            SavedIB &s = saved[saved_count++]; s.va = ib.va_start; s.bytes = ib.ib_bytes;
            s.data = (uint8_t *)malloc(s.bytes); require(s.data != nullptr, "IB observer allocation"); memcpy(s.data, data, s.bytes);
        } else {
            for (unsigned j = 0; j < saved_count; ++j) {
                const uint32_t common = saved[j].bytes < ib.ib_bytes ? saved[j].bytes : ib.ib_bytes;
                if (saved[j].va == ib.va_start && memcmp(saved[j].data, data, common)) {
                    counts.reused_changed_IB = 1;
                    counts.first_reused_IB_bytes = saved[j].bytes;
                    counts.second_reused_IB_bytes = ib.ib_bytes;
                }
            }
        }
    }
    ++counts.submits; uncertain = true;
}
static kern_return_t guard_call(mach_port_t connection, uint32_t sel, const uint64_t *input, uint32_t input_count,
    const void *structure, size_t structure_size, uint64_t *output, uint32_t *output_count, void *result, size_t *result_size)
{
    Lock lock;
    if (!armed) { ++counts.blocked; return kIOReturnNotPermitted; }
    ready(connection); require(++native_calls <= 10000, "native API call bound");
    if (sel == N48N_SEL_HELLO)
        require(hello_calls < 2 && !creates && !counts.submits && input_count == 2 && input && input[0] == 1 && input[1] == N48N_HELLO_F_MINOR &&
                output && output_count && *output_count == 4, "core/tail original34 Hello only; no ABI fallback");
    else require(hello_ok, "Hello before native operations");
    if (sel != N48N_SEL_HELLO && sel != N48N_SEL_QUERYINFO) require(info_ok, "QueryInfo admission before operations");
    switch (sel) {
    case N48N_SEL_HELLO: break;
    case N48N_SEL_QUERYINFO: require(result && result_size && *result_size == sizeof(n48n_info), "QueryInfo shape"); break;
    case 30: require(!input_count && !structure_size, "read-only topology shape"); break;
    case N48N_SEL_READREGS:
        require(input && input_count == 3 && input[1] && input[1] <= 16 && input[2] == UINT32_MAX, "read-only register shape"); break;
    case N48N_SEL_BOCREATE: {
        require(structure && structure_size == sizeof(n48n_gem_create_in) && output && output_count && *output_count == 4, "BO create shape");
        const n48n_gem_create_in *in = (const n48n_gem_create_in *)structure;
        require(in->bo_size && in->bo_size <= (64ull << 20) && total_bytes + ((in->bo_size + 4095) & ~4095ull) <= (256ull << 20), "bounded BO allocation");
        if (!creates) require(in->bo_size == 4096 && in->domains == N48N_GEM_DOMAIN_GTT, "first BO is the core tail");
        break;
    }
    case N48N_SEL_BOFREE:
        retired(); require(input && input_count == 1 && input[0] && input[0] < N48N_MAX_BOS &&
                          bos[input[0]].live && !bos[input[0]].cpu_maps && input[0] != tail_handle, "retired BO free identity"); break;
    case N48N_SEL_GEMVA: {
        require(structure && structure_size == sizeof(n48n_gem_va), "GPU map shape");
        const n48n_gem_va *m = (const n48n_gem_va *)structure;
        require(m->handle && m->handle < N48N_MAX_BOS && bos[m->handle].live && !m->_pad && !m->vm_timeline_point &&
                !m->vm_timeline_syncobj_out && !m->num_syncobj_handles && !m->input_fence_syncobj_handles && m->map_size &&
                !(m->va_address & 4095) && !(m->offset_in_bo & 4095) && !(m->map_size & 4095) &&
                m->offset_in_bo <= bos[m->handle].size && m->map_size <= bos[m->handle].size - m->offset_in_bo &&
                canonical(m->va_address) && (m->va_address & va_mask) >= 0x10000 &&
                m->map_size <= (1ull << 48) - (m->va_address & va_mask) &&
                (m->operation == N48N_VA_OP_MAP || m->operation == N48N_VA_OP_UNMAP), "tracked GPU map bounds");
        if (m->operation == N48N_VA_OP_UNMAP) retired();
        if (m->handle == tail_handle)
            require(tail_unmapped && !counts.tail_published && !counts.submits && m->operation == N48N_VA_OP_MAP &&
                    m->map_size == 4096 && !m->offset_in_bo && m->flags == (N48N_VM_PAGE_READABLE | N48N_VM_PAGE_EXECUTABLE), "immutable read/execute tail mapping");
        break;
    }
    case N48N_SEL_CTX: {
        require(structure && structure_size == sizeof(n48n_ctx) && result && result_size && *result_size == sizeof(n48n_ctx), "context shape");
        const n48n_ctx *in = (const n48n_ctx *)structure;
        require(in->op == N48N_CTX_OP_ALLOC || in->op == N48N_CTX_OP_FREE || in->op == N48N_CTX_OP_QUERY_STATE2, "context operation");
        if (in->op != N48N_CTX_OP_ALLOC) require(in->ctx_id && in->ctx_id <= N48N_MAX_CTX && contexts[in->ctx_id], "known context");
        if (in->op == N48N_CTX_OP_FREE) retired(); break;
    }
    case N48N_SEL_SUBMIT:
        require(output && output_count && *output_count == 1, "submit response destination");
        inspect_submit(structure, structure_size); break;
    case N48N_SEL_WAITSEQ:
        require(input && input_count == 3 && counts.submits && !uncertain && input[0] && input[0] <= counts.last_sequence &&
                input[1] <= N48N_WAIT_CAP_NS && output && output_count && *output_count == 3, "bounded wait shape"); break;
    default: phx34_runtime_hold("selector outside compute test; no scanout, proxy or imports");
    }
    kern_return_t r = platform_call(connection, sel, input, input_count, structure, structure_size, output, output_count, result, result_size);
    if (sel == 30 && r == kIOReturnUnsupported) return r;
    require(r == KERN_SUCCESS, "native API error; no replay or cleanup");
    switch (sel) {
    case N48N_SEL_HELLO:
        require(*output_count == 4 && output[0] == (1 | (12ull << 16)) && output[1] == 34 && output[2] == 64 && output[3] == 8,
                "exact original34 ABI1.12/VMID8 identity"); hello_ok = true; ++hello_calls; break;
    case N48N_SEL_QUERYINFO: {
        const n48n_info *info = (const n48n_info *)result;
        require(*result_size == sizeof(*info) && info->abi_version == 1 && info->reserved[2] == 12 && info->kext_build == 34 &&
                info->vmid == 8 && info->max_ibs == 64 && info->gc_version == ((11u << 16) | 1) &&
                (info->flags & (N48N_INFO_HUNG | N48N_INFO_NATIVE_BOOT | N48N_INFO_S1B_POSITIVE)) ==
                (N48N_INFO_NATIVE_BOOT | N48N_INFO_S1B_POSITIVE), "original34 ready/not-HUNG QueryInfo"); info_ok = true; break;
    }
    case N48N_SEL_BOCREATE: {
        const n48n_gem_create_in *in = (const n48n_gem_create_in *)structure;
        require(*output_count == 4 && output[0] && output[0] < N48N_MAX_BOS && !bos[output[0]].live &&
                output[1] == ((in->bo_size + 4095) & ~4095ull) &&
                (output[2] == N48N_GEM_DOMAIN_GTT || output[2] == N48N_GEM_DOMAIN_VRAM) && (output[2] & in->domains) &&
                (output[3] & N48N_PLACED_ZEROED) && !(output[3] & ~(uint64_t)(N48N_PLACED_ZEROED | N48N_PLACED_CPU_MAPPABLE)), "BO response geometry");
        if (!creates++) tail_handle = output[0];
        bos[output[0]] = {output[1],0,0,true}; total_bytes += output[1]; break;
    }
    case N48N_SEL_BOFREE:
        for (Mapping &m : mappings) if (m.live && m.handle == input[0]) m.live = false;
        total_bytes -= bos[input[0]].size; bos[input[0]] = {}; break;
    case N48N_SEL_GEMVA: {
        const n48n_gem_va *in = (const n48n_gem_va *)structure;
        const uint64_t va = in->va_address & va_mask;
        if (in->operation == N48N_VA_OP_MAP) {
            Mapping *empty = nullptr;
            for (Mapping &m : mappings) {
                if (!m.live && !empty) empty = &m;
                if (m.live) require(va + in->map_size <= m.va || m.va + m.size <= va, "nonoverlapping GPU maps");
            }
            require(empty != nullptr, "GPU map observer capacity");
            *empty = {va,in->map_size,in->offset_in_bo,in->handle,in->flags,true};
            if (in->handle == tail_handle) { tail_va = in->va_address; counts.tail_published = 1; }
        } else {
            bool found = false;
            for (Mapping &m : mappings) if (m.live && m.handle == in->handle && m.va == va && m.size == in->map_size) { m.live = false; found = true; }
            require(found, "known full GPU unmap");
        }
        break;
    }
    case N48N_SEL_CTX: {
        require(*result_size == sizeof(n48n_ctx), "context response size");
        const n48n_ctx *in = (const n48n_ctx *)structure, *out = (const n48n_ctx *)result;
        if (in->op == N48N_CTX_OP_ALLOC) {
            require(out->op && out->op <= N48N_MAX_CTX && !contexts[out->op] && !out->flags && !out->ctx_id && !out->priority, "context allocation response"); contexts[out->op] = true;
        } else {
            require(!out->op && !out->flags && !out->ctx_id && !out->priority, "context reset/hang response");
            if (in->op == N48N_CTX_OP_FREE) contexts[in->ctx_id] = false;
        }
        break;
    }
    case N48N_SEL_SUBMIT:
        require(*output_count == 1 && output[0] && output[0] != N48N_SEQ_LAST && output[0] > counts.last_sequence, "strictly increasing submitted sequence");
        counts.last_sequence = output[0]; uncertain = false; break;
    case N48N_SEL_WAITSEQ:
        require(*output_count == 3 && output[0] <= 1 && output[1] != N48N_SEQ_LAST && output[2] == counts.last_sequence && output[1] <= output[2], "wait response sequence bounds");
        if (!output[0]) { require(output[1] >= input[0], "positive requested retirement"); counts.retired_sequence = output[1]; } break;
    default: break;
    }
    return r;
}
static kern_return_t guard_close(io_connect_t connection)
{
    Lock lock;
    if (!armed) { ++counts.blocked; return kIOReturnNotPermitted; }
    ready(connection); retired(); require(counts.submits == 2 && counts.arena_passes == 2 && counts.reused_changed_IB, "both guarded passes before close");
    kern_return_t r = platform_close(connection); require(r == KERN_SUCCESS, "native client close response"); ++counts.closes; return r;
}
extern "C" void phx34_runtime_bind_arena(void *address, size_t bytes)
{
    Lock lock; require(armed && !arena_bound && !counts.submits && address && bytes == 16384, "one 16-KiB arena binding");
    bool found = false;
    for (const BO &b : bos) if (b.live && b.cpu_maps && b.cpu && b.size >= bytes && uintptr_t(address) >= b.cpu && uintptr_t(address) - b.cpu <= b.size - bytes) found = true;
    require(found, "arena belongs to the tracked client"); arena_bound = true;
#ifdef PHX34_RUNTIME_GUARD_CPU
    phx34_cpu_arena(address, bytes);
#endif
}
extern "C" void phx34_runtime_verify_pass(unsigned pass)
{
    Lock lock; retired(); require(pass < 2 && counts.arena_passes == pass && counts.submits == pass + 1 &&
                                 (!pass || counts.reused_changed_IB), "matching submission/reused changed IB/arena pass"); ++counts.arena_passes;
}
extern "C" void phx34_runtime_finish(void)
{
    Lock lock; retired(); require(hello_calls == 2 && counts.opens == 1 && counts.closes == 1 && counts.submits == 2 && counts.arena_passes == 2 &&
                                 counts.tail_published && counts.reused_changed_IB && !counts.blocked, "complete full-runtime evidence");
    for (SavedIB &s : saved) { free(s.data); s.data = nullptr; }
}
#define INTERPOSE(replacement, original) \
    __attribute__((used)) static const struct { const void *replace, *original; } \
    pair_##original __attribute__((section("__DATA,__interpose"))) = \
    { (const void *)(uintptr_t)&replacement, (const void *)(uintptr_t)&original }
INTERPOSE(guard_match, IOServiceGetMatchingService);
INTERPOSE(guard_matches, IOServiceGetMatchingServices);
INTERPOSE(guard_open, IOServiceOpen);
INTERPOSE(guard_close, IOServiceClose);
INTERPOSE(guard_map, IOConnectMapMemory64);
INTERPOSE(guard_unmap, IOConnectUnmapMemory64);
INTERPOSE(guard_call, IOConnectCallMethod);
