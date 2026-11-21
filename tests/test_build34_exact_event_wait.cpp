// SPDX-License-Identifier: MIT
#include "build34_exact_callbacks.h"
#include "build34_exact_ownership.h"
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <cstdlib>
#include <functional>
#include <mutex>
#include <thread>
#include <utility>

using namespace phx34_exact;
static constexpr uint64_t PHXN_WAIT_CAP_NS = 2000000000;
static std::atomic<unsigned> checks{0};
#define CHECK(x) do { ++checks; if (!(x)) { std::fprintf(stderr, "failed %d: %s\n", __LINE__, #x); std::exit(86); } } while (0)

static thread_local unsigned clientHeld = 0, gpuHeld = 0;
static thread_local uint64_t now = 10000000;
static thread_local std::function<void()> onObservationUnlock;
static thread_local std::function<void()> onNextClientUnlock;
static thread_local std::function<void()> onParkDeadline;
static uint64_t mach_absolute_time() { return now; }
static void absolutetime_to_nanoseconds(uint64_t v, uint64_t *out) { *out = v; }

struct IOLock {
    bool gpu = true;
    std::mutex mutex;
    std::condition_variable changed[2], enrolled;
    void *keys[2]{};
    unsigned parkCount[2]{}, wakeCount[2]{};
    uint64_t deadlines[8]{};
    bool block = false, spurious = false;
};
static void IOLockLock(IOLock *p) {
    CHECK(!gpuHeld && (p->gpu || !clientHeld));
    p->mutex.lock();
    ++(p->gpu ? gpuHeld : clientHeld);
}
static void IOLockUnlock(IOLock *p) {
    CHECK((p->gpu ? gpuHeld : clientHeld) == 1);
    --(p->gpu ? gpuHeld : clientHeld);
    p->mutex.unlock();
    if (!p->gpu && onNextClientUnlock) std::exchange(onNextClientUnlock, {})();
}
static thread_local unsigned polls = 0;
static thread_local std::function<void()> onPoll;
static void IOSleep(unsigned ms) {
    CHECK(!gpuHeld && !clientHeld && ms == 1 && ++polls <= 8);
    now += 1000000;
    if (onPoll) std::exchange(onPoll, {})();
}
static void sleepEvent(IOLock *p, void *key, uint64_t sampledAt, uint64_t slice) {
    CHECK(gpuHeld && !clientHeld && sampledAt == now && slice > 0 && slice <= 1000000);
    const unsigned q = key == p->keys[1] ? 1 : 0;
    CHECK(key == p->keys[q] && ++p->parkCount[q] <= 4);
    p->deadlines[4*q + p->parkCount[q]-1] = slice;
    if (p->spurious) return;
    if (!p->block) {
        now = sampledAt + slice;
        if (onParkDeadline) std::exchange(onParkDeadline, {})();
        return;
    }
    const unsigned before = p->wakeCount[q];
    std::unique_lock<std::mutex> held(p->mutex, std::adopt_lock);
    p->enrolled.notify_all();
    CHECK(p->changed[q].wait_for(held, std::chrono::seconds(4), [&] { return p->wakeCount[q] != before; }));
    held.release();
    now += 1000;
}
static void wakeEvent(IOLock *p, void *key) {
    CHECK(gpuHeld && !clientHeld);
    const unsigned q = key == p->keys[1] ? 1 : 0;
    CHECK(key == p->keys[q]);
    ++p->wakeCount[q];
    p->changed[q].notify_all();
}

class PhxBringup {
public:
    IOLock lock;
    IOLock *gpuLock = &lock;
    CallbackGate<> exactCallbacks;
    struct FenceModel { void invalidate() {} } exactFenceWindow[2];
    uint64_t exactQueueGeneration[2]{7, 8}, exactInvalidationEpoch = 0;
    bool exactQueueLive[2]{true, true}, exactStopped = false, isSleeping = false;
    QueueObservation observations[2]{{7, 10, 0, true, false}, {8, 20, 0, true, false}};
    // PHX34_EVENT_FIELDS
    void invalidateExactQueues();
    Status observeExact(Registry &reg, Ticket ticket, const CallbackGate<> &client, const void *identity) {
        CHECK(clientHeld && !gpuHeld && reg.boundTo(this, identity));
        IOLockLock(gpuLock);
        for (unsigned q = 0; q < 2; ++q) {
            observations[q].generation = exactQueueGeneration[q];
            observations[q].ready = exactQueueLive[q];
        }
        auto state = reg.observe(ticket, !client.closed() && !exactCallbacks.closed(), observations);
        IOLockUnlock(gpuLock);
        onNextClientUnlock = std::exchange(onObservationUnlock, {});
        return state;
    }
    void complete(unsigned q) {
        IOLockLock(gpuLock);
        observations[q].completed = observations[q].submitted;
        IOLockUnlock(gpuLock);
    }
    Status bind(Registry &reg, const void *client) {
        static OwnerEpochs owners;
        return reg.bind(this, client, owners);
    }
};

class IOAccelPhxNativeClient {
public:
    IOLock clientLock;
    IOLock *lock = &clientLock;
    CallbackGate<> exactClientCallbacks;
    uint32_t legacyState = 2;
    Registry exactRegistry{0};
    Registry *exactOwnership = &exactRegistry;
    bool exactClientPinned = true;
    PhxBringup *owner;
    Ticket tickets[2];
    Receipt receipts[2]{{10, 7, 0}, {20, 8, 1}};
    explicit IOAccelPhxNativeClient(PhxBringup *p) : owner(p) {
        clientLock.gpu = false;
        CHECK(owner->bind(exactRegistry, this) == Status::Ok);
        for (unsigned q = 0; q < 2; ++q) {
            CHECK(exactRegistry.reserve(tickets[q]) == Status::Ok);
            CHECK(exactRegistry.publish(tickets[q], receipts[q]) == Status::Ok);
        }
    }
    Status waitExactReceipt(Ticket, const Receipt &, uint64_t, uint64_t);
    Status wait(unsigned q, uint64_t time, uint64_t already = 0) {
        polls = 0;
        return waitExactReceipt(tickets[q], receipts[q], time, now - already);
    }
};

// PHX34_EVENT_METHODS

struct Trial {
    PhxBringup::ExactEventOps ops{sleepEvent, wakeEvent, 3};
    PhxBringup gpu;
    IOAccelPhxNativeClient client{&gpu};
    explicit Trial(bool enable = true) {
        gpu.exactEventOps = enable ? &ops : nullptr;
        gpu.lock.keys[0] = &gpu.exactEventSerial[0];
        gpu.lock.keys[1] = &gpu.exactEventSerial[1];
    }
    void waitForPark(unsigned q, unsigned count = 1) {
        std::unique_lock<std::mutex> held(gpu.lock.mutex);
        CHECK(gpu.lock.enrolled.wait_for(held, std::chrono::seconds(4), [&] { return gpu.lock.parkCount[q] >= count; }));
    }
};

int main() {
    {
        Trial t(false);
        CHECK(t.client.wait(1, 0) == Status::TimedOut && !polls);
        onPoll = [&] { t.gpu.complete(1); };
        CHECK(t.client.wait(1, 500) == Status::Complete && polls == 1);
    }
    {
        Trial t;
        CHECK(t.client.wait(1, 0) == Status::TimedOut && !polls && !t.gpu.lock.parkCount[1]);
        onObservationUnlock = [&] { t.gpu.complete(1); CHECK(t.gpu.notifyExactEvent(1, 8)); };
        CHECK(t.client.wait(1, 1000000) == Status::Complete && !polls && !t.gpu.lock.parkCount[1]);
        CHECK(t.client.wait(0, 0) == Status::TimedOut);
        CHECK(t.client.exactRegistry.forget(t.client.tickets[1]) == Status::Ok); // wait pin released
    }
    {
        Trial t;
        CHECK(t.gpu.notifyExactEvent(1, 8)); // a prior notification is not proof of this target
        CHECK(!t.gpu.notifyExactEvent(1, 7) && !t.gpu.notifyExactEvent(2, 8));
        CHECK(t.client.wait(1, 1) == Status::TimedOut && !polls && t.gpu.lock.deadlines[4] == 1);
    }
    {
        Trial t;
        onObservationUnlock = [&] { now += 200000; };
        CHECK(t.client.wait(1, 1000000, 750000) == Status::TimedOut && !polls);
        CHECK(t.gpu.lock.parkCount[1] == 1 && t.gpu.lock.deadlines[4] == 50000);
    }
    {
        Trial t;
        t.gpu.lock.spurious = true;
        CHECK(t.client.wait(1, 900000) == Status::TimedOut && polls == 1 && t.gpu.lock.parkCount[1] == 1);
    }
    {
        Trial t;
        onParkDeadline = [&] {
            CHECK(gpuHeld && !clientHeld);
            t.gpu.observations[1].completed = 20; // completion visible, interrupt missing
        };
        CHECK(t.client.wait(1, 2000000) == Status::Complete && !polls && t.gpu.lock.parkCount[1] == 1);
        CHECK(!t.gpu.lock.wakeCount[1] && t.gpu.lock.deadlines[4] == 1000000);
    }
    {
        Trial t;
        t.ops.queues = 1;
        CHECK(!t.gpu.notifyExactEvent(1, 8));
        CHECK(t.client.wait(1, 100) == Status::TimedOut && polls == 1 && !t.gpu.lock.parkCount[1]);
    }
    {
        Trial t;
        t.gpu.exactEventSerial[1] = UINT64_MAX-1;
        CHECK(t.gpu.notifyExactEvent(1, 8));
        CHECK(!t.gpu.notifyExactEvent(1, 8) && t.gpu.exactEventSerial[1] == UINT64_MAX);
        CHECK(t.client.wait(1, 1) == Status::TimedOut && polls == 1 && !t.gpu.lock.parkCount[1]);
    }
    {
        Trial t;
        t.gpu.lock.block = true;
        Status result[2]{};
        std::thread gfx([&] { result[0] = t.client.wait(1, 1000000); });
        std::thread gfx2([&] { result[1] = t.client.wait(1, 1000000); });
        t.waitForPark(1, 2);
        CHECK(t.gpu.notifyExactEvent(0, 7));
        CHECK(!t.gpu.notifyExactEvent(1, 7));
        IOLockLock(t.gpu.gpuLock);
        CHECK(t.gpu.lock.wakeCount[1] == 0);
        IOLockUnlock(t.gpu.gpuLock);
        CHECK(t.gpu.notifyExactEvent(1, 8)); // both wake, neither target is complete yet
        t.waitForPark(1, 4);
        t.gpu.complete(1);
        CHECK(t.gpu.notifyExactEvent(1, 8));
        gfx.join();
        gfx2.join();
        CHECK(result[0] == Status::Complete && result[1] == Status::Complete);
        CHECK(t.client.wait(0, 0) == Status::TimedOut);
    }
    for (bool close : {false, true}) {
        Trial t;
        t.gpu.lock.block = true;
        Status result{};
        std::thread waiter([&] { result = t.client.wait(1, 1000000); });
        t.waitForPark(1);
        if (close) t.gpu.exactCallbacks.close();
        IOLockLock(t.gpu.gpuLock);
        t.gpu.invalidateExactQueues();
        IOLockUnlock(t.gpu.gpuLock);
        waiter.join();
        CHECK(result == Status::Lost && t.gpu.lock.parkCount[1] == 1);
    }
    {
        Trial t;
        onObservationUnlock = [&] { t.client.exactClientCallbacks.close(); };
        CHECK(t.client.wait(1, 100) == Status::Closed && !t.gpu.lock.parkCount[1]);
    }
    std::printf("PASS %u exact event-wait checks\n", checks.load());
}
