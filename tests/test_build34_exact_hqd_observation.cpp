// SPDX-License-Identifier: MIT
#include "hqd-fixture.inc"

using Bank = PhxBringup::HqdBank;
static constexpr uint32_t saved = 0x1000, target = 0x2000, untouched = 0x5a5a;
static constexpr unsigned selector = 4; // CPU fake address, not an MMIO offset
struct Model {
    unsigned reads = 0, writes = 0, samples = 0, failRead = 0, failWrite = 0, mismatch = 0;
    bool failResolve = false, failSample = false;
    Pause *duringSample = nullptr;
};
static Model model;

static void leased(PhxBringup *d) {
    CHECK(gpuHeld == 1 && d->exactCallbacks.active() == 1 && d->exactRawWriters.active() == 1);
}
static bool get(PhxBringup *d, uint32_t *out) {
    leased(d);
    *out = ++model.reads == model.mismatch ? 0xff : d->rreg(selector);
    return model.reads != model.failRead;
}
static bool resolve(PhxBringup *d, Bank bank, uint32_t original, uint32_t *out) {
    leased(d);
    CHECK(original == saved);
    *out = target + static_cast<unsigned>(bank);
    return !model.failResolve;
}
static bool set(PhxBringup *d, uint32_t value) {
    leased(d);
    d->wreg(selector, value); // a failure may still have changed the selector
    return ++model.writes != model.failWrite;
}
static bool readSample(PhxBringup *d, Bank bank, uint32_t *out) {
    leased(d);
    ++model.samples;
    if (model.duringSample) model.duringSample->arrive();
    *out = d->rreg(selector) == target + static_cast<unsigned>(bank) ? 0 : 1;
    return !model.failSample;
}
static constexpr PhxBringup::HqdAccess access{get, resolve, set, readSample};

static void init(PhxBringup &d) {
    model = {};
    d.wreg(selector, saved);
    d.exactHqdAccess = &access;
}
static void checkFault(PhxBringup &d) {
    uint32_t rb = untouched;
    CHECK(d.exactRawWriters.closed());
    CHECK(d.writeReg(selector, 1, &rb) == kIOReturnNotReady && rb == untouched);
    const uint64_t queue[6] = {0, 1024, 8192, 0, 8, 9000};
    CHECK(d.adoptQueue(queue) == kIOReturnNotReady && !d.exactQueueAdopted[0]);
    CHECK(d.aperture.words[9000 / 8] == 0);
}

int main() {
    {
        PhxBringup d;
        uint32_t out = untouched;
        CHECK(d.observeInitialHqd(Bank::Kiq, &out) == kIOReturnNotReady && out == untouched);
        init(d);
        CHECK(d.observeInitialHqd(static_cast<Bank>(8), &out) == kIOReturnBadArgument);
        CHECK(d.observeInitialHqd(Bank::Kiq, nullptr) == kIOReturnBadArgument);
        d.isSleeping = true;
        CHECK(d.observeInitialHqd(Bank::Kiq, &out) == kIOReturnNotReady && !model.reads);
        d.isSleeping = false;
        IOLockLock(d.gpuLock);
        std::thread contender([&] { CHECK(d.observeInitialHqd(Bank::Kiq, &out) == kIOReturnBusy); });
        contender.join();
        IOLockUnlock(d.gpuLock);
        CHECK(!model.reads);
        CHECK(d.observeInitialHqd(Bank::Gfx, &out) == kIOReturnSuccess && out == 0);
        CHECK(model.reads == 4 && model.samples == 1 && model.writes == 2 && d.rreg(selector) == saved);
    }
    for (unsigned fault = 0; fault < 10; ++fault) {
        PhxBringup d;
        init(d);
        if (fault < 4) model.failRead = fault + 1;
        else if (fault < 6) model.failWrite = fault - 3;
        else if (fault < 8) model.mismatch = fault - 4;
        else if (fault == 8) model.failResolve = true;
        else model.failSample = true;
        uint32_t out = untouched;
        CHECK(d.observeInitialHqd(Bank::Compute, &out) == kIOReturnNotReady && out == untouched);
        CHECK(d.rreg(selector) == saved);
        if (fault == 0 || fault == 8) CHECK(!model.writes && !model.samples && !d.exactRawWriters.closed());
        else if (fault == 9) CHECK(model.writes == 2 && model.samples == 1 && !d.exactRawWriters.closed());
        else {
            CHECK(model.writes == 2);
            checkFault(d);
        }
    }
    for (bool close : {false, true}) {
        PhxBringup d;
        init(d);
        Pause pause;
        model.duringSample = &pause;
        uint32_t out = untouched;
        IOReturn result = kIOReturnBadArgument;
        std::thread observer([&] { result = d.observeInitialHqd(Bank::Scheduler, &out); });
        pause.wait();
        uint32_t rb = untouched;
        CHECK(d.writeReg(selector, 0x77, &rb) == kIOReturnBusy && rb == untouched);
        CHECK(d.observeInitialHqd(Bank::Gfx, &rb) == kIOReturnBusy && rb == untouched);
        if (close) CHECK(d.exactCallbacks.close() && !d.exactCallbacks.drained());
        pause.resume();
        observer.join();
        CHECK(result == (close ? kIOReturnNotReady : kIOReturnSuccess));
        CHECK(out == (close ? untouched : 0) && d.rreg(selector) == saved && !d.exactRawWriters.active());
        if (close) CHECK(d.exactCallbacks.drained());
    }
    std::printf("PASS %u HQD observation checks\n", checks.load());
}
