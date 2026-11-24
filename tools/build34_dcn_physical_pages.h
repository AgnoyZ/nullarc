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

class DcnManagedWriteHolds {
public:
    bool active() const { return holds_[0].count || holds_[1].count; }

    bool excludes(uint64_t physicalPage) const {
        return holds_[0].contains(physicalPage) || holds_[1].contains(physicalPage);
    }

    bool acquire(PhysicalPageSet next) {
        if (!next.pages || !next.count || holds_[0].overlaps(next) || holds_[1].overlaps(next)) return false;
        for (auto &held : holds_) {
            if (held.count) continue;
            held = next;
            return true;
        }
        return false;
    }

    void release(PhysicalPageSet retired) {
        for (auto &held : holds_)
            if (held.pages == retired.pages && held.count == retired.count) held = {};
    }

private:
    PhysicalPageSet holds_[2]{};
};

}
