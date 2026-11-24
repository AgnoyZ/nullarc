#include "../tools/build34_dcn_page_layout.h"

#include <array>
#include <cassert>
#include <cstdio>
#include <vector>

using namespace build34::dcn;

static constexpr uint64_t kUnwritten = UINT64_MAX;

static SurfaceDescription bgraSurface() {
    return {kSurfaceBgra, 2560, 1600, 10240, 0, 0, 0, 40ull << 20, true, true, true};
}

static void testSurfaceQualifications() {
    const SurfaceDescription surface = bgraSurface();
    ScanoutSurface scanout{};
    assert(validateScanoutSurface(surface, 2560, 1600, &scanout));
    assert(scanout.width == 2560 && scanout.height == 1600);
    assert(scanout.pitchPixelsMinusOne == 2559 && scanout.dcnPixelFormat == kDcnArgb8888);
    assert(scanout.mappedBytes == 4000 * kPageBytes);

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
    candidate.planeCount = 1;
    assert(validateScanoutSurface(candidate, 2560, 1600, &scanout));
    candidate.planeOffset = kPageBytes;
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
    candidate.height = 7000;
    candidate.allocationBytes = (uint64_t)candidate.bytesPerRow * candidate.height;
    reject(candidate, 2560, candidate.height);
    assert(!validateScanoutSurface(surface, 2560, 1600, nullptr));

    candidate = surface;
    candidate.bytesPerRow = 2560 * 4 + 64;
    candidate.allocationBytes = (uint64_t)candidate.bytesPerRow * candidate.height;
    ScanoutSurface padded{};
    assert(validateScanoutSurface(candidate, 2560, 1600, &padded));
    assert(padded.pitchPixelsMinusOne == 2575);
    assert(padded.mappedBytes == ((candidate.allocationBytes + kPageBytes - 1) & ~(kPageBytes - 1)));
}

enum class BatchResult { Normal, Error, Empty, Excess, WrongOffset, TooLong, Unaligned, Short };

static constexpr unsigned kFixtureMapper = 1;
static constexpr uint64_t kDmaBase = 0x80000000;

struct PhysicalPages {
    const uint64_t *addresses;
    size_t count;
    size_t calls = 0;
};

static bool lookupPage(PhysicalPages &pages, uint64_t offset, uint64_t *physical) {
    assert(offset % kPageBytes == 0);
    const size_t index = offset / kPageBytes;
    assert(index < pages.count && index == pages.calls);
    ++pages.calls;
    if (pages.addresses[index] == kUnwritten)
        return false;
    *physical = pages.addresses[index];
    return true;
}

struct BatchSource {
    uint64_t total;
    BatchResult result;
    PhysicalPages targets;
    unsigned calls = 0;
    bool contiguous = false;
};

static bool resolvePage(void *context, const void *mapper, uint64_t address, uint64_t *physical) {
    auto &source = *static_cast<BatchSource *>(context);
    const uint64_t stride = source.contiguous ? 1 : 3;
    assert(mapper == &kFixtureMapper && address >= kDmaBase && (address - kDmaBase) % stride == 0);
    return lookupPage(source.targets, (address - kDmaBase) / stride, physical);
}

static bool readOriginalPage(void *context, uint64_t offset, uint64_t *physical) {
    return lookupPage(*static_cast<PhysicalPages *>(context), offset, physical);
}

static bool readBatch(void *context, uint64_t *offset, DmaSegment *segments, uint32_t *count) {
    auto &source = *static_cast<BatchSource *>(context);
    assert(*count && *count <= 8);
    assert(*offset <= source.total && *offset % kPageBytes == 0);
    ++source.calls;
    if (*offset == source.total)
        return false;
    const uint32_t capacity = *count;
    *count = 0;
    while (*offset < source.total && *count < capacity) {
        const uint64_t bytes = source.contiguous ? source.total - *offset : kPageBytes;
        segments[(*count)++] = {kDmaBase + *offset * (source.contiguous ? 1 : 3), bytes};
        *offset += bytes;
    }
    if (source.calls == 2) {
        switch (source.result) {
        case BatchResult::Normal: break;
        case BatchResult::Error: return false;
        case BatchResult::Empty: *count = 0; break;
        case BatchResult::Excess: *count = capacity + 1; break;
        case BatchResult::WrongOffset: *offset -= kPageBytes; break;
        case BatchResult::TooLong: segments[*count - 1].bytes = source.total; break;
        case BatchResult::Unaligned: ++segments[*count - 1].address; break;
        case BatchResult::Short: source.total = *offset; break;
        }
    }
    return true;
}

static void testSegmentBatches() {
    ScanoutSurface surface{};
    assert(validateScanoutSurface(bgraSurface(), 2560, 1600, &surface));
    const uint64_t windowStart = 0x100000000;
    const size_t pageCount = surface.mappedBytes / kPageBytes;
    std::vector<DmaRun> runs(pageCount);
    std::vector<uint64_t> pages(pageCount + 1, kUnwritten);
    std::vector<uint64_t> originals(4025);
    for (size_t index = 0; index < originals.size(); ++index)
        originals[index] = 0x10000000 + index * 5 * kPageBytes;
    const auto targets = originals;
    const auto collect = [&](BatchSource &source, uint64_t preparedBytes, size_t runCapacity, size_t pageCapacity) {
        PhysicalPages originalPages{originals.data(), originals.size()};
        const OriginalBacking backing{&originalPages, readOriginalPage};
        const PreparedDmaMapping mapping{preparedBytes, &kFixtureMapper, &source, readBatch, resolvePage};
        const auto layout = collectScanoutPages(windowStart, surface, mapping, &kFixtureMapper, backing,
                                                runs.data(), runCapacity, pages.data(), pageCapacity);
        assert(originalPages.calls == layout.entryCount && source.targets.calls == layout.entryCount);
        return layout;
    };
    BatchSource complete{surface.mappedBytes, BatchResult::Normal, {targets.data(), targets.size()}};
    const auto layout = collect(complete, surface.mappedBytes, runs.size(), pages.size());
    assert(layout.entryCount == 4000 && layout.tableBytes == 32000 && complete.calls == 500);
    assert(layout.firstLogicalPage == windowStart / kPageBytes);
    for (size_t index = 0; index < pageCount; ++index)
        assert(pages[index] == kDmaBase + index * 3 * kPageBytes && pages[index] != originals[index]);
    assert(pages.back() == kUnwritten);

    const auto refuse = [&](BatchResult result, uint64_t preparedBytes, size_t runCapacity,
                            size_t pageCapacity, unsigned expectedCalls) {
        pages.assign(pages.size(), kUnwritten);
        BatchSource source{surface.mappedBytes, result, {targets.data(), targets.size()}};
        assert(!collect(source, preparedBytes, runCapacity, pageCapacity).entryCount);
        assert(source.calls == expectedCalls);
        for (uint64_t address : pages)
            assert(address == kUnwritten);
    };
    for (const auto result : {BatchResult::Error, BatchResult::Empty, BatchResult::Excess, BatchResult::WrongOffset,
                              BatchResult::TooLong, BatchResult::Unaligned})
        refuse(result, surface.mappedBytes, runs.size(), pages.size(), 2);
    refuse(BatchResult::Short, surface.mappedBytes, runs.size(), pages.size(), 3);
    refuse(BatchResult::Normal, surface.mappedBytes, 9, pages.size(), 2);
    refuse(BatchResult::Normal, surface.mappedBytes - kPageBytes, runs.size(), pages.size(), 0);
    refuse(BatchResult::Normal, surface.mappedBytes + kPageBytes, runs.size(), pages.size(), 0);
    refuse(BatchResult::Normal, surface.mappedBytes, runs.size(), pageCount - 1, 0);

    auto padded = bgraSurface();
    padded.bytesPerRow += 64;
    assert(validateScanoutSurface(padded, 2560, 1600, &surface));
    assert(surface.mappedBytes == 4025 * kPageBytes);
    runs.resize(4025);
    pages.assign(4026, kUnwritten);
    BatchSource tail{surface.mappedBytes, BatchResult::Normal, {targets.data(), targets.size()}};
    const auto paddedLayout = collect(tail, surface.mappedBytes, runs.size(), pages.size());
    assert(paddedLayout.entryCount == 4025 && tail.calls == 504);
    assert(pages[4024] == kDmaBase + 4024 * 3 * kPageBytes && pages.back() == kUnwritten);
}

static void testPageIdentity() {
    const ScanoutSurface surface{1024, 3, 1023, kDcnArgb8888, 3 * kPageBytes};
    const std::array<uint64_t, 3> expected{0x10000, 0x50000, 0x20000};
    auto originals = expected;
    auto targets = expected;
    PhysicalPages originalPages{originals.data(), originals.size()};
    BatchSource source{surface.mappedBytes, BatchResult::Normal, {targets.data(), targets.size()}, 0, true};
    OriginalBacking backing{&originalPages, readOriginalPage};
    PreparedDmaMapping mapping{surface.mappedBytes, &kFixtureMapper, &source, readBatch, resolvePage};
    DmaRun scratch{};
    std::array<uint64_t, 4> pages;

    const auto check = [&](const void *deviceMapper, size_t batches, size_t reads, size_t resolutions,
                           bool accept = false) {
        originalPages.calls = source.calls = source.targets.calls = 0;
        pages.fill(kUnwritten);
        const auto layout = collectScanoutPages(0, surface, mapping, deviceMapper, backing,
                                                &scratch, 1, pages.data(), pages.size());
        assert(source.calls == batches && originalPages.calls == reads && source.targets.calls == resolutions);
        if (accept) {
            assert(layout.entryCount == 3 && layout.tableBytes == 24);
            assert(pages[0] == kDmaBase && pages[1] == kDmaBase + kPageBytes);
            assert(pages[2] == kDmaBase + 2 * kPageBytes && pages[3] == kUnwritten);
        } else {
            assert(!layout.firstLogicalPage && !layout.lastLogicalPage && !layout.entryCount && !layout.tableBytes);
            for (uint64_t address : pages)
                assert(address == kUnwritten);
        }
    };

    check(&kFixtureMapper, 1, 3, 3, true);
    targets[1] = 0x90000;
    check(&kFixtureMapper, 1, 2, 2);
    targets = {expected[1], expected[0], expected[2]};
    check(&kFixtureMapper, 1, 1, 1);
    targets = {expected[0], expected[1], expected[1]};
    check(&kFixtureMapper, 1, 3, 3);
    targets = expected;
    for (uint64_t invalid : {kUnwritten, uint64_t{0}, expected[2] + 1}) {
        targets[2] = invalid;
        check(&kFixtureMapper, 1, 3, 3);
    }
    targets = expected;
    for (uint64_t invalid : {kUnwritten, uint64_t{0}, expected[2] + 1}) {
        originals[2] = invalid;
        check(&kFixtureMapper, 1, 3, 2);
    }
    originals = expected;

    const unsigned otherMapper = 2;
    check(nullptr, 0, 0, 0);
    check(&otherMapper, 0, 0, 0);
    mapping.mapper = nullptr;
    check(&kFixtureMapper, 0, 0, 0);
    mapping.mapper = &kFixtureMapper;
    mapping.resolvePage = nullptr;
    check(&kFixtureMapper, 0, 0, 0);
    mapping.resolvePage = resolvePage;
    backing.readPage = nullptr;
    check(&kFixtureMapper, 0, 0, 0);
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
    testSegmentBatches();
    testPageIdentity();
    testFragmentedBacking();
    testAddressAndCapacityEdges();
    testRefusesMalformedRunsBeforeWriting();
    testPanelAndBoundedWork();
    std::puts("[PASS] offline build34 DCN DMA page layout");
}
