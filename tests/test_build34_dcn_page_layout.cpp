#include "../tools/build34_dcn_render_binding.h"
#include "../tools/build34_dcn_physical_pages.h"

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

static void testManagedWriteHoldsRequireCanonicalPages() {
    DcnManagedWriteHolds holds;
    DcnManagedWriteExclusion blocked{};
    const std::array<uint64_t, 3> valid{0x10000, 0x20000, 0x30000};
    const std::array<std::array<uint64_t, 3>, 4> malformed{{
        {{0x10000, 0x30000, 0x20000}},
        {{0x10000, 0x20000, 0x20000}},
        {{0x10000, 0x20001, 0x30000}},
        {{0, 0x20000, 0x30000}},
    }};

    assert(!holds.acquire({}, blocked));
    for (const auto &pages : malformed) {
        assert(!holds.acquire({pages.data(), pages.size()}, blocked));
        assert(!holds.active());
        for (uint64_t page : valid)
            assert(!holds.excludes(page));
    }
    assert(!holds.acquire({valid.data(), kMaxBackingBytes / kPageBytes + 1}, blocked));
    assert(holds.acquire({valid.data(), valid.size()}, blocked));
    assert(holds.active());
    for (uint64_t page : valid)
        assert(holds.excludes(page));

    const std::array<uint64_t, 2> overlapping{0x20000, 0x40000};
    assert(!holds.acquire({overlapping.data(), overlapping.size()}, blocked));
    assert(holds.active() && holds.excludes(0x20000));
    holds.release({valid.data(), valid.size()});
    assert(!holds.active() && !holds.excludes(0x20000));
}

enum class BatchResult { Normal, Error, Empty, Excess, WrongOffset, TooLong, Unaligned, Short };

static constexpr unsigned kFixtureMapper = 1;
static constexpr uint64_t kDmaBase = 0x80000000;

struct PhysicalPages {
    const uint64_t *addresses;
    size_t count;
    size_t calls = 0;
};

struct DescriptorFixture final : IOMemoryDescriptor {
    const uint64_t *pages;
    uint64_t bytes;
    uint64_t contiguous = kPageBytes;
    unsigned reads = 0;
    uint64_t preparation = 42;
    uint64_t replacementPreparation = 0;
    unsigned references = 1;
    unsigned wires = 1;
    unsigned prepares = 0;
    unsigned completes = 0;
    IOReturn prepareResult = kIOReturnSuccess;
    IOReturn completeResult = kIOReturnSuccess;
    void (*onComplete)(void *) = nullptr;
    void *completeContext = nullptr;

    DescriptorFixture(const uint64_t *addresses, uint64_t length) : pages(addresses), bytes(length) {}

    IOByteCount getLength() const override { return bytes; }

    uint64_t getPhysicalSegment(IOByteCount offset, IOByteCount *length, unsigned options) override {
        assert(references && wires && options == kIOMemoryMapperNone && offset < bytes && offset % kPageBytes == 0);
        ++reads;
        *length = contiguous;
        return pages[offset / kPageBytes];
    }

    uint64_t getPreparationID() override { return wires ? preparation : 0; }

    IOReturn prepare() override {
        assert(references);
        ++prepares;
        if (prepareResult == kIOReturnSuccess) {
            ++wires;
            if (replacementPreparation)
                preparation = replacementPreparation;
        }
        return prepareResult;
    }

    IOReturn complete() override {
        assert(references && wires);
        ++completes;
        if (onComplete)
            onComplete(completeContext);
        --wires;
        return completeResult;
    }

    void retain() override { assert(references); ++references; }
    void release() override { assert(references); --references; }
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
    const auto presented = originals;
    const auto targets = originals;
    const auto collect = [&](BatchSource &source, uint64_t preparedBytes, size_t runCapacity, size_t pageCapacity) {
        PhysicalPages renderPages{originals.data(), originals.size()};
        PhysicalPages presentPages{presented.data(), presented.size()};
        const OriginalBacking renderBacking{&renderPages, readOriginalPage};
        const OriginalBacking presentBacking{&presentPages, readOriginalPage};
        const PreparedDmaMapping mapping{preparedBytes, &kFixtureMapper, &source, readBatch, resolvePage};
        const auto layout = collectScanoutPages(windowStart, surface, mapping, &kFixtureMapper,
                                                renderBacking, presentBacking,
                                                runs.data(), runCapacity, pages.data(), pageCapacity);
        assert(renderPages.calls == layout.entryCount && presentPages.calls == layout.entryCount);
        assert(source.targets.calls == layout.entryCount);
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

struct TlbSamples {
    const RenderTlbSample *samples;
    size_t size;
    size_t calls = 0;

    static bool read(void *context, RenderTlbSample *sample) {
        auto &source = *static_cast<TlbSamples *>(context);
        const size_t index = source.calls++;
        if (index >= source.size)
            return false;
        *sample = source.samples[index];
        return true;
    }
};

static constexpr uint32_t kFixtureAck = 1u << 8;

static RenderTlbAck confirmedTlb(const RenderVmTranslation &translation) {
    const RenderTlbSample samples[] = {{translation, 0, 0}, {translation, 1000, kFixtureAck}};
    TlbSamples source{samples, 2};
    const auto ack = RenderTlbAck::observe(translation, &source, TlbSamples::read);
    assert(ack.matches(translation) && source.calls == 2);
    return ack;
}

static void testRenderTlbAck() {
    const unsigned client = 1, provider = 2, other = 3;
    const RenderVmTranslation translation{{&client, 17}, &provider, 2, 3, 4, 5, 1, 8};
    const RenderVmTranslation changes[] = {
        {{&other, 17}, &provider, 2, 3, 4, 5, 1, 8}, {{&client, 18}, &provider, 2, 3, 4, 5, 1, 8},
        {{&client, 17}, &other, 2, 3, 4, 5, 1, 8}, {{&client, 17}, &provider, 3, 3, 4, 5, 1, 8},
        {{&client, 17}, &provider, 2, 4, 4, 5, 1, 8}, {{&client, 17}, &provider, 2, 3, 5, 5, 1, 8},
        {{&client, 17}, &provider, 2, 3, 4, 6, 1, 8}, {{&client, 17}, &provider, 2, 3, 4, 5, 2, 8},
        {{&client, 17}, &provider, 2, 3, 4, 5, 1, 9},
    };
    const auto observe = [&](const RenderTlbSample *samples, size_t size, size_t expectedCalls) {
        TlbSamples source{samples, size};
        const auto ack = RenderTlbAck::observe(translation, &source, TlbSamples::read);
        assert(source.calls == expectedCalls);
        return ack;
    };
    const RenderTlbSample ordered[] = {{translation, 0, kFixtureAck}, {translation, 1000, 0},
                                      {translation, 2000, 1u << 9}, {translation, 999999, kFixtureAck}};
    const auto valid = observe(ordered, 4, 4);
    assert(valid.matches(translation));
    assert(!observe(ordered, 1, 2).matches(translation));
    assert(!observe(ordered, 3, 4).matches(translation));
    for (const auto &changed : changes) {
        const RenderTlbSample rebound[] = {{translation, 1000, 0}, {changed, 2000, kFixtureAck}};
        assert(!observe(rebound, 2, 2).matches(translation));
        assert(!valid.matches(changed));
    }

    const RenderTlbSample late[] = {{translation, 999999, 0}, {translation, 1000000, kFixtureAck}};
    assert(!observe(late, 2, 2).matches(translation));
    const RenderTlbSample rewound[] = {{translation, 1000, 0}, {translation, 999, kFixtureAck}};
    assert(!observe(rewound, 2, 2).matches(translation));
    const RenderTlbSample failedRead[] = {{translation, 0, 0}, {translation, 1000, UINT32_MAX}};
    assert(!observe(failedRead, 2, 2).matches(translation));
    const std::vector<RenderTlbSample> stuck(1001, {translation, 0, kFixtureAck});
    assert(!observe(stuck.data(), stuck.size(), 1000).matches(translation));

    TlbSamples unused{ordered, 4};
    auto invalid = translation;
    invalid.vmid = 32;
    assert(!RenderTlbAck::observe(invalid, &unused, TlbSamples::read).matches(invalid));
    invalid = translation;
    invalid.invalidateGeneration = 0;
    assert(!RenderTlbAck::observe(invalid, &unused, TlbSamples::read).matches(invalid));
    invalid = translation;
    invalid.bindingGeneration = UINT64_MAX;
    assert(!RenderTlbAck::observe(invalid, &unused, TlbSamples::read).matches(invalid));
    assert(!unused.calls);
}

static void testPageIdentity() {
    const ScanoutSurface surface{1024, 3, 1023, kDcnArgb8888, 3 * kPageBytes};
    const std::array<uint64_t, 3> expected{0x10000, 0x50000, 0x20000};
    auto rendered = expected;
    auto presented = expected;
    auto targets = expected;
    DescriptorFixture renderPages{rendered.data(), surface.mappedBytes};
    DescriptorFixture presentPages{presented.data(), surface.mappedBytes};
    PinnedDescriptorSlice presentSlice{&presentPages, 0, surface.mappedBytes};
    BatchSource source{surface.mappedBytes, BatchResult::Normal, {targets.data(), targets.size()}, 0, true};
    RenderDescriptorLease renderLease;
    const RenderVmTranslation translation{{&renderPages, 17}, &kFixtureMapper, 2, 3, 4, 5, 1, 8};
    const BoundRenderImage image{translation, &presentPages, 0x80000, 0, kSurfaceBgra, 1024, 3, 4096};
    const LiveHostRenderMap mappingSnapshot{translation, &renderPages, renderPages.preparation, surface.mappedBytes,
                                          image.gpuAddress, 0, surface.mappedBytes};
    assert(acquireBoundRenderBacking(image, mappingSnapshot, confirmedTlb(translation), &presentPages, surface, renderLease));
    assert(renderPages.complete() == kIOReturnSuccess);
    renderPages.release();
    OriginalBacking renderBacking = renderLease.backing();
    OriginalBacking presentBacking{&presentSlice, readPinnedDescriptorPage};
    PreparedDmaMapping mapping{surface.mappedBytes, &kFixtureMapper, &source, readBatch, resolvePage};
    DmaRun scratch{};
    std::array<uint64_t, 4> pages;

    const auto check = [&](const void *deviceMapper, size_t batches, size_t renderReads, size_t presentReads,
                           size_t resolutions, bool accept = false) {
        renderPages.reads = presentPages.reads = source.calls = source.targets.calls = 0;
        pages.fill(kUnwritten);
        const auto layout = collectScanoutPages(0, surface, mapping, deviceMapper, renderBacking, presentBacking,
                                                &scratch, 1, pages.data(), pages.size());
        assert(source.calls == batches && source.targets.calls == resolutions);
        assert(renderPages.reads == renderReads && presentPages.reads == presentReads);
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

    check(&kFixtureMapper, 1, 3, 3, 3, true);
    targets[1] = 0x90000;
    check(&kFixtureMapper, 1, 2, 2, 2);
    targets = {expected[1], expected[0], expected[2]};
    check(&kFixtureMapper, 1, 1, 1, 1);
    targets = {expected[0], expected[1], expected[1]};
    check(&kFixtureMapper, 1, 3, 3, 3);
    targets = expected;
    for (uint64_t invalid : {kUnwritten, uint64_t{0}, expected[2] + 1}) {
        targets[2] = invalid;
        check(&kFixtureMapper, 1, 3, 3, 3);
    }
    targets = expected;
    for (uint64_t invalid : {kUnwritten, uint64_t{0}, expected[2] + 1}) {
        rendered[2] = invalid;
        check(&kFixtureMapper, 1, 3, 2, 2);
        rendered = expected;
        presented[2] = invalid;
        check(&kFixtureMapper, 1, 3, 3, 2);
    }
    presented[2] = 0xa0000;
    check(&kFixtureMapper, 1, 3, 3, 2);
    targets = presented;
    check(&kFixtureMapper, 1, 3, 3, 2);
    presented = targets = expected;
    --presentPages.bytes;
    check(&kFixtureMapper, 1, 1, 0, 0);
    ++presentPages.bytes;
    --presentPages.contiguous;
    check(&kFixtureMapper, 1, 1, 1, 0);
    ++presentPages.contiguous;

    const unsigned otherMapper = 2;
    check(nullptr, 0, 0, 0, 0);
    check(&otherMapper, 0, 0, 0, 0);
    mapping.mapper = nullptr;
    check(&kFixtureMapper, 0, 0, 0, 0);
    mapping.mapper = &kFixtureMapper;
    mapping.resolvePage = nullptr;
    check(&kFixtureMapper, 0, 0, 0, 0);
    mapping.resolvePage = resolvePage;
    renderBacking.readPage = nullptr;
    check(&kFixtureMapper, 0, 0, 0, 0);
    renderBacking = renderLease.backing();
    presentBacking.readPage = nullptr;
    check(&kFixtureMapper, 0, 0, 0, 0);
    assert(renderLease.releaseAfterRetirement());
    assert(!renderPages.references && !renderPages.wires);
}

static void testDescriptorSlice() {
    const uint64_t addresses[] = {0xa0000, 0x70000, 0x210000, 0x4000};
    DescriptorFixture descriptor{addresses, 4 * kPageBytes};
    PinnedDescriptorSlice slice{&descriptor, kPageBytes, 3 * kPageBytes};
    uint64_t physical = kUnwritten;
    assert(readPinnedDescriptorPage(&slice, 0, &physical) && physical == addresses[1]);
    assert(readPinnedDescriptorPage(&slice, 2 * kPageBytes, &physical) && physical == addresses[3]);
    assert(descriptor.reads == 2);

    const auto refuse = [&](PinnedDescriptorSlice candidate, uint64_t offset = 0) {
        physical = kUnwritten;
        assert(!readPinnedDescriptorPage(&candidate, offset, &physical) && physical == kUnwritten);
    };
    assert(!readPinnedDescriptorPage(nullptr, 0, &physical));
    assert(!readPinnedDescriptorPage(&slice, 0, nullptr));
    refuse({nullptr, 0, kPageBytes});
    refuse({&descriptor, 0, 0});
    refuse({&descriptor, 0, kPageBytes - 1});
    refuse({&descriptor, 0, 2 * kPageBytes - 1});
    refuse({&descriptor, 0, kMaxBackingBytes + kPageBytes});
    refuse({&descriptor, 1, kPageBytes});
    refuse({&descriptor, 2 * kPageBytes, 3 * kPageBytes});
    refuse({&descriptor, UINT64_MAX & ~(kPageBytes - 1), 2 * kPageBytes});
    refuse(slice, 1);
    refuse(slice, slice.bytes);
    refuse(slice, UINT64_MAX & ~(kPageBytes - 1));
    assert(descriptor.reads == 2);
    descriptor.contiguous = 0;
    refuse(slice);
    assert(descriptor.reads == 3);
}

static void testRenderLease() {
    const uint64_t addresses[] = {0x30000, 0x70000};
    constexpr uint64_t bytes = kPageBytes;
    for (const bool ownerReleasesFirst : {false, true}) {
        DescriptorFixture descriptor{addresses, 2 * bytes};
        PinnedDescriptorSlice slice{&descriptor, bytes, bytes};
        RenderDescriptorLease lease;
        assert(!lease.backing().readPage && !lease.releaseAfterRetirement());
        for (const uint64_t invalid : {uint64_t{0}, uint64_t{1}, kIOPreparationIDAlwaysPrepared, UINT64_MAX, uint64_t{41}})
            assert(!lease.acquire(slice, invalid));
        assert(!lease.acquire({&descriptor, bytes, 2 * bytes}, 42));
        descriptor.bytes = kMaxBackingBytes + bytes;
        assert(!lease.acquire(slice, 42));
        descriptor.bytes = 2 * bytes;
        assert(descriptor.references == 1 && descriptor.wires == 1 && !descriptor.prepares);

        assert(lease.acquire(slice, 42));
        assert(!lease.acquire(slice, 42));
        assert(descriptor.references == 2 && descriptor.wires == 2 && descriptor.prepares == 1);
        if (ownerReleasesFirst) {
            assert(descriptor.complete() == kIOReturnSuccess);
            descriptor.release();
        }

        const auto backing = lease.backing();
        slice = {};
        uint64_t physical = kUnwritten;
        assert(backing.readPage(backing.context, 0, &physical) && physical == addresses[1]);
        assert(lease.releaseAfterRetirement());
        assert(!lease.backing().readPage && !lease.uncertain());
        assert(!lease.releaseAfterRetirement() && !lease.acquire({&descriptor, 0, bytes}, 42));
        physical = kUnwritten;
        assert(!backing.readPage(backing.context, 0, &physical) && physical == kUnwritten);
        if (!ownerReleasesFirst) {
            assert(descriptor.references == 1 && descriptor.wires == 1);
            assert(descriptor.complete() == kIOReturnSuccess);
            descriptor.release();
        }
        assert(!descriptor.references && !descriptor.wires && descriptor.completes == 2 && descriptor.reads == 1);
    }
}

static void testRenderLeaseFailures() {
    const uint64_t address = 0x30000;
    DescriptorFixture descriptor{&address, kPageBytes};
    const PinnedDescriptorSlice slice{&descriptor, 0, kPageBytes};
    RenderDescriptorLease lease;
    descriptor.prepareResult = -1;
    assert(!lease.acquire(slice, 42));
    assert(!lease.backing().readPage && !lease.uncertain());
    assert(descriptor.references == 1 && descriptor.wires == 1 && descriptor.prepares == 1 && !descriptor.completes);

    descriptor.prepareResult = kIOReturnSuccess;
    descriptor.replacementPreparation = 43;
    assert(!lease.acquire(slice, 42));
    assert(!lease.backing().readPage && !lease.uncertain());
    assert(descriptor.references == 1 && descriptor.wires == 1 && descriptor.prepares == 2 && descriptor.completes == 1);

    RenderDescriptorLease retiring;
    assert(retiring.acquire(slice, 43));
    const auto backing = retiring.backing();
    struct CompletionCheck {
        RenderDescriptorLease &lease;
        const OriginalBacking &backing;
        const PinnedDescriptorSlice &slice;
        unsigned calls = 0;
    } check{retiring, backing, slice};
    descriptor.onComplete = [](void *context) {
        auto &check = *static_cast<CompletionCheck *>(context);
        ++check.calls;
        assert(!check.lease.backing().readPage && !check.lease.releaseAfterRetirement());
        assert(!check.lease.acquire(check.slice, 43));
        uint64_t physical = kUnwritten;
        assert(!check.backing.readPage(check.backing.context, 0, &physical) && physical == kUnwritten);
    };
    descriptor.completeContext = &check;
    descriptor.completeResult = -1;
    assert(!retiring.releaseAfterRetirement() && retiring.uncertain());
    assert(!retiring.releaseAfterRetirement() && !retiring.acquire(slice, 43));
    assert(!retiring.backing().readPage && check.calls == 1);
    assert(descriptor.references == 2 && descriptor.wires == 1 && descriptor.completes == 2 && !descriptor.reads);

    descriptor.onComplete = nullptr;
    descriptor.replacementPreparation = 44;
    RenderDescriptorLease rollback;
    assert(!rollback.acquire(slice, 43) && rollback.uncertain());
    assert(!rollback.backing().readPage && !rollback.releaseAfterRetirement());
    assert(descriptor.references == 3 && descriptor.wires == 1 && descriptor.completes == 3);
}

static void testBoundRenderBacking() {
    constexpr uint64_t page = kPageBytes;
    constexpr uint64_t va = 0x80000;
    const uint64_t addresses[] = {0x10000, 0x30000, 0x90000, 0x50000, 0x70000};
    DescriptorFixture descriptor{addresses, 5 * page};
    const unsigned client = 1, otherClient = 2, surfaceObject = 3, otherSurfaceObject = 4;
    const RenderVmTranslation translation{{&client, 17}, &kFixtureMapper, 2, 3, 4, 5, 1, 8};
    const BoundRenderImage image{translation, &surfaceObject, va + page, 2 * page, kSurfaceBgra, 1023, 2, 4092};
    const LiveHostRenderMap mapping{translation, &descriptor, descriptor.preparation, 5 * page, va, page, 3 * page};
    const auto ack = confirmedTlb(translation);
    const ScanoutSurface scanout{image.width, image.height, 1022, kDcnArgb8888, 2 * page};

    const auto refuse = [&](const BoundRenderImage &candidate, const LiveHostRenderMap &snapshot,
                            const void *surface, const ScanoutSurface &target) {
        RenderDescriptorLease lease;
        assert(!acquireBoundRenderBacking(candidate, snapshot, ack, surface, target, lease));
        assert(!lease.backing().readPage && !lease.uncertain());
        assert(!descriptor.prepares && !descriptor.completes && descriptor.references == 1 && descriptor.wires == 1);
    };
    refuse(image, mapping, nullptr, scanout);
    refuse(image, mapping, &otherSurfaceObject, scanout);
    for (const uint64_t stale : {uint64_t{0}, uint64_t{18}, UINT64_MAX}) {
        auto candidate = image;
        auto snapshot = mapping;
        candidate.translation.mapping.generation = stale;
        refuse(candidate, snapshot, &surfaceObject, scanout);
        snapshot.translation.mapping.generation = stale;
        refuse(candidate, snapshot, &surfaceObject, scanout);
    }
    auto snapshot = mapping;
    snapshot.translation.mapping.client = &otherClient;
    refuse(image, snapshot, &surfaceObject, scanout);
    auto reboundImage = image;
    snapshot = mapping;
    ++snapshot.translation.bindingGeneration;
    reboundImage.translation = snapshot.translation;
    refuse(reboundImage, snapshot, &surfaceObject, scanout);
    snapshot = mapping;
    snapshot.descriptor = nullptr;
    refuse(image, snapshot, &surfaceObject, scanout);
    snapshot = mapping;
    ++snapshot.preparation;
    refuse(image, snapshot, &surfaceObject, scanout);
    snapshot = mapping;
    snapshot.boBytes -= page;
    refuse(image, snapshot, &surfaceObject, scanout);
    snapshot = mapping;
    snapshot.boOffset = UINT64_MAX & ~(page - 1);
    refuse(image, snapshot, &surfaceObject, scanout);
    snapshot = mapping;
    snapshot.bytes -= page;
    refuse(image, snapshot, &surfaceObject, scanout);
    snapshot = mapping;
    snapshot.gpuAddress = (1ull << 48) - page;
    auto candidate = image;
    candidate.gpuAddress = snapshot.gpuAddress;
    candidate.boOffset = snapshot.boOffset;
    refuse(candidate, snapshot, &surfaceObject, scanout);
    candidate = image;
    --candidate.gpuAddress;
    refuse(candidate, mapping, &surfaceObject, scanout);
    candidate = image;
    candidate.boOffset -= page;
    refuse(candidate, mapping, &surfaceObject, scanout);
    candidate = image;
    candidate.pixelFormat = 0x6c313072;
    refuse(candidate, mapping, &surfaceObject, scanout);
    candidate = image;
    --candidate.height;
    refuse(candidate, mapping, &surfaceObject, scanout);
    candidate = image;
    candidate.bytesPerRow -= 4;
    refuse(candidate, mapping, &surfaceObject, scanout);
    auto target = scanout;
    target.mappedBytes -= page;
    refuse(image, mapping, &surfaceObject, target);

    RenderDescriptorLease lease;
    assert(!acquireBoundRenderBacking(image, mapping, {}, &surfaceObject, scanout, lease));
    assert(!descriptor.prepares && !lease.backing().readPage);
    assert(acquireBoundRenderBacking(image, mapping, ack, &surfaceObject, scanout, lease));
    const auto backing = lease.backing();
    uint64_t physical = kUnwritten;
    assert(backing.readPage(backing.context, 0, &physical) && physical == addresses[2]);
    assert(backing.readPage(backing.context, page, &physical) && physical == addresses[3]);
    assert(!backing.readPage(backing.context, 2 * page, &physical) && physical == addresses[3]);
    assert(lease.releaseAfterRetirement());
    assert(descriptor.prepares == 1 && descriptor.completes == 1 && descriptor.references == 1 && descriptor.wires == 1);
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
    testManagedWriteHoldsRequireCanonicalPages();
    testSegmentBatches();
    testPageIdentity();
    testDescriptorSlice();
    testRenderLease();
    testRenderLeaseFailures();
    testRenderTlbAck();
    testBoundRenderBacking();
    testFragmentedBacking();
    testAddressAndCapacityEdges();
    testRefusesMalformedRunsBeforeWriting();
    testPanelAndBoundedWork();
    std::puts("[PASS] offline build34 DCN DMA page layout");
}
