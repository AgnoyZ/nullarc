#pragma once

#include "build34_dcn_page_layout.h"

namespace build34::dcn {

struct PhysicalPageSet {
    const uint64_t *pages;
    size_t count;

    bool contains(uint64_t page) const {
        size_t first = 0, end = count;
        while (first < end) {
            const size_t middle = first + (end - first) / 2;
            if (pages[middle] < page) first = middle + 1;
            else end = middle;
        }
        return first < count && pages[first] == page;
    }

    bool overlaps(PhysicalPageSet other) const {
        size_t left = 0, right = 0;
        while (left < count && right < other.count) {
            if (pages[left] == other.pages[right]) return true;
            if (pages[left] < other.pages[right]) ++left;
            else ++right;
        }
        return false;
    }
};

inline void sortPhysicalPages(uint64_t *pages, size_t count) {
    const auto sift = [&](size_t root, size_t end) {
        while (root < end / 2) {
            size_t child = 2 * root + 1;
            if (child + 1 < end && pages[child] < pages[child + 1]) ++child;
            if (pages[root] >= pages[child]) break;
            const auto page = pages[child];
            pages[child] = pages[root];
            pages[root] = page;
            root = child;
        }
    };
    for (size_t root = count / 2; root; --root) sift(root - 1, count);
    for (size_t end = count; end > 1; --end) {
        const auto largest = pages[0];
        pages[0] = pages[end - 1];
        pages[end - 1] = largest;
        sift(0, end - 1);
    }
}

struct DcnManagedWriteExclusion {
    static constexpr uint32_t kContexts = 128, kVmidSlots = 32;
    uint64_t contexts[2]{};
    uint32_t slots{0};

    bool blocksContext(uint32_t handle) const {
        return handle && handle <= kContexts && (contexts[(handle - 1) / 64] & (1ull << ((handle - 1) % 64)));
    }

    bool blocksSlot(uint32_t slot) const {
        return slot < kVmidSlots && (slots & (1u << slot));
    }
};

class DcnManagedWriteHolds {
public:
    bool active() const { return holds_[0].pages.count || holds_[1].pages.count; }

    bool excludes(uint64_t physicalPage) const {
        return holds_[0].pages.contains(physicalPage) || holds_[1].pages.contains(physicalPage);
    }

    bool blocksContext(uint32_t handle) const {
        return holds_[0].blocked.blocksContext(handle) || holds_[1].blocked.blocksContext(handle);
    }

    bool blocksSlot(uint32_t slot) const {
        return holds_[0].blocked.blocksSlot(slot) || holds_[1].blocked.blocksSlot(slot);
    }

    bool acquire(PhysicalPageSet next, DcnManagedWriteExclusion blocked) {
        if (!next.pages || !next.count || holds_[0].pages.overlaps(next) || holds_[1].pages.overlaps(next)) return false;
        for (auto &held : holds_) {
            if (held.pages.count) continue;
            held = {next, blocked};
            return true;
        }
        return false;
    }

    void release(PhysicalPageSet retired) {
        for (auto &held : holds_)
            if (held.pages.pages == retired.pages && held.pages.count == retired.count) held = {};
    }

private:
    struct Hold {
        PhysicalPageSet pages;
        DcnManagedWriteExclusion blocked;
    } holds_[2]{};
};

}
