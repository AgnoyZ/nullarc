// SPDX-License-Identifier: MIT
// Byte-exact, full-arena tests for production packed/row SSE and scalar paths.
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <vector>

// ACTUAL_SSE

static int gIopSse;
static void production(const volatile unsigned int *src, volatile unsigned int *d,
                       unsigned words, unsigned spr, unsigned dpr, unsigned h, bool l10r)
{
// ACTUAL_COPY
}

static unsigned cases;
static void check(unsigned words, unsigned spr, unsigned dpr, unsigned h,
                  unsigned sourceOffset, unsigned destOffset, bool sse, bool l10r,
                  bool sameAllocation = false)
{
    constexpr size_t guard = 64;
    const size_t sourceBytes = guard * 2 + sourceOffset + (size_t)spr * h * 4;
    const size_t destBytes = guard * 2 + destOffset + (size_t)dpr * h * 4;
    void *sa = nullptr, *da = nullptr;
    assert(posix_memalign(&sa, 64, sourceBytes) == 0);
    assert(posix_memalign(&da, 64, destBytes) == 0);
    auto cleanup = [](void *p) { free(p); };
    std::unique_ptr<void, decltype(cleanup)> sourceArena(sa, cleanup), destArena(da, cleanup);
    auto *sb = static_cast<uint8_t *>(sa), *db = static_cast<uint8_t *>(da);
    uint32_t seed = 0xa1a2a3u;
    for (size_t i = 0; i < sourceBytes; ++i) {
        seed ^= seed << 13; seed ^= seed >> 17; seed ^= seed << 5;
        sb[i] = (uint8_t)seed;
    }
    memset(db, 0xa5, destBytes);
    std::vector<uint8_t> original(sb, sb + sourceBytes), reference(db, db + destBytes);
    const unsigned int *src = reinterpret_cast<unsigned int *>(sb + guard + sourceOffset);
    unsigned int *dst = reinterpret_cast<unsigned int *>(db + guard + destOffset);
    if (sameAllocation) {
        assert(spr == dpr && sourceOffset == destOffset && sourceBytes == destBytes);
        dst = reinterpret_cast<unsigned int *>(sb + guard + sourceOffset);
        reference = original;
    }
    auto *referencePixels = reference.data() + guard + destOffset;
    for (unsigned y = 0; y < h; ++y) for (unsigned x = 0; x < words; ++x) {
        uint32_t v;
        memcpy(&v, original.data() + guard + sourceOffset + ((size_t)y * spr + x) * 4, 4);
        if (l10r) v = 0xff000000u | ((v >> 6) & 0xff0000u) | ((v >> 4) & 0xff00u) | ((v >> 2) & 0xffu);
        memcpy(referencePixels + ((size_t)y * dpr + x) * 4, &v, 4);
    }
    gIopSse = sse;
    production(src, dst, words, spr, dpr, h, l10r);
    if (sameAllocation) assert(memcmp(sb, reference.data(), sourceBytes) == 0);
    else {
        assert(memcmp(sb, original.data(), sourceBytes) == 0);
        assert(memcmp(db, reference.data(), destBytes) == 0);
    }
    ++cases;
}

int main()
{
    for (unsigned words : {16u, 32u, 64u, 2560u})
        for (unsigned h : {0u, 1u, 2u, 17u})
            for (unsigned so : {0u, 4u, 8u, 16u}) for (unsigned d : {0u, 4u, 8u, 16u})
                for (bool sse : {false, true}) for (bool l10r : {false, true})
                    check(words, words, words, h, so, d, sse, l10r);
    for (unsigned words : {1u, 2u, 3u, 15u, 16u, 17u, 18u, 20u, 31u, 33u, 65u})
        for (unsigned padding : {0u, 1u, 4u, 16u})
            for (unsigned h : {1u, 3u, 19u})
                for (bool sse : {false, true}) for (bool l10r : {false, true}) {
                    check(words, words, words + padding, h, 0, 0, sse, l10r);
                    check(words, words + padding, words, h, 0, 0, sse, l10r);
                }
    for (bool l10r : {false, true}) {
        check(2560, 2560, 2560, 1600, 0, 0, true, l10r);
        check(16, 16, 16, 9, 0, 0, true, l10r, true);
        check(20, 20, 20, 9, 0, 0, true, l10r, true);
    }
    printf("PASS %u production-copy cases; BGRA/l10r, packed/row/scalar, alignment, padding, guards, alias\n", cases);
}
