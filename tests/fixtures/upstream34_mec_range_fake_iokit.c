/* SPDX-License-Identifier: MIT OR GPL-2.0-only
 * Actual generated CLI, synthetic registers, real CF objects; never link IOKit.
 * Stop at the first scheduler-MQD write: no firmware/completion/GPU model.
 */
#include <CoreFoundation/CoreFoundation.h>
#include <IOKit/IOKitLib.h>
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define main candidate_main
#include PHX34_SOURCE
#undef main
#undef IOConnectCallScalarMethod
#undef IOConnectCallMethod

const mach_port_t kIOMainPortDefault = 0;
static const char *fault;
static uint32_t registers[0x20000];
static unsigned lookups, opens, hellos, kiq_reads, kiq_register_writes, kiq_vram_writes;
static unsigned range_writes, range_reads, range_events, scheduler_entered, closes;
static int is(const char *s) { return !strcmp(fault, s); }
static int at(const char *name, unsigned step) {
    char text[64]; snprintf(text, sizeof(text), "%s-%u", name, step); return is(text);
}
static void require_kiq_prefix(void) {
    if (kiq_reads != 2 || kiq_register_writes != 23 || kiq_vram_writes != 1598) {
        fprintf(stderr, "fake KIQ prefix mismatch: reads=%u registers=%u VRAM=%u\n",
                kiq_reads, kiq_register_writes, kiq_vram_writes);
        exit(76);
    }
}
static void report(void) {
    printf("fake-mec-range {\"lookups\":%u,\"opens\":%u,\"hellos\":%u,"
           "\"kiq_reads\":%u,\"kiq_register_writes\":%u,\"kiq_vram_writes\":%u,"
           "\"range_writes\":%u,\"range_reads\":%u,\"range_events\":%u,"
           "\"scheduler_entered\":%u,\"closes\":%u}\n", lookups, opens, hellos,
           kiq_reads, kiq_register_writes, kiq_vram_writes, range_writes,
           range_reads, range_events, scheduler_entered, closes);
}
CFMutableDictionaryRef IOServiceMatching(const char *name) {
    assert(!strcmp(name, "PhxBringup"));
    return CFDictionaryCreateMutable(NULL, 0, NULL, NULL);
}
io_service_t IOServiceGetMatchingService(mach_port_t port, CFDictionaryRef matching) {
    (void)port; CFRelease(matching); ++lookups; return is("no-service") ? 0 : 1;
}
CFTypeRef IORegistryEntryCreateCFProperty(io_registry_entry_t entry, CFStringRef key,
                                         CFAllocatorRef allocator, IOOptionBits options) {
    assert(entry == 1); (void)allocator; (void)options;
    int64_t value = 0;
    if (CFEqual(key, CFSTR("phx-build")))
        value = is("wrong-build") ? 40 : is("wrong-build41") ? 41 : is("wrong-build42") ? 42 : 34;
    if (CFEqual(key, CFSTR("phx-fb-mc-base"))) value = is("wrong-mc") ? 0x8100000000ll : 0x8000000000ll;
    if (CFEqual(key, CFSTR("phx-fb-phys"))) {
        if (is("missing-geometry")) return NULL;
        if (is("wrong-type")) return CFRetain(CFSTR("synthetic"));
        value = 0x600000000ll;
        if (is("zero-physical")) value = 0;
        if (is("negative-physical")) value = -1;
        if (is("unaligned-physical")) ++value;
        if (is("overflow-physical")) value = 0xfffffe000000ll;
    }
    if (CFEqual(key, CFSTR("phx-fb-size"))) value = is("small-vram") ? 0x8000000ll : 0x100000000ll;
    if (CFEqual(key, CFSTR("phx-fb-aper-len"))) value = is("small-aperture") ? 0x8000000ll : 0x10000000ll;
    return CFNumberCreate(NULL, kCFNumberSInt64Type, &value);
}
kern_return_t IOObjectRelease(io_object_t object) { assert(object == 1); return 0; }
kern_return_t IOServiceOpen(io_service_t service, task_port_t task, uint32_t type, io_connect_t *out) {
    (void)task; assert(service == 1 && type == 0x4e34384e); ++opens; *out = 2;
    return is("open-status") ? kIOReturnError : 0;
}
kern_return_t IOServiceClose(io_connect_t connection) { assert(connection == 2); ++closes; return 0; }
kern_return_t IOConnectCallScalarMethod(mach_port_t connection, uint32_t selector,
    const uint64_t *input, uint32_t ni, uint64_t *output, uint32_t *no) {
    assert(connection == 2 && input);
    if (output && no) memset(output, 0, *no * sizeof(*output));
    if (selector == 0) {
        assert(ni == 2 && input[0] == 1 && output && *no == 4); ++hellos;
        output[0] = is("hello-ABI") ? 1 : 1 | (12u << 16);
        output[1] = is("hello-build") ? 40 : is("hello-build41") ? 41 : is("hello-build42") ? 42 : 34;
        if (is("hello-short")) --*no;
        if (is("hello-long")) ++*no;
        return is("hello-status") ? kIOReturnError : 0;
    }
    if (selector == 109) {
        assert(ni == 2 && !output && !no);
        if (input[0] == 0x2512000) {
            assert(range_events == (PHX34_MEC_RANGE_TRIAL ? 4u : 0u));
            assert(range_writes == (PHX34_MEC_RANGE_TRIAL ? 2u : 0u));
            assert(range_reads == (PHX34_MEC_RANGE_TRIAL ? 2u : 0u));
            require_kiq_prefix();
            ++scheduler_entered;
            exit(0); /* This fixture does not model the scheduler or GPU. */
        }
        assert(input[0] >= 0x2500000 && input[0] < 0x2504000 && !range_events);
        ++kiq_vram_writes;
        return at("kiq-vram-status", kiq_vram_writes) ? kIOReturnError : 0;
    }
    assert(selector == 108 && ni == 2 && output && *no == 1);
    const uint32_t reg = (uint32_t)input[0], value = (uint32_t)input[1];
    assert(reg < sizeof(registers) / sizeof(registers[0]));
    if (reg == 0x305d || reg == 0x305c) {
        assert(PHX34_MEC_RANGE_TRIAL); require_kiq_prefix();
        assert(range_events == 2 * range_writes && range_writes < 2);
        assert(reg == (range_writes ? 0x305c : 0x305d));
        assert(value == (range_writes ? 0 : 0x450));
        ++range_events; ++range_writes;
        if (at("write-status", range_writes)) return kIOReturnError;
        registers[reg] = value; output[0] = value;
        if (at("write-short", range_writes)) --*no;
        if (at("write-long", range_writes)) ++*no;
        if (at("write-bad", range_writes)) output[0] ^= 4;
        if (at("write-ones", range_writes)) output[0] = UINT32_MAX;
        return 0;
    }
    assert(!range_events); ++kiq_register_writes; registers[reg] = value; output[0] = value;
    return at("kiq-register-status", kiq_register_writes) ? kIOReturnError : 0;
}
kern_return_t IOConnectCallMethod(mach_port_t connection, uint32_t selector,
    const uint64_t *input, uint32_t ni, const void *data, size_t size,
    uint64_t *output, uint32_t *no, void *bytes, size_t *nb) {
    assert(connection == 2 && selector == 2 && ni == 3 && input && input[1] == 1);
    assert(!data && !size && !output && !no && bytes && *nb == 4);
    uint32_t reg = (uint32_t)input[0];
    assert(reg < sizeof(registers) / sizeof(registers[0]));
    uint32_t value = registers[reg];
    if (reg == 0x305d || reg == 0x305c) {
        assert(PHX34_MEC_RANGE_TRIAL && range_events == 2 * range_reads + 1 && range_reads < 2);
        assert(reg == (range_reads ? 0x305c : 0x305d));
        ++range_events; ++range_reads;
        if (at("read-status", range_reads)) return kIOReturnError;
        if (at("read-short", range_reads)) *nb = 0;
        if (at("read-long", range_reads)) *nb = 8;
        if (at("read-bad", range_reads)) value ^= 4;
        if (at("read-ones", range_reads)) value = UINT32_MAX;
    } else {
        assert(reg == 0xa98a && !range_events); ++kiq_reads;
        if (at("kiq-read-status", kiq_reads)) return kIOReturnError;
    }
    memcpy(bytes, &value, 4); return 0;
}
int main(int argc, char **argv) {
    assert(argc == 2); fault = argv[1]; atexit(report);
    registers[0x305c] = 0x110; registers[0x305d] = 0xffc;
    char *args[] = {"fake-candidate", "kiqsched", "extra", NULL};
    int count = 2;
    if (is("arg-missing")) count = 1;
    if (is("arg-extra")) count = 3;
    if (is("arg-null")) args[1] = NULL;
    if (is("arg-layout")) args[1] = "layout";
    if (is("arg-sched")) args[1] = "sched";
    if (is("arg-viakiq")) args[1] = "viakiq";
    if (is("arg-all")) args[1] = "all";
    if (is("arg-gart")) args[1] = "gart";
    if (is("arg-gfx")) args[1] = "gfx";
    return candidate_main(count, args);
}
