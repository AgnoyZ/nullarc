#pragma once

#include "build34_dcn_render_lease.h"

#define BUILD34_DCN_PIN_PREPARE "phx34DcnPinPrepareV1"
#define BUILD34_DCN_PIN_CANCEL "phx34DcnPinCancelV1"

namespace build34::dcn {

struct ScanoutPinToken {
    const void *provider;
    uint64_t serial;

    bool operator==(const ScanoutPinToken &other) const { return provider == other.provider && serial == other.serial; }
};

class ScanoutDescriptorPin {
public:
    bool acquire(const PinnedDescriptorSlice &slice, uint64_t preparation) {
        const bool acquired = lease_.acquire(slice, preparation);
        lease_.recycleClosed();
        return acquired;
    }

    bool releaseUnused() {
        if (displayUse_) return false;
        const bool released = lease_.releaseAfterRetirement();
        lease_.recycleClosed();
        return released;
    }

    bool beginDisplayUse() {
        if (!cancellable()) return false;
        displayUse_ = true;
        return true;
    }

    bool held() const { return lease_.bytes() != 0; }
    bool cancellable() const { return held() && !displayUse_; }
    bool uncertain() const { return lease_.uncertain(); }

private:
    friend class ScanoutDmaLease;
    friend class ScanoutFlipCommit;

    bool retireDisplayUse() {
        if (!held() || !displayUse_) return false;
        if (!lease_.releaseAfterRetirement()) return false;
        displayUse_ = false;
        lease_.recycleClosed();
        return true;
    }

    RenderDescriptorLease lease_;
    bool displayUse_{false};
};

}
