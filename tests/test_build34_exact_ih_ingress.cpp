#include <array>
#include <initializer_list>

using Vector = std::array<uint8_t, 32>;
using Batch = PhxBringup::ExactIHBatch;
using Route = PhxBringup::ExactIHRoute;
using RouteState = PhxBringup::ExactIHState;
static constexpr int Stale = PhxBringup::kExactIHStale;
static constexpr uint32_t RingBytes = 128, StartCursor = 96;
static constexpr Vector gfx{0x14, 0xb5, 0x80};

static int collectCopy(PhxBringup &gpu, const Route &route, const Batch &batch, bool &kick) {
    const Batch *input = &batch;
    return gpu.collectExactIH(route, [](void *context, Batch &output) {
        CHECK(!gpuHeld && !clientHeld);
        output = **static_cast<const Batch **>(context);
        return true;
    }, &input, kick);
}

static int deliverCopy(PhxBringup &gpu, const Route &route, const Batch &batch) {
    gpu.signalExactIH(route);
    bool kick = false;
    return collectCopy(gpu, route, batch, kick);
}

struct IHStream {
    uint32_t cursor = StartCursor, size = RingBytes;
    uint64_t ordinal = 1;

    Batch capture(std::initializer_list<Vector> vectors) const {
        CHECK(vectors.size() <= 32);
        Batch batch{};
        batch.ordinal = ordinal;
        batch.read = cursor;
        for (const auto &vector : vectors) {
            for (unsigned index = 0; index < vector.size(); ++index) batch.entries[batch.count][index] = vector[index];
            ++batch.count;
        }
        batch.before = batch.after = (cursor + batch.count * 32) % size;
        return batch;
    }

    int deliver(PhxBringup &gpu, const Route &route, std::initializer_list<Vector> vectors) {
        const auto batch = capture(vectors);
        const int result = deliverCopy(gpu, route, batch);
        if (result >= 0) {
            cursor = batch.after;
            ++ordinal;
        }
        return result;
    }
};

#if MODELED_IH
static constexpr int Invalid = PhxBringup::kExactIHInvalid;
static constexpr int Idle = PhxBringup::kExactIHIdle;
static constexpr Vector compute{0x14, 0xb5, 0x04};

static void openActive(PhxBringup &gpu, Route &route, uint32_t size = RingBytes, uint32_t cursor = StartCursor) {
    CHECK(gpu.openExactIHRoute(route, size, cursor));
    bool kick = true;
    CHECK(gpu.activateExactIHRoute(route, kick) && !kick);
}

static void testArmingRaces() {
    for (bool revoke : {false, true}) {
        Trial racing;
        PhxBringup &gpu = racing.gpu;
        gpu.modeledIHAdmission = true;
        Route route{};
        CHECK(gpu.openExactIHRoute(route, RingBytes, StartCursor));
        auto unrelated = route;
        ++unrelated.generation[1];
        CHECK(!gpu.signalExactIH(unrelated));
        bool signalKick = false, activateKick = false;
        std::atomic<bool> start{false};
        std::thread source([&] {
            while (!start.load(std::memory_order_acquire)) std::this_thread::yield();
            if (revoke) {
                IOLockLock(gpu.gpuLock);
                gpu.invalidateExactQueues();
                IOLockUnlock(gpu.gpuLock);
            } else {
                signalKick = gpu.signalExactIH(route);
            }
        });
        if (revoke) CHECK(!gpu.signalExactIH(route));
        start.store(true, std::memory_order_release);
        const bool activated = gpu.activateExactIHRoute(route, activateKick);
        source.join();
        bool laterKick = true;
        if (revoke) {
            CHECK(activateKick == activated && gpu.exactIHState == RouteState::Retiring);
            CHECK(!gpu.activateExactIHRoute(route, laterKick) && !laterKick);
            CHECK(!gpu.signalExactIH(route));
            CHECK(collectCopy(gpu, route, {}, laterKick) == Stale && !laterKick);
        } else {
            CHECK(activated && activateKick != signalKick && gpu.exactIHState == RouteState::Active);
            CHECK(collectCopy(gpu, route, IHStream{}.capture({gfx}), laterKick) == 2 && !laterKick);
            CHECK(collectCopy(gpu, route, {}, laterKick) == Idle && !laterKick);
        }
    }

    Trial cancelled;
    auto &gpu = cancelled.gpu;
    gpu.modeledIHAdmission = true;
    Route arming{};
    CHECK(gpu.openExactIHRoute(arming, RingBytes, StartCursor));
    CHECK(!gpu.signalExactIH(arming));
    CHECK(gpu.loseExactIHRoute(arming) && gpu.exactIHState == RouteState::Lost);
    bool kick = true;
    CHECK(!gpu.activateExactIHRoute(arming, kick) && !kick);
    CHECK(!gpu.signalExactIH(arming) && collectCopy(gpu, arming, {}, kick) == Stale && !kick);
    IOLockLock(gpu.gpuLock);
    CHECK(gpu.exactIHWorkerDrainedLocked(arming));
    IOLockUnlock(gpu.gpuLock);
}
#endif

int main() {
    Trial trial;
    PhxBringup &gpu = trial.gpu;
    Route route{};
    IHStream stream;
    CHECK(!gpu.openExactIHRoute(route, RingBytes, StartCursor) && !route.epoch);
    bool kick = true;
    CHECK(!gpu.signalExactIH(route) && !gpu.activateExactIHRoute(route, kick) && !kick);
    CHECK(stream.deliver(gpu, route, {gfx}) == Stale);
    CHECK(trial.client.wait(1, 500) == Status::TimedOut && polls == 1);
    CHECK(gpu.exactIHState == RouteState::Empty);
#if MODELED_IH
    gpu.modeledIHAdmission = true;
    gpu.serviceId = 0;
    CHECK(!gpu.openExactIHRoute(route, RingBytes, StartCursor) && !route.epoch);
    gpu.serviceId = 1;
    gpu.exactEventOps = nullptr;
    CHECK(!gpu.openExactIHRoute(route, RingBytes, StartCursor));
    gpu.exactEventOps = &trial.ops;
    gpu.isSleeping = true;
    CHECK(!gpu.openExactIHRoute(route, RingBytes, StartCursor));
    gpu.isSleeping = false;
    CHECK(!gpu.openExactIHRoute(route, 32, 0));
    CHECK(!gpu.openExactIHRoute(route, 96, 32));
    CHECK(!gpu.openExactIHRoute(route, 1u << 19, 0));
    CHECK(!gpu.openExactIHRoute(route, RingBytes, RingBytes));
    CHECK(!gpu.openExactIHRoute(route, RingBytes, StartCursor + 1));
    CHECK(gpu.openExactIHRoute(route, RingBytes, StartCursor) && route.epoch == 1);
    Route duplicate{};
    CHECK(!gpu.openExactIHRoute(duplicate, RingBytes, StartCursor) && !duplicate.epoch);
    CHECK(route.service == gpu.serviceId && route.generation[0] == 7 && route.generation[1] == 8);
    auto unrelated = route;
    ++unrelated.epoch;
    CHECK(gpu.exactIHState == RouteState::Arming);
    CHECK(!gpu.signalExactIH(unrelated) && !gpu.activateExactIHRoute(unrelated, kick) && !kick);
    IOLockLock(gpu.gpuLock);
    CHECK(!gpu.signalExactIH(route) && !gpu.signalExactIH(route));
    IOLockUnlock(gpu.gpuLock);
    CHECK(collectCopy(gpu, route, stream.capture({compute}), kick) == Stale && !kick);
    CHECK(!gpu.lock.wakeCount[0] && !gpu.lock.wakeCount[1]);
    CHECK(gpu.activateExactIHRoute(route, kick) && kick);
    CHECK(!gpu.activateExactIHRoute(route, kick) && !kick);
    CHECK(!gpu.signalExactIH(route));
    const auto firstCompute = stream.capture({compute});
    CHECK(collectCopy(gpu, route, firstCompute, kick) == 1 && !kick);
    stream.cursor = firstCompute.after;
    ++stream.ordinal;
    CHECK(gpu.lock.wakeCount[0] == 1 && !gpu.lock.wakeCount[1]);
    CHECK(!gpu.signalExactIH(unrelated) && collectCopy(gpu, route, {}, kick) == Idle && !kick);
    CHECK(gpu.signalExactIH(route) && !gpu.signalExactIH(route));
    CHECK(gpu.lock.wakeCount[0] == 1 && !gpu.lock.wakeCount[1]);
    CHECK(stream.deliver(gpu, route, {gfx}) == 2);
    CHECK(gpu.lock.wakeCount[0] == 1 && gpu.lock.wakeCount[1] == 1);
    CHECK(trial.client.wait(1, 0) == Status::TimedOut);

    for (unsigned offset : {0u, 1u, 2u, 19u}) {
        auto malformed = compute;
        malformed[offset] ^= 1;
        CHECK(stream.deliver(gpu, route, {malformed}) == 0);
    }
    Route stale = route;
    stale.service++;
    CHECK(!gpu.signalExactIH(stale) && stream.deliver(gpu, stale, {gfx}) == Stale && !gpu.loseExactIHRoute(stale));
    stale = route;
    stale.generation[0]++;
    CHECK(!gpu.signalExactIH(stale) && stream.deliver(gpu, stale, {gfx}) == Stale && !gpu.loseExactIHRoute(stale));
    stale = route;
    stale.generation[1]++;
    CHECK(!gpu.signalExactIH(stale) && stream.deliver(gpu, stale, {gfx}) == Stale && !gpu.loseExactIHRoute(stale));
    stale = route;
    stale.epoch++;
    CHECK(deliverCopy(gpu, stale, {}) == Stale && !gpu.loseExactIHRoute(stale));
    CHECK(gpu.lock.wakeCount[0] == 1 && gpu.lock.wakeCount[1] == 1);

    gpu.lock.block = true;
    Status completed{};
    std::thread waiter([&] { completed = trial.client.wait(1, 1000000); });
    trial.waitForPark(1);
    CHECK(stream.deliver(gpu, route, {compute}) == 1);
    IOLockLock(gpu.gpuLock);
    CHECK(gpu.lock.wakeCount[1] == 1);
    IOLockUnlock(gpu.gpuLock);
    CHECK(stream.deliver(gpu, route, {gfx}) == 2);
    trial.waitForPark(1, 2);
    gpu.complete(1);
    CHECK(stream.deliver(gpu, route, {gfx}) == 2);
    waiter.join();
    CHECK(completed == Status::Complete && trial.client.wait(0, 0) == Status::TimedOut);

    Status fallback{};
    unsigned fallbacks = 0;
    std::thread waiting([&] { fallback = trial.client.wait(0, 1000000); fallbacks = polls; });
    trial.waitForPark(0);
    CHECK(gpu.loseExactIHRoute(route));
    waiting.join();
    CHECK(fallback == Status::TimedOut && fallbacks == 1);
    CHECK(gpu.exactIHState == RouteState::Lost && gpu.exactIHRoute.epoch == route.epoch);
    CHECK(!gpu.loseExactIHRoute(route));
    CHECK(stream.deliver(gpu, route, {compute}) == Stale &&
          !gpu.openExactIHRoute(duplicate, RingBytes, StartCursor) && !duplicate.epoch);

    Trial invalidated;
    invalidated.gpu.modeledIHAdmission = true;
    invalidated.gpu.serviceId = 2;
    Route original{};
    openActive(invalidated.gpu, original);
    IHStream invalidatingStream;
    CHECK(invalidatingStream.deliver(invalidated.gpu, route, {gfx}) == Stale);
    invalidated.gpu.lock.block = true;
    Status lost{};
    std::thread sleeper([&] { lost = invalidated.client.wait(1, 1000000); });
    invalidated.waitForPark(1);
    IOLockLock(invalidated.gpu.gpuLock);
    invalidated.gpu.isSleeping = true;
    invalidated.gpu.invalidateExactQueues();
    IOLockUnlock(invalidated.gpu.gpuLock);
    sleeper.join();
    CHECK(lost == Status::Lost && invalidated.gpu.exactIHState == RouteState::Retiring);
    CHECK(invalidated.gpu.exactIHRoute.epoch == original.epoch);
    CHECK(!invalidated.gpu.signalExactIH(original));
    CHECK(invalidatingStream.deliver(invalidated.gpu, original, {gfx}) == Stale &&
          !invalidated.gpu.openExactIHRoute(duplicate, RingBytes, StartCursor));
    IOLockLock(invalidated.gpu.gpuLock);
    invalidated.gpu.isSleeping = false;
    invalidated.gpu.exactQueueLive[0] = invalidated.gpu.exactQueueLive[1] = true;
    IOLockUnlock(invalidated.gpu.gpuLock);
    CHECK(!invalidated.gpu.openExactIHRoute(duplicate, RingBytes, StartCursor) && !duplicate.epoch);
    CHECK(invalidatingStream.deliver(invalidated.gpu, original, {gfx}) == Stale);
    CHECK(!invalidated.gpu.loseExactIHRoute(route));
    Route relabeled = original;
    relabeled.generation[0] = invalidated.gpu.exactQueueGeneration[0];
    relabeled.generation[1] = invalidated.gpu.exactQueueGeneration[1];
    CHECK(invalidatingStream.deliver(invalidated.gpu, relabeled, {gfx}) == Stale &&
          !invalidated.gpu.loseExactIHRoute(relabeled));
    CHECK(invalidated.gpu.lock.wakeCount[0] == 1 && invalidated.gpu.lock.wakeCount[1] == 1);
    CHECK(invalidated.gpu.loseExactIHRoute(original));
    CHECK(invalidated.gpu.exactIHState == RouteState::Lost);
    CHECK(invalidated.gpu.lock.wakeCount[0] == 1 && invalidated.gpu.lock.wakeCount[1] == 1);
    CHECK(!invalidated.gpu.openExactIHRoute(duplicate, RingBytes, StartCursor));

    Trial stopped;
    stopped.gpu.modeledIHAdmission = true;
    stopped.gpu.serviceId = 3;
    Route stopping{};
    openActive(stopped.gpu, stopping);
    stopped.gpu.lock.block = true;
    Status cancelled{};
    std::thread stoppingWaiter([&] { cancelled = stopped.client.wait(0, 1000000); });
    stopped.waitForPark(0);
    stopped.gpu.exactCallbacks.close();
    CHECK(!stopped.gpu.signalExactIH(stopping));
    CHECK(deliverCopy(stopped.gpu, stopping, {}) == Stale);
    IOLockLock(stopped.gpu.gpuLock);
    stopped.gpu.exactStopped = true;
    stopped.gpu.invalidateExactQueues();
    IOLockUnlock(stopped.gpu.gpuLock);
    stoppingWaiter.join();
    CHECK(cancelled == Status::Lost && stopped.gpu.exactIHState == RouteState::Retiring);
    CHECK(stopped.gpu.exactIHRoute.epoch == stopping.epoch &&
          !stopped.gpu.openExactIHRoute(duplicate, RingBytes, StartCursor));
    IOLockLock(invalidated.gpu.gpuLock);
    invalidated.gpu.invalidateExactQueues();
    IOLockUnlock(invalidated.gpu.gpuLock);
    CHECK(invalidated.gpu.exactIHState == RouteState::Lost && invalidated.gpu.exactIHRoute.epoch == original.epoch);

    Trial batching;
    batching.gpu.modeledIHAdmission = true;
    Route batched{};
    IHStream combined;
    openActive(batching.gpu, batched);
    const auto firstBatch = combined.capture({gfx, compute, gfx});
    CHECK(combined.deliver(batching.gpu, batched, {gfx, compute, gfx}) == 3);
    CHECK(combined.cursor == 64 && batching.gpu.exactIHNext == 64);
    CHECK(batching.gpu.lock.wakeCount[0] == 1 && batching.gpu.lock.wakeCount[1] == 1);
    CHECK(combined.deliver(batching.gpu, batched, {Vector{}}) == 0);
    CHECK(combined.cursor == StartCursor);
    CHECK(deliverCopy(batching.gpu, batched, firstBatch) == Invalid);
    CHECK(batching.gpu.exactIHBatchOrdinal == 2 && batching.gpu.exactIHState == RouteState::Lost);
    CHECK(batching.gpu.lock.wakeCount[0] == 2 && batching.gpu.lock.wakeCount[1] == 2);

    Trial split;
    split.gpu.modeledIHAdmission = true;
    Route segmented{};
    IHStream backlog{2016, 2048};
    openActive(split.gpu, segmented, backlog.size, backlog.cursor);
    CHECK(backlog.deliver(split.gpu, segmented, {}) == 0);
    auto chunk = backlog.capture({});
    chunk.count = 32;
    chunk.before = chunk.after = 1024;
    for (unsigned index = 0; index < gfx.size(); ++index) chunk.entries[31][index] = gfx[index];
    CHECK(split.gpu.signalExactIH(segmented));
    CHECK(collectCopy(split.gpu, segmented, chunk, kick) == 2 && kick);
    CHECK(split.gpu.exactIHNext == 992 && split.gpu.exactIHBatchOrdinal == 2);
    backlog.cursor = 992;
    backlog.ordinal = 3;
    CHECK(collectCopy(split.gpu, segmented, backlog.capture({compute}), kick) == 1 && !kick);
    CHECK(split.gpu.exactIHNext == 1024 && split.gpu.lock.wakeCount[0] == 1 && split.gpu.lock.wakeCount[1] == 1);

    for (auto defect : {"skip", "unstable", "overflow", "near-full", "misaligned", "count", "gap", "large"}) {
        Trial malformed;
        malformed.gpu.modeledIHAdmission = true;
        const IHStream input{StartCursor, 2048};
        Route token{};
        openActive(malformed.gpu, token, input.size, input.cursor);
        auto bad = input.capture({gfx});
        const char kind = defect[0];
        if (kind == 's') { bad.read -= 32; bad.count = 2; }
        if (kind == 'u') bad.after += 32;
        if (kind == 'o') { bad.before |= 1; bad.after = bad.before; }
        if (kind == 'n') { bad.before |= 0x40000; bad.after = bad.before; }
        if (kind == 'm') { bad.before += 16; bad.after = bad.before; }
        if (kind == 'c') bad.count = 0;
        if (kind == 'g') ++bad.ordinal;
        if (kind == 'l') { bad.count = 33; bad.before = bad.after = bad.read + 33 * 32; }
        CHECK(deliverCopy(malformed.gpu, token, bad) == Invalid);
        CHECK(malformed.gpu.exactIHState == RouteState::Lost && malformed.gpu.exactIHNext == input.cursor &&
              malformed.gpu.exactIHBatchOrdinal == 0);
        CHECK(malformed.gpu.lock.wakeCount[0] == 1 && malformed.gpu.lock.wakeCount[1] == 1);
        CHECK(deliverCopy(malformed.gpu, token, input.capture({gfx})) == Stale);
        CHECK(!malformed.gpu.openExactIHRoute(duplicate, input.size, input.cursor));
    }

    testArmingRaces();

    for (auto outcome : {RouteState::Active, RouteState::Lost, RouteState::Retiring}) {
        Trial racing;
        racing.gpu.modeledIHAdmission = true;
        Route running{};
        openActive(racing.gpu, running);
        CHECK(racing.gpu.collectExactIH(running, nullptr, nullptr, kick) == Stale && !kick);
        struct PausedCopy {
            std::mutex mutex;
            std::condition_variable changed;
            bool entered = false, resume = false, fail = false;
        } capture;
        capture.fail = outcome == RouteState::Lost;
        const auto copy = +[](void *context, Batch &target) {
            CHECK(!gpuHeld && !clientHeld);
            auto &paused = *static_cast<PausedCopy *>(context);
            std::unique_lock<std::mutex> held(paused.mutex);
            paused.entered = true;
            paused.changed.notify_all();
            CHECK(paused.changed.wait_for(held, std::chrono::seconds(4), [&] { return paused.resume; }));
            target = IHStream{}.capture({gfx});
            return !paused.fail;
        };
        int result = Stale;
        bool workerKick = false;
        CHECK(racing.gpu.signalExactIH(running));
        std::thread worker([&] { result = racing.gpu.collectExactIH(running, copy, &capture, workerKick); });
        {
            std::unique_lock<std::mutex> held(capture.mutex);
            CHECK(capture.changed.wait_for(held, std::chrono::seconds(4), [&] { return capture.entered; }));
        }
        CHECK(!racing.gpu.signalExactIH(running));
        CHECK(collectCopy(racing.gpu, running, {}, kick) == PhxBringup::kExactIHBusy && !kick);
        IOLockLock(racing.gpu.gpuLock);
        CHECK(!racing.gpu.exactIHWorkerDrainedLocked(running));
        if (outcome == RouteState::Retiring) racing.gpu.invalidateExactQueues();
        CHECK(!racing.gpu.exactIHWorkerDrainedLocked(running));
        IOLockUnlock(racing.gpu.gpuLock);
        if (outcome == RouteState::Retiring) CHECK(collectCopy(racing.gpu, running, {}, kick) == Stale && !kick);
        {
            std::lock_guard<std::mutex> held(capture.mutex);
            capture.resume = true;
            capture.changed.notify_all();
        }
        worker.join();
        if (outcome == RouteState::Active) {
            CHECK(result == 2 && workerKick);
            const IHStream following{0, RingBytes, 2};
            CHECK(collectCopy(racing.gpu, running, following.capture({compute}), kick) == 1 && !kick);
            CHECK(collectCopy(racing.gpu, running, {}, kick) == Idle && !kick);
            CHECK(racing.gpu.loseExactIHRoute(running));
            CHECK(racing.gpu.exactIHBatchOrdinal == 2 && racing.gpu.lock.wakeCount[0] == 2 &&
                  racing.gpu.lock.wakeCount[1] == 2);
        } else {
            CHECK(result == (outcome == RouteState::Lost ? Invalid : Stale) && !workerKick);
            CHECK(racing.gpu.exactIHBatchOrdinal == 0 && racing.gpu.exactIHState == outcome);
            CHECK(racing.gpu.lock.wakeCount[0] == 1 && racing.gpu.lock.wakeCount[1] == 1);
        }
        IOLockLock(racing.gpu.gpuLock);
        CHECK(racing.gpu.exactIHWorkerDrainedLocked(running) && !racing.gpu.exactIHWorkerDrainedLocked({}));
        CHECK(racing.gpu.exactIHWorker.active() == 0);
        IOLockUnlock(racing.gpu.gpuLock);
        CHECK(!racing.gpu.openExactIHRoute(duplicate, RingBytes, StartCursor));
    }
#endif
    std::printf("PASS IH ingress: %u checks; modeled=%d\n", checks.load(), MODELED_IH);
}
