// Downstream research policy for the frame copy: which row path a copy may take, and the ARGB2101010 ->
// XRGB8888 narrowing done while copying it.
//
// These are the decisions inside the copy loop of nvrm-accel.cpp, which is the only way a frame reaches this
// panel (docs/analysis.md §1.1). Nothing here copies: the SSE and movnti routines stay in the driver, the
// caller passes addresses and strides, and the rules are pure so tests/test_copy_path.cpp can assert them on
// any host instead of only where the GPU is.
#ifndef PHX_780M_COPY_PATH_HPP
#define PHX_780M_COPY_PATH_HPP
#include <stdint.h>
namespace phx780m {
// 8-byte (two pixel) accesses need both sides 8-byte aligned and an even number of pixels per row. They matter
// because the scan-out's system-RAM view maps write-back whatever cache mode it asks for, so plain stores left
// the frame in the CPU cache while the panel scanned stale DRAM under it, in stripes (docs/analysis.md §1.3).
constexpr bool wideEligible(uintptr_t source, uintptr_t dest, unsigned source_stride, unsigned dest_stride) {
    return (((source | dest) & 7u) == 0u) && ((source_stride & 1u) == 0u) && ((dest_stride & 1u) == 0u);
}
// The 64-byte row (movntdqa reads, movntdq stores) needs 16-byte alignment on both sides and 4-pixel strides,
// and is only ever taken when debug.nvaccel_iop_sse is on. It is the fast path from a write-combined surface,
// which plain loads read at ~0.5 GB/s (docs/analysis.md §1.3).
constexpr bool sseEligible(bool enabled, uintptr_t source, uintptr_t dest, unsigned source_stride,
                           unsigned dest_stride) {
    return enabled && (((source | dest) & 15u) == 0u) && ((source_stride & 3u) == 0u) && ((dest_stride & 3u) == 0u);
}
// How many words of a row the SSE routine takes, in 16-word (64-byte) steps. The rest of the row falls to the
// pair and then the dword path; a row shorter than one step never uses SSE at all.
constexpr unsigned sseWords(unsigned words, bool sse) {
    return (sse && words >= 16u) ? (words & ~15u) : 0u;
}
// Where the pair loop resumes: whole 8-byte pairs from the SSE boundary, so an odd trailing word is left to the
// dword loop rather than copied twice.
constexpr unsigned pairResume(unsigned words, unsigned taken) {
    const unsigned edge = (words / 2u) * 2u;
    return taken < edge ? edge : taken;
}
// One pixel, ARGB2101010 -> XRGB8888: channels are A 2 bits, R 10, G 10, B 10 from the top, and the two low bits
// of each channel are dropped because the panel scans 8-bit channels while WindowServer composites 10-bit once
// colour management is up (docs/analysis.md §1.3).
constexpr uint32_t narrowWord(uint32_t value) {
    return 0xff000000u | ((value >> 6) & 0xff0000u) | ((value >> 4) & 0xff00u) | ((value >> 2) & 0xffu);
}
// Two pixels in one 64-bit load; asserted to be exactly narrowWord on each half.
constexpr uint64_t narrowPair(uint64_t value) {
    const uint64_t pixels = ((value >> 6) & 0x00ff000000ff0000ull) | ((value >> 4) & 0x0000ff000000ff00ull) |
                            ((value >> 2) & 0x000000ff000000ffull);
    return 0xff000000ff000000ull | pixels;
}
}
#endif
