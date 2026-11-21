#include <algorithm>
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

static unsigned checks = 0;
#define CHECK(condition) do { ++checks; if (!(condition)) { \
    std::fprintf(stderr, "failed: %s\n", #condition); std::_Exit(86); \
} } while (false)

using IOByteCount = uint64_t;
static constexpr unsigned kIODirectionInOut = 1, kIOMemoryPhysicallyContiguous = 2;
static constexpr unsigned kernel_task = 7;
static constexpr size_t chunkBytes = 64 * 1024;
static constexpr uint64_t sentinel = 0xa5a5a5a5a5a5a5a5ull;

// PT_MASK

struct IOBufferMemoryDescriptor {
    std::array<uint64_t, chunkBytes / sizeof(uint64_t)> words;
    uint64_t base = 0x10000;
    IOByteCount length = chunkBytes, contiguous = chunkBytes;
    bool mapped = true;
    unsigned releases = 0;
    IOBufferMemoryDescriptor() { words.fill(sentinel); }
    void *getBytesNoCopy() { return mapped ? words.data() : nullptr; }
    IOByteCount getLength() const { return length; }
    uint64_t getPhysicalAddress() const { return base; }
    uint64_t getPhysicalSegment(IOByteCount offset, IOByteCount *size, unsigned options = 0) const {
        CHECK(mapped && length >= chunkBytes && offset == 0 && size && options == 0);
        *size = contiguous;
        return base;
    }
    void release() { CHECK(!releases); ++releases; }
    static IOBufferMemoryDescriptor *inTaskWithPhysicalMask(unsigned task, unsigned options,
                                                           IOByteCount size, uint64_t mask);
};

class PhxBringup {
public:
    // PT_FIELDS
    uint64_t *ptTable(const VmCtx &context, uint64_t phys) const;
    uint64_t ptTablePhys(VmCtx &context, uint32_t index);
    uint64_t *vmPte(VmCtx &context, uint64_t va, bool alloc);
};

static IOBufferMemoryDescriptor *next = nullptr;
static unsigned allocations = 0, zeroes = 0, flushes = 0;
static PhxBringup::VmCtx *unpublished = nullptr;
static uint32_t pendingIndex = 0;

IOBufferMemoryDescriptor *IOBufferMemoryDescriptor::inTaskWithPhysicalMask(
        unsigned task, unsigned options, IOByteCount size, uint64_t mask) {
    CHECK(task == kernel_task && options == (kIODirectionInOut | kIOMemoryPhysicallyContiguous));
    CHECK(size == chunkBytes && mask == kPtAddrMask);
    ++allocations;
    return next;
}

static void checkedZero(void *memory, size_t length) {
    CHECK(memory && length == chunkBytes && next && next->words.data() == memory);
    ++zeroes;
    std::memset(memory, 0, length);
}

static void flushLine(const volatile void *) {
    if (unpublished) CHECK(!unpublished->chunk[pendingIndex] && !unpublished->chunkPhys[pendingIndex]);
    ++flushes;
}

#define bzero checkedZero
// PT_METHODS
#undef bzero

static void rejected(const char *scenario) {
    PhxBringup service;
    PhxBringup::VmCtx context{};
    IOBufferMemoryDescriptor existing, candidate;
    context.chunk[0] = &existing;
    context.chunkPhys[0] = existing.base;
    candidate.base *= 2;
    next = &candidate;
    if (!std::strcmp(scenario, "allocation-failed")) next = nullptr;
    else if (!std::strcmp(scenario, "missing-map")) candidate.mapped = false;
    else if (!std::strcmp(scenario, "short-descriptor")) --candidate.length;
    else if (!std::strcmp(scenario, "short-segment")) --candidate.contiguous;
    else if (!std::strcmp(scenario, "zero-base")) candidate.base = 0;
    else if (!std::strcmp(scenario, "misaligned")) ++candidate.base;
    else if (!std::strcmp(scenario, "above-mask")) candidate.base = kPtAddrMask + 4096;
    else if (!std::strcmp(scenario, "crosses-mask")) candidate.base = kPtAddrMask;
    else CHECK(false);

    CHECK(service.ptTablePhys(context, PhxBringup::kPtChunkPages + 1) == 0);
    CHECK(!context.chunk[1] && !context.chunkPhys[1]);
    CHECK(context.chunk[0] == &existing && context.chunkPhys[0] == existing.base && !existing.releases);
    CHECK(!zeroes && !flushes && candidate.releases == (next ? 1u : 0u) && allocations == 1);
    CHECK(std::all_of(candidate.words.begin(), candidate.words.end(), [](uint64_t value) { return value == sentinel; }));
}

static void accepted() {
    PhxBringup service;
    PhxBringup::VmCtx context{};
    IOBufferMemoryDescriptor root, last;
    const auto pages = PhxBringup::kPtChunks * PhxBringup::kPtChunkPages;
    CHECK(service.ptTablePhys(context, pages) == 0 && !allocations);
    next = &root;
    unpublished = &context;
    context.phys = service.ptTablePhys(context, 0);
    CHECK(context.phys == root.base && allocations == 1 && zeroes == 1 && flushes == chunkBytes / 64);
    unpublished = nullptr;
    context.pages = pages;
    context.used = 1;
    const uint64_t va = 0x10000;
    CHECK(!service.vmPte(context, va, false) && context.used == 1);
    auto *leaf = service.vmPte(context, va, true);
    CHECK(leaf == &root.words[3 * 512 + 16] && !*leaf && context.used == 4);
    CHECK(service.vmPte(context, va, false) == leaf && context.used == 4 && allocations == 1);
    CHECK(service.vmPte(context, va + 4096, false) == leaf + 1);
    CHECK(flushes == chunkBytes / 64 + 3 && !root.releases);

    next = &last;
    last.base = kPtAddrMask - (chunkBytes - 4096);
    unpublished = &context;
    pendingIndex = 1;
    CHECK(service.ptTablePhys(context, 2 * PhxBringup::kPtChunkPages - 1) == kPtAddrMask);
    unpublished = nullptr;
    CHECK(service.ptTable(context, kPtAddrMask) == last.words.data() + last.words.size() - 512);
    CHECK(allocations == 2 && zeroes == 2 && flushes == 2 * chunkBytes / 64 + 3 && !last.releases);
}

int main(int argc, char **argv) {
    CHECK(argc == 2);
    if (!std::strcmp(argv[1], "accepted")) accepted();
    else rejected(argv[1]);
    std::printf("PASS %u checks; GPU_executed=false\n", checks);
}
