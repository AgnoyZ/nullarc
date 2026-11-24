#include "build34_dcn_writer_receipt.h"
#include "build34_exact_callbacks.h"
#include "build34_exact_ownership.h"
#ifdef TEST_PRESENT_HANDOFF
#include "build34_dcn_present_route.h"
#endif
#ifdef TEST_SCANOUT_PINS
#include "build34_dcn_scanout_pin.h"
#endif

#include <cassert>
#include <cstdio>
#include <cstring>
#include <functional>

using namespace build34::dcn;
using namespace phx34_exact;

constexpr uint64_t kPage = 4096, kVa = 0x10000, kVaMask = (1ull << 48) - 1;
constexpr int kMaxMaps = 8;
constexpr uint32_t kIOExternalMethodArgumentsCurrentVersion = 1;
constexpr IOReturn kIOReturnBadArgument = -1, kIOReturnUnsupported = -2, kIOReturnNotFound = -3;
constexpr IOReturn kIOReturnNoMemory = -4, kIOReturnNoResources = -5, kIOReturnNotReady = -6, kIOReturnBusy = -7;

struct IOExternalMethodArguments {
    uint32_t selector = PHX34_R3_SEL_SUBMIT_RECEIPT, version = kIOExternalMethodArgumentsCurrentVersion;
    uint32_t scalarInputCount = 0, scalarOutputCount = 0;
    uint32_t structureInputSize = 0, structureOutputSize = 0, structureOutputDescriptorSize = 0;
    const void *structureInput = nullptr, *structureInputDescriptor = nullptr, *structureOutputDescriptor = nullptr;
    void *structureOutput = nullptr, *structureVariableOutputData = nullptr;
    uint32_t asyncWakePort = 0, asyncReferenceCount = 0;
    const void *asyncReference = nullptr;
};

struct IOLock { bool held = false; };
static void IOLockLock(IOLock *lock) { assert(!lock->held); lock->held = true; }
static void IOLockUnlock(IOLock *lock) { assert(lock->held); lock->held = false; }
static bool IOLockTryLock(IOLock *lock) {
    if (lock->held) return false;
    IOLockLock(lock);
    return true;
}

static bool vaCanonical(uint64_t va) { return va <= kVaMask || (va & ~kVaMask) == ~kVaMask; }
#ifdef TEST_SCANOUT_TRANSACTION
static uint64_t transactionNow = 1;
static bool transactionSleeping = false;
static uint64_t mach_absolute_time() { return transactionNow; }
static void IOSleep(unsigned ms) {
    assert(transactionSleeping && ms == 2);
    transactionNow += uint64_t{ms} * 1000000;
}
#else
static uint64_t mach_absolute_time() { return 1; }
static void IOSleep(unsigned) { assert(false); }
#endif
static void absolutetime_to_nanoseconds(uint64_t ticks, uint64_t *ns) { *ns = ticks; }
static void IOLog(const char *, ...) { assert(false); }

struct Descriptor final : IOMemoryDescriptor {
    uint64_t preparation = 9, base = 0x80000, wrongPage = UINT64_MAX;
    unsigned reads = 0;
    std::function<void()> afterRead;
    IOByteCount getLength() const override { return 4 * kPage; }
    uint64_t getPreparationID() override { return preparation; }
    uint64_t getPhysicalSegment(IOByteCount offset, IOByteCount *length, unsigned options) override {
        assert(offset < getLength() && offset % kPage == 0 && options == kIOMemoryMapperNone);
        ++reads;
        *length = kPage;
        if (afterRead) afterRead();
        return base + 2 * offset + (offset == wrongPage ? kPage : 0);
    }
#ifdef TEST_SCANOUT_PINS
    unsigned references = 1, wires = 1, prepares = 0, completes = 0;
    IOReturn prepareResult = kIOReturnSuccess, completeResult = kIOReturnSuccess;
    std::function<void()> afterPrepare, onComplete;
    IOReturn prepare() override {
        ++prepares;
        if (prepareResult != kIOReturnSuccess) return prepareResult;
        ++wires;
        if (afterPrepare) afterPrepare();
        return kIOReturnSuccess;
    }
    IOReturn complete() override {
        assert(wires);
        if (onComplete) onComplete();
        ++completes;
        if (completeResult == kIOReturnSuccess) --wires;
        return completeResult;
    }
    void retain() override { assert(references); ++references; }
    void release() override { assert(references); --references; }
#else
    IOReturn prepare() override { assert(false); return kIOReturnNotReady; }
    IOReturn complete() override { assert(false); return kIOReturnNotReady; }
    void retain() override { assert(false); }
    void release() override { assert(false); }
#endif
};

struct IOAccelPhxNativeClient;

#ifdef TEST_PRESENT_HANDOFF
using task_t = void *;
static task_t taskNow;
static task_t current_task() { return taskNow; }
constexpr IOReturn kIOReturnNotPermitted = -8, kIOReturnNotAttached = -9;
struct OSObject {
    unsigned references = 1;
    void retain() { assert(references); ++references; }
    void release() { assert(references > 1); --references; }
};
struct OSSymbol {
    const char *str;
    bool isEqualTo(const char *name) const { return !strcmp(str, name); }
};
struct IOService : OSObject {
    std::function<IOReturn(task_t, uint32_t, OSObject **)> lookup;
    bool inactive = false;
    bool isInactive() const { return inactive; }
#ifdef TEST_SCANOUT_FLIP
    const void *provider = nullptr;
    bool isPhxFramebuffer = false, isPhxBringup = false;
    std::function<void()> onRelease;
    const void *getProvider() const { return provider; }
    IOService *metaCast(const char *name) {
        return ((isPhxFramebuffer && !strcmp(name, "PhxAMDFB")) || (isPhxBringup && !strcmp(name, "PhxBringup"))) ? this : nullptr;
    }
    void release() {
        if (onRelease) onRelease();
        OSObject::release();
    }
#endif
    static IOService *accelerator;
    static const char *serviceMatching(const char *service) { return service; }
    static IOService *copyMatchingService(const char *service) {
        assert(!strcmp(service, "NMXAccel"));
        if (accelerator) accelerator->retain();
        return accelerator;
    }
    IOReturn callPlatformFunction(const char *name, bool wait, void *first, void *second, void *third, void *fourth) {
        OSSymbol symbol{name};
        return callPlatformFunction(&symbol, wait, first, second, third, fourth);
    }
    virtual IOReturn callPlatformFunction(const OSSymbol *name, bool wait, void *first, void *second, void *third, void *fourth) {
        assert(!wait && first && second && third && !fourth && name->isEqualTo(BUILD34_DCN_PRESENT_LOOKUP));
        return lookup(second, *static_cast<uint32_t *>(first), static_cast<OSObject **>(third));
    }
};
IOService *IOService::accelerator = nullptr;
struct Phx34ScopedReference {
    OSObject *object;
    explicit Phx34ScopedReference(OSObject *value, bool take = true) : object(value) { if (object && take) object->retain(); }
    ~Phx34ScopedReference() { if (object) object->release(); }
};
#endif

#ifdef TEST_SCANOUT_DMA
#include "build34_dcn_scanout_dma.h"
#ifdef TEST_SCANOUT_FLIP
#include "build34_dcn_flip_commit.h"
#include "build34_dcn_gpu_write_history.h"
#include "build34_dcn_gpu_permissions.h"
using addr64_t = uint64_t;
constexpr uint64_t kPtAddrMask = 0x0000FFFFFFFFF000ull, kPteSysFlags = 0x0004000000000077ull;
constexpr IOReturn kIOReturnVMError = -10;
constexpr uint32_t kFirstUserVmid = 8, kNumUserVmids = 3;
constexpr uint32_t kRegCtx0BaseLo = 0x2953, kRegCtx0Cntl = 0x28e8;
constexpr uint32_t kRegCtx0StartLo = 0x2973, kRegCtx0EndLo = 0x2993;
static void flushLine(const volatile void *) {}
#endif
#ifdef TEST_SCANOUT_BAR5
#include "build34_dcn_bar5.h"
#ifdef TEST_SCANOUT_FB_LEASE
#include "build34_dcn_framebuffer_route.h"
#endif
constexpr uint32_t kIOPCIConfigBaseAddress5 = 0x24, kIOPCIConfigCommand = 4, kIOPCIConfigVendorID = 0;
struct Bar5Resource : IOBufferMemoryDescriptor {
    uint64_t bytes = dcnPeers::kMmioBytes;
    uint64_t getPhysicalAddress() const { return physical; }
    IOByteCount getLength() const override { return bytes; }
};
struct IOMemoryMap {
    Bar5Resource *resource;
    uint64_t address, bytes, physical;
    task_t task = kernel_task;
    uint64_t getVirtualAddress() const { return address; }
    uint64_t getLength() const { return bytes; }
    uint64_t getPhysicalAddress() const { return physical; }
    IOMemoryDescriptor *getMemoryDescriptor() const { return resource; }
    task_t getAddressTask() const { return task; }
};
static unsigned bar5Delays = 0;
static void IODelay(unsigned us) { assert(us == 1); ++bar5Delays; }
#endif
struct IOPCIDevice : IOService {
    IOMapper *mapper = nullptr;
    unsigned mapperLookups = 0;
    uint64_t directGeneration = 0;
    std::function<bool(const IOMemoryDescriptor &, uint64_t, uint64_t, DcnDirectUse)> directEvidence;
#ifdef TEST_SCANOUT_FLIP
    HubpFlipRoute *route = nullptr;
#endif
#ifdef TEST_SCANOUT_BAR5
    Bar5Resource *bar5 = nullptr;
    uint16_t command = 2;
    uint32_t identity = 0x19001002;
    uint16_t configRead16(uint32_t reg) const { assert(reg == kIOPCIConfigCommand); return command; }
    uint32_t configRead32(uint32_t reg) const { assert(reg == kIOPCIConfigVendorID); return identity; }
    Bar5Resource *getDeviceMemoryWithRegister(uint32_t reg) const { assert(reg == kIOPCIConfigBaseAddress5); return bar5; }
#endif
};

IOMapper *IOMapper::copyMapperForDevice(IOPCIDevice *device) {
    assert(device && !device->inactive);
    ++device->mapperLookups;
    if (device->mapper) device->mapper->retain();
    return device->mapper;
}
#endif

struct PhxBringup
#ifdef TEST_PRESENT_HANDOFF
    : IOService
#endif
{
#ifdef TEST_SCANOUT_DMA
    IOPCIDevice pciObject;
    IOPCIDevice *pci = &pciObject;
#endif
#ifdef TEST_SCANOUT_BAR5
    IOMemoryMap *mmio = nullptr;
    CallbackGate<1> exactRawWriters;
#endif
    static constexpr uint32_t kMaxCtx = 4;
    struct VmCtx {
        uint64_t generation = 5, newest = 0, queueSequence[2]{}, queueGeneration[2]{};
        const void *client = nullptr;
        bool closing = false, busy = false;
#ifdef TEST_SCANOUT_FLIP
        uint64_t phys = 0x1e0000;
        uint32_t hw = 0, pages = 0, used = 0;
        static constexpr uint32_t kPtChunks = 4;
        IOBufferMemoryDescriptor *chunk[kPtChunks]{};
        uint64_t chunkPhys[kPtChunks]{};
#endif
    } vm[kMaxCtx];
    struct GpuQueue {
        bool ready = true;
        uint32_t head = 0, tail = 0;
        uint64_t fseq[64]{};
    } gq[2];
    struct { bool active = false, terminal = false; } watchdogRecovery;
    CallbackGate<> exactCallbacks;
    IOLock guard;
    IOLock *gpuLock = &guard;
    uint64_t gSeq = 0, exactQueueSubmitted[2]{}, exactQueueGeneration[2]{3, 4}, done[2]{};
    bool exactQueueLive[2]{true, true}, exactStopped = false, isSleeping = false, exactVMFault = false;
#ifdef TEST_PRESENT_HANDOFF
    uint64_t exactInvalidationEpoch = 0;
    bool exactQueueAdopted[2]{true, true};
    struct ExactOverlapSnapshot {
        struct Queue { uint64_t generation, submitted, completed; } queues[2];
    };
    bool exactGlobalRetiredLocked(uint64_t &, ExactOverlapSnapshot * = nullptr);
    bool readExactFence32(uint32_t queue, uint64_t *out) const {
        assert(guard.held);
        if (!gq[queue].ready || !exactQueueLive[queue]) return false;
        *out = done[queue];
        return true;
    }
    struct LegacyClientSlot { IOAccelPhxNativeClient *client; bool pending; } legacyClients[kMaxCtx]{};
    IOReturn callPlatformFunction(const OSSymbol *, bool, void *, void *, void *, void *) override;
    bool exactClaimCurrentLocked(void *) { assert(false); return false; }
    bool requestLegacyClose(IOAccelPhxNativeClient *);
    void invalidateExactQueues() { exactQueueLive[0] = exactQueueLive[1] = false; }
    void sealStoppedQueues();
#endif
    IOReturn dispatchResult = kIOReturnSuccess, mapResult = kIOReturnSuccess;
    unsigned dispatches = 0;
    std::function<void()> beforeDispatch;
#ifdef TEST_SCANOUT_FLIP
    uint64_t submitTime = 0;
    std::function<void()> onSubmitSleep;
#endif

    bool exactAdmissionClosed() const { return exactCallbacks.closed(); }
    bool gpuReady() const { return true; }
    bool debugEnabled() const { return false; }
    VmCtx *vmCtx(uint32_t handle) { return handle && handle <= kMaxCtx && vm[handle - 1].busy ? &vm[handle - 1] : nullptr; }
    VmCtx *vmOwned(uint32_t, uint64_t, const void *, bool = false);
    bool vmWorkCurrent(const VmCtx &) const;
    // WRITER_SERVICE

#ifdef TEST_SCANOUT_FLIP
    static constexpr uint32_t kPtChunks = VmCtx::kPtChunks, kPtChunkPages = 2, kPtChunkBytes = kPtChunkPages * kPage;
    unsigned pteLookups = 0, gpuVmWrites = 0;
    uint64_t lastPte = 0;
    uint64_t *testGpuLeaf = nullptr;
    std::function<DcnGpuPermissionAck(const DcnGpuPermissionUse &, DcnGpuPermissionPhase)> permission;
    struct HwVmid { uint32_t ctx; uint64_t generation, lastSeq, lastUse; } hwv[kNumUserVmids]{};
    uint64_t hwTick = 0;
    bool isolationEvidence = true;
    static bool proveIsolation(const PhxBringup &device, PhysicalPageSet pages) {
        assert(device.guard.held && pages.count == 2);
        return device.isolationEvidence;
    }
    uint64_t *vmPte(VmCtx &, uint64_t va, bool allocate) {
        assert(guard.held && allocate);
        ++pteLookups;
        return testGpuLeaf ? testGpuLeaf + ((va / kPage) % 512) : &lastPte;
    }
    bool vmFlushTlbChecked(uint32_t slot) { assert(guard.held && slot >= kFirstUserVmid); return true; }
    void wreg(uint32_t, uint32_t) { assert(guard.held); ++gpuVmWrites; }
    uint32_t vmBind(uint32_t, uint64_t, const void *, uint64_t);
    bool vmidFree(uint32_t, uint64_t, const void *, uint64_t);
    IOReturn guardedVmMap(uint32_t, uint64_t, const void *, uint64_t, IOMemoryDescriptor *, uint64_t, uint64_t);
#endif
    IOReturn vmMap(uint32_t, uint64_t, const void *, uint64_t, IOMemoryDescriptor *, uint64_t, uint64_t) {
        return mapResult;
    }
    IOReturn vmUnmap(uint32_t, uint64_t, const void *, uint64_t, uint64_t) { return mapResult; }
    uint64_t recordQueued(uint32_t queue) {
        assert(guard.held);
        auto &entry = gq[queue];
        assert(entry.tail - entry.head < 63);
        const uint64_t sequence = exactQueueSubmitted[queue] = ++gSeq;
        entry.fseq[entry.tail++ & 63] = sequence;
        return sequence;
    }
    IOReturn gpuSubmit(uint32_t handle, uint64_t generation, const void *client, bool gfx, const uint64_t *,
                       const uint32_t *, uint32_t, uint64_t *seq, Registry *registry, Ticket ticket, const void *) {
        if (beforeDispatch) beforeDispatch();
        if (dispatchResult != kIOReturnSuccess) return dispatchResult;
#ifdef TEST_SCANOUT_FLIP
        const auto mach_absolute_time = [&] { return submitTime; };
        const auto absolutetime_to_nanoseconds = [](uint64_t elapsed, uint64_t *out) { *out = elapsed; };
        const auto IOSleep = [&](unsigned ms) {
            assert(ms == 1 && !guard.held && onSubmitSleep);
            onSubmitSleep();
        };
        const auto start = mach_absolute_time();
        for (;;) {
            IOLockLock(gpuLock);
            // DCN_SUBMIT_GATE
            break;
        }
#else
        IOLockLock(gpuLock);
#endif
        assert(vmOwned(handle, generation, client));
        const uint32_t queue = gfx ? 1 : 0;
        auto &ctx = vm[handle - 1];
        ctx.newest = ctx.queueSequence[queue] = *seq = recordQueued(queue);
        ctx.queueGeneration[queue] = exactQueueGeneration[queue];
        assert(!registry || registry->publish(ticket, {*seq, exactQueueGeneration[queue], queue}) == Status::Ok);
        IOLockUnlock(gpuLock);
        ++dispatches;
        return kIOReturnSuccess;
    }
    Status observeExact(Registry &registry, Ticket ticket, const CallbackGate<> &client, const void *) {
        const QueueObservation queues[]{
            {exactQueueGeneration[0], exactQueueSubmitted[0], static_cast<uint32_t>(done[0]), exactQueueLive[0], false},
            {exactQueueGeneration[1], exactQueueSubmitted[1], static_cast<uint32_t>(done[1]), exactQueueLive[1], false},
        };
        return registry.observe(ticket, !exactAdmissionClosed() && !client.closed(), queues);
    }
    uint64_t exactEventStamp(const Receipt &) { assert(false); return UINT64_MAX; }
    bool parkExactEvent(const Receipt &, uint64_t, const CallbackGate<> &, uint64_t, uint64_t) { assert(false); return false; }
};

struct IOAccelPhxNativeClient
#ifdef TEST_PRESENT_HANDOFF
    : OSObject
#endif
{
    // WRITER_TYPES
    // WRITER_CLIENT
    PhxBringup device;
    PhxBringup *owner = &device;
    IOLock guard;
    IOLock *lock = &guard;
    Bo boTable[5]{}, *bos = boTable;
    Map mapTable[kMaxMaps]{}, *maps = mapTable;
    Registry exactRegistry{0}, *exactOwnership = &exactRegistry;
    OwnerEpochs owners;
    CallbackGate<> exactClientCallbacks;
    bool ctx[PHXN_MAX_CTX + 1]{}, hello = true, exactClientPinned = true, exactRequested = true;
    bool boCleanupFault = false, mayHaveLogicalMappings = false, exactResourcesExposed = false;
    uint32_t vmid = 1, legacyState = 2, pendFenceHandle = 0, pendFenceOffset = 0;
    uint64_t vmGeneration = 5, lastSeq = 0, emitted = 0, pendFenceSeq = 0;
#ifdef TEST_PRESENT_HANDOFF
    task_t task = this;
#endif

    IOAccelPhxNativeClient() {
        assert(exactRegistry.bind(owner, this, owners) == Status::Ok);
        device.vm[0].client = this;
        device.vm[0].busy = true;
        ctx[1] = true;
#ifdef TEST_PRESENT_HANDOFF
        device.legacyClients[0] = {this, false};
#endif
    }

    Bo *findBo(uint32_t);
    IOReturn doGemVa(IOExternalMethodArguments *);
    IOReturn doCtx(IOExternalMethodArguments *);
    IOReturn doExactSubmit(IOExternalMethodArguments *);
    IOReturn submitExactReceipt(const void *, uint32_t, Ticket &, Receipt &, bool &);
    Status waitExactReceipt(Ticket, const Receipt &, uint64_t, uint64_t);
    Status ackExactReceipt(Ticket, const Receipt &);
    bool ensureVmid() const { return vmid != 0; }
    bool nativeMappingsReady() const { return true; }
    void flushBos() { assert(guard.held); }
    bool ibCovered(uint64_t, uint64_t) const { return true; }

    IOReturn changeMap(uint32_t op, uint64_t va, uint32_t handle, uint64_t offset, uint64_t bytes) {
        const phxn_gem_va request{handle, 0, op, 0, va, offset, bytes, 0, 0, 0, 0};
        IOExternalMethodArguments args;
        args.structureInput = &request;
        args.structureInputSize = sizeof(request);
        IOLockLock(lock);
        const auto result = doGemVa(&args);
        IOLockUnlock(lock);
        return result;
    }
    void freeContext() {
        phxn_ctx request{}, reply{};
        request.op = PHX_AMDGPU_CTX_OP_FREE_CTX;
        request.ctx_id = 1;
        IOExternalMethodArguments args;
        args.structureInput = &request;
        args.structureOutput = &reply;
        args.structureInputSize = args.structureOutputSize = sizeof(request);
        IOLockLock(lock);
        assert(doCtx(&args) == kIOReturnSuccess);
        IOLockUnlock(lock);
    }
};

// WRITER_METHODS

struct Frame {
    Descriptor host, present;
    IOAccelPhxNativeClient client;
    build34_dcn_writer_request request{};
    PresentCopyBacking copy{};

    Frame() {
        client.boTable[1] = {&host, host.getLength(), 2, 0, nullptr, true};
        client.boTable[2] = {&host, host.getLength(), 2, 0, nullptr, true};
        assert(client.changeMap(PHX_AMDGPU_VA_OP_MAP, kVa, 1, kPage, 2 * kPage) == kIOReturnSuccess);
        present.base += 2 * kPage;
        const uint32_t width = 64, height = 17, pitch = width * 4;
        copy = observePreparedCopyBacking(this, &present, &present, kSurfaceBgra, width, height, pitch, width, height);
        assert(copy.slice.bytes == 2 * kPage);
        request.submit.version = PHX34_R3_WIRE_VERSION;
        request.submit.size = sizeof(request);
        request.submit.owner = 1;
        request.submit.submit.abi = PHXN_ABI_VERSION;
        request.submit.submit.ctx_id = 1;
        request.submit.submit.num_ibs = 2;
        request.submit.ibs[0].va_start = 0x30000;
        request.submit.ibs[0].ib_bytes = 32;
        request.submit.ibs[0].ip_type = PHX_AMDGPU_HW_IP_GFX;
        request.submit.ibs[0].flags = PHX_AMDGPU_IB_FLAG_PREAMBLE;
        request.submit.ibs[1].va_start = 0x31000;
        request.submit.ibs[1].ib_bytes = 64;
        request.submit.ibs[1].ip_type = PHX_AMDGPU_HW_IP_GFX;
        request.writer = {{0x31000, 64, 1}, {kVa, 2 * kPage, 1, 0}};
    }

    phx34_r3_reply submit(IOReturn expected = kIOReturnSuccess) {
        phx34_r3_reply reply{};
        uint8_t unaligned[sizeof(request) + 1];
        memcpy(unaligned + 1, &request, sizeof(request));
        IOExternalMethodArguments args;
        args.structureInput = unaligned + 1;
        args.structureInputSize = request.submit.size;
        args.structureOutput = &reply;
        args.structureOutputSize = sizeof(reply);
        assert(client.doExactSubmit(&args) == expected);
        return reply;
    }

    build34_dcn_native_submit nominate() {
        const auto reply = submit();
        assert(reply.status == PHX34_R3_REPLY_WRITER_SUBMITTED);
        return {reply.sequence, reply.owner, reply.serial, reply.generation, reply.slot, reply.queue, 1};
    }
    Status wait(build34_dcn_native_submit native) {
        return client.waitExactReceipt({native.owner, native.serial, native.slot},
                                       {native.sequence, native.generation, native.queue}, 0, 0);
    }
    Status ack(build34_dcn_native_submit native) {
        return client.ackExactReceipt({native.owner, native.serial, native.slot},
                                      {native.sequence, native.generation, native.queue});
    }
    bool probe(build34_dcn_native_submit native) {
        return client.probeExactWriterBacking(native, request.writer.range, copy);
    }
};

static void completionAndPages() {
    Frame frame;
    const auto writer = frame.nominate();
    assert(!frame.probe(writer) && !frame.present.reads);
    assert(frame.wait(writer) == Status::TimedOut);
    frame.client.device.done[1] = writer.sequence;
    auto forgery = writer;
    ++forgery.serial;
    assert(frame.wait(forgery) != Status::Complete && !frame.probe(writer));
    assert(frame.wait(writer) == Status::Complete && frame.probe(writer));
    assert(frame.present.reads == 2 && frame.host.reads == 2);
    assert(frame.ack(writer) == Status::Ok && frame.client.exactRegistry.occupied() == 0);
    assert(frame.probe(writer));
    assert(frame.wait(writer) != Status::Complete);

    forgery = writer;
    ++forgery.context;
    frame.client.ctx[2] = true;
    assert(!frame.probe(forgery));
    forgery = writer;
    ++forgery.owner;
    assert(!frame.probe(forgery));
    auto wrongRange = frame.request.writer.range;
    wrongRange.bo = 2;
    assert(!frame.client.probeExactWriterBacking(writer, wrongRange, frame.copy));
    frame.present.wrongPage = kPage;
    assert(!frame.probe(writer));
    frame.present.wrongPage = UINT64_MAX;
    frame.client.guard.held = true;
    assert(!frame.probe(writer));
    frame.client.guard.held = false;
    frame.client.device.guard.held = true;
    assert(!frame.probe(writer));
    frame.client.device.guard.held = false;
    ++frame.host.preparation;
    assert(!frame.probe(writer));
}

static void newerAndRacingCompletions() {
    Frame frame;
    const auto early = frame.nominate();
    const auto late = frame.nominate();
    frame.client.device.done[1] = early.sequence;
    assert(frame.ack(early) == Status::Ok);
    assert(!frame.probe(early) && !frame.probe(late));
    frame.client.device.done[1] = late.sequence;
    assert(frame.ack(late) == Status::Ok && frame.probe(late));
    const auto reused = frame.nominate();
    assert(reused.slot == early.slot && reused.serial != early.serial);
    assert(frame.ack(early) != Status::Ok && !frame.probe(reused));
    frame.client.device.done[1] = reused.sequence;
    assert(frame.wait(reused) == Status::Complete && frame.probe(reused));
    assert(!frame.probe(late));

    frame.present.afterRead = [&] {
        assert(frame.client.guard.held && !frame.client.device.guard.held);
        ++frame.client.device.exactQueueGeneration[1];
    };
    assert(!frame.probe(reused));
}

static void refusalAndInvalidation() {
    Frame frame;
    const auto first = frame.nominate();
    frame.client.device.done[1] = first.sequence;
    assert(frame.ack(first) == Status::Ok && frame.probe(first));
    frame.client.device.dispatchResult = kIOReturnBusy;
    frame.submit(kIOReturnBusy);
    assert(!frame.probe(first) && !frame.client.exactWriter.native.sequence && frame.client.device.dispatches == 1);
    frame.client.device.dispatchResult = kIOReturnSuccess;

    const auto original = frame.request;
    for (unsigned fault = 0; fault < 7; ++fault) {
        frame.request = original;
        switch (fault) {
        case 0: frame.request.writer.ib.index = 0; break;
        case 1: frame.request.writer.ib.bytes -= 4; break;
        case 2: frame.request.submit.ibs[0].va_start = frame.request.writer.ib.va; break;
        case 3: frame.request.writer.range.bo = 2; break;
        case 4: frame.request.writer.range.bytes += kPage; break;
        case 5: frame.request.submit.ibs[1].flags |= PHX_AMDGPU_IB_FLAG_PREAMBLE; break;
        case 6:
            for (unsigned index = 0; index < 2; ++index) frame.request.submit.ibs[index].ip_type = PHX_AMDGPU_HW_IP_COMPUTE;
            break;
        }
        const auto accepted = frame.submit();
        assert(accepted.status == PHX34_R3_REPLY_SUBMITTED && !frame.client.exactWriter.native.sequence);
    }

    frame.request = original;
    const auto last = frame.nominate();
    frame.client.device.done[1] = last.sequence;
#ifdef TEST_PRESENT_HANDOFF
    assert(frame.wait(last) == Status::Complete && !frame.probe(last));
    frame.client.device.done[0] = frame.client.device.exactQueueSubmitted[0];
#endif
    assert(frame.ack(last) == Status::Ok && frame.probe(last));
    frame.request.submit.size = sizeof(frame.request.submit);
    assert(frame.submit().status == PHX34_R3_REPLY_SUBMITTED && !frame.probe(last));
    frame.request = original;
    frame.client.device.beforeDispatch = [&] { ++frame.host.preparation; };
    assert(frame.submit().status == PHX34_R3_REPLY_SUBMITTED && !frame.client.exactWriter.native.sequence);
}

static void remapCloseAndPressure() {
    Frame frame;
    const auto writer = frame.nominate();
    frame.client.device.done[1] = writer.sequence;
    assert(frame.ack(writer) == Status::Ok && frame.probe(writer));
    const auto previousGeneration = frame.client.mapTable[0].writerGeneration;
    assert(frame.client.changeMap(PHX_AMDGPU_VA_OP_UNMAP, kVa, 1, kPage, 2 * kPage) == kIOReturnBusy);
    assert(!frame.probe(writer));
    assert(frame.client.changeMap(PHX_AMDGPU_VA_OP_MAP, kVa + 3 * kPage, 1, kPage, 2 * kPage) == kIOReturnSuccess);
    assert(frame.client.mapTable[1].writerGeneration > previousGeneration);
    const auto current = frame.nominate();
    frame.client.device.done[1] = current.sequence;
    assert(frame.ack(current) == Status::Ok && frame.probe(current));
    Ticket reserved{};
    for (unsigned index = 0; index < Registry::capacity; ++index)
        assert(frame.client.exactRegistry.reserve(reserved) == Status::Ok);
    assert(frame.submit().status == PHX34_R3_REPLY_RECEIPT_FULL && !frame.probe(current));

    Frame closing;
    const auto previous = closing.nominate();
    closing.client.device.done[1] = previous.sequence;
    assert(closing.ack(previous) == Status::Ok && closing.probe(previous));
    closing.client.freeContext();
    closing.client.ctx[1] = true;
    assert(!closing.probe(previous));
    const auto newest = closing.nominate();
    closing.client.device.done[1] = newest.sequence;
    assert(closing.ack(newest) == Status::Ok && closing.probe(newest));
    closing.client.exactClientCallbacks.close();
    assert(!closing.probe(newest));
}

#ifdef TEST_PRESENT_HANDOFF
static void drainAcrossPresent() {
    Frame frame;
    auto &device = frame.client.device;
    auto otherComputeSubmit = [&] {
        IOLockLock(device.gpuLock);
        const auto sequence = device.recordQueued(0);
        IOLockUnlock(device.gpuLock);
        return sequence;
    };
    const auto older = otherComputeSubmit();
    const auto writer = frame.nominate();
    device.done[1] = writer.sequence;
    assert(frame.wait(writer) == Status::Complete);
    assert(!frame.probe(writer) && !frame.host.reads);
    device.done[0] = older;
    device.exactQueueAdopted[0] = false;
    assert(!frame.probe(writer) && !frame.host.reads);
    device.exactQueueAdopted[0] = true;
    assert(frame.probe(writer) && frame.host.reads == 2);

    frame.host.afterRead = [&] {
        assert(frame.client.guard.held && !device.guard.held);
        ++device.exactQueueGeneration[0];
    };
    assert(!frame.probe(writer) && frame.host.reads == 4);
    frame.host.afterRead = [&] { ++device.exactInvalidationEpoch; };
    assert(!frame.probe(writer) && frame.host.reads == 6);

    frame.host.afterRead = [&] { device.done[0] = otherComputeSubmit(); };
    assert(!frame.probe(writer) && frame.host.reads == 8);
    frame.host.afterRead = nullptr;
    assert(!frame.probe(writer) && frame.host.reads == 8);
    const auto replacement = frame.nominate();
    device.done[1] = replacement.sequence;
    assert(frame.ack(replacement) == Status::Ok && frame.probe(replacement) && frame.host.reads == 10);
}

static void exercisePresentHandoff() {
    Frame frame;
    auto &client = frame.client;
    taskNow = client.task;
    IOService accelerator;
    IOService::accelerator = &accelerator;
    OSObject surface, otherSurface;
    OSObject *resolved = &surface;
    unsigned lookups = 0;
    std::function<void()> duringLookup;
    accelerator.lookup = [&](task_t task, uint32_t id, OSObject **out) {
        assert(!client.guard.held && !client.device.guard.held && task == client.task && id == 17);
        ++lookups;
        if (duringLookup) duringLookup();
        resolved->retain();
        *out = resolved;
        return kIOReturnSuccess;
    };
    auto writer = frame.nominate();
    build34_dcn_present_offer offer{BUILD34_DCN_PRESENT_VERSION, sizeof(offer), writer, frame.request.writer.range, 17, 0};
    IOExternalMethodArguments args;
    args.selector = BUILD34_DCN_SEL_OFFER;
    args.structureInput = &offer;
    args.structureInputSize = sizeof(offer);
    assert(client.doDcnPresentOffer(&args) == kIOReturnNotReady && !lookups);
    client.device.done[1] = writer.sequence;
    assert(frame.ack(writer) == Status::Ok);
    taskNow = &otherSurface;
    assert(client.doDcnPresentOffer(&args) == kIOReturnNotPermitted && !lookups);
    taskNow = client.task;
    --args.structureInputSize;
    assert(client.doDcnPresentOffer(&args) == kIOReturnBadArgument && !lookups);
    ++args.structureInputSize;
    offer.reserved = 1;
    assert(client.doDcnPresentOffer(&args) == kIOReturnBadArgument && !lookups);
    offer.reserved = 0;
    ++offer.native.serial;
    assert(client.doDcnPresentOffer(&args) == kIOReturnNotReady && !lookups);
    offer.native = writer;
    assert(client.doDcnPresentOffer(&args) == kIOReturnSuccess && lookups == 1 && surface.references == 2);
    frame.copy.surface = &otherSurface;
    const OSSymbol probe{BUILD34_DCN_PRESENT_PROBE};
    assert(client.device.callPlatformFunction(&probe, false, &frame.copy, nullptr, nullptr, nullptr) == kIOReturnNotReady);
    assert(surface.references == 2 && !frame.host.reads);
    frame.copy.surface = &surface;
    IOLockLock(client.device.gpuLock);
    assert(!client.device.checkDcnPresent(frame.copy) && surface.references == 2 && !frame.host.reads);
    IOLockUnlock(client.device.gpuLock);
    assert(client.device.callPlatformFunction(&probe, false, &frame.copy, nullptr, nullptr, nullptr) == kIOReturnSuccess);
    assert(!client.device.checkDcnPresent(frame.copy) && surface.references == 1 && frame.host.reads == 2);
    assert(client.doDcnPresentOffer(&args) == kIOReturnNotReady && lookups == 1);

    offer.native = frame.nominate();
    client.device.done[1] = offer.native.sequence;
    assert(frame.wait(offer.native) == Status::Complete);
    duringLookup = [&] { frame.nominate(); };
    assert(client.doDcnPresentOffer(&args) == kIOReturnNotReady && lookups == 2 && surface.references == 1);
    duringLookup = nullptr;
    offer.native = frame.nominate();
    client.device.done[1] = offer.native.sequence;
    assert(frame.wait(offer.native) == Status::Complete);
    assert(client.doDcnPresentOffer(&args) == kIOReturnSuccess && surface.references == 2);
    frame.nominate();
    assert(!client.device.checkDcnPresent(frame.copy) && surface.references == 1 && frame.host.reads == 2);

    offer.native = frame.nominate();
    client.device.done[1] = offer.native.sequence;
    assert(frame.ack(offer.native) == Status::Ok);
    assert(client.doDcnPresentOffer(&args) == kIOReturnSuccess && surface.references == 2);
    offer.native = frame.nominate();
    client.device.done[1] = offer.native.sequence;
    assert(frame.ack(offer.native) == Status::Ok);
    resolved = &otherSurface;
    assert(client.doDcnPresentOffer(&args) == kIOReturnSuccess && surface.references == 1 && otherSurface.references == 2);
    client.device.sealStoppedQueues();
    assert(otherSurface.references == 1 && client.references == 1 && accelerator.references == 1);
    IOService::accelerator = nullptr;
}

static void closeDuringPresent(bool inLookup) {
    Frame frame;
    auto &client = frame.client;
    taskNow = client.task;
    IOService accelerator;
    IOService::accelerator = &accelerator;
    OSObject surface;
    auto close = [&] {
        if (client.exactClientCallbacks.close()) assert(client.device.requestLegacyClose(&client));
    };
    accelerator.lookup = [&](task_t, uint32_t, OSObject **out) {
        if (inLookup) close();
        surface.retain();
        *out = &surface;
        return kIOReturnSuccess;
    };
    auto writer = frame.nominate();
    client.device.done[1] = writer.sequence;
    assert(frame.ack(writer) == Status::Ok);
    build34_dcn_present_offer offer{BUILD34_DCN_PRESENT_VERSION, sizeof(offer), writer, frame.request.writer.range, 17, 0};
    IOExternalMethodArguments args;
    args.selector = BUILD34_DCN_SEL_OFFER;
    args.structureInput = &offer;
    args.structureInputSize = sizeof(offer);
    frame.copy.surface = &surface;
    if (inLookup) {
        assert(client.doDcnPresentOffer(&args) == kIOReturnNotReady);
    } else {
        assert(client.doDcnPresentOffer(&args) == kIOReturnSuccess && surface.references == 2);
        frame.host.afterRead = close;
        assert(!client.device.checkDcnPresent(frame.copy));
    }
    assert(client.exactClientCallbacks.closed() && !client.device.checkDcnPresent(frame.copy));
    assert(surface.references == 1 && client.references == 1 && accelerator.references == 1);
    IOService::accelerator = nullptr;
}
#endif

#ifdef TEST_SCANOUT_PINS
struct ScanoutFixture {
    Frame frame;
    IOAccelPhxNativeClient &client = frame.client;
    PhxBringup &device = client.device;
    IOService accelerator;
    OSObject surface;
    const OSSymbol prepare{BUILD34_DCN_PIN_PREPARE}, cancel{BUILD34_DCN_PIN_CANCEL};

    ScanoutFixture() {
        taskNow = client.task;
        IOService::accelerator = &accelerator;
        frame.copy.surface = &surface;
        accelerator.lookup = [&](task_t task, uint32_t id, OSObject **out) {
            assert(task == client.task && id == 21);
            surface.retain();
            *out = &surface;
            return kIOReturnSuccess;
        };
    }
    ~ScanoutFixture() {
        IOService::accelerator = nullptr;
#ifdef TEST_SCANOUT_DMA
        DcnAllocationStub::reset();
#endif
    }

    void offer() {
        const auto writer = frame.nominate();
        device.done[1] = writer.sequence;
        assert(frame.ack(writer) == Status::Ok);
        build34_dcn_present_offer offer{BUILD34_DCN_PRESENT_VERSION, sizeof(offer), writer, frame.request.writer.range, 21, 0};
        IOExternalMethodArguments args;
        args.selector = BUILD34_DCN_SEL_OFFER;
        args.structureInput = &offer;
        args.structureInputSize = sizeof(offer);
        assert(client.doDcnPresentOffer(&args) == kIOReturnSuccess);
    }
    IOReturn pin(ScanoutPinToken &out) {
        return device.callPlatformFunction(&prepare, false, &frame.copy, &out, nullptr, nullptr);
    }
    IOReturn cancelPin(ScanoutPinToken token) {
        return device.callPlatformFunction(&cancel, false, &token, nullptr, nullptr, nullptr);
    }
};

static void scanoutPinLifetime() {
    ScanoutFixture fixture;
    auto &host = fixture.frame.host;
    ScanoutPinToken first{}, second{}, third{};
    fixture.offer();
    assert(fixture.pin(first) == kIOReturnSuccess && first.provider == &fixture.device && first.serial);
    assert(host.references == 2 && host.wires == 2 && fixture.surface.references == 2 && fixture.client.references == 2);
    assert(fixture.pin(second) == kIOReturnNotReady && !second.serial);
    fixture.offer();
    assert(fixture.pin(second) == kIOReturnSuccess && second.serial > first.serial);
    fixture.offer();
    assert(fixture.pin(third) == kIOReturnNoResources && !third.serial);
    assert(fixture.cancelPin({&fixture.surface, first.serial}) == kIOReturnBadArgument);
    IOLockLock(fixture.client.lock);
    assert(fixture.cancelPin(first) == kIOReturnBusy);
    IOLockUnlock(fixture.client.lock);
    assert(fixture.cancelPin(first) == kIOReturnSuccess && fixture.pin(third) == kIOReturnSuccess);
    assert(third.serial > second.serial && fixture.cancelPin(first) == kIOReturnNotFound);
    assert(fixture.cancelPin(second) == kIOReturnSuccess);

    fixture.client.exactClientCallbacks.close();
    assert(fixture.device.requestLegacyClose(&fixture.client));
    assert(host.complete() == kIOReturnSuccess);
    host.release();
    fixture.device.sealStoppedQueues();
    assert(host.references == 1 && host.wires == 1 && fixture.client.references == 2 && fixture.surface.references == 2);
    assert(fixture.cancelPin(third) == kIOReturnSuccess);
    assert(!host.references && !host.wires && fixture.client.references == 1 && fixture.surface.references == 1);
}

static void scanoutPinFailedPrepareAndRollback() {
    ScanoutFixture fixture;
    auto &host = fixture.frame.host;
    ScanoutPinToken token{};
    fixture.offer();
    host.prepareResult = kIOReturnNotReady;
    assert(fixture.pin(token) == kIOReturnNotReady && !token.serial);
    assert(host.references == 1 && host.wires == 1 && !host.completes && fixture.surface.references == 1);
    host.prepareResult = kIOReturnSuccess;
    fixture.offer();
    host.afterPrepare = [&] {
        assert(fixture.client.guard.held && !fixture.device.guard.held);
        ScanoutPinToken reentrant{};
        assert(fixture.pin(reentrant) == kIOReturnBusy && !reentrant.serial);
        ++fixture.device.exactInvalidationEpoch;
    };
    assert(fixture.pin(token) == kIOReturnNotReady && !token.serial);
    assert(host.references == 1 && host.wires == 1 && host.completes == 1 && fixture.surface.references == 1);

    host.completeResult = kIOReturnNotReady;
    fixture.offer();
    assert(fixture.pin(token) == kIOReturnNotReady && !token.serial);
    assert(host.references == 2 && host.wires == 2 && host.completes == 2 && fixture.surface.references == 2);
    host.completeResult = kIOReturnSuccess;
    host.afterPrepare = nullptr;
    fixture.offer();
    assert(fixture.pin(token) == kIOReturnSuccess && token.serial);
    ScanoutPinToken overflow{};
    fixture.offer();
    assert(fixture.pin(overflow) == kIOReturnNoResources && !overflow.serial);
    assert(fixture.device.dcnPins[1].descriptor.beginDisplayUse());
    assert(!fixture.device.dcnPins[1].descriptor.beginDisplayUse());
    fixture.device.sealStoppedQueues();
    assert(fixture.cancelPin(token) == kIOReturnNotFound && host.completes == 2);
    assert(host.references == 3 && host.wires == 3 && fixture.surface.references == 3);
}
#endif

#ifdef TEST_SCANOUT_DMA
enum class DmaFault { None, AlternateDescriptor, WrongOffset, WrongPage, NoMappedPage, FailedPrepare, ChangedEpoch, NoPlanMemory };
enum class DmaCleanupFault { None, Complete, ConfirmUnmap, Clear, PresentComplete };

static ScanoutDmaMapper mapperContract(IOPCIDevice &device, IOMapper &mapper) {
    assert(device.mapper == &mapper && mapper.references >= 2);
    return {&mapper,
        [](IOMapper &selected, const IODMACommand &command, uint64_t address, uint64_t &physical) {
            return selected.resolve(command, address, physical);
        },
        [](IOMapper &selected, const IODMACommand &command) { return selected.confirmUnmap(command); }};
}

static DcnDirectDomain directContract(IOPCIDevice &device) {
    return {&device, device.directGeneration,
        [](IOService &selected, uint64_t generation) {
            return static_cast<IOPCIDevice &>(selected).directGeneration == generation;
        },
        [](IOService &selected, uint64_t, const IOMemoryDescriptor &descriptor, uint64_t offset, uint64_t address,
           DcnDirectUse use) {
            auto &pci = static_cast<IOPCIDevice &>(selected);
            assert(pci.references >= 2 && pci.directEvidence);
            return pci.directEvidence(descriptor, offset, address, use);
        }, DcnHostFlatProfile::Gmc11SnoopedSystemUc};
}

static void hostFlatWords() {
    using Words = DcnHostFlatWords;
    constexpr auto profile = DcnHostFlatProfile::Gmc11SnoopedSystemUc;
    constexpr auto unavailable = DcnHostFlatProfile::Unqualified;
    constexpr uint64_t limit = 1ull << 44, leafFlags = 0x0003000000000027;
    uint64_t word = UINT64_MAX;
    assert(!Words::root(unavailable, kPage, kPage, word) && word == UINT64_MAX);
    assert(!Words::leaf(unavailable, kPage, word) && word == UINT64_MAX);
    assert(!Words::decode(unavailable, kPage | leafFlags, word) && word == UINT64_MAX);
    assert(!Words::root(profile, limit - kPage, 2 * kPage, word) && word == UINT64_MAX);
    assert(!Words::root(profile, kPage, kPage + 1, word) && word == UINT64_MAX);
    assert(Words::root(profile, limit - kPage, kPage, word) && word == ((limit - kPage) | 7));
    assert(Words::leaf(profile, limit - kPage, word) && word == ((limit - kPage) | leafFlags));
    uint64_t decoded = UINT64_MAX;
    for (const uint64_t flag : {1ull, 2ull, 4ull, 8ull, 16ull, 32ull, 64ull, 0xf80ull, 1ull << 44, 1ull << 48,
                               1ull << 51, 1ull << 54, 1ull << 63})
        assert(!Words::decode(profile, word ^ flag, decoded) && decoded == UINT64_MAX);
    assert(!Words::decode(profile, leafFlags, decoded) && decoded == UINT64_MAX);
    assert(Words::decode(profile, word, decoded) && decoded == limit - kPage);
    assert(!Words::leaf(profile, 0, word) && !Words::leaf(profile, kPage + 1, word) && !Words::leaf(profile, limit, word));
}

static void scanoutDmaQualification() {
    ScanoutFixture fixture;
    auto &device = fixture.device;
    auto &pci = *device.pci;
    auto &host = fixture.frame.host;
    IOMapper mapper;
    static IOMapper foreign;
    IODMACommand command;
    IODMACommand::next = &command;
    DmaRun scratch[2]{};
    uint64_t pages[2]{UINT64_MAX, UINT64_MAX};
    ScanoutDmaRequest request{&fixture.frame.copy, 0x100000, scratch, 2, pages, 2, {}, {}};
    const OSSymbol map{BUILD34_DCN_PIN_MAP};
    auto refuses = [&](IOReturn result, unsigned lookups) {
        assert(device.callPlatformFunction(&map, false, &request, nullptr, nullptr, nullptr) == result);
        assert(pci.mapperLookups == lookups && mapper.references == 1 && foreign.references == 1);
        assert(!command.created && !host.prepares && host.wires == 1 && !DcnAllocationStub::live());
        assert(!request.layout.entryCount && !request.token.serial && pages[0] == UINT64_MAX && pages[1] == UINT64_MAX);
    };
    fixture.offer();
    refuses(kIOReturnNotReady, 0);
    device.dcnQualifyMapper = mapperContract;
    device.pci = nullptr;
    refuses(kIOReturnNotReady, 0);
    device.pci = &pci;
    pci.inactive = true;
    refuses(kIOReturnNotReady, 0);
    pci.inactive = false;
    request.pageCapacity = 1;
    refuses(kIOReturnBadArgument, 0);
    request.pageCapacity = 2;
    refuses(kIOReturnNotReady, 1);
    pci.mapper = &mapper;
    mapper.inactive = true;
    device.dcnQualifyMapper = [](IOPCIDevice &, IOMapper &) -> ScanoutDmaMapper { assert(false); return {}; };
    refuses(kIOReturnNotReady, 2);
    mapper.inactive = false;
    device.dcnQualifyMapper = [](IOPCIDevice &selected, IOMapper &actual) {
        auto contract = mapperContract(selected, actual);
        contract.mapper = &foreign;
        return contract;
    };
    refuses(kIOReturnNotReady, 3);
    device.dcnQualifyMapper = [](IOPCIDevice &selected, IOMapper &actual) {
        auto contract = mapperContract(selected, actual);
        contract.resolveMappedPage = nullptr;
        return contract;
    };
    refuses(kIOReturnNotReady, 4);
    device.dcnQualifyMapper = [](IOPCIDevice &selected, IOMapper &actual) {
        auto contract = mapperContract(selected, actual);
        contract.confirmUnusedUnmap = nullptr;
        return contract;
    };
    refuses(kIOReturnNotReady, 5);
    device.dcnQualifyMapper = [](IOPCIDevice &selected, IOMapper &actual) {
        auto contract = mapperContract(selected, actual);
        actual.inactive = true;
        return contract;
    };
    refuses(kIOReturnNotReady, 6);
    mapper.inactive = false;
    ScanoutPinToken token{};
    assert(fixture.pin(token) == kIOReturnSuccess && fixture.cancelPin(token) == kIOReturnSuccess);
    IODMACommand::next = nullptr;
}

static void scanoutDmaPresentPreparation(bool uncertain) {
    ScanoutFixture fixture;
    auto &present = fixture.frame.present;
    auto &host = fixture.frame.host;
    if (uncertain) {
        present.afterPrepare = [&] { ++present.preparation; };
        present.completeResult = kIOReturnNotReady;
    } else {
        present.prepareResult = kIOReturnNotReady;
    }
    IOMapper mapper;
    IODMACommand command;
    IODMACommand::next = &command;
    fixture.device.pci->mapper = &mapper;
    fixture.device.dcnQualifyMapper = mapperContract;
    fixture.offer();
    DmaRun scratch[2]{};
    uint64_t pages[2]{UINT64_MAX, UINT64_MAX};
    ScanoutDmaRequest request{&fixture.frame.copy, 0x100000, scratch, 2, pages, 2, {}, {}};
    const OSSymbol map{BUILD34_DCN_PIN_MAP};
    assert(fixture.device.callPlatformFunction(&map, false, &request, nullptr, nullptr, nullptr) == kIOReturnNotReady);
    assert(!command.created && mapper.references == 1 && !DcnAllocationStub::live());
    assert(!request.layout.entryCount && !request.token.serial && pages[0] == UINT64_MAX && pages[1] == UINT64_MAX);
    assert(present.prepares == 1 && present.completes == uncertain && host.prepares == 1 && host.completes == !uncertain);
    assert(present.references == (uncertain ? 2u : 1u) && present.wires == present.references);
    assert(host.references == (uncertain ? 2u : 1u) && host.wires == host.references);
    assert(fixture.surface.references == (uncertain ? 2u : 1u) && fixture.client.references == fixture.surface.references);
    IODMACommand::next = nullptr;
}

static void scanoutDirectQualification() {
    ScanoutFixture fixture;
    auto &device = fixture.device;
    auto &pci = *device.pci;
    auto &host = fixture.frame.host;
    const auto &present = fixture.frame.present;
    IODMACommand command;
    IODMACommand::next = &command;
    DmaRun scratch[2]{};
    uint64_t pages[2]{UINT64_MAX, UINT64_MAX};
    ScanoutDmaRequest request{&fixture.frame.copy, 0x100000, scratch, 2, pages, 2, {}, {}};
    const OSSymbol mapped{BUILD34_DCN_PIN_MAP}, direct{BUILD34_DCN_PIN_MAP_DIRECT};
    auto dispatch = [&](const OSSymbol &selector) {
        return device.callPlatformFunction(&selector, false, &request, nullptr, nullptr, nullptr);
    };
    fixture.offer();
    assert(dispatch(direct) == kIOReturnNotReady && !pci.mapperLookups);
    device.dcnQualifyDirect = directContract;
    assert(dispatch(direct) == kIOReturnNotReady && !pci.mapperLookups && !host.prepares);
    pci.directGeneration = 17;
    device.dcnQualifyDirect = [](IOPCIDevice &selected) {
        auto contract = directContract(selected);
        contract.encoding = DcnHostFlatProfile::Unqualified;
        return contract;
    };
    assert(dispatch(direct) == kIOReturnNotReady && !pci.mapperLookups && !host.prepares);
    device.dcnQualifyDirect = directContract;
    device.dcnQualifyMapper = mapperContract;
    assert(dispatch(mapped) == kIOReturnNotReady && pci.mapperLookups == 1 && !host.prepares);
    unsigned pagesChecked = 0;
    pci.directEvidence = [&](const IOMemoryDescriptor &descriptor, uint64_t offset, uint64_t physical, DcnDirectUse use) {
        assert(use == DcnDirectUse::Pixel && &descriptor == &host && host.wires == 2 && present.wires == 2);
        assert(fixture.client.guard.held && !fixture.device.guard.held && offset == (++pagesChecked) * kPage);
        assert(physical == host.base + 2 * offset);
        return pagesChecked == 1;
    };
    assert(dispatch(direct) == kIOReturnNotReady && pagesChecked == 2 && !command.created && pci.mapperLookups == 1);
    assert(!request.layout.entryCount && !request.token.serial && pages[0] == UINT64_MAX && pages[1] == UINT64_MAX);
    assert(pci.references == 1 && host.wires == 1 && present.wires == 1 && !DcnAllocationStub::live());
    IODMACommand::next = nullptr;
}

static void scanoutDma(DmaFault fault, DmaCleanupFault cleanup = DmaCleanupFault::None) {
    ScanoutFixture fixture;
    DmaRun scratch[2]{};
    uint64_t pages[2]{UINT64_MAX, UINT64_MAX};
    ScanoutDmaRequest request{&fixture.frame.copy, 0x100000, scratch, 2, pages, 2, {}, {}};
    const OSSymbol map{BUILD34_DCN_PIN_MAP};
    auto dispatch = [&] {
        return fixture.device.callPlatformFunction(&map, false, &request, nullptr, nullptr, nullptr);
    };
    IOMapper mapper;
    IODMACommand command;
    IODMACommand::next = &command;
    fixture.device.pci->mapper = &mapper;
    fixture.device.dcnQualifyMapper = mapperContract;
    fixture.offer();
    command.failPrepare = fault == DmaFault::FailedPrepare;
    command.wrongOffset = fault == DmaFault::WrongOffset;
    command.failComplete = cleanup == DmaCleanupFault::Complete;
    command.failClear = cleanup == DmaCleanupFault::Clear;
    if (fault == DmaFault::AlternateDescriptor) command.substitute = &fixture.frame.present;
    command.segments = [&](UInt64 *cursor, IODMACommand::Segment64 *segments, UInt32 *count) {
        assert(!command.substitute && !command.wrongOffset);
        assert(fixture.client.guard.held && !fixture.device.guard.held && command.offset == kPage);
        assert((*cursor == 0 && *count == 2) || (*cursor == kPage && *count == 1));
        segments[0] = {*cursor ? 0x600000ull : 0x400000ull, kPage};
        *cursor += kPage;
        *count = 1;
        if (*cursor == 2 * kPage && fault == DmaFault::ChangedEpoch) ++fixture.device.exactInvalidationEpoch;
        return kIOReturnSuccess;
    };
    auto &host = fixture.frame.host;
    auto &present = fixture.frame.present;
    if (cleanup == DmaCleanupFault::PresentComplete) present.completeResult = kIOReturnNotReady;
    mapper.resolve = [&](const IODMACommand &mapped, uint64_t address, uint64_t &physical) {
        assert(&mapped == &command && command.prepared && command.memory == &host);
        assert(address == 0x400000 || address == 0x600000);
        const bool first = address == 0x400000;
        physical = host.base + (first ? 2 : fault == DmaFault::WrongPage ? 5 : 4) * kPage;
        return first || fault != DmaFault::NoMappedPage;
    };
    command.onComplete = [&] {
        assert(host.wires == 2 && present.wires == 2 && fixture.client.guard.held && !fixture.device.guard.held);
    };
    unsigned confirmations = 0;
    mapper.confirmUnmap = [&](const IODMACommand &completed) {
        ++confirmations;
        assert(&completed == &command && command.completes == 1 && !command.prepared && command.memory == &host);
        assert(!command.clears && host.wires == 2 && fixture.client.guard.held && !fixture.device.guard.held);
        return cleanup != DmaCleanupFault::ConfirmUnmap;
    };
    present.onComplete = [&] { assert(command.clears == 1 && !command.memory && host.wires == 2); };
    auto *savedPages = request.pages;
    request.pages = reinterpret_cast<uint64_t *>(scratch);
    assert(dispatch() == kIOReturnBadArgument && !command.created && !fixture.device.pci->mapperLookups);
    request.pages = savedPages;
    const bool failedPlan = fault != DmaFault::None;
    DcnAllocationStub::fail = fault == DmaFault::NoPlanMemory;
    assert(dispatch() == (failedPlan ? kIOReturnNotReady : kIOReturnSuccess) && command.created == 1);
    assert(fixture.device.pci->mapperLookups == 1);
    if (!failedPlan) {
        assert(request.layout.entryCount == 2 && request.token.provider == &fixture.device && request.token.serial);
        assert(pages[0] == 0x400000 && pages[1] == 0x600000);
        assert(DcnAllocationStub::live() == 1);
        assert(mapper.references == 2 && host.references == 3 && host.wires == 2 && present.wires == 2);
        assert(fixture.cancelPin(request.token) == (cleanup == DmaCleanupFault::None ? kIOReturnSuccess : kIOReturnNotReady));
        assert(fixture.cancelPin(request.token) == kIOReturnNotFound);
    } else {
        assert(!request.layout.entryCount && !request.token.serial && pages[0] == UINT64_MAX && pages[1] == UINT64_MAX);
    }
    const bool completed = !command.failPrepare && !command.substitute;
    const bool confirmed = completed && !command.failComplete;
    const bool cleared = confirmed && cleanup != DmaCleanupFault::ConfirmUnmap;
    const bool presentCompleted = cleared && !command.failClear;
    const bool reserved = !presentCompleted || cleanup == DmaCleanupFault::PresentComplete;
    assert(command.completes == completed && confirmations == confirmed);
    assert(command.clears == cleared && command.releases == !reserved);
    assert(mapper.references == (reserved ? 2u : 1u) && host.wires == (reserved ? 2u : 1u));
    assert(present.prepares == 1 && present.completes == presentCompleted);
    assert(present.references == (reserved ? 2u : 1u) && present.wires == present.references);
    assert(fixture.surface.references == (reserved ? 2u : 1u) && fixture.client.references == (reserved ? 2u : 1u));
    assert(DcnAllocationStub::live() == (!failedPlan && reserved ? 1u : 0u));
    IODMACommand::next = nullptr;
}
#endif

#ifdef TEST_SCANOUT_FLIP
enum class FlipFault { None, Decline, ForeignLock, HeldLock, Dcc, LockTimeout, HighWrite, RouteLost, ClockRewind,
                       Issue, UnlockTimeout, Close, CloseDuringQualify, CloseDuringRetire, LateRetire, Unmap,
                       WrongFormat, SwappedChannels, AlphaPlane, Protected, Tiled, WrongPitch, Cropped, WrongViewport,
                       SplitInput, SplitOutput, WrongOdmSource, DisabledOtg,
                       NoTranslationReader, TranslationError, WrongLastPage, LateTranslation, RevokedTranslation,
                       WrongPreviousPage, NoContextRoot, UnreadyContext, WrongContextRoot, WrongContextDepth,
                       WrongContextBlock, WrongContextStart, WrongContextEnd, ContextAfterPageWalk, ContextAtLock,
                       ContextWhilePending, ContextDuringRetire, ReplacedFrontContext,
                       DualPins, DualContextDuringRetire, DifferentPinnedPitch, GeometryAtLock, GeometryAtRetire,
                       GeometryBeforeRetire, Install, InstallDenied, InstallMissingProof, InstallSameVmid, InstallOccupied,
                       InstallWrongLeaf,
                       InstallRevoked, InstallWriteUncertain, InstallAckTimeout, InstallWrongAck,
                       NoTableMemory, ShortTable, EncodeError, PublishError, PublishBadRoot, PublishCorruptPadding,
                       PublicationLost, WithdrawError, CloseDuringWithdraw, CancelWithdrawError, SharedTable,
                       SharedRoot, RetryTable, TableWrongPhysical, TablePrepareUncertain, TableBadSegments,
                       TableSubstituted, RetireRootStillInstalled, RetireRangeStillInstalled,
                       RetireContextReappears, ReturnSameVmid, MissingFramebuffer, WrongFramebufferPci,
                       WrongFramebufferType, InactiveFramebuffer, NoHomeSample, WrongHomeAddress, WrongHomeGeometry,
                       WrongHomeBacking, HomeLostAfterInstall, HomeLostAtRetire, WrongReturnAddress, ReplacedFramebuffer,
                       PeerActive, PeerShortWindow, PeerDuringInstall, PeerAfterHigh, PeerDuringRetire, PeerAfterWithdraw,
                       NoRetirementProof, ClearDenied, ClearWriteUncertain, ReplacedDuringFetchDrain,
                       TranslationPending, TranslationLost, FrontRevertedDuringTranslations, PhysicalAlias,
                       FetchBusy, FetchNeverDrained };

struct CommitFixture {
    struct Table : IOBufferMemoryDescriptor {
        IODMACommand dma;
        uint64_t root = 0;
        unsigned withdrawals = 0;
    };
    struct Framebuffer : IOService {
        CommitFixture *fixture = nullptr;
        unsigned samples = 0, checks = 0, releases = 0;
        IOReturn callPlatformFunction(const OSSymbol *name, bool wait, void *pci, void *record, void *third, void *fourth) override {
            assert(!wait && pci == provider && record && !fourth && references == 2 && fixture);
            auto &self = *fixture;
            assert(!self.lockRequested && !self.scanout.device.guard.held);
            const auto fault = self.translationFault;
            auto &value = *static_cast<FirmwareScanoutSample *>(record);
            constexpr uint64_t backing = 0x18004000, offset = 0x4000;
            if (name->isEqualTo(BUILD34_DCN_SAMPLE_FIRMWARE)) {
                assert(!third);
                ++samples;
                if (fault == FlipFault::NoHomeSample) return kIOReturnNotReady;
                assert(self.active == self.home);
                value = {self.home, {64, 17, 63, 8, 2 * kPage}, offset, backing, self.frame};
                if (fault == FlipFault::WrongHomeAddress) value.scanout.address += kPage;
                if (fault == FlipFault::WrongHomeGeometry) --value.surface.height;
                if (fault == FlipFault::WrongHomeBacking) value.backing += kPage;
                return kIOReturnSuccess;
            }
            assert(name->isEqualTo(BUILD34_DCN_CHECK_FIRMWARE));
            ++checks;
            assert(value.scanout == self.home && value.surface.height == 17 && value.barOffset == offset);
            const bool planned = self.route.presentWindows.domain != DcnPresentDomain::None;
            assert(bool(third) == (self.directMode || planned));
            if (third) {
                const auto &windows = *static_cast<const FirmwareFlatWindows *>(third);
                if (planned) {
                    assert(windows.previous.start == self.mapped.address && windows.previous.bytes == 2 * kPage &&
                           windows.next.start == self.alternate.address && windows.next.bytes == 2 * kPage);
                } else {
                    const bool returning = self.target == self.home;
                    const auto &pinWindow = returning ? windows.previous : windows.next;
                    const auto &homeWindow = returning ? windows.next : windows.previous;
                    assert(pinWindow.start == self.mapped.address && pinWindow.bytes == 2 * kPage && !homeWindow.start && !homeWindow.bytes);
                }
                if (self.flatWindowConflict) return kIOReturnNotReady;
            }
            return value.backing == backing && !(fault == FlipFault::HomeLostAtRetire && self.retireChecks == 3) &&
                !(fault == FlipFault::HomeLostAfterInstall && self.vmWrites) ? kIOReturnSuccess : kIOReturnNotReady;
        }
    };
    ScanoutFixture scanout;
    Descriptor nextHost, nextPresent;
    IOMapper mapper;
    IODMACommand command, nextCommand;
    OSObject lifetime;
    Framebuffer framebuffer;
    Table homeTable, alternateTable;
    const HubpAddress home{0x800000000, 0}, mapped{0xa00100100000, 7};
    const HubpAddress alternate{mapped.address + 2 * kPage, 8};
    HubpAddress programmed = home, active = home, earliest = home, target = home;
    uint32_t frame = 42;
    uint64_t now = 800;
    unsigned issues = 0, reads = 0, writes = 0, delays = 0, retireChecks = 0, pageReads = 0;
    unsigned pixelReads = 0;
    std::function<bool(bool, uint64_t &)> pixelEvidence;
    std::function<void()> afterVmInstall, afterOtgLock;
    unsigned vmWrites = 0, vmAckReads = 0, clearChecks = 0, clearWrites = 0, translationChecks = 0;
    uint32_t lockSelect = 0, surfaceControl = 0;
    uint32_t surfaceFormat = 8, returnControl = 0x00e00000, swizzle = 0, start = 0;
    uint32_t dimensions = (17u << 16) | 64u, pitch = 63, odm = 0xfff00000, otg = 0x00010001;
    const uint64_t ownedRoot;
    uint64_t contextRoot = 0, firstPage = 0, lastPage = 0;
    const uint64_t alternateRoot = 0x123400006001;
    uint64_t alternateContextRoot = 0, alternateFirst = 0, alternateLast = 0;
    uint32_t contextControl = 0, alternateControl = 0;
    bool lockRequested = false, lockHeld = false, lockTimeout = false, unlockTimeout = false;
    bool qualify = true, live = true, pending = false, failHigh = false, failIssue = false, retire = false, failUnmap = false;
    bool loseRouteAfterHigh = false, rewindAfterHigh = false;
    bool closeDuringQualify = false, closeDuringRetire = false, lateRetire = false;
    bool noOutstanding = true;
    bool changeGeometryAtLock = false, changeGeometryAtRetire = false;
    bool publicationCurrent = true;
    bool directMode = false;
    bool flatWindowConflict = false;
    FlipFault translationFault = FlipFault::None;
    uint64_t outputPages[2]{};
    HubpFlipRoute route{this, 5, &lifetime, {this, 0x80000, routeCurrent, read, clock, this}, {write, delay},
                       qualified, {encodeLeaf, decodeLeaf, encodeRoot, tableCurrent}, retired, canInstallFlatVm,
                       canClearFlatVm, translationsRetired, &framebuffer};
    ScanoutPinToken pin{}, alternatePin{};

    explicit CommitFixture(bool direct = false)
        : ownedRoot(direct ? 0xe3400005007 : 0x123400005001), directMode(direct) {
        scanout.device.dcnProveGpuVmOwnership = PhxBringup::proveIsolation;
        framebuffer.fixture = this;
        framebuffer.provider = scanout.device.pci;
        framebuffer.isPhxFramebuffer = true;
        framebuffer.onRelease = [&] {
            assert(!scanout.client.guard.held && !scanout.device.guard.held);
            ++framebuffer.releases;
        };
        alternateTable.physical += 2 * kPage;
        if (directMode) {
            auto &pci = *scanout.device.pci;
            auto &host = scanout.frame.host;
            pci.directGeneration = 7;
            homeTable.physical = ownedRoot & ~(kPage - 1);
            pci.directEvidence = [&](const IOMemoryDescriptor &descriptor, uint64_t offset, uint64_t address, DcnDirectUse use) {
                if (use == DcnDirectUse::Table)
                    return &descriptor == &homeTable && offset == 0 && address == homeTable.physical;
                assert(&descriptor == &host && (offset == kPage || offset == 2 * kPage));
                ++pixelReads;
                return address == host.base + 2 * offset;
            };
            scanout.device.dcnQualifyDirect = directContract;
            route.flatFormat = {nullptr, nullptr, nullptr, tableCurrent};
            constexpr uint64_t flags = 0x0003000000000027;
            configureTable(homeTable, ownedRoot, (host.base + 2 * kPage) | flags, (host.base + 4 * kPage) | flags);
        } else {
            configureTable(homeTable, ownedRoot, 0x500091, 0x601091);
        }
        configureTable(alternateTable, alternateRoot, 0x800091, 0x901091);
        IODMACommand::next = &command;
        scanout.device.pci->mapper = &mapper;
        scanout.device.pci->route = &route;
        scanout.device.dcnQualifyMapper = mapperContract;
        command.segments = [](UInt64 *cursor, IODMACommand::Segment64 *segments, UInt32 *count) {
            assert(!*cursor && *count == 2);
            segments[0] = {0x500000, kPage};
            segments[1] = {0x601000, kPage};
            *cursor = 2 * kPage;
            return kIOReturnSuccess;
        };
        nextCommand.segments = [](UInt64 *cursor, IODMACommand::Segment64 *segments, UInt32 *count) {
            assert(!*cursor && *count == 2);
            segments[0] = {0x800000, kPage};
            segments[1] = {0x901000, kPage};
            *cursor = 2 * kPage;
            return kIOReturnSuccess;
        };
        mapper.resolve = [&](const IODMACommand &mapped, uint64_t address, uint64_t &physical) {
            if (&mapped == &homeTable.dma || &mapped == &alternateTable.dma) {
                const auto &table = &mapped == &homeTable.dma ? homeTable : alternateTable;
                const auto root = &mapped == &homeTable.dma || translationFault == FlipFault::SharedTable ? ownedRoot : alternateRoot;
                assert(mapped.prepared && mapped.memory == &table && address == (root & ~(kPage - 1)));
                physical = table.physical + (translationFault == FlipFault::TableWrongPhysical ? kPage : 0);
                return true;
            }
            const bool alternate = &mapped == &nextCommand;
            const auto &host = alternate ? nextHost : scanout.frame.host;
            assert((alternate || &mapped == &command) && mapped.prepared && mapped.memory == &host);
            const bool first = address == (alternate ? 0x800000 : 0x500000);
            assert(first || address == (alternate ? 0x901000 : 0x601000));
            physical = host.base + (first ? 2 : 4) * kPage;
            ++pixelReads;
            return !pixelEvidence || pixelEvidence(first, physical);
        };
        mapper.confirmUnmap = [&](const IODMACommand &completed) {
            if (&completed == &homeTable.dma || &completed == &alternateTable.dma) {
                auto &table = &completed == &homeTable.dma ? homeTable : alternateTable;
                assert(completed.memory == &table && !completed.prepared && table.references == 2 &&
                       scanout.client.guard.held && !scanout.device.guard.held);
                ++table.withdrawals;
                if (translationFault == FlipFault::CloseDuringWithdraw) scanout.device.exactCallbacks.close();
                if (translationFault == FlipFault::RetireContextReappears) contextRoot = ownedRoot;
                return translationFault != FlipFault::WithdrawError && translationFault != FlipFault::CancelWithdrawError;
            }
            if (!issues || &completed == &nextCommand) {
                assert(scanout.client.guard.held && !scanout.device.guard.held);
                return true;
            }
            assert(&completed == &command && retire && retireChecks >= (alternatePin.serial ? 2u : 3u) &&
                   clearWrites == 7 && translationChecks &&
                   scanout.client.guard.held && !scanout.device.guard.held && lifetime.references == (alternatePin.serial ? 4u : 3u) &&
                   homeTable.withdrawals == 1 && !homeTable.dma.prepared && homeTable.references == 1 &&
                   scanout.frame.host.wires == 2);
            return !failUnmap;
        };
        scanout.offer();
        DmaRun scratch[2]{};
        ScanoutDmaRequest request{&scanout.frame.copy, mapped.address, scratch, 2, outputPages, 2, {}, {}};
        const OSSymbol symbol{directMode ? BUILD34_DCN_PIN_MAP_DIRECT : BUILD34_DCN_PIN_MAP};
        const auto surface = scanout.frame.copy.scanout;
        scanout.frame.copy.scanout.pitchPixelsMinusOne = 1;
        assert(dispatch(symbol, &request) == kIOReturnBadArgument && !command.created);
        scanout.frame.copy.scanout.pitchPixelsMinusOne = 127;
        assert(dispatch(symbol, &request) == kIOReturnBadArgument && !command.created);
        scanout.frame.copy.scanout = surface;
        assert(dispatch(symbol, &request) == kIOReturnSuccess && request.token.serial);
        const auto base = scanout.frame.host.base;
        assert(outputPages[0] == (directMode ? base + 2 * kPage : 0x500000) &&
               outputPages[1] == (directMode ? base + 4 * kPage : 0x601000) && DcnAllocationStub::live() == 1);
        outputPages[0] = outputPages[1] = 0x700000;
        pin = request.token;
        scanout.frame.copy.scanout = {};
    }

    ~CommitFixture() { IODMACommand::next = nullptr; IOBufferMemoryDescriptor::next = nullptr; }

    void selectAlternate(bool alias = false) {
        auto &frame = scanout.frame;
        nextHost.base = frame.host.base + (alias ? 2 * kPage : 16 * kPage);
        nextPresent.base = nextHost.base + 2 * kPage;
        frame.client.boTable[1].md = &nextHost;
        frame.copy.slice.descriptor = &nextPresent;
        IODMACommand::next = &nextCommand;
    }

    void configureTable(Table &table, uint64_t root, uint64_t first, uint64_t second) {
        table.root = root;
        table.dma.segments = [&, root](UInt64 *cursor, IODMACommand::Segment64 *segments, UInt32 *count) {
            assert(!*cursor && *count == 1);
            const auto selected = translationFault == FlipFault::SharedTable ? ownedRoot : root;
            segments[0] = {selected & ~(kPage - 1), kPage};
            *cursor = translationFault == FlipFault::TableBadSegments ? 2 * kPage : kPage;
            return kIOReturnSuccess;
        };
        table.onStore = [&, first, second] {
            assert(table.words[0] == first && table.words[1] == second);
            for (size_t index = 2; index < kPage / sizeof(uint64_t); ++index) assert(!table.words[index]);
            assert(table.words[512] == UINT64_MAX);
            if (translationFault == FlipFault::PublishCorruptPadding) table.words[511] = 1;
            if (translationFault == FlipFault::WrongLastPage || translationFault == FlipFault::InstallWrongLeaf)
                table.words[1] = outputPages[1] | 0x91;
        };
    }

    static bool routeCurrent(void *context, const HubpFlipRequest &request) {
        const auto &self = *static_cast<CommitFixture *>(context);
        return self.live && request.routeOwner == &self && request.routeGeneration == self.route.generation;
    }

    static bool qualified(void *context, const HubpFlipRequest &request, DcnPixelMapping old, DcnPixelMapping next) {
        auto &self = *static_cast<CommitFixture *>(context);
        assert(self.lifetime.references >= 2 && !self.scanout.device.guard.held);
        const auto check = [&](ScanoutPinToken token, DcnPixelMapping mapping) {
            if (!token.serial) {
                assert(!mapping.command && !mapping.direct);
                return;
            }
            assert(token == self.pin || token == self.alternatePin);
            if (self.directMode) {
                assert(!mapping.command && mapping.direct && mapping.direct->device == self.scanout.device.pci);
            } else {
                assert(!mapping.direct && mapping.command == (token == self.pin ? &self.command : &self.nextCommand));
            }
        };
        check(request.previousPin, old);
        check(request.nextPin, next);
        if (request.nextPin.serial) {
            auto &table = request.nextPin == self.pin ? self.homeTable : self.alternateTable;
            table.failStore = self.translationFault == FlipFault::PublishError;
            table.shortBuffer = self.translationFault == FlipFault::ShortTable;
            table.dma.failPrepare = self.translationFault == FlipFault::TablePrepareUncertain;
            if (self.translationFault == FlipFault::TableSubstituted) table.dma.substitute = &self.alternateTable;
            IOBufferMemoryDescriptor::next = self.translationFault == FlipFault::NoTableMemory ? nullptr : &table;
            IODMACommand::next = &table.dma;
        }
        self.target = request.next;
        if (self.closeDuringQualify) self.scanout.device.exactCallbacks.close();
        return self.qualify;
    }

    const Table &tableFor(const DcnFlatMapping &mapping) const {
        const auto &table = directMode || mapping.pixels.command == &command ? homeTable : alternateTable;
        if (directMode) {
            assert(!mapping.pixels.command && mapping.pixels.direct && mapping.pixels.direct->device == scanout.device.pci);
            assert(mapping.directTable == &table && !mapping.table && !mapping.mapper && !table.dma.created && table.references == 1);
        } else {
            assert(!mapping.pixels.direct && (mapping.pixels.command == &command || mapping.pixels.command == &nextCommand) &&
                   mapping.pixels.command->prepared);
            assert(!mapping.directTable && mapping.table == &table.dma && table.dma.prepared && table.references == 2 &&
                   mapping.mapper == &mapper);
        }
        assert(mapping.bytes == kPage && mapping.address == (table.root & ~(kPage - 1)));
        return table;
    }

    static bool encodeLeaf(void *context, const DcnFlatMapping &mapping, uint64_t address, uint64_t &word) {
        const auto &self = *static_cast<CommitFixture *>(context);
        assert(!(address % kPage) && !self.tableFor(mapping).stores);
        word = address | 0x91;
        return self.translationFault != FlipFault::EncodeError;
    }

    static bool encodeRoot(void *context, const DcnFlatMapping &mapping, uint64_t &root) {
        const auto &self = *static_cast<CommitFixture *>(context);
        const auto &table = self.tableFor(mapping);
        assert(!table.stores && !self.scanout.device.guard.held && !self.scanout.client.guard.held);
        root = self.translationFault == FlipFault::SharedRoot ? self.ownedRoot : mapping.address | 1;
        if (self.translationFault == FlipFault::PublishBadRoot) root &= ~uint64_t{1};
        return true;
    }

    static bool tableCurrent(void *context, const DcnFlatMapping &mapping, const DcnFlatContext &vm) {
        const auto &self = *static_cast<CommitFixture *>(context);
        const auto &table = self.tableFor(mapping);
        return table.stores == 1 && vm.rootEntry == table.root && self.publicationCurrent;
    }

    static bool canInstallFlatVm(void *context, const HubpFlipRequest &request, const DcnFlatContext &vm) {
        const auto &self = *static_cast<CommitFixture *>(context);
        const bool alternate = request.nextPin == self.alternatePin;
        assert(request.nextPin == self.pin || alternate);
        assert(vm.vmid == (alternate ? self.alternate.vmid : self.mapped.vmid) &&
               vm.rootEntry == (alternate ? self.alternateRoot : self.ownedRoot));
        assert(!self.lockRequested && self.lifetime.references >= 3);
        assert(!self.scanout.client.guard.held && !self.scanout.device.guard.held);
        return self.translationFault != FlipFault::InstallDenied &&
            !(self.translationFault == FlipFault::InstallRevoked && self.vmWrites == 3);
    }

    static bool decodeLeaf(void *context, const DcnFlatMapping &mapping, uint64_t word, uint64_t &dmaPage) {
        auto &self = *static_cast<CommitFixture *>(context);
        assert(!self.scanout.device.guard.held && !self.scanout.client.guard.held && !self.lockRequested);
        assert(self.tableFor(mapping).stores == 1 && self.lifetime.references >= 3);
        const bool last = (self.pageReads++ & 1) != 0;
        if ((word & (kPage - 1)) != 0x91) return false;
        dmaPage = word & ~(kPage - 1);
        if (last && self.translationFault == FlipFault::ContextAfterPageWalk) self.contextRoot ^= kPage;
        if (self.translationFault == FlipFault::LateTranslation) self.now += 100000000;
        if (self.translationFault == FlipFault::RevokedTranslation) self.live = false;
        return self.translationFault != FlipFault::TranslationError;
    }

    static bool write(void *context, uint32_t address, uint32_t value) {
        auto &self = *static_cast<CommitFixture *>(context);
        assert(self.scanout.cancelPin(self.pin) == kIOReturnBusy);
        assert(self.lifetime.references >= 3 && !self.scanout.device.guard.held);
        if (self.scanout.client.guard.held) {
            const uint32_t sequence[]{3, 4, 5, 6, 0, 1, 2};
            assert(self.retire && !self.lockRequested && !self.translationChecks && self.clearWrites < 7 &&
                   self.clearChecks == self.clearWrites + 1 && address == 0x03a4a + sequence[self.clearWrites++] && !value);
            assert(self.homeTable.dma.prepared == !self.directMode && !self.homeTable.withdrawals &&
                   self.command.prepared == !self.directMode);
            switch (address - 0x03a4a) {
            case 0: self.contextControl = 0; break;
            case 1: self.contextRoot &= UINT32_MAX; break;
            case 2:
                if (self.translationFault != FlipFault::RetireRootStillInstalled) self.contextRoot = 0;
                break;
            case 3: self.firstPage &= UINT32_MAX; break;
            case 4:
                if (self.translationFault != FlipFault::RetireRangeStillInstalled) self.firstPage = 0;
                break;
            case 5: self.lastPage &= UINT32_MAX; break;
            case 6: self.lastPage = 0; break;
            default: assert(false); return false;
            }
            return self.translationFault != FlipFault::ClearWriteUncertain;
        }
        if (address >= 0x03a4a && address <= 0x03a57) {
            assert(self.scanout.device.dcnSubmitGate.held());
            const bool alternate = address >= 0x03a51;
            const uint32_t base = alternate ? 0x03a51 : 0x03a4a;
            const uint32_t sequence[]{3, 4, 5, 6, 0, 1, 2};
            const auto &table = alternate ? self.alternateTable : self.homeTable;
            const auto first = (alternate ? self.alternate : self.mapped).address / kPage, last = first + 1;
            const uint32_t values[]{static_cast<uint32_t>(first >> 32), static_cast<uint32_t>(first),
                static_cast<uint32_t>(last >> 32), static_cast<uint32_t>(last), 0,
                static_cast<uint32_t>(table.root >> 32), static_cast<uint32_t>(table.root)};
            const unsigned index = self.vmWrites++ % 7;
            assert(sequence[index] == address - base && values[index] == value && !self.lockRequested && table.stores == 1);
            assert(self.pageReads == (self.directMode ? 0u : alternate ? 6u : 2u));
            auto &root = alternate ? self.alternateContextRoot : self.contextRoot;
            auto &firstPage = alternate ? self.alternateFirst : self.firstPage;
            auto &lastPage = alternate ? self.alternateLast : self.lastPage;
            switch (address - base) {
            case 0: (alternate ? self.alternateControl : self.contextControl) = value; break;
            case 1: root = uint64_t{value} << 32; break;
            case 2:
                root |= value;
                if (self.translationFault == FlipFault::Install || self.translationFault == FlipFault::InstallAckTimeout)
                    root &= ~uint64_t{1};
                if (self.translationFault == FlipFault::InstallWrongAck) root ^= kPage;
                if (self.afterVmInstall) self.afterVmInstall();
                return self.translationFault != FlipFault::InstallWriteUncertain;
            case 3: firstPage = uint64_t{value} << 32; break;
            case 4: firstPage |= value; break;
            case 5: lastPage = uint64_t{value} << 32; break;
            case 6: lastPage |= value; break;
            default: assert(false); return false;
            }
            return true;
        }
        const auto target = self.target;
        assert(self.scanout.device.dcnSubmitGate.held() == bool(target.vmid));
        const auto step = self.writes++ % 5;
        switch (address) {
        case hubp0::kOtgUpdateLock:
            if (value) {
                assert(step == 0 && !self.lockRequested && !self.lockHeld && value == hubp0::kOtgLockRequest);
                self.lockRequested = true;
                self.lockHeld = !self.lockTimeout;
                if (self.changeGeometryAtLock) ++self.pitch;
                if (self.translationFault == FlipFault::ContextAtLock) self.contextRoot ^= kPage;
                if (self.afterOtgLock) self.afterOtgLock();
            } else {
                assert(step == 4 && self.lockRequested && self.lockHeld && self.pending &&
                       self.programmed == target);
                self.lockRequested = false;
                self.lockHeld = self.unlockTimeout;
            }
            return true;
        case hubp0::kVmid:
            assert(step == 1 && self.lockHeld && value == (0x10 | target.vmid));
            self.programmed.vmid = value & 0xf;
            if (self.rewindAfterHigh) self.now += 10;
            return true;
        case hubp0::kProgrammedHigh:
            assert(step == 2 && self.lockHeld && value == target.address >> 32);
            self.programmed.address = (uint64_t{value} << 32) | (self.programmed.address & 0xffffffff);
            if (self.loseRouteAfterHigh) self.live = false;
            if (self.rewindAfterHigh) --self.now;
            return !self.failHigh;
        case hubp0::kProgrammedLow:
            assert(step == 3 && self.lockHeld && value == static_cast<uint32_t>(target.address));
            self.programmed.address = (self.programmed.address & ~uint64_t{0xffffffff}) | value;
            self.pending = true;
            ++self.issues;
            return !self.failIssue;
        default: assert(false); return false;
        }
    }

    static void delay(void *context, uint32_t us) {
        auto &self = *static_cast<CommitFixture *>(context);
        assert(us == 1);
        ++self.delays;
    }

    static bool retired(void *context, const HubpFlipRequest &request) {
        auto &self = *static_cast<CommitFixture *>(context);
        assert(self.active == request.next && self.earliest == request.next && !self.pending);
        assert(self.scanout.client.guard.held == bool(request.previousPin.serial));
        ++self.retireChecks;
        if (self.closeDuringRetire && request.previousPin.serial) self.scanout.device.exactCallbacks.close();
        if (self.lateRetire && request.previousPin.serial) self.now += 100000000;
        if (self.changeGeometryAtRetire && request.previousPin.serial) ++self.pitch;
        if (request.previousPin.serial && self.retire && self.translationFault == FlipFault::ReplacedDuringFetchDrain)
            self.contextRoot ^= kPage;
        if (self.translationFault == FlipFault::ContextDuringRetire && request.nextPin.serial) self.contextRoot ^= kPage;
        if (self.translationFault == FlipFault::DualContextDuringRetire && request.nextPin == self.alternatePin)
            self.alternateContextRoot ^= kPage;
        return self.retire;
    }

    static bool canClearFlatVm(void *context, const HubpFlipRequest &request, const DcnFlatContext &old) {
        auto &self = *static_cast<CommitFixture *>(context);
        assert(self.scanout.client.guard.held && !self.scanout.device.guard.held && self.retire &&
               request.previous == self.mapped && request.previousPin == self.pin && request.next == self.active &&
               old.vmid == self.mapped.vmid && old.rootEntry == self.ownedRoot && old.firstPage == self.mapped.address / kPage &&
               old.lastPage == old.firstPage + 1 && !self.translationChecks);
        ++self.clearChecks;
        return self.translationFault != FlipFault::ClearDenied;
    }

    static DcnRetirement translationsRetired(void *context, const HubpFlipRequest &request, const DcnFlatContext &old) {
        auto &self = *static_cast<CommitFixture *>(context);
        assert(self.scanout.client.guard.held && !self.scanout.device.guard.held && self.retire &&
               request.previousPin == self.pin && request.next == self.active && old.vmid == self.mapped.vmid &&
               old.rootEntry == self.ownedRoot && self.clearWrites == 7 && !self.contextRoot && !self.firstPage &&
               !self.lastPage && !self.contextControl && self.homeTable.dma.prepared == !self.directMode &&
               self.command.prepared == !self.directMode);
        ++self.translationChecks;
        if (self.translationFault == FlipFault::TranslationLost) return DcnRetirement::Lost;
        if (self.translationFault == FlipFault::TranslationPending && self.translationChecks == 1) return DcnRetirement::Pending;
        if (self.translationFault == FlipFault::FrontRevertedDuringTranslations) self.earliest = request.previous;
        return DcnRetirement::Complete;
    }

    static bool read(void *context, uint32_t address, uint32_t &value) {
        auto &self = *static_cast<CommitFixture *>(context);
        const auto low = [](HubpAddress surface) { return static_cast<uint32_t>(surface.address); };
        const auto high = [](HubpAddress surface) { return static_cast<uint32_t>(surface.address >> 32); };
        ++self.reads;
        switch (address) {
        case hubp0::kControl: value = self.noOutstanding ? 0x2 : 0; break;
        case hubp0::kFlip2: value = 0; break;
        case hubp0::kFlip:
            value = (self.pending ? hubp0::kPending : 0) | (self.lockHeld ? hubp0::kUpdateLocked : 0);
            break;
        case hubp0::kVmid: value = 0x10 | self.programmed.vmid; break;
        case 0x03ada: value = self.surfaceControl; break;
        case 0x03aa5: value = self.surfaceFormat; break;
        case 0x03b2c: value = self.returnControl; break;
        case 0x03aa7: value = self.swizzle; break;
        case 0x03aa9: value = self.start; break;
        case 0x03aaa: value = self.dimensions; break;
        case 0x03ac7: value = self.pitch; break;
        case 0x04f8b: value = self.odm; break;
        case 0x05001: value = self.otg; break;
        case 0x03543: case 0x03545: case 0x03547: value = 0x80000000; break;
        case 0x05081: case 0x05101: value = 0; break;
        case 0x05181:
            value = self.translationFault == FlipFault::PeerActive ||
                (self.translationFault == FlipFault::PeerDuringInstall && self.vmWrites >= 3) ||
                (self.translationFault == FlipFault::PeerAfterHigh && self.writes >= 3) ||
                (self.translationFault == FlipFault::PeerDuringRetire && self.retireChecks >= 3) ||
                (self.translationFault == FlipFault::PeerAfterWithdraw && self.homeTable.withdrawals) ? 0x10000 : 0;
            break;
        case 0x03a4a: value = self.contextControl; break;
        case 0x03a4b: value = static_cast<uint32_t>(self.contextRoot >> 32); break;
        case 0x03a4c:
            if (self.vmWrites == 7 && !(self.contextRoot & 1)) {
                ++self.vmAckReads;
                if (self.translationFault == FlipFault::Install && self.vmAckReads == 3) self.contextRoot |= 1;
            }
            value = static_cast<uint32_t>(self.contextRoot);
            break;
        case 0x03a4d: value = static_cast<uint32_t>(self.firstPage >> 32); break;
        case 0x03a4e: value = static_cast<uint32_t>(self.firstPage); break;
        case 0x03a4f: value = static_cast<uint32_t>(self.lastPage >> 32); break;
        case 0x03a50: value = static_cast<uint32_t>(self.lastPage); break;
        case 0x03a51: value = self.alternateControl; break;
        case 0x03a52: value = static_cast<uint32_t>(self.alternateContextRoot >> 32); break;
        case 0x03a53: value = static_cast<uint32_t>(self.alternateContextRoot); break;
        case 0x03a54: value = static_cast<uint32_t>(self.alternateFirst >> 32); break;
        case 0x03a55: value = static_cast<uint32_t>(self.alternateFirst); break;
        case 0x03a56: value = static_cast<uint32_t>(self.alternateLast >> 32); break;
        case 0x03a57: value = static_cast<uint32_t>(self.alternateLast); break;
        case hubp0::kOtgLockSelect: value = self.lockSelect; break;
        case hubp0::kOtgUpdateLock:
            value = (self.lockRequested ? hubp0::kOtgLockRequest : 0) | (self.lockHeld ? hubp0::kOtgLockStatus : 0);
            break;
        case hubp0::kProgrammedLow: value = low(self.programmed); break;
        case hubp0::kProgrammedHigh: value = high(self.programmed); break;
        case hubp0::kInUseLow: value = low(self.active); break;
        case hubp0::kInUseHigh: value = high(self.active) | (self.active.vmid << 28); break;
        case hubp0::kEarliestLow: value = low(self.earliest); break;
        case hubp0::kEarliestHigh: value = high(self.earliest) | (self.earliest.vmid << 28); break;
        case hubp0::kFrame: value = self.frame; break;
        default: return false;
        }
        return true;
    }

    static bool clock(void *context, uint64_t &value) {
        value = static_cast<CommitFixture *>(context)->now;
        return true;
    }

    IOReturn dispatch(const OSSymbol &symbol, void *value) {
        return scanout.device.callPlatformFunction(&symbol, false, value, nullptr, nullptr, nullptr);
    }

    IOReturn begin(ScanoutFlipIntent &request) {
        const OSSymbol symbol{BUILD34_DCN_FLIP_BEGIN};
        return dispatch(symbol, &request);
    }

    IOReturn poll(ScanoutFlipPoll &request) {
        const OSSymbol symbol{BUILD34_DCN_FLIP_POLL};
        return dispatch(symbol, &request);
    }

    void step(ScanoutFlipPoll &request, ScanoutFlipResult expected) {
        ++frame;
        now += 8000000;
        assert(poll(request) == kIOReturnSuccess && request.result == expected);
    }

    void completeNewComputeWork() {
        auto &device = scanout.device;
        IOLockLock(device.gpuLock);
        device.done[0] = device.recordQueued(0);
        IOLockUnlock(device.gpuLock);
    }
};

enum class WriterFault { NewerCompletedWork, ChangedEpoch, ChangedQueueGeneration, ReplacedWriterMap, ClientBusy, GpuBusy,
                         DuringPageWalk, AfterVmInstall, UnderOtgLock };

static void revalidateScanoutWriter(WriterFault fault, bool direct) {
    CommitFixture fixture(direct);
    auto &client = fixture.scanout.client;
    auto &device = fixture.scanout.device;
    device.dcnQualifiedFlipRoute = [](IOPCIDevice *pci) -> const HubpFlipRoute * { return pci->route; };
    std::function<void()> newWork = [&] { fixture.completeNewComputeWork(); };
    switch (fault) {
    case WriterFault::NewerCompletedWork: newWork(); break;
    case WriterFault::ChangedEpoch: ++device.exactInvalidationEpoch; break;
    case WriterFault::ChangedQueueGeneration: ++device.exactQueueGeneration[0]; break;
    case WriterFault::ReplacedWriterMap: ++client.maps[0].writerGeneration; break;
    case WriterFault::ClientBusy: IOLockLock(client.lock); break;
    case WriterFault::GpuBusy: IOLockLock(device.gpuLock); break;
    case WriterFault::DuringPageWalk:
        fixture.scanout.frame.host.afterRead = newWork;
        break;
    case WriterFault::AfterVmInstall: fixture.afterVmInstall = newWork; break;
    case WriterFault::UnderOtgLock: fixture.afterOtgLock = newWork; break;
    }
    ScanoutFlipIntent intent{fixture.home, fixture.mapped, fixture.pin, {}, ScanoutFlipResult::Refused};
    const bool issued = fault == WriterFault::AfterVmInstall || fault == WriterFault::UnderOtgLock;
    assert(fixture.begin(intent) == (issued ? kIOReturnSuccess : kIOReturnNotReady));
    assert(!device.dcnSubmitGate.held());
    if (fault == WriterFault::ClientBusy) IOLockUnlock(client.lock);
    if (fault == WriterFault::GpuBusy) IOLockUnlock(device.gpuLock);
    assert(bool(intent.operation.serial) == issued && !fixture.issues);
    assert(fixture.writes == (fault == WriterFault::UnderOtgLock ? 1u : 0u));
    assert(fixture.vmWrites == (issued ? 7u : 0u));
    if (issued) {
        assert(intent.result == ScanoutFlipResult::Uncertain && fixture.scanout.frame.host.wires == 2);
        assert(fixture.scanout.cancelPin(fixture.pin) == kIOReturnNotFound && !fixture.command.completes);
        ScanoutFlipPoll poll{intent.operation, ScanoutFlipResult::Refused};
        fixture.step(poll, ScanoutFlipResult::Uncertain);
    } else {
        assert(bool(fixture.reads) == (fault == WriterFault::DuringPageWalk));
        assert(fixture.scanout.cancelPin(fixture.pin) == kIOReturnSuccess && fixture.scanout.frame.host.wires == 1);
    }
}

static void scanoutSubmitReservation(bool direct) {
    CommitFixture fixture(direct);
    auto &device = fixture.scanout.device;
    auto &client = fixture.scanout.client;
    device.dcnQualifiedFlipRoute = [](IOPCIDevice *pci) -> const HubpFlipRoute * { return pci->route; };
    const auto original = device.gSeq;
    unsigned sleeps = 0;
    device.onSubmitSleep = [&] {
        ++sleeps;
        assert(device.dcnSubmitGate.held());
        device.submitTime += 2000000000ull;
    };
    const auto submit = [&](bool graphics) {
        uint64_t sequence = UINT64_MAX;
        assert(device.gpuSubmit(1, client.vmGeneration, &client, graphics, nullptr, nullptr, 1,
                                &sequence, nullptr, {}, nullptr) == kIOReturnBusy);
        assert(sequence == UINT64_MAX && device.gSeq == original);
    };
    fixture.afterVmInstall = [&] { submit(false); };
    fixture.afterOtgLock = [&] { submit(true); };
    ScanoutFlipIntent intent{fixture.home, fixture.mapped, fixture.pin, {}, ScanoutFlipResult::Refused};
    assert(fixture.begin(intent) == kIOReturnSuccess && intent.result == ScanoutFlipResult::Issued);
    assert(sleeps == 2 && !device.dcnSubmitGate.held() && fixture.issues == 1);
    uint64_t sequence = 0;
    assert(device.gpuSubmit(1, client.vmGeneration, &client, true, nullptr, nullptr, 1,
                            &sequence, nullptr, {}, nullptr) == kIOReturnSuccess);
    assert(sequence == original + 1 && sleeps == 2);
}

static void scanoutWriteIsolation(bool direct, bool physicalDrift) {
    CommitFixture fixture(direct);
    auto &device = fixture.scanout.device;
    const auto first = fixture.scanout.frame.host.base + 2 * kPage;
    const auto second = first + 2 * kPage;
    device.dcnQualifiedFlipRoute = [](IOPCIDevice *pci) -> const HubpFlipRoute * { return pci->route; };
    ScanoutFlipIntent intent{fixture.home, fixture.mapped, fixture.pin, {}, ScanoutFlipResult::Refused};
    device.dcnProveGpuVmOwnership = nullptr;
    assert(fixture.begin(intent) == kIOReturnNotReady && !device.dcnManagedWrites.active() && !fixture.vmWrites);
    device.dcnProveGpuVmOwnership = PhxBringup::proveIsolation;
    device.isolationEvidence = false;
    assert(fixture.begin(intent) == kIOReturnNotReady && !device.dcnManagedWrites.active() && !fixture.vmWrites);
    device.isolationEvidence = true;
    fixture.pageReads = 0;
    assert(fixture.begin(intent) == kIOReturnSuccess && intent.result == ScanoutFlipResult::Issued);
    assert(!device.dcnSubmitGate.held() && device.dcnManagedWrites.excludes(first) && device.dcnManagedWrites.excludes(second));

    Descriptor alias;
    device.vm[1].busy = true;
    device.vm[1].client = &alias;
    const auto map = [&] { return device.guardedVmMap(2, device.vm[1].generation, &alias, 4 * kVa, &alias, 0, 2 * kPage); };
    alias.base = first - 2 * kPage;
    assert(map() == kIOReturnBusy && !device.pteLookups && !device.lastPte && !device.exactVMFault);
    alias.base = second + 4 * kPage;
    assert(map() == kIOReturnSuccess && device.pteLookups == 2);

    if (physicalDrift) {
        const auto count = alias.reads;
        alias.afterRead = [&] { if (alias.reads == count + 4) alias.base = first; };
        assert(map() == kIOReturnVMError && device.pteLookups == 3 && device.exactVMFault);
        assert(device.dcnManagedWrites.excludes(second));
        return;
    }

    ScanoutFlipPoll poll{intent.operation, ScanoutFlipResult::Refused};
    fixture.pending = false;
    fixture.active = fixture.earliest = fixture.mapped;
    fixture.retire = true;
    fixture.step(poll, ScanoutFlipResult::Waiting);
    fixture.step(poll, ScanoutFlipResult::Presented);
    alias.base = first;
    assert(map() == kIOReturnBusy && device.pteLookups == 2);
    intent = {fixture.mapped, fixture.home, {}, {}, ScanoutFlipResult::Refused};
    assert(fixture.begin(intent) == kIOReturnSuccess && intent.result == ScanoutFlipResult::Issued);
    poll.operation = intent.operation;
    fixture.pending = fixture.retire = false;
    fixture.active = fixture.earliest = fixture.home;
    fixture.step(poll, ScanoutFlipResult::Waiting);
    fixture.step(poll, ScanoutFlipResult::Waiting);
    fixture.retire = true;
    fixture.step(poll, ScanoutFlipResult::Presented);
    assert(!device.dcnManagedWrites.active() && map() == kIOReturnSuccess && device.pteLookups == 4);
}

static void managedWriteHistoryLimits() {
    DcnGpuWriteHistory<1> history;
    const uint64_t page = 29 * kPage, next = page + kPage;
    DcnManagedWriteExclusion blocked{};
    history.mapped(128, page);
    history.bound(128, 31);
    assert(history.exclusion({&page, 1}, blocked));
    assert(blocked.blocksContext(128) && !blocked.blocksContext(127) && blocked.blocksSlot(31));
    history.mapped(1, page);
    assert(history.exclusion({&page, 1}, blocked) && blocked.blocksContext(1));
    DcnManagedWriteHolds holds;
    assert(holds.acquire({&page, 1}, blocked));
    DcnManagedWriteExclusion alternate{};
    alternate.contexts[0] = 1ull << 1;
    alternate.slots = 1u << 5;
    assert(holds.acquire({&next, 1}, alternate));
    history.mapped(1, next);
    assert(!history.exclusion({&page, 1}, blocked) && blocked.blocksContext(128) && blocked.blocksSlot(31));
    assert(holds.blocksContext(1) && holds.blocksContext(2) && holds.blocksSlot(31) && holds.blocksSlot(5));
    holds.release({&page, 1});
    assert(!holds.blocksContext(1) && holds.blocksContext(2) && !holds.blocksSlot(31) && holds.blocksSlot(5));
    holds.release({&next, 1});
    assert(!holds.active());

    DcnGpuWriteHistory<1> noMemory;
    DcnAllocationStub::fail = true;
    noMemory.mapped(1, page);
    DcnAllocationStub::fail = false;
    noMemory.mapped(1, page);
    assert(!noMemory.exclusion({&page, 1}, blocked));
}

static void scanoutHistoricalAliases(bool direct) {
    CommitFixture fixture(direct);
    auto &scanout = fixture.scanout;
    auto &device = scanout.device;
    auto &client = scanout.client;
    Descriptor alias, reused, unrelated;
    alias.base = scanout.frame.host.base + 2 * kPage;
    for (uint32_t handle = 2; handle <= device.kMaxCtx; ++handle) device.vm[handle - 1].busy = true;
    device.vm[1].client = &alias;
    device.vm[2].client = &reused;
    device.vm[3].client = &unrelated;
    const auto bind = [&](uint32_t handle) {
        auto &ctx = device.vm[handle - 1];
        IOLockLock(device.gpuLock);
        const auto assigned = device.vmBind(handle, ctx.generation, ctx.client, device.gSeq);
        IOLockUnlock(device.gpuLock);
        return assigned;
    };
    assert(device.guardedVmMap(1, client.vmGeneration, &client, kVa, &alias, 0, 2 * kPage) == kIOReturnSuccess);
    assert(bind(1) == kFirstUserVmid && bind(2) == kFirstUserVmid + 1);
    assert(device.guardedVmMap(2, device.vm[1].generation, &alias, 2 * kVa, &alias, 0, kPage) == kIOReturnSuccess);
    ++device.vm[1].generation;
    device.vm[1].hw = 0;
    device.hwv[1] = {};
    assert(bind(3) == kFirstUserVmid + 1);
    device.dcnQualifiedFlipRoute = [](IOPCIDevice *pci) -> const HubpFlipRoute * { return pci->route; };
    ScanoutFlipIntent intent{fixture.home, fixture.mapped, fixture.pin, {}, ScanoutFlipResult::Refused};
    assert(fixture.begin(intent) == kIOReturnSuccess && intent.result == ScanoutFlipResult::Issued);
    const auto &holds = device.dcnManagedWrites;
    assert(!device.dcnSubmitGate.held() && holds.blocksContext(1) && holds.blocksContext(2) && !holds.blocksContext(3));
    assert(holds.blocksSlot(0) && holds.blocksSlot(1) && !holds.blocksSlot(2));
    const auto writes = device.gpuVmWrites;
    assert(!bind(1) && !bind(2) && !bind(3) && device.gpuVmWrites == writes);
    device.vm[2].hw = 0;
    device.hwv[1] = {};
    assert(bind(4) == kFirstUserVmid + 2 && device.gpuVmWrites == writes + 7);
    const auto submit = [&](uint32_t handle, bool graphics, IOReturn expected) {
        auto &ctx = device.vm[handle - 1];
        uint64_t sequence = UINT64_MAX;
        const auto prior = device.gSeq;
        assert(device.gpuSubmit(handle, ctx.generation, ctx.client, graphics, nullptr, nullptr, 1, &sequence,
                                nullptr, {}, nullptr) == expected);
        assert(expected == kIOReturnSuccess ? sequence == prior + 1 : sequence == UINT64_MAX && device.gSeq == prior);
    };
    submit(1, true, kIOReturnBusy);
    submit(2, false, kIOReturnBusy);
    submit(4, true, kIOReturnSuccess);

    ScanoutFlipPoll poll{intent.operation, ScanoutFlipResult::Refused};
    fixture.pending = false;
    fixture.retire = true;
    fixture.active = fixture.earliest = fixture.mapped;
    fixture.step(poll, ScanoutFlipResult::Waiting);
    fixture.step(poll, ScanoutFlipResult::Presented);
    submit(1, false, kIOReturnBusy);
    intent = {fixture.mapped, fixture.home, {}, {}, ScanoutFlipResult::Refused};
    assert(fixture.begin(intent) == kIOReturnSuccess && intent.result == ScanoutFlipResult::Issued);
    poll.operation = intent.operation;
    fixture.pending = fixture.retire = false;
    fixture.active = fixture.earliest = fixture.home;
    fixture.step(poll, ScanoutFlipResult::Waiting);
    fixture.step(poll, ScanoutFlipResult::Waiting);
    fixture.retire = true;
    fixture.step(poll, ScanoutFlipResult::Presented);
    assert(!holds.active() && bind(1) == kFirstUserVmid && bind(2) == kFirstUserVmid + 1);
    submit(1, false, kIOReturnSuccess);
}

struct ScanoutPermissionFixture : CommitFixture {
    IOBufferMemoryDescriptor directories, leaves;

    explicit ScanoutPermissionFixture(bool direct = false) : CommitFixture(direct) {
        auto &device = scanout.device;
        auto &context = device.vm[0];
        context.used = 4;
        context.pages = device.kPtChunks * device.kPtChunkPages;
        context.chunk[0] = &directories;
        context.chunk[1] = &leaves;
        context.chunkPhys[0] = context.phys;
        context.chunkPhys[1] = context.phys + 16 * kPage;
        directories.words[0] = (context.phys + kPage) | 7;
        directories.words[512] = context.chunkPhys[1] | 7;
        leaves.words[0] = (context.chunkPhys[1] + kPage) | 7;
        device.testGpuLeaf = leaves.words + 512;
        auto &frame = scanout.frame;
        map(frame.host, kVa);
        map(frame.host, 3 * kVa);
        IOLockLock(device.gpuLock);
        assert(device.vmBind(1, context.generation, &scanout.client, device.gSeq) == kFirstUserVmid);
        IOLockUnlock(device.gpuLock);
        device.dcnQualifiedFlipRoute = [](IOPCIDevice *pci) -> const HubpFlipRoute * { return pci->route; };
        device.dcnGpuPermissionEvidence = [](PhxBringup &provider, const DcnGpuPermissionUse &use,
                                               DcnGpuPermissionPhase phase) {
            assert(provider.guard.held && provider.permission && use.serial && use.owner.context == 1 && !use.owner.slot);
            return provider.permission(use, phase);
        };
        device.permission = [](const DcnGpuPermissionUse &use, DcnGpuPermissionPhase phase) {
            return DcnGpuPermissionAck{use.serial, use.owner, phase};
        };
    }

    void map(Descriptor &descriptor, uint64_t va) {
        assert(scanout.device.guardedVmMap(1, scanout.client.vmGeneration, &scanout.client, va, &descriptor,
                                          kPage, 2 * kPage) == kIOReturnSuccess);
    }

    uint64_t &leaf(uint64_t va) { return scanout.device.testGpuLeaf[va / kPage]; }

    bool writable(uint64_t va) { return leaf(va) & kGpuPteWrite; }

    void submit(bool gfx, IOReturn expected) {
        uint64_t sequence = UINT64_MAX;
        auto &device = scanout.device;
        assert(device.gpuSubmit(1, scanout.client.vmGeneration, &scanout.client, gfx, nullptr, nullptr, 1,
                                &sequence, nullptr, {}, nullptr) == expected);
        assert((sequence != UINT64_MAX) == (expected == kIOReturnSuccess));
    }
};

static void scanoutReadOnlyRejection(bool stale, bool brokenTable, bool afterWrite) {
    ScanoutPermissionFixture fixture;
    auto &device = fixture.scanout.device;
    if (brokenTable) fixture.directories.words[1] = fixture.directories.words[0];
    unsigned permissions = 0;
    device.permission = [&](const DcnGpuPermissionUse &use, DcnGpuPermissionPhase phase) {
        ++permissions;
        auto serial = use.serial;
        if (stale && (phase == DcnGpuPermissionPhase::Restricted) == afterWrite) --serial;
        return DcnGpuPermissionAck{serial, use.owner, phase};
    };
    ScanoutFlipIntent intent{fixture.home, fixture.mapped, fixture.pin, {}, ScanoutFlipResult::Refused};
    assert(fixture.begin(intent) == kIOReturnNotReady && !fixture.vmWrites && !fixture.writes && !intent.operation.serial);
    assert(permissions == (brokenTable ? 0u : afterWrite ? 2u : 1u));
    assert(fixture.writable(kVa) == !afterWrite && fixture.writable(3 * kVa) == !afterWrite && device.exactVMFault == afterWrite);
    assert(!device.dcnManagedWrites.active() && fixture.scanout.cancelPin(fixture.pin) == kIOReturnSuccess);
}

static void scanoutReadOnlyDoubleBuffer(bool loseRestore) {
    ScanoutPermissionFixture fixture;
    auto &scanout = fixture.scanout;
    auto &device = scanout.device;
    auto &frame = scanout.frame;
    ScanoutFlipIntent intent{fixture.home, fixture.mapped, fixture.pin, {}, ScanoutFlipResult::Refused};
    assert(fixture.begin(intent) == kIOReturnSuccess && intent.result == ScanoutFlipResult::Issued);
    assert(!fixture.writable(kVa) && !fixture.writable(kVa + kPage) && !fixture.writable(3 * kVa));
    assert(device.dcnManagedWrites.pinsContext(1) && device.dcnManagedWrites.pinsSlot(0));
    assert(!device.vmidFree(1, scanout.client.vmGeneration, &scanout.client, device.gSeq));
    assert(!device.vm[0].closing && device.vm[0].hw == kFirstUserVmid);
    IOLockLock(device.gpuLock);
    for (uint32_t handle = 2; handle <= device.kMaxCtx; ++handle) {
        auto &context = device.vm[handle - 1];
        context.busy = true;
        context.client = &context;
        const auto expected = kFirstUserVmid + (handle == 3 ? 2 : 1);
        assert(device.vmBind(handle, context.generation, context.client, device.gSeq) == expected);
    }
    IOLockUnlock(device.gpuLock);
    assert(device.hwv[0].ctx == 1 && device.vm[0].hw == kFirstUserVmid);

    ScanoutFlipPoll poll{intent.operation, ScanoutFlipResult::Refused};
    fixture.pending = false;
    fixture.retire = true;
    fixture.active = fixture.earliest = fixture.mapped;
    fixture.step(poll, ScanoutFlipResult::Waiting);
    fixture.step(poll, ScanoutFlipResult::Presented);

    fixture.selectAlternate();
    frame.client.boTable[1].md = &frame.host;
    frame.client.boTable[2].md = &fixture.nextHost;
    assert(frame.client.changeMap(PHX_AMDGPU_VA_OP_MAP, 2 * kVa, 2, kPage, 2 * kPage) == kIOReturnSuccess);
    frame.request.writer.range = {2 * kVa, 2 * kPage, 2, 0};
    frame.copy.scanout = {64, 17, fixture.pitch, 8, 2 * kPage};
    fixture.map(fixture.nextHost, 2 * kVa);
    assert(fixture.writable(2 * kVa) && !fixture.writable(kVa));
    scanout.offer();
    DmaRun scratch[2]{};
    uint64_t pages[2]{};
    ScanoutDmaRequest mapped{&frame.copy, fixture.alternate.address, scratch, 2, pages, 2, {}, {}};
    const OSSymbol map{BUILD34_DCN_PIN_MAP};
    assert(fixture.dispatch(map, &mapped) == kIOReturnSuccess && mapped.token.serial);
    fixture.alternatePin = mapped.token;
    intent = {fixture.mapped, fixture.alternate, fixture.alternatePin, {}, ScanoutFlipResult::Refused};
    assert(fixture.begin(intent) == kIOReturnSuccess && intent.result == ScanoutFlipResult::Issued);
    assert(!fixture.writable(kVa) && !fixture.writable(2 * kVa));
    fixture.submit(false, kIOReturnSuccess);
    const auto compute = device.gSeq;
    poll.operation = intent.operation;
    fixture.pending = false;
    fixture.active = fixture.earliest = fixture.alternate;
    fixture.step(poll, ScanoutFlipResult::Waiting);
    fixture.step(poll, ScanoutFlipResult::Waiting);
    assert(!fixture.writable(kVa) && !fixture.command.completes);
    fixture.submit(true, kIOReturnBusy);
    device.done[0] = compute;
    device.permission = [&](const DcnGpuPermissionUse &use, DcnGpuPermissionPhase phase) {
        return DcnGpuPermissionAck{use.serial - (loseRestore && phase == DcnGpuPermissionPhase::Restored), use.owner, phase};
    };
    fixture.step(poll, loseRestore ? ScanoutFlipResult::Uncertain : ScanoutFlipResult::Presented);
    assert(fixture.writable(kVa) && fixture.writable(3 * kVa) && !fixture.writable(2 * kVa));
    assert(device.dcnManagedWrites.excludes(frame.host.base + 2 * kPage) == loseRestore);
    assert(device.dcnManagedWrites.excludes(fixture.nextHost.base + 2 * kPage) && device.exactVMFault == loseRestore);
    fixture.submit(true, loseRestore ? kIOReturnBusy : kIOReturnSuccess);
    ++device.exactInvalidationEpoch;
    fixture.submit(true, kIOReturnNotReady);
}

enum class PixelFault { MapperRemap, MapperUnavailable, RenderPage, PresentPage, RenderGeneration, PresentGeneration,
                        LateGeneration, WrongCommandSlice, SubstitutedDescriptor, LateEvidence, FrontRemap, None };

static void revalidateScanoutPixels(PixelFault fault) {
    CommitFixture fixture;
    auto &scanout = fixture.scanout;
    auto &host = scanout.frame.host;
    auto &present = scanout.frame.present;
    assert(present.prepares == 1 && present.wires == 2 && present.references == 2);
    assert(present.complete() == kIOReturnSuccess && present.wires == 1);
    scanout.device.dcnQualifiedFlipRoute = [](IOPCIDevice *device) -> const HubpFlipRoute * { return device->route; };
    ScanoutFlipIntent request{fixture.home, fixture.mapped, fixture.pin, {}, ScanoutFlipResult::Refused};
    if (fault == PixelFault::RenderPage) host.wrongPage = 2 * kPage;
    if (fault == PixelFault::PresentPage) present.wrongPage = kPage;
    if (fault == PixelFault::RenderGeneration) ++host.preparation;
    if (fault == PixelFault::PresentGeneration) ++present.preparation;
    fixture.command.wrongOffset = fault == PixelFault::WrongCommandSlice;
    if (fault == PixelFault::SubstitutedDescriptor) fixture.command.substitute = &present;
    fixture.pixelEvidence = [&](bool first, uint64_t &physical) {
        assert(!fixture.lockRequested && !scanout.device.guard.held && !scanout.client.guard.held);
        if (first) return true;
        if (fault == PixelFault::MapperRemap) physical ^= kPage;
        if (fault == PixelFault::LateGeneration) ++present.preparation;
        if (fault == PixelFault::LateEvidence) fixture.now += 100000000;
        return fault != PixelFault::MapperUnavailable;
    };
    if (fault != PixelFault::FrontRemap && fault != PixelFault::None) {
        assert(fixture.begin(request) == kIOReturnNotReady && !request.operation.serial);
        assert(!fixture.vmWrites && !fixture.writes && !fixture.issues && !fixture.command.completes);
        const unsigned expectedReads = fault <= PixelFault::MapperUnavailable || fault == PixelFault::LateGeneration ||
            fault == PixelFault::LateEvidence ? 2 : fault <= PixelFault::PresentPage ? 1 : 0;
        assert(fixture.pixelReads == 2 + expectedReads && present.wires == 1 && present.references == 2);
        fixture.command.substitute = nullptr;
        assert(scanout.cancelPin(fixture.pin) == kIOReturnSuccess && fixture.command.completes == 1);
        assert(present.wires == 0 && present.references == 1 && host.wires == 1);
        return;
    }
    assert(fixture.begin(request) == kIOReturnSuccess && request.result == ScanoutFlipResult::Issued);
    assert(fixture.pixelReads == 4 && present.wires == 1 && present.references == 2);
    ScanoutFlipPoll poll{request.operation, ScanoutFlipResult::Refused};
    fixture.pending = false;
    fixture.retire = true;
    fixture.active = fixture.earliest = fixture.mapped;
    fixture.step(poll, ScanoutFlipResult::Waiting);
    fixture.step(poll, ScanoutFlipResult::Presented);
    fixture.completeNewComputeWork();
    request = {fixture.mapped, fixture.home, {}, {}, ScanoutFlipResult::Refused};
    if (fault == PixelFault::FrontRemap) {
        fixture.pixelEvidence = [](bool first, uint64_t &physical) {
            if (!first) physical ^= kPage;
            return true;
        };
        assert(fixture.begin(request) == kIOReturnNotReady && !request.operation.serial);
        assert(fixture.pixelReads == 6 && fixture.vmWrites == 7 && fixture.writes == 5 && !fixture.command.completes);
        assert(present.wires == 1 && scanout.cancelPin(fixture.pin) == kIOReturnNotFound);
        fixture.pixelEvidence = {};
    }
    assert(fixture.begin(request) == kIOReturnSuccess && request.result == ScanoutFlipResult::Issued);
    poll.operation = request.operation;
    fixture.pending = false;
    fixture.retire = false;
    fixture.active = fixture.earliest = fixture.home;
    fixture.step(poll, ScanoutFlipResult::Waiting);
    fixture.step(poll, ScanoutFlipResult::Waiting);
    assert(!fixture.command.completes && present.wires == 1);
    fixture.retire = true;
    fixture.step(poll, ScanoutFlipResult::Presented);
    assert(fixture.command.completes == 1 && present.wires == 0 && present.references == 1 && host.wires == 1);
}

enum class DirectFlipFault { None, DeniedTable, ShortTable, DomainLost, ReplacedPci, WriteableLeaf, WindowConflict,
                             DomainLostAfterIssue, WindowConflictAtRetirement };

static void scanoutDirectFlip(DirectFlipFault fault) {
    CommitFixture fixture(true);
    auto &scanout = fixture.scanout;
    auto &pci = *scanout.device.pci;
    assert(pci.mapperLookups == 0 && pci.references == 2 && fixture.pixelReads == 2);
    scanout.device.dcnQualifiedFlipRoute = [](IOPCIDevice *device) -> const HubpFlipRoute * { return device->route; };
    if (fault == DirectFlipFault::DeniedTable) {
        const auto original = pci.directEvidence;
        pci.directEvidence = [original](const IOMemoryDescriptor &descriptor, uint64_t offset, uint64_t physical, DcnDirectUse use) {
            return use != DcnDirectUse::Table && original(descriptor, offset, physical, use);
        };
    }
    if (fault == DirectFlipFault::ShortTable) fixture.homeTable.shortPhysical = true;
    if (fault == DirectFlipFault::DomainLost) ++pci.directGeneration;
    fixture.flatWindowConflict = fault == DirectFlipFault::WindowConflict;
    if (fault == DirectFlipFault::WriteableLeaf) {
        const auto verifyStored = fixture.homeTable.onStore;
        fixture.homeTable.onStore = [&, verifyStored] {
            verifyStored();
            fixture.homeTable.words[1] |= 0x40;
        };
    }
    IOPCIDevice replacement;
    if (fault == DirectFlipFault::ReplacedPci) {
        replacement.route = &fixture.route;
        fixture.framebuffer.provider = &replacement;
        scanout.device.pci = &replacement;
    }
    ScanoutFlipIntent intent{fixture.home, fixture.mapped, fixture.pin, {}, ScanoutFlipResult::Refused};
    if (fault != DirectFlipFault::None && fault != DirectFlipFault::DomainLostAfterIssue &&
        fault != DirectFlipFault::WindowConflictAtRetirement) {
        assert(fixture.begin(intent) == kIOReturnNotReady && !intent.operation.serial && !fixture.writes && !fixture.vmWrites);
        assert(!fixture.command.created && !fixture.homeTable.dma.created && !pci.mapperLookups);
        assert(fixture.homeTable.stores == (fault == DirectFlipFault::WriteableLeaf));
        assert(scanout.cancelPin(fixture.pin) == kIOReturnSuccess && pci.references == 1 && !fixture.homeTable.references);
        return;
    }
    assert(fixture.begin(intent) == kIOReturnSuccess && intent.result == ScanoutFlipResult::Issued);
    assert(fixture.homeTable.direct && fixture.homeTable.references == 1 && fixture.pixelReads == 4);
    assert(fixture.writes == 5 && fixture.vmWrites == 7 && fixture.homeTable.stores == 1 && !fixture.command.created);
    assert(!fixture.homeTable.dma.created && scanout.frame.host.wires == 2 && scanout.frame.present.wires == 2);
    ScanoutFlipPoll poll{intent.operation, ScanoutFlipResult::Refused};
    fixture.pending = false;
    fixture.active = fixture.earliest = fixture.mapped;
    if (fault == DirectFlipFault::DomainLostAfterIssue) {
        ++pci.directGeneration;
        fixture.step(poll, ScanoutFlipResult::Uncertain);
        assert(pci.references == 2 && fixture.homeTable.references == 1 && scanout.frame.present.wires == 2);
        assert(scanout.cancelPin(fixture.pin) == kIOReturnNotFound && !pci.mapperLookups);
        return;
    }
    fixture.retire = true;
    fixture.step(poll, ScanoutFlipResult::Waiting);
    fixture.step(poll, ScanoutFlipResult::Presented);
    intent = {fixture.mapped, fixture.home, {}, {}, ScanoutFlipResult::Refused};
    assert(fixture.begin(intent) == kIOReturnSuccess && intent.result == ScanoutFlipResult::Issued);
    poll.operation = intent.operation;
    fixture.pending = fixture.retire = false;
    fixture.active = fixture.earliest = fixture.home;
    fixture.step(poll, ScanoutFlipResult::Waiting);
    fixture.step(poll, ScanoutFlipResult::Waiting);
    assert(fixture.homeTable.references == 1 && pci.references == 2 && !fixture.clearWrites);
    fixture.retire = true;
    if (fault == DirectFlipFault::WindowConflictAtRetirement) {
        fixture.flatWindowConflict = true;
        fixture.step(poll, ScanoutFlipResult::Uncertain);
        assert(!fixture.clearWrites && !fixture.translationChecks && pci.references == 2 && fixture.homeTable.references == 1);
        assert(scanout.frame.host.wires == 2 && scanout.frame.present.wires == 2);
        return;
    }
    fixture.step(poll, ScanoutFlipResult::Presented);
    assert(fixture.clearWrites == 7 && fixture.translationChecks && fixture.pixelReads == 6 && !fixture.homeTable.references);
    assert(!fixture.command.created && !fixture.homeTable.dma.created && !pci.mapperLookups && pci.references == 1);
    assert(scanout.frame.host.wires == 1 && scanout.frame.present.wires == 1 && !DcnAllocationStub::live());
}

static void rejectChangedPresentWindows() {
    CommitFixture fixture;
    fixture.scanout.device.dcnQualifiedFlipRoute = [](IOPCIDevice *device) -> const HubpFlipRoute * { return device->route; };
    fixture.route.presentWindows = {{fixture.mapped, 2 * kPage}, {fixture.alternate, 2 * kPage}, DcnPresentDomain::Mapped};
    ScanoutFlipIntent request{fixture.home, fixture.mapped, fixture.pin, {}, ScanoutFlipResult::Refused, &fixture.framebuffer};
    for (unsigned fault = 0; fault < 5; ++fault) {
        auto planned = fixture.route;
        request.plannedRoute = &planned;
        if (fault == 0) ++planned.generation;
        if (fault == 1) planned.presentWindows.second.bytes += kPage;
        if (fault == 2) planned.reader.context = &planned;
        if (fault == 3) request.next = fixture.alternate;
        if (fault == 4) fixture.route.presentWindows.domain = planned.presentWindows.domain = DcnPresentDomain::Direct;
        assert(fixture.begin(request) == kIOReturnNotReady && !request.operation.serial &&
               !fixture.reads && !fixture.issues && !fixture.vmWrites && !fixture.writes);
        request.next = fixture.mapped;
    }
    assert(fixture.scanout.cancelPin(fixture.pin) == kIOReturnSuccess);
}

static void presentWindowRetirement(bool conflict) {
    CommitFixture fixture;
    auto &device = fixture.scanout.device;
    device.dcnQualifiedFlipRoute = [](IOPCIDevice *device) -> const HubpFlipRoute * { return device->route; };
    fixture.route.presentWindows = {{fixture.mapped, 2 * kPage}, {fixture.alternate, 2 * kPage}, DcnPresentDomain::Mapped};
    const auto planned = fixture.route;
    ScanoutFlipIntent incoming{fixture.home, fixture.mapped, fixture.pin, {}, ScanoutFlipResult::Refused, &fixture.framebuffer, &planned};
    assert(fixture.begin(incoming) == kIOReturnSuccess && incoming.result == ScanoutFlipResult::Issued);
    ScanoutFlipPoll poll{incoming.operation, ScanoutFlipResult::Refused};
    fixture.pending = false;
    fixture.active = fixture.earliest = fixture.mapped;
    fixture.retire = true;
    fixture.step(poll, ScanoutFlipResult::Waiting);
    fixture.flatWindowConflict = conflict;
    fixture.step(poll, conflict ? ScanoutFlipResult::Uncertain : ScanoutFlipResult::Presented);
    assert(fixture.command.prepared && !fixture.command.completes);
    if (conflict) return;

    assert(device.dcnFlip.matchesPresentWindows(planned.presentWindows));
    ScanoutFlipIntent home{fixture.mapped, fixture.home, {}, {}, ScanoutFlipResult::Refused, &fixture.framebuffer};
    fixture.route.presentWindows.second.bytes -= kPage;
    assert(fixture.begin(home) == kIOReturnNotReady && fixture.issues == 1 && !fixture.clearWrites);
    fixture.route.presentWindows = planned.presentWindows;
    assert(fixture.begin(home) == kIOReturnSuccess && home.result == ScanoutFlipResult::Issued);
    poll.operation = home.operation;
    fixture.target = fixture.active = fixture.earliest = fixture.home;
    fixture.pending = false;
    fixture.retire = false;
    fixture.step(poll, ScanoutFlipResult::Waiting);
    fixture.step(poll, ScanoutFlipResult::Waiting);
    fixture.retire = true;
    fixture.step(poll, ScanoutFlipResult::Presented);
    assert(!device.dcnFlip.front().serial && fixture.command.completes == 1);
}

static void scanoutFlip(FlipFault fault) {
    CommitFixture fixture;
    auto &scanout = fixture.scanout;
    ScanoutFlipIntent request{fixture.home, fixture.mapped, fixture.pin, {}, ScanoutFlipResult::Refused};
    assert(fixture.begin(request) == kIOReturnNotReady && !fixture.reads && !fixture.issues);
    scanout.device.dcnQualifiedFlipRoute = [](IOPCIDevice *device) -> const HubpFlipRoute * { return device->route; };
    request.next.address += kPage;
    assert(fixture.begin(request) == kIOReturnNotReady && !fixture.reads && !fixture.issues);
    request.next = fixture.mapped;
    fixture.qualify = fault != FlipFault::Decline;
    fixture.closeDuringQualify = fault == FlipFault::CloseDuringQualify;
    fixture.lockSelect = fault == FlipFault::ForeignLock ? 1u << 25 : 0;
    fixture.lockRequested = fixture.lockHeld = fault == FlipFault::HeldLock;
    fixture.surfaceControl = fault == FlipFault::Dcc ? 1u << 1 : 0;
    if (fault == FlipFault::Protected) fixture.surfaceControl |= 1u << 17;
    fixture.surfaceFormat += fault == FlipFault::WrongFormat;
    if (fault == FlipFault::AlphaPlane) fixture.surfaceFormat |= 1u << 11;
    if (fault == FlipFault::SwappedChannels) fixture.returnControl = 0x00b00000;
    fixture.swizzle = fault == FlipFault::Tiled;
    fixture.start = fault == FlipFault::Cropped ? 1u << 16 : 0;
    fixture.dimensions -= fault == FlipFault::WrongViewport;
    fixture.pitch += fault == FlipFault::WrongPitch;
    if (fault == FlipFault::SplitInput) fixture.odm |= 1u;
    if (fault == FlipFault::SplitOutput) fixture.odm |= 1u << 8;
    if (fault == FlipFault::WrongOdmSource) fixture.odm |= 1u << 16;
    if (fault == FlipFault::DisabledOtg) fixture.otg &= ~0x00010000u;
    fixture.changeGeometryAtLock = fault == FlipFault::GeometryAtLock;
    fixture.lockTimeout = fault == FlipFault::LockTimeout;
    fixture.unlockTimeout = fault == FlipFault::UnlockTimeout;
    fixture.failHigh = fault == FlipFault::HighWrite;
    fixture.loseRouteAfterHigh = fault == FlipFault::RouteLost;
    fixture.rewindAfterHigh = fault == FlipFault::ClockRewind;
    fixture.failIssue = fault == FlipFault::Issue;
    fixture.translationFault = fault;
    if (fault == FlipFault::PeerActive || fault == FlipFault::PeerShortWindow || fault == FlipFault::NoRetirementProof) {
        if (fault == FlipFault::PeerShortWindow) fixture.route.reader.apertureBytes = 0x05181 * sizeof(uint32_t);
        if (fault == FlipFault::NoRetirementProof) fixture.route.translationsRetired = nullptr;
        assert(fixture.begin(request) == kIOReturnNotReady && !request.operation.serial);
        assert(!fixture.writes && !fixture.vmWrites && !fixture.issues && !fixture.homeTable.stores &&
               fixture.command.prepared && fixture.framebuffer.references == 1);
        return;
    }
    if (fault >= FlipFault::MissingFramebuffer && fault <= FlipFault::WrongHomeBacking) {
        if (fault == FlipFault::MissingFramebuffer) fixture.route.framebuffer = nullptr;
        if (fault == FlipFault::WrongFramebufferPci) fixture.framebuffer.provider = &fixture;
        if (fault == FlipFault::WrongFramebufferType) fixture.framebuffer.isPhxFramebuffer = false;
        if (fault == FlipFault::InactiveFramebuffer) fixture.framebuffer.inactive = true;
        const bool admitted = fault >= FlipFault::NoHomeSample;
        assert(fixture.begin(request) == kIOReturnNotReady && !request.operation.serial);
        assert(!fixture.writes && !fixture.vmWrites && !fixture.issues && !fixture.command.completes);
        assert(bool(fixture.reads) == admitted && fixture.framebuffer.samples == admitted);
        assert(fixture.framebuffer.checks == (fault == FlipFault::WrongHomeBacking ? 1u : 0u));
        assert(fixture.framebuffer.references == 1 && fixture.framebuffer.releases == admitted &&
               fixture.lifetime.references == 1);
        return;
    }
    if (fault == FlipFault::InstallOccupied) fixture.contextRoot = fixture.ownedRoot;
    if (fault == FlipFault::InstallMissingProof) fixture.route.canInstallFlatVm = nullptr;
    if (fault == FlipFault::InstallSameVmid) {
        request.previous.vmid = fixture.mapped.vmid;
        fixture.programmed = fixture.active = fixture.earliest = request.previous;
    }
    if (fault == FlipFault::RetryTable) {
        fixture.translationFault = FlipFault::InstallDenied;
        assert(fixture.begin(request) == kIOReturnNotReady && !request.operation.serial && !fixture.vmWrites);
        assert(fixture.homeTable.stores == 1 && fixture.homeTable.dma.prepared && fixture.homeTable.references == 2);
        fixture.translationFault = FlipFault::None;
    }
    if (fault >= FlipFault::InstallDenied && fault <= FlipFault::InstallWrongLeaf) {
        assert(fixture.begin(request) == kIOReturnNotReady && !request.operation.serial);
        assert(!fixture.writes && !fixture.vmWrites && fixture.pageReads == (fault == FlipFault::InstallWrongLeaf ? 2u : 0u));
        const bool acquired = fault == FlipFault::InstallDenied || fault == FlipFault::InstallOccupied ||
            fault == FlipFault::InstallWrongLeaf;
        assert(fixture.command.prepared && fixture.lifetime.references == (acquired ? 2u : 1u));
        return;
    }
    if (fault >= FlipFault::InstallRevoked && fault <= FlipFault::InstallWrongAck) {
        assert(fixture.begin(request) == kIOReturnSuccess && request.result == ScanoutFlipResult::Uncertain);
        assert(!fixture.writes && fixture.vmWrites == (fault == FlipFault::InstallRevoked ? 3u : 7u));
        assert(fixture.delays == (fault == FlipFault::InstallAckTimeout ? 9u : 0u));
        assert(fixture.command.prepared && fixture.lifetime.references == 3 && DcnAllocationStub::live() == 1);
        assert(scanout.cancelPin(fixture.pin) == kIOReturnNotFound);
        ScanoutFlipPoll poll{request.operation, ScanoutFlipResult::Refused};
        fixture.step(poll, ScanoutFlipResult::Uncertain);
        assert(!fixture.writes && !fixture.retireChecks);
        return;
    }
    if (fault == FlipFault::NoContextRoot || fault == FlipFault::NoTranslationReader) {
        if (fault == FlipFault::NoContextRoot) fixture.route.flatFormat.encodeRoot = nullptr;
        else fixture.route.flatFormat.decodeLeaf = nullptr;
        assert(fixture.begin(request) == kIOReturnNotReady && !fixture.reads && !fixture.writes && !fixture.pageReads);
        return;
    }
    if (fault == FlipFault::UnreadyContext) fixture.contextRoot = fixture.ownedRoot & ~uint64_t{1};
    if (fault == FlipFault::WrongContextRoot) fixture.contextRoot ^= 1ull << 32;
    if (fault == FlipFault::WrongContextDepth) fixture.contextControl |= 1u << 1;
    if (fault == FlipFault::WrongContextBlock) fixture.contextControl |= 1u << 3;
    if (fault == FlipFault::WrongContextStart) fixture.firstPage ^= 1ull << 32;
    if (fault == FlipFault::WrongContextEnd) ++fixture.lastPage;
    if (fault >= FlipFault::UnreadyContext && fault <= FlipFault::ContextAfterPageWalk) {
        assert(fixture.begin(request) == kIOReturnNotReady && fixture.reads && !fixture.writes && !request.operation.serial);
        assert(fixture.pageReads == (fault == FlipFault::ContextAfterPageWalk ? 2u : 0u));
        assert(fixture.command.prepared && fixture.lifetime.references == 2);
        return;
    }
    if (fault >= FlipFault::TranslationError && fault <= FlipFault::RevokedTranslation) {
        assert(fixture.begin(request) == kIOReturnNotReady && !request.operation.serial && !fixture.writes);
        assert(fixture.pageReads == (fault == FlipFault::WrongLastPage ? 2u : 1u));
        assert(fixture.lifetime.references == 2 && fixture.command.prepared && DcnAllocationStub::live() == 1);
        return;
    }
    if (!fixture.qualify || fixture.closeDuringQualify) {
        assert(fixture.begin(request) == kIOReturnNotReady && !fixture.reads && !fixture.issues);
        assert(!request.operation.serial && fixture.lifetime.references == 1);
        return;
    }
    const bool badGeometry = fault >= FlipFault::WrongFormat && fault <= FlipFault::DisabledOtg;
    if (fixture.lockSelect || fixture.lockHeld || fault == FlipFault::Dcc || badGeometry) {
        assert(fixture.begin(request) == kIOReturnNotReady && fixture.reads && !fixture.writes);
        assert(!request.operation.serial && fixture.lifetime.references == 1);
        return;
    }
    if (fault == FlipFault::CancelWithdrawError) fixture.publicationCurrent = false;
    if ((fault >= FlipFault::NoTableMemory && fault <= FlipFault::PublishCorruptPadding) ||
        fault == FlipFault::CancelWithdrawError || (fault >= FlipFault::TableWrongPhysical && fault <= FlipFault::TableSubstituted)) {
        const bool acquired = fault != FlipFault::NoTableMemory;
        const bool mapped = acquired && fault != FlipFault::ShortTable;
        const bool uncertain = fault == FlipFault::TablePrepareUncertain || fault == FlipFault::TableSubstituted;
        const bool withdrawn = fault != FlipFault::CancelWithdrawError && !uncertain;
        const bool confirmed = mapped && !uncertain;
        assert(fixture.begin(request) == kIOReturnNotReady && !fixture.vmWrites && !fixture.writes);
        assert(fixture.homeTable.references == (mapped ? 2u : acquired ? 1u : 0u) && !fixture.homeTable.withdrawals);
        assert(scanout.cancelPin(fixture.pin) == (withdrawn ? kIOReturnSuccess : kIOReturnNotReady));
        assert(fixture.homeTable.withdrawals == confirmed && fixture.command.completes == withdrawn &&
               fixture.lifetime.references == (withdrawn ? 1u : 2u));
        assert(fixture.homeTable.references == (withdrawn ? 0u : 2u));
        assert(scanout.cancelPin(fixture.pin) == kIOReturnNotFound && fixture.homeTable.withdrawals == confirmed);
        return;
    }
    assert(fixture.begin(request) == kIOReturnSuccess && request.operation.serial != fixture.pin.serial);
    assert(fixture.framebuffer.references == 2 && fixture.framebuffer.releases == (fault == FlipFault::RetryTable));
    if (fault == FlipFault::HomeLostAfterInstall || fault == FlipFault::PeerDuringInstall) {
        const bool installed = fault == FlipFault::HomeLostAfterInstall;
        assert(request.result == ScanoutFlipResult::Uncertain && !fixture.writes && fixture.vmWrites == (installed ? 7u : 3u));
        ScanoutFlipPoll poll{request.operation, ScanoutFlipResult::Refused};
        fixture.step(poll, ScanoutFlipResult::Uncertain);
        assert(fixture.framebuffer.samples == 1 && fixture.framebuffer.checks == (installed ? 3u : 2u) &&
               fixture.framebuffer.references == 2);
        assert(fixture.homeTable.dma.prepared && fixture.command.prepared && !fixture.command.completes);
        assert(scanout.cancelPin(fixture.pin) == kIOReturnNotFound);
        return;
    }
    assert(fixture.writes && fixture.lifetime.references == 3 && !fixture.command.completes && fixture.pageReads == 2);
    assert(fixture.vmWrites == 7 && fixture.homeTable.stores == 1 && fixture.homeTable.references == 2);
    if (fault == FlipFault::Install) assert(fixture.vmAckReads == 3 && fixture.delays == 2);
    assert(scanout.cancelPin(fixture.pin) == kIOReturnNotFound && fixture.begin(request) == kIOReturnBusy);
    ScanoutFlipPoll poll{request.operation, ScanoutFlipResult::Refused};
    const bool afterHigh = fixture.failHigh || fixture.loseRouteAfterHigh || fixture.rewindAfterHigh || fault == FlipFault::PeerAfterHigh;
    const bool atLock = fixture.lockTimeout || fixture.changeGeometryAtLock || fault == FlipFault::ContextAtLock;
    if (atLock || afterHigh || fixture.failIssue || fixture.unlockTimeout) {
        const unsigned expectedWrites = atLock ? 1 : afterHigh ? 3 : fixture.failIssue ? 4 : 5;
        assert(fixture.writes == expectedWrites && fixture.issues == (expectedWrites >= 4));
        assert(fixture.delays == (fixture.lockTimeout || fixture.unlockTimeout ? 9u : 0u));
        assert(request.result == ScanoutFlipResult::Uncertain);
        assert(fixture.poll(poll) == kIOReturnSuccess && poll.result == ScanoutFlipResult::Uncertain);
        assert(fixture.writes == expectedWrites && fixture.retireChecks == 0 && fixture.command.prepared);
        return;
    }
    if (fault == FlipFault::ContextWhilePending || fault == FlipFault::PublicationLost) {
        if (fault == FlipFault::ContextWhilePending) fixture.contextRoot ^= kPage;
        else fixture.publicationCurrent = false;
        fixture.step(poll, ScanoutFlipResult::Uncertain);
        assert(fixture.writes == 5 && !fixture.retireChecks && fixture.command.prepared);
        return;
    }
    assert(request.result == ScanoutFlipResult::Issued && fixture.writes == 5 && fixture.issues == 1);
    if (fault == FlipFault::Close) {
        scanout.device.exactCallbacks.close();
        const auto reads = fixture.reads;
        assert(fixture.poll(poll) == kIOReturnNotReady && fixture.reads == reads && fixture.command.prepared);
        return;
    }
    fixture.step(poll, ScanoutFlipResult::Waiting);
    fixture.pending = false;
    fixture.active = fixture.earliest = fixture.mapped;
    fixture.retire = true;
    fixture.step(poll, ScanoutFlipResult::Waiting);
    if (fault == FlipFault::ContextDuringRetire) {
        fixture.step(poll, ScanoutFlipResult::Uncertain);
        assert(fixture.writes == 5 && fixture.retireChecks == 1 && fixture.command.prepared && !fixture.command.completes);
        return;
    }
    fixture.step(poll, ScanoutFlipResult::Presented);
    assert(!fixture.command.completes && fixture.retireChecks == 1);
    assert(fixture.framebuffer.samples == (fault == FlipFault::RetryTable ? 2u : 1u) && fixture.framebuffer.references == 2);
    assert(fixture.poll(poll) == kIOReturnNotFound && scanout.cancelPin(fixture.pin) == kIOReturnNotFound);

    if (fault == FlipFault::DifferentPinnedPitch) {
        fixture.selectAlternate();
        scanout.frame.copy.scanout = {64, 17, ++fixture.pitch, 8, 2 * kPage};
        scanout.offer();
        DmaRun scratch[2]{};
        uint64_t pages[2]{};
        const HubpAddress next{fixture.mapped.address + 2 * kPage, fixture.mapped.vmid};
        ScanoutDmaRequest mapped{&scanout.frame.copy, next.address, scratch, 2, pages, 2, {}, {}};
        const OSSymbol map{BUILD34_DCN_PIN_MAP};
        assert(fixture.dispatch(map, &mapped) == kIOReturnSuccess && mapped.token.serial);
        const auto reads = fixture.reads;
        ScanoutFlipIntent different{fixture.mapped, next, mapped.token, {}, ScanoutFlipResult::Refused};
        assert(fixture.begin(different) == kIOReturnNotReady && !different.operation.serial);
        assert(fixture.reads == reads && fixture.writes == 5 && !fixture.command.completes);
        return;
    }

    if (fault == FlipFault::DualPins || fault == FlipFault::DualContextDuringRetire || fault == FlipFault::PhysicalAlias ||
        fault == FlipFault::SharedTable || fault == FlipFault::SharedRoot) {
        fixture.selectAlternate(fault == FlipFault::PhysicalAlias);
        scanout.frame.copy.scanout = {64, 17, fixture.pitch, 8, 2 * kPage};
        scanout.offer();
        DmaRun scratch[2]{};
        uint64_t pages[2]{};
        ScanoutDmaRequest mapped{&scanout.frame.copy, fixture.alternate.address, scratch, 2, pages, 2, {}, {}};
        const OSSymbol map{BUILD34_DCN_PIN_MAP};
        assert(fixture.dispatch(map, &mapped) == kIOReturnSuccess && mapped.token.serial);
        fixture.alternatePin = mapped.token;
        request = {fixture.mapped, fixture.alternate, fixture.alternatePin, {}, ScanoutFlipResult::Refused};
        if (fault == FlipFault::PhysicalAlias) {
            assert(pages[0] == 0x800000 && pages[1] == 0x901000);
            assert(fixture.begin(request) == kIOReturnNotReady && !request.operation.serial);
            assert(fixture.vmWrites == 7 && fixture.writes == 5 && !fixture.alternateTable.stores);
            assert(scanout.cancelPin(fixture.alternatePin) == kIOReturnSuccess);
            assert(scanout.device.dcnManagedWrites.excludes(scanout.frame.host.base + 4 * kPage));
            return;
        }
        if (fault == FlipFault::SharedTable || fault == FlipFault::SharedRoot) {
            assert(fixture.begin(request) == kIOReturnNotReady && fixture.vmWrites == 7 && fixture.writes == 5);
            assert(fixture.homeTable.references == 2 && fixture.homeTable.stores == 1 && fixture.homeTable.dma.prepared &&
                   fixture.alternateTable.dma.prepared && !fixture.alternateTable.stores);
            assert(scanout.cancelPin(fixture.alternatePin) == kIOReturnNotReady && !fixture.homeTable.withdrawals &&
                   !fixture.alternateTable.withdrawals);
            return;
        }
        assert(fixture.begin(request) == kIOReturnSuccess && request.result == ScanoutFlipResult::Issued);
        const auto &holds = scanout.device.dcnManagedWrites;
        assert(holds.excludes(scanout.frame.host.base + 2 * kPage) && holds.excludes(fixture.nextHost.base + 2 * kPage));
        assert(fixture.pageReads == 6 && fixture.writes == 10 && fixture.vmWrites == 14 && DcnAllocationStub::live() == 2);
        poll.operation = request.operation;
        fixture.pending = false;
        fixture.active = fixture.earliest = fixture.alternate;
        fixture.step(poll, ScanoutFlipResult::Waiting);
        const bool failed = fault == FlipFault::DualContextDuringRetire;
        fixture.step(poll, failed ? ScanoutFlipResult::Uncertain : ScanoutFlipResult::Presented);
        assert(holds.excludes(scanout.frame.host.base + 2 * kPage) == failed && holds.excludes(fixture.nextHost.base + 2 * kPage));
        assert(fixture.retireChecks == 2 && fixture.command.completes == !failed && !fixture.nextCommand.completes);
        assert(DcnAllocationStub::live() == (failed ? 2u : 1u));
        assert(fixture.homeTable.references == (failed ? 2u : 0u) && fixture.alternateTable.references == 2);
        assert(scanout.cancelPin(fixture.alternatePin) == kIOReturnNotFound);
        return;
    }

    request = {fixture.mapped, fixture.home, {}, {}, ScanoutFlipResult::Refused};
    if (fault == FlipFault::WrongReturnAddress || fault == FlipFault::ReplacedFramebuffer) {
        CommitFixture::Framebuffer replacement;
        replacement.provider = scanout.device.pci;
        replacement.isPhxFramebuffer = true;
        if (fault == FlipFault::WrongReturnAddress) request.next.address += kPage;
        else fixture.route.framebuffer = &replacement;
        const auto checks = fixture.framebuffer.checks;
        assert(fixture.begin(request) == kIOReturnNotReady && !request.operation.serial);
        assert(fixture.writes == 5 && fixture.vmWrites == 7 && !fixture.command.completes && fixture.command.prepared);
        assert(fixture.framebuffer.samples == 1 && fixture.framebuffer.checks == checks && fixture.framebuffer.references == 2);
        assert(replacement.references == 1 && !replacement.samples && !replacement.checks);
        return;
    }
    if (fault == FlipFault::ReturnSameVmid) {
        request.next.vmid = request.previous.vmid;
        const auto reads = fixture.reads;
        assert(fixture.begin(request) == kIOReturnNotReady && !request.operation.serial);
        assert(reads == fixture.reads && fixture.writes == 5 && !fixture.command.completes);
        return;
    }
    if (fault == FlipFault::WrongPreviousPage || fault == FlipFault::ReplacedFrontContext) {
        if (fault == FlipFault::ReplacedFrontContext) fixture.contextRoot ^= kPage;
        else fixture.homeTable.words[1] ^= kPage;
        assert(fixture.begin(request) == kIOReturnNotReady && !request.operation.serial);
        assert(fixture.pageReads == (fault == FlipFault::WrongPreviousPage ? 4u : 2u));
        assert(fixture.writes == 5 && !fixture.command.completes);
        assert(fixture.lifetime.references == 3 && scanout.cancelPin(fixture.pin) == kIOReturnNotFound);
        return;
    }
    assert(fixture.begin(request) == kIOReturnSuccess && request.result == ScanoutFlipResult::Issued);
    assert(fixture.writes == 10 && fixture.issues == 2 && fixture.pageReads == 4);
    poll.operation = request.operation;
    fixture.pending = fixture.retire = false;
    fixture.active = fixture.earliest = fixture.home;
    fixture.step(poll, ScanoutFlipResult::Waiting);
    if (fault == FlipFault::CloseDuringRetire || fault == FlipFault::LateRetire ||
        fault == FlipFault::GeometryAtRetire || fault == FlipFault::GeometryBeforeRetire) {
        fixture.retire = true;
        fixture.closeDuringRetire = fault == FlipFault::CloseDuringRetire;
        fixture.lateRetire = fault == FlipFault::LateRetire;
        fixture.changeGeometryAtRetire = fault == FlipFault::GeometryAtRetire;
        if (fault == FlipFault::GeometryBeforeRetire) ++fixture.pitch;
        fixture.step(poll, ScanoutFlipResult::Uncertain);
        assert(fixture.command.prepared && !fixture.command.completes && fixture.lifetime.references == 3);
        assert(fixture.retireChecks == (fault == FlipFault::GeometryBeforeRetire ? 1u : 2u));
        return;
    }
    fixture.step(poll, ScanoutFlipResult::Waiting);
    assert(fixture.retireChecks == 2 && !fixture.clearWrites && !fixture.translationChecks && !fixture.command.completes &&
           scanout.frame.host.wires == 2);
    IOLockLock(scanout.client.lock);
    assert(fixture.poll(poll) == kIOReturnBusy && fixture.retireChecks == 2);
    IOLockUnlock(scanout.client.lock);
    fixture.retire = true;
    fixture.failUnmap = fault == FlipFault::Unmap;
    if (fault == FlipFault::FetchBusy || fault == FlipFault::FetchNeverDrained) {
        fixture.noOutstanding = false;
        fixture.step(poll, ScanoutFlipResult::Waiting);
        assert(fixture.retireChecks == 2 && !fixture.clearChecks && !fixture.clearWrites && !fixture.translationChecks &&
               fixture.contextRoot == fixture.ownedRoot && !fixture.homeTable.withdrawals && fixture.command.prepared &&
               scanout.device.dcnManagedWrites.excludes(scanout.frame.host.base + 2 * kPage));
        if (fault == FlipFault::FetchNeverDrained) {
            fixture.now += 100000000;
            fixture.step(poll, ScanoutFlipResult::Uncertain);
            fixture.noOutstanding = true;
            fixture.step(poll, ScanoutFlipResult::Uncertain);
            assert(!fixture.clearWrites && !fixture.homeTable.withdrawals && fixture.command.prepared &&
                   scanout.device.dcnManagedWrites.excludes(scanout.frame.host.base + 2 * kPage));
            return;
        }
        fixture.noOutstanding = true;
    }
    if (fault == FlipFault::HomeLostAtRetire || fault == FlipFault::PeerDuringRetire || fault == FlipFault::PeerAfterWithdraw) {
        const bool withdrew = fault == FlipFault::PeerAfterWithdraw;
        fixture.step(poll, ScanoutFlipResult::Uncertain);
        assert(fixture.retireChecks == 3 && fixture.command.prepared && !fixture.command.completes &&
               fixture.homeTable.dma.prepared == !withdrew && fixture.homeTable.withdrawals == withdrew &&
               scanout.frame.host.wires == 2);
        assert(fixture.framebuffer.samples == 1 && fixture.framebuffer.references == 2 && !fixture.framebuffer.releases);
        const auto checks = fixture.framebuffer.checks;
        fixture.step(poll, ScanoutFlipResult::Uncertain);
        assert(fixture.framebuffer.checks == checks && !fixture.command.completes);
        return;
    }
    if (fault >= FlipFault::RetireRootStillInstalled && fault <= FlipFault::RetireContextReappears) {
        fixture.step(poll, ScanoutFlipResult::Uncertain);
        const bool withdrew = fault == FlipFault::RetireContextReappears;
        assert(fixture.homeTable.withdrawals == withdrew && fixture.homeTable.dma.prepared == !withdrew);
        assert(fixture.command.prepared && !fixture.command.completes && fixture.lifetime.references == 3);
        fixture.step(poll, ScanoutFlipResult::Uncertain);
        assert(fixture.homeTable.withdrawals == withdrew && !fixture.command.completes);
        return;
    }
    if (fault == FlipFault::ClearDenied || fault == FlipFault::ClearWriteUncertain || fault == FlipFault::ReplacedDuringFetchDrain ||
        fault == FlipFault::TranslationLost || fault == FlipFault::FrontRevertedDuringTranslations) {
        const bool afterClear = fault == FlipFault::TranslationLost || fault == FlipFault::FrontRevertedDuringTranslations;
        fixture.step(poll, ScanoutFlipResult::Uncertain);
        assert(fixture.clearWrites == (afterClear ? 7u : fault == FlipFault::ClearWriteUncertain ? 1u : 0u) &&
               fixture.translationChecks == afterClear && !fixture.homeTable.withdrawals && fixture.homeTable.dma.prepared &&
               fixture.command.prepared && !fixture.command.completes && fixture.framebuffer.references == 2);
        const auto writes = fixture.clearWrites;
        fixture.step(poll, ScanoutFlipResult::Uncertain);
        assert(fixture.clearWrites == writes && fixture.translationChecks == afterClear);
        return;
    }
    if (fault == FlipFault::TranslationPending) {
        fixture.step(poll, ScanoutFlipResult::Waiting);
        assert(fixture.clearWrites == 7 && fixture.retireChecks == 3 && fixture.translationChecks == 1 &&
               !fixture.homeTable.withdrawals && fixture.homeTable.dma.prepared && fixture.command.prepared);
    }
    if (fault == FlipFault::WithdrawError || fault == FlipFault::CloseDuringWithdraw) {
        fixture.step(poll, ScanoutFlipResult::Uncertain);
        assert(fixture.homeTable.withdrawals == 1 && !fixture.homeTable.dma.prepared &&
               fixture.homeTable.references == (fault == FlipFault::WithdrawError ? 2u : 1u));
        assert(fixture.command.prepared && !fixture.command.completes && scanout.frame.host.wires == 2);
        if (fault == FlipFault::WithdrawError) fixture.step(poll, ScanoutFlipResult::Uncertain);
        assert(fixture.homeTable.withdrawals == 1);
        return;
    }
    fixture.step(poll, fixture.failUnmap ? ScanoutFlipResult::Uncertain : ScanoutFlipResult::Presented);
    assert(fixture.clearWrites == 7 && fixture.retireChecks == 3 &&
           fixture.translationChecks == (fault == FlipFault::TranslationPending ? 2u : 1u));
    assert(fixture.command.completes == 1 && fixture.command.clears == !fixture.failUnmap);
    assert(DcnAllocationStub::live() == (fixture.failUnmap ? 1u : 0u));
    assert(scanout.frame.host.wires == (fixture.failUnmap ? 2u : 1u));
    assert(fixture.lifetime.references == (fixture.failUnmap ? 3u : 1u));
    assert(fixture.framebuffer.samples == (fault == FlipFault::RetryTable ? 2u : 1u));
    assert(fixture.framebuffer.references == (fixture.failUnmap ? 2u : 1u) &&
           fixture.framebuffer.releases == (fault == FlipFault::RetryTable) + unsigned(!fixture.failUnmap));
    assert(fixture.homeTable.withdrawals == 1 && !fixture.homeTable.dma.prepared &&
           fixture.homeTable.references == (fixture.failUnmap ? 1u : 0u));
    assert(scanout.surface.references == (fixture.failUnmap ? 2u : 1u));
    if (fixture.failUnmap) {
        fixture.step(poll, ScanoutFlipResult::Uncertain);
        assert(fixture.command.completes == 1);
    } else {
        assert(fixture.poll(poll) == kIOReturnNotFound && scanout.cancelPin(fixture.pin) == kIOReturnNotFound);
    }
}
#endif

#if defined(TEST_SCANOUT_BAR5) && !defined(TEST_SCANOUT_FB_LEASE)
static void exerciseDcnBar5() {
    PhxBringup device;
    Bar5Resource resource;
    uint32_t registers[dcnPeers::kMmioBytes / sizeof(uint32_t)]{};
    IOMemoryMap mapping{&resource, reinterpret_cast<uintptr_t>(registers), sizeof(registers), resource.physical};
    device.mmio = &mapping;
    device.pci->bar5 = &resource;
    device.provider = device.pci;
    bool current = true;
    HubpFlipRoute route{};
    route.reader.context = &current;
    route.reader.current = [](void *context, const HubpFlipRequest &) { return *static_cast<bool *>(context); };
    const ScanoutFlipIntent intent{{0x80000000, 0}, {0x90000000, 7}, {}, {}, ScanoutFlipResult::Refused};
    assert(!device.bindDcnBar5(intent, route));
    CallbackGate<>::Lease life(device.exactCallbacks);
    CallbackGate<1>::Lease operation(device.dcnPinOperation);
    assert(life && operation);
    {
        CallbackGate<1>::Lease raw(device.exactRawWriters);
        assert(raw && device.exactRawWriters.close());
        assert(!device.bindDcnBar5(intent, route));
    }
    device.pci->identity ^= 1;
    assert(!device.bindDcnBar5(intent, route));
    device.pci->identity ^= 1;
    mapping.task = &current;
    assert(!device.bindDcnBar5(intent, route));
    mapping.task = kernel_task;
    --mapping.bytes;
    assert(!device.bindDcnBar5(intent, route));
    ++mapping.bytes;
    mapping.physical += kPage;
    assert(!device.bindDcnBar5(intent, route));
    mapping.physical -= kPage;
    assert(device.bindDcnBar5(intent, route) && route.reader.context == &current && route.reader.ioContext == &device);
    auto *io = route.reader.ioContext;
    const auto read = [&](uint32_t reg, uint32_t &value) { return route.reader.readDword(io, reg, value); };
    const auto write = [&](uint32_t reg, uint32_t value) { return route.writer.writeDword(io, reg, value); };
    uint32_t value = 0;
    registers[hubp0::kFrame] = 22;
    assert(read(hubp0::kFrame, value) && value == 22);
    assert(!read(UINT32_MAX, value) && !read(0, value) && value == 22);
    registers[hubp0::kFrame] = UINT32_MAX;
    assert(!read(hubp0::kFrame, value) && value == 22);
    assert(!write(hubp0::kFrame, 1) && !write(0, 1) && !write(dcnVm::base(0), 1) && !write(dcnVm::base(8), 1));
    assert(!registers[dcnVm::base(0)] && !registers[dcnVm::base(8)]);
    assert(write(dcnVm::base(7) + 2, 0x3001) && read(dcnVm::base(7) + 2, value) && value == 0x3001);
    assert(write(hubp0::kProgrammedHigh, 0x90) && registers[hubp0::kProgrammedHigh] == 0x90);
    registers[hubp0::kFrame] = 22;
    registers[hubp0::kProgrammedHigh] = 0;
    registers[hubp0::kProgrammedLow] = registers[hubp0::kInUseLow] = registers[hubp0::kEarliestLow] = intent.previous.address;
    const HubpFlipRequest request{&current, 1, 2, intent.previous, intent.next, {}, {&device, 3}};
    HubpFlipReadback readback;
    assert(readback.begin(request, route.reader));
    ++registers[hubp0::kFrame];
    registers[hubp0::kVmid] = intent.next.vmid;
    registers[hubp0::kInUseHigh] = registers[hubp0::kEarliestHigh] = intent.next.vmid << 28;
    registers[hubp0::kProgrammedLow] = registers[hubp0::kInUseLow] = registers[hubp0::kEarliestLow] = intent.next.address;
    assert(readback.poll() == HubpFlipProgress::Latched);
    ++registers[hubp0::kFrame];
    assert(readback.poll() == HubpFlipProgress::OldAddressAbsent);
    current = false;
    assert(readback.poll() == HubpFlipProgress::Uncertain);
    assert(write(hubp0::kProgrammedHigh, 0x90));
    uint64_t ns = 0;
    assert(route.reader.readClockNs(io, ns) && ns == 1);
    route.writer.delayUs(io, 2);
    route.writer.delayUs(io, 1);
    assert(bar5Delays == 1);
    auto replacement = mapping;
    device.mmio = &replacement;
    assert(!read(hubp0::kControl, value) && !write(hubp0::kProgrammedHigh, 0));
    device.mmio = &mapping;
    device.pci->command = 0;
    assert(!write(hubp0::kProgrammedHigh, 0) && registers[hubp0::kProgrammedHigh] == 0x90);
    device.pci->command = 2;
    __atomic_store_n(&device.dcnBar5Revoked, true, __ATOMIC_RELEASE);
    assert(!device.bindDcnBar5(intent, route) && !route.reader.readClockNs(io, ns) && !read(hubp0::kControl, value));
    route.writer.delayUs(io, 1);
    assert(bar5Delays == 1);
}
#endif

#ifdef TEST_SCANOUT_FB_LEASE
struct LeaseFramebuffer : IOService {
    IOLock guard;
    IOLock *fDcnFirmwareLock = &guard;
    IOPCIDevice *fPCI = nullptr;
    IOMemoryMap *fMmio = nullptr, *fSurfMap = nullptr;
    bool fDcnFirmwareReady = true, fDcnFirmwarePower = true, fDcnFirmwareClosed = false, fBeside = false;
    // FRAMEBUFFER_ROUTE_FIELDS

    IOReturn callPlatformFunction(const OSSymbol *fn, bool wait, void *p1, void *p2, void *p3, void *p4) override {
        // FRAMEBUFFER_ROUTE_QUERY
        return kIOReturnUnsupported;
    }
};

static void exerciseDcnFramebufferRoute() {
    PhxBringup device, other;
    Bar5Resource resource;
    uint32_t registers[dcnPeers::kMmioBytes / sizeof(uint32_t)]{};
    IOMemoryMap mapping{&resource, reinterpret_cast<uintptr_t>(registers), sizeof(registers), resource.physical};
    device.mmio = &mapping;
    device.pci->bar5 = &resource;
    device.provider = other.provider = device.pci;
    device.isPhxBringup = other.isPhxBringup = true;
    other.pci = device.pci;
    assert(other.exactRawWriters.close());

    LeaseFramebuffer framebuffer;
    framebuffer.fPCI = device.pci;
    framebuffer.provider = device.pci;
    framebuffer.fMmio = framebuffer.fSurfMap = &mapping;
    framebuffer.fDcnRoute.setLock(framebuffer.fDcnFirmwareLock);
    bool live = true;
    HubpFlipRoute route{};
    route.owner = &live;
    route.generation = 7;
    route.framebuffer = &framebuffer;
    route.reader.context = &live;
    route.reader.current = [](void *state, const HubpFlipRequest &) { return *static_cast<bool *>(state); };
    route.presentWindows = {{{0xa0000000, 7}, 2 * kPage}, {{0xb0000000, 15}, 2 * kPage}, DcnPresentDomain::Mapped};
    FirmwareScanoutSample home{{0x80000000, 0}, {16, 32, 15, kDcnArgb8888, kPage}, 0, 0x180000000, 12};
    registers[hubp0::kFrame] = home.frame;
    registers[hubp0::kProgrammedLow] = registers[hubp0::kInUseLow] = registers[hubp0::kEarliestLow] = home.scanout.address;
    for (unsigned index = 0; index < dcnPeers::kCount; ++index)
        registers[dcnPeers::kPower1 + index * dcnPeers::kPowerStride] = dcnPeers::kGated;
    unsigned frameReads = 0;
    assert(!checkUnclaimedDcnContexts(route.presentWindows, home.scanout, kPage, sizeof(registers),
        [&](uint32_t reg, uint32_t &value) {
            value = registers[reg];
            if (reg == hubp0::kFrame && ++frameReads > 4) ++value;
            return true;
        }));

    assert(!device.acquireDcnFbRoute(route, home) && !device.dcnFbRouteService && device.references == 1);
    assert(device.exactRawWriters.close());
    registers[dcnVm::base(15) + 6] = kPage;
    assert(!device.acquireDcnFbRoute(route, home) && device.references == 1);
    registers[dcnVm::base(15) + 6] = 0;
    registers[hubp0::kOtgControl + dcnPeers::kOtgStride] = hubp0::kOtgEnabled;
    assert(!device.acquireDcnFbRoute(route, home) && !device.dcnFbRouteService);
    registers[hubp0::kOtgControl + dcnPeers::kOtgStride] = 0;
    IOLockLock(&framebuffer.guard);
    assert(!device.acquireDcnFbRoute(route, home));
    IOLockUnlock(&framebuffer.guard);
    assert(device.acquireDcnFbRoute(route, home) && framebuffer.references == 2 && device.references == 2);
    const auto old = device.dcnFbRoute;
    assert(old.serial && old.gate && device.acquireDcnFbRoute(route, home) && device.dcnFbRoute.serial == old.serial);
    assert(!other.acquireDcnFbRoute(route, home) && other.references == 1);
    assert(device.releaseDcnFbRoute() && framebuffer.references == 1 && device.references == 1);
    assert(device.acquireDcnFbRoute(route, home) && device.dcnFbRoute.serial > old.serial);
    assert(framebuffer.releaseDcnRoute(device.pci, old) == kIOReturnNotFound);
    assert(!old.gate->access(old, [] { assert(false); return true; }));

    ScanoutFlipIntent intent{home.scanout, route.presentWindows.first.base, {}, {}, ScanoutFlipResult::Refused};
    CallbackGate<>::Lease life(device.exactCallbacks);
    CallbackGate<1>::Lease operation(device.dcnPinOperation);
    assert(life && operation && device.bindDcnBar5(intent, route));
    const auto read = [&](uint32_t &value) { return route.reader.readDword(route.reader.ioContext, hubp0::kProgrammedHigh, value); };
    const auto write = [&](uint32_t value) { return route.writer.writeDword(route.reader.ioContext, hubp0::kProgrammedHigh, value); };
    uint32_t value = 0;
    assert(write(0x90) && read(value) && value == 0x90);
    IOLockLock(&framebuffer.guard);
    assert(!write(0xa0) && !read(value) && registers[hubp0::kProgrammedHigh] == 0x90);
    framebuffer.fDcnRoute.closeLocked();
    IOLockUnlock(&framebuffer.guard);
    assert(!write(0xa0) && !read(value) && !device.acquireDcnFbRoute(route, home));
    assert(device.releaseDcnFbRoute() && framebuffer.references == 1 && device.references == 1);
    registers[hubp0::kProgrammedHigh] = 0;
    assert(!device.acquireDcnFbRoute(route, home));
}
#endif

#ifdef TEST_SCANOUT_TRANSACTION
#include "build34_dcn_transaction.h"

struct TransactionFramebuffer : IOService {
    const FirmwareScanoutSample firmware{{0x80000000, 0}, {16, 32, 15, kDcnArgb8888, kPage}, 0, 0x80000000, 1};
    unsigned samples = 0, checks = 0;
    bool conflict = false;
    IOReturn callPlatformFunction(const OSSymbol *name, bool wait, void *device, void *out, void *third, void *fourth) override {
        assert(!wait && device == provider && out && !fourth);
        auto &sample = *static_cast<FirmwareScanoutSample *>(out);
        if (name->isEqualTo(BUILD34_DCN_SAMPLE_FIRMWARE)) {
            assert(!third);
            ++samples;
            sample = firmware;
            return kIOReturnSuccess;
        }
        assert(name->isEqualTo(BUILD34_DCN_CHECK_FIRMWARE) && third && sample.scanout == firmware.scanout);
        const auto &windows = *static_cast<const FirmwareFlatWindows *>(third);
        assert(windows.previous.start == 0x90000000 && windows.previous.bytes == 2 * kPage &&
               windows.next.start == 0xa0000000 && windows.next.bytes == 2 * kPage);
        ++checks;
        return conflict ? kIOReturnNotReady : kIOReturnSuccess;
    }
};

struct TransactionFixture {
    IOPCIDevice device;
    IOPCIDevice *pci = &device;
    CallbackGate<> exactCallbacks;
    // TRANSACTION_FIELDS
    struct {
        ScanoutPinToken token{};
        HubpAddress address{};
        FirmwareScanoutSample home{};
        DcnPresentWindowPair windows{};
        bool waiting = false;
        ScanoutPinToken front() const { return token; }
        HubpAddress frontAddress() const { return address; }
        HubpAddress firmwareAddress() const { return home.scanout; }
        FirmwareScanoutSample firmwareSample() const { return home; }
        bool matchesPresentWindows(const DcnPresentWindowPair &pair) const { return !token.serial || pair == windows; }
        bool pending() const { return waiting; }
    } dcnFlip;
    const HubpFlipRoute *(*dcnQualifiedFlipRoute)(IOPCIDevice *) = [](IOPCIDevice *device) -> const HubpFlipRoute * { return device->route; };
    DcnDirectDomain (*dcnQualifyDirect)(IOPCIDevice &) = [](IOPCIDevice &) { return DcnDirectDomain{}; };
    ScanoutDmaMapper (*dcnQualifyMapper)(IOPCIDevice &, IOMapper &) = nullptr;
    TransactionFramebuffer framebuffer;
    OSObject lifetime;
    HubpFlipRoute route{};
    ScanoutFlipIntent issued{};
    const PresentCopyBacking *mapped = nullptr;
    unsigned maps = 0, begins = 0, polls = 0, cancels = 0, waits = 0;
    bool mapRefused = false, routeDrift = false, beginRefused = false, uncertainIssue = false, mismatch = false, timeout = false;

    TransactionFixture() {
        framebuffer.provider = pci;
        framebuffer.isPhxFramebuffer = true;
        dcnFlip.home = framebuffer.firmware;
        route.owner = this;
        route.generation = 11;
        route.lifetime = &lifetime;
        route.framebuffer = &framebuffer;
        route.presentWindows = {{{0x90000000, 7}, 2 * kPage}, {{0xa0000000, 6}, 2 * kPage}, DcnPresentDomain::Direct};
        device.route = &route;
    }

    IOReturn mapDcnPin(ScanoutDmaRequest &map, bool direct) {
        assert(direct && map.present == mapped && validScanoutDmaStorage(map, kPage) && lifetime.references == 2);
        const auto current = dcnFlip.front().serial ? dcnFlip.frontAddress() : dcnFlip.firmwareAddress();
        assert(map.windowStart == route.presentWindows.select(current, kPage).address);
        ++maps;
        if (mapRefused) return kIOReturnNotReady;
        if (routeDrift) ++route.generation;
        map.token = {this, 2 * maps};
        return kIOReturnSuccess;
    }

    IOReturn beginDcnFlip(ScanoutFlipIntent &intent) {
        assert(!dcnFlip.pending() && intent.framebuffer == &framebuffer);
        assert(intent.previous == (dcnFlip.front().serial ? dcnFlip.frontAddress() : dcnFlip.firmwareAddress()));
        assert(intent.nextPin.serial ? intent.nextPin.provider == this : intent.next == dcnFlip.firmwareAddress());
        ++begins;
        if (intent.nextPin.serial) {
            assert(intent.plannedRoute && lifetime.references == 2);
            if (!sameDcnPresentRoute(*intent.plannedRoute, route)) return kIOReturnNotReady;
        } else {
            assert(!intent.plannedRoute);
            if (!dcnFlip.matchesPresentWindows(route.presentWindows)) return kIOReturnNotReady;
        }
        if (beginRefused) return kIOReturnNotReady;
        intent.operation = {this, 2 * begins + 1};
        intent.result = uncertainIssue ? ScanoutFlipResult::Uncertain : ScanoutFlipResult::Issued;
        issued = intent;
        issued.plannedRoute = nullptr;
        dcnFlip.waiting = true;
        return kIOReturnSuccess;
    }

    IOReturn pollDcnFlip(ScanoutFlipPoll &poll) {
        assert(dcnFlip.pending() && poll.operation == issued.operation);
        ++polls;
        if (timeout) return kIOReturnBusy;
        if (mismatch) {
            ++poll.operation.serial;
            poll.result = ScanoutFlipResult::Presented;
            return kIOReturnSuccess;
        }
        if (waits) {
            --waits;
            poll.result = ScanoutFlipResult::Waiting;
            return kIOReturnSuccess;
        }
        poll.result = ScanoutFlipResult::Presented;
        dcnFlip.waiting = false;
        dcnFlip.token = issued.nextPin;
        dcnFlip.address = issued.next;
        dcnFlip.windows = issued.nextPin.serial ? route.presentWindows : DcnPresentWindowPair{};
        return kIOReturnSuccess;
    }

    IOReturn cancelDcnPin(ScanoutPinToken pin) {
        assert(!dcnFlip.pending() && !(pin == dcnFlip.front()));
        ++cancels;
        return kIOReturnSuccess;
    }
};

// TRANSACTION_METHOD

static void exerciseDcnTransaction() {
    TransactionFixture fixture;
    Descriptor descriptor;
    OSObject pipe, otherPipe;
    const int first = 0, next = 0;
    auto backing = observePreparedCopyBacking(&first, &descriptor, &descriptor, kSurfaceBgra, 16, 32, 64, 16, 32);
    fixture.mapped = &backing;
    DcnPresentTransaction request{&pipe, &fixture.framebuffer, &next, &backing, DcnPresentResult::Copy};
    assert(fixture.submitDcnPresent(request) == kIOReturnBadArgument && request.result == DcnPresentResult::Blocked && !fixture.maps);
    request.transaction = &first;
    const auto pair = fixture.route.presentWindows;
    assert(!pair.select({0x90000000, 6}, kPage).valid() && !pair.select(fixture.dcnFlip.home.scanout, 3 * kPage).valid());
    for (unsigned fault = 0; fault < 6; ++fault) {
        fixture.route.presentWindows = pair;
        auto &windows = fixture.route.presentWindows;
        if (fault == 0) windows.second.base.vmid = windows.first.base.vmid;
        if (fault == 1) windows.second.base.vmid = 0;
        if (fault == 2) windows.second.base.address = windows.first.base.address + kPage;
        if (fault == 3) windows.second.base.address = kAddressLimit - kPage;
        if (fault == 4) windows.domain = DcnPresentDomain::None;
        if (fault == 5) windows.domain = DcnPresentDomain::Mapped;
        assert(fixture.submitDcnPresent(request) == kIOReturnSuccess && request.result == DcnPresentResult::Copy && !fixture.maps);
    }
    fixture.route.presentWindows = pair;
    fixture.framebuffer.conflict = true;
    assert(fixture.submitDcnPresent(request) == kIOReturnSuccess && request.result == DcnPresentResult::Copy && !fixture.maps);
    fixture.framebuffer.conflict = false;
    fixture.mapRefused = true;
    assert(fixture.submitDcnPresent(request) == kIOReturnSuccess && request.result == DcnPresentResult::Copy && !fixture.begins);
    fixture.mapRefused = false;
    fixture.routeDrift = true;
    assert(fixture.submitDcnPresent(request) == kIOReturnSuccess && request.result == DcnPresentResult::Copy && fixture.cancels == 1);
    fixture.routeDrift = false;
    fixture.beginRefused = true;
    assert(fixture.submitDcnPresent(request) == kIOReturnSuccess && request.result == DcnPresentResult::Copy && fixture.cancels == 2);
    fixture.beginRefused = false;
    fixture.waits = 2;
    assert(fixture.submitDcnPresent(request) == kIOReturnSuccess && request.result == DcnPresentResult::Direct && fixture.polls == 3);
    assert(pipe.references == 2 && fixture.framebuffer.references == 2);
    request.pipe = &otherPipe;
    assert(fixture.submitDcnPresent(request) == kIOReturnNotReady && request.result == DcnPresentResult::Blocked && fixture.polls == 3);
    request.pipe = &pipe;
    request.transaction = &next;
    backing.transaction = &next;
    assert(fixture.submitDcnPresent(request) == kIOReturnSuccess && request.result == DcnPresentResult::Direct && fixture.polls == 4);
    assert(fixture.dcnFlip.frontAddress() == pair.second.base && fixture.framebuffer.samples == 5);
    request.transaction = &first;
    backing.transaction = &first;
    fixture.route.presentWindows.first.bytes -= kPage;
    const auto maps = fixture.maps;
    assert(fixture.submitDcnPresent(request) == kIOReturnNotReady && request.result == DcnPresentResult::Blocked && fixture.maps == maps);
    fixture.route.presentWindows = pair;
    request.backing = nullptr;
    fixture.beginRefused = true;
    assert(fixture.submitDcnPresent(request) == kIOReturnNotReady && request.result == DcnPresentResult::Blocked && fixture.polls == 4);
    fixture.beginRefused = false;
    assert(fixture.submitDcnPresent(request) == kIOReturnSuccess && request.result == DcnPresentResult::Copy && fixture.polls == 5);
    assert(!fixture.dcnFlip.front().serial && pipe.references == 1 && fixture.framebuffer.references == 1 && fixture.cancels == 2);

    for (unsigned fault = 0; fault < 3; ++fault) {
        TransactionFixture faulted;
        faulted.mapped = &backing;
        faulted.uncertainIssue = fault == 0;
        faulted.mismatch = fault == 1;
        faulted.timeout = fault == 2;
        request = {&pipe, &faulted.framebuffer, &first, &backing, DcnPresentResult::Copy};
        assert(faulted.submitDcnPresent(request) == kIOReturnNotReady && request.result == DcnPresentResult::Blocked);
        const auto polls = faulted.polls;
        assert(polls == (fault == 0 ? 0u : fault == 1 ? 1u : 50u));
        request.backing = nullptr;
        assert(faulted.submitDcnPresent(request) == kIOReturnNotReady && request.result == DcnPresentResult::Blocked);
        assert(faulted.begins == 1 && faulted.polls == polls && !faulted.cancels && faulted.framebuffer.references == 2);
        assert(faulted.dcnPresentUncertain && faulted.dcnFlip.pending());
        pipe.release();
    }

    DcnPresentCompletion completion;
    bool done = true;
    assert(!completion.check(&first, done) && !done);
    completion.block();
    assert(completion.check(&first, done) && !done);
    completion.presented(&first);
    assert(completion.check(&first, done) && done);
    assert(completion.check(&next, done) && !done);
    completion.legacy();
    assert(!completion.check(&first, done) && !done);
}
#endif

int main() {
    completionAndPages();
    newerAndRacingCompletions();
    refusalAndInvalidation();
    remapCloseAndPressure();
#ifdef TEST_PRESENT_HANDOFF
    drainAcrossPresent();
    exercisePresentHandoff();
    closeDuringPresent(true);
    closeDuringPresent(false);
#endif
#ifdef TEST_SCANOUT_PINS
    scanoutPinLifetime();
    scanoutPinFailedPrepareAndRollback();
#endif
#ifdef TEST_SCANOUT_DMA
    hostFlatWords();
    scanoutDmaQualification();
    scanoutDirectQualification();
    scanoutDmaPresentPreparation(false);
    scanoutDmaPresentPreparation(true);
    scanoutDma(DmaFault::None);
    scanoutDma(DmaFault::AlternateDescriptor);
    scanoutDma(DmaFault::WrongOffset);
    scanoutDma(DmaFault::WrongPage);
    scanoutDma(DmaFault::NoMappedPage);
    scanoutDma(DmaFault::ChangedEpoch);
    scanoutDma(DmaFault::FailedPrepare);
    scanoutDma(DmaFault::NoPlanMemory);
    scanoutDma(DmaFault::None, DmaCleanupFault::Complete);
    scanoutDma(DmaFault::None, DmaCleanupFault::Clear);
    scanoutDma(DmaFault::None, DmaCleanupFault::ConfirmUnmap);
    scanoutDma(DmaFault::None, DmaCleanupFault::PresentComplete);
    scanoutDma(DmaFault::WrongPage, DmaCleanupFault::ConfirmUnmap);
#endif
#ifdef TEST_SCANOUT_FLIP
    for (const bool direct : {false, true}) scanoutSubmitReservation(direct);
    scanoutWriteIsolation(false, false);
    scanoutWriteIsolation(true, false);
    scanoutWriteIsolation(false, true);
    managedWriteHistoryLimits();
    scanoutHistoricalAliases(false);
    scanoutHistoricalAliases(true);
    scanoutReadOnlyRejection(true, false, false);
    scanoutReadOnlyRejection(true, false, true);
    scanoutReadOnlyRejection(false, true, false);
    scanoutReadOnlyDoubleBuffer(false);
    scanoutReadOnlyDoubleBuffer(true);
    for (const bool direct : {false, true})
        for (const auto fault : {WriterFault::NewerCompletedWork, WriterFault::ChangedEpoch, WriterFault::ChangedQueueGeneration,
             WriterFault::ReplacedWriterMap, WriterFault::ClientBusy, WriterFault::GpuBusy, WriterFault::DuringPageWalk,
             WriterFault::AfterVmInstall, WriterFault::UnderOtgLock}) revalidateScanoutWriter(fault, direct);
    for (const auto fault : {DirectFlipFault::None, DirectFlipFault::DeniedTable, DirectFlipFault::ShortTable,
         DirectFlipFault::DomainLost, DirectFlipFault::ReplacedPci, DirectFlipFault::WriteableLeaf,
         DirectFlipFault::WindowConflict, DirectFlipFault::DomainLostAfterIssue,
         DirectFlipFault::WindowConflictAtRetirement}) scanoutDirectFlip(fault);
    for (const auto fault : {PixelFault::MapperRemap, PixelFault::MapperUnavailable, PixelFault::RenderPage,
         PixelFault::PresentPage, PixelFault::RenderGeneration, PixelFault::PresentGeneration, PixelFault::LateGeneration,
         PixelFault::WrongCommandSlice, PixelFault::SubstitutedDescriptor, PixelFault::LateEvidence, PixelFault::FrontRemap,
         PixelFault::None}) revalidateScanoutPixels(fault);
    rejectChangedPresentWindows();
    presentWindowRetirement(false);
    presentWindowRetirement(true);
    scanoutFlip(FlipFault::None);
    scanoutFlip(FlipFault::Decline);
    scanoutFlip(FlipFault::ForeignLock);
    scanoutFlip(FlipFault::HeldLock);
    scanoutFlip(FlipFault::Dcc);
    scanoutFlip(FlipFault::LockTimeout);
    scanoutFlip(FlipFault::HighWrite);
    scanoutFlip(FlipFault::RouteLost);
    scanoutFlip(FlipFault::ClockRewind);
    scanoutFlip(FlipFault::Issue);
    scanoutFlip(FlipFault::UnlockTimeout);
    scanoutFlip(FlipFault::Close);
    scanoutFlip(FlipFault::CloseDuringQualify);
    scanoutFlip(FlipFault::CloseDuringRetire);
    scanoutFlip(FlipFault::LateRetire);
    scanoutFlip(FlipFault::Unmap);
    scanoutFlip(FlipFault::WrongFormat);
    scanoutFlip(FlipFault::SwappedChannels);
    scanoutFlip(FlipFault::AlphaPlane);
    scanoutFlip(FlipFault::Protected);
    scanoutFlip(FlipFault::Tiled);
    scanoutFlip(FlipFault::WrongPitch);
    scanoutFlip(FlipFault::Cropped);
    scanoutFlip(FlipFault::WrongViewport);
    scanoutFlip(FlipFault::SplitInput);
    scanoutFlip(FlipFault::SplitOutput);
    scanoutFlip(FlipFault::WrongOdmSource);
    scanoutFlip(FlipFault::DisabledOtg);
    scanoutFlip(FlipFault::NoTranslationReader);
    scanoutFlip(FlipFault::TranslationError);
    scanoutFlip(FlipFault::WrongLastPage);
    scanoutFlip(FlipFault::LateTranslation);
    scanoutFlip(FlipFault::RevokedTranslation);
    scanoutFlip(FlipFault::WrongPreviousPage);
    scanoutFlip(FlipFault::NoContextRoot);
    scanoutFlip(FlipFault::UnreadyContext);
    scanoutFlip(FlipFault::WrongContextRoot);
    scanoutFlip(FlipFault::WrongContextDepth);
    scanoutFlip(FlipFault::WrongContextBlock);
    scanoutFlip(FlipFault::WrongContextStart);
    scanoutFlip(FlipFault::WrongContextEnd);
    scanoutFlip(FlipFault::ContextAfterPageWalk);
    scanoutFlip(FlipFault::ContextAtLock);
    scanoutFlip(FlipFault::ContextWhilePending);
    scanoutFlip(FlipFault::ContextDuringRetire);
    scanoutFlip(FlipFault::ReplacedFrontContext);
    scanoutFlip(FlipFault::DualPins);
    scanoutFlip(FlipFault::PhysicalAlias);
    scanoutFlip(FlipFault::DualContextDuringRetire);
    scanoutFlip(FlipFault::DifferentPinnedPitch);
    scanoutFlip(FlipFault::GeometryAtLock);
    scanoutFlip(FlipFault::GeometryAtRetire);
    scanoutFlip(FlipFault::GeometryBeforeRetire);
    scanoutFlip(FlipFault::Install);
    scanoutFlip(FlipFault::InstallDenied);
    scanoutFlip(FlipFault::InstallMissingProof);
    scanoutFlip(FlipFault::InstallSameVmid);
    scanoutFlip(FlipFault::InstallOccupied);
    scanoutFlip(FlipFault::InstallWrongLeaf);
    scanoutFlip(FlipFault::InstallRevoked);
    scanoutFlip(FlipFault::InstallWriteUncertain);
    scanoutFlip(FlipFault::InstallAckTimeout);
    scanoutFlip(FlipFault::InstallWrongAck);
    scanoutFlip(FlipFault::NoTableMemory);
    scanoutFlip(FlipFault::ShortTable);
    scanoutFlip(FlipFault::EncodeError);
    scanoutFlip(FlipFault::PublishError);
    scanoutFlip(FlipFault::PublishBadRoot);
    scanoutFlip(FlipFault::PublishCorruptPadding);
    scanoutFlip(FlipFault::PublicationLost);
    scanoutFlip(FlipFault::WithdrawError);
    scanoutFlip(FlipFault::CloseDuringWithdraw);
    scanoutFlip(FlipFault::CancelWithdrawError);
    scanoutFlip(FlipFault::SharedTable);
    scanoutFlip(FlipFault::SharedRoot);
    scanoutFlip(FlipFault::RetryTable);
    scanoutFlip(FlipFault::TableWrongPhysical);
    scanoutFlip(FlipFault::TablePrepareUncertain);
    scanoutFlip(FlipFault::TableBadSegments);
    scanoutFlip(FlipFault::TableSubstituted);
    scanoutFlip(FlipFault::RetireRootStillInstalled);
    scanoutFlip(FlipFault::RetireRangeStillInstalled);
    scanoutFlip(FlipFault::RetireContextReappears);
    scanoutFlip(FlipFault::ReturnSameVmid);
    scanoutFlip(FlipFault::MissingFramebuffer);
    scanoutFlip(FlipFault::WrongFramebufferPci);
    scanoutFlip(FlipFault::WrongFramebufferType);
    scanoutFlip(FlipFault::InactiveFramebuffer);
    scanoutFlip(FlipFault::NoHomeSample);
    scanoutFlip(FlipFault::WrongHomeAddress);
    scanoutFlip(FlipFault::WrongHomeGeometry);
    scanoutFlip(FlipFault::WrongHomeBacking);
    scanoutFlip(FlipFault::HomeLostAfterInstall);
    scanoutFlip(FlipFault::HomeLostAtRetire);
    scanoutFlip(FlipFault::WrongReturnAddress);
    scanoutFlip(FlipFault::ReplacedFramebuffer);
    scanoutFlip(FlipFault::PeerActive);
    scanoutFlip(FlipFault::PeerShortWindow);
    scanoutFlip(FlipFault::PeerDuringInstall);
    scanoutFlip(FlipFault::PeerAfterHigh);
    scanoutFlip(FlipFault::PeerDuringRetire);
    scanoutFlip(FlipFault::PeerAfterWithdraw);
    scanoutFlip(FlipFault::NoRetirementProof);
    scanoutFlip(FlipFault::ClearDenied);
    scanoutFlip(FlipFault::ClearWriteUncertain);
    scanoutFlip(FlipFault::ReplacedDuringFetchDrain);
    scanoutFlip(FlipFault::TranslationPending);
    scanoutFlip(FlipFault::FetchBusy);
    scanoutFlip(FlipFault::FetchNeverDrained);
    scanoutFlip(FlipFault::TranslationLost);
    scanoutFlip(FlipFault::FrontRevertedDuringTranslations);
#endif
#if defined(TEST_SCANOUT_FB_LEASE)
    exerciseDcnFramebufferRoute();
#elif defined(TEST_SCANOUT_BAR5)
    exerciseDcnBar5();
#endif
#ifdef TEST_SCANOUT_TRANSACTION
    transactionSleeping = true;
    exerciseDcnTransaction();
#endif
    std::puts("[PASS] exact writer backing (CPU only)");
}
