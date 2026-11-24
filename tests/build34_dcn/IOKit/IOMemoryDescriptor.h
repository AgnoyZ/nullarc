#pragma once

#include <stdint.h>

using IOByteCount = uint64_t;
using IOReturn = int;
inline constexpr unsigned kIOMemoryMapperNone = 0x800;
inline constexpr uint64_t kIOPreparationIDAlwaysPrepared = 2;
inline constexpr IOReturn kIOReturnSuccess = 0;

struct IOMemoryDescriptor {
    static IOMemoryDescriptor *withAddressRange(uint64_t address, uint64_t bytes, unsigned direction, void *task);
    virtual IOByteCount getLength() const = 0;
    virtual uint64_t getPhysicalSegment(IOByteCount offset, IOByteCount *length, unsigned options) = 0;
    virtual uint64_t getPreparationID() = 0;
    virtual IOReturn prepare() = 0;
    virtual IOReturn complete() = 0;
    virtual void retain() = 0;
    virtual void release() = 0;
};
