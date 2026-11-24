#pragma once

#include "build34_dcn_render_lease.h"

namespace build34::dcn {

struct RenderMapIdentity {
    const void *client;
    uint64_t generation;
};

struct BoundRenderImage {
    RenderMapIdentity mapping;
    const void *surface;
    uint64_t gpuAddress;
    uint64_t boOffset;
    uint32_t pixelFormat;
    uint32_t width;
    uint32_t height;
    uint32_t bytesPerRow;
};

struct LiveHostRenderMap {
    RenderMapIdentity identity;
    IOMemoryDescriptor *descriptor;
    uint64_t preparation;
    uint64_t boBytes;
    uint64_t gpuAddress;
    uint64_t boOffset;
    uint64_t bytes;
};

inline bool acquireBoundRenderBacking(const BoundRenderImage &image, const LiveHostRenderMap &mapping,
                                      const void *presentSurface, const ScanoutSurface &scanout,
                                      RenderDescriptorLease &lease) {
    if (!presentSurface || image.surface != presentSurface || !image.mapping.client ||
        image.mapping.client != mapping.identity.client || !image.mapping.generation ||
        image.mapping.generation == UINT64_MAX || image.mapping.generation != mapping.identity.generation ||
        !mapping.descriptor || image.pixelFormat != kSurfaceBgra || scanout.dcnPixelFormat != kDcnArgb8888 ||
        !image.width || image.width != scanout.width || !image.height || image.height != scanout.height ||
        image.bytesPerRow % 4 || image.bytesPerRow / 4 != uint64_t{scanout.pitchPixelsMinusOne} + 1 ||
        scanout.pitchPixelsMinusOne >= 0x4000 || image.bytesPerRow < uint64_t{image.width} * 4)
        return false;

    const uint64_t imageBytes = uint64_t{image.bytesPerRow} * image.height;
    if (imageBytes > kMaxBackingBytes ||
        scanout.mappedBytes != ((imageBytes + kPageBytes - 1) & ~(kPageBytes - 1)))
        return false;

    constexpr uint64_t renderVaLimit = 1ull << 48;
    if (!mapping.bytes || (mapping.gpuAddress | mapping.boOffset | mapping.bytes | mapping.boBytes |
                          image.gpuAddress | image.boOffset) % kPageBytes ||
        mapping.gpuAddress < 0x10000 || mapping.gpuAddress >= renderVaLimit ||
        mapping.bytes > renderVaLimit - mapping.gpuAddress || image.gpuAddress < mapping.gpuAddress ||
        mapping.boOffset > mapping.boBytes || mapping.bytes > mapping.boBytes - mapping.boOffset ||
        mapping.boBytes > kMaxBackingBytes)
        return false;

    const uint64_t offset = image.gpuAddress - mapping.gpuAddress;
    if (offset >= mapping.bytes || scanout.mappedBytes > mapping.bytes - offset ||
        image.boOffset != mapping.boOffset + offset || mapping.boBytes != mapping.descriptor->getLength())
        return false;

    return lease.acquire({mapping.descriptor, image.boOffset, scanout.mappedBytes}, mapping.preparation);
}

}  // namespace build34::dcn
