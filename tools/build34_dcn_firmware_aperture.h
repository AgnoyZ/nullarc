#pragma once

#include "build34_dcn_flat_context.h"

namespace build34::dcn {

namespace firmwareAperture {
inline constexpr uint32_t kDcnBase = 0x03935, kDcnTop = 0x03936, kDcnOffset = 0x03937;
inline constexpr uint32_t kAgpBottom = 0x03938, kAgpTop = 0x03939;
inline constexpr uint32_t kMmhubBase = 0x1a8ec, kMmhubTop = 0x1a8ed, kMmhubOffset = 0x1a8d7;
inline constexpr unsigned kUnitShift = 24;
inline constexpr uint32_t kUnitsMask = 0x00ffffff;
inline constexpr uint64_t kMmioBytes = (uint64_t{kMmhubTop} + 1) * sizeof(uint32_t);
}

class FirmwareLocalAperture {
public:
    template<typename ReadDword>
    bool sample(const ReadDword &read) {
        using namespace firmwareAperture;
        if (!read(kDcnBase, dcnBase_) || !read(kDcnTop, dcnTop_) || !read(kDcnOffset, dcnOffset_) ||
            !read(kMmhubBase, mmhubBase_) || !read(kMmhubTop, mmhubTop_) || !read(kMmhubOffset, mmhubOffset_) ||
            !read(kAgpBottom, agpBottom_) || !read(kAgpTop, agpTop_)) return false;
        for (uint32_t field = 0; field < dcnVm::kStride; ++field)
            if (!read(dcnVm::base(0) + field, context_[field])) return false;
        return true;
    }

    bool same(const FirmwareLocalAperture &other) const {
        if (dcnBase_ != other.dcnBase_ || dcnTop_ != other.dcnTop_ || dcnOffset_ != other.dcnOffset_ ||
            mmhubBase_ != other.mmhubBase_ || mmhubTop_ != other.mmhubTop_ || mmhubOffset_ != other.mmhubOffset_ ||
            agpBottom_ != other.agpBottom_ || agpTop_ != other.agpTop_) return false;
        for (uint32_t field = 0; field < dcnVm::kStride; ++field)
            if (context_[field] != other.context_[field]) return false;
        return true;
    }

    bool bind(HubpAddress scanout, uint64_t barOffset, uint64_t bytes, uint64_t &backing) const {
        using namespace firmwareAperture;
        backing = 0;
        if (!scanout.valid() || scanout.vmid || !bytes || bytes % kPageBytes || bytes > kAddressLimit - scanout.address ||
            ((dcnBase_ | dcnTop_ | dcnOffset_ | agpBottom_ | agpTop_) & ~kUnitsMask) ||
            dcnBase_ != mmhubBase_ || dcnTop_ != mmhubTop_ || dcnOffset_ != mmhubOffset_ ||
            dcnBase_ > dcnTop_ || !dcnOffset_) return false;

        const uint64_t start = scanout.address, last = start + bytes - 1;
        const uint64_t window = uint64_t{dcnBase_} << kUnitShift;
        if (start < window || (last >> kUnitShift) > dcnTop_ || start - window != barOffset ||
            rangeIntersects(start >> kUnitShift, last >> kUnitShift, agpBottom_, agpTop_)) return false;

        if (hasContext()) {
            const uint64_t firstPage = contextPage(3), lastPage = contextPage(5);
            const uint64_t root = (uint64_t{context_[1]} << 32) | context_[2];
            if ((context_[0] & ~dcnVm::kDepthAndBlock) || !(root & 1) || root == UINT64_MAX || !(root & ~(kPageBytes - 1)) ||
                firstPage > lastPage || lastPage >= kAddressLimit / kPageBytes ||
                rangeIntersects(start / kPageBytes, last / kPageBytes, firstPage, lastPage)) return false;
        }
        const uint64_t physicalBase = uint64_t{dcnOffset_} << kUnitShift;
        if (barOffset >= kAddressLimit - physicalBase || bytes > kAddressLimit - physicalBase - barOffset) return false;
        backing = physicalBase + barOffset;
        return true;
    }

    bool excludesFlatWindow(uint64_t start, uint64_t bytes) const {
        using namespace firmwareAperture;
        if (!bytes) return !start;
        if (!start || start >= kAddressLimit || start % kPageBytes || bytes % kPageBytes ||
            bytes > kMaxBackingBytes || bytes > kAddressLimit - start) return false;
        const uint64_t last = start + bytes - 1;
        const uint64_t firstUnit = start >> kUnitShift, lastUnit = last >> kUnitShift;
        return !rangeIntersects(firstUnit, lastUnit, dcnBase_, dcnTop_) &&
            !rangeIntersects(firstUnit, lastUnit, agpBottom_, agpTop_) &&
            (!hasContext() || !rangeIntersects(start / kPageBytes, last / kPageBytes, contextPage(3), contextPage(5)));
    }

private:
    bool hasContext() const {
        return context_[0] | context_[1] | context_[2] | context_[3] | context_[4] | context_[5] | context_[6];
    }

    uint64_t contextPage(size_t high) const { return (uint64_t{context_[high]} << 32) | context_[high + 1]; }

    static bool rangeIntersects(uint64_t first, uint64_t last, uint64_t otherFirst, uint64_t otherLast) {
        return otherFirst <= otherLast && first <= otherLast && otherFirst <= last;
    }

    uint32_t dcnBase_{0}, dcnTop_{0}, dcnOffset_{0};
    uint32_t mmhubBase_{0}, mmhubTop_{0}, mmhubOffset_{0};
    uint32_t agpBottom_{0}, agpTop_{0}, context_[dcnVm::kStride]{};
};

}
