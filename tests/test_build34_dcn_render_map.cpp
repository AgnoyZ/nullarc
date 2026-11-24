#include "PhxNativeABI.h"
#include "build34_dcn_render_binding.h"
#include <cassert>
#include <cstdio>
#include <functional>

constexpr uint64_t page = 4096, start = 0x10000;
constexpr unsigned kIODirectionInOut = 3;
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
    uint64_t *scalarOutput = nullptr;
};

struct IOLock { bool held = false; };
static void IOLockLock(IOLock *lock) { assert(!lock->held); lock->held = true; }
static void IOLockUnlock(IOLock *lock) { assert(lock->held); lock->held = false; }

struct Descriptor final : IOMemoryDescriptor {
    unsigned completes = 0, releases = 0, prepares = 0, references = 1, wires = 0;
    uint64_t bytes = 4 * page, preparation = 17;
    std::function<void()> beforeComplete, beforePrepare;
    IOByteCount getLength() const override { return bytes; }
    uint64_t getPreparationID() override { return wires ? preparation : 0; }
    uint64_t getPhysicalSegment(IOByteCount offset, IOByteCount *length, unsigned options) override {
        assert(wires && offset < bytes && options == kIOMemoryMapperNone);
        *length = page;
        return 0x80000 + offset * 2;
    }
    IOReturn prepare() override { if (beforePrepare) beforePrepare(); ++prepares; ++wires; return kIOReturnSuccess; }
    IOReturn complete() override {
        if (beforeComplete) beforeComplete();
        assert(wires);
        ++completes;
        --wires;
        return kIOReturnSuccess;
    }
    void retain() override { ++references; }
    void release() override { assert(references); --references; ++releases; }
};

IOMemoryDescriptor *IOMemoryDescriptor::withAddressRange(uint64_t va, uint64_t size, unsigned direction, void *task) {
    assert(va && direction == kIODirectionInOut && task);
    auto *candidate = static_cast<Descriptor *>(task);
    candidate->bytes = size;
    return candidate;
}

struct PhxBringup {
    bool ready = true;
    bool exactPages = true;
    IOLock gpuGuard;
    IOLock *gpuLock = &gpuGuard;
    uint64_t table = 3, invalidate = 0;
    uint64_t confirmedMap = 0;
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
        assert(gpuGuard.held);
        return {mapping, this, 1, 2, table, mapping.generation == confirmedMap ? invalidate : 0, handle, 8};
    }
    build34::dcn::RenderTlbAck confirmRenderTlbLocked(uint32_t handle, build34::dcn::RenderMapIdentity mapping) {
        assert(handle == context && mapping.client == renderClient && mapping.generation);
        ++confirms;
        ++invalidate;
        confirmedMap = mapping.generation;
        struct Samples { build34::dcn::RenderVmTranslation translation; unsigned count; } state{
            renderVmIdentityLocked(handle, mapping), 0};
        return build34::dcn::RenderTlbAck::observe(state.translation, &state, [](void *opaque, build34::dcn::RenderTlbSample *sample) {
            auto &fixture = *static_cast<Samples *>(opaque);
            *sample = {fixture.translation, 1000, fixture.count++ ? (1u << 8) : 0u};
            return true;
        });
    }
    IOReturn vmMap(uint32_t vmid, uint64_t, IOMemoryDescriptor *, uint64_t, uint64_t, bool *exact) {
        assert(vmid == context);
        ++mapCalls;
        if (onMap) onMap();
        if (exact)
            *exact = exactPages && mapResult == kIOReturnSuccess;
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
    Descriptor *task = nullptr;
    void terminate() { terminated = true; }
    IOAccelPhxNativeClient() { bos = boTable; maps = mapTable; }
    Bo *findBo(uint32_t handle);
    IOReturn doBoFree(IOExternalMethodArguments *args);
    IOReturn doBoImportHost(IOExternalMethodArguments *args);
    void boRelease(Bo &bo);
    IOReturn doGemVa(IOExternalMethodArguments *args);
    void freeAll();
    IOReturn clientClose();

    uint32_t importHost(Descriptor &descriptor, uint64_t bytes) {
        task = &descriptor;
        const uint64_t in[] = {start, bytes, 0, 0};
        uint64_t out[4]{};
        IOExternalMethodArguments args;
        args.scalarInputCount = args.scalarOutputCount = 4;
        args.scalarInput = in;
        args.scalarOutput = out;
        IOLockLock(lock);
        const auto result = doBoImportHost(&args);
        IOLockUnlock(lock);
        assert(result == kIOReturnSuccess && out[1] == bytes);
        return static_cast<uint32_t>(out[0]);
    }

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
        const auto result = generationLocked(va, bytes);
        IOLockUnlock(lock);
        return result;
    }
    uint64_t generationLocked(uint64_t va, uint64_t bytes) const {
        const auto *entry = softwareMappedHostRangeLocked(va, bytes);
        return entry ? entry->softwareGeneration : 0;
    }
    build34::dcn::LiveHostRenderMap snapshot(uint64_t va, uint64_t bytes) {
        IOLockLock(lock);
        IOLockLock(device.gpuLock);
        const auto result = liveHostRenderMapLocked(va, bytes);
        IOLockUnlock(device.gpuLock);
        IOLockUnlock(lock);
        return result;
    }
    build34::dcn::RenderTlbAck confirm(uint64_t va, uint64_t bytes) {
        IOLockLock(lock);
        IOLockLock(device.gpuLock);
        const auto ack = confirmRenderTlbLocked(va, bytes);
        IOLockUnlock(device.gpuLock);
        IOLockUnlock(lock);
        return ack;
    }
    bool acquire(const build34::dcn::BoundRenderImage &image, const build34::dcn::RenderTlbAck &ack,
                 const void *surface, const build34::dcn::ScanoutSurface &scanout,
                 build34::dcn::RenderDescriptorLease &lease) {
        IOLockLock(lock);
        const bool result = acquireRenderBackingClientLocked(image, ack, surface, scanout, lease);
        IOLockUnlock(lock);
        return result;
    }
};

// PHX34_RENDER_MAP_METHODS

constexpr uint32_t mapOp = PHX_AMDGPU_VA_OP_MAP, unmapOp = PHX_AMDGPU_VA_OP_UNMAP;

static void testPublicationAndReuse() {
    IOAccelPhxNativeClient client;
    Descriptor host, other, local, replacement;
    assert(client.importHost(host, 4 * page) == 1);
    assert(client.importHost(other, 4 * page) == 2);
    client.bos[3] = {&local, 4 * page, 2, 0, nullptr, false};

    client.device.ready = false;
    assert(client.changeMap(mapOp, start, 1, page, 2 * page) == kIOReturnSuccess);
    assert(client.maps[0].used && !client.maps[0].softwareGeneration && !client.device.allocs);
    client.device.ready = true;
    assert(client.changeMap(mapOp, start + 2 * page, 2, page, 2 * page) == kIOReturnSuccess);
    assert(client.vmid && client.generation(start, page) == 0);
    assert(client.generation(start + 2 * page, 2 * page) == 1);
    const auto translation = client.snapshot(start + 2 * page, 2 * page).translation;
    assert(translation.mapping.client == &client && translation.mapping.generation == 1);
    assert(translation.provider == &client.device && !client.snapshot(start, page).descriptor);
    assert(!client.snapshot(start + 2 * page, 3 * page).descriptor);
    client.confirm(start, page);
    client.confirm(start + 2 * page, 3 * page);
    assert(!client.device.confirms);
    client.confirm(start + 2 * page, 2 * page);
    assert(client.device.confirms == 1);

    assert(client.changeMap(unmapOp, start, 1, page, 2 * page) == kIOReturnSuccess);
    client.device.onMap = [&] {
        assert(client.guard.held);
        assert(client.generationLocked(start, page) == 0);
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
        assert(client.generationLocked(start, page) == 0);
    };
    assert(client.changeMap(unmapOp, start, 1, page, page) == kIOReturnBadArgument);
    assert(client.generation(start, page) == 2);
    assert(client.changeMap(unmapOp, start, 1, page, 2 * page) == kIOReturnSuccess);
    assert(client.changeMap(mapOp, start, 1, page, 2 * page) == kIOReturnSuccess);
    assert(client.generation(start, 2 * page) == 3);

    host.beforeComplete = [&] {
        assert(client.guard.held && !client.maps[0].softwareGeneration);
        assert(client.generationLocked(start, page) == 0);
        assert(client.generationLocked(start + 2 * page, page) == 1);
    };
    assert(client.freeBo(1) == kIOReturnSuccess && host.completes == 1 && host.releases == 1);
    assert(client.hostUsed == 4 * page);
    assert(client.importHost(replacement, 4 * page) == 1);
    assert(client.changeMap(mapOp, start, 1, 0, 2 * page) == kIOReturnSuccess);
    assert(client.generation(start, page) == 4);
}

static void testCloseAndExhaustion() {
    IOAccelPhxNativeClient client;
    Descriptor host, replacement;
    assert(client.importHost(host, 3 * page) == 1);
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
        assert(client.generationLocked(start, page) == 0);
    };
    assert(client.clientClose() == kIOReturnSuccess && client.device.vmFrees == 1);
    assert(client.device.sessionReleased && client.terminated && host.completes == 1 && host.releases == 1);
    assert(client.generation(start, page) == 0);
    client.renderMapGeneration = 9;
    assert(client.importHost(replacement, 3 * page) == 1);
    assert(client.changeMap(mapOp, start + 2 * page, 1, 0, page) == kIOReturnSuccess);
    assert(client.maps[2].used && !client.maps[2].softwareGeneration && client.renderMapGeneration == 9);
    assert(client.generation(start + 2 * page, page) == 0);
}

static void testRangeBoundaries() {
    IOAccelPhxNativeClient client;
    Descriptor host;
    assert(client.importHost(host, 2 * page) == 1);
    const uint64_t high = UINT64_MAX - page + 1;
    assert(client.changeMap(mapOp, high, 1, 0, 2 * page) == kIOReturnBadArgument);
    assert(client.changeMap(mapOp, start, 1, high, 2 * page) == kIOReturnBadArgument);
    assert(!client.device.mapCalls && !client.renderMapGeneration);
    assert(client.changeMap(mapOp, high, 1, page, page) == kIOReturnSuccess);
    assert(client.generation(high & kVaMask, page) == 1);
    assert(client.generation(high & kVaMask, 2 * page) == 0);
    assert(client.generation(high, page) == 0);
}

static void testLiveRenderBacking() {
    using namespace build34::dcn;
    IOAccelPhxNativeClient client;
    Descriptor host, replacement, large;
    const auto handle = client.importHost(host, 4 * page);
    const auto largeHandle = client.importHost(large, kMaxBackingBytes + page);
    assert(!client.bos[largeHandle].renderPreparation);
    assert(client.changeMap(mapOp, start + 4 * page, largeHandle, 0, page) == kIOReturnSuccess);
    assert(!client.generation(start + 4 * page, page));
    client.device.exactPages = false;
    assert(client.changeMap(mapOp, start, handle, page, 3 * page) == kIOReturnSuccess);
    assert(!client.generation(start, page) && !client.snapshot(start, page).descriptor);
    assert(client.changeMap(unmapOp, start, handle, page, 3 * page) == kIOReturnSuccess);
    client.device.exactPages = true;
    assert(client.changeMap(mapOp, start, handle, page, 3 * page) == kIOReturnSuccess);

    const uint64_t address = start + page;
    const ScanoutSurface scanout{1024, 2, 1023, kDcnArgb8888, 2 * page};
    const unsigned surface = 1, otherSurface = 2;
    const auto initial = client.snapshot(address, scanout.mappedBytes);
    assert(initial.descriptor == &host && initial.preparation == host.preparation && initial.boBytes == 4 * page);
    assert(initial.gpuAddress == start && initial.boOffset == page && initial.bytes == 3 * page);
    auto ack = client.confirm(address, scanout.mappedBytes);
    BoundRenderImage image{client.snapshot(address, scanout.mappedBytes).translation, &surface,
                           address, 2 * page, kSurfaceBgra, 1024, 2, 4096};
    assert(ack.matches(image.translation));
    RenderDescriptorLease lease;
    assert(!client.acquire(image, ack, &otherSurface, scanout, lease) && host.prepares == 1);
    auto wrong = image;
    wrong.boOffset = page;
    assert(!client.acquire(wrong, ack, &surface, scanout, lease) && host.prepares == 1);
    ++host.preparation;
    assert(!client.snapshot(address, scanout.mappedBytes).descriptor);
    assert(!client.acquire(image, ack, &surface, scanout, lease) && host.prepares == 1);
    --host.preparation;
    ++host.bytes;
    assert(!client.acquire(image, ack, &surface, scanout, lease) && host.prepares == 1);
    --host.bytes;

    RenderDescriptorLease stale;
    host.beforePrepare = [&] {
        assert(client.guard.held && !client.device.gpuGuard.held);
        IOLockLock(client.device.gpuLock);
        ++client.device.table;
        IOLockUnlock(client.device.gpuLock);
    };
    assert(!client.acquire(image, ack, &surface, scanout, stale));
    assert(!stale.backing().readPage && host.wires == 1 && host.references == 1);
    host.beforePrepare = [&] { assert(client.guard.held && !client.device.gpuGuard.held); };
    ack = client.confirm(address, scanout.mappedBytes);
    image.translation = client.snapshot(address, scanout.mappedBytes).translation;
    assert(client.acquire(image, ack, &surface, scanout, lease));
    assert(host.wires == 2 && host.references == 2 && client.freeBo(handle) == kIOReturnSuccess);
    assert(host.wires == 1 && host.references == 1);
    assert(client.importHost(replacement, 4 * page) == handle);
    assert(client.changeMap(mapOp, start, handle, page, 3 * page) == kIOReturnSuccess);
    RenderDescriptorLease reused;
    assert(!client.acquire(image, ack, &surface, scanout, reused) && replacement.prepares == 1);
    uint64_t physical = 0;
    const auto backing = lease.backing();
    assert(backing.readPage(backing.context, 0, &physical) && physical == 0x80000 + 4 * page);
    assert(backing.readPage(backing.context, page, &physical) && physical == 0x80000 + 6 * page);
    assert(lease.releaseAfterRetirement() && !host.wires && !host.references);
}

int main() {
    testPublicationAndReuse();
    testCloseAndExhaustion();
    testRangeBoundaries();
    testLiveRenderBacking();
    std::puts("[PASS] staged build34 host-map generations (CPU only)");
}
