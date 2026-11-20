// SPDX-License-Identifier: MIT
// Experimental R3 source-only receipt operations, not an installed native ABI.
// No capability/session admission or production client requests these methods.
// Neither success nor ACK authorizes native BO/VMID release. No prefix is
// returned: a separately admitted global visibility/snapshot protocol is needed.
#ifndef BUILD34_EXACT_RECEIPT_WIRE_H
#define BUILD34_EXACT_RECEIPT_WIRE_H
#include <stddef.h>
#include <stdint.h>

#if !defined(__BYTE_ORDER__) || __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error Experimental R3 receipt wire requires a little-endian host
#endif

#define PHX34_R3_WIRE_VERSION 1u
#define PHX34_R3_SEL_WAIT_RECEIPT 64u
#define PHX34_R3_SEL_ACK_RECEIPT 65u
#define PHX34_R3_REPLY_COMPLETE 0u
#define PHX34_R3_REPLY_PENDING 1u
#define PHX34_R3_REPLY_ACKED 2u

struct phx34_r3_request {
    uint32_t version, size;
    uint64_t owner, serial, sequence, generation;
    uint32_t slot, queue;
    uint64_t timeout_ns, reserved;
};
struct phx34_r3_reply {
    uint32_t version, size, status, reserved0;
    uint64_t owner, serial, sequence, generation;
    uint32_t slot, queue;
    uint64_t reserved;
};
#ifdef __cplusplus
#define PHX34_R3_ASSERT static_assert
#else
#define PHX34_R3_ASSERT _Static_assert
#endif
PHX34_R3_ASSERT(sizeof(struct phx34_r3_request) == 64, "R3 request size");
PHX34_R3_ASSERT(offsetof(struct phx34_r3_request, owner) == 8, "R3 owner offset");
PHX34_R3_ASSERT(offsetof(struct phx34_r3_request, slot) == 40, "R3 slot offset");
PHX34_R3_ASSERT(offsetof(struct phx34_r3_request, timeout_ns) == 48, "R3 timeout offset");
PHX34_R3_ASSERT(sizeof(struct phx34_r3_reply) == 64, "R3 reply size");
PHX34_R3_ASSERT(offsetof(struct phx34_r3_reply, owner) == 16, "R3 reply owner offset");
PHX34_R3_ASSERT(offsetof(struct phx34_r3_reply, slot) == 48, "R3 reply slot offset");
#undef PHX34_R3_ASSERT
#endif
