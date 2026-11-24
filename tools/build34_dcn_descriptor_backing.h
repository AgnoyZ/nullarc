#pragma once

#include <IOKit/IOMemoryDescriptor.h>

#include "build34_dcn_page_layout.h"

namespace build34::dcn {

struct PinnedDescriptorSlice {
    IOMemoryDescriptor *descriptor;
    uint64_t offset;
    uint64_t bytes;
};

inline bool readPinnedDescriptorPage(void *context, uint64_t backingOffset, uint64_t *physical) {
    if (!context || !physical)
        return false;
    const auto &slice = *static_cast<const PinnedDescriptorSlice *>(context);
    if (!slice.descriptor || slice.bytes < kPageBytes || slice.bytes > kMaxBackingBytes ||
        (slice.offset | slice.bytes | backingOffset) % kPageBytes || backingOffset > slice.bytes - kPageBytes)
        return false;

    const uint64_t length = slice.descriptor->getLength();
    if (slice.offset > length || slice.bytes > length - slice.offset)
        return false;

    IOByteCount contiguous = 0;
    const uint64_t address = slice.descriptor->getPhysicalSegment(slice.offset + backingOffset, &contiguous,
                                                                  kIOMemoryMapperNone);
    if (!address || address % kPageBytes || contiguous < kPageBytes)
        return false;

    *physical = address;
    return true;
}

}  // namespace build34::dcn
