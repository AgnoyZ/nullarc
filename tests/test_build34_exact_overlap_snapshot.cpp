// SPDX-License-Identifier: MIT
// Actual staged observation methods; clocks, registry IDs and fences are CPU doubles.
#include <array>
#include <cstdio>
#include <cstdlib>
#include <mutex>
#include <thread>
#include "build34_exact_callbacks.h"
#include "build34_exact_fence32.h"

static unsigned checks;
#define CHECK(x) do { ++checks; if (!(x)) { std::fprintf(stderr, "failed %d: %s\n", __LINE__, #x); std::exit(86); } } while (0)
static thread_local bool gpuHeld;
struct IOLock { std::mutex mutex; };
static void IOLockLock(IOLock *lock) { CHECK(!gpuHeld); lock->mutex.lock(); gpuHeld = true; }
static void IOLockUnlock(IOLock *lock) { CHECK(gpuHeld); gpuHeld = false; lock->mutex.unlock(); }

struct IOMemoryMap {
    uint32_t words[2]{};
    uint64_t getLength() const { return sizeof(words); }
    uintptr_t getVirtualAddress() const { return reinterpret_cast<uintptr_t>(words); }
};

struct PhxBringup {
    // PHX34_OVERLAP_FIELDS
    phx34_exact::CallbackGate<> exactCallbacks;
    IOLock lock;
    IOLock *gpuLock = &lock;
    uint64_t registryId = 7, gSeq = 0;
    uint64_t getRegistryEntryID() { CHECK(!gpuHeld && exactCallbacks.active() == 1); return registryId; }
    bool exactStopped = false, isSleeping = false, exactVMFault = false;
    bool exactQueueAdopted[2]{true, true}, exactQueueLive[2]{true, true};
    uint64_t exactQueueGeneration[2]{2, 3}, exactQueueSubmitted[2]{};
    struct GpuQueue { bool ready = true; uint64_t fenceOff = 0; uint32_t head = 0, tail = 1; uint64_t fseq[64]{}; } gq[2];
    struct VmCtx { bool busy = false; uint64_t queueSequence[2]{}, queueGeneration[2]{}, newest = 0; };
    static constexpr unsigned kMaxCtx = 2;
    VmCtx vm[kMaxCtx];
    IOMemoryMap map;
    IOMemoryMap *fbAper = &map;
    uint64_t fbAperLen = map.getLength();
    phx34_exact::FenceWindow32 exactFenceWindow[2];
    bool (*exactDwordReader)(const volatile uint32_t *, uint32_t *) = nullptr;
    bool readExactFence32(uint32_t, uint64_t *);
    bool vmWorkCurrent(const VmCtx &) const;
};

static PhxBringup *service;
static unsigned reads, clocks;
static bool failSecond, closeOnEnd;
static uint64_t ticks[2];

static uint64_t mach_absolute_time() {
    CHECK(gpuHeld && clocks < 2);
    if (clocks == 1 && closeOnEnd) std::thread([] { service->exactCallbacks.close(); }).join();
    return ticks[clocks++];
}
static void absolutetime_to_nanoseconds(uint64_t tick, uint64_t *ns) { *ns = tick; }
static bool readDword(const volatile uint32_t *p, uint32_t *out) {
    CHECK(gpuHeld && service->exactCallbacks.active() == 1 && clocks == 1 && reads < 2);
    CHECK(p == &service->map.words[reads]);
    *out = *p;
    return ++reads != 2 || !failSecond;
}

// PHX34_OVERLAP_METHODS

using Sample = PhxBringup::ExactOverlapSnapshot;
static void setup(PhxBringup &d, uint32_t base = 99) {
    service = &d;
    d.gSeq = base + 2;
    d.exactDwordReader = readDword;
    for (unsigned qi = 0; qi < 2; ++qi) {
        d.map.words[qi] = base;
        d.gq[qi].fenceOff = qi * sizeof(uint32_t);
        const uint64_t seq = base + qi + 1, gen = d.exactQueueGeneration[qi];
        d.exactQueueSubmitted[qi] = d.gq[qi].fseq[0] = seq;
        CHECK(d.exactFenceWindow[qi].seed(gen, base) && d.exactFenceWindow[qi].submit(gen, seq));
    }
}
static void interval(uint64_t begin, uint64_t end) {
    reads = clocks = 0;
    ticks[0] = begin;
    ticks[1] = end;
}
static auto fields(const Sample &s) {
    return std::array<uint64_t, 10>{s.serviceEpoch, s.beginNs, s.endNs,
        s.queues[0].generation, s.queues[0].submitted, s.queues[0].completed,
        s.queues[1].generation, s.queues[1].submitted, s.queues[1].completed, s.retired};
}
static Sample capture(PhxBringup &d, uint64_t begin, uint64_t end) {
    interval(begin, end);
    Sample sample{};
    CHECK(d.captureExactOverlap(sample) && reads == 2 && clocks == 2);
    CHECK(!gpuHeld && !d.exactCallbacks.active());
    return sample;
}
static void scenario() {
    PhxBringup d;
    setup(d);
    const auto before = capture(d, 10, 11);
    d.map.words[1] = 101;
    const auto witness = capture(d, 24, 25);
    const auto after = capture(d, 39, 40);
    d.map.words[0] = 100;
    const auto drained = capture(d, 50, 51);
    CHECK((fields(after) == std::array<uint64_t, 10>{7, 39, 40, 2, 100, 99, 3, 101, 101, 99}));
    CHECK(drained.retired == 101);
    for (const auto &s : {before, witness, after, drained}) {
        for (uint64_t field : fields(s)) std::printf("%llu ", static_cast<unsigned long long>(field));
        std::puts("");
    }
}
static void reject(unsigned mode) {
    PhxBringup d;
    setup(d);
    interval(10, 11);
    switch (mode) {
    case 0: failSecond = true; break;
    case 1: ++d.exactQueueGeneration[1]; break;
    case 2: d.exactQueueLive[1] = false; break;
    case 3: d.exactQueueAdopted[1] = false; break;
    case 4: d.exactQueueGeneration[1] = 0; d.gq[1] = {}; d.gq[1].ready = false;
            d.gq[1].tail = 0; d.exactQueueLive[1] = false; d.exactQueueSubmitted[1] = 0; break;
    case 5: closeOnEnd = true; break;
    case 6: d.exactCallbacks.close(); break;
    case 7: d.registryId = 0; break;
    case 8: d.registryId = UINT64_MAX; break;
    case 9: ticks[1] = 9; break;
    case 10: ticks[0] = 0; break;
    case 11: d.exactDwordReader = nullptr; break;
    case 12: d.gq[1].fseq[0] = 1; break;
    case 13: d.vm[0] = {true, {100, 0}, {1, 0}, 100}; break;
    case 14: d.exactVMFault = true; break;
    case 15: ticks[1] = UINT64_MAX; break;
    case 16: d.gpuLock = nullptr; break;
    }
    Sample out{{{11, 12, 13}, {14, 15, 16}}, 17, 18, 19, 20};
    const auto old = fields(out);
    CHECK(!d.captureExactOverlap(out) && fields(out) == old);
    CHECK(!gpuHeld && !d.exactCallbacks.active());
    if (mode == 0 || mode == 5) CHECK(reads == 2);
    if (mode == 5) CHECK(d.exactCallbacks.drained());
    failSecond = closeOnEnd = false;
    if (mode == 4) {
        // The existing global helper still accepts a truly unused slot.
        reads = 0;
        clocks = 1; // call the helper directly, without the timed wrapper
        phx34_exact::CallbackGate<>::Lease lease(d.exactCallbacks);
        CHECK(lease);
        IOLockLock(d.gpuLock);
        uint64_t retired = 0;
        CHECK(d.exactGlobalRetiredLocked(retired) && reads == 1 && retired == 99);
        IOLockUnlock(d.gpuLock);
    }
}

int main() {
    scenario();
    for (unsigned i = 0; i < 17; ++i) reject(i);
    PhxBringup d;
    setup(d, 0);
    d.registryId = 8;
    const auto zero = capture(d, 10, 10);
    CHECK(zero.retired == 0 && zero.serviceEpoch == 8);
    std::printf("%u\n", checks);
}
