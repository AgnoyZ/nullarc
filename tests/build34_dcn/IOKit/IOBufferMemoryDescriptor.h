#pragma once

#include <cassert>
#include <cstddef>
#include <functional>

#include "IOMemoryDescriptor.h"

inline void *kernel_task = nullptr;
inline constexpr unsigned kIODirectionOut = 2, kIOMemoryIncoherentIOStore = 2;

struct IOBufferMemoryDescriptor : IOMemoryDescriptor {
    inline static IOBufferMemoryDescriptor *next = nullptr;
    alignas(4096) uint64_t words[1024]{};
    uint64_t physical = 0x90000000;
    unsigned references = 0, stores = 0;
    bool shortBuffer = false, failStore = false;
    std::function<void()> onStore;

    static IOBufferMemoryDescriptor *inTaskWithOptions(void *task, unsigned options, size_t capacity, size_t alignment) {
        assert(task == kernel_task && options == (kIODirectionOut | kIOMemoryMapperNone) && capacity == 8192 && alignment == 4096);
        if (!next) return nullptr;
        assert(!next->references);
        next->retain();
        for (auto &word : next->words) word = UINT64_MAX;
        return next;
    }
    void *getBytesNoCopy() { return words; }
    IOByteCount getLength() const override { return shortBuffer ? 4096 : sizeof(words); }
    uint64_t getPhysicalSegment(IOByteCount offset, IOByteCount *length, unsigned options) override {
        assert(references && options == kIOMemoryMapperNone && !offset);
        *length = 4096;
        return physical;
    }
    IOReturn performOperation(unsigned op, IOByteCount offset, IOByteCount length) {
        assert(references == 2 && op == kIOMemoryIncoherentIOStore && !offset && length == 4096);
        ++stores;
        if (onStore) onStore();
        return failStore ? -1 : kIOReturnSuccess;
    }
    uint64_t getPreparationID() override { return kIOPreparationIDAlwaysPrepared; }
    IOReturn prepare() override { assert(false); return -1; }
    IOReturn complete() override { assert(false); return -1; }
    void retain() override { ++references; }
    void release() override { assert(references); --references; }
};
