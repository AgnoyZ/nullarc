static constexpr uint8_t gfx[32] = {0x14, 0xb5, 0x80};
#if MODELED_IH
static constexpr uint8_t compute[32] = {0x14, 0xb5, 0x04};
#endif

int main() {
    using Route = PhxBringup::ExactIHRoute;
    Trial trial;
    PhxBringup &gpu = trial.gpu;
    Route route{};
    CHECK(!gpu.openExactIHRoute(route) && !route.epoch);
    CHECK(!gpu.notifyExactIH(route, gfx));
    CHECK(trial.client.wait(1, 500) == Status::TimedOut && polls == 1);
#if MODELED_IH
    gpu.modeledIHAdmission = true;
    gpu.serviceId = 0;
    CHECK(!gpu.openExactIHRoute(route) && !route.epoch);
    gpu.serviceId = 1;
    gpu.exactEventOps = nullptr;
    CHECK(!gpu.openExactIHRoute(route));
    gpu.exactEventOps = &trial.ops;
    gpu.isSleeping = true;
    CHECK(!gpu.openExactIHRoute(route));
    gpu.isSleeping = false;
    CHECK(gpu.openExactIHRoute(route) && route.epoch == 1);
    Route duplicate{};
    CHECK(!gpu.openExactIHRoute(duplicate) && !duplicate.epoch);
    CHECK(route.service == gpu.serviceId && route.generation[0] == 7 && route.generation[1] == 8);
    CHECK(gpu.notifyExactIH(route, compute));
    CHECK(gpu.lock.wakeCount[0] == 1 && !gpu.lock.wakeCount[1]);
    CHECK(gpu.notifyExactIH(route, gfx));
    CHECK(gpu.lock.wakeCount[0] == 1 && gpu.lock.wakeCount[1] == 1);
    CHECK(trial.client.wait(1, 0) == Status::TimedOut);

    for (unsigned offset : {0u, 1u, 2u, 19u}) {
        uint8_t malformed[32]{};
        for (unsigned index = 0; index < sizeof(malformed); ++index) malformed[index] = compute[index];
        malformed[offset] ^= 1;
        CHECK(!gpu.notifyExactIH(route, malformed));
    }
    Route stale = route;
    stale.service++;
    CHECK(!gpu.notifyExactIH(stale, gfx) && !gpu.loseExactIHRoute(stale));
    stale = route;
    stale.generation[0]++;
    CHECK(!gpu.notifyExactIH(stale, gfx) && !gpu.loseExactIHRoute(stale));
    stale = route;
    stale.epoch++;
    CHECK(!gpu.notifyExactIH(stale, gfx) && !gpu.loseExactIHRoute(stale));
    CHECK(gpu.lock.wakeCount[0] == 1 && gpu.lock.wakeCount[1] == 1);

    gpu.lock.block = true;
    Status completed{};
    std::thread waiter([&] { completed = trial.client.wait(1, 1000000); });
    trial.waitForPark(1);
    CHECK(gpu.notifyExactIH(route, compute));
    IOLockLock(gpu.gpuLock);
    CHECK(gpu.lock.wakeCount[1] == 1);
    IOLockUnlock(gpu.gpuLock);
    CHECK(gpu.notifyExactIH(route, gfx));
    trial.waitForPark(1, 2);
    gpu.complete(1);
    CHECK(gpu.notifyExactIH(route, gfx));
    waiter.join();
    CHECK(completed == Status::Complete && trial.client.wait(0, 0) == Status::TimedOut);

    Status fallback{};
    unsigned fallbacks = 0;
    std::thread waiting([&] { fallback = trial.client.wait(0, 1000000); fallbacks = polls; });
    trial.waitForPark(0);
    CHECK(gpu.loseExactIHRoute(route));
    waiting.join();
    CHECK(fallback == Status::TimedOut && fallbacks == 1);
    CHECK(!gpu.notifyExactIH(route, compute) && !gpu.openExactIHRoute(duplicate) && !duplicate.epoch);

    Trial invalidated;
    invalidated.gpu.modeledIHAdmission = true;
    invalidated.gpu.serviceId = 2;
    Route original{};
    CHECK(invalidated.gpu.openExactIHRoute(original));
    CHECK(!invalidated.gpu.notifyExactIH(route, gfx));
    invalidated.gpu.lock.block = true;
    Status lost{};
    std::thread sleeper([&] { lost = invalidated.client.wait(1, 1000000); });
    invalidated.waitForPark(1);
    IOLockLock(invalidated.gpu.gpuLock);
    invalidated.gpu.isSleeping = true;
    invalidated.gpu.invalidateExactQueues();
    IOLockUnlock(invalidated.gpu.gpuLock);
    sleeper.join();
    CHECK(lost == Status::Lost && !invalidated.gpu.exactIHRoute.epoch);
    CHECK(!invalidated.gpu.notifyExactIH(original, gfx) && !invalidated.gpu.openExactIHRoute(duplicate));
    IOLockLock(invalidated.gpu.gpuLock);
    invalidated.gpu.isSleeping = false;
    invalidated.gpu.exactQueueLive[0] = invalidated.gpu.exactQueueLive[1] = true;
    IOLockUnlock(invalidated.gpu.gpuLock);
    CHECK(invalidated.gpu.openExactIHRoute(duplicate) && duplicate.epoch == original.epoch + 1);
    CHECK(!invalidated.gpu.notifyExactIH(original, gfx) && !invalidated.gpu.loseExactIHRoute(original));
    CHECK(invalidated.gpu.notifyExactIH(duplicate, gfx));
    invalidated.gpu.exactCallbacks.close();
    CHECK(!invalidated.gpu.notifyExactIH(duplicate, gfx));
    IOLockLock(invalidated.gpu.gpuLock);
    invalidated.gpu.invalidateExactQueues();
    IOLockUnlock(invalidated.gpu.gpuLock);
    CHECK(!invalidated.gpu.exactIHRoute.epoch && !invalidated.gpu.openExactIHRoute(duplicate));
#endif
    std::printf("PASS IH ingress: %u checks; modeled=%d\n", checks.load(), MODELED_IH);
}
