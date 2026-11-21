// SPDX-License-Identifier: MIT
// Included after the unchanged event-wait fixture by the offline runner.

int main() {
    priorWaitTests();
    const unsigned previous = checks.load();
    {
        Trial t;
        t.ops.sleep = PhxBringup::sleepExactIOKit;
        t.ops.wake = PhxBringup::wakeExactIOKit;
        now = 100;
        IOLockLock(t.gpu.gpuLock);
        PhxBringup::sleepExactIOKit(t.gpu.gpuLock, t.gpu.lock.keys[0], 80, 40);
        CHECK(now == 120 && t.gpu.lock.deadlines[0] == 20);
        PhxBringup::sleepExactIOKit(t.gpu.gpuLock, t.gpu.lock.keys[0], 80, 40);
        nsPerTick = 3;
        PhxBringup::sleepExactIOKit(t.gpu.gpuLock, t.gpu.lock.keys[0], now, 2);
        nsPerTick = 1;
        PhxBringup::sleepExactIOKit(t.gpu.gpuLock, t.gpu.lock.keys[0], UINT64_MAX-4, 5);
        CHECK(t.gpu.lock.parkCount[0] == 1);
        IOLockUnlock(t.gpu.gpuLock);
        t.gpu.lock.spurious = true;
        CHECK(t.client.wait(1, 1000000) == Status::TimedOut && polls == 1);
        CHECK(t.gpu.exactEventSleepers == 0 && t.gpu.lock.parkCount[1] == 1);
    }
    {
        Trial t;
        t.ops.sleep = PhxBringup::sleepExactIOKit;
        t.ops.wake = PhxBringup::wakeExactIOKit;
        t.gpu.lock.block = true;
        t.gpu.exactEventSleepers = t.gpu.kExactEventSleepers - 1; // model 31 existing leases
        Status result{};
        std::thread waiter([&] { result = t.client.wait(1, 1000000); });
        t.waitForPark(1);
        IOLockLock(t.gpu.gpuLock);
        CHECK(t.gpu.exactEventSleepers == t.gpu.kExactEventSleepers);
        IOLockUnlock(t.gpu.gpuLock);
        CHECK(t.client.wait(0, 1000000) == Status::TimedOut && polls == 1);
        CHECK(t.gpu.lock.parkCount[0] == 0);
        t.gpu.complete(1);
        CHECK(t.gpu.notifyExactEvent(1, 8));
        waiter.join();
        CHECK(t.gpu.exactEventSleepers == t.gpu.kExactEventSleepers - 1 && result == Status::Complete);
    }
    std::printf("PASS %u IOKit event-wait checks\n", checks.load() - previous);
}
