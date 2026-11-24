#pragma once

#include <IOKit/IOLib.h>
#include "build34_dcn_present_windows.h"

#define BUILD34_DCN_ACQUIRE_FB_ROUTE "phx34DcnAcquireFramebufferRouteV1"
#define BUILD34_DCN_RELEASE_FB_ROUTE "phx34DcnReleaseFramebufferRouteV1"

namespace build34::dcn {

class DcnFramebufferRouteGate;

struct DcnFramebufferRouteClaim {
    IOService *provider;
    const void *owner;
    uint64_t generation;
    DcnPresentWindowPair windows;
    DcnFramebufferRouteGate *gate;
    uint64_t serial;

    bool sameOwner(const DcnFramebufferRouteClaim &other) const {
        return provider == other.provider && owner == other.owner && generation == other.generation && windows == other.windows;
    }
};

class DcnFramebufferRouteGate {
public:
    DcnFramebufferRouteGate() = default;
    DcnFramebufferRouteGate(const DcnFramebufferRouteGate &) = delete;
    DcnFramebufferRouteGate &operator=(const DcnFramebufferRouteGate &) = delete;

    void setLock(IOLock *lock) { lock_ = lock; }

    bool canAcquireLocked(const DcnFramebufferRouteClaim &claim, uint64_t bytes) const {
        return lock_ && !closed_ && !active_.serial && serial_ < UINT64_MAX && !claim.gate && !claim.serial &&
            claim.provider && claim.owner && claim.generation && claim.windows.valid(bytes);
    }

    bool acquireLocked(DcnFramebufferRouteClaim &claim, uint64_t bytes) {
        if (!canAcquireLocked(claim, bytes)) return false;
        claim.gate = this;
        claim.serial = ++serial_;
        active_ = claim;
        return true;
    }

    bool releaseLocked(const DcnFramebufferRouteClaim &claim) {
        if (!matchesLocked(claim)) return false;
        active_ = {};
        return true;
    }

    void closeLocked() { closed_ = true; }

    template<typename Access>
    bool access(const DcnFramebufferRouteClaim &claim, Access perform) const {
        if (!lock_ || !IOLockTryLock(lock_)) return false;
        const bool accepted = !closed_ && matchesLocked(claim) && perform();
        IOLockUnlock(lock_);
        return accepted;
    }

private:
    bool matchesLocked(const DcnFramebufferRouteClaim &claim) const {
        return claim.gate == this && active_.serial && claim.serial == active_.serial && active_.sameOwner(claim);
    }

    IOLock *lock_{nullptr};
    DcnFramebufferRouteClaim active_{};
    uint64_t serial_{0};
    bool closed_{false};
};

template<typename Read>
bool checkUnclaimedDcnContexts(const DcnPresentWindowPair &windows, HubpAddress firmware,
                              uint64_t bytes, uint64_t apertureBytes, const Read &read) {
    if (!windows.valid(bytes) || !firmware.valid() || firmware.vmid || apertureBytes < dcnPeers::kMmioBytes) return false;
    const auto checked = [&](uint32_t reg, uint32_t &value) { return read(reg, value) && value != UINT32_MAX; };
    const auto empty = [&](uint32_t vmid) {
        for (uint32_t field = 0; field < dcnVm::kStride; ++field) {
            uint32_t value = 0;
            if (!checked(dcnVm::base(vmid) + field, value) || value) return false;
        }
        return true;
    };
    HubpAddress current{};
    uint32_t frame = 0, after = 0;
    return HubpFlipReadback::observeQuiescent(checked, current, frame) && current == firmware &&
        empty(windows.first.base.vmid) && empty(windows.second.base.vmid) && matchIdleDcnPeers(checked) &&
        empty(windows.first.base.vmid) && empty(windows.second.base.vmid) && checked(hubp0::kFrame, after) &&
        (after & hubp0::kFrameMask) == frame;
}

}
