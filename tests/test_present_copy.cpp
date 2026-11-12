// Host-RAM execution of extracted current driver bodies. No driver installation or GPU work.
#include "PhxCopyPath.hpp"
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <vector>

using SInt64 = int64_t;
using UInt32 = uint32_t;
static const unsigned kNvMaxFB = 2;
static int gIopSse, gIopDamage, gIopFullOnce;
static SInt64 gCntIopDamageBusy, gCntIopDamageFull, gIopDamageBytes, gIopDamageBytesSum;
static bool failAllocation;
static unsigned allocations;
static bool OSCompareAndSwap(UInt32 old, UInt32 next, volatile UInt32 *p) {
    if (*p != old) return false;
    *p = next;
    return true;
}
static SInt64 OSAddAtomic64(SInt64 n, SInt64 *p) { SInt64 old = *p; *p += n; return old; }
static void *IOMallocAligned(size_t bytes, size_t align) {
    if (failAllocation) return nullptr;
    void *p = nullptr;
    if (posix_memalign(&p, align, bytes)) return nullptr;
    ++allocations;
    return p;   // Deliberately uninitialized; MSan checks forced frames never compare this memory.
}
static void IOFreeAligned(void *p, size_t) { std::free(p); --allocations; }
#include "present-copy.inc"

static constexpr uint32_t guard = 0xa55ac33cu;
struct Buffer {
    uint32_t *base;
    size_t count;
    explicit Buffer(size_t n) : base(nullptr), count(n) {
        void *p = nullptr;
        assert(posix_memalign(&p, 64, n * sizeof(uint32_t)) == 0);
        base = static_cast<uint32_t *>(p);
        for (size_t i = 0; i < count; ++i) base[i] = guard;
    }
    ~Buffer() { std::free(base); }
    Buffer(const Buffer &) = delete;
    Buffer &operator=(const Buffer &) = delete;
};
static uint32_t pattern(size_t i) { return uint32_t(i * 1664525u + 1013904223u); }
static uint32_t expectedPixel(uint32_t v, bool narrow) {
    if (!narrow) return v;
    // Independent ARGB2101010 channel decode, not the driver's narrowing helper.
    const uint32_t b = (v & 1023u) / 4u;
    const uint32_t g = ((v >> 10) & 1023u) / 4u;
    const uint32_t r = ((v >> 20) & 1023u) / 4u;
    return 0xff000000u | (r << 16) | (g << 8) | b;
}
static unsigned fullCases, damageCases;
static void fullCase(unsigned w, unsigned h, unsigned spad, unsigned dpad, unsigned so, unsigned dO,
                     bool narrow, bool enabled) {
    const unsigned spr = w + spad, dpr = w + dpad;
    const size_t startS = 16u + so, startD = 16u + dO;
    Buffer source(startS + size_t(spr) * h + 16), dest(startD + size_t(dpr) * h + 16);
    std::vector<uint32_t> expected(dest.count, guard);
    for (size_t i = 0; i < source.count; ++i) source.base[i] = pattern(i);
    for (unsigned y = 0; y < h; ++y) for (unsigned x = 0; x < w; ++x)
        expected[startD + size_t(y) * dpr + x] = expectedPixel(source.base[startS + size_t(y) * spr + x], narrow);
    gIopSse = enabled;
    sseCalls = 0;
    nvIopCopyFull(source.base + startS, spr, dest.base + startD, dpr, w, h, narrow);
    for (size_t i = 0; i < dest.count; ++i) assert(dest.base[i] == expected[i]);
    for (size_t i = 0; i < source.count; ++i) assert(source.base[i] == pattern(i));
    const bool sse = enabled && so % 4 == 0 && dO % 4 == 0 && spr % 4 == 0 && dpr % 4 == 0;
    const bool packed = sse && spr == w && dpr == w && (uint64_t(w) * h) % 16 == 0;
    const unsigned expectedCalls = packed ? 1u : (sse && w >= 16 ? h : 0u);
    assert(sseCalls == expectedCalls);
    ++fullCases;
}
static void damageCase(unsigned w, unsigned h, unsigned pad, unsigned offset, bool narrow) {
    const unsigned stride = w + pad;
    const size_t start = 16 + offset;
    Buffer source(start + size_t(stride) * h + 16), dest(start + size_t(stride) * h + 16);
    for (size_t i = 0; i < source.count; ++i) source.base[i] = pattern(i);
    gIopDamage = 1;
    gIopFullOnce = 0;
    nvIopShadowDrop(0);
    auto copy = [&]() { ++damageCases; return nvIopCopyDamage(0, source.base + start, stride,
        dest.base + start, stride, w, h, narrow); };
    const SInt64 fullBytes = SInt64(w) * h * 4;
    assert(copy() == fullBytes);
    assert(copy() == 0);  // Stable frame makes no stores.
    // One changed tail pixel rewrites only its group in its own row, including an odd short tail.
    const size_t changed = start + size_t(h - 1) * stride + w - 1;
    source.base[changed] ^= 0x0ff00ff0u;
    const unsigned tail = w % 16 ? w % 16 : 16;
    assert(copy() == SInt64(tail) * 4);
    assert(copy() == 0);
    gIopFullOnce = 1;
    assert(copy() == fullBytes && gIopFullOnce == 0);
    for (size_t i = 0; i < dest.count; ++i) {
        bool visible = i >= start && i - start < size_t(stride) * h && (i - start) % stride < w;
        assert(dest.base[i] == (visible ? expectedPixel(source.base[i], narrow) : guard));
    }
    // Disable/re-enable invalidates the shadow even if the destination has been changed externally.
    gIopDamage = 0;
    assert(copy() == -1);
    gIopDamage = 1;
    assert(copy() == fullBytes);
}
int main() {
    assert(__builtin_cpu_supports("sse4.1") && "actual streaming test needs SSE4.1");
    for (unsigned w : {1u,2u,3u,4u,7u,15u,16u,17u,31u,32u,33u,64u,65u,2560u})
        for (unsigned h : {1u,3u,4u}) for (unsigned sp : {0u,1u,8u}) for (unsigned dp : {0u,1u,8u})
            for (unsigned so = 0; so < 4; ++so) for (unsigned dO = 0; dO < 4; ++dO)
                for (bool narrow : {false,true}) for (bool enabled : {false,true})
                    fullCase(w,h,sp,dp,so,dO,narrow,enabled);
    // Native raster, both formats: exactly one real SSE invocation instead of 1600.
    fullCase(2560,1600,0,0,0,0,false,true);
    fullCase(2560,1600,0,0,0,0,true,true);
    for (unsigned w : {1u,15u,16u,17u,31u,32u,33u,65u}) for (unsigned h : {1u,3u})
        for (unsigned pad : {0u,3u}) for (unsigned offset : {0u,1u}) for (bool narrow : {false,true})
            damageCase(w,h,pad,offset,narrow);
    Buffer source(128), dest(128);
    gIopShadow[0].busy = 1;
    gIopShadow[0].valid = true;
    const auto beforeBusy = gCntIopDamageBusy;
    assert(nvIopCopyDamage(0,source.base,16,dest.base,16,16,1,false) == -1);
    assert(!gIopShadow[0].valid && gCntIopDamageBusy == beforeBusy + 1);
    gIopShadow[0].busy = 0;
    failAllocation = true;
    assert(nvIopCopyDamage(1,source.base,16,dest.base,16,16,1,false) == -1);
    assert(!gIopShadow[1].busy && !gIopShadow[1].valid);
    failAllocation = false;
    assert(nvIopCopyDamage(kNvMaxFB,source.base,16,dest.base,16,16,1,false) == -1);
    assert(nvIopCopyDamage(0,source.base,16,dest.base,16,0,1,false) == -1);
    assert(nvIopCopyDamage(0,source.base,16,dest.base,16,16,0,false) == -1);
    for (auto &sh : gIopShadow) if (sh.buf) { IOFreeAligned(sh.buf,sh.bytes); sh.buf = nullptr; }
    assert(allocations == 0);
    std::printf("{\"full_cases\":%u,\"damage_cases\":%u,\"packed_2560x1600_sse_calls\":1,"
                "\"previous_row_sse_calls\":1600,\"hardware_executed\":false}\n",fullCases,damageCases);
}
