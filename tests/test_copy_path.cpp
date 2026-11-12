// Asserts the copy path's selection rules and its ARGB2101010 -> XRGB8888 narrowing
// (src/phxaccel/PhxCopyPath.hpp).
//
// Policy, not hardware: this proves which row path a copy would take and what bits the narrowing produces. It
// cannot prove a frame reaches the panel, and it does not run the SSE or movnti routines. The selection rules
// are compared against the inline expressions they replaced, and the narrowing against the documented bit
// layout of ARGB2101010.
#include "PhxCopyPath.hpp"
#include <cassert>
#include <cstdio>
#include <initializer_list>

namespace {
// The expressions the driver used before the extraction, kept here as the reference.
bool inline_wide(uintptr_t source, uintptr_t dest, unsigned source_stride, unsigned dest_stride) {
    return (((source | dest) & 7) == 0) && !(source_stride & 1) && !(dest_stride & 1);
}
bool inline_sse(bool enabled, uintptr_t source, uintptr_t dest, unsigned source_stride, unsigned dest_stride) {
    return enabled && (((source | dest) & 15) == 0) && !(source_stride & 3) && !(dest_stride & 3);
}

void selection_tests() {
    // Every alignment and stride combination in a row's first bytes, against the expressions being replaced.
    for (uintptr_t source = 0; source <= 24; ++source) {
        for (uintptr_t dest = 0; dest <= 24; ++dest) {
            for (unsigned source_stride = 1; source_stride <= 6; ++source_stride) {
                for (unsigned dest_stride = 1; dest_stride <= 6; ++dest_stride) {
                    assert(phx780m::wideEligible(source, dest, source_stride, dest_stride) ==
                           inline_wide(source, dest, source_stride, dest_stride));
                    for (bool enabled : {false, true}) {
                        assert(phx780m::sseEligible(enabled, source, dest, source_stride, dest_stride) ==
                               inline_sse(enabled, source, dest, source_stride, dest_stride));
                    }
                }
            }
        }
    }
    // The cases that matter on this hardware: a 2560-pixel row, both sides 16-byte aligned, SSE on.
    assert(phx780m::wideEligible(0x1000, 0x2000, 2560, 2560));
    assert(phx780m::sseEligible(true, 0x1000, 0x2000, 2560, 2560));
    // SSE is a switch, not a property of the addresses: debug.nvaccel_iop_sse defaults to 0.
    assert(!phx780m::sseEligible(false, 0x1000, 0x2000, 2560, 2560));
    // A destination eight bytes off 16-byte alignment keeps the pair path but loses the 64-byte one.
    assert(phx780m::wideEligible(0x1000, 0x2008, 2560, 2560));
    assert(!phx780m::sseEligible(true, 0x1000, 0x2008, 2560, 2560));
    // Four bytes off loses both: the movnti path wants 8-byte alignment.
    assert(!phx780m::wideEligible(0x1000, 0x2004, 2560, 2560));
    assert(!phx780m::sseEligible(true, 0x1000, 0x2004, 2560, 2560));
    // An odd destination stride keeps neither.
    assert(!phx780m::wideEligible(0x1000, 0x2000, 2560, 2559));
    assert(!phx780m::sseEligible(true, 0x1000, 0x2000, 2560, 2559));
}

void row_split_tests() {
    assert(phx780m::visibleRowFits(2560, 10240));
    assert(phx780m::visibleRowFits(2560, 10496));
    assert(!phx780m::visibleRowFits(2560, 10236));
    assert(!phx780m::visibleRowFits(2560, 10241));
    assert(!phx780m::visibleRowFits(0, 10240));
    assert(phx780m::packedSseBytes(true, 2560, 1600, 2560, 2560) == 16384000u);
    assert(!phx780m::packedSseBytes(false, 2560, 1600, 2560, 2560));
    assert(!phx780m::packedSseBytes(true, 2560, 1600, 2624, 2560));
    assert(!phx780m::packedSseBytes(true, 2560, 1600, 2560, 2624));
    assert(!phx780m::packedSseBytes(true, 1, 1, 1, 1));
    assert(!phx780m::packedSseBytes(true, 16, 0, 16, 16));
    assert(!phx780m::packedSseBytes(true, ~0u, ~0u, ~0u, ~0u));
    // The SSE routine takes whole 64-byte steps and hands the rest on; a short row never uses it.
    for (unsigned words = 0; words <= 80; ++words) {
        for (bool sse : {false, true}) {
            const unsigned expected = (sse && words >= 16) ? (words & ~15u) : 0u;
            assert(phx780m::sseWords(words, sse) == expected);
            assert(phx780m::sseWords(words, sse) <= words);
            assert(phx780m::sseWords(words, sse) % 16 == 0);
        }
    }
    assert(phx780m::sseWords(15, true) == 0);
    assert(phx780m::sseWords(16, true) == 16);
    assert(phx780m::sseWords(31, true) == 16);
    assert(phx780m::sseWords(2560, true) == 2560);
    assert(phx780m::sseWords(2559, true) == 2544);
    // The pair loop resumes on an even word and leaves an odd trailing word to the dword loop.
    for (unsigned words = 0; words <= 40; ++words) {
        for (unsigned taken = 0; taken <= words; taken += 1) {
            unsigned expected = taken;
            const unsigned edge = (words / 2) * 2;
            if (expected < edge) expected = edge;
            assert(phx780m::pairResume(words, taken) == expected);
            assert(phx780m::pairResume(words, taken) <= words);
        }
    }
    // A row of 2560 words with SSE: 2560 taken, nothing left; 2559: 2544 taken, the pair loop resumes to 2558.
    assert(phx780m::pairResume(2560, 2560) == 2560);
    assert(phx780m::pairResume(2559, 2544) == 2558);
    assert(phx780m::pairResume(1, 0) == 0);
}

void narrowing_tests() {
    // ARGB2101010: A 2 bits at 31:30, R 10 at 29:20, G 10 at 19:10, B 10 at 9:0. Each 10-bit channel keeps its
    // top 8 bits, and the result is opaque XRGB8888 in little-endian order (B, G, R, X).
    const unsigned shifts[3] = {0u, 10u, 20u};   // B, G, R
    const uint32_t masks[3] = {0x000000ffu, 0x0000ff00u, 0x00ff0000u};
    for (unsigned channel = 0; channel < 3; ++channel) {
        unsigned previous = 0;
        for (unsigned value = 0; value < 1024; ++value) {
            const uint32_t word = (value << shifts[channel]);
            const uint32_t out = phx780m::narrowWord(static_cast<uint32_t>(word));
            assert(((out >> 24) & 0xffu) == 0xffu);                       // opaque
            assert(((out & ~0xff000000u) & ~masks[channel]) == 0u);        // only this channel is set
            assert((out & masks[channel]) >> (8 * channel) == (value >> 2));
            assert((out & masks[channel]) >> (8 * channel) >= previous);   // monotone in the channel
            previous = (out & masks[channel]) >> (8 * channel);
        }
    }
    // The two dropped bits are exactly that.
    assert(phx780m::narrowWord(0x3ffu) == phx780m::narrowWord(0x3fcu));
    assert(phx780m::narrowWord(0x000u) == 0xff000000u);
    // A fully specified pixel: B = 0x3ff, G = 0x200, R = 0x155, A = 3.
    const uint32_t pixel = 0xc0000000u | (0x155u << 20) | (0x200u << 10) | 0x3ffu;
    assert(phx780m::narrowWord(pixel) == 0xff5580ffu);   // R 0x155 >> 2 = 0x55, G 0x200 >> 2 = 0x80, B = 0xff
    // Two pixels in one 64-bit load are exactly two single-pixel conversions.
    for (unsigned low = 0; low < 1024; low += 37) {
        for (unsigned high = 0; high < 1024; high += 41) {
            const uint64_t pair = (static_cast<uint64_t>(high << 20) << 32) | (low << 20);
            const uint64_t expected = static_cast<uint64_t>(phx780m::narrowWord(low << 20)) |
                                      (static_cast<uint64_t>(phx780m::narrowWord(high << 20)) << 32);
            assert(phx780m::narrowPair(pair) == expected);
        }
    }
    // Arbitrary bits, including alpha and the dropped low bits, still agree with the per-pixel conversion.
    uint64_t seed = 0x0123456789abcdefull;
    for (int round = 0; round < 4096; ++round) {
        seed = seed * 6364136223846793005ull + 1442695040888963407ull;
        const uint32_t low = static_cast<uint32_t>(seed);
        const uint32_t high = static_cast<uint32_t>(seed >> 32);
        const uint64_t pair = (static_cast<uint64_t>(high) << 32) | low;
        const uint64_t expected = static_cast<uint64_t>(phx780m::narrowWord(low)) |
                                  (static_cast<uint64_t>(phx780m::narrowWord(high)) << 32);
        assert(phx780m::narrowPair(pair) == expected);
    }
    assert(phx780m::narrowPair(0) == 0xff000000ff000000ull);
}

// The damage-only copy walks a row in 64-byte groups and stores only the ones that changed. What must hold without
// hardware: the groups tile a row exactly once in order, and the shape rules drop a shadow whenever the scan-out
// it describes has changed under it.
void damage_tests() {
    assert(phx780m::kDamageGroupWords == 16u);   // 64 bytes: one cache line, the unit the comparison reads in
    for (unsigned words = 1; words <= 600; ++words) {
        unsigned covered = 0;
        for (unsigned group = 0; group < phx780m::groupCount(words); ++group) {
            const unsigned n = phx780m::groupWords(words, group);
            assert(n > 0);
            assert(n <= phx780m::kDamageGroupWords);
            covered += n;
        }
        assert(covered == words);
    }
    // 2560 pixels is the panel: 160 whole groups, no tail.
    assert(phx780m::groupCount(2560) == 160);
    assert(phx780m::groupWords(2560, 0) == 16);
    assert(phx780m::groupWords(2560, 159) == 16);
    // 1080-wide and an odd width both end on a short group, never on an empty or over-long one.
    assert(phx780m::groupCount(1080) == 68);
    assert(phx780m::groupWords(1080, 67) == 8);
    assert(phx780m::groupCount(17) == 2 && phx780m::groupWords(17, 1) == 1);
    assert(phx780m::groupCount(16) == 1 && phx780m::groupWords(16, 0) == 16);
    assert(phx780m::groupWords(16, 1) == 0);   // past the end: the loop never asks, this proves asking is safe
    // 8-byte pairs only at an 8-byte-aligned destination word, exactly as the full copy's pair loop decides.
    for (uintptr_t address = 0; address <= 32; address += 4) {
        assert(phx780m::pairStoreEligible(address) == ((address & 7) == 0));
    }
    // A shadow describes one scan-out: a new destination, geometry, stride or format must invalidate it.
    const phx780m::CopyShape base{reinterpret_cast<const void *>(uintptr_t(0x2000)), 2560, 1600, 2560, false};
    assert(phx780m::sameShape(base, base));
    phx780m::CopyShape other = base;
    other.dest = reinterpret_cast<const void *>(uintptr_t(0x3000));
    assert(!phx780m::sameShape(base, other));
    other = base;
    other.words = 1920;
    assert(!phx780m::sameShape(base, other));
    other = base;
    other.rows = 1200;
    assert(!phx780m::sameShape(base, other));
    other = base;
    other.destStride = 2688;
    assert(!phx780m::sameShape(base, other));
    other = base;
    other.narrows = true;
    assert(!phx780m::sameShape(base, other));
}
}

int main() {
    selection_tests();
    row_split_tests();
    narrowing_tests();
    damage_tests();
    std::printf("copy path policy: row selection, row split, ARGB2101010 narrowing and the damage-only group walk "
                "agree with the driver\n");
    return 0;
}
