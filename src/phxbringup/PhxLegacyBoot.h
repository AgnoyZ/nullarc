/* SPDX-License-Identifier: MIT OR GPL-2.0-only
 * Explicit legacy-tool compatibility. Numeric validation is not a memory reservation.
 */
#ifndef PHX_LEGACY_BOOT_H
#define PHX_LEGACY_BOOT_H
#include "PhxPspLayout.h"

#define PHX_LEGACY_BOOT_VERSION 1ull
#define PHX_LEGACY_BOOT_RAW_PSP 1ull
#define PHX_LEGACY_BOOT_PROPERTY "phx-legacy-boot"

struct PhxLegacyBoot {
    uint64_t version;
    uint64_t flags;
    uint64_t mcBase;
    uint64_t physicalBase;
    uint64_t vramBytes;
    uint64_t apertureBytes;
    uint64_t consoleOffset;
    uint64_t consoleBytes;
    struct PhxPspLayout psp;
};

static inline int phxLegacyBootValid(const struct PhxLegacyBoot *p, uint64_t mcBase,
                                    uint64_t physicalBase, uint64_t vramBytes, uint64_t apertureBytes) {
    if (!p || p->version != PHX_LEGACY_BOOT_VERSION || p->flags != PHX_LEGACY_BOOT_RAW_PSP ||
        p->mcBase != mcBase || p->physicalBase != physicalBase ||
        p->vramBytes != vramBytes || p->apertureBytes != apertureBytes ||
        !phxPspLayoutValid(&p->psp, mcBase, physicalBase, vramBytes, apertureBytes) ||
        !phxPspTmrFits(&p->psp, mcBase, physicalBase, 1) ||
        ((p->consoleOffset | p->consoleBytes) & 0xfffull) ||
        !phxPspSpanFits(p->consoleOffset, p->consoleBytes, vramBytes) ||
        !phxPspSpanFits(p->consoleOffset, p->consoleBytes, apertureBytes))
        return 0;
    return phxPspDisjoint(p->consoleOffset, p->consoleBytes, p->psp.ringOffset, PHX_PSP_LAYOUT_RING_BYTES) &&
           phxPspDisjoint(p->consoleOffset, p->consoleBytes, p->psp.tmrOffset, p->psp.tmrCapacity) &&
           phxPspDisjoint(p->consoleOffset, p->consoleBytes, p->psp.stagingOffset, p->psp.stagingCapacity);
}
#endif
