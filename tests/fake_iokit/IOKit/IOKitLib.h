/* Test-only IOKit declarations. Never use this include path in a native tool build. */
#ifndef PHX_TEST_IOKIT_H
#define PHX_TEST_IOKIT_H
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <string.h>
/* CFBase.h and CFString.h, not the CoreFoundation umbrella: the real <IOKit/IOKitLib.h> stops there too, so a
 * tool that calls CFNumberGetValue() without <CoreFoundation/CFNumber.h> fails here as well as in `macos-kexts`
 * (see tests/fake_iokit/CoreFoundation/CFBase.h). */
#include <CoreFoundation/CFBase.h>
#include <CoreFoundation/CFString.h>
typedef uint32_t io_connect_t;
typedef uint32_t io_service_t;
typedef uint32_t io_registry_entry_t;
typedef uint32_t mach_port_t;
typedef int32_t kern_return_t;
#define KERN_SUCCESS 0
#define kIOMainPortDefault 0
void *IOServiceMatching(const char *name);
io_service_t IOServiceGetMatchingService(mach_port_t port, void *matching);
kern_return_t IOServiceOpen(io_service_t service, mach_port_t task, uint32_t type, io_connect_t *connection);
kern_return_t IOServiceClose(io_connect_t connection);
kern_return_t IOObjectRelease(io_service_t service);
mach_port_t mach_task_self(void);
/* The registry hands back CF objects. The fake only needs a number-like one, and it must not reach into
 * CFNumber.h -- withholding that header is the point of the split (CFBase.h). One slot is enough: every reader
 * takes the value before asking for the next property. */
__attribute__((unused)) static CFTypeRef phxFakePropertyNumber(long long value)
{
    static struct FakeCF store;
    store.kind = (int)PHX_FAKE_CF_NUMBER_KIND;
    store.number = value;
    return &store;
}
/* The registry doubles model the reference machine: they answer with the carve-out that machine's driver
 * publishes (PhxBringup.cpp publishes the same three properties from its own read). A harness that wants to
 * exercise mesboot's refusal path defines PHX_FAKE_CF_WITHHOLD and gets nothing back. */
#ifndef PHX_FAKE_CF_WITHHOLD
__attribute__((unused)) static CFTypeRef IORegistryEntryCreateCFProperty(io_registry_entry_t service, CFStringRef key,
                                                                        CFAllocatorRef allocator, uint32_t options)
{
    (void)service;
    (void)allocator;
    (void)options;
    if (!key) return 0;
    if (!strcmp(key, "phx-fb-mc-base")) return phxFakePropertyNumber(0x8000000000ll);
    if (!strcmp(key, "phx-fb-size")) return phxFakePropertyNumber(0x180000000ll);
    if (!strcmp(key, "phx-fb-phys")) return phxFakePropertyNumber(0x6A0000000ll);
    if (!strcmp(key, "phx-build")) return phxFakePropertyNumber(1);
    return 0;
}
#else
__attribute__((unused)) static CFTypeRef IORegistryEntryCreateCFProperty(io_registry_entry_t service, CFStringRef key,
                                                                        CFAllocatorRef allocator, uint32_t options)
{
    (void)service;
    (void)key;
    (void)allocator;
    (void)options;
    return 0;
}
#endif
kern_return_t IOConnectCallScalarMethod(io_connect_t connection, uint32_t selector,
    const uint64_t *input, uint32_t input_count, uint64_t *output, uint32_t *output_count);
kern_return_t IOConnectCallMethod(io_connect_t connection, uint32_t selector,
    const uint64_t *input, uint32_t input_count, const void *input_data, size_t input_size,
    uint64_t *output, uint32_t *output_count, void *output_data, size_t *output_size);
#endif
