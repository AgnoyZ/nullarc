#pragma once

#include "build34_dcn_flip_readback.h"

namespace build34::dcn {

namespace dcnVm {
inline constexpr uint32_t kContext0 = 0x03a19, kStride = 7, kDepthAndBlock = 0x7e;
constexpr uint32_t base(uint32_t vmid) { return kContext0 + vmid * kStride; }
}

struct DcnFlatContext {
    uint64_t rootEntry, firstPage, lastPage;
    uint32_t vmid;

    bool valid() const {
        return vmid && vmid < 16 && (rootEntry & 1) && rootEntry != UINT64_MAX &&
            (rootEntry & ~(kPageBytes - 1)) && firstPage && firstPage <= lastPage && lastPage < kAddressLimit / kPageBytes;
    }

    bool operator==(const DcnFlatContext &other) const {
        return rootEntry == other.rootEntry && firstPage == other.firstPage && lastPage == other.lastPage &&
            vmid == other.vmid;
    }
};

inline bool canReadDcnContext(uint32_t vmid, const HubpFlipReader &reader) {
    return vmid && vmid < 16 && reader.readDword &&
        reader.apertureBytes >= uint64_t{dcnVm::base(vmid) + dcnVm::kStride} * sizeof(uint32_t);
}

template<typename Current>
bool matchDcnFlatContext(const DcnFlatContext &expected, const HubpFlipReader &reader, const Current &current) {
    if (!expected.valid() || !canReadDcnContext(expected.vmid, reader)) return false;
    const uint32_t base = dcnVm::base(expected.vmid);

    const auto equal = [&](uint32_t offset, uint32_t value, uint32_t mask = UINT32_MAX) {
        uint32_t reg = 0;
        return current() && reader.readDword(reader.ioContext, base + offset, reg) && (reg & mask) == value;
    };
    return equal(0, 0, dcnVm::kDepthAndBlock) &&
        equal(1, static_cast<uint32_t>(expected.rootEntry >> 32)) && equal(2, static_cast<uint32_t>(expected.rootEntry)) &&
        equal(3, static_cast<uint32_t>(expected.firstPage >> 32)) && equal(4, static_cast<uint32_t>(expected.firstPage)) &&
        equal(5, static_cast<uint32_t>(expected.lastPage >> 32)) && equal(6, static_cast<uint32_t>(expected.lastPage)) &&
        current();
}

}
