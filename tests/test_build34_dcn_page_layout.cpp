#include "../tools/build34_dcn_page_layout.h"

#include <array>
#include <cassert>
#include <cstdio>
#include <vector>

using namespace build34::dcn;

static constexpr uint64_t kUnwritten = UINT64_MAX;

static SurfaceDescription bgraSurface() {
    return {kSurfaceBgra, 2560, 1600, 10240, 0, 1, 40ull << 20, true, true, true};
}

static void testSurfaceQualifications() {
    const SurfaceDescription surface = bgraSurface();
    ScanoutSurface scanout{};
    assert(validateScanoutSurface(surface, 2560, 1600, &scanout));
    assert(scanout.width == 2560 && scanout.height == 1600);
    assert(scanout.pitchPixelsMinusOne == 2559 && scanout.dcnPixelFormat == kDcnArgb8888);
    assert(scanout.mappedBytes == 40ull << 20);

    auto reject = [&](SurfaceDescription candidate, uint32_t width = 2560, uint32_t height = 1600) {
        ScanoutSurface unchanged{7, 11, 13, 17, 19};
        assert(!validateScanoutSurface(candidate, width, height, &unchanged));
        assert(unchanged.width == 7 && unchanged.height == 11 && unchanged.pitchPixelsMinusOne == 13);
        assert(unchanged.dcnPixelFormat == 17 && unchanged.mappedBytes == 19);
    };

    auto candidate = surface;
    candidate.pixelFormat = 0x6c313072;
    reject(candidate);
    candidate = surface;
    candidate.directlyImportedForRendering = false;
    reject(candidate);
    candidate = surface;
    candidate.backingRetained = false;
    reject(candidate);
    candidate = surface;
    candidate.linearLayout = false;
    reject(candidate);
    candidate = surface;
    candidate.planeIndex = 1;
    reject(candidate);
    candidate = surface;
    candidate.planeCount = 2;
    reject(candidate);
    reject(surface, 1920, 1080);
    candidate = surface;
    candidate.width = 0;
    reject(candidate);
    candidate = surface;
    candidate.height = 0;
    reject(candidate);
    candidate = surface;
    candidate.bytesPerRow = 0;
    reject(candidate);
    candidate = surface;
    candidate.bytesPerRow = 10241;
    reject(candidate);
    candidate = surface;
    candidate.bytesPerRow = 10236;
    reject(candidate);
    candidate = surface;
    candidate.bytesPerRow = 65540;
    reject(candidate);
    candidate = surface;
    candidate.allocationBytes = 0;
    reject(candidate);
    candidate = surface;
    candidate.allocationBytes = (uint64_t)candidate.bytesPerRow * candidate.height - 1;
    reject(candidate);
    candidate = surface;
    candidate.allocationBytes = kMaxBackingBytes + 1;
    reject(candidate);
    assert(!validateScanoutSurface(surface, 2560, 1600, nullptr));

    candidate = surface;
    candidate.bytesPerRow = 2560 * 4 + 64;
    candidate.allocationBytes = (uint64_t)candidate.bytesPerRow * candidate.height;
    ScanoutSurface padded{};
    assert(validateScanoutSurface(candidate, 2560, 1600, &padded));
    assert(padded.pitchPixelsMinusOne == 2575);
    assert(padded.mappedBytes == ((candidate.allocationBytes + kPageBytes - 1) & ~(kPageBytes - 1)));
}

static void expectRefusal(uint64_t start, uint64_t bytes, const DmaRun *runs, size_t count,
                           size_t capacity = 4) {
    std::array<uint64_t, 4> pages;
    pages.fill(kUnwritten);
    const auto layout = buildFlatPageLayout(start, bytes, runs, count, pages.data(), capacity);
    assert(!layout.firstLogicalPage && !layout.lastLogicalPage && !layout.entryCount && !layout.tableBytes);
    for (uint64_t address : pages)
        assert(address == kUnwritten);
}

static void testFragmentedBacking() {
    const uint64_t start = (1ull << 44) - kPageBytes;
    const DmaRun runs[] = {{0, 0x40000, kPageBytes},
                           {kPageBytes, 0x20000, 2 * kPageBytes},
                           {3 * kPageBytes, 0x80000, kPageBytes}};
    std::array<uint64_t, 5> pages;
    pages.fill(kUnwritten);
    const auto layout = buildFlatPageLayout(start, 3 * kPageBytes + 1, runs, 3, pages.data(), pages.size());
    assert(layout.firstLogicalPage == UINT32_MAX);
    assert(layout.lastLogicalPage == (1ull << 32) + 2);
    assert(layout.entryCount == 4 && layout.tableBytes == 32);
    const std::array<uint64_t, 5> expected = {0x40000, 0x20000, 0x21000, 0x80000, kUnwritten};
    assert(pages == expected);
}

static void testAddressAndCapacityEdges() {
    const uint64_t lastAddress = kAddressLimit - kPageBytes;
    const DmaRun edge = {0, lastAddress, kPageBytes};
    uint64_t page = kUnwritten;
    const auto layout = buildFlatPageLayout(lastAddress, 1, &edge, 1, &page, 1);
    assert(layout.firstLogicalPage == (1ull << 36) - 1);
    assert(layout.firstLogicalPage == layout.lastLogicalPage);
    assert(layout.entryCount == 1 && layout.tableBytes == 8 && page == lastAddress);

    expectRefusal(lastAddress, kPageBytes + 1, &edge, 1);
    expectRefusal(lastAddress + 1, 1, &edge, 1);
    expectRefusal(kAddressLimit, 1, &edge, 1);
    expectRefusal(UINT64_MAX, 1, &edge, 1);
    expectRefusal(0, 0, &edge, 1);
    expectRefusal(0, UINT64_MAX, &edge, 1);
    expectRefusal(0, 1, &edge, 1, 0);
    expectRefusal(0, 1, &edge, 0);
    expectRefusal(0, 1, &edge, 2);
    expectRefusal(0, 1, nullptr, 1);
    assert(!buildFlatPageLayout(0, 1, &edge, 1, nullptr, 1).entryCount);
}

static void testRefusesMalformedRunsBeforeWriting() {
    const DmaRun badSecondRuns[] = {
        {0, 0x20000, kPageBytes},
        {2 * kPageBytes, 0x20000, kPageBytes},
        {kPageBytes, 0x20000, 0},
        {kPageBytes, 0x20000, kPageBytes - 1},
        {kPageBytes, 0x20000, 3 * kPageBytes},
        {kPageBytes, 0x20000, UINT64_MAX & ~(kPageBytes - 1)},
        {kPageBytes, 0, kPageBytes},
        {kPageBytes, 0x20001, kPageBytes},
        {kPageBytes, kAddressLimit, kPageBytes},
        {kPageBytes, kAddressLimit - kPageBytes, 2 * kPageBytes},
        {kPageBytes, UINT64_MAX & ~(kPageBytes - 1), kPageBytes},
    };
    for (const auto &bad : badSecondRuns) {
        const DmaRun runs[] = {{0, 0x40000, kPageBytes}, bad};
        expectRefusal(0, 3 * kPageBytes, runs, 2);
    }
    const DmaRun shortRun = {0, 0x40000, kPageBytes};
    expectRefusal(0, kPageBytes + 1, &shortRun, 1);
    const DmaRun extraRun = {0, 0x40000, 2 * kPageBytes};
    expectRefusal(0, 1, &extraRun, 1);
}

static void testPanelAndBoundedWork() {
    const uint64_t stride = 2560 * 4;
    const uint64_t bytes = stride * 1600;
    const uint64_t windowStart = 0x100000000;
    const size_t count = bytes / kPageBytes;
    std::vector<DmaRun> runs(count);
    std::vector<uint64_t> pages(count, kUnwritten);
    for (size_t index = 0; index < count; ++index)
        runs[index] = {index * kPageBytes, 0x80000000 + (count - index) * 3 * kPageBytes, kPageBytes};
    const auto frame = buildFlatPageLayout(windowStart, bytes, runs.data(), count, pages.data(), count);
    assert(frame.entryCount == 4000 && frame.tableBytes == 32000);
    assert(frame.firstLogicalPage == windowStart / kPageBytes);
    assert(frame.lastLogicalPage - frame.firstLogicalPage + 1 == count);
    for (size_t index = 0; index < count; ++index)
        assert(pages[index] == runs[index].dmaAddress);

    const DmaRun largest = {0, 0x80000000, kMaxBackingBytes};
    pages.assign(kMaxBackingBytes / kPageBytes + 1, kUnwritten);
    const auto bound = buildFlatPageLayout(windowStart, kMaxBackingBytes, &largest, 1, pages.data(), pages.size());
    assert(bound.entryCount == pages.size() - 1 && bound.tableBytes == 128 * 1024);
    assert(pages.front() == largest.dmaAddress && pages.back() == kUnwritten);
    assert(pages[bound.entryCount - 1] == largest.dmaAddress + kMaxBackingBytes - kPageBytes);
    const DmaRun oversized = {0, largest.dmaAddress, kMaxBackingBytes + kPageBytes};
    pages.assign(pages.size(), kUnwritten);
    assert(!buildFlatPageLayout(windowStart, kMaxBackingBytes + 1, &oversized, 1,
                                pages.data(), pages.size()).entryCount);
    for (uint64_t address : pages)
        assert(address == kUnwritten);
}

int main() {
    testSurfaceQualifications();
    testFragmentedBacking();
    testAddressAndCapacityEdges();
    testRefusesMalformedRunsBeforeWriting();
    testPanelAndBoundedWork();
    std::puts("[PASS] offline build34 DCN DMA page layout");
}
