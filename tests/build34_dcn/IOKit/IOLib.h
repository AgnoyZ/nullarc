#pragma once

#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <cstring>

struct DcnAllocationStub {
    struct Slot {
        uint64_t pages[3 * 16384];
        size_t bytes;
    };
    inline static Slot slots[2]{};
    inline static bool fail = false;

    static unsigned live() { return (slots[0].bytes != 0) + (slots[1].bytes != 0); }
    static void reset() { slots[0].bytes = slots[1].bytes = 0; fail = false; }
};

inline void *IOMallocZero(size_t bytes) {
    assert(bytes);
    if (DcnAllocationStub::fail) return nullptr;
    if (bytes > sizeof(DcnAllocationStub::Slot::pages)) return std::calloc(1, bytes);
    for (auto &slot : DcnAllocationStub::slots) {
        if (slot.bytes) continue;
        slot.bytes = bytes;
        std::memset(slot.pages, 0, bytes);
        return slot.pages;
    }
    assert(false);
    return nullptr;
}

inline void IOFree(void *pages, size_t bytes) {
    for (auto &slot : DcnAllocationStub::slots) {
        if (slot.pages != pages) continue;
        assert(bytes && slot.bytes == bytes);
        slot.bytes = 0;
        return;
    }
    assert(bytes > sizeof(DcnAllocationStub::Slot::pages));
    std::free(pages);
}
