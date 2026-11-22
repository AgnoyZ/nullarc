static constexpr IOReturn kIOReturnSuccess = 0, kIOReturnBusy = -1, kIOReturnNotReady = -2,
    kIOReturnNotPermitted = -3, kIOReturnNotAttached = -4, kIOReturnError = -5;

class IOWorkLoop;
static thread_local IOWorkLoop *heldLoop;
static thread_local std::function<void()> beforeKick, duringWake, beforeRemove;
static thread_local bool failAttach;
static std::atomic<unsigned> loopsCreated{0}, loopsFreed{0};

class IOEventSource : public OSObject {
    friend class IOWorkLoop;
    IOWorkLoop *attached{nullptr};
protected:
    virtual bool checkForWork() = 0;
    void signalWorkAvailable();
public:
    bool init(OSObject *owner) { return owner != nullptr; }
    IOWorkLoop *getWorkLoop() const { return attached; }
};

class IOWorkLoop final : public OSObject {
    std::mutex gate;
    IOEventSource *source{nullptr};
    std::atomic<bool> pending{false};
public:
    std::atomic<unsigned> wakeCount{0}, removeCount{0};
    bool failRemoveAfterUnlink = false, falseSuccess = false;

    static IOWorkLoop *workLoop() { ++loopsCreated; return new IOWorkLoop; }
    bool onThread() const { return heldLoop == this; }
    bool inGate() const { return heldLoop == this; }

    IOReturn addEventSource(IOEventSource *incoming) {
        CHECK(!gpuHeld && !clientHeld && !heldLoop && !source);
        if (failAttach) return kIOReturnError;
        std::lock_guard<std::mutex> lock(gate);
        source = incoming;
        source->retain();
        source->attached = this;
        heldLoop = this;
        CHECK(!source->checkForWork());
        heldLoop = nullptr;
        return kIOReturnSuccess;
    }

    void wake() {
        ++wakeCount;
        pending.store(true);
    }

    bool turn(bool forced = false) {
        CHECK(!gpuHeld && !clientHeld && !heldLoop);
        std::lock_guard<std::mutex> lock(gate);
        if ((!pending.exchange(false) && !forced) || !source) return false;
        heldLoop = this;
        CHECK(!source->checkForWork());
        heldLoop = nullptr;
        return true;
    }

    IOReturn removeEventSource(IOEventSource *outgoing) {
        CHECK(!gpuHeld && !clientHeld && !heldLoop);
        ++removeCount;
        if (beforeRemove) std::exchange(beforeRemove, {})();
        std::lock_guard<std::mutex> lock(gate);
        CHECK(source == outgoing);
        if (falseSuccess) return kIOReturnSuccess;
        source = nullptr;
        outgoing->attached = nullptr;
        outgoing->release();
        return failRemoveAfterUnlink ? kIOReturnError : kIOReturnSuccess;
    }

    ~IOWorkLoop() override { CHECK(!source); ++loopsFreed; }
};

void IOEventSource::signalWorkAvailable() {
    CHECK(!gpuHeld && !clientHeld);
    if (duringWake) std::exchange(duringWake, {})();
    CHECK(attached);
    attached->wake();
}

#define OSDeclareDefaultStructors(Type)
#define OSDefineMetaClassAndStructors(Type, Parent)
// PHX34_WORKLOOP_SOURCE
#undef OSDeclareDefaultStructors
#undef OSDefineMetaClassAndStructors

using Source = PhxExactIHWorkSource;
using Batch = PhxBringup::ExactIHBatch;

struct Barrier {
    std::mutex mutex;
    std::condition_variable changed;
    bool ready = false, proceed = false;
    void arrive() {
        std::unique_lock<std::mutex> lock(mutex);
        ready = true;
        changed.notify_all();
        CHECK(changed.wait_for(lock, std::chrono::seconds(4), [&] { return proceed; }));
    }
    void wait() {
        std::unique_lock<std::mutex> lock(mutex);
        CHECK(changed.wait_for(lock, std::chrono::seconds(4), [&] { return ready; }));
    }
    void resume() {
        std::lock_guard<std::mutex> lock(mutex);
        proceed = true;
        changed.notify_all();
    }
};

struct Capture final : OSObject {
    unsigned calls = 0;
    uint32_t cursor = 0, producer = 32;
    bool fail = false, selfDetach = false;
    Barrier *pause{nullptr};
    Source *expectedSource{nullptr};

    static bool copy(void *opaque, Batch &batch) {
        auto &owner = *static_cast<Capture *>(static_cast<OSObject *>(opaque));
        CHECK(heldLoop && !gpuHeld && !clientHeld);
        CHECK(owner.references == 2);
        if (owner.selfDetach) CHECK(owner.expectedSource->detach() == kIOReturnNotPermitted);
        if (owner.pause) owner.pause->arrive();
        if (owner.fail) return false;
        batch.ordinal = ++owner.calls;
        batch.read = owner.cursor;
        batch.before = batch.after = owner.producer;
        const uint32_t available = (owner.producer - owner.cursor) / 32;
        batch.count = available > 32 ? 32 : available;
        if (batch.count) {
            batch.entries[0][0] = 0x14;
            batch.entries[0][1] = 0xb5;
            batch.entries[0][2] = batch.ordinal == 1 ? 0x04 : 0x00;
        }
        owner.cursor += batch.count * 32;
        return true;
    }
};

static Source *prepare(Trial &trial, Capture &capture) {
    auto *source = Source::prepare(&trial.gpu, 2048, 0, Capture::copy, &capture);
    capture.expectedSource = source;
    return source;
}

[[maybe_unused]] static void releaseCaller(Trial &trial, Capture &capture, Source *source) {
    CHECK(source->references == 1 && trial.gpu.references == 2 && capture.references == 2);
    source->release();
    CHECK(trial.gpu.references == 1 && capture.references == 1);
}

int main() {
    Trial closed;
    Capture capture;
    CHECK(!prepare(closed, capture) && loopsCreated == 0);
    CHECK(capture.references == 1 && closed.gpu.references == 1);
#if MODELED_IH
    Trial rejected;
    rejected.gpu.modeledIHAdmission = true;
    failAttach = true;
    CHECK(!prepare(rejected, capture));
    failAttach = false;
    CHECK(loopsCreated == 1 && loopsFreed == 1);
    CHECK(rejected.gpu.exactIHState == PhxBringup::ExactIHState::Lost);
    CHECK(capture.references == 1 && rejected.gpu.references == 1);

    Trial arming;
    arming.gpu.modeledIHAdmission = true;
    capture.producer = 33 * 32;
    capture.selfDetach = true;
    auto *source = prepare(arming, capture);
    CHECK(source && source->references == 3);
    auto *loop = source->getWorkLoop();
    IOLockLock(arming.gpu.gpuLock);
    source->hint();
    source->hint();
    IOLockUnlock(arming.gpu.gpuLock);
    CHECK(!loop->wakeCount && loop->turn(true) && !capture.calls);
    CHECK(source->activate() && loop->wakeCount == 1);
    CHECK(loop->turn() && capture.calls == 1 && capture.cursor == 32 * 32);
    CHECK(loop->wakeCount == 2);
    CHECK(loop->turn() && capture.calls == 2 && capture.cursor == capture.producer);
    CHECK(!loop->turn());
    CHECK(arming.gpu.lock.wakeCount[0] == 1 && arming.gpu.lock.wakeCount[1] == 1);
    CHECK(arming.client.wait(1, 0) == Status::TimedOut);
    CHECK(source->detach() == kIOReturnBusy && loop->removeCount == 0);

    beforeKick = [&] {
        source->closeAdmission();
        CHECK(source->detach() == kIOReturnSuccess);
    };
    source->hint();
    CHECK(!beforeKick && !source->getWorkLoop() && loop->wakeCount == 2);
    source->hint();
    CHECK(!source->activate() && source->detach() == kIOReturnNotReady && loop->removeCount == 1);
    releaseCaller(arming, capture, source);

    Trial waking;
    Capture scheduled;
    waking.gpu.modeledIHAdmission = true;
    source = prepare(waking, scheduled);
    CHECK(source && source->activate());
    loop = source->getWorkLoop();
    Barrier wake;
    std::thread interrupt([&] {
        duringWake = [&] { wake.arrive(); };
        source->hint();
    });
    wake.wait();
    source->closeAdmission();
    CHECK(source->detach() == kIOReturnBusy && loop->removeCount == 0);
    wake.resume();
    interrupt.join();
    CHECK(loop->wakeCount == 1 && loop->turn() && scheduled.calls == 0);
    CHECK(source->detach() == kIOReturnSuccess && loop->removeCount == 1);
    releaseCaller(waking, scheduled, source);

    enum class Invalidation { Queue, Sleep, Stop };
    for (auto trigger : {Invalidation::Queue, Invalidation::Sleep, Invalidation::Stop}) {
        Trial invalidated;
        Capture pending;
        invalidated.gpu.modeledIHAdmission = true;
        source = prepare(invalidated, pending);
        CHECK(source && source->activate());
        loop = source->getWorkLoop();
        source->hint();
        if (trigger == Invalidation::Stop) {
            invalidated.gpu.stop(nullptr);
            CHECK(invalidated.gpu.exactStopped && invalidated.gpu.hangDrainRequests == 1);
        } else if (trigger == Invalidation::Sleep) {
            CHECK(invalidated.gpu.setPowerState(0, nullptr) == IOPMAckImplied);
            CHECK(invalidated.gpu.isSleeping);
            CHECK(invalidated.gpu.setPowerState(1, nullptr) == IOPMAckImplied);
            CHECK(!invalidated.gpu.isSleeping);
        } else {
            IOLockLock(invalidated.gpu.gpuLock);
            invalidated.gpu.invalidateExactQueues();
            IOLockUnlock(invalidated.gpu.gpuLock);
        }
        CHECK(loop->removeCount == 0 && source->getWorkLoop() == loop);
        source->hint();
        CHECK(loop->turn() && !pending.calls && loop->wakeCount == 1);
        CHECK(invalidated.gpu.exactIHState == PhxBringup::ExactIHState::Retiring);
        CHECK(!source->activate());
        CHECK(source->detach() == kIOReturnSuccess);
        if (trigger == Invalidation::Stop) {
            CHECK(invalidated.gpu.references == 3);
            invalidated.gpu.release();
        }
        releaseCaller(invalidated, pending, source);
    }

    Trial busyStop;
    Capture stopped;
    busyStop.gpu.modeledIHAdmission = true;
    source = prepare(busyStop, stopped);
    CHECK(source && source->activate());
    loop = source->getWorkLoop();
    {
        decltype(busyStop.gpu.exactCallbacks)::Lease callback(busyStop.gpu.exactCallbacks);
        CHECK(callback);
        beforeKick = [&] {
            busyStop.gpu.stop(nullptr);
            CHECK(!busyStop.gpu.exactStopped && busyStop.gpu.hangDrainRequests == 1);
            CHECK(busyStop.gpu.exactIHState == PhxBringup::ExactIHState::Active);
            CHECK(loop->removeCount == 0);
        };
        source->hint();
        CHECK(!beforeKick && !loop->wakeCount && loop->turn(true) && !stopped.calls);
    }
    busyStop.gpu.sealStoppedQueues();
    CHECK(busyStop.gpu.exactIHState == PhxBringup::ExactIHState::Retiring && busyStop.gpu.exactStopped);
    CHECK(source->detach() == kIOReturnSuccess);
    CHECK(busyStop.gpu.references == 3);
    busyStop.gpu.release();
    releaseCaller(busyStop, stopped, source);

    Trial copying;
    Capture paused;
    copying.gpu.modeledIHAdmission = true;
    Barrier copy, removal;
    paused.pause = &copy;
    source = prepare(copying, paused);
    CHECK(source && source->activate());
    loop = source->getWorkLoop();
    source->hint();
    std::thread worker([&] { CHECK(loop->turn()); });
    copy.wait();
    source->hint();
    CHECK(copying.gpu.setPowerState(0, nullptr) == IOPMAckImplied);
    CHECK(copying.gpu.isSleeping && copying.gpu.exactIHState == PhxBringup::ExactIHState::Retiring);
    beforeRemove = [&] { CHECK(false); };
    CHECK(source->detach() == kIOReturnBusy && loop->removeCount == 0 && source->references == 3);
    CHECK(beforeRemove);
    beforeRemove = {};
    CHECK(copying.gpu.exactIHState == PhxBringup::ExactIHState::Lost);
    CHECK(paused.references == 2 && copying.gpu.exactIHBatchOrdinal == 0);
    copy.resume();
    worker.join();
    IOReturn detached = kIOReturnError;
    std::thread cleanup([&] {
        beforeRemove = [&] { removal.arrive(); };
        detached = source->detach();
    });
    removal.wait();
    CHECK(source->detach() == kIOReturnNotReady && source->references == 3 && loop->removeCount == 1);
    CHECK(loop->turn(true) && paused.calls == 1);
    removal.resume();
    cleanup.join();
    CHECK(detached == kIOReturnSuccess && !source->getWorkLoop() && paused.calls == 1);
    CHECK(copying.gpu.exactIHBatchOrdinal == 0 && loop->wakeCount == 1);
    releaseCaller(copying, paused, source);

    for (bool falseSuccess : {false, true}) {
        Trial uncertain;
        Capture pinned;
        uncertain.gpu.modeledIHAdmission = true;
        source = prepare(uncertain, pinned);
        CHECK(source && source->activate());
        loop = source->getWorkLoop();
        loop->falseSuccess = falseSuccess;
        loop->failRemoveAfterUnlink = !falseSuccess;
        source->closeAdmission();
        CHECK(source->detach() == (falseSuccess ? kIOReturnNotReady : kIOReturnError));
        CHECK(source->references == (falseSuccess ? 3 : 2));
        CHECK(source->detach() == kIOReturnNotReady && loop->removeCount == 1);
        source->hint();
        CHECK(!loop->wakeCount && !pinned.calls && pinned.references == 2);
        if (falseSuccess) {
            loop->falseSuccess = false;
            CHECK(loop->removeEventSource(source) == kIOReturnSuccess);
        }
        source->release();
        releaseCaller(uncertain, pinned, source);
    }
#endif
    CHECK(loopsCreated == loopsFreed);
    std::printf("PASS IH workloop: %u checks; modeled=%d\n", checks.load(), MODELED_IH);
}
