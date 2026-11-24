#pragma once

#include "build34_dcn_page_layout.h"

namespace build34::dcn {

enum class DcnHostFlatProfile : uint8_t { Unqualified, Gmc11SnoopedSystemUc };

struct DcnHostFlatWords {
    static constexpr uint64_t kLimit = 1ull << 44;
    static constexpr uint64_t kAddress = (kLimit - 1) & ~(kPageBytes - 1);
    static constexpr uint64_t kValid = 1ull << 0, kSystem = 1ull << 1, kSnooped = 1ull << 2;
    static constexpr uint64_t kReadable = 1ull << 5, kUncached = 3ull << 48;
    static constexpr uint64_t kRoot = kValid | kSystem | kSnooped;
    static constexpr uint64_t kLeaf = kRoot | kReadable | kUncached;

    static bool supported(DcnHostFlatProfile profile) { return profile == DcnHostFlatProfile::Gmc11SnoopedSystemUc; }

    static bool range(uint64_t base, uint64_t bytes) {
        return base && !(base & ~kAddress) && bytes && !(bytes % kPageBytes) && bytes <= kLimit - base;
    }

    static bool root(DcnHostFlatProfile profile, uint64_t base, uint64_t bytes, uint64_t &word) {
        if (!supported(profile) || !range(base, bytes)) return false;
        word = base | kRoot;
        return true;
    }

    static bool leaf(DcnHostFlatProfile profile, uint64_t address, uint64_t &word) {
        if (!supported(profile) || !range(address, kPageBytes)) return false;
        word = address | kLeaf;
        return true;
    }

    static bool decode(DcnHostFlatProfile profile, uint64_t word, uint64_t &address) {
        const uint64_t base = word & kAddress;
        if (!supported(profile) || !base || (word & ~kAddress) != kLeaf) return false;
        address = base;
        return true;
    }
};

}
