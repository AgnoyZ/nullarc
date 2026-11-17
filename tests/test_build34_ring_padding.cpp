/* SPDX-License-Identifier: MIT
 * CPU fakes around the extracted MIT-option original34 submit function.
 * No IOKit, GPU, real MMIO, hardware cache or completion emulation. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <vector>
#include "PhxNativeABI.h"
using IOReturn = int;
static constexpr int kIOReturnSuccess = 0, kIOReturnNotReady = 1,
    kIOReturnBadArgument = 2, kIOReturnBusy = 3;
static constexpr uint32_t kFirstUserVmid = 8;
static unsigned held, delays;
static void IOLockLock(void *) { assert(!held); held = 1; }
static void IOLockUnlock(void *) { assert(held == 1); held = 0; }
static void IODelay(unsigned value) { assert(held && value == 50); ++delays; }
struct Memory {
    alignas(16) uint8_t bytes[64]{};
    uintptr_t getVirtualAddress() { return reinterpret_cast<uintptr_t>(bytes); }
};
struct PhxBringup {
    struct GpuQueue {
        bool ready{}, gfx{};
        uint32_t ringOff{}, ringDw{}, wbOff{};
        uint64_t wptr{}, doneEnd{}, fenceOff{}, dbByte{};
        uint64_t fseq[64]{}, fend[64]{};
        uint32_t fvmid[64]{}, head{}, tail{};
    };
    struct HardwareVm { uint64_t lastSeq{}; } hwv[8];
    GpuQueue gq[2];
    uint64_t gSeq{99}, fbMcBase{0x123400000ull}, mockFence{99};
    void *gpuLock{};
    Memory aperture, doorbells;
    Memory *fbAper{&aperture}, *doorbellMap{&doorbells};
    bool contextReady{true}, bindReady{true}, retireAfterDelay{};
    unsigned flushes{};
    uint32_t vmid{8};
    std::vector<uint32_t> writes;
    void *vmCtx(uint32_t handle) { return contextReady && handle == 7 ? this : nullptr; }
    uint32_t vmBind(uint32_t handle) { assert(held && handle == 7); return bindReady ? vmid : 0; }
    uint64_t queueFence(const GpuQueue &) { assert(held); return retireAfterDelay && delays ? 99 : mockFence; }
    void ringPut(GpuQueue &q, uint32_t index, uint32_t value) {
        assert(held && index == writes.size());
        assert(((q.wptr + index) & (q.ringDw - 1)) < q.ringDw);
        writes.push_back(value);
    }
    void hdpFlush() { assert(held); ++flushes; }
    IOReturn gpuSubmit(uint32_t, bool, const uint64_t *, const uint32_t *, uint32_t, uint64_t *);
};

// PHX34_EXTRACTED_GPU_SUBMIT_FUNCTION

static uint64_t scenarios, padded, refused;
static void run(uint32_t ring, uint64_t start, unsigned n, bool gfx, unsigned history = 0, bool fallback = false) {
    assert(!held); delays = 0;
    PhxBringup d;
    d.vmid = 8 + ((n + static_cast<unsigned>(start)) & 7);
    auto &q = d.gq[gfx ? 1 : 0];
    q.ready = true; q.gfx = gfx; q.ringDw = ring; q.wptr = q.doneEnd = start;
    q.fenceOff = 0x100;
    if (history) {
        q.head = 9; q.tail = history == 3 ? 72 : 10;
        q.doneEnd = history == 3 ? start : start - ring + 16;
        for (unsigned j = q.head; j != q.tail; ++j) {
            q.fseq[j & 63] = 99; q.fend[j & 63] = start;
        }
        d.mockFence = 98; d.retireAfterDelay = history == 1;
    }
    const auto originalHead = q.head, originalTail = q.tail;
    uint64_t addresses[PHXN_MAX_IBS]; uint32_t lengths[PHXN_MAX_IBS];
    for (unsigned i = 0; i < n; ++i) {
        addresses[i] = ((start & 1) ? 0x800012340000ull : 0x12340000ull) + i * 0x1000;
        lengths[i] = 80 + i * 8;
    }
    const unsigned raw = n * 4 + 8;
    // Independent arithmetic oracle uses division, not the transform's mask.
    const uint64_t end = start + raw;
    const unsigned count = PHX34_CPU_PADDING && !gfx ? static_cast<unsigned>(((end + 255) / 256) * 256 - start) : raw;
    uint64_t seq = 0xabcdef;
    const int result = d.gpuSubmit(7, fallback ? !gfx : gfx, addresses, lengths, n, &seq);
    ++scenarios;
    if (count + 16 > ring || history >= 2) {
        assert(result == (count + 16 > ring ? kIOReturnBadArgument : kIOReturnBusy));
        assert(!held && d.writes.empty() && !d.flushes && d.gSeq == 99 && seq == 0xabcdef);
        assert(q.wptr == start && q.head == originalHead && q.tail == originalTail);
        assert(delays == (count + 16 > ring ? 0u : 40001u)); ++refused; return;
    }
    assert(result == kIOReturnSuccess && !held && seq == 100 && d.gSeq == 100);
    assert(d.writes.size() == count && q.wptr == start + count && q.tail == originalTail + 1);
    assert(q.head == originalTail && q.fend[originalTail & 63] == q.wptr);
    assert(q.fseq[originalTail & 63] == 100 && q.fvmid[originalTail & 63] == d.vmid);
    assert(d.hwv[d.vmid - 8].lastSeq == 100 && d.flushes == 2 && delays == unsigned(history == 1));
    for (unsigned i = 0; i < n; ++i) {
        const uint64_t canonical = (addresses[i] & (1ull << 47)) ? addresses[i] | 0xffff000000000000ull : addresses[i];
        assert(d.writes[i * 4] == 0xc0023f00u);
        assert(d.writes[i * 4 + 1] == uint32_t(canonical));
        assert(d.writes[i * 4 + 2] == uint32_t(canonical >> 32));
        assert(d.writes[i * 4 + 3] == (lengths[i] | (gfx ? 0u : 1u << 23) | d.vmid << 24));
    }
    const uint64_t fence = d.fbMcBase + q.fenceOff;
    const uint32_t release[] = {0xc0064900u, 0x06603514u, 0x40000000u,
        uint32_t(fence), uint32_t(fence >> 32), 100, 0, 0};
    for (unsigned i = 0; i < 8; ++i) assert(d.writes[n * 4 + i] == release[i]);
    for (unsigned i = raw; i < count; ++i) assert(d.writes[i] == 0xffff1000u);
    const auto *wb = reinterpret_cast<const uint32_t *>(d.aperture.bytes + 16);
    assert(wb[0] == uint32_t(q.wptr) && wb[1] == uint32_t(q.wptr >> 32));
    assert(*reinterpret_cast<const uint64_t *>(d.doorbells.bytes) == q.wptr);
    if (PHX34_CPU_PADDING && !gfx) assert((q.wptr & 255) == 0);
    if (count != raw) ++padded;
}
static void admission() {
    for (unsigned fault = 0; fault < 3; ++fault) {
        PhxBringup d;
        if (fault) { d.gq[0].ready = true; d.gq[0].ringDw = 4096; }
        if (fault == 1) d.contextReady = false;
        if (fault == 2) d.bindReady = false;
        uint64_t address = 0x10000, seq = 0xabcdef; uint32_t length = 80;
        assert(d.gpuSubmit(7, false, &address, &length, 1, &seq) == (fault == 2 ? kIOReturnBusy : kIOReturnNotReady));
        assert(!held && d.writes.empty() && !d.flushes && seq == 0xabcdef && d.gSeq == 99); ++scenarios;
    }
}
int main() {
    for (unsigned offset = 0; offset < 256; ++offset)
        for (unsigned n = 1; n <= PHXN_MAX_IBS; ++n)
            for (const bool gfx : {false,true}) run(4096, (1ull << 33) + offset, n, gfx);
    for (const unsigned ring : {256,512,1024,4096,65536})
        for (const unsigned offset : {ring-300u,ring-256u,ring-16u,ring-1u}) {
            if (offset >= ring) continue;
            for (unsigned n = 1; n <= PHXN_MAX_IBS; ++n)
                for (const bool gfx : {false,true}) run(ring, (1ull << 33) + offset, n, gfx);
        }
    for (unsigned history = 1; history <= 3; ++history)
        for (unsigned n = 1; n <= PHXN_MAX_IBS; ++n)
            for (const bool gfx : {false,true}) run(4096, (1ull << 33) + 17, n, gfx, history);
    const uint64_t starts[] = {(1ull << 63) + 4090, UINT64_MAX - 1023, (1ull << 33) + 256};
    for (const uint64_t start : starts)
        for (unsigned n = 1; n <= PHXN_MAX_IBS; ++n)
            for (const bool gfx : {false,true}) run(4096, start, n, gfx, 0, true);
    admission();
    printf("{\"passed\":true,\"policy\":\"%s\",\"scenarios\":%llu,\"padded_submissions\":%llu,\"refused_submissions\":%llu,\"GPU_executed\":false}\n",
        PHX34_CPU_PADDING ? "compute-padding" : "original", (unsigned long long)scenarios,
        (unsigned long long)padded, (unsigned long long)refused);
}
