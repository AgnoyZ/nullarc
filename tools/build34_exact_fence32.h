// SPDX-License-Identifier: MIT
// Original R3 CPU-only decoding primitive; not a device reader.
// Caller serializes access and supplies a coherent, non-regressing, aligned
// device dword from the SAME seeded generation. This code cannot establish
// mapping coherency, packet completion ordering or GPU quiescence.
#ifndef BUILD34_EXACT_FENCE32_H
#define BUILD34_EXACT_FENCE32_H

#include <stdint.h>

namespace phx34_exact {

// The smaller widths exist only to exhaustively test wrap ambiguity. Native
// use, if admitted later, must use FenceWindow32 and a genuine 32-bit read.
template <unsigned Bits = 32> class FenceWindow {
    static_assert(Bits > 0 && Bits <= 32, "device fence width must be 1..32");
    static constexpr uint64_t modulus = uint64_t{1} << Bits;
    static constexpr uint64_t mask = modulus - 1;
    uint64_t generation_ = 0, floor_ = 0, submitted_ = 0;
    bool ready_ = false;
public:
    FenceWindow() = default;
    FenceWindow(const FenceWindow &) = delete;
    FenceWindow &operator=(const FenceWindow &) = delete;

    // Only invalidation plus a strictly newer generation permits reseeding.
    // The caller must seed the actual device fence before publishing readiness.
    bool seed(uint64_t generation, uint64_t value) {
        if (ready_ || !generation || generation == UINT64_MAX ||
            generation <= generation_ || value == UINT64_MAX) return false;
        generation_ = generation;
        floor_ = submitted_ = value;
        ready_ = true;
        return true;
    }
    void invalidate() { ready_ = false; }

    // Call before every irreversible packet write, including legacy submits
    // sharing a queue. Global sequence gaps count toward this bound as well.
    bool canSubmit(uint64_t generation, uint64_t sequence) const {
        return ready_ && generation == generation_ && sequence != UINT64_MAX &&
               sequence > submitted_ && sequence - floor_ < modulus;
    }
    bool submit(uint64_t generation, uint64_t sequence) {
        if (!canSubmit(generation, sequence)) return false;
        submitted_ = sequence;
        return true;
    }
    bool observe(uint64_t generation, uint32_t raw, uint64_t &completed) {
        if (!ready_ || generation != generation_ || uint64_t{raw} > mask) return false;
        const uint64_t distance = (uint64_t{raw} - (floor_ & mask)) & mask;
        if (distance > submitted_ - floor_) return false;
        floor_ += distance;
        completed = floor_; // output is untouched on every refusal
        return true;
    }
};
using FenceWindow32 = FenceWindow<32>;
static_assert(sizeof(FenceWindow32) <= 32, "fixed-size per-queue metadata");
} // namespace phx34_exact
#endif
