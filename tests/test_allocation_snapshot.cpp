// Actual dispatcher, snapshot method and service wrappers; CPU-only OS fakes.
#include "PhxNativeABI.h"
#include "PhxAllocationDiagnostic.hpp"
#include <cassert>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <vector>
using IOReturn = uint32_t;
constexpr IOReturn kIOReturnSuccess = 0, kIOReturnBadArgument = 0xe00002c2u,
    kIOReturnNotReady = 0xe00002d8u, kIOReturnUnsupported = 0xe00002c7u,
    kIOReturnNotPrivileged = 0xe00002c1u;
struct IOExternalMethodDispatch {};
struct OSObject {};
struct Lock { unsigned rank; bool held{}; };
static std::vector<unsigned> held;
static void IOLockLock(Lock *lock) {
    assert(lock && !lock->held && (held.empty() || held.back() < lock->rank));
    lock->held = true; held.push_back(lock->rank);
}
static void IOLockUnlock(Lock *lock) {
    assert(lock && lock->held && !held.empty() && held.back() == lock->rank);
    lock->held = false; held.pop_back();
}
struct IOExternalMethodArguments {
    uint32_t scalarInputCount{1}, scalarOutputCount{}, structureInputSize{};
    uint32_t structureOutputSize{sizeof(phxn_allocation_snapshot)};
    void *structureInputDescriptor{}, *structureOutputDescriptor{};
    const uint64_t *scalarInput{};
    void *structureOutput{};
};
// The actual dispatcher references these types only in non-snapshot paths.
#include "snapshot-constants.inc"
#include "PhxDesktopHandoff.h"
static void IOLog(const char *, ...) { assert(false && "snapshot must not log"); }
class PhxBringup {
public:
    Lock mutex{2}; Lock *gpuLock{&mutex};
#include "snapshot-state.inc"
    void recordAllocation(const phxn_allocation_record &);
    IOReturn copyAllocationSnapshot(phxn_allocation_snapshot *);
    IOReturn lockDebugMutation(const void *, uint32_t) { assert(false && "snapshot must bypass mutation lock"); return kIOReturnNotReady; }
    void unlockDebugMutation() { assert(false && "snapshot must bypass mutation lock"); }
};
class IOAccelPhxNativeClient {
public:
    Lock mutex{1}; Lock *lock{&mutex};
    bool closed{}, hello{}, privileged{true}, submitFailureLogged{};
    PhxBringup *owner;
    explicit IOAccelPhxNativeClient(PhxBringup &p) : owner(&p) {}
    void reapPending() { assert(false && "snapshot must bypass reaping"); }
    IOReturn externalMethod(uint32_t, IOExternalMethodArguments *, IOExternalMethodDispatch *, OSObject *, void *);
    IOReturn doAllocationSnapshot(IOExternalMethodArguments *);
#include "snapshot-stubs.inc"
};
#include "snapshot-methods.inc"

int main() {
    unsigned cases = 0;
    PhxBringup service;
    IOAccelPhxNativeClient client(service);
    phxn_allocation_snapshot output{};
    uint64_t version = PHXN_ALLOCATION_SNAPSHOT_VERSION;
    IOExternalMethodArguments request; request.scalarInput = &version; request.structureOutput = &output;
    const auto call = [&](IOExternalMethodArguments *args = nullptr) {
        auto status = client.externalMethod(PHXN_SEL_ALLOCATION_SNAPSHOT, args, nullptr, nullptr, nullptr);
        assert(held.empty() && !client.mutex.held && !service.mutex.held);
        return status;
    };
    // Independent handshake works before and after Hello, with no GPU/readiness state.
    for (bool hello : {false, true}) {
        client.hello = hello;
        assert(call(&request) == kIOReturnSuccess);
        assert(output.version == version && output.kext_build == PHX_KEXT_BUILD);
        assert(output.reason_count == 7 && output.samples_per_reason == 4 && !output.observed);
        phxn_allocation_snapshot expected{};
        expected.version = version; expected.kext_build = PHX_KEXT_BUILD;
        expected.reason_count = 7; expected.samples_per_reason = 4;
        assert(std::memcmp(&expected, &output, sizeof output) == 0);
        ++cases;
    }
    const auto unchanged = [&](IOReturn expected, IOExternalMethodArguments *args) {
        std::memset(&output, 0xa5, sizeof output);
        const auto before = output;
        assert(call(args) == expected && std::memcmp(&before, &output, sizeof output) == 0);
        ++cases;
    };
    unchanged(kIOReturnBadArgument, nullptr);
    for (unsigned field = 0; field < 4; ++field) {
        auto invalid = request;
        if (field == 0) ++invalid.scalarInputCount;
        if (field == 1) ++invalid.scalarOutputCount;
        if (field == 2) ++invalid.structureInputSize;
        if (field == 3) --invalid.structureOutputSize;
        unchanged(kIOReturnBadArgument, &invalid);
    }
    for (unsigned field = 0; field < 4; ++field) {
        auto invalid = request;
        if (field == 0) invalid.structureInputDescriptor = &version;
        if (field == 1) invalid.structureOutputDescriptor = &version;
        if (field == 2) invalid.scalarInput = nullptr;
        if (field == 3) invalid.structureOutput = nullptr;
        unchanged(kIOReturnBadArgument, &invalid);
    }
    for (uint64_t bad : {uint64_t(0), uint64_t(2), UINT64_MAX}) {
        version = bad; unchanged(kIOReturnUnsupported, &request);
    }
    version = PHXN_ALLOCATION_SNAPSHOT_VERSION;
    client.privileged = false; unchanged(kIOReturnNotPrivileged, &request);
    client.privileged = true; client.closed = true; unchanged(kIOReturnNotReady, &request);
    client.closed = false; client.owner = nullptr; unchanged(kIOReturnNotReady, &request);
    client.owner = &service; service.gpuLock = nullptr; unchanged(kIOReturnNotReady, &request);
    service.recordAllocation(phxAllocationRefusal(PHXN_ALLOC_HOST_PREPARE, 2, 4096));
    service.gpuLock = &service.mutex;
    assert(service.copyAllocationSnapshot(nullptr) == kIOReturnNotReady); ++cases;

    // No shared-context key or native-client reset; all categories have their own capacity.
    for (unsigned reason = 0; reason < PHXN_ALLOCATION_REASON_COUNT; ++reason) {
        for (unsigned attempt = 0; attempt < 300; ++attempt) {
            IOAccelPhxNativeClient temporary(service);
            temporary.owner->recordAllocation(phxAllocationRefusal(reason, reason == 6 ? 2 : 0xe00002d5u, 4096 + attempt));
        }
        ++cases;
    }
    service.recordAllocation(phxAllocationRefusal(UINT32_MAX, 2, 4096));
    assert(call(&request) == kIOReturnSuccess && output.observed == 2100);
    for (unsigned reason = 0; reason < 7; ++reason) {
        assert(output.counts[reason] == 300);
        for (unsigned i = 0; i < 4; ++i) {
            const auto &slot = output.records[reason][i];
            assert(slot.reason == reason && slot.ordinal == reason * 300 + i + 1 && slot.bytes == 4096 + i);
            assert(slot.status == (reason == 6 ? 2 : 0xe00002d5u));
            assert(!slot.observation_valid && !slot.last_seq && !slot.retired && !slot.submitted && !slot.reserved);
            for (const auto &q : slot.queue) assert(!q.reason && !q.fence_read && !q.done && !q.floor && !q.first_pending && !q.count && !q.reserved);
        }
    }
    const auto stable = output;
    assert(call(&request) == kIOReturnSuccess && std::memcmp(&stable, &output, sizeof output) == 0); ++cases;
    for (uint64_t seed : {uint64_t(0), UINT64_MAX - 1, UINT64_MAX}) {
        uint64_t count = seed;
        for (unsigned i = 0; i < 1000; ++i) {
            uint64_t before = count; phxAllocationIncrement(count);
            assert(count == (before == UINT64_MAX ? before : before + 1));
        }
        ++cases;
    }
    std::cout << "{\"cases\":" << cases << ",\"passed\":true,\"hardware_executed\":false,\"kernel_loaded\":false}\n";
}
