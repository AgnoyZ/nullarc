// Downstream research policy for the display path's present pacing.
//
// The rules here decide when a copied frame is reported complete, how its arrival is bucketed against the
// panel's refresh, and when a surface that never becomes copy-ready is copied anyway. They are pure: the
// caller supplies clock readings and counter values, so the rules can be asserted on any host
// (tests/test_present_pacing.cpp, run by CI) instead of only where the GPU is. No IOKit, no registers, no
// timing side effects, and no change to what the driver does: nvrm-accel.cpp calls these in place of the
// inline expressions it used to carry, which is what makes them checkable.
#ifndef PHX_780M_PRESENT_PACING_HPP
#define PHX_780M_PRESENT_PACING_HPP
#include <stdint.h>
namespace phx780m {
constexpr uint64_t kMaxTick = ~static_cast<uint64_t>(0);
// A panel refresh and a present gap are mach_absolute_time values: a few million ticks. Anything past a
// quarter of the counter's range is not a frame period, and the comparisons below would overflow on it.
constexpr bool tickMeasurable(uint64_t refresh) { return refresh != 0 && refresh <= kMaxTick / 4; }
// A copied frame completes on the VBL tick after it was copied, as a flip latches at the next vblank.
// Completed at once, WindowServer presented twice inside one refresh whenever an app's update came between
// its own ticks and then skipped the next: frames 3-4 ms apart followed by 12-16 ms gaps, 97 presents a
// second on a 120 Hz panel (2026-10-21). A pending frame whose tick never arrives completes anyway past two
// refreshes, so a broken tick cannot freeze the desktop (docs/analysis.md §1.4).
enum class PresentCompletion { Complete, CompleteLate, WaitForTick };
constexpr PresentCompletion presentCompletion(bool paced, bool refreshKnown, bool tickPending,
                                              bool tickArrived, uint64_t waited, uint64_t refresh) {
    if (!paced || !refreshKnown || !tickPending) return PresentCompletion::Complete;
    if (tickArrived) return PresentCompletion::Complete;
    if (tickMeasurable(refresh) && waited > 2 * refresh) return PresentCompletion::CompleteLate;
    return PresentCompletion::WaitForTick;
}
// Which present-cadence bucket a copied frame belongs to, counted in refreshes since the previous copied
// frame: below 1.5 refreshes is "about one refresh after the previous frame", below 2.5 "two", below 3.5
// "three", else "four or more, idle" (debug.nvaccel_iop_gap1 ... gap4). The boundaries are the integer ones
// the inline expression used -- gap < refresh * 3 / 2 -- so a capture stays comparable with earlier ones:
// floor(3 * refresh / 2) == refresh + refresh / 2.
constexpr unsigned iopGapBucket(uint64_t gap, uint64_t refresh) {
    if (!tickMeasurable(refresh)) return 3u;
    const uint64_t half = refresh / 2;
    if (gap < refresh) return 0u;
    if (gap - refresh < half) return 0u;
    if (gap < 2 * refresh) return 1u;
    if (gap - 2 * refresh < half) return 1u;
    if (gap < 3 * refresh) return 2u;
    if (gap - 3 * refresh < half) return 2u;
    return 3u;
}
// A surface that never becomes copy-ready is copied anyway after this many consecutive holds per head, so a
// page-off that never completes cannot freeze the panel; that frame shows stale pixels, the lesser failure.
// Counted from the caller's per-head counter, which nextCopyHold returns the new value of (docs/analysis.md
// §1.4, §5 H4).
constexpr unsigned kCopyHoldLimit = 4;
struct CopyHold { unsigned held; bool copy; };
constexpr CopyHold nextCopyHold(unsigned held, bool ready) {
    if (ready) return CopyHold{0u, true};
    if (held + 1u > kCopyHoldLimit) return CopyHold{0u, true};
    return CopyHold{held + 1u, false};
}
}
#endif
