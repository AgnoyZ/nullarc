#pragma once

#include "IOMapper.h"

using UInt64 = uint64_t;
using UInt32 = uint32_t;

struct IODMACommand {
    struct Segment64 { UInt64 fIOVMAddr, fLength; };
    enum MappingOptions { kMapped };
    static bool OutputHost64() { return true; }
    inline static IODMACommand *next = nullptr;
    IOMemoryDescriptor *memory = nullptr, *substitute = nullptr;
    UInt64 offset = 0, bytes = 0, extent = 0;
    unsigned created = 0, completes = 0, clears = 0, releases = 0;
    bool prepared = false, failPrepare = false, wrongOffset = false, failComplete = false, failClear = false;
    std::function<IOReturn(UInt64 *, Segment64 *, UInt32 *)> segments;
    std::function<void()> onComplete;

    static IODMACommand *withSpecification(bool (*output)(), unsigned bits, UInt64 maxSegment,
        MappingOptions mode, UInt64 transfer, UInt32 alignment, IOMapper *mapper) {
        assert(output == OutputHost64 && bits == 48 && !maxSegment && mode == kMapped && mapper && alignment == 4096);
        assert(next && !next->prepared && !next->memory);
        next->extent = transfer;
        ++next->created;
        return next;
    }
    IOReturn setMemoryDescriptor(IOMemoryDescriptor *descriptor, bool autoPrepare) {
        assert(descriptor && !autoPrepare && !memory);
        descriptor->retain();
        memory = descriptor;
        return kIOReturnSuccess;
    }
    const IOMemoryDescriptor *getMemoryDescriptor() const { return memory; }
    IOMemoryDescriptor *getIOMemoryDescriptor() const { return substitute ? substitute : memory; }
    IOReturn prepare(UInt64 start, UInt64 length, bool flush, bool synchronize) {
        assert(memory && !prepared && !flush && !synchronize && length == extent);
        assert(start && start < memory->getLength() && length < memory->getLength() - start);
        offset = start;
        bytes = length;
        prepared = true;
        return failPrepare ? -1 : kIOReturnSuccess;
    }
    IOReturn getPreparedOffsetAndLength(UInt64 *start, UInt64 *length) {
        assert(prepared);
        *start = wrongOffset ? 0 : offset;
        *length = bytes;
        return kIOReturnSuccess;
    }
    IOReturn gen64IOVMSegments(UInt64 *cursor, Segment64 *out, UInt32 *count) {
        assert(prepared && *cursor < bytes);
        return segments(cursor, out, count);
    }
    IOReturn complete(bool invalidate, bool synchronize) {
        assert(prepared && !invalidate && !synchronize);
        if (onComplete) onComplete();
        prepared = false;
        ++completes;
        return failComplete ? -1 : kIOReturnSuccess;
    }
    IOReturn clearMemoryDescriptor(bool autoComplete) {
        assert(memory && !prepared && !autoComplete);
        ++clears;
        if (failClear) return -1;
        memory->release();
        memory = nullptr;
        return kIOReturnSuccess;
    }
    void release() { assert(!prepared && !memory); ++releases; }
};

#define kIODMACommandOutputHost64 (IODMACommand::OutputHost64)
