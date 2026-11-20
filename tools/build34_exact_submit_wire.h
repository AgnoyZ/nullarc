// SPDX-License-Identifier: MIT
// Source-only R3 submit experiment. Not an installed ABI or capability.
#ifndef BUILD34_EXACT_SUBMIT_WIRE_H
#define BUILD34_EXACT_SUBMIT_WIRE_H
#include "build34_exact_receipt_wire.h"
#ifndef __cplusplus
#include <assert.h> // C11 static_assert spelling used by the existing native ABI header
#endif
#include "PhxNativeABI.h"

#define PHX34_R3_SEL_SUBMIT_RECEIPT 66u
#define PHX34_R3_REPLY_SUBMITTED 3u

// Fixed inband envelope. Unused IB records and reserved words must be zero.
// A session handshake must eventually supply owner; no native handshake exists.
struct phx34_r3_submit_request {
    uint32_t version, size;
    uint64_t owner, reserved[2];
    struct phxn_cs_in submit;
    struct phxn_cs_ib ibs[PHXN_MAX_IBS];
};
#ifdef __cplusplus
#define PHX34_R3_SUBMIT_ASSERT static_assert
#else
#define PHX34_R3_SUBMIT_ASSERT _Static_assert
#endif
PHX34_R3_SUBMIT_ASSERT(sizeof(struct phx34_r3_submit_request) == 2112, "R3 submit envelope size");
PHX34_R3_SUBMIT_ASSERT(offsetof(struct phx34_r3_submit_request, owner) == 8, "R3 submit owner");
PHX34_R3_SUBMIT_ASSERT(offsetof(struct phx34_r3_submit_request, submit) == 32, "R3 submit header");
PHX34_R3_SUBMIT_ASSERT(offsetof(struct phx34_r3_submit_request, ibs) == 64, "R3 submit IBs");
#undef PHX34_R3_SUBMIT_ASSERT
#endif
