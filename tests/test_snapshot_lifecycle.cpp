// Actual reader -> provider creation -> client lifecycle/dispatcher; fake OS only.
#include <IOKit/IOKitLib.h>
#include "PhxNativeABI.h"
#include "PhxAllocationDiagnostic.hpp"
#include "PhxDesktopHandoff.h"
#include <cassert>
#include <cstdlib>
#include <cstring>
#include <map>
#include <string>
#include <vector>
using IOReturn = kern_return_t;
using UInt32 = uint32_t;
using SInt32 = int32_t;
using task_t = void *;
enum { kIOReturnSuccess, kIOReturnBadArgument, kIOReturnNotReady, kIOReturnUnsupported,
       kIOReturnNotPrivileged, kIOReturnNoMemory, kIOReturnExclusiveAccess };
static std::string test;
static unsigned heapCalls{}, objectCalls{}, objectsFreed{}, locksFreed{}, registrations{};
static unsigned detaches{}, terminations{}, opens{}, calls{}, closes{}, releases{};
static std::map<void *, size_t> heap;
static std::vector<unsigned> held;
[[noreturn]] static void forbidden(const char *) { std::abort(); }
struct IOLock { unsigned rank{1}; bool held{}; };
static IOLock *IOLockAlloc() {
    return test == "lock-allocation-failure" ? nullptr : new IOLock;
}
static void IOLockLock(IOLock *p) {
    assert(p && !p->held && (held.empty() || held.back() < p->rank));
    p->held = true; held.push_back(p->rank);
}
static void IOLockUnlock(IOLock *p) {
    assert(p && p->held && !held.empty() && held.back() == p->rank);
    p->held = false; held.pop_back();
}
static void IOLockFree(IOLock *p) { assert(p && !p->held); ++locksFreed; delete p; }
static void *IOMallocZero(size_t bytes) {
    ++heapCalls;
    if ((test == "buffer-allocation-failure" && heapCalls == 1) ||
        (test == "maps-allocation-failure" && heapCalls == 2)) return nullptr;
    void *p = std::calloc(1, bytes); assert(p); heap.emplace(p, bytes); return p;
}
static void IOFree(void *p, size_t bytes) {
    assert(heap.count(p) == 1 && heap.at(p) == bytes);
    heap.erase(p); std::free(p);
}
template<class T> static bool OSCompareAndSwap(int old, int value, volatile T *p) {
    if (*p != static_cast<T>(old)) return false;
    *p = static_cast<T>(value); return true;
}
static volatile UInt32 gSysctlUp{};
static int sysctl__debug_phxbos_flush, sysctl__debug_phxbos_flush_bytes,
    sysctl__debug_phxbos_handles_high, sysctl__debug_phxbos_handles_full,
    sysctl__debug_phx_hang_ms, sysctl__debug_phx_hang_kills;
static void sysctl_register_oid(int *) { ++registrations; }
static constexpr const char *kIOClientPrivilegeAdministrator = "administrator";
static void IOLog(const char *, ...) { forbidden("snapshot log"); }
struct OSObject { virtual ~OSObject() = default; };
struct IOService : OSObject {};
struct IOUserClient : IOService {
    bool baseFreed{};
    bool initWithTask(task_t, void *, UInt32) { return test != "base-init-failure"; }
    bool attach(IOService *) { return test != "attach-failure"; }
    bool start(IOService *) { return test != "start-failure"; }
    void detach(IOService *) { ++detaches; }
    void terminate() { ++terminations; }
    virtual IOReturn clientClose() = 0;
    virtual void free() { assert(!baseFreed); baseFreed = true; ++objectsFreed; }
    void release() { free(); assert(baseFreed); delete this; }
    static IOReturn clientHasPrivilege(task_t, const char *name) {
        assert(std::strcmp(name, "administrator") == 0);
        return test == "unprivileged" ? kIOReturnNotPrivileged : kIOReturnSuccess;
    }
};
#define OSTypeAlloc(type) allocateObject<type>()
#define OSDynamicCast(type, p) dynamic_cast<type *>(p)
template<class T> static T *allocateObject() {
    ++objectCalls; return test == "client-allocation-failure" ? nullptr : new T;
}
struct IOMemoryDescriptor {};
struct IOExternalMethodDispatch {};
struct IOExternalMethodArguments {
    uint32_t scalarInputCount{}, scalarOutputCount{}, structureInputSize{}, structureOutputSize{};
    const uint64_t *scalarInput{};
    void *structureInputDescriptor{}, *structureOutputDescriptor{}, *structureOutput{};
};
#include "lifecycle-constants.inc"
#include "lifecycle-shared.inc"
class PhxBringup : public IOService {
public:
    IOLock mutex{2}; IOLock *gpuLock{&mutex};
#include "lifecycle-state.inc"
    // Foreign reservation sentinel is a fake; any cleanup entry is forbidden.
    const void *foreignReservation{};
    uint64_t foreignState{};
    IOReturn newUserClient(task_t, void *, UInt32, IOUserClient **);
    bool claimSession(); void releaseSession();
    IOReturn copyAllocationSnapshot(phxn_allocation_snapshot *);
    uint32_t vmidAlloc() { forbidden("GPU context allocation"); }
    void deferClient(uint32_t, uint64_t, PhxRetiredBuffers *) { forbidden("GPU context retirement"); }
    void abandonDesktop(const void *) { forbidden("desktop cleanup"); }
    IOReturn lockDebugMutation(const void *, uint32_t) { forbidden("mutation lock"); }
    void unlockDebugMutation() { forbidden("mutation lock"); }
};
class IOAccelPhxNativeClient : public IOUserClient {
public:
#include "lifecycle-client.inc"
    bool initWithTask(task_t, void *, UInt32);
    bool start(IOService *);
    IOReturn clientClose() override;
    void free() override;
    void freeAll(); void closeResources();
    IOReturn externalMethod(uint32_t, IOExternalMethodArguments *, IOExternalMethodDispatch *, OSObject *, void *);
    IOReturn doAllocationSnapshot(IOExternalMethodArguments *);
    void boRelease(Bo &) { forbidden("BO cleanup"); }
    void reapPending() { forbidden("pending reaper"); }
#include "lifecycle-stubs.inc"
};
#include "lifecycle-methods.inc"
#define main allocationSnapshotMain
#include "../tools/allocation_snapshot.cpp"
#undef main
static PhxBringup service;
static IOAccelPhxNativeClient *client{};
mach_port_t mach_task_self() { return 7; }
CFMutableDictionaryRef IOServiceMatching(const char *name) {
    assert(std::strcmp(name, "PhxBringup") == 0); return nullptr;
}
io_service_t IOServiceGetMatchingService(mach_port_t port, CFMutableDictionaryRef) {
    assert(port == kIOMainPortDefault); return 8;
}
kern_return_t IOObjectRelease(io_object_t object) { assert(object == 8); ++releases; return 0; }
kern_return_t IOServiceOpen(io_service_t object, mach_port_t task, uint32_t type, io_connect_t *out) {
    assert(object == 8 && task == 7 && type == PHXN_UC_TYPE && out && !client); ++opens;
    IOUserClient *created = nullptr;
    const auto result = service.newUserClient(reinterpret_cast<void *>(uintptr_t(task)), nullptr, type, &created);
    if (result == kIOReturnSuccess) {
        client = dynamic_cast<IOAccelPhxNativeClient *>(created); assert(client);
        assert(!client->hello && !client->closed && !client->vmid && !client->desktopReservationOwned);
        assert(client->owner == &service && client->bufferStorage && client->bos && client->maps && client->lock);
        for (const auto &entry : heap) {
            const auto *bytes = static_cast<const unsigned char *>(entry.first);
            for (size_t i = 0; i < entry.second; ++i) assert(!bytes[i]);
        }
        *out = 9;
    } else assert(!created && !*out);
    return result;
}
kern_return_t IOConnectCallMethod(io_connect_t connection, uint32_t selector,
    const uint64_t *in, uint32_t count, const void *data, size_t size,
    uint64_t *scalars, uint32_t *scalarCount, void *out, size_t *bytes) {
    assert(client && connection == 9 && selector == PHXN_SEL_ALLOCATION_SNAPSHOT);
    assert(in && count == 1 && *in == PHXN_ALLOCATION_SNAPSHOT_VERSION && !data && !size);
    assert(!scalars && scalarCount && !*scalarCount && out && bytes && *bytes == sizeof(phxn_allocation_snapshot));
    ++calls;
    IOExternalMethodArguments a;
    a.scalarInput = in; a.scalarInputCount = count;
    a.structureOutput = out; a.structureOutputSize = static_cast<uint32_t>(*bytes);
    const auto result = client->externalMethod(selector, &a, nullptr, nullptr, nullptr);
    assert(!client->hello && !client->vmid && !client->desktopReservationOwned && held.empty());
    *scalarCount = a.scalarOutputCount; *bytes = a.structureOutputSize;
    return result;
}
kern_return_t IOServiceClose(io_connect_t connection) {
    assert(client && connection == 9); ++closes;
    if (test != "destructor-only") {
        assert(client->clientClose() == kIOReturnSuccess);
        if (test == "repeat-close") assert(client->clientClose() == kIOReturnSuccess);
        assert(client->closed && !client->sessionClaimed);
    }
    client->release(); client = nullptr; return KERN_SUCCESS;
}
int main(int argc, char **argv) {
    assert(argc == 2); test = argv[1];
    const bool existing = test == "existing-session" || test == "foreign-reservation";
    service.sessionOpen = existing ? 1 : 0;
    if (test == "foreign-reservation") { service.foreignReservation = &argc; service.foreignState = 0x51ea1; }
    if (test == "missing-gpu-lock") service.gpuLock = nullptr;
    if (test == "samples") service.allocationHistory.record(phxAllocationRefusal(PHXN_ALLOC_HOST_PREPARE, 2, 4096));
    phxn_allocation_snapshot before{}, after{};
    service.allocationHistory.copy(&before, PHX_KEXT_BUILD);
    const bool openFailure = test.size() >= 8 && test.substr(test.size() - 8) == "-failure";
    const int expected = openFailure ? 77 : test == "unprivileged" || test == "missing-gpu-lock" ? 74 : 0;
    const unsigned repeat = test == "repeated-readers" ? 2 : 1;
    for (unsigned i = 0; i < repeat; ++i) {
        assert(allocationSnapshotMain(1, nullptr) == expected);
        assert(!client && heap.empty() && held.empty() && !service.mutex.held);
        assert(service.sessionOpen == (existing ? 1 : 0));
        assert(service.foreignReservation == (test == "foreign-reservation" ? &argc : nullptr));
        assert(service.foreignState == (test == "foreign-reservation" ? 0x51ea1u : 0u));
        service.allocationHistory.copy(&after, PHX_KEXT_BUILD);
        assert(std::memcmp(&before, &after, sizeof before) == 0);
    }
    assert(registrations == 6 && gSysctlUp == 1 && opens == repeat && releases == repeat && objectCalls == repeat);
    assert(objectsFreed == (test == "client-allocation-failure" ? 0 : repeat));
    assert(locksFreed == (test == "client-allocation-failure" || test == "base-init-failure" ||
                         test == "lock-allocation-failure" ? 0 : repeat));
    assert(detaches == (test == "start-failure" ? 1u : 0u));
    assert(calls == (openFailure ? 0 : repeat) && closes == calls);
    assert(terminations == (openFailure || test == "destructor-only" ? 0 : test == "repeat-close" ? 2 : repeat));
}
