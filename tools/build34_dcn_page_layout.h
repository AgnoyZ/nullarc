#pragma once

#include <stddef.h>
#include <stdint.h>

namespace build34::dcn {

inline constexpr uint64_t kPageBytes = 4096;
inline constexpr uint64_t kAddressLimit = 1ull << 48;
inline constexpr uint64_t kMaxBackingBytes = 64ull << 20;
inline constexpr uint32_t kSurfaceBgra = 0x42475241;
inline constexpr uint32_t kDcnArgb8888 = 8;

struct SurfaceDescription {
    uint32_t pixelFormat;
    uint32_t width;
    uint32_t height;
    uint32_t bytesPerRow;
    uint32_t planeIndex;
    uint32_t planeCount;
    uint64_t allocationBytes;
    bool directlyImportedForRendering;
    bool backingRetained;
    bool linearLayout;
};

struct ScanoutSurface {
    uint32_t width;
    uint32_t height;
    uint32_t pitchPixelsMinusOne;
    uint32_t dcnPixelFormat;
    uint64_t mappedBytes;
};

inline bool validateScanoutSurface(const SurfaceDescription &surface, uint32_t displayWidth,
                                   uint32_t displayHeight, ScanoutSurface *result) {
    if (!result || !surface.directlyImportedForRendering || !surface.backingRetained ||
        !surface.linearLayout || surface.planeCount != 1 || surface.planeIndex != 0 ||
        surface.pixelFormat != kSurfaceBgra || !surface.width || !surface.height ||
        surface.width != displayWidth || surface.height != displayHeight ||
        !surface.bytesPerRow || surface.bytesPerRow % 4 || !surface.allocationBytes ||
        surface.allocationBytes > kMaxBackingBytes)
        return false;

    const uint64_t minRowBytes = static_cast<uint64_t>(surface.width) * 4;
    const uint64_t pitchPixels = surface.bytesPerRow / 4;
    const uint64_t usedBytes = static_cast<uint64_t>(surface.bytesPerRow) * surface.height;
    if (surface.bytesPerRow < minRowBytes || pitchPixels > 0x4000 ||
        usedBytes > surface.allocationBytes)
        return false;

    const uint64_t mappedBytes = (surface.allocationBytes + kPageBytes - 1) & ~(kPageBytes - 1);
    if (mappedBytes > kMaxBackingBytes)
        return false;

    *result = {surface.width, surface.height, static_cast<uint32_t>(pitchPixels - 1),
               kDcnArgb8888, mappedBytes};
    return true;
}

struct DmaRun {
    uint64_t backingOffset;
    uint64_t dmaAddress;
    uint64_t bytes;
};

struct FlatPageLayout {
    uint64_t firstLogicalPage;
    uint64_t lastLogicalPage;
    size_t entryCount;
    size_t tableBytes;
};

inline FlatPageLayout buildFlatPageLayout(uint64_t windowStart, uint64_t frameBytes,
                                          const DmaRun *runs, size_t runCount,
                                          uint64_t *pageAddresses, size_t pageCapacity) {
    if (!frameBytes || frameBytes > kMaxBackingBytes || windowStart >= kAddressLimit ||
        windowStart % kPageBytes || !runs || !pageAddresses)
        return {};

    const uint64_t mappedBytes = (frameBytes + kPageBytes - 1) & ~(kPageBytes - 1);
    const size_t entryCount = static_cast<size_t>(mappedBytes / kPageBytes);
    if (mappedBytes > kAddressLimit - windowStart || pageCapacity < entryCount ||
        !runCount || runCount > entryCount)
        return {};

    uint64_t covered = 0;
    for (size_t index = 0; index < runCount; ++index) {
        const auto &run = runs[index];
        if (run.backingOffset != covered || !run.bytes || run.bytes % kPageBytes ||
            run.bytes > mappedBytes - covered || !run.dmaAddress ||
            run.dmaAddress % kPageBytes || run.dmaAddress >= kAddressLimit ||
            run.bytes > kAddressLimit - run.dmaAddress)
            return {};
        covered += run.bytes;
    }
    if (covered != mappedBytes)
        return {};

    size_t entry = 0;
    for (size_t index = 0; index < runCount; ++index) {
        const auto &run = runs[index];
        for (uint64_t offset = 0; offset < run.bytes; offset += kPageBytes)
            pageAddresses[entry++] = run.dmaAddress + offset;
    }

    const uint64_t firstPage = windowStart / kPageBytes;
    return {firstPage, firstPage + entryCount - 1, entryCount, entryCount * sizeof(uint64_t)};
}

}  // namespace build34::dcn
