#include "PhxNativeABI.h"
#include "build34_dcn_render_tlb.h"
#include <cassert>
#include <cstdio>
#include <functional>

using IOReturn = int;
constexpr IOReturn kIOReturnSuccess = 0;
constexpr IOReturn kIOReturnBadArgument = -1;
constexpr IOReturn kIOReturnUnsupported = -2;
constexpr IOReturn kIOReturnNotFound = -3;
constexpr IOReturn kIOReturnNoMemory = -4;
constexpr IOReturn kIOReturnNoResources = -5;
constexpr IOReturn kIOReturnVMError = -6;

struct IOExternalMethodArguments {
    uint32_t scalarInputCount = 0, scalarOutputCount = 0;
    uint32_t structureInputSize = 0, structureOutputSize = 0;
    const void *structureInputDescriptor = nullptr, *structureOutputDescriptor = nullptr;
    const void *structureInput = nullptr;
    const uint64_t *scalarInput = nullptr;
};

struct IOLock { bool held = false; };
static void IOLockLock(IOLock *lock) { assert(!lock->held); lock->held = true; }
static void IOLockUnlock(IOLock *lock) { assert(lock->held); lock->held = false; }

struct IOMemoryDescriptor {
    unsigned completes = 0, releases = 0;
    std::function<void()> beforeComplete;
    void complete() { if (beforeComplete) beforeComplete(); ++completes; }
    void release() { ++releases; }
};

struct PhxBringup {
    bool ready = true;
    uint32_t context = 1;
    IOReturn mapResult = kIOReturnSuccess;
    unsigned allocs = 0, mapCalls = 0, unmapCalls = 0, vmFrees = 0;
    unsigned confirms = 0;
    bool sessionReleased = false;
    std::function<void()> onMap, onUnmap;
    bool gpuReady() const { return ready; }
    const void *renderClient = nullptr;
    uint32_t vmidAlloc(const void *client) { ++allocs; renderClient = client; return context; }
    build34::dcn::RenderVmTranslation renderVmIdentityLocked(uint32_t handle,
                                                            build34::dcn::RenderMapIdentity mapping) {
        assert(handle == context && mapping.client == renderClient);
        return {mapping, this, 1, 2, 3, 0, handle, 8};
    }
    build34::dcn::RenderTlbAck confirmRenderTlbLocked(uint32_t handle, build34::dcn::RenderMapIdentity mapping) {
        assert(handle == context && mapping.client == renderClient && mapping.generation);
        ++confirms;
        return {};
    }
    IOReturn vmMap(uint32_t vmid, uint64_t, IOMemoryDescriptor *, uint64_t, uint64_t) {
        assert(vmid == context);
        ++mapCalls;
        if (onMap) onMap();
        return mapResult;
    }
    IOReturn vmUnmap(uint32_t vmid, uint64_t, uint64_t) {
        assert(vmid == context);
        ++unmapCalls;
        if (onUnmap) onUnmap();
        return kIOReturnSuccess;
    }
    void vmidFree(uint32_t vmid, uint64_t) { assert(vmid == context); ++vmFrees; }
    void releaseSession() { assert(!sessionReleased); sessionReleased = true; }
};

// PHX34_RENDER_MAP_CONSTANTS

struct IOAccelPhxNativeClient {
    // PHX34_RENDER_MAP_TYPES
    // PHX34_RENDER_MAP_FIELDS
    IOLock guard;
    IOLock *lock = &guard;
    PhxBringup device;
    PhxBringup *owner = &device;
    Bo boTable[PHXN_MAX_BOS]{};
    Map mapTable[kMaxMaps]{};
    bool sessionClaimed = true, terminated = false;
    void terminate() { terminated = true; }
    IOAccelPhxNativeClient() { bos = boTable; maps = mapTable; }
    Bo *findBo(uint32_t handle);
    IOReturn doBoFree(IOExternalMethodArguments *args);
    void boRelease(Bo &bo);
    IOReturn doGemVa(IOExternalMethodArguments *args);
    void freeAll();
    IOReturn clientClose();

    IOReturn changeMap(uint32_t op, uint64_t va, uint32_t handle, uint64_t offset, uint64_t bytes) {
        const phxn_gem_va request{handle, 0, op, 0, va, offset, bytes, 0, 0, 0, 0};
        IOExternalMethodArguments args;
        args.structureInputSize = sizeof(request);
        args.structureInput = &request;
        IOLockLock(lock);
        const auto result = doGemVa(&args);
        IOLockUnlock(lock);
        return result;
    }
    IOReturn freeBo(uint64_t handle) {
        IOExternalMethodArguments args;
        args.scalarInputCount = 1;
        args.scalarInput = &handle;
        IOLockLock(lock);
        const auto result = doBoFree(&args);
        IOLockUnlock(lock);
        return result;
    }
    uint64_t generation(uint64_t va, uint64_t bytes) {
        IOLockLock(lock);
        const auto result = softwareMappedHostGenerationLocked(va, bytes);
        IOLockUnlock(lock);
        return result;
    }
    build34::dcn::RenderVmTranslation translation(uint64_t va, uint64_t bytes) {
        IOLockLock(lock);
        const auto result = renderTranslationLocked(va, bytes);
        IOLockUnlock(lock);
        return result;
    }
    void confirm(uint64_t va, uint64_t bytes) {
        IOLockLock(lock);
        confirmRenderTlbLocked(va, bytes);
        IOLockUnlock(lock);
    }
};

// PHX34_RENDER_MAP_METHODS

constexpr uint64_t page = 4096, start = 0x10000;
constexpr uint32_t mapOp = PHX_AMDGPU_VA_OP_MAP, unmapOp = PHX_AMDGPU_VA_OP_UNMAP;

static void testPublicationAndReuse() {
    IOAccelPhxNativeClient client;
    IOMemoryDescriptor host, other, local;
    client.bos[1] = {&host, 4 * page, 2, 0, nullptr, true};
    client.bos[2] = {&other, 4 * page, 2, 0, nullptr, true};
    client.bos[3] = {&local, 4 * page, 2, 0, nullptr, false};
    client.hostUsed = 8 * page;

    client.device.ready = false;
    assert(client.changeMap(mapOp, start, 1, page, 2 * page) == kIOReturnSuccess);
    assert(client.maps[0].used && !client.maps[0].softwareGeneration && !client.device.allocs);
    client.device.ready = true;
    assert(client.changeMap(mapOp, start + 2 * page, 2, page, 2 * page) == kIOReturnSuccess);
    assert(client.vmid && client.generation(start, page) == 0);
    assert(client.generation(start + 2 * page, 2 * page) == 1);
    const auto translation = client.translation(start + 2 * page, 2 * page);
    assert(translation.mapping.client == &client && translation.mapping.generation == 1);
    assert(translation.provider == &client.device && !client.translation(start, page).provider);
    assert(!client.translation(start + 2 * page, 3 * page).provider);
    client.confirm(start, page);
    client.confirm(start + 2 * page, 3 * page);
    assert(!client.device.confirms);
    client.confirm(start + 2 * page, 2 * page);
    assert(client.device.confirms == 1);

    assert(client.changeMap(unmapOp, start, 1, page, 2 * page) == kIOReturnSuccess);
    client.device.onMap = [&] {
        assert(client.guard.held);
        assert(client.softwareMappedHostGenerationLocked(start, page) == 0);
    };
    client.device.mapResult = kIOReturnVMError;
    assert(client.changeMap(mapOp, start, 1, page, 2 * page) == kIOReturnVMError);
    assert(!client.maps[0].used && !client.maps[0].softwareGeneration);
    assert(client.renderMapGeneration == 1);
    client.device.mapResult = kIOReturnSuccess;
    assert(client.changeMap(mapOp, start, 1, page, 2 * page) == kIOReturnSuccess);
    client.device.onMap = {};
    assert(client.generation(start, 2 * page) == 2 && client.generation(start + page, page) == 2);
    assert(client.generation(start + page, 2 * page) == 0);
    assert(client.generation(start, 0) == 0 && client.generation(start, page + 1) == 0);
    assert(client.generation(start + 1, page) == 0);
    assert(client.changeMap(mapOp, start + page, 2, page, page) == kIOReturnBadArgument);
    assert(client.changeMap(mapOp, start + 4 * page, 3, 0, page) == kIOReturnSuccess);
    assert(client.generation(start + 4 * page, page) == 0 && client.renderMapGeneration == 2);

    client.device.onUnmap = [&] {
        assert(client.guard.held && !client.maps[0].softwareGeneration);
        assert(client.softwareMappedHostGenerationLocked(start, page) == 0);
    };
    assert(client.changeMap(unmapOp, start, 1, page, page) == kIOReturnBadArgument);
    assert(client.generation(start, page) == 2);
    assert(client.changeMap(unmapOp, start, 1, page, 2 * page) == kIOReturnSuccess);
    assert(client.changeMap(mapOp, start, 1, page, 2 * page) == kIOReturnSuccess);
    assert(client.generation(start, 2 * page) == 3);

    host.beforeComplete = [&] {
        assert(client.guard.held && !client.maps[0].softwareGeneration);
        assert(client.softwareMappedHostGenerationLocked(start, page) == 0);
        assert(client.softwareMappedHostGenerationLocked(start + 2 * page, page) == 1);
    };
    assert(client.freeBo(1) == kIOReturnSuccess && host.completes == 1 && host.releases == 1);
    assert(client.hostUsed == 4 * page);
    client.bos[1] = {&host, 4 * page, 2, 0, nullptr, true};
    client.hostUsed += 4 * page;
    assert(client.changeMap(mapOp, start, 1, 0, 2 * page) == kIOReturnSuccess);
    assert(client.generation(start, page) == 4);
}

static void testCloseAndExhaustion() {
    IOAccelPhxNativeClient client;
    IOMemoryDescriptor host;
    client.bos[1] = {&host, 3 * page, 2, 0, nullptr, true};
    client.device.context = 0;
    assert(client.changeMap(mapOp, start, 1, 0, page) == kIOReturnNoResources);
    assert(!client.maps[0].used && !client.renderMapGeneration && !client.device.mapCalls);
    client.device.context = 1;
    client.renderMapGeneration = UINT64_MAX - 2;
    assert(client.changeMap(mapOp, start, 1, page, page) == kIOReturnSuccess);
    assert(client.generation(start, page) == UINT64_MAX - 1);
    assert(client.changeMap(mapOp, start + page, 1, 2 * page, page) == kIOReturnSuccess);
    assert(client.maps[1].used && client.generation(start + page, page) == 0);
    assert(client.renderMapGeneration == UINT64_MAX - 1);

    host.beforeComplete = [&] {
        assert(client.guard.held && client.renderMapsClosed && !client.maps[0].softwareGeneration);
        assert(client.softwareMappedHostGenerationLocked(start, page) == 0);
    };
    assert(client.clientClose() == kIOReturnSuccess && client.device.vmFrees == 1);
    assert(client.device.sessionReleased && client.terminated && host.completes == 1 && host.releases == 1);
    assert(client.generation(start, page) == 0);
    client.renderMapGeneration = 9;
    client.bos[1] = {&host, 3 * page, 2, 0, nullptr, true};
    assert(client.changeMap(mapOp, start + 2 * page, 1, 0, page) == kIOReturnSuccess);
    assert(client.maps[2].used && !client.maps[2].softwareGeneration && client.renderMapGeneration == 9);
    assert(client.generation(start + 2 * page, page) == 0);
}

static void testRangeBoundaries() {
    IOAccelPhxNativeClient client;
    IOMemoryDescriptor host;
    client.bos[1] = {&host, 2 * page, 2, 0, nullptr, true};
    const uint64_t high = UINT64_MAX - page + 1;
    assert(client.changeMap(mapOp, high, 1, 0, 2 * page) == kIOReturnBadArgument);
    assert(client.changeMap(mapOp, start, 1, high, 2 * page) == kIOReturnBadArgument);
    assert(!client.device.mapCalls && !client.renderMapGeneration);
    assert(client.changeMap(mapOp, high, 1, page, page) == kIOReturnSuccess);
    assert(client.generation(high & kVaMask, page) == 1);
    assert(client.generation(high & kVaMask, 2 * page) == 0);
    assert(client.generation(high, page) == 0);
}

int main() {
    testPublicationAndReuse();
    testCloseAndExhaustion();
    testRangeBoundaries();
    std::puts("[PASS] staged build34 host-map generations (CPU only)");
}
