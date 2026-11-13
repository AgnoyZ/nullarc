// Compile the actual reader with an IOKit boundary fake; never open a service.
#include <cassert>
#include <cstring>
#include <string>
#define main allocationSnapshotMain
#include "../tools/allocation_snapshot.cpp"
#undef main
static std::string test;
static unsigned opens{}, calls{}, closes{}, releases{}, matches{};
mach_port_t mach_task_self() { return 7; }
CFMutableDictionaryRef IOServiceMatching(const char *name) {
    assert(std::strcmp(name, "PhxBringup") == 0); ++matches;
    return nullptr;
}
io_service_t IOServiceGetMatchingService(mach_port_t port, CFMutableDictionaryRef) {
    assert(port == kIOMainPortDefault); return test == "no-service" ? 0 : 8;
}
kern_return_t IOObjectRelease(io_object_t service) { assert(service == 8); ++releases; return 0; }
kern_return_t IOServiceOpen(io_service_t service, mach_port_t task, uint32_t type, io_connect_t *out) {
    assert(service == 8 && task == 7 && type == PHXN_UC_TYPE); ++opens; *out = 9;
    return test == "open-refusal" ? 2 : 0;
}
kern_return_t IOServiceClose(io_connect_t connection) {
    assert(connection == 9); ++closes; return test == "close-refusal" ? 2 : 0;
}
kern_return_t IOConnectCallMethod(io_connect_t connection, uint32_t selector,
        const uint64_t *in, uint32_t count, const void *data, size_t size,
        uint64_t *scalars, uint32_t *scalarCount, void *out, size_t *bytes) {
    assert(connection == 9 && selector == PHXN_SEL_ALLOCATION_SNAPSHOT && count == 1 && in && *in == 1);
    assert(!data && !size && !scalars && scalarCount && !*scalarCount && out && *bytes == 3888);
    ++calls;
    PhxAllocationHistory history;
    if (test == "samples") {
        PhxRetirementObservation observation{}; observation.submitted = 5;
        observation.queue[0] = {PhxQueueObservationReason::FutureFence, true, 6, 4, 0, 1};
        history.record(phxAllocationRetirement(PHXN_ALLOC_MAP_INVALID, 0xe00002d5u, 5, 0, observation));
        for (unsigned i = 0; i < 20; ++i)
            history.record(phxAllocationRefusal(PHXN_ALLOC_HOST_PREPARE, 2, 4096));
    }
    auto *snapshot = static_cast<phxn_allocation_snapshot *>(out);
    history.copy(snapshot, 37);
    if (test == "bad-count") snapshot->counts[0] = 1;
    if (test == "bad-total") snapshot->observed = 1;
    if (test == "bad-record" || test == "bad-queue") {
        snapshot->observed = snapshot->counts[0] = 1;
        if (test == "bad-queue") {
            snapshot->records[0][0].ordinal = 1;
            snapshot->records[0][0].queue[0].reason = 15;
        }
    }
    if (test == "short") --*bytes;
    if (test == "long") ++*bytes;
    if (test == "scalars") ++*scalarCount;
    if (test == "version") ++snapshot->version;
    if (test == "reasons") ++snapshot->reason_count;
    if (test == "capacity") ++snapshot->samples_per_reason;
    return test == "request-refusal" ? 2 : 0;
}
int main(int argc, char **argv) {
    assert(argc == 2); test = argv[1];
    const int result = allocationSnapshotMain(test == "arguments" ? 2 : 1, nullptr);
    assert(matches == (test == "arguments" ? 0 : 1));
    if (test == "arguments") assert(result == 64 && !opens && !calls && !closes);
    else if (test == "no-service") assert(result == 69 && !opens && !calls && !closes && !releases);
    else if (test == "open-refusal") assert(result == 77 && opens == 1 && releases == 1 && !calls && !closes);
    else {
        assert(opens == 1 && calls == 1 && closes == 1 && releases == 1);
        assert(result == (test == "empty" || test == "samples" ? 0 : 74));
    }
}
