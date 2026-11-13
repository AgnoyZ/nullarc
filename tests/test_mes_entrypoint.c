/* Actual current mesboot main, compiled only with fake IOKit. No native IOKit link. */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#define IORegistryEntryCreateCFProperty ignored_default_property
#include <IOKit/IOKitLib.h>
#undef IORegistryEntryCreateCFProperty
static CFTypeRef IORegistryEntryCreateCFProperty(io_registry_entry_t, CFStringRef, CFAllocatorRef, uint32_t);
static int fake_usleep(useconds_t);
#define main mesboot_actual_main
#define usleep fake_usleep
#include "mesboot.c"
#undef main
#undef usleep

static const char *fixture, *fault;
static unsigned lookups, opens, releases, hellos, claims, snapshots, closes;

static void summary(void)
{
    fprintf(stderr, "fake-entrypoint-summary {\"lookups\":%u,\"opens\":%u,\"releases\":%u,"
            "\"hellos\":%u,\"claims\":%u,\"snapshots\":%u,\"closes\":%u}\n",
            lookups, opens, releases, hellos, claims, snapshots, closes);
}

static CFTypeRef IORegistryEntryCreateCFProperty(io_registry_entry_t service, CFStringRef key,
                                                CFAllocatorRef allocator, uint32_t options)
{
    assert(service == 1 && allocator == kCFAllocatorDefault && options == 0 && key);
    if (!strcmp(fixture, "missing")) return NULL;
    const int relocated = !strcmp(fixture, "relocated");
    if (!strcmp(key, "phx-build")) return phxFakePropertyNumber(37);
    if (!strcmp(key, "phx-fb-mc-base")) return phxFakePropertyNumber(relocated ? 0x6000000000ll : 0x8000000000ll);
    if (!strcmp(key, "phx-fb-phys")) return phxFakePropertyNumber(relocated ? 0x300000000ll : 0x6A0000000ll);
    if (!strcmp(key, "phx-fb-size")) return phxFakePropertyNumber(0x10000000ll);
    assert(0);
    return NULL;
}

void *IOServiceMatching(const char *name)
{
    assert(!strcmp(name, "PhxBringup"));
    return (void *)1;
}
io_service_t IOServiceGetMatchingService(mach_port_t port, void *matching)
{
    assert(port == kIOMainPortDefault && matching == (void *)1);
    ++lookups;
    return 1;
}
mach_port_t mach_task_self(void) { return 42; }
kern_return_t IOServiceOpen(io_service_t service, mach_port_t task, uint32_t type, io_connect_t *connection)
{
    assert(service == 1 && task == 42 && type == UC_TYPE && connection);
    ++opens;
    *connection = 7;
    return KERN_SUCCESS;
}
kern_return_t IOObjectRelease(io_service_t service) { assert(service == 1); ++releases; return KERN_SUCCESS; }
kern_return_t IOServiceClose(io_connect_t connection) { assert(connection == 7); ++closes; return KERN_SUCCESS; }

kern_return_t IOConnectCallScalarMethod(io_connect_t connection, uint32_t selector,
    const uint64_t *input, uint32_t input_count, uint64_t *output, uint32_t *output_count)
{
    assert(connection == 7 && input);
    if (selector == SEL_HELLO) {
        assert(input_count == 2 && input[0] == 1 && input[1] == 0 && output && output_count && *output_count == 4);
        ++hellos;
        memset(output, 0, 4 * sizeof(*output));
        output[0] = !strcmp(fault, "hello-abi") ? 2 : input[0];
        if (!strcmp(fault, "hello-short")) --*output_count;
        if (!strcmp(fault, "hello-long")) ++*output_count;
        return !strcmp(fault, "hello-status") ? 5 : KERN_SUCCESS;
    }
    /* Every other scalar selector, including register writes and queue adoption, is forbidden here. */
    assert(selector == 113 && input_count == 1 && input[0] == 1 && !output && !output_count);
    ++claims;
    if (!strcmp(fault, "claim-block")) {
        const char *path = getenv("PHX_FAKE_CLAIM_FIFO");
        assert(path);
        FILE *pipe = fopen(path, "r");
        assert(pipe);
        fputs("fake-claim-waiting-for-input\n", stderr);
        assert(fflush(stderr) == 0);
        assert(fgetc(pipe) == '\n'); /* Fixture FIFO only, not a kernel/GPU hang. */
        assert(fclose(pipe) == 0);
    }
    return !strcmp(fault, "claim-status") ? 5 : KERN_SUCCESS;
}

kern_return_t IOConnectCallMethod(io_connect_t connection, uint32_t selector,
    const uint64_t *input, uint32_t input_count, const void *input_data, size_t input_size,
    uint64_t *output, uint32_t *output_count, void *output_data, size_t *output_size)
{
    assert(connection == 7 && selector == PHX_BOOT_MEMORY_SELECTOR && !input && !input_count);
    assert(!input_data && !input_size && !output && !output_count && output_data && output_size);
    assert(*output_size == sizeof(struct PhxBootMemory));
    ++snapshots;
    /* A deliberate terminal transport refusal stops explicit commands before register/memory activity. */
    return 5;
}
static int fake_usleep(useconds_t delay) { (void)delay; assert(0); return -1; }

int main(int argc, char **argv)
{
    assert(argc >= 4);
    fixture = argv[1];
    fault = argv[2];
    assert(!strcmp(fixture, "reference") || !strcmp(fixture, "relocated") || !strcmp(fixture, "missing"));
    /* Test execution must not inherit the legacy override or experiment switches. */
    assert(!getenv("PHX_LAYOUT_REFERENCE") && !getenv("MESBOOT_MC") && !getenv("ADOPT"));
    assert(atexit(summary) == 0);
    int status = mesboot_actual_main(argc - 2, argv + 2);
    printf("fake-entrypoint-returned=%d\n", status);
    return status;
}
