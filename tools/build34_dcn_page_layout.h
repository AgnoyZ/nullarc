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
    uint64_t planeOffset;
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
        !surface.linearLayout || surface.planeCount > 1 || surface.planeIndex || surface.planeOffset ||
        surface.pixelFormat != kSurfaceBgra || !surface.width || !surface.height ||
        surface.width != displayWidth || surface.height != displayHeight ||
        !surface.bytesPerRow || surface.bytesPerRow % 4)
        return false;

    const uint64_t minRowBytes = static_cast<uint64_t>(surface.width) * 4;
    const uint64_t pitchPixels = surface.bytesPerRow / 4;
    const uint64_t usedBytes = static_cast<uint64_t>(surface.bytesPerRow) * surface.height;
    if (surface.bytesPerRow < minRowBytes || pitchPixels > 0x4000 ||
        usedBytes > surface.allocationBytes || usedBytes > kMaxBackingBytes)
        return false;

    const uint64_t mappedBytes = (usedBytes + kPageBytes - 1) & ~(kPageBytes - 1);
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

inline bool validDmaSegment(uint64_t address, uint64_t bytes, uint64_t remaining) {
    return bytes && bytes % kPageBytes == 0 && bytes <= remaining &&
           address && address % kPageBytes == 0 && address < kAddressLimit &&
           bytes <= kAddressLimit - address;
}

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
        if (run.backingOffset != covered || !validDmaSegment(run.dmaAddress, run.bytes, mappedBytes - covered))
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

struct DmaSegment {
    uint64_t address;
    uint64_t bytes;
};

using ReadDmaBatch = bool (*)(void *context, uint64_t *offset, DmaSegment *segments, uint32_t *count);
using ResolveDmaPage = bool (*)(void *context, const void *mapper, uint64_t dmaAddress, uint64_t *physical);
using ReadOriginalPage = bool (*)(void *context, uint64_t backingOffset, uint64_t *physical);

struct PreparedDmaMapping {
    uint64_t bytes;
    const void *mapper;
    void *context;
    ReadDmaBatch readBatch;
    ResolveDmaPage resolvePage;
};

struct OriginalBacking {
    void *context;
    ReadOriginalPage readPage;
};

inline FlatPageLayout collectScanoutPages(uint64_t windowStart, const ScanoutSurface &surface,
                                          const PreparedDmaMapping &mapping, const void *deviceMapper,
                                          const OriginalBacking &backing,
                                          DmaRun *scratch, size_t runCapacity,
                                          uint64_t *pageAddresses, size_t pageCapacity) {
    const uint64_t bytes = surface.mappedBytes;
    if (!deviceMapper || mapping.mapper != deviceMapper || !mapping.readBatch || !mapping.resolvePage ||
        !backing.readPage || !scratch || !runCapacity || !pageAddresses || !bytes || bytes > kMaxBackingBytes ||
        bytes % kPageBytes || mapping.bytes != bytes || pageCapacity < bytes / kPageBytes ||
        windowStart % kPageBytes || windowStart >= kAddressLimit || bytes > kAddressLimit - windowStart)
        return {};

    uint64_t covered = 0;
    size_t runCount = 0;
    while (covered < bytes) {
        constexpr uint32_t batchSize = 8;
        DmaSegment segments[batchSize]{};
        const size_t available = runCapacity - runCount;
        const uint32_t capacity = available < batchSize ? static_cast<uint32_t>(available) : batchSize;
        uint32_t count = capacity;
        uint64_t next = covered;
        if (!capacity || !mapping.readBatch(mapping.context, &next, segments, &count) || !count || count > capacity)
            return {};

        for (uint32_t index = 0; index < count; ++index) {
            const auto &segment = segments[index];
            if (!validDmaSegment(segment.address, segment.bytes, bytes - covered))
                return {};
            scratch[runCount++] = {covered, segment.address, segment.bytes};
            covered += segment.bytes;
        }
        if (next != covered)
            return {};
    }

    for (size_t index = 0; index < runCount; ++index) {
        const auto &run = scratch[index];
        for (uint64_t offset = 0; offset < run.bytes; offset += kPageBytes) {
            uint64_t original = 0;
            uint64_t resolved = 0;
            if (!backing.readPage(backing.context, run.backingOffset + offset, &original) ||
                !original || original % kPageBytes ||
                !mapping.resolvePage(mapping.context, deviceMapper, run.dmaAddress + offset, &resolved) ||
                resolved != original)
                return {};
        }
    }

    return buildFlatPageLayout(windowStart, bytes, scratch, runCount, pageAddresses, pageCapacity);
}

}  // namespace build34::dcn
