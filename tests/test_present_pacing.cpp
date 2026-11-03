// Asserts the present-pacing policy the display path uses (src/phxaccel/PhxPresentPacing.hpp).
//
// This is policy, not hardware: it proves the decision rules, and nothing about a frame reaching a panel.
// The gap buckets are compared against the inline expression they replaced, including odd refresh periods
// where floor(3 * refresh / 2) is not 1.5 * refresh, so a capture stays comparable with earlier ones.
#include "PhxPresentPacing.hpp"
#include <cassert>
#include <cstdio>

namespace {
using phx780m::CopyHold;
using phx780m::PresentCompletion;

void completion_tests() {
    const uint64_t frame = 8333333;   // one 120 Hz refresh in mach_absolute_time ticks, for scale only
    // Unpaced sessions, an unknown refresh, or no tick to wait for: complete at once, as before.
    assert(phx780m::presentCompletion(false, true, true, false, 0, frame) == PresentCompletion::Complete);
    assert(phx780m::presentCompletion(true, false, true, false, 0, 0) == PresentCompletion::Complete);
    assert(phx780m::presentCompletion(true, true, false, false, 0, frame) == PresentCompletion::Complete);
    // The tick arrived: complete, and the caller clears its wait state.
    assert(phx780m::presentCompletion(true, true, true, true, 0, frame) == PresentCompletion::Complete);
    assert(phx780m::presentCompletion(true, true, true, true, 100 * frame, frame) == PresentCompletion::Complete);
    // The tick has not arrived yet: wait, until two refreshes have passed without one.
    assert(phx780m::presentCompletion(true, true, true, false, 0, frame) == PresentCompletion::WaitForTick);
    assert(phx780m::presentCompletion(true, true, true, false, frame, frame) == PresentCompletion::WaitForTick);
    assert(phx780m::presentCompletion(true, true, true, false, 2 * frame, frame) == PresentCompletion::WaitForTick);
    assert(phx780m::presentCompletion(true, true, true, false, 2 * frame + 1, frame) == PresentCompletion::CompleteLate);
    assert(phx780m::presentCompletion(true, true, true, false, 200 * frame, frame) == PresentCompletion::CompleteLate);
    // An unmeasurable refresh cannot judge lateness, so the frame waits rather than being declared late.
    assert(phx780m::presentCompletion(true, true, true, false, phx780m::kMaxTick, phx780m::kMaxTick)
           == PresentCompletion::WaitForTick);
}

void gap_bucket_tests() {
    // Exactly the expression nvrm-accel.cpp used inline: g < refresh * 3 / 2 -> 0, < 5 / 2 -> 1, < 7 / 2 -> 2.
    auto inline_bucket = [](uint64_t gap, uint64_t refresh) -> unsigned {
        if (gap < refresh * 3 / 2) return 0;
        if (gap < refresh * 5 / 2) return 1;
        if (gap < refresh * 7 / 2) return 2;
        return 3;
    };
    for (uint64_t refresh = 1; refresh <= 64; ++refresh) {
        for (uint64_t gap = 0; gap <= 8 * refresh + 2; ++gap) {
            assert(phx780m::iopGapBucket(gap, refresh) == inline_bucket(gap, refresh));
        }
    }
    // Odd periods are the ones a naive "half a refresh" test gets wrong.
    // With a five-tick refresh the boundaries are 15 / 2 == 7, 25 / 2 == 12 and 35 / 2 == 17.
    assert(phx780m::iopGapBucket(6, 5) == 0);
    assert(phx780m::iopGapBucket(7, 5) == 1);
    assert(phx780m::iopGapBucket(9, 5) == 1);
    assert(phx780m::iopGapBucket(11, 5) == 1);
    assert(phx780m::iopGapBucket(12, 5) == 2);
    assert(phx780m::iopGapBucket(16, 5) == 2);
    assert(phx780m::iopGapBucket(17, 5) == 3);
    // A real frame period, near 8.33 ms in mach ticks.
    const uint64_t frame = 8333333;
    assert(phx780m::iopGapBucket(frame, frame) == 0);
    assert(phx780m::iopGapBucket(2 * frame, frame) == 1);
    assert(phx780m::iopGapBucket(3 * frame, frame) == 2);
    assert(phx780m::iopGapBucket(4 * frame, frame) == 3);
    assert(phx780m::iopGapBucket(phx780m::kMaxTick, frame) == 3);
    // Unmeasurable periods: no bucket to report, the caller counts an idle gap.
    assert(phx780m::iopGapBucket(1000, 0) == 3);
    assert(phx780m::iopGapBucket(phx780m::kMaxTick, phx780m::kMaxTick) == 3);
    // Monotone in the gap for a fixed period: a longer gap never lands in an earlier bucket.
    for (uint64_t refresh = 1; refresh <= 32; ++refresh) {
        unsigned previous = 0;
        for (uint64_t gap = 0; gap <= 6 * refresh; ++gap) {
            const unsigned bucket = phx780m::iopGapBucket(gap, refresh);
            assert(bucket >= previous);
            previous = bucket;
        }
    }
}

void copy_hold_tests() {
    // Four consecutive holds, then the frame is copied regardless: a surface that never syncs must not
    // freeze the panel.
    CopyHold hold = phx780m::nextCopyHold(0, false);
    for (unsigned held = 1; held <= phx780m::kCopyHoldLimit; ++held) {
        assert(hold.held == held);
        assert(!hold.copy);
        hold = phx780m::nextCopyHold(hold.held, false);
    }
    assert(hold.copy);
    assert(hold.held == 0);
    // Ready resets the counter without a copy penalty.
    const CopyHold ready = phx780m::nextCopyHold(3, true);
    assert(ready.copy);
    assert(ready.held == 0);
    // The counter never climbs past the limit however often it is polled.
    unsigned state = 0;
    for (int poll = 0; poll < 100; ++poll) {
        const CopyHold step = phx780m::nextCopyHold(state, false);
        assert(step.held <= phx780m::kCopyHoldLimit);
        state = step.held;
    }
    // A degenerate counter value still yields a copy rather than an unbounded wait.
    assert(phx780m::nextCopyHold(phx780m::kCopyHoldLimit + 10, false).copy);
}
}

int main() {
    completion_tests();
    gap_bucket_tests();
    copy_hold_tests();
    std::printf("present pacing policy: completion, gap buckets and copy holds agree with the driver's rules\n");
    return 0;
}
