#include "build34_dcn_writer_receipt.h"
#include "build34_exact_callbacks.h"
#include "build34_exact_ownership.h"
#ifdef TEST_PRESENT_HANDOFF
#include "build34_dcn_present_route.h"
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
    IOReturn prepare() override { assert(false); return kIOReturnNotReady; }
    IOReturn complete() override { assert(false); return kIOReturnNotReady; }
    void retain() override { assert(false); }
    void release() override { assert(false); }
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

struct PhxBringup
#ifdef TEST_PRESENT_HANDOFF
    : IOService
#endif
{
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
    std::puts("[PASS] exact writer backing (CPU only)");
}
