#pragma once

#include "build34_dcn_firmware_home.h"

namespace build34::dcn {

enum class DcnPresentDomain { None, Mapped, Direct };

struct DcnPresentWindow {
    HubpAddress base;
    uint64_t bytes;

    bool fits(uint64_t footprint) const {
        return base.valid() && base.vmid && footprint && footprint % kPageBytes == 0 &&
            footprint <= bytes && bytes <= kMaxBackingBytes && bytes % kPageBytes == 0 &&
            bytes <= kAddressLimit - base.address;
    }

    bool operator==(const DcnPresentWindow &other) const { return base == other.base && bytes == other.bytes; }
};

struct DcnPresentWindowPair {
    DcnPresentWindow first, second;
    DcnPresentDomain domain;

    bool valid(uint64_t footprint) const {
        return (domain == DcnPresentDomain::Mapped || domain == DcnPresentDomain::Direct) &&
            first.fits(footprint) && second.fits(footprint) && first.base.vmid != second.base.vmid &&
            (first.base.address < second.base.address ? first.bytes <= second.base.address - first.base.address :
                second.bytes <= first.base.address - second.base.address);
    }

    HubpAddress select(HubpAddress previous, uint64_t footprint) const {
        if (!previous.valid() || !valid(footprint)) return {};
        if (!previous.vmid || previous == second.base) return first.base;
        return previous == first.base ? second.base : HubpAddress{};
    }

    FirmwareFlatWindows exclusions() const {
        return {{first.base.address, first.bytes}, {second.base.address, second.bytes}};
    }

    bool operator==(const DcnPresentWindowPair &other) const {
        return domain == other.domain && first == other.first && second == other.second;
    }
};

}
