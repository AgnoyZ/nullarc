#pragma once

#include "build34_dcn_flip_commit.h"

namespace build34::dcn {

class DcnBar5Window {
public:
    bool arm(HubpAddress previous, HubpAddress next) {
        if (!previous.valid() || !next.valid() || previous.vmid == next.vmid) return false;
        vmids_ = ((1u << previous.vmid) | (1u << next.vmid)) & ~1u;
        return true;
    }

    bool canRead(uint32_t reg, uint64_t bytes) const {
        using namespace hubp0;
        if (!vmids_ || !contains(reg, bytes)) return false;
        switch (reg) {
        case kControl: case kVmid: case kProgrammedLow: case kProgrammedHigh: case kFlip: case kFlip2:
        case kInUseLow: case kInUseHigh: case kEarliestLow: case kEarliestHigh: case kFrame:
        case kSurfaceConfig: case kTilingConfig: case kViewportStart: case kViewportDimensions: case kSurfacePitch:
        case kSurfaceControl: case kReturnControl: case kOdmSelect: case kOtgControl: case kOtgUpdateLock: case kOtgLockSelect:
            return true;
        }
        for (uint32_t index = 0; index < dcnPeers::kCount; ++index) {
            const auto pipe = index + 1;
            if (reg == dcnPeers::kPower1 + index * dcnPeers::kPowerStride || reg == kOtgControl + pipe * dcnPeers::kOtgStride ||
                reg == kControl + pipe * dcnPeers::kHubpStride || reg == kFlip + pipe * dcnPeers::kHubpStride) return true;
        }
        return contextRegister(reg);
    }

    bool canWrite(uint32_t reg, uint64_t bytes) const {
        using namespace hubp0;
        return vmids_ && contains(reg, bytes) &&
            (reg == kVmid || reg == kProgrammedHigh || reg == kProgrammedLow || reg == kOtgUpdateLock || contextRegister(reg));
    }

private:
    static bool contains(uint32_t reg, uint64_t bytes) { return (uint64_t{reg} + 1) * sizeof(uint32_t) <= bytes; }

    bool contextRegister(uint32_t reg) const {
        if (reg < dcnVm::base(1) || reg >= dcnVm::base(16)) return false;
        const auto vmid = (reg - dcnVm::kContext0) / dcnVm::kStride;
        return vmids_ & (1u << vmid);
    }

    uint32_t vmids_{0};
};

}
