// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Fixed, read-only display-order observations. No pointers or process identities.
#ifndef PHX_DISPLAY_HISTORY_H
#define PHX_DISPLAY_HISTORY_H
#include <stdint.h>

enum { PHX_DISPLAY_HISTORY_VERSION = 1 };
enum { PHX_RELEASE_SYSCTL = 1, PHX_RELEASE_TIMEOUT = 2, PHX_RELEASE_STOP = 3 };
struct PhxDisplayHistory {
    uint64_t version, bytes, framebufferID, preparations;
    uint64_t preparedNs, holdOnNs, holdDeadlineNs, firstReleaseNs, releaseReason;
    uint64_t holdOnCount, releaseCount, firstServerRequestNs, serverRequests;
    uint64_t firstServerSuccessNs, serverSuccesses, readNs, held, invalid;
};
static_assert(sizeof(PhxDisplayHistory) == 144, "display history wire size");

// Caller serializes these functions with the same lock as holdSet(). History
// is never reset, including on framebuffer restart, hold rearm or sysctl read.
static inline void phxHistoryPrepare(PhxDisplayHistory &h, uint64_t id, uint64_t ns)
{
    h.version = PHX_DISPLAY_HISTORY_VERSION; h.bytes = sizeof(h);
    if (++h.preparations != 1 || !id || !ns) h.invalid = 1;
    if (!h.framebufferID) { h.framebufferID = id; h.preparedNs = ns; }
    else if (h.framebufferID != id) h.invalid = 1;
}
static inline void phxHistoryHold(PhxDisplayHistory &h, uint64_t ns, uint64_t deadline)
{
    if (++h.holdOnCount != 1 || !h.preparedNs || ns < h.preparedNs || deadline <= ns) h.invalid = 1;
    if (!h.holdOnNs) { h.holdOnNs = ns; h.holdDeadlineNs = deadline; }
    h.held = 1;
}
static inline void phxHistoryRelease(PhxDisplayHistory &h, uint64_t ns, uint64_t reason)
{
    ++h.releaseCount;
    if (!h.firstReleaseNs) { h.firstReleaseNs = ns; h.releaseReason = reason; }
    if (!h.holdOnNs || ns < h.holdOnNs) h.invalid = 1;
    h.held = 0;
}
static inline void phxHistoryServer(PhxDisplayHistory &h, uint64_t ns, bool completed)
{
    if (!h.preparedNs || ns < h.preparedNs) h.invalid = 1;
    if (completed) {
        ++h.serverSuccesses;
        if (!h.firstServerSuccessNs) h.firstServerSuccessNs = ns;
    } else {
        ++h.serverRequests;
        if (!h.firstServerRequestNs) h.firstServerRequestNs = ns;
    }
}
#endif
