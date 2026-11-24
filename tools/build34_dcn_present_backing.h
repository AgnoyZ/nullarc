#pragma once

#include "build34_dcn_render_binding.h"

namespace build34::dcn {

struct PresentCopyBacking {
    const void *transaction;
    const void *surface;
    PinnedDescriptorSlice slice;
    uint64_t preparation;
    ScanoutSurface scanout;
};

inline uint64_t livePresentPreparation(const PinnedDescriptorSlice &slice) {
    if (!validDescriptorSlice(slice))
        return 0;
    const uint64_t preparation = slice.descriptor->getPreparationID();
    return preparation > kIOPreparationIDAlwaysPrepared && preparation != UINT64_MAX ? preparation : 0;
}

inline PresentCopyBacking observePreparedCopyBacking(const void *transaction, const void *surface,
    IOMemoryDescriptor *descriptor, uint32_t format, uint32_t width, uint32_t height, uint32_t pitch,
    uint32_t panelWidth, uint32_t panelHeight) {
    if (!transaction || !surface || !descriptor || format != kSurfaceBgra || !width || !height ||
        width != panelWidth || height != panelHeight || pitch < uint64_t{width} * 4 || pitch % 4 || pitch / 4 > 0x4000)
        return {};

    const uint64_t footprint = uint64_t{pitch} * height;
    if (footprint > kMaxBackingBytes)
        return {};
    const uint64_t rounded = (footprint + kPageBytes - 1) & ~(kPageBytes - 1);
    const PinnedDescriptorSlice slice{descriptor, 0, rounded};
    const uint64_t preparation = livePresentPreparation(slice);
    return preparation ? PresentCopyBacking{transaction, surface, slice, preparation,
        {width, height, pitch / 4 - 1, kDcnArgb8888, rounded}} : PresentCopyBacking{};
}

inline bool comparePreparedCopyBacking(const PresentCopyBacking &present, OriginalBacking backing, uint64_t bytes) {
    auto slice = present.slice;
    if (!present.transaction || !present.surface || !present.preparation || slice.offset ||
        slice.bytes != present.scanout.mappedBytes || !backing.readPage || bytes != slice.bytes ||
        livePresentPreparation(slice) != present.preparation)
        return false;

    for (uint64_t offset = 0; offset < slice.bytes; offset += kPageBytes) {
        uint64_t rendered = 0, presented = 0;
        if (!backing.readPage(backing.context, offset, &rendered) ||
            !readPinnedDescriptorPage(&slice, offset, &presented) || rendered != presented)
            return false;
    }
    return livePresentPreparation(slice) == present.preparation;
}

inline bool comparePreparedCopyBacking(const PresentCopyBacking &present, RenderDescriptorLease &render) {
    return comparePreparedCopyBacking(present, render.backing(), render.bytes());
}

}
