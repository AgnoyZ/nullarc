// SPDX-License-Identifier: MIT OR GPL-2.0-only
// Host-testable diagnostic state only. No addresses, retries or completion policy.
#pragma once
#include <stdint.h>

static constexpr uint8_t kPhxAllocationDiagnosticLimit = 4;
static inline bool phxAllocationDiagnosticSample(uint8_t &count) {
    if (count >= kPhxAllocationDiagnosticLimit) return false;
    ++count;
    return true;
}

enum class PhxQueueObservationReason : uint32_t {
    Unobserved, Valid, MissingOutput, NoAperture, Inactive, UnalignedFence,
    HistoryOverflow, FutureFloor, AllOnesFence, RegressedFence, FutureFence,
    ZeroSequence, NonmonotonicSequence, FutureSequence, UnknownFence
};

static inline const char *phxQueueObservationName(PhxQueueObservationReason reason) {
    switch (reason) {
    case PhxQueueObservationReason::Unobserved: return "unobserved";
    case PhxQueueObservationReason::Valid: return "valid";
    case PhxQueueObservationReason::MissingOutput: return "missing-output";
    case PhxQueueObservationReason::NoAperture: return "no-aperture";
    case PhxQueueObservationReason::Inactive: return "inactive";
    case PhxQueueObservationReason::UnalignedFence: return "unaligned-fence";
    case PhxQueueObservationReason::HistoryOverflow: return "history-overflow";
    case PhxQueueObservationReason::FutureFloor: return "future-floor";
    case PhxQueueObservationReason::AllOnesFence: return "all-ones-fence";
    case PhxQueueObservationReason::RegressedFence: return "regressed-fence";
    case PhxQueueObservationReason::FutureFence: return "future-fence";
    case PhxQueueObservationReason::ZeroSequence: return "zero-sequence";
    case PhxQueueObservationReason::NonmonotonicSequence: return "nonmonotonic-sequence";
    case PhxQueueObservationReason::FutureSequence: return "future-sequence";
    case PhxQueueObservationReason::UnknownFence: return "unknown-fence";
    }
    return "unknown-reason";
}

struct PhxQueueObservation {
    PhxQueueObservationReason reason{};
    bool fenceRead{};
    uint64_t done{}, floor{}, firstPending{};
    uint32_t count{};
};

struct PhxRetirementObservation {
    PhxQueueObservation queue[2]{};
    uint64_t submitted{};
    bool valid{};
};
