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
static uint64_t mach_absolute_time() { return 1; }
static void absolutetime_to_nanoseconds(uint64_t ticks, uint64_t *ns) { *ns = ticks; }
static void IOSleep(unsigned) { assert(false); }
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
    std::function<void()> afterPrepare;
    IOReturn prepare() override {
        ++prepares;
        if (prepareResult != kIOReturnSuccess) return prepareResult;
        ++wires;
        if (afterPrepare) afterPrepare();
        return kIOReturnSuccess;
    }
    IOReturn complete() override {
        assert(wires);
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
    Phx34ScopedReference(OSObject *value, bool take) : object(value) { assert(!take); }
    ~Phx34ScopedReference() { if (object) object->release(); }
};
#endif

#ifdef TEST_SCANOUT_DMA
#include "build34_dcn_scanout_dma.h"
#ifdef TEST_SCANOUT_FLIP
#include "build34_dcn_flip_commit.h"
#endif
struct IOPCIDevice {
    IOMapper *mapper = nullptr;
#ifdef TEST_SCANOUT_FLIP
    HubpFlipRoute *route = nullptr;
#endif
};
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
    static constexpr uint32_t kMaxCtx = 2;
    struct VmCtx {
        uint64_t generation = 5, newest = 0, queueSequence[2]{}, queueGeneration[2]{};
        const void *client = nullptr;
        bool closing = false, busy = false;
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
    bool exactGlobalRetiredLocked(uint64_t &, ExactOverlapSnapshot *);
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

    bool exactAdmissionClosed() const { return exactCallbacks.closed(); }
    bool gpuReady() const { return true; }
    bool debugEnabled() const { return false; }
    VmCtx *vmCtx(uint32_t handle) { return handle == 1 ? &vm[0] : nullptr; }
    VmCtx *vmOwned(uint32_t, uint64_t, const void *, bool = false);
    bool vmWorkCurrent(const VmCtx &) const;
    // WRITER_SERVICE

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
        IOLockLock(gpuLock);
        assert(vmOwned(handle, generation, client));
        const uint32_t queue = gfx ? 1 : 0;
        vm[0].newest = vm[0].queueSequence[queue] = *seq = recordQueued(queue);
        vm[0].queueGeneration[queue] = exactQueueGeneration[queue];
        assert(registry->publish(ticket, {*seq, exactQueueGeneration[queue], queue}) == Status::Ok);
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
enum class DmaCleanupFault { None, Complete, ConfirmUnmap, Clear };

static void scanoutDma(DmaFault fault, DmaCleanupFault cleanup = DmaCleanupFault::None) {
    ScanoutFixture fixture;
    DmaRun scratch[2]{};
    uint64_t pages[2]{UINT64_MAX, UINT64_MAX};
    ScanoutDmaRequest request{&fixture.frame.copy, 0x100000, scratch, 2, pages, 2, {}, {}};
    const OSSymbol map{BUILD34_DCN_PIN_MAP};
    auto dispatch = [&] {
        return fixture.device.callPlatformFunction(&map, false, &request, nullptr, nullptr, nullptr);
    };
    assert(dispatch() == kIOReturnNotReady);
    IOMapper mapper;
    IODMACommand command;
    IODMACommand::next = &command;
    fixture.device.pci->mapper = &mapper;
    fixture.device.dcnCopyQualifiedMapper = [](IOPCIDevice *device) -> ScanoutDmaMapper {
        device->mapper->retain();
        return {device->mapper, nullptr, nullptr};
    };
    fixture.offer();
    assert(dispatch() == kIOReturnNotReady && !command.created && mapper.references == 1);
    fixture.device.dcnCopyQualifiedMapper = [](IOPCIDevice *device) -> ScanoutDmaMapper {
        device->mapper->retain();
        return {device->mapper,
            [](IOMapper &mapper, const IODMACommand &command, uint64_t address, uint64_t &physical) {
                return mapper.resolve(command, address, physical);
            },
            [](IOMapper &mapper, const IODMACommand &command) { return mapper.confirmUnmap(command); }};
    };
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
    mapper.resolve = [&](const IODMACommand &mapped, uint64_t address, uint64_t &physical) {
        assert(&mapped == &command && command.prepared && command.memory == &host);
        assert(address == 0x400000 || address == 0x600000);
        const bool first = address == 0x400000;
        physical = host.base + (first ? 2 : fault == DmaFault::WrongPage ? 5 : 4) * kPage;
        return first || fault != DmaFault::NoMappedPage;
    };
    command.onComplete = [&] { assert(host.wires == 2 && fixture.client.guard.held && !fixture.device.guard.held); };
    unsigned confirmations = 0;
    mapper.confirmUnmap = [&](const IODMACommand &completed) {
        ++confirmations;
        assert(&completed == &command && command.completes == 1 && !command.prepared && command.memory == &host);
        assert(!command.clears && host.wires == 2 && fixture.client.guard.held && !fixture.device.guard.held);
        return cleanup != DmaCleanupFault::ConfirmUnmap;
    };
    auto *savedPages = request.pages;
    request.pages = reinterpret_cast<uint64_t *>(scratch);
    assert(dispatch() == kIOReturnBadArgument && !command.created);
    request.pages = savedPages;
    const bool failedPlan = fault != DmaFault::None;
    DcnAllocationStub::fail = fault == DmaFault::NoPlanMemory;
    assert(dispatch() == (failedPlan ? kIOReturnNotReady : kIOReturnSuccess) && command.created == 1);
    if (!failedPlan) {
        assert(request.layout.entryCount == 2 && request.token.provider == &fixture.device && request.token.serial);
        assert(pages[0] == 0x400000 && pages[1] == 0x600000);
        assert(DcnAllocationStub::live() == 1);
        assert(mapper.references == 2 && host.references == 3 && host.wires == 2);
        assert(fixture.cancelPin(request.token) == (cleanup == DmaCleanupFault::None ? kIOReturnSuccess : kIOReturnNotReady));
        assert(fixture.cancelPin(request.token) == kIOReturnNotFound);
    } else {
        assert(!request.layout.entryCount && !request.token.serial && pages[0] == UINT64_MAX && pages[1] == UINT64_MAX);
    }
    const bool completed = !command.failPrepare && !command.substitute;
    const bool confirmed = completed && !command.failComplete;
    const bool cleared = confirmed && cleanup != DmaCleanupFault::ConfirmUnmap;
    const bool reserved = !cleared || command.failClear;
    assert(command.completes == completed && confirmations == confirmed);
    assert(command.clears == cleared && command.releases == !reserved);
    assert(mapper.references == (reserved ? 2u : 1u) && host.wires == (reserved ? 2u : 1u));
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
                       RetireContextReappears, ReturnSameVmid };

struct CommitFixture {
    struct Table : IOBufferMemoryDescriptor {
        IODMACommand dma;
        uint64_t root = 0;
        unsigned withdrawals = 0;
    };
    ScanoutFixture scanout;
    IOMapper mapper;
    IODMACommand command, nextCommand;
    OSObject lifetime;
    Table homeTable, alternateTable;
    const HubpAddress home{0x800000000, 0}, mapped{0xa00100100000, 7};
    const HubpAddress alternate{mapped.address + 2 * kPage, 8};
    HubpAddress programmed = home, active = home, earliest = home, target = home;
    uint32_t frame = 42;
    uint64_t now = 800;
    unsigned issues = 0, reads = 0, writes = 0, delays = 0, retireChecks = 0, pageReads = 0;
    unsigned vmWrites = 0, vmAckReads = 0;
    uint32_t lockSelect = 0, surfaceControl = 0;
    uint32_t surfaceFormat = 8, returnControl = 0x00e00000, swizzle = 0, start = 0;
    uint32_t dimensions = (17u << 16) | 64u, pitch = 63, odm = 0xfff00000, otg = 0x00010001;
    const uint64_t ownedRoot = 0x123400005001;
    uint64_t contextRoot = 0, firstPage = 0, lastPage = 0;
    const uint64_t alternateRoot = 0x123400006001;
    uint64_t alternateContextRoot = 0, alternateFirst = 0, alternateLast = 0;
    uint32_t contextControl = 0, alternateControl = 0;
    bool lockRequested = false, lockHeld = false, lockTimeout = false, unlockTimeout = false;
    bool qualify = true, live = true, pending = false, failHigh = false, failIssue = false, retire = false, failUnmap = false;
    bool loseRouteAfterHigh = false, rewindAfterHigh = false;
    bool closeDuringQualify = false, closeDuringRetire = false, lateRetire = false;
    bool changeGeometryAtLock = false, changeGeometryAtRetire = false;
    bool publicationCurrent = true;
    FlipFault translationFault = FlipFault::None;
    uint64_t outputPages[2]{};
    HubpFlipRoute route{this, 5, &lifetime, {this, 0x80000, routeCurrent, read, clock}, {write, delay},
                       qualified, {encodeLeaf, decodeLeaf, encodeRoot, tableCurrent}, retired, canInstallFlatVm};
    ScanoutPinToken pin{}, alternatePin{};

    CommitFixture() {
        alternateTable.physical += 2 * kPage;
        configureTable(homeTable, ownedRoot, 0x500091, 0x601091);
        configureTable(alternateTable, alternateRoot, 0x800091, 0x901091);
        IODMACommand::next = &command;
        scanout.device.pci->mapper = &mapper;
        scanout.device.pci->route = &route;
        scanout.device.dcnCopyQualifiedMapper = [](IOPCIDevice *pci) -> ScanoutDmaMapper {
            pci->mapper->retain();
            return {pci->mapper,
                [](IOMapper &mapper, const IODMACommand &command, uint64_t address, uint64_t &physical) {
                    return mapper.resolve(command, address, physical);
                },
                [](IOMapper &mapper, const IODMACommand &command) { return mapper.confirmUnmap(command); }};
        };
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
            assert(&mapped == IODMACommand::next);
            const bool alternate = &mapped == &nextCommand;
            assert(alternate || &mapped == &command);
            const bool first = address == (alternate ? 0x800000 : 0x500000);
            assert(first || address == (alternate ? 0x901000 : 0x601000));
            physical = scanout.frame.host.base + (first ? 2 : 4) * kPage;
            return true;
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
            if (!issues) {
                assert(&completed == &command && scanout.client.guard.held && !scanout.device.guard.held);
                return true;
            }
            assert(&completed == &command && retire && retireChecks >= (alternatePin.serial ? 2u : 3u) &&
                   scanout.client.guard.held && !scanout.device.guard.held && lifetime.references == (alternatePin.serial ? 4u : 3u) &&
                   homeTable.withdrawals == 1 && !homeTable.dma.prepared && homeTable.references == 1 &&
                   scanout.frame.host.wires == (alternatePin.serial ? 3u : 2u));
            return !failUnmap;
        };
        scanout.offer();
        DmaRun scratch[2]{};
        ScanoutDmaRequest request{&scanout.frame.copy, mapped.address, scratch, 2, outputPages, 2, {}, {}};
        const OSSymbol symbol{BUILD34_DCN_PIN_MAP};
        const auto surface = scanout.frame.copy.scanout;
        scanout.frame.copy.scanout.pitchPixelsMinusOne = 1;
        assert(dispatch(symbol, &request) == kIOReturnBadArgument && !command.created);
        scanout.frame.copy.scanout.pitchPixelsMinusOne = 127;
        assert(dispatch(symbol, &request) == kIOReturnBadArgument && !command.created);
        scanout.frame.copy.scanout = surface;
        assert(dispatch(symbol, &request) == kIOReturnSuccess && request.token.serial);
        assert(outputPages[0] == 0x500000 && outputPages[1] == 0x601000 && DcnAllocationStub::live() == 1);
        outputPages[0] = outputPages[1] = 0x700000;
        pin = request.token;
        scanout.frame.copy.scanout = {};
    }

    ~CommitFixture() { IODMACommand::next = nullptr; IOBufferMemoryDescriptor::next = nullptr; }

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

    static bool qualified(void *context, const HubpFlipRequest &request, const IODMACommand *old,
                          const IODMACommand *next) {
        auto &self = *static_cast<CommitFixture *>(context);
        assert(self.lifetime.references >= 2 && !self.scanout.device.guard.held);
        const auto commandFor = [&](ScanoutPinToken token) -> const IODMACommand * {
            if (!token.serial) return nullptr;
            assert(token == self.pin || token == self.alternatePin);
            return token == self.pin ? &self.command : &self.nextCommand;
        };
        assert(old == commandFor(request.previousPin) && next == commandFor(request.nextPin));
        if (next) {
            auto &table = next == &self.command ? self.homeTable : self.alternateTable;
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
        const auto &table = &mapping.pixels == &command ? homeTable : alternateTable;
        assert((&mapping.pixels == &command || &mapping.pixels == &nextCommand) && mapping.pixels.prepared);
        assert(&mapping.table == &table.dma && table.dma.prepared && table.references == 2);
        assert(&mapping.mapper == &mapper && mapping.bytes == kPage && mapping.address == (table.root & ~(kPage - 1)));
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
        if (address >= 0x03a4a && address <= 0x03a57) {
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
            assert(self.pageReads == (alternate ? 6u : 2u));
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
        const auto step = self.writes++ % 5;
        switch (address) {
        case hubp0::kOtgUpdateLock:
            if (value) {
                assert(step == 0 && !self.lockRequested && !self.lockHeld && value == hubp0::kOtgLockRequest);
                self.lockRequested = true;
                self.lockHeld = !self.lockTimeout;
                if (self.changeGeometryAtLock) ++self.pitch;
                if (self.translationFault == FlipFault::ContextAtLock) self.contextRoot ^= kPage;
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
        if (request.previousPin.serial && self.retire) {
            if (self.translationFault != FlipFault::RetireRootStillInstalled) self.contextRoot = 0;
            if (self.translationFault != FlipFault::RetireRangeStillInstalled) self.firstPage = self.lastPage = 0;
            self.contextControl = 0;
        }
        if (self.translationFault == FlipFault::ContextDuringRetire && request.nextPin.serial) self.contextRoot ^= kPage;
        if (self.translationFault == FlipFault::DualContextDuringRetire && request.nextPin == self.alternatePin)
            self.alternateContextRoot ^= kPage;
        return self.retire;
    }

    static bool read(void *context, uint32_t address, uint32_t &value) {
        auto &self = *static_cast<CommitFixture *>(context);
        const auto low = [](HubpAddress surface) { return static_cast<uint32_t>(surface.address); };
        const auto high = [](HubpAddress surface) { return static_cast<uint32_t>(surface.address >> 32); };
        ++self.reads;
        switch (address) {
        case hubp0::kControl: case hubp0::kFlip2: value = 0; break;
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
};

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
    assert(fixture.writes && fixture.lifetime.references == 3 && !fixture.command.completes && fixture.pageReads == 2);
    assert(fixture.vmWrites == 7 && fixture.homeTable.stores == 1 && fixture.homeTable.references == 2);
    if (fault == FlipFault::Install) assert(fixture.vmAckReads == 3 && fixture.delays == 2);
    assert(scanout.cancelPin(fixture.pin) == kIOReturnNotFound && fixture.begin(request) == kIOReturnBusy);
    ScanoutFlipPoll poll{request.operation, ScanoutFlipResult::Refused};
    const bool afterHigh = fixture.failHigh || fixture.loseRouteAfterHigh || fixture.rewindAfterHigh;
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
    assert(fixture.poll(poll) == kIOReturnNotFound && scanout.cancelPin(fixture.pin) == kIOReturnNotFound);

    if (fault == FlipFault::DifferentPinnedPitch) {
        IODMACommand::next = &fixture.nextCommand;
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

    if (fault == FlipFault::DualPins || fault == FlipFault::DualContextDuringRetire ||
        fault == FlipFault::SharedTable || fault == FlipFault::SharedRoot) {
        IODMACommand::next = &fixture.nextCommand;
        scanout.frame.copy.scanout = {64, 17, fixture.pitch, 8, 2 * kPage};
        scanout.offer();
        DmaRun scratch[2]{};
        uint64_t pages[2]{};
        ScanoutDmaRequest mapped{&scanout.frame.copy, fixture.alternate.address, scratch, 2, pages, 2, {}, {}};
        const OSSymbol map{BUILD34_DCN_PIN_MAP};
        assert(fixture.dispatch(map, &mapped) == kIOReturnSuccess && mapped.token.serial);
        fixture.alternatePin = mapped.token;
        request = {fixture.mapped, fixture.alternate, fixture.alternatePin, {}, ScanoutFlipResult::Refused};
        if (fault == FlipFault::SharedTable || fault == FlipFault::SharedRoot) {
            assert(fixture.begin(request) == kIOReturnNotReady && fixture.vmWrites == 7 && fixture.writes == 5);
            assert(fixture.homeTable.references == 2 && fixture.homeTable.stores == 1 && fixture.homeTable.dma.prepared &&
                   fixture.alternateTable.dma.prepared && !fixture.alternateTable.stores);
            assert(scanout.cancelPin(fixture.alternatePin) == kIOReturnNotReady && !fixture.homeTable.withdrawals &&
                   !fixture.alternateTable.withdrawals);
            return;
        }
        assert(fixture.begin(request) == kIOReturnSuccess && request.result == ScanoutFlipResult::Issued);
        assert(fixture.pageReads == 6 && fixture.writes == 10 && fixture.vmWrites == 14 && DcnAllocationStub::live() == 2);
        poll.operation = request.operation;
        fixture.pending = false;
        fixture.active = fixture.earliest = fixture.alternate;
        fixture.step(poll, ScanoutFlipResult::Waiting);
        const bool failed = fault == FlipFault::DualContextDuringRetire;
        fixture.step(poll, failed ? ScanoutFlipResult::Uncertain : ScanoutFlipResult::Presented);
        assert(fixture.retireChecks == 2 && fixture.command.completes == !failed && !fixture.nextCommand.completes);
        assert(DcnAllocationStub::live() == (failed ? 2u : 1u));
        assert(fixture.homeTable.references == (failed ? 2u : 0u) && fixture.alternateTable.references == 2);
        assert(scanout.cancelPin(fixture.alternatePin) == kIOReturnNotFound);
        return;
    }

    request = {fixture.mapped, fixture.home, {}, {}, ScanoutFlipResult::Refused};
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
    assert(fixture.retireChecks == 2 && !fixture.command.completes && scanout.frame.host.wires == 2);
    IOLockLock(scanout.client.lock);
    assert(fixture.poll(poll) == kIOReturnBusy && fixture.retireChecks == 2);
    IOLockUnlock(scanout.client.lock);
    fixture.retire = true;
    fixture.failUnmap = fault == FlipFault::Unmap;
    if (fault >= FlipFault::RetireRootStillInstalled && fault <= FlipFault::RetireContextReappears) {
        fixture.step(poll, ScanoutFlipResult::Uncertain);
        const bool withdrew = fault == FlipFault::RetireContextReappears;
        assert(fixture.homeTable.withdrawals == withdrew && fixture.homeTable.dma.prepared == !withdrew);
        assert(fixture.command.prepared && !fixture.command.completes && fixture.lifetime.references == 3);
        fixture.step(poll, ScanoutFlipResult::Uncertain);
        assert(fixture.homeTable.withdrawals == withdrew && !fixture.command.completes);
        return;
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
    assert(fixture.command.completes == 1 && fixture.command.clears == !fixture.failUnmap);
    assert(DcnAllocationStub::live() == (fixture.failUnmap ? 1u : 0u));
    assert(scanout.frame.host.wires == (fixture.failUnmap ? 2u : 1u));
    assert(fixture.lifetime.references == (fixture.failUnmap ? 3u : 1u));
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
    scanoutDma(DmaFault::WrongPage, DmaCleanupFault::ConfirmUnmap);
#endif
#ifdef TEST_SCANOUT_FLIP
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
#endif
    std::puts("[PASS] exact writer backing (CPU only)");
}
