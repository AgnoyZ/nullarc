// SPDX-License-Identifier: MIT OR GPL-2.0-only
// Host-testable diagnostic state only. No addresses, retries or completion policy.
#pragma once
#include <stdint.h>
#include "PhxAllocationSnapshot.h"

static constexpr uint8_t kPhxAllocationDiagnosticLimit = 4;
static inline bool phxAllocationDiagnosticSample(uint8_t &count) {
    if (count >= kPhxAllocationDiagnosticLimit) return false;
    ++count;
    return true;
}

enum class PhxQueueObservationReason : uint32_t {
    Unobserved = 0, Valid = 1, MissingOutput = 2, NoAperture = 3, Inactive = 4, UnalignedFence = 5,
    HistoryOverflow = 6, FutureFloor = 7, AllOnesFence = 8, RegressedFence = 9, FutureFence = 10,
    ZeroSequence = 11, NonmonotonicSequence = 12, FutureSequence = 13, UnknownFence = 14
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

// Caller serializes all access with the existing service GPU lock. This store
// never touches hardware, allocates memory, resets, or overwrites early samples.
static inline void phxAllocationIncrement(uint64_t &count) {
    if (count != UINT64_MAX) ++count;
}

class PhxAllocationHistory {
    phxn_allocation_snapshot state{};
public:
    void record(const phxn_allocation_record &record) {
        if (record.reason >= PHXN_ALLOCATION_REASON_COUNT) return;
        phxAllocationIncrement(state.observed);
        uint64_t &count = state.counts[record.reason];
        if (count < PHXN_ALLOCATION_SAMPLES) {
            phxn_allocation_record &slot = state.records[record.reason][count];
            slot = record;
            slot.ordinal = state.observed;
        }
        phxAllocationIncrement(count);
    }
    void copy(phxn_allocation_snapshot *out, uint32_t build) const {
        *out = state;
        out->version = PHXN_ALLOCATION_SNAPSHOT_VERSION;
        out->kext_build = build;
        out->reason_count = PHXN_ALLOCATION_REASON_COUNT;
        out->samples_per_reason = PHXN_ALLOCATION_SAMPLES;
    }
};

static inline phxn_allocation_record phxAllocationRefusal(uint32_t reason, uint32_t status, uint64_t bytes) {
    phxn_allocation_record record{};
    record.reason = reason; record.status = status; record.bytes = bytes;
    return record;
}

static inline phxn_allocation_record phxAllocationRetirement(uint32_t reason, uint32_t status,
        uint64_t last, uint64_t retired, const PhxRetirementObservation &observation) {
    auto record = phxAllocationRefusal(reason, status, 0);
    record.last_seq = last; record.submitted = observation.submitted;
    record.retired = retired; record.observation_valid = observation.valid;
    for (uint32_t i = 0; i < 2; ++i) {
        const PhxQueueObservation &q = observation.queue[i];
        record.queue[i] = {q.done, q.floor, q.firstPending,
            static_cast<uint32_t>(q.reason), static_cast<uint32_t>(q.fenceRead), q.count, 0};
    }
    return record;
}
