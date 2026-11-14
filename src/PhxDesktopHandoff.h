/* SPDX-License-Identifier: MIT OR GPL-2.0-only
 * One provider-lifetime desktop bootstrap reservation. No reset/release operation.
 */
#ifndef PHX_DESKTOP_HANDOFF_H
#define PHX_DESKTOP_HANDOFF_H
#include "PhxMesQueueLayout.h"
#define PHX_DESKTOP_SELECTOR 117u
#define PHX_DESKTOP_VERSION 1ull
#define PHX_DESKTOP_RESERVE 1ull
#define PHX_DESKTOP_SEAL 2ull
#define PHX_DESKTOP_CLAIM 3ull
#define PHX_DESKTOP_COMPUTE_BYTES 0x6000ull
#define PHX_DESKTOP_GRAPHICS_BYTES 0x8000ull
#define PHX_DESKTOP_CSB_DWORDS 960u
#define PHX_DESKTOP_COMPUTE_WPTR 16ull
#define PHX_DESKTOP_GRAPHICS_WPTR (PHX_DESKTOP_CSB_DWORDS + 16ull)
#define PHX_DESKTOP_COMPUTE_TOKEN 0x7800c00100000001ull
#define PHX_DESKTOP_GRAPHICS_TOKEN 0x7800f00100000001ull
struct PhxDesktopLayout {
    uint64_t version;
    struct PhxGartLayout gart;
    struct PhxMesQueueLayout kiq, scheduler, compute, graphics;
};
struct PhxDesktopRequest {
    uint64_t operation;
    struct PhxDesktopLayout layout;
    uint64_t computeWptr, graphicsWptr;
};
static inline int phxDesktopInputsValid(const struct PhxDesktopLayout *layout) {
    if (!layout || layout->version != PHX_DESKTOP_VERSION || !phxGartInputsValid(&layout->gart)) return 0;
    const struct PhxMesQueueLayout *queues[] = {&layout->kiq, &layout->scheduler, &layout->compute, &layout->graphics};
    for (unsigned i = 0; i < 4; ++i) {
        if (!phxMesQueueInputsValid(queues[i])) return 0;
        for (unsigned j = 0; j < i; ++j)
            if (queues[i]->doorbellIndex == queues[j]->doorbellIndex) return 0;
    }
    /* The graphics helper programs the existing CP_RB upper range, in bytes. */
    if (layout->graphics.doorbellIndex < 0x116ull || layout->graphics.doorbellIndex * 4 > 0x7f8ull) return 0;
    for (unsigned i = 0; i < 3; ++i)
        if (queues[i]->doorbellIndex >= layout->graphics.doorbellIndex) return 0;
    return 1;
}
static inline int phxDesktopLayoutValid(const struct PhxDesktopLayout *layout, const struct PhxBootMemory *memory) {
    if (!phxDesktopInputsValid(layout)) return 0;
    const struct PhxMesQueueLayout *queues[] = {&layout->kiq, &layout->scheduler, &layout->compute, &layout->graphics};
    const uint64_t sizes[] = {PHX_MES_QUEUE_ARENA_BYTES, PHX_MES_QUEUE_ARENA_BYTES,
                            PHX_DESKTOP_COMPUTE_BYTES, PHX_DESKTOP_GRAPHICS_BYTES};
    for (unsigned i = 0; i < 4; ++i) {
        if (!phxMesArenaLayoutValid(queues[i], &layout->gart, memory, sizes[i])) return 0;
        for (unsigned j = 0; j < i; ++j)
            if (!phxPspDisjoint(queues[i]->arenaOffset, sizes[i], queues[j]->arenaOffset, sizes[j])) return 0;
    }
    return 1;
}
/* Only the debug mutation lane is serialized; passive readers/normal submits are unchanged. */
static inline int phxDesktopMutationSelector(uint32_t selector) {
    return selector == 100 || selector == 101 || (selector >= 103 && selector <= 115) ||
           selector == PHX_DESKTOP_SELECTOR;
}
static inline int phxDesktopInitializerSelector(uint32_t selector) {
    return selector == 108 || selector == 109 || selector == 110;
}
#if defined(__cplusplus)
static_assert(sizeof(PhxDesktopLayout) == 144, "Desktop layout wire size");
static_assert(sizeof(PhxDesktopRequest) == 168, "Desktop request wire size");
#else
_Static_assert(sizeof(struct PhxDesktopLayout) == 144, "Desktop layout wire size");
_Static_assert(sizeof(struct PhxDesktopRequest) == 168, "Desktop request wire size");
#endif
#endif
