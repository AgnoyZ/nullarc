// SPDX-License-Identifier: MIT OR GPL-2.0-only
// Independent, versioned, software-only diagnostic export. No addresses or IDs.
#ifndef PHX_ALLOCATION_SNAPSHOT_H
#define PHX_ALLOCATION_SNAPSHOT_H
#include <stdint.h>

#define PHXN_SEL_ALLOCATION_SNAPSHOT 31u
#define PHXN_ALLOCATION_SNAPSHOT_VERSION 1u
#define PHXN_ALLOCATION_REASON_COUNT 7u
#define PHXN_ALLOCATION_SAMPLES 4u

enum {
    PHXN_ALLOC_MAP_PENDING = 0, PHXN_ALLOC_MAP_INVALID = 1,
    PHXN_ALLOC_UNMAP_PENDING = 2, PHXN_ALLOC_UNMAP_INVALID = 3,
    PHXN_ALLOC_MAP_OVERLAP = 4, PHXN_ALLOC_HOST_DESCRIPTOR = 5,
    PHXN_ALLOC_HOST_PREPARE = 6
};

// reason is PhxQueueObservationReason (0..14); reserved fields are zero.
struct phxn_allocation_queue {
    uint64_t done, floor, first_pending;
    uint32_t reason, fence_read, count, reserved;
};
struct phxn_allocation_record {
    uint64_t ordinal, last_seq, submitted, retired, bytes;
    uint32_t reason, status, observation_valid, reserved;
    struct phxn_allocation_queue queue[2];
};
struct phxn_allocation_snapshot {
    uint32_t version, kext_build, reason_count, samples_per_reason;
    uint64_t observed, counts[PHXN_ALLOCATION_REASON_COUNT];
    struct phxn_allocation_record records[PHXN_ALLOCATION_REASON_COUNT][PHXN_ALLOCATION_SAMPLES];
};

// in: one scalar = snapshot version; out: exactly this struct, no scalars.
// Administrator-only, allowed before Hello. No reaping, GPU access, or reset.
// Counts include internal cleanup guard calls, not unique external requests.
// First four per reason are retained for this service instance; no reboot persistence.
static_assert(sizeof(struct phxn_allocation_queue) == 40, "allocation queue wire size");
static_assert(sizeof(struct phxn_allocation_record) == 136, "allocation record wire size");
static_assert(sizeof(struct phxn_allocation_snapshot) == 3888, "allocation snapshot wire size");
#endif
