#pragma once

#include <stdint.h>

using IOByteCount = uint64_t;
inline constexpr unsigned kIOMemoryMapperNone = 0x800;

struct IOMemoryDescriptor {
    virtual IOByteCount getLength() const = 0;
    virtual uint64_t getPhysicalSegment(IOByteCount offset, IOByteCount *length, unsigned options) = 0;
};
