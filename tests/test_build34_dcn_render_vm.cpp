#include "build34_dcn_render_tlb.h"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <functional>

using IOReturn = int;
using IOByteCount = uint64_t;
using addr64_t = uint64_t;
constexpr IOReturn kIOReturnSuccess = 0, kIOReturnNotReady = -1, kIOReturnVMError = -2, kIOReturnNoMemory = -3;
constexpr IOReturn IOPMAckImplied = 0;
constexpr unsigned kIOMemoryMapperNone = 0;

static constexpr uint64_t page = 4096;
struct IOService {};
struct IOMemoryDescriptor {
    uint64_t validBytes = 2 * page;
    uint64_t getPhysicalSegment(uint64_t offset, IOByteCount *bytes, unsigned options) const {
        assert(options == kIOMemoryMapperNone);
        *bytes = offset < validBytes ? page : 0;
        return *bytes ? 0x80000 + offset : 0;
    }
};
struct IOBufferMemoryDescriptor {
    uint8_t storage[64 * 1024]{};
    void *getBytesNoCopy() { return storage; }
};
struct IOLock { bool held = false; };
static void IOLockLock(IOLock *lock) { assert(!lock->held); lock->held = true; }
static void IOLockUnlock(IOLock *lock) { assert(lock->held); lock->held = false; }
static void IODelay(unsigned) { assert(false); }
static void IOSleep(unsigned) { assert(false); }
static void IOLog(const char *) {}
static void flushLine(const volatile void *) {}
static uint64_t testClock = 0, clockStep = 100;
static uint64_t mach_absolute_time() { return testClock += clockStep; }
static void absolutetime_to_nanoseconds(uint64_t time, uint64_t *ns) { *ns = time; }

// PHX34_VM_REGISTERS

struct PhxBringup {
    // PHX34_VM_FIELDS
    IOLock lock;
    IOLock *gpuLock = &lock;
    bool isSleeping = false;
    struct Mmio {
        uint64_t length = (kRegInvEng17Ack + 1) * 4;
        uint64_t getLength() const { return length; }
    } aperture;
    Mmio *mmio = &aperture;
    IOBufferMemoryDescriptor root;
    mutable unsigned invalidations = 0;
    mutable uint32_t request = 0;
    mutable unsigned ackReads = 0;
    mutable unsigned requestReads = 0;
    mutable unsigned ownershipChecks = 0;
    bool engineIdleAndExclusive = false;
    std::function<uint32_t(unsigned)> ackRead;
    uint64_t ptes[2]{};

    bool gpuReady() const { return true; }
    uint64_t gpuRetired() const { return 100; }
    VmCtx *vmCtx(uint32_t handle) { return handle && handle <= kMaxCtx && vm[handle - 1].busy ? &vm[handle - 1] : nullptr; }
    uint64_t ptTablePhys(VmCtx &context, uint32_t index) {
        assert(lock.held && index == 0);
        context.chunk[0] = &root;
        return 0x10000;
    }
    uint64_t *vmPte(VmCtx &, uint64_t va, bool) {
        assert(lock.held && !(va & (page - 1)));
        return &ptes[(va / page) % 2];
    }
    void wreg(uint32_t reg, uint32_t value) const {
        assert(lock.held);
        if (reg == kRegInvEng17Req) {
            request = value;
            ++invalidations;
            requestReads = 0;
        }
    }
    uint32_t rreg(uint32_t reg) const {
        assert(lock.held && reg == kRegInvEng17Ack && request);
        ++ackReads;
        const auto index = requestReads++;
        return ackRead ? ackRead(index) : request & 0xff01u;
    }

    void vmFlushTlb(uint32_t vmid);
    uint32_t vmidAlloc(const void *client);
    uint32_t vmBind(uint32_t handle);
    void vmidFree(uint32_t handle, uint64_t lastSeq);
    IOReturn vmMap(uint32_t handle, uint64_t va, IOMemoryDescriptor *descriptor, uint64_t offset, uint64_t bytes);
    IOReturn vmUnmap(uint32_t handle, uint64_t va, uint64_t bytes);
    IOReturn setPowerState(unsigned long ordinal, IOService *whichDevice);

    uint32_t bind(uint32_t handle) {
        IOLockLock(gpuLock);
        const auto vmid = vmBind(handle);
        IOLockUnlock(gpuLock);
        return vmid;
    }

    build34::dcn::RenderVmTranslation identity(uint32_t handle, build34::dcn::RenderMapIdentity mapping) {
        IOLockLock(gpuLock);
        const auto snapshot = renderVmIdentityLocked(handle, mapping);
        IOLockUnlock(gpuLock);
        return snapshot;
    }

    build34::dcn::RenderTlbAck confirm(uint32_t handle, build34::dcn::RenderMapIdentity mapping) {
        IOLockLock(gpuLock);
        const auto ack = confirmRenderTlbLocked(handle, mapping);
        IOLockUnlock(gpuLock);
        return ack;
    }

    void useFixtureEngineProof() {
        renderEngine17IdleAndExclusive = [](const PhxBringup *service) {
            assert(service->lock.held);
            ++service->ownershipChecks;
            return service->engineIdleAndExclusive;
        };
    }
};

// PHX34_VM_METHODS

static void testIdentityLifetime() {
    PhxBringup service;
    const unsigned client = 1, otherClient = 2;
    const build34::dcn::RenderMapIdentity mapping{&client, 1};
    const uint32_t handle = service.vmidAlloc(&client);
    assert(handle == 1 && !service.identity(handle, mapping).provider);

    IOMemoryDescriptor descriptor;
    assert(service.vmMap(handle, 0x10000, &descriptor, 0, 2 * page) == kIOReturnSuccess);
    assert(!service.invalidations && !service.identity(handle, mapping).provider);
    const auto vmid = service.bind(handle);
    const auto original = service.identity(handle, mapping);
    assert(vmid == kFirstUserVmid && original.vmid == vmid && original.context == handle);
    assert(original.provider == &service && original.contextGeneration && original.bindingGeneration && original.tableGeneration);
    assert(!original.invalidateGeneration && service.invalidations == 1);
    assert(!service.identity(handle, {&otherClient, 1}).provider);
    assert(!service.identity(handle, {&client, 0}).provider);
    assert(!service.identity(handle, {&client, UINT64_MAX}).provider);
    service.hwv[0].ctx = 0;
    assert(!service.identity(handle, mapping).provider);
    service.hwv[0].ctx = handle;

    assert(service.bind(handle) == vmid && service.invalidations == 1);
    assert(build34::dcn::sameRenderTranslation(original, service.identity(handle, mapping)));
    assert(service.vmUnmap(handle, 0x10000, page) == kIOReturnSuccess);
    assert(!service.ptes[0] && service.ptes[1] && service.invalidations == 2);
    const auto edited = service.identity(handle, mapping);
    assert(edited.contextGeneration == original.contextGeneration && edited.bindingGeneration == original.bindingGeneration);
    assert(edited.tableGeneration > original.tableGeneration);

    for (uint32_t index = 0; index < kNumUserVmids; ++index)
        assert(service.bind(service.vmidAlloc(&otherClient)) == kFirstUserVmid + (index + 1) % kNumUserVmids);
    assert(!service.identity(handle, mapping).provider);
    assert(service.bind(handle) == kFirstUserVmid + 1);
    const auto rebound = service.identity(handle, mapping);
    assert(rebound.contextGeneration == edited.contextGeneration && rebound.tableGeneration == edited.tableGeneration);
    assert(rebound.bindingGeneration > edited.bindingGeneration);

    service.vmidFree(handle, 0);
    assert(!service.identity(handle, mapping).provider);
    assert(service.vmidAlloc(&client) == handle);
    assert(service.bind(handle) == rebound.vmid);
    const auto reused = service.identity(handle, mapping);
    assert(reused.contextGeneration > rebound.contextGeneration && reused.bindingGeneration > rebound.bindingGeneration);
    assert(reused.tableGeneration > rebound.tableGeneration && !reused.invalidateGeneration);

    descriptor.validBytes = page;
    assert(service.vmMap(handle, 0x10000, &descriptor, 0, 2 * page) == kIOReturnVMError);
    assert(service.ptes[0] && !service.identity(handle, mapping).provider);
    assert(service.vmMap(handle, 0x10000, &descriptor, 0, page) == kIOReturnSuccess);
    assert(!service.identity(handle, mapping).provider);
}

static void testPowerAndExhaustion() {
    PhxBringup service;
    const unsigned client = 1;
    const build34::dcn::RenderMapIdentity mapping{&client, 1};
    const auto handle = service.vmidAlloc(&client);
    assert(service.bind(handle) == kFirstUserVmid && service.identity(handle, mapping).provider);
    assert(service.setPowerState(0, nullptr) == IOPMAckImplied && !service.identity(handle, mapping).provider);
    assert(service.setPowerState(1, nullptr) == IOPMAckImplied && !service.identity(handle, mapping).provider);

    PhxBringup exhausted;
    exhausted.renderVmSerial = UINT64_MAX - 4;
    const auto last = exhausted.vmidAlloc(&client);
    assert(exhausted.bind(last) == kFirstUserVmid);
    assert(exhausted.identity(last, mapping).bindingGeneration == UINT64_MAX - 1);
    assert(exhausted.vmUnmap(last, 0x10000, page) == kIOReturnSuccess);
    assert(!exhausted.identity(last, mapping).provider);
    exhausted.vmidFree(last, 0);
    assert(exhausted.vmidAlloc(&client) == last && exhausted.bind(last) == kFirstUserVmid);
    assert(!exhausted.identity(last, mapping).provider && exhausted.renderVmSerial == UINT64_MAX - 1);
}

static constexpr uint32_t targetBit = 1u << kFirstUserVmid, requestMask = targetBit | 1u;

static void testCheckedRequest() {
    PhxBringup service;
    const unsigned client = 1;
    const build34::dcn::RenderMapIdentity mapping{&client, 1}, differentMap{&client, 2};
    const auto handle = service.vmidAlloc(&client);
    assert(!service.confirm(handle, mapping).matches(service.identity(handle, mapping)) && !service.ackReads);
    assert(service.bind(handle) == kFirstUserVmid && service.invalidations == 1 && service.ackReads == 1);
    const auto attempt = [&] { return service.confirm(handle, mapping); };
    const auto current = [&] { return service.identity(handle, mapping); };
    assert(!attempt().matches(current()) && service.ackReads == 1);
    service.useFixtureEngineProof();
    assert(!attempt().matches(current()) && service.ownershipChecks == 1 && service.ackReads == 1);
    service.engineIdleAndExclusive = true;
    --service.aperture.length;
    assert(!attempt().matches(current()) && service.ownershipChecks == 1 && service.ackReads == 1);
    ++service.aperture.length;
    for (const uint32_t unusable : {targetBit, UINT32_MAX}) {
        service.ackRead = [=](unsigned) { return unusable; };
        assert(!attempt().matches(current()) && service.invalidations == 1 && !service.renderInvalidateUncertain);
    }

    const auto script = [&] {
        service.ackRead = [&, nextRequest = service.invalidations + 1](unsigned read) {
            if (service.invalidations < nextRequest)
                return requestMask;
            assert(service.request == (0x00F80000u | requestMask));
            const uint32_t samples[] = {1u, targetBit, requestMask};
            assert(read < 3);
            return samples[read];
        };
    };
    script();
    const auto first = attempt();
    const auto firstIdentity = current();
    assert(first.matches(firstIdentity) && firstIdentity.invalidateGeneration && service.requestReads == 3);
    assert(!service.identity(handle, differentMap).invalidateGeneration);
    assert(!first.matches(service.identity(handle, differentMap)));
    script();
    const auto second = attempt();
    assert(second.matches(current()) && current().invalidateGeneration > firstIdentity.invalidateGeneration);
    assert(!first.matches(current()));

    service.ackRead = {};
    assert(service.vmUnmap(handle, 0x10000, page) == kIOReturnSuccess);
    assert(!current().invalidateGeneration && !second.matches(current()));
    script();
    const auto third = attempt();
    assert(third.matches(current()));
    assert(service.setPowerState(0, nullptr) == IOPMAckImplied && !third.matches(current()));
    assert(service.setPowerState(1, nullptr) == IOPMAckImplied && !attempt().matches(current()));
}

static void testUncertainRequest() {
    enum class Fault { Stale, Companion, AllOnes, Deadline, Rewind, PowerLoss, TableChange };
    for (const auto fault : {Fault::Stale, Fault::Companion, Fault::AllOnes, Fault::Deadline,
                             Fault::Rewind, Fault::PowerLoss, Fault::TableChange}) {
        testClock = 1000;
        clockStep = fault == Fault::Stale ? 0 : 100;
        PhxBringup service;
        const unsigned client = 1;
        const build34::dcn::RenderMapIdentity mapping{&client, 1};
        const auto handle = service.vmidAlloc(&client);
        assert(service.bind(handle) == kFirstUserVmid);
        service.useFixtureEngineProof();
        service.engineIdleAndExclusive = true;
        service.ackRead = [&](unsigned read) {
            if (service.invalidations == 1)
                return requestMask;
            switch (fault) {
            case Fault::Stale: return requestMask;
            case Fault::Companion: return read ? requestMask : 1u;
            case Fault::AllOnes: return UINT32_MAX;
            case Fault::Deadline:
                if (read) testClock += 1000000;
                break;
            case Fault::Rewind: testClock -= 500; break;
            case Fault::PowerLoss: service.setPowerState(0, nullptr); break;
            case Fault::TableChange: ++service.vm[0].renderTableGeneration; break;
            }
            return read ? requestMask : 0u;
        };
        const auto ack = service.confirm(handle, mapping);
        const auto current = service.identity(handle, mapping);
        assert(!ack.matches(current) && !current.invalidateGeneration && service.renderInvalidateUncertain);
        if (fault == Fault::Stale || fault == Fault::Companion)
            assert(service.requestReads == 1000);
        assert(service.invalidations == 2 && service.ownershipChecks == 1);
        service.ackRead = {};
        assert(!service.confirm(handle, mapping).matches(current));
        assert(service.invalidations == 2 && service.ownershipChecks == 1);
    }
}

int main() {
    testIdentityLifetime();
    testPowerAndExhaustion();
    testCheckedRequest();
    testUncertainRequest();
    std::puts("[PASS] staged build34 GPUVM identities (CPU only)");
}
