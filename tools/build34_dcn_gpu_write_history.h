#pragma once

#include <IOKit/IOLib.h>

#include "build34_dcn_physical_pages.h"

namespace build34::dcn {

template<size_t Capacity = (1u << 18)>
class DcnGpuWriteHistory {
    static_assert(Capacity && !(Capacity & (Capacity - 1)));
    static constexpr size_t kProbeLimit = Capacity < 32 ? Capacity : 32;
    struct Entry {
        uint64_t page, contexts[2];
    };

public:
    DcnGpuWriteHistory() = default;
    DcnGpuWriteHistory(const DcnGpuWriteHistory &) = delete;
    DcnGpuWriteHistory &operator=(const DcnGpuWriteHistory &) = delete;
    ~DcnGpuWriteHistory() { if (table_) IOFree(table_, Capacity * sizeof(Entry)); }

    void mapped(uint32_t handle, uint64_t page) {
        if (lost_) return;
        if (!validContext(handle) || !page || page % kPageBytes) {
            lost_ = true;
            return;
        }
        if (!table_) table_ = static_cast<Entry *>(IOMallocZero(Capacity * sizeof(Entry)));
        auto *entry = lookup(page);
        if (!entry) {
            lost_ = true;
            return;
        }
        entry->page = page;
        entry->contexts[(handle - 1) / 64] |= 1ull << ((handle - 1) % 64);
    }

    void bound(uint32_t handle, uint32_t slot) {
        if (!validContext(handle) || slot >= DcnManagedWriteExclusion::kVmidSlots) lost_ = true;
        else slots_[handle - 1] |= 1u << slot;
    }

    bool exclusion(PhysicalPageSet pages, DcnManagedWriteExclusion &out) const {
        if (lost_ || !pages.pages || !pages.count || pages.count > kMaxBackingBytes / kPageBytes) return false;
        DcnManagedWriteExclusion excluded{};
        for (size_t index = 0; index < pages.count && table_; ++index) {
            const auto *entry = lookup(pages.pages[index]);
            if (entry && entry->page) {
                excluded.contexts[0] |= entry->contexts[0];
                excluded.contexts[1] |= entry->contexts[1];
            }
        }
        for (uint32_t handle = 1; handle <= DcnManagedWriteExclusion::kContexts; ++handle)
            if (excluded.blocksContext(handle)) excluded.slots |= slots_[handle - 1];
        out = excluded;
        return true;
    }

private:
    static bool validContext(uint32_t handle) {
        return handle && handle <= DcnManagedWriteExclusion::kContexts;
    }

    Entry *lookup(uint64_t page) const {
        if (!table_) return nullptr;
        uint64_t hash = page / kPageBytes;
        hash = (hash ^ (hash >> 30)) * 0xbf58476d1ce4e5b9ull;
        hash = (hash ^ (hash >> 27)) * 0x94d049bb133111ebull;
        hash ^= hash >> 31;
        for (size_t probe = 0; probe < kProbeLimit; ++probe) {
            auto &entry = table_[(hash + probe) & (Capacity - 1)];
            if (!entry.page || entry.page == page) return &entry;
        }
        return nullptr;
    }

    Entry *table_{nullptr};
    uint32_t slots_[DcnManagedWriteExclusion::kContexts]{};
    bool lost_{false};
};

}
