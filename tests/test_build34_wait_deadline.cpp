// SPDX-License-Identifier: MIT
// CPU doubles for the extracted production wait method; no IOKit/GPU backend.
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <limits>
#include "PhxNativeABI.h"

#define CHECK(x) do { if (!(x)) { std::fprintf(stderr, "check failed at %d: %s\n", __LINE__, #x); std::exit(1); } } while (0)
using IOReturn = int;
enum { kIOReturnSuccess = 0, kIOReturnNotReady = 1, kIOReturnBadArgument = 2 };
struct IOExternalMethodArguments {
    uint64_t scalarInput[3]{}, scalarOutput[3]{99, 99, 99};
    bool validShape = true;
};
static bool shape(IOExternalMethodArguments *a, int i, int o, int si, int so) {
    CHECK(i == 3 && o == 3 && si == 0 && so == 0);
    return a->validShape;
}

static uint64_t ticks, origin, numer = 125, denom = 3;
static uint64_t delayCost = 50000, sleepCost = 1000000, firstPollCost;
static uint64_t completeAt = std::numeric_limits<uint64_t>::max();
static unsigned delays, sleeps, polls, conversions, locks, lockDepth;
static char firstWait;
static uint64_t nsNow() {
    return static_cast<uint64_t>((static_cast<__uint128_t>(ticks - origin) * numer) / denom);
}
static void advance(uint64_t ns) {
    ticks += static_cast<uint64_t>((static_cast<__uint128_t>(ns) * denom + numer - 1) / numer);
}
static uint64_t mach_absolute_time() { return ticks; }
static void absolutetime_to_nanoseconds(uint64_t value, uint64_t *out) {
    conversions++;
    *out = static_cast<uint64_t>((static_cast<__uint128_t>(value) * numer) / denom);
}
static void IODelay(unsigned us) {
    CHECK(us == 50 && lockDepth == 0 && delays + sleeps < 5000);
    if (!firstWait) firstWait = 'D';
    delays++; advance(delayCost);
}
static void IOSleep(unsigned ms) {
    CHECK(ms == 1 && lockDepth == 0 && delays + sleeps < 5000);
    if (!firstWait) firstWait = 'S';
    sleeps++; advance(sleepCost);
}
static void IOLockLock(void *) { CHECK(lockDepth == 0); lockDepth++; locks++; }
static void IOLockUnlock(void *) { CHECK(lockDepth == 1); lockDepth--; }
static void phx_cpu_bcopy(const void *src, void *dst, size_t count) {
    CHECK(lockDepth == 1); std::memcpy(dst, src, count);
}
#define bcopy phx_cpu_bcopy
struct Owner {
    bool ready = true;
    uint64_t pending = 2, completed = 5;
    bool gpuReady() const { return ready; }
    uint64_t gpuRetired() const {
        CHECK(lockDepth == 0);
        if (!polls++) advance(firstPollCost);
        return nsNow() >= completeAt ? completed : pending;
    }
};
struct Bo { uint8_t *kva; uint64_t size; };
struct IOAccelPhxNativeClient {
    bool hello = true, haveBo = true;
    void *lock = nullptr;
    Owner *owner;
    uint64_t emitted = 5, pendFenceSeq = 0, pendFenceOffset = 8;
    uint32_t pendFenceHandle = 7;
    uint8_t bytes[32];
    Bo bo{bytes, sizeof bytes};
    unsigned flushes = 0;
    explicit IOAccelPhxNativeClient(Owner *o) : owner(o) { std::memset(bytes, 0xa5, sizeof bytes); }
    void flushBos() { CHECK(lockDepth == 1); flushes++; }
    Bo *findBo(uint32_t handle) { CHECK(lockDepth == 1 && handle == 7); return haveBo ? &bo : nullptr; }
    IOReturn doWaitSeq(IOExternalMethodArguments *a);
};

// PHX34_EXTRACTED_WAIT_SEQ_METHOD

int main(int argc, char **argv) {
    CHECK(argc == 2);
    const std::string name(argv[1]);
    Owner owner;
    IOAccelPhxNativeClient client(&owner);
    IOExternalMethodArguments a;
    a.scalarInput[0] = 5; a.scalarInput[1] = 100000;
    IOReturn expected = kIOReturnSuccess;
    bool ready = false;
    if (name == "not-hello") { client.hello = false; expected = kIOReturnNotReady; }
    else if (name == "bad-shape") { a.validShape = false; expected = kIOReturnBadArgument; }
    else if (name == "future-sequence") { a.scalarInput[0] = 6; expected = kIOReturnBadArgument; }
    else if (name == "not-adopted") { owner.ready = false; ready = true; }
    else if (name == "already-retired") { completeAt = 0; ready = true; }
    else if (name == "last-sequence") { a.scalarInput[0] = PHXN_SEQ_LAST; completeAt = 0; ready = true; }
    else if (name == "zero-target") { a.scalarInput[0] = 0; ready = true; }
    else if (name == "zero-pending") { a.scalarInput[1] = 0; client.pendFenceSeq = 4; }
    else if (name == "zero-ready") { a.scalarInput[1] = 0; completeAt = 0; ready = true; }
    else if (name == "one-nanosecond") { a.scalarInput[1] = 1; }
    else if (name == "normal-fast-timeout") {}
    else if (name == "delay-overshoot") { delayCost = 600000; }
    else if (name == "delay-boundary") { delayCost = 100000; }
    else if (name == "initial-poll-over-budget") { firstPollCost = 200000; }
    else if (name == "elapsed-phase") { firstPollCost = 1200000; a.scalarInput[1] = 2000000; }
    else if (name == "sleep-overshoot") { a.scalarInput[1] = 3000000; sleepCost = 30000000; }
    else if (name == "cap-budget") { a.scalarInput[1] = UINT64_MAX; delayCost = 3000000000; }
    else if (name == "non-unit-timebase") { numer = 1000; denom = 7; delayCost = 100000; }
    else if (name == "clock-wrap") { ticks = origin = UINT64_MAX - 1200; }
    else if (name == "completion-after-delay") { completeAt = 50000; ready = true; }
    else if (name == "completion-at-deadline") { completeAt = 100000; ready = true; }
    else if (name == "completion-after-oversleep") { delayCost = 600000; completeAt = 500000; ready = true; }
    else if (name == "completion-after-sleep") { a.scalarInput[1] = 5000000; completeAt = 2000000; ready = true; }
    else if (name == "pending-retained") { client.pendFenceSeq = 4; }
    else if (name == "fence-published") { client.pendFenceSeq = 4; completeAt = 0; ready = true; }
    else if (name == "newer-fence-retained") { client.pendFenceSeq = 6; completeAt = 0; ready = true; }
    else if (name == "missing-fence-bo") { client.pendFenceSeq = 4; client.haveBo = false; completeAt = 0; ready = true; }
    else if (name == "short-fence-bo") { client.pendFenceSeq = 4; client.bo.size = 12; completeAt = 0; ready = true; }
    else if (name == "unmapped-fence-bo") { client.pendFenceSeq = 4; client.bo.kva = nullptr; completeAt = 0; ready = true; }
    else CHECK(false);
    const uint64_t oldPending = client.pendFenceSeq;
    const IOReturn result = client.doWaitSeq(&a);
    CHECK(result == expected && lockDepth == 0);
    if (expected != kIOReturnSuccess) {
        CHECK(polls == 0 && delays == 0 && sleeps == 0 && client.flushes == 0);
        CHECK(a.scalarOutput[0] == 99 && a.scalarOutput[1] == 99 && a.scalarOutput[2] == 99);
    } else {
        const uint64_t retired = !owner.ready ? client.emitted : ready && completeAt != UINT64_MAX ? owner.completed : owner.pending;
        CHECK(a.scalarOutput[0] == static_cast<uint64_t>(!ready));
        CHECK(a.scalarOutput[1] == retired && a.scalarOutput[2] == client.emitted);
        CHECK(client.flushes == static_cast<unsigned>(ready && owner.ready));
        const bool publish = ready && owner.ready && oldPending && oldPending <= retired;
        CHECK(client.pendFenceSeq == (publish ? 0 : oldPending));
        if (name == "fence-published") {
            uint64_t value; std::memcpy(&value, client.bytes + 8, sizeof value); CHECK(value == 4);
            for (unsigned i = 0; i < sizeof client.bytes; i++) if (i < 8 || i >= 16) CHECK(client.bytes[i] == 0xa5);
        } else for (uint8_t byte : client.bytes) CHECK(byte == 0xa5);
    }
    if (name == "not-adopted" || name == "already-retired" || name == "last-sequence" || name == "zero-target" ||
        name == "zero-pending" || name == "zero-ready" || name == "fence-published" || name == "newer-fence-retained" ||
        name == "missing-fence-bo" || name == "short-fence-bo" || name == "unmapped-fence-bo") CHECK(delays == 0 && sleeps == 0);
    if (name == "initial-poll-over-budget") CHECK(delays == 0 && sleeps == 0);
    if (name == "delay-overshoot" || name == "delay-boundary" || name == "cap-budget" ||
        name == "non-unit-timebase" || name == "one-nanosecond" || name == "completion-after-delay" ||
        name == "completion-after-oversleep") CHECK(delays == 1 && sleeps == 0);
    if (name == "normal-fast-timeout" || name == "clock-wrap" || name == "completion-at-deadline") CHECK(delays == 2 && sleeps == 0);
    if (name == "elapsed-phase") CHECK(firstWait == 'S' && delays == 0 && sleeps == 1);
    if (name == "sleep-overshoot") CHECK(delays == 20 && sleeps == 1);
    if (name == "completion-after-sleep") CHECK(delays == 20 && sleeps == 1);
    std::printf("{\"case\":\"%s\",\"passed\":true,\"GPU_executed\":false,\"delays\":%u,\"sleeps\":%u,\"polls\":%u,\"elapsed_ns\":%llu}\n",
                name.c_str(), delays, sleeps, polls, static_cast<unsigned long long>(nsNow()));
}
