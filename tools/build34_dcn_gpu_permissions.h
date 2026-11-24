#pragma once

#include "build34_dcn_physical_pages.h"

namespace build34::dcn {

inline constexpr uint64_t kGpuPteWrite = 1ull << 6;

struct DcnGpuPteTable {
    uint64_t *words;
    uint32_t ordinal;
};

enum class DcnGpuPermissionPhase { CanRestrict, Restricted, CanRestore, Restored };

struct DcnGpuPermissionUse {
    uint64_t serial;
    DcnGpuWriteOwner owner;
    PhysicalPageSet pages;
};

struct DcnGpuPermissionAck {
    uint64_t serial;
    DcnGpuWriteOwner owner;
    DcnGpuPermissionPhase phase;

    bool matches(const DcnGpuPermissionUse &use, DcnGpuPermissionPhase required) const {
        return serial == use.serial && owner == use.owner && phase == required;
    }
};

template<typename Resolve, typename Visit>
bool walkDcnGpuPtes(uint64_t root, uint32_t used, uint64_t addressMask, uint64_t writableFlags,
                   const Resolve &resolve, const Visit &visit) {
    constexpr uint32_t maxTables = 1024;
    if (!root || (root & ~addressMask) || !used || used > maxTables) return false;
    uint64_t visited[maxTables / 64]{};
    uint32_t count = 0;
    const auto walk = [&](const auto &descend, uint64_t physical, uint32_t depth, uint32_t parent) -> bool {
        const auto table = resolve(physical);
        if (!table.words || table.ordinal >= used || (depth ? table.ordinal <= parent : table.ordinal != 0)) return false;
        auto &seen = visited[table.ordinal / 64];
        const uint64_t bit = 1ull << (table.ordinal % 64);
        if (seen & bit) return false;
        seen |= bit;
        ++count;
        for (size_t index = 0; index < kPageBytes / sizeof(uint64_t); ++index) {
            auto &word = table.words[index];
            if (!word) continue;
            const auto page = word & addressMask;
            const auto flags = word & ~addressMask;
            if (!page) return false;
            if (depth != 3) {
                if (flags != 7 || !descend(descend, page, depth + 1, table.ordinal)) return false;
            } else if ((flags != writableFlags && flags != (writableFlags & ~kGpuPteWrite)) || !visit(word, page)) {
                return false;
            }
        }
        return true;
    };
    return walk(walk, root, 0, 0) && count == used;
}

}
