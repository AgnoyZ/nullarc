/* SPDX-License-Identifier: MIT
 * Extracted gpuSubmit with CPU-only queue, lock and monotonic clock doubles. */
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <functional>
#include <string_view>
#include <vector>
#include "PhxNativeABI.h"

using IOReturn = int;
static constexpr int kIOReturnSuccess = 0, kIOReturnNotReady = 1,
    kIOReturnBadArgument = 2, kIOReturnBusy = 3;
static constexpr uint32_t kFirstUserVmid = 8;
static constexpr uint64_t budget = 2000000000ull, sentinel = 0xabcdef;
static bool held;
static uint64_t ticks = 30, sleepTicks = 1000000, scale = 1;
static unsigned sleeps;
static std::function<void()> wake;
static void IOLockLock(void *) { assert(!held); held = true; }
static void IOLockUnlock(void *) { assert(held); held = false; }
[[maybe_unused]] static void IODelay(unsigned) { assert(!held && "global lock held during queue backpressure"); }
[[maybe_unused]] static uint64_t mach_absolute_time() { return ticks; }
[[maybe_unused]] static void absolutetime_to_nanoseconds(uint64_t delta, uint64_t *ns) { *ns = delta * scale; }
[[maybe_unused]] static void IOSleep(unsigned ms) {
    assert(!held && ms == 1 && sleeps < 3);
    ++sleeps;
    ticks += sleepTicks;
    if (wake) wake();
}

struct Memory {
    alignas(16) uint64_t words[8]{};
    uintptr_t getVirtualAddress() { return reinterpret_cast<uintptr_t>(words); }
};
struct PhxBringup {
    struct GpuQueue {
        bool ready{true}, gfx{};
        uint32_t ringOff{}, ringDw{1024}, wbOff{}, fenceOff{};
        uint64_t dbByte{}, wptr{8}, doneEnd{8}, completed{99};
        uint64_t fseq[64]{}, fend[64]{};
        uint32_t fvmid[64]{};
        volatile uint32_t head{}, tail{};
        std::vector<uint32_t> packets;
    };
    GpuQueue gq[2];
    struct { uint64_t lastSeq{}; } hwv[8];
    uint64_t gSeq{99}, fbMcBase{0x123400000ull}, checkTicks{};
    Memory aperture, bells;
    Memory *fbAper{&aperture}, *doorbellMap{&bells};
    void *gpuLock{};
    bool contextReady{true};
    unsigned binds{}, flushes{};
    PhxBringup() {
        gq[1].gfx = true;
        gq[1].wbOff = 32;
        gq[1].dbByte = 8;
    }
    void *vmCtx(uint32_t handle) { return contextReady && handle == 7 ? this : nullptr; }
    uint32_t vmBind(uint32_t handle) { assert(held && handle == 7); ++binds; return 8; }
    uint64_t queueFence(const GpuQueue &q) { assert(held); ticks += checkTicks; return q.completed; }
    void ringPut(GpuQueue &q, uint32_t idx, uint32_t value) {
        assert(held);
        if (idx == 0) q.packets.clear();
        assert(idx == q.packets.size());
        q.packets.push_back(value);
    }
    void hdpFlush() { assert(held); ++flushes; }
    IOReturn gpuSubmit(uint32_t, bool, const uint64_t *, const uint32_t *, uint32_t, uint64_t *);
};

// PHX34_EXTRACTED_GPU_SUBMIT_FUNCTION

static IOReturn submit(PhxBringup &d, bool gfx, uint64_t &seq, uint32_t count = 1) {
    uint64_t va[PHXN_MAX_IBS];
    uint32_t dw[PHXN_MAX_IBS];
    for (uint32_t i = 0; i < count; ++i) { va[i] = 0x800012340000ull; dw[i] = 16; }
    const auto r = d.gpuSubmit(7, gfx, va, dw, count, &seq);
    assert(!held);
    return r;
}

static void fill(PhxBringup::GpuQueue &q, unsigned entries, uint64_t used) {
    assert(used % entries == 0);
    q.head = 0;
    q.tail = entries;
    q.wptr = q.doneEnd + used;
    q.completed = 0;
    for (unsigned i = 0; i < entries; ++i) {
        q.fseq[i] = i + 1;
        q.fend[i] = q.doneEnd + (i + 1) * (used / entries);
    }
}

static void checkPackets(PhxBringup &d, unsigned queue, uint32_t slot, uint64_t seq) {
    const auto &q = d.gq[queue];
    const bool gfx = q.gfx;
    const auto fence = d.fbMcBase + q.fenceOff;
    std::vector<uint32_t> expected;
    if (!gfx) expected = {0xc0065800, 0, 0xffffffff, 0x00ffffff, 0, 0, 10, 0xc3b1};
    expected.insert(expected.end(), {0xc0023f00, 0x12340000, 0xffff8000,
        16u | (gfx ? 0u : 1u << 23) | 8u << 24, 0xc0064900, 0x06603514, 0x40000000,
        uint32_t(fence), uint32_t(fence >> 32), uint32_t(seq), uint32_t(seq >> 32), 0});
    assert(q.packets == expected && q.tail == slot + 1);
    assert(q.fseq[slot & 63] == seq && q.fend[slot & 63] == q.wptr && q.fvmid[slot & 63] == 8);
    assert(d.bells.words[queue] == q.wptr && d.aperture.words[(q.wbOff + 16) / 8] == q.wptr);
}

int main(int argc, char **argv) {
    assert(argc == 2);
    const std::string_view name(argv[1]);
    PhxBringup d;
    auto &q = d.gq[0];
    uint64_t seq = sentinel;
    if (name == "compute-fast" || name == "gfx-fast") {
        const bool gfx = name == "gfx-fast";
        assert(submit(d, gfx, seq) == kIOReturnSuccess && seq == 100 && sleeps == 0);
        checkPackets(d, gfx, 0, seq);
    } else if (name == "ring-other-queue") {
        fill(q, 4, 1008);
        wake = [&] { // Run a real invocation on another client while this one is waiting.
            uint64_t other = sentinel;
            assert(submit(d, true, other) == kIOReturnSuccess && other == 100);
            checkPackets(d, 1, 0, other);
            q.completed = 1;
        };
        assert(submit(d, false, seq) == kIOReturnSuccess && seq == 101 && sleeps == 1);
        assert(q.head == 1 && q.doneEnd == 260 && d.binds == 2);
        checkPackets(d, 0, 4, seq);
    } else if (name == "history-space-stolen") {
        q.ringDw = 4096;
        fill(q, 63, 1260);
        wake = [&] {
            q.completed = sleeps;
            if (sleeps != 1) return;
            uint64_t other = sentinel;
            assert(submit(d, false, other) == kIOReturnSuccess && other == 100);
            checkPackets(d, 0, 63, other);
        };
        assert(submit(d, false, seq) == kIOReturnSuccess && seq == 101 && sleeps == 2);
        assert(q.head == 2 && q.doneEnd == 48);
        checkPackets(d, 0, 64, seq);
    } else if (name == "new-preferred-queue") {
        fill(q, 4, 1008);
        d.gq[1].ready = false;
        wake = [&] { IOLockLock(d.gpuLock); d.gq[1].ready = true; IOLockUnlock(d.gpuLock); };
        assert(submit(d, true, seq) == kIOReturnSuccess && seq == 100 && sleeps == 1);
        assert(q.tail == 4 && q.packets.empty() && d.bells.words[0] == 0);
        checkPackets(d, 1, 0, seq);
    } else {
        const bool smaller = name == "readopt-smaller";
        const auto count = smaller ? PHXN_MAX_IBS : 1;
        fill(q, 4, 1008);
        if (smaller) wake = [&] { q = {}; q.ringDw = 256; };
        else if (name == "context-invalid") wake = [&] { d.contextReady = false; };
        else if (name == "queue-unready") wake = [&] { q.ready = d.gq[1].ready = false; };
        else if (name == "oversleep-completed") {
            sleepTicks = budget + 1;
            wake = [&] { q.completed = 4; };
        } else if (name == "timeout-exact-wrap") {
            scale = 2;
            ticks = UINT64_MAX - 50;
            sleepTicks = budget / scale;
        } else if (name == "initial-check-over-budget") d.checkTicks = budget;
        else assert(false && "unknown case");
        const auto expected = smaller ? kIOReturnBadArgument :
            (name == "context-invalid" || name == "queue-unready") ? kIOReturnNotReady : kIOReturnBusy;
        assert(submit(d, false, seq, count) == expected);
        assert(sleeps == (d.checkTicks ? 0u : 1u));
        assert(seq == sentinel && d.gSeq == 99 && !d.binds && !d.flushes && q.packets.empty());
        assert(q.wptr == (smaller ? 8u : 1016u) && q.tail == (smaller ? 0u : 4u));
        assert(!d.bells.words[0] && !d.bells.words[1] && !d.aperture.words[2]);
    }
    puts("passed (CPU only)");
}
