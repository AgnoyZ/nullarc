// SPDX-License-Identifier: MIT
#ifndef BUILD34_EXACT_PROGRESS_WIRE_H
#define BUILD34_EXACT_PROGRESS_WIRE_H

#include "build34_exact_receipt_wire.h"

#define PHX34_R3_SEL_PREFIX 67u
#define PHX34_R3_SEL_SESSION 68u
#define PHX34_R3_PROGRESS_BUILD 34u
#define PHX34_R3_CAP_EXACT_RECEIPTS (1u << 0)
#define PHX34_R3_CAP_CHECKED_PREFIX (1u << 1)
#define PHX34_R3_PROGRESS_FLAGS (PHX34_R3_CAP_EXACT_RECEIPTS | PHX34_R3_CAP_CHECKED_PREFIX)

struct phx34_r3_progress_request {
    uint32_t version, size;
    uint64_t owner, target, timeout_ns;
};

struct phx34_r3_progress_reply {
    uint32_t version, size, build, flags;
    uint64_t owner, target, retired, reserved;
};

#ifdef __cplusplus
#define PHX34_R3_PROGRESS_ASSERT static_assert
#else
#define PHX34_R3_PROGRESS_ASSERT _Static_assert
#endif
PHX34_R3_PROGRESS_ASSERT(sizeof(struct phx34_r3_progress_request) == 32, "R3 progress request size");
PHX34_R3_PROGRESS_ASSERT(offsetof(struct phx34_r3_progress_request, owner) == 8, "R3 progress request owner");
PHX34_R3_PROGRESS_ASSERT(offsetof(struct phx34_r3_progress_request, timeout_ns) == 24, "R3 progress request timeout");
PHX34_R3_PROGRESS_ASSERT(sizeof(struct phx34_r3_progress_reply) == 48, "R3 progress reply size");
PHX34_R3_PROGRESS_ASSERT(offsetof(struct phx34_r3_progress_reply, owner) == 16, "R3 progress reply owner");
PHX34_R3_PROGRESS_ASSERT(offsetof(struct phx34_r3_progress_reply, retired) == 32, "R3 progress reply prefix");
#undef PHX34_R3_PROGRESS_ASSERT
#endif
