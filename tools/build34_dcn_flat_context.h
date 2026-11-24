#pragma once

#include "build34_dcn_flip_readback.h"

namespace build34::dcn {

struct DcnFlatContext {
    uint64_t rootEntry, firstPage, lastPage;
    uint32_t vmid;

    bool operator==(const DcnFlatContext &other) const {
        return rootEntry == other.rootEntry && firstPage == other.firstPage && lastPage == other.lastPage &&
            vmid == other.vmid;
    }
};

template<typename Current>
bool matchDcnFlatContext(const DcnFlatContext &expected, const HubpFlipReader &reader, const Current &current) {
    constexpr uint32_t context0 = 0x03a19, stride = 7, depthAndBlock = 0x7e;
    if (!expected.vmid || expected.vmid >= 16 || !(expected.rootEntry & 1) || expected.rootEntry == UINT64_MAX ||
        !(expected.rootEntry & ~(kPageBytes - 1)) || !expected.firstPage || expected.firstPage > expected.lastPage ||
        expected.lastPage >= kAddressLimit / kPageBytes || !reader.readDword)
        return false;
    const uint32_t base = context0 + expected.vmid * stride;
    if (reader.apertureBytes < uint64_t{base + stride} * sizeof(uint32_t)) return false;

    const auto equal = [&](uint32_t offset, uint32_t value, uint32_t mask = UINT32_MAX) {
        uint32_t reg = 0;
        return current() && reader.readDword(reader.context, base + offset, reg) && (reg & mask) == value;
    };
    return equal(0, 0, depthAndBlock) &&
        equal(1, static_cast<uint32_t>(expected.rootEntry >> 32)) && equal(2, static_cast<uint32_t>(expected.rootEntry)) &&
        equal(3, static_cast<uint32_t>(expected.firstPage >> 32)) && equal(4, static_cast<uint32_t>(expected.firstPage)) &&
        equal(5, static_cast<uint32_t>(expected.lastPage >> 32)) && equal(6, static_cast<uint32_t>(expected.lastPage)) &&
        current();
}

}
