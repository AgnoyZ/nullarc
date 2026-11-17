// SPDX-License-Identifier: MIT
// Bounded original34 probe through the REAL Mesa core/CS/transport functions.
// No Vulkan/desktop claim, initialization, deployment, proxy route or open retry.
#include <IOKit/IOKitLib.h>
#include <CoreFoundation/CoreFoundation.h>
#include <mach/mach_time.h>
#include <sys/utsname.h>
#include <unistd.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "ac_darwin_drm.h"
#include "ac_darwin_kext.h"
#include "util/u_sync_provider.h"
#include "ib_preamble_packets.h"

static constexpr size_t arenaBytes = 16384;
static unsigned opens, closes;
static bool closeFailed;
[[noreturn]] static void hold(const char *why);
struct Direct {
    io_connect_t connection;
    uint64_t sizes[N48N_MAX_BOS];
    unsigned submits;
    uint64_t lastSeq, retired;
    bool uncertain;
};

static int pciValue(io_registry_entry_t entry, CFStringRef key, uint32_t *out) {
    CFTypeRef value = IORegistryEntryCreateCFProperty(entry, key, kCFAllocatorDefault, 0);
    if (!value) return 0;
    int valid = 0;
    if (CFGetTypeID(value) == CFDataGetTypeID() && CFDataGetLength((CFDataRef)value) == 4) {
        const UInt8 *p = CFDataGetBytePtr((CFDataRef)value);
        if (p) { *out = p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24; valid = 1; }
    } else if (CFGetTypeID(value) == CFNumberGetTypeID()) {
        int64_t number = -1;
        if (CFNumberGetValue((CFNumberRef)value, kCFNumberSInt64Type, &number) && number >= 0 && number <= UINT32_MAX) {
            *out = (uint32_t)number; valid = 1;
        }
    }
    CFRelease(value); return valid;
}
static int directCall(void *opaque, uint32_t sel, const uint64_t *sin, uint32_t nsin,
    const void *stin, size_t stinsz, uint64_t *sout, uint32_t *nsout, void *stout, size_t *stoutsz) {
    Direct *c = static_cast<Direct *>(opaque);
    if (sel == ACD_SEL_SUBMIT) {
        if (c->submits >= 2 || c->uncertain) hold("native dispatch bound");
        ++c->submits; c->uncertain = true;
    }
    const int r = IOConnectCallMethod(c->connection, sel, sin, nsin, stin, stinsz, sout, nsout, stout, stoutsz);
    if (!r && sel == ACD_SEL_BO_CREATE && stin && stinsz == sizeof(n48n_gem_create_in) && nsout && *nsout == 4) {
        const n48n_gem_create_in *create = static_cast<const n48n_gem_create_in *>(stin);
        if (!sout[0] || sout[0] >= N48N_MAX_BOS || sout[1] != create->bo_size ||
            (sout[1] != 4096 && sout[1] != arenaBytes) || sout[2] != N48N_GEM_DOMAIN_GTT ||
            !(sout[3] & N48N_PLACED_ZEROED) || (sout[3] & ~(uint64_t)(N48N_PLACED_ZEROED | N48N_PLACED_CPU_MAPPABLE)))
            hold("created BO response geometry");
        c->sizes[sout[0]] = sout[1];
    }
    if (!r && sel == ACD_SEL_SUBMIT && nsout && *nsout == 1 && sout[0] &&
        sout[0] != N48N_SEQ_LAST && sout[0] > c->lastSeq) {
        c->lastSeq = sout[0]; c->uncertain = false;
    }
    if (!r && sel == ACD_SEL_WAIT_SEQ && nsout && *nsout == 3 && !sout[0] &&
        sout[1] != N48N_SEQ_LAST && sout[1] >= c->lastSeq && sout[2] == c->lastSeq)
        c->retired = sout[1];
    return r;
}
static int directMap(void *opaque, uint32_t handle, void **addr, size_t *size) {
    Direct *c = static_cast<Direct *>(opaque); mach_vm_address_t a = 0; mach_vm_size_t s = 0;
    int r = IOConnectMapMemory64(c->connection, handle, mach_task_self(), &a, &s, kIOMapAnywhere);
    if (!r && (!handle || handle >= N48N_MAX_BOS || !c->sizes[handle] || s != c->sizes[handle] ||
        !a || (a & 4095) || a > UINTPTR_MAX - s)) hold("CPU mapping response geometry");
    if (!r) { *addr = reinterpret_cast<void *>(a); *size = s; }
    return r;
}
static int directUnmap(void *opaque, uint32_t handle, void *addr) {
    Direct *c = static_cast<Direct *>(opaque);
    return IOConnectUnmapMemory64(c->connection, handle, mach_task_self(), reinterpret_cast<uintptr_t>(addr));
}
static void directClose(void *opaque) {
    Direct *c = static_cast<Direct *>(opaque);
    if (c->uncertain || c->retired < c->lastSeq) hold("platform close without retirement");
    ++closes;
    closeFailed |= IOServiceClose(c->connection) != KERN_SUCCESS; delete c;
}
// Only the platform open/map/call boundary is replaced. The Mesa core, VA
// allocator, BO, CS parser, splitting, tail creation and teardown are real code.
extern "C" int acd_kext_open_iokit(struct acd_kext **out) {
    *out = nullptr;
    if (opens++) return -1;
    CFMutableDictionaryRef matching = IOServiceMatching("PhxBringup");
    if (!matching) return -1;
    io_iterator_t iterator = IO_OBJECT_NULL;
    if (IOServiceGetMatchingServices(kIOMainPortDefault, matching, &iterator) != KERN_SUCCESS || !iterator) return -1;
    io_service_t chosen = IO_OBJECT_NULL; unsigned count = 0; bool failed = false;
    for (io_service_t service; (service = IOIteratorNext(iterator));) {
        io_registry_entry_t parent = IO_OBJECT_NULL; uint32_t vendor = 0, product = 0; bool target = false;
        if (IORegistryEntryGetParentEntry(service, kIOServicePlane, &parent) == KERN_SUCCESS) {
            target = IOObjectConformsTo(parent, "IOPCIDevice") && pciValue(parent, CFSTR("vendor-id"), &vendor) &&
                pciValue(parent, CFSTR("device-id"), &product) && vendor == 0x1002 && product == 0x1900;
            failed |= IOObjectRelease(parent) != KERN_SUCCESS;
        }
        if (target && ++count == 1) chosen = service;
        else failed |= IOObjectRelease(service) != KERN_SUCCESS;
    }
    failed |= IOObjectRelease(iterator) != KERN_SUCCESS;
    if (failed || count != 1) { if (chosen) IOObjectRelease(chosen); return -1; }
    Direct *c = new Direct{};
    const int r = IOServiceOpen(chosen, mach_task_self(), N48N_UC_TYPE, &c->connection);
    const int released = IOObjectRelease(chosen);
    if (r || !c->connection) { delete c; return -1; }
    const acd_kext_ops ops = {directCall, directMap, directUnmap, directClose, nullptr};
    struct acd_kext *k = acd_kext_create(&ops, c);
    if (!k) return -1;
    acd_hello h{}; n48n_info info{};
    if (released || acd_kext_hello(k, &h) || acd_kext_query_info(k, &info) ||
        h.abi != 1 || h.minor != 12 || h.build != 34 || h.max_ibs != N48N_MAX_IBS || h.vmid != 8 ||
        info.abi_version != 1 || info.reserved[2] != 12 || info.kext_build != 34 || info.vmid != 8 ||
        info.gc_version != ((11u << 16) | 1u) || info.max_ibs != N48N_MAX_IBS ||
        (info.flags & (N48N_INFO_HUNG | N48N_INFO_NATIVE_BOOT | N48N_INFO_S1B_POSITIVE)) !=
        (N48N_INFO_NATIVE_BOOT | N48N_INFO_S1B_POSITIVE)) { acd_kext_destroy(k); return -1; }
    *out = k; return 0;
}

[[noreturn]] static void hold(const char *why) {
    fprintf(stderr, "FAIL: real-transport %s\nHOLD: retain client, BOs and VA reservations for independent recovery\n", why);
    fflush(nullptr); for (;;) pause();
}
static void require(bool okay, const char *why) { if (!okay) hold(why); }

static void exercise(bool tail) {
    require(!setenv("RADV_DARWIN_BUILD34_IB_TAIL", tail ? "1" : "0", 1), "local policy selection");
    acd_device_handle dev = nullptr; uint32_t major = 0, minor = 0;
    require(!acd_device_initialize(&major, &minor, &dev) && dev, "real core initialization refused");
    uint32_t abiMinor = 0; struct acd_kext *k = acd_device_kext(dev, &abiMinor);
    require(k && abiMinor == 12, "core ABI");
    uint64_t first = 0, last = 0;
    require(!acd_va_range_query(dev, amdgpu_gpu_va_range_general, &first, &last) &&
        first >= 0x10000 && !(first & 4095) && last > first && last - first >= arenaBytes && last <= 0x800000000000ull,
        "canned VA geometry");
    // Request the same deterministic payload VA for both modes. The tail gets
    // a distinct reservation from the same manager during core creation.
    amdgpu_va_handle range = nullptr; uint64_t va = 0;
    require(!acd_va_range_alloc(dev, amdgpu_gpu_va_range_general, arenaBytes, 4096, first, &va, &range, 0) && va == first,
        "payload reservation");
    union drm_amdgpu_ctx ctx{}; ctx.in.op = AMDGPU_CTX_OP_ALLOC_CTX;
    require(!acd_ioctl(dev, DRM_AMDGPU_CTX, &ctx, sizeof(ctx)), "context allocation");
    const uint32_t context = ctx.out.alloc.ctx_id;
    require(context && context <= 64 && !ctx.out.alloc._pad && !ctx.out.state.hangs && !ctx.out.state.reset_status,
        "context identity");
    amdgpu_bo_alloc_request create{}; create.alloc_size = arenaBytes; create.phys_alignment = 4096;
    create.preferred_heap = AMDGPU_GEM_DOMAIN_GTT; create.flags = AMDGPU_GEM_CREATE_CPU_ACCESS_REQUIRED;
    amdgpu_bo_handle bo = nullptr;
    require(!acd_bo_alloc(dev, &create, &bo) && bo, "payload BO allocation");
    uint32_t handle = 0;
    require(!acd_bo_export(dev, bo, amdgpu_bo_handle_type_kms, &handle) && handle && handle < N48N_MAX_BOS, "payload BO identity");
    void *cpu = nullptr;
    require(!acd_bo_cpu_map(dev, bo, &cpu) && cpu && !(reinterpret_cast<uintptr_t>(cpu) & 4095), "payload CPU mapping");
    drm_amdgpu_gem_va map{}; map.handle = handle; map.operation = AMDGPU_VA_OP_MAP;
    map.flags = AMDGPU_VM_PAGE_EXECUTABLE; map.va_address = va; map.map_size = arenaBytes;
    require(!acd_ioctl(dev, DRM_AMDGPU_GEM_VA, &map, sizeof(map)), "payload GPU mapping");
    uint32_t packets[2][80]{};
    for (unsigned pass = 0; pass < 2; ++pass) {
        const uint32_t pattern[4] = {0x7800c0deu ^ pass, 0x13579bdfu + pass, 0x2468ace0u ^ (pass << 16), 0xc001d00du - pass};
        require(phxGfx11DispatchCommands(packets[pass], 80, va, va + 0x2010, pattern) == PHX_SHADER_DISPATCH_DWORDS,
            "dispatch packet construction");
        packets[pass][78] = packets[pass][79] = 0xffff1000u;
    }
    uint8_t expected[arenaBytes]; memset(expected, 0xa5, arenaBytes); memset(expected, 0, 8192);
    memcpy(expected, phxGfx11ClearShader, sizeof(phxGfx11ClearShader));
    memcpy(expected + 0x1000, packets[0], sizeof(packets[0]));
    memcpy(expected + 0x1200, packets[1], sizeof(packets[1]));
    const uint32_t nop[8] = {0xc0061000u, 0, 0, 0, 0, 0, 0, 0};
    memcpy(expected + 0x1400, nop, sizeof(nop)); // guarded, never submitted from this arena
    memcpy(cpu, expected, arenaBytes);
    uint64_t previous = 0;
    for (unsigned pass = 0; pass < 2; ++pass) {
        const uint32_t pattern[4] = {0x7800c0deu ^ pass, 0x13579bdfu + pass, 0x2468ace0u ^ (pass << 16), 0xc001d00du - pass};
        if (pass) { memcpy(expected + 0x1000, packets[pass], sizeof(packets[pass]));
            memcpy(static_cast<uint8_t *>(cpu) + 0x1000, packets[pass], sizeof(packets[pass])); }
        for (unsigned i = 0; i < 256; ++i) {
            const uint32_t poison = ~pattern[i & 3];
            memcpy(static_cast<uint8_t *>(cpu) + 0x2010 + i * 4, &poison, 4);
            memcpy(expected + 0x2010 + i * 4, &pattern[i & 3], 4);
        }
        __sync_synchronize();
        drm_amdgpu_cs_chunk_ib ib{}; ib.va_start = va + 0x1000; ib.ib_bytes = sizeof(packets[0]); ib.ip_type = AMDGPU_HW_IP_COMPUTE;
        drm_amdgpu_cs_chunk chunk{}; chunk.chunk_id = AMDGPU_CHUNK_ID_IB; chunk.length_dw = sizeof(ib) / 4;
        chunk.chunk_data = reinterpret_cast<uintptr_t>(&ib);
        const uint64_t pointer = reinterpret_cast<uintptr_t>(&chunk);
        union drm_amdgpu_cs cs{}; cs.in.ctx_id = context; cs.in.num_chunks = 1; cs.in.chunks = reinterpret_cast<uintptr_t>(&pointer);
        require(!acd_ioctl(dev, DRM_AMDGPU_CS, &cs, sizeof(cs)), "real CS submission");
        const uint64_t seq = cs.out.handle;
        require(seq && seq != N48N_SEQ_LAST && seq > previous, "submitted sequence");
        const uint64_t budgets[] = {0, 50000, N48N_WAIT_CAP_NS};
        bool busy = true; acd_wait_status status{}; mach_timebase_info_data_t tb{};
        require(mach_timebase_info(&tb) == KERN_SUCCESS && tb.numer && tb.denom, "clock scale");
        for (uint64_t budget : budgets) {
            const uint64_t start = mach_absolute_time();
            require(!acd_kext_wait_seq(k, seq, budget, &busy, &status), "retirement wait");
            const uint64_t elapsed = static_cast<uint64_t>((__uint128_t)(mach_absolute_time() - start) * tb.numer / tb.denom);
            printf("{\"pass\":%u,\"budget_ns\":%llu,\"busy\":%u,\"elapsed_ns\":%llu}\n", pass,
                (unsigned long long)budget, busy ? 1u : 0u, (unsigned long long)elapsed); fflush(stdout);
            if (!busy) break;
        }
        require(!busy && status.retired >= seq && status.retired != N48N_SEQ_LAST && status.emitted == seq, "positive retirement");
        __sync_synchronize();
        const volatile uint8_t *actual = static_cast<const volatile uint8_t *>(cpu);
        for (size_t i = 0; i < arenaBytes; ++i) if (actual[i] != expected[i]) {
            fprintf(stderr, "FAIL: native shader output/code/IB/guard mismatch at byte %zu (pass=%u actual=0x%02x expected=0x%02x)\n",
                i, pass, static_cast<unsigned>(actual[i]), static_cast<unsigned>(expected[i]));
            hold("whole-arena verification");
        }
        previous = seq; usleep(250000);
    }
    require(!acd_bo_cpu_unmap(dev, bo), "payload CPU unmap");
    map.operation = AMDGPU_VA_OP_UNMAP; map.flags = 0;
    require(!acd_ioctl(dev, DRM_AMDGPU_GEM_VA, &map, sizeof(map)), "payload GPU unmap");
    require(!acd_bo_free(dev, bo), "payload BO free");
    ctx = {}; ctx.in.op = AMDGPU_CTX_OP_FREE_CTX; ctx.in.ctx_id = context;
    require(!acd_ioctl(dev, DRM_AMDGPU_CTX, &ctx, sizeof(ctx)), "context free");
    require(!ctx.out.state.flags && !ctx.out.state.hangs && !ctx.out.state.reset_status, "context release response");
    require(!amdgpu_va_range_free(range), "payload reservation release");
    acd_device_get_sync_provider(dev)->finalize(acd_device_get_sync_provider(dev));
    acd_device_deinitialize(dev); // actual tail retirement/lifetime guard
    require(opens == 1 && closes == 1 && !closeFailed, "connection teardown");
}

int main(int argc, char **argv) {
    const bool check = argc == 2 && !strcmp(argv[1], "--check");
    const bool single = argc == 2 && !strcmp(argv[1], "--run-single");
    const bool tail = argc == 2 && !strcmp(argv[1], "--run-tail");
    if (!check && !single && !tail) { fputs("usage: build34-radv-ib-tail-probe --check|--run-single|--run-tail\n", stderr); return 64; }
    utsname host{};
    if (uname(&host) || strcmp(host.sysname, "Darwin") || strcmp(host.machine, "x86_64") || strncmp(host.release, "25.", 3)) return 4;
    extern char **environ;
    for (char **e = environ; *e; ++e) if (!strncmp(*e, "RADV_", 5)) { fputs("REFUSED: inherited RADV override\n", stderr); return 4; }
    if (check) {
        struct acd_kext *k = nullptr;
        if (acd_kext_open_iokit(&k)) return 4;
        acd_kext_destroy(k);
        if (closes != 1 || closeFailed) return 74;
        puts("CHECK: build34 real-transport identity and ABI readiness only; no GPU work submitted"); return 0;
    }
    exercise(tail);
    printf("TRANSPORT-PASS: original34 policy=%s; real Mesa core and CS; two guarded dispatches; no desktop acceptance\n", tail ? "tail" : "single");
    return 0;
}
