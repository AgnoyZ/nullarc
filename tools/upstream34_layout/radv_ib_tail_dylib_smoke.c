/* SPDX-License-Identifier: MIT */
#include <CoreFoundation/CoreFoundation.h>
#include <IOKit/IOKitLib.h>
#include <dlfcn.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdatomic.h>

#ifdef PHX34_SMOKE_GUARD
static atomic_uint blocked;

unsigned phx34_smoke_blocked_count(void) { return atomic_load(&blocked); }
void phx34_smoke_reset(void) { atomic_store(&blocked, 0); }

static io_service_t deny_match(mach_port_t port, CFDictionaryRef matching)
{
    (void)port;
    ++blocked;
    if (matching) CFRelease(matching);
    return IO_OBJECT_NULL;
}

static kern_return_t deny_matches(mach_port_t port, CFDictionaryRef matching, io_iterator_t *iterator)
{
    (void)port;
    ++blocked;
    if (matching) CFRelease(matching);
    if (iterator) *iterator = IO_OBJECT_NULL;
    return kIOReturnNotPermitted;
}

static kern_return_t deny_open(io_service_t service, task_port_t task, uint32_t type, io_connect_t *connect)
{
    (void)service; (void)task; (void)type;
    ++blocked;
    if (connect) *connect = IO_OBJECT_NULL;
    return kIOReturnNotPermitted;
}

static kern_return_t deny_call(mach_port_t connection, uint32_t selector,
    const uint64_t *input, uint32_t input_count, const void *structure, size_t structure_size,
    uint64_t *output, uint32_t *output_count, void *result, size_t *result_size)
{
    (void)connection; (void)selector; (void)input; (void)input_count; (void)structure;
    (void)structure_size; (void)output; (void)output_count; (void)result; (void)result_size;
    ++blocked;
    return kIOReturnNotPermitted;
}

static kern_return_t deny_map(io_connect_t connection, uint32_t memory, task_port_t task,
    mach_vm_address_t *address, mach_vm_size_t *size, IOOptionBits options)
{
    (void)connection; (void)memory; (void)task; (void)address; (void)size; (void)options;
    ++blocked;
    return kIOReturnNotPermitted;
}

static kern_return_t deny_unmap(io_connect_t connection, uint32_t memory, task_port_t task,
    mach_vm_address_t address)
{
    (void)connection; (void)memory; (void)task; (void)address;
    ++blocked;
    return kIOReturnNotPermitted;
}

static kern_return_t deny_close(io_connect_t connection)
{
    (void)connection;
    ++blocked;
    return kIOReturnNotPermitted;
}

#define INTERPOSE(replacement, original) \
    __attribute__((used)) static const struct { const void *replace, *original; } \
    pair_##original __attribute__((section("__DATA,__interpose"))) = \
    { (const void *)(uintptr_t)&replacement, (const void *)(uintptr_t)&original }

INTERPOSE(deny_match, IOServiceGetMatchingService);
INTERPOSE(deny_matches, IOServiceGetMatchingServices);
INTERPOSE(deny_open, IOServiceOpen);
INTERPOSE(deny_call, IOConnectCallMethod);
INTERPOSE(deny_map, IOConnectMapMemory64);
INTERPOSE(deny_unmap, IOConnectUnmapMemory64);
INTERPOSE(deny_close, IOServiceClose);

#else
extern unsigned phx34_smoke_blocked_count(void);
extern void phx34_smoke_reset(void);

int main(int argc, char **argv)
{
    if (argc != 2) return 64;
    io_connect_t connection = IO_OBJECT_NULL;
    if (phx34_smoke_blocked_count() ||
        IOServiceOpen(IO_OBJECT_NULL, mach_task_self(), 0, &connection) != kIOReturnNotPermitted ||
        connection != IO_OBJECT_NULL || phx34_smoke_blocked_count() != 1) {
        fputs("FAIL: IOKit guard unavailable; target was not loaded\n", stderr);
        return 6;
    }
    phx34_smoke_reset();
    void *library = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
    if (!library) {
        fputs("FAIL: runtime could not be loaded\n", stderr);
        return 2;
    }
    int (*set_service)(const char *) = (int (*)(const char *))dlsym(library, "radv_darwin_set_service_class");
    const int exports = set_service && dlsym(library, "vk_icdGetInstanceProcAddr") &&
        dlsym(library, "vk_icdNegotiateLoaderICDInterfaceVersion");
    const int policy = exports && set_service("PhxBringup") == 0 &&
        set_service("Navi48Bringup") == -EINVAL && set_service("Navi48Accelerator") == -EINVAL;
    if (dlclose(library)) return 3;
    if (phx34_smoke_blocked_count()) {
        fprintf(stderr, "FAIL: unexpected IOKit activity blocked (%u calls)\n", phx34_smoke_blocked_count());
        return 4;
    }
    if (!policy) {
        fputs("FAIL: required exports or Phoenix service policy missing\n", stderr);
        return 5;
    }
    puts("{\"dylib_loaded\":true,\"guard_self_test\":true,\"required_exports\":true,\"Phoenix_service_policy\":true,"
         "\"IOKit_calls\":0,\"physical_device_enumeration\":false,\"GPU_executed\":false}");
    return 0;
}
#endif
