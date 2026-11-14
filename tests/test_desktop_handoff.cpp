// Actual provider methods with CPU memory, lock and PCI fakes. Never a kext or GPU.
#include "PhxDesktopHandoff.h"
#include "PhxHardwarePolicy.hpp"
#include <cassert>
#include <cstring>
#include <iostream>
#include <string>
#include <vector>
using IOReturn = int;
enum { kIOReturnSuccess, kIOReturnBadArgument, kIOReturnNotReady, kIOReturnExclusiveAccess };
struct FakeLock { unsigned rank; bool held{false}; };
static std::vector<FakeLock *> held;
static void (*afterLock)(FakeLock *) = nullptr;
static void IOLockLock(FakeLock *lock) {
    assert(lock && !lock->held && (held.empty() || held.back()->rank < lock->rank));
    lock->held = true; held.push_back(lock);
    if (afterLock) afterLock(lock);
}
static void IOLockUnlock(FakeLock *lock) {
    assert(lock && !held.empty() && held.back() == lock && lock->held);
    held.pop_back(); lock->held = false;
}
static void IOLog(const char *, ...) {}
struct FakeMap {
    std::vector<uint64_t> words;
    uint64_t length;
    explicit FakeMap(size_t bytes) : words(bytes / 8, 0), length(bytes) {}
    uintptr_t getVirtualAddress() { return reinterpret_cast<uintptr_t>(words.data()); }
    uint64_t getLength() const { return length; }
};
static const bool fakeTrue = true;
static const void *kOSBooleanTrue = &fakeTrue;
struct FakePci {
    unsigned properties{0}, registrations{0};
    void setProperty(const char *name, const void *value) {
        assert(!std::strcmp(name, "nmxgpu-claimed") && value == kOSBooleanTrue);
        assert(held.size() == 1 && held[0]->rank == 1); ++properties;
    }
    void registerService() { assert(held.size() == 1 && held[0]->rank == 1); ++registrations; }
};
class PhxBringup {
public:
#include "queue-structure.inc"
    GpuQueue gq[2]{};
    FakeMap memory{0x400000}, bells{0x1000};
    FakeMap *fbAper{&memory}, *doorbellMap{&bells};
    void *mmio{reinterpret_cast<void *>(1)};
    FakeLock bootstrapMutex{1}, gpuMutex{2}, smuMutex{3};
    FakeLock *bootstrapLock{&bootstrapMutex}, *gpuLock{&gpuMutex}, *smuLock{&smuMutex};
    uint64_t fbAperLen{0x400000}, fbSize{0x8000000}, fbMcBase{0x100000000ull}, fbPhys{0x200000000ull};
    uint64_t gSeq{0x1122334455667788ull};
    bool pspLayoutConfigured{true}, pspSubmissionFaulted{false}, stopping{false};
    PhxPspLayout pspLayout{PHX_PSP_LAYOUT_VERSION, 0, 0x100000, 0x10000, 0x200000, 0x10000, {0, 0}};
    uint64_t ringMc{fbMcBase}, tmrSize{0x1000}; bool tmrSetUp{true};
    struct VmCtx { bool busy{false}; } vm[2];
    struct HwVmid { uint32_t ctx{0}; bool faulted{false}; } hwv[2];
    enum DesktopState { DesktopUnused, DesktopInitializing, DesktopSealed, DesktopClaimed, DesktopAbandoned };
    DesktopState desktopState{DesktopUnused};
    const void *desktopOwner{nullptr}; PhxDesktopLayout desktopLayout{};
    FakePci device; FakePci *pci{&device}; unsigned flushes{0};
    void hdpFlush() { assert(held.size() == 3); ++flushes; }
    IOReturn adoptQueue(const uint64_t in[6]); IOReturn claimAccel(); IOReturn bootMemory(PhxBootMemory *);
    IOReturn lockDebugMutation(const void *, uint32_t); void unlockDebugMutation();
    IOReturn desktopHandoff(const void *, const PhxDesktopRequest &); void abandonDesktop(const void *);
    void deferClient(uint32_t, uint64_t, void *) { assert(false); }
#include "queue-readiness-declaration.inc"
};
#include "queue-adoption.inc"
#include "queue-readiness-methods.inc"
#include "desktop-methods.inc"

class IOAccelPhxNativeClient {
public:
    bool closed{false}, desktopReservationOwned{false};
    PhxBringup *owner{nullptr};
    uint32_t vmid{0}; uint64_t lastSeq{0}; void *bufferStorage{nullptr}, *bos{nullptr};
    unsigned frees{0};
    void freeAll() { ++frees; }
    void closeResources();
};
#include "desktop-client-close.inc"

static const void *owner = reinterpret_cast<void *>(1), *other = reinterpret_cast<void *>(2);
static PhxDesktopRequest request() {
    return {PHX_DESKTOP_RESERVE, {1, {1, 0x4000000000ull, 0x400000, 0x300000, 0x302000},
        {1, 0x310000, 0x18}, {1, 0x314000, 0x16}, {1, 0x318000, 6}, {1, 0x320000, 0x116}}, 0, 0};
}
static IOReturn execute(PhxBringup &p, const void *client, const PhxDesktopRequest &r) {
    IOReturn result = p.lockDebugMutation(client, PHX_DESKTOP_SELECTOR);
    if (result == kIOReturnSuccess) { result = p.desktopHandoff(client, r); p.unlockDebugMutation(); }
    assert(held.empty()); return result;
}
static void ready(PhxBringup &p, PhxDesktopRequest &r) {
    assert(execute(p, owner, r) == kIOReturnSuccess);
    r.operation = PHX_DESKTOP_SEAL; r.computeWptr = PHX_DESKTOP_COMPUTE_WPTR; r.graphicsWptr = PHX_DESKTOP_GRAPHICS_WPTR;
    p.memory.words[(r.layout.compute.arenaOffset + 0x5000) / 8] = PHX_DESKTOP_COMPUTE_TOKEN;
    p.memory.words[(r.layout.graphics.arenaOffset + 0x7000) / 8] = PHX_DESKTOP_GRAPHICS_TOKEN;
    p.memory.words[(r.layout.compute.arenaOffset + 0x1010) / 8] = r.computeWptr;
    p.memory.words[(r.layout.graphics.arenaOffset + 0x4010) / 8] = r.graphicsWptr;
}
static PhxBringup *injection;
static unsigned adoptionLocks;
static void stopSecond(FakeLock *lock) {
    if (lock == injection->gpuLock && ++adoptionLocks == 2) injection->stopping = true;
}
static void test(const std::string &name) {
    PhxBringup p; auto r = request(); const auto empty = p.memory.words;
    if (name == "passive-close") {
        assert(execute(p, owner, r) == kIOReturnSuccess);
        IOAccelPhxNativeClient passive; passive.owner = &p;
        // Model a blocked initializer holding this lock. Reentry would assert.
        assert(p.lockDebugMutation(owner, 108) == kIOReturnSuccess);
        passive.closeResources(); passive.closeResources();
        assert(passive.closed && passive.frees == 1 && p.bootstrapMutex.held);
        p.unlockDebugMutation();
        assert(p.desktopState == p.DesktopInitializing && p.desktopOwner == owner);
        return;
    }
    if (name == "initializer-close") {
        IOAccelPhxNativeClient initializer; initializer.owner = &p;
        assert(execute(p, &initializer, r) == kIOReturnSuccess);
        initializer.desktopReservationOwned = true;
        initializer.closeResources(); initializer.closeResources();
        assert(initializer.closed && !initializer.desktopReservationOwned && initializer.frees == 1);
        assert(p.desktopState == p.DesktopAbandoned && !p.desktopOwner && p.memory.words == empty);
        return;
    }
    if (name == "lease") {
        for (uint32_t selector = 0; selector < 128; ++selector) {
            if (!phxDesktopMutationSelector(selector)) continue;
            assert(p.lockDebugMutation(other, selector) == kIOReturnSuccess); p.unlockDebugMutation();
        }
        assert(execute(p, owner, r) == kIOReturnSuccess && p.memory.words == empty && !p.flushes);
        for (uint32_t selector = 0; selector < 128; ++selector) {
            if (!phxDesktopMutationSelector(selector)) continue;
            for (const void *client : {owner, other}) {
                const bool allow = selector == PHX_DESKTOP_SELECTOR || (client == owner && phxDesktopInitializerSelector(selector));
                assert(p.lockDebugMutation(client, selector) == (allow ? kIOReturnSuccess : kIOReturnExclusiveAccess));
                if (allow) p.unlockDebugMutation();
            }
        }
        p.abandonDesktop(other); assert(p.desktopState == p.DesktopInitializing);
        p.abandonDesktop(owner); assert(p.desktopState == p.DesktopAbandoned && !p.desktopOwner);
        assert(execute(p, owner, r) == kIOReturnExclusiveAccess);
        assert(p.memory.words == empty && !p.gq[0].ready && !p.gq[1].ready); return;
    }
    if (name == "live-vm" || name == "live-slot" || name == "faulted-slot" || name == "stopping") {
        p.vm[0].busy = name == "live-vm"; p.hwv[0].ctx = name == "live-slot";
        p.hwv[0].faulted = name == "faulted-slot"; p.stopping = name == "stopping";
        assert(execute(p, owner, r) == kIOReturnNotReady && p.desktopState == p.DesktopUnused); return;
    }
    if (name == "invalid-layout" || name == "doorbell-overrun" || name == "psp-fault" || name == "pre-adopted") {
        if (name == "invalid-layout") r.layout.compute.arenaOffset = r.layout.graphics.arenaOffset;
        if (name == "doorbell-overrun") r.layout.kiq.doorbellIndex = 0x400;
        if (name == "psp-fault") p.pspSubmissionFaulted = true;
        if (name == "pre-adopted") p.gq[0].ready = true;
        assert(execute(p, owner, r) == kIOReturnBadArgument && p.desktopState == p.DesktopUnused);
        assert(p.memory.words == empty && !p.flushes); return;
    }
    ready(p, r);
    if (name == "foreign-seal") {
        assert(execute(p, other, r) == kIOReturnExclusiveAccess && p.desktopState == p.DesktopInitializing); return;
    }
    if (name == "layout-drift" || name == "wrong-wptr") {
        if (name == "layout-drift") r.layout.gart.virtualBase += 4096; else ++r.computeWptr;
        assert(execute(p, owner, r) == kIOReturnBadArgument && p.desktopState == p.DesktopInitializing); return;
    }
    if (name.rfind("bad-evidence-", 0) == 0) {
        const unsigned i = static_cast<unsigned>(std::stoul(name.substr(13)));
        const uint64_t offsets[] = {r.layout.compute.arenaOffset + 0x5000, r.layout.graphics.arenaOffset + 0x7000,
            r.layout.compute.arenaOffset + 0x1010, r.layout.graphics.arenaOffset + 0x4010};
        assert(i < 4); p.memory.words[offsets[i] / 8] ^= 1ull << 32;
        const auto before = p.memory.words;
        assert(execute(p, owner, r) == kIOReturnNotReady && p.desktopState == p.DesktopAbandoned);
        assert(p.memory.words == before && !p.flushes && !p.gq[0].ready && !p.gq[1].ready); return;
    }
    if (name == "adoption-failure" || name == "second-adoption-failure") {
        if (name == "adoption-failure") p.pspSubmissionFaulted = true;
        else { injection = &p; adoptionLocks = 0; afterLock = stopSecond; }
        assert(execute(p, owner, r) == kIOReturnNotReady && p.desktopState == p.DesktopAbandoned);
        afterLock = nullptr;
        assert(p.gq[0].ready == (name == "second-adoption-failure") && !p.gq[1].ready && !p.device.properties); return;
    }
    assert(execute(p, owner, r) == kIOReturnSuccess && p.desktopState == p.DesktopSealed);
    p.abandonDesktop(owner); // Sealed provider ownership survives initializer exit.
    assert(p.desktopState == p.DesktopSealed && !p.desktopOwner && p.flushes == 2);
    assert(p.gq[0].ready && p.gq[1].ready && p.gq[0].ringOff == r.layout.compute.arenaOffset);
    assert(p.gq[1].ringOff == r.layout.graphics.arenaOffset && p.gq[0].wptr == 16 && p.gq[1].wptr == 976);
    for (uint32_t selector : {100u, 101u, 103u, 108u, 109u, 110u, 111u, 112u, 113u, 114u, 115u})
        assert(p.lockDebugMutation(owner, selector) == kIOReturnExclusiveAccess);
    r.operation = PHX_DESKTOP_CLAIM;
    if (name == "claim-no-pci") p.pci = nullptr;
    const auto before = p.memory.words;
    assert(execute(p, other, r) == (p.pci ? kIOReturnSuccess : kIOReturnNotReady));
    assert(p.desktopState == (p.pci ? p.DesktopClaimed : p.DesktopAbandoned));
    assert(p.device.properties == (p.pci ? 1u : 0u) && p.device.registrations == p.device.properties);
    assert(p.memory.words == before && execute(p, other, r) == kIOReturnNotReady);
    PhxBootMemory snapshot{}; assert(p.bootMemory(&snapshot) == kIOReturnSuccess);
    assert(snapshot.flags & PHX_BOOT_GPU_ACTIVE); // Existing passive bootstrap export remains unchanged.
}
static void arithmetic() {
    PhxBringup p; auto r = request(); PhxBootMemory memory{};
    assert(p.bootMemory(&memory) == kIOReturnSuccess && phxDesktopLayoutValid(&r.layout, &memory));
    for (unsigned i = 0; i < 4; ++i) for (unsigned j = 0; j < 4; ++j) {
        if (i == j) continue;
        auto bad = r.layout;
        PhxMesQueueLayout *queues[] = {&bad.kiq, &bad.scheduler, &bad.compute, &bad.graphics};
        queues[i]->arenaOffset = queues[j]->arenaOffset;
        assert(!phxDesktopLayoutValid(&bad, &memory));
        bad = r.layout; queues[i]->doorbellIndex = queues[j]->doorbellIndex;
        assert(!phxDesktopLayoutValid(&bad, &memory));
    }
    for (unsigned i = 0; i < 4; ++i) for (unsigned k = 0; k < 10; ++k) {
        auto bad = r.layout; PhxMesQueueLayout *queues[] = {&bad.kiq, &bad.scheduler, &bad.compute, &bad.graphics};
        const uint64_t offsets[] = {0, 0x100000, 0x200000, 0x300000, 0x302000, 0x3ff000,
                                    0xfffff000ull, UINT64_MAX - 4095};
        if (k < 8) queues[i]->arenaOffset = offsets[k];
        else if (k == 8) ++queues[i]->arenaOffset;
        else ++queues[i]->doorbellIndex;
        assert(!phxDesktopLayoutValid(&bad, &memory));
    }
}
int main(int argc, char **argv) {
    assert(argc == 2);
    const std::string name = argv[1];
    if (name == "arithmetic") arithmetic(); else test(name);
    assert(held.empty());
    std::cout << "actual-desktop-methods-passed " << name << '\n';
}
