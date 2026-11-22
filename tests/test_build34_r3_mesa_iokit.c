#include <IOKit/IOKitLib.h>
#include <stdlib.h>

extern kern_return_t phx34_fixture_method(mach_port_t, uint32_t, const uint64_t *, uint32_t, const void *, size_t,
                                          uint64_t *, uint32_t *, void *, size_t *);
extern kern_return_t phx34_fixture_close(io_connect_t);

const mach_port_t kIOMainPortDefault = MACH_PORT_NULL;

kern_return_t
IOConnectCallMethod(mach_port_t conn, uint32_t selector, const uint64_t *scalars, uint32_t scalar_count,
                    const void *structure, size_t structure_size, uint64_t *scalar_out, uint32_t *scalar_out_count,
                    void *structure_out, size_t *structure_out_size)
{
    return phx34_fixture_method(conn, selector, scalars, scalar_count, structure, structure_size,
                               scalar_out, scalar_out_count, structure_out, structure_out_size);
}

kern_return_t IOServiceClose(io_connect_t conn) { return phx34_fixture_close(conn); }
#ifdef PHX34_TEST_EXACT_OPEN
extern kern_return_t phx34_fixture_open(io_service_t, task_port_t, uint32_t, io_connect_t *);
extern io_service_t phx34_fixture_lookup(mach_port_t, CFDictionaryRef);
extern CFMutableDictionaryRef phx34_fixture_match(const char *);
extern kern_return_t phx34_fixture_release(io_object_t);

kern_return_t IOServiceOpen(io_service_t svc, task_port_t task, uint32_t type, io_connect_t *out)
{
    return phx34_fixture_open(svc, task, type, out);
}

io_service_t IOServiceGetMatchingService(mach_port_t port, CFDictionaryRef match)
{
    return phx34_fixture_lookup(port, match);
}

CFMutableDictionaryRef IOServiceMatching(const char *name) { return phx34_fixture_match(name); }
kern_return_t IOObjectRelease(io_object_t object) { return phx34_fixture_release(object); }
#else
kern_return_t IOServiceOpen(io_service_t svc, task_port_t task, uint32_t type, io_connect_t *out) { abort(); }
io_service_t IOServiceGetMatchingService(mach_port_t port, CFDictionaryRef match) { abort(); }
CFMutableDictionaryRef IOServiceMatching(const char *name) { abort(); }
kern_return_t IOObjectRelease(io_object_t object) { abort(); }
#endif

kern_return_t
IOConnectMapMemory64(io_connect_t conn, uint32_t type, task_port_t task, mach_vm_address_t *addr,
                     mach_vm_size_t *size, IOOptionBits options)
{
    abort();
}

kern_return_t
IOConnectUnmapMemory64(io_connect_t conn, uint32_t type, task_port_t task, mach_vm_address_t addr)
{
    abort();
}
