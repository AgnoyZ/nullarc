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

struct DcnGpuWriteOwner {
    uint64_t allocation, root, epoch;
    uint32_t context, slot;

    bool operator==(const DcnGpuWriteOwner &other) const {
        return allocation == other.allocation && root == other.root && epoch == other.epoch &&
            context == other.context && slot == other.slot;
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

    DcnGpuWriteOwner readOnly(PhysicalPageSet pages) const {
        for (const auto &hold : holds_)
            if (samePages(hold.pages, pages)) return hold.readOnly;
        return {};
    }

    bool pinReadOnly(PhysicalPageSet pages, DcnGpuWriteOwner owner) {
        for (auto &hold : holds_) {
            if (!samePages(hold.pages, pages) || hold.readOnly.context || !owner.allocation || !owner.root ||
                !hold.blocked.blocksContext(owner.context) || !hold.blocked.blocksSlot(owner.slot)) continue;
            hold.readOnly = owner;
            return true;
        }
        return false;
    }

    bool setReadOnlyAccess(PhysicalPageSet pages, bool allow) {
        for (auto &hold : holds_) {
            const auto owner = hold.readOnly;
            if (!samePages(hold.pages, pages) || !owner.context) continue;
            const uint64_t bit = 1ull << ((owner.context - 1) % 64);
            auto &mask = hold.blocked.contexts[(owner.context - 1) / 64];
            if (allow) {
                mask &= ~bit;
                hold.blocked.slots &= ~(1u << owner.slot);
            } else {
                mask |= bit;
                hold.blocked.slots |= 1u << owner.slot;
            }
            return true;
        }
        return false;
    }

    bool pinsContext(uint32_t context) const {
        return context && (holds_[0].readOnly.context == context || holds_[1].readOnly.context == context);
    }

    bool pinsSlot(uint32_t slot) const {
        for (const auto &hold : holds_)
            if (hold.readOnly.context && hold.readOnly.slot == slot) return true;
        return false;
    }

    bool permissionsCurrent(uint64_t epoch) const {
        for (const auto &hold : holds_)
            if (hold.readOnly.context && hold.readOnly.epoch != epoch) return false;
        return true;
    }

    bool acquire(PhysicalPageSet next, DcnManagedWriteExclusion blocked) {
        if (!canonicalPages(next) || holds_[0].pages.overlaps(next) || holds_[1].pages.overlaps(next)) return false;
        for (auto &held : holds_) {
            if (held.pages.count) continue;
            held = {next, blocked, {}};
            return true;
        }
        return false;
    }

    void release(PhysicalPageSet retired) {
        for (auto &held : holds_)
            if (samePages(held.pages, retired)) held = {};
    }

private:
    static bool canonicalPages(PhysicalPageSet pages) {
        if (!pages.pages || !pages.count || pages.count > kMaxBackingBytes / kPageBytes) return false;
        for (size_t index = 0; index < pages.count; ++index) {
            const uint64_t page = pages.pages[index];
            if (!page || page % kPageBytes || (index && pages.pages[index - 1] >= page)) return false;
        }
        return true;
    }

    static bool samePages(PhysicalPageSet first, PhysicalPageSet second) {
        return first.count && first.count == second.count && first.pages == second.pages;
    }

    struct Hold {
        PhysicalPageSet pages;
        DcnManagedWriteExclusion blocked;
        DcnGpuWriteOwner readOnly;
    } holds_[2]{};
};

}
