/* SPDX-License-Identifier: MIT OR GPL-2.0-only
 * Experimental compute-ring visibility prefix. Hardware acceptance is pending.
 * Independently encoded from the GFX11 ACQUIRE_MEM fields reviewed in Linux
 * v6.12 (adc218676eef25575469234709c2d87185ca223a), gfx_v11_0_emit_mem_sync.
 * This packet precedes the first INDIRECT_BUFFER, outside user command memory.
 */
#ifndef PHX_IB_FETCH_SYNC_H
#define PHX_IB_FETCH_SYNC_H
#include <stdint.h>
#ifndef PHX_IB_FETCH_SYNC
#define PHX_IB_FETCH_SYNC 1
#endif
#if PHX_IB_FETCH_SYNC != 0 && PHX_IB_FETCH_SYNC != 1
#error "PHX_IB_FETCH_SYNC must be 0 or 1"
#endif
static constexpr uint32_t phxIbFetchSyncPacket[] = {
    0xc0065800u, 0, 0xffffffffu, 0x00ffffffu, 0, 0, 10, 0xc3b1u
};
static constexpr uint32_t phxIbFetchSyncDwords = sizeof(phxIbFetchSyncPacket) / sizeof(uint32_t);
static_assert(phxIbFetchSyncDwords == 8, "complete GFX11 ACQUIRE_MEM packet");
#endif
