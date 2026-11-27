// SPDX-License-Identifier: MIT OR GPL-2.0-only
// Clean-room UMA carve-out reservation planner, host-exclusion verifier, and
// GPU-local high-VRAM pool for Phoenix / Radeon 780M (build34).
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace phx::uma {

static constexpr uint64_t kPageBytes = 4096ull;
static constexpr uint64_t kFbAlignment = 16ull << 20;
static constexpr uint64_t kExpectedBar0Bytes = 256ull << 20;
static constexpr uint64_t kExpectedMcBase = 0x8000000000ull;
static constexpr uint64_t kAddressLimit = 1ull << 48;
static constexpr uint64_t kPilotWindowBytes = 64ull << 20;
static constexpr uint64_t kDefaultTopReserveBytes = 64ull << 20;

// GFX11 / GC 11.0.1 register indices for read-only IP Discovery verification
// (matches Linux amdgpu_discovery.c and PhxProbe.cpp).
static constexpr uint32_t kRegMmIndex = 0x0u;
static constexpr uint32_t kRegMmData = 0x1u;
static constexpr uint32_t kRegMmIndexHi = 0x6u;
static constexpr uint32_t kRegDriverScratch0 = 0x94u;
static constexpr uint32_t kRegDriverScratch1 = 0x95u;
static constexpr uint32_t kRegDriverScratch2 = 0x96u;
static constexpr uint32_t kRegRccConfigMemsize = 0xde3u;
static constexpr uint32_t kRegIpDiscoveryVersion = 0x16a00u;

static constexpr uint64_t kDiscoveryTmrOffset = 64ull << 10;
static constexpr uint32_t kDiscoveryTmrSize = 10u << 10;
static constexpr uint32_t kDiscoveryMaxSize = 64u << 10;
static constexpr uint32_t kDiscoverySignature = 0x28211407u;

// GPUVM leaf PTE flags for local UMA VRAM (mesboot.c vm8_test):
// VALID(0x1) | READ(0x20) | WRITE(0x40), SYSTEM=0, SNOOPED=0, EXEC=0, MTYPE=4.
static constexpr uint64_t kPtAddrMask = 0x0000FFFFFFFFF000ull;
static constexpr uint64_t kPteLocalReadFlags = 0x21ull | (4ull << 48);
static constexpr uint64_t kPteLocalRwFlags = 0x61ull | (4ull << 48);

// Minimum valid alias sample counts when verifying phx-fb-phys against BAR0.
static constexpr uint32_t kAliasMinSamples = 64u;
static constexpr uint32_t kAliasMinNonZero = 8u;

enum class HostExclusionStatus : uint32_t {
    Unchecked = 0,
    BootArgsUnavailable = 1,
    BootMapUnreadable = 2,
    Refused = 3,
    HostUsableOverlap = 4,
    OtherOverlap = 5,
    Incomplete = 6,
    ReservedTypeOnly = 7,
};

struct Range {
    uint64_t offset{0};
    uint64_t bytes{0};

    constexpr bool within(uint64_t limit) const {
        return bytes != 0 && offset < limit && bytes <= limit - offset;
    }

    constexpr uint64_t end() const { return offset + bytes; }
};

struct Geometry {
    uint64_t mcBase{0};
    uint64_t physBase{0};
    uint64_t fbBytes{0};
    uint64_t bar0Bytes{0};
};

struct DiscoveryProbe {
    uint32_t rccMemsizeMb{0};
    uint32_t ipDiscoveryVersion{0};
    uint64_t discoveryOffset{0};
    uint32_t discoveryBytes{0};
    uint32_t discoverySignature{0};
    bool signatureValid{false};
    bool memsizeMatchesFb{false};
};

struct WindowPlan {
    bool valid{false};
    Range pilotWindow{};
    Range fullHighWindow{};
    Range discoveryRange{};
    uint64_t topReserveBytes{0};
};

static inline uint64_t alignUp(uint64_t value, uint64_t alignment) {
    return (value + alignment - 1ull) & ~(alignment - 1ull);
}

static inline bool rangesOverlap(Range left, Range right) {
    return left.bytes != 0 && right.bytes != 0 && left.offset < right.end() && right.offset < left.end();
}

static inline bool geometryValid(const Geometry &geometry) {
    if (geometry.mcBase != kExpectedMcBase || !geometry.physBase || !geometry.fbBytes)
        return false;
    if (geometry.bar0Bytes != kExpectedBar0Bytes)
        return false;
    if ((geometry.mcBase | geometry.physBase | geometry.fbBytes) & (kFbAlignment - 1ull))
        return false;
    if (geometry.fbBytes <= geometry.bar0Bytes)
        return false;
    if (!Range{geometry.mcBase, geometry.fbBytes}.within(kAddressLimit))
        return false;
    if (!Range{geometry.physBase, geometry.fbBytes}.within(kAddressLimit))
        return false;
    return true;
}

static inline bool aliasVerificationMatches(uint32_t matchingSamples, uint32_t totalSamples, uint32_t nonZeroSamples) {
    return totalSamples >= kAliasMinSamples && nonZeroSamples >= kAliasMinNonZero &&
           matchingSamples == totalSamples;
}

static inline DiscoveryProbe classifyDiscoveryProbe(uint64_t fbBytes, uint32_t rccMemsizeMb,
                                                    uint32_t ipDiscoveryVersion, uint64_t discoveryOffset,
                                                    uint32_t discoveryBytes, uint32_t discoverySignature) {
    DiscoveryProbe probe{};
    probe.rccMemsizeMb = rccMemsizeMb;
    probe.ipDiscoveryVersion = ipDiscoveryVersion;
    probe.discoveryOffset = discoveryOffset;
    probe.discoveryBytes = discoveryBytes;
    probe.discoverySignature = discoverySignature;
    probe.memsizeMatchesFb = rccMemsizeMb != 0 && rccMemsizeMb != 0xFFFFFFFFu &&
                             (static_cast<uint64_t>(rccMemsizeMb) << 20) == fbBytes;
    const Range discRange{discoveryOffset, discoveryBytes};
    probe.signatureValid = discoverySignature == kDiscoverySignature &&
                           (discoveryOffset & 3u) == 0 &&
                           discoveryBytes >= 4u && discoveryBytes <= kDiscoveryMaxSize &&
                           discRange.within(fbBytes);
    return probe;
}

static inline WindowPlan planHighUmaWindows(const Geometry &geometry, const DiscoveryProbe &discovery,
                                            uint64_t topReserveBytes = kDefaultTopReserveBytes) {
    WindowPlan plan{};
    if (!geometryValid(geometry) || !discovery.signatureValid || !discovery.memsizeMatchesFb)
        return plan;
    if (topReserveBytes < kPageBytes || (topReserveBytes & (kPageBytes - 1ull)))
        return plan;

    const Range discRange{discovery.discoveryOffset,
                          alignUp(discovery.discoveryBytes, kPageBytes)};
    if (!discRange.within(geometry.fbBytes))
        return plan;

    uint64_t upperLimit = geometry.fbBytes > topReserveBytes ? geometry.fbBytes - topReserveBytes : 0;
    if (discRange.offset < upperLimit)
        upperLimit = discRange.offset & ~(kPageBytes - 1ull);
    if (upperLimit <= geometry.bar0Bytes)
        return plan;

    const uint64_t highBytes = upperLimit - geometry.bar0Bytes;
    if (highBytes < kPilotWindowBytes)
        return plan;

    const Range fullHigh{geometry.bar0Bytes, highBytes};
    const Range pilot{geometry.bar0Bytes, kPilotWindowBytes};
    if (rangesOverlap(fullHigh, discRange) || rangesOverlap(pilot, discRange))
        return plan;

    plan.valid = true;
    plan.pilotWindow = pilot;
    plan.fullHighWindow = fullHigh;
    plan.discoveryRange = discRange;
    plan.topReserveBytes = geometry.fbBytes - upperLimit;
    return plan;
}

// Freestanding x86_64 boot_args EFI memory map verifier (mirrors
// tools/build34_uma_boot_map.c with support for full high-UMA windows up to 4 GiB).
static inline uint64_t readLittleEndian(const uint8_t *bytes, unsigned width) {
    uint64_t value = 0;
    for (unsigned index = 0; index < width; ++index)
        value |= static_cast<uint64_t>(bytes[index]) << (index * 8u);
    return value;
}

static inline HostExclusionStatus classifyBootMap(const void *bootArgs, size_t bootArgsLength,
                                                  const void *mapBytes, size_t mapLength,
                                                  uint64_t mapPhysicalBase, uint64_t candidateBase,
                                                  uint64_t candidateLength) {
    constexpr size_t kBootArgsLength = 4096;
    constexpr size_t kBootRevisionOffset = 0;
    constexpr size_t kBootVersionOffset = 2;
    constexpr size_t kBootEfiModeOffset = 4;
    constexpr size_t kBootMapAddressOffset = 1032;
    constexpr size_t kBootMapSizeOffset = 1036;
    constexpr size_t kBootMapStrideOffset = 1040;
    constexpr size_t kBootMapVersionOffset = 1044;
    constexpr size_t kEfiDescriptorMinBytes = 40;
    constexpr size_t kEfiTypeOffset = 0;
    constexpr size_t kEfiPhysicalOffset = 8;
    constexpr size_t kEfiPagesOffset = 24;
    constexpr size_t kEfiAttributesOffset = 32;
    constexpr size_t kEfiMaxDescriptors = 512;
    constexpr size_t kEfiMaxMapBytes = 1u << 20;
    constexpr uint64_t kMapAddressLimit = 1ull << 32;
    constexpr uint64_t kEfiMemoryRuntime = 1ull << 63;

    if (!bootArgs || bootArgsLength != kBootArgsLength || !mapBytes)
        return HostExclusionStatus::Refused;
    if (!candidateBase || candidateBase >= kAddressLimit || !candidateLength ||
        candidateLength > kAddressLimit - candidateBase ||
        ((candidateBase | candidateLength) & (kPageBytes - 1ull)))
        return HostExclusionStatus::Refused;

    const uint8_t *args = static_cast<const uint8_t *>(bootArgs);
    if (readLittleEndian(args + kBootRevisionOffset, 2) > 1 ||
        readLittleEndian(args + kBootVersionOffset, 2) != 2 ||
        args[kBootEfiModeOffset] != 64 ||
        readLittleEndian(args + kBootMapVersionOffset, 4) != 1)
        return HostExclusionStatus::Refused;

    const uint64_t mapAddress = readLittleEndian(args + kBootMapAddressOffset, 4);
    const uint64_t length = readLittleEndian(args + kBootMapSizeOffset, 4);
    const uint64_t stride = readLittleEndian(args + kBootMapStrideOffset, 4);
    if (!mapAddress || (mapAddress & 7u) || mapAddress != mapPhysicalBase || length != mapLength ||
        length == 0 || length > kEfiMaxMapBytes || length > kMapAddressLimit - mapAddress ||
        stride < kEfiDescriptorMinBytes || stride > length || (stride & 7u) ||
        (length % stride) != 0 || (length / stride) > kEfiMaxDescriptors)
        return HostExclusionStatus::Refused;

    const uint64_t basePage = candidateBase >> 12;
    const uint64_t endPage = (candidateBase + candidateLength) >> 12;
    const uint8_t *data = static_cast<const uint8_t *>(mapBytes);
    uint64_t coveredPages = 0;
    HostExclusionStatus overlap = HostExclusionStatus::Incomplete;

    for (size_t offset = 0; offset < length; offset += stride) {
        const uint8_t *entry = data + offset;
        const uint64_t physical = readLittleEndian(entry + kEfiPhysicalOffset, 8);
        const uint64_t pages = readLittleEndian(entry + kEfiPagesOffset, 8);
        const uint64_t startPage = physical >> 12;
        if ((physical & (kPageBytes - 1ull)) || !pages ||
            pages > (1ull << (64 - 12)) - startPage)
            return HostExclusionStatus::Refused;
        const uint64_t stopPage = startPage + pages;

        for (size_t prior = 0; prior < offset; prior += stride) {
            const uint8_t *previous = data + prior;
            const uint64_t prevStart = readLittleEndian(previous + kEfiPhysicalOffset, 8) >> 12;
            const uint64_t prevStop = prevStart + readLittleEndian(previous + kEfiPagesOffset, 8);
            if (startPage < prevStop && prevStart < stopPage)
                return HostExclusionStatus::Refused;
        }

        if (startPage >= endPage || basePage >= stopPage)
            continue;

        const uint64_t clipStart = startPage > basePage ? startPage : basePage;
        const uint64_t clipStop = stopPage < endPage ? stopPage : endPage;
        coveredPages += clipStop - clipStart;

        const uint64_t kind = readLittleEndian(entry + kEfiTypeOffset, 4);
        const uint64_t attrs = readLittleEndian(entry + kEfiAttributesOffset, 8);
        const bool hostUsable = ((kind >= 1 && kind <= 4) || kind == 7) && !(attrs & kEfiMemoryRuntime);
        if (hostUsable)
            overlap = HostExclusionStatus::HostUsableOverlap;
        else if ((kind != 0 || (attrs & kEfiMemoryRuntime)) &&
                 overlap != HostExclusionStatus::HostUsableOverlap)
            overlap = HostExclusionStatus::OtherOverlap;
    }

    if (overlap != HostExclusionStatus::Incomplete)
        return overlap;
    return coveredPages == (endPage - basePage)
        ? HostExclusionStatus::ReservedTypeOnly
        : HostExclusionStatus::Incomplete;
}

static inline uint64_t encodeLocalVramPte(uint64_t physBase, uint64_t vramOffset, bool writable) {
    const uint64_t pagePhys = (physBase + vramOffset) & kPtAddrMask;
    return pagePhys | (writable ? kPteLocalRwFlags : kPteLocalReadFlags);
}

// Kernel-safe, fixed-capacity range allocator for an admitted high-UMA window.
// Callers serialize all methods under a lock (e.g. PhxBringup::umaLock).
class HighUmaAllocator {
public:
    static constexpr uint32_t kMaxAllocs = 512u;

    struct Allocation {
        uint64_t serial{0};
        uint32_t slot{0};
        uint64_t vramOffset{0};
        uint64_t bytes{0};
        uint64_t physBase{0};
        uint64_t mcBase{0};
    };

    struct Stats {
        uint64_t capacityBytes{0};
        uint64_t usedBytes{0};
        uint64_t quarantinedBytes{0};
        uint32_t liveCount{0};
        uint32_t quarantinedCount{0};
        bool admitted{false};
        bool faulted{false};
    };

    HighUmaAllocator() = default;
    HighUmaAllocator(const HighUmaAllocator &) = delete;
    HighUmaAllocator &operator=(const HighUmaAllocator &) = delete;

    void reset() {
        geometry_ = Geometry{};
        window_ = Range{};
        nextSerial_ = 0;
        admitted_ = false;
        faulted_ = false;
        for (uint32_t index = 0; index < kMaxAllocs; ++index)
            records_[index] = Record{};
    }

    bool admit(const Geometry &geometry, Range ownedWindow, Range discoveryRange,
               HostExclusionStatus hostStatus, bool aliasMatched) {
        if (admitted_ || !geometryValid(geometry))
            return false;
        if (hostStatus != HostExclusionStatus::ReservedTypeOnly || !aliasMatched)
            return false;
        if (!ownedWindow.within(geometry.fbBytes) || ownedWindow.offset < geometry.bar0Bytes)
            return false;
        if ((ownedWindow.offset | ownedWindow.bytes) & (kPageBytes - 1ull))
            return false;
        if (!discoveryRange.within(geometry.fbBytes) || rangesOverlap(ownedWindow, discoveryRange))
            return false;

        geometry_ = geometry;
        window_ = ownedWindow;
        admitted_ = true;
        faulted_ = false;
        return true;
    }

    bool allocate(uint64_t ownerId, uint64_t requestedBytes, uint64_t alignment, Allocation &out) {
        out = Allocation{};
        if (!admitted_ || faulted_ || !ownerId || !requestedBytes)
            return false;
        if (alignment < kPageBytes || alignment > (2ull << 20) || (alignment & (alignment - 1ull)))
            return false;
        if (requestedBytes > window_.bytes)
            return false;
        const uint64_t bytes = alignUp(requestedBytes, kPageBytes);
        if (bytes > window_.bytes || nextSerial_ == UINT64_MAX)
            return false;

        uint32_t freeSlot = kMaxAllocs;
        for (uint32_t index = 0; index < kMaxAllocs; ++index) {
            if (records_[index].serial == 0) {
                freeSlot = index;
                break;
            }
        }
        if (freeSlot == kMaxAllocs)
            return false;

        for (uint64_t offset = alignUp(window_.offset, alignment);
             offset < window_.end() && bytes <= window_.end() - offset;) {
            const Range proposed{offset, bytes};
            uint64_t nextOffset = offset;
            for (uint32_t index = 0; index < kMaxAllocs; ++index) {
                const Record &record = records_[index];
                if (record.serial != 0 && rangesOverlap(proposed, record.range) && record.range.end() > nextOffset)
                    nextOffset = record.range.end();
            }
            if (nextOffset != offset) {
                offset = alignUp(nextOffset, alignment);
                continue;
            }

            Record &slot = records_[freeSlot];
            slot.ownerId = ownerId;
            slot.serial = ++nextSerial_;
            slot.range = proposed;
            slot.quarantined = false;

            out.serial = slot.serial;
            out.slot = freeSlot;
            out.vramOffset = proposed.offset;
            out.bytes = proposed.bytes;
            out.physBase = geometry_.physBase + proposed.offset;
            out.mcBase = geometry_.mcBase + proposed.offset;
            return true;
        }
        return false;
    }

    bool release(uint64_t ownerId, uint32_t slot, uint64_t serial) {
        Record *record = lookup(ownerId, slot, serial);
        if (!record || record->quarantined)
            return false;
        *record = Record{};
        return true;
    }

    bool quarantine(uint64_t ownerId, uint32_t slot, uint64_t serial) {
        Record *record = lookup(ownerId, slot, serial);
        if (!record)
            return false;
        record->quarantined = true;
        faulted_ = true;
        return true;
    }

    void tripFault() { faulted_ = true; }

    bool pagePhysAddress(uint64_t ownerId, uint32_t slot, uint64_t serial,
                         uint64_t boOffset, uint64_t &physOut) const {
        physOut = 0;
        if (faulted_ || (boOffset & (kPageBytes - 1ull)))
            return false;
        const Record *record = lookup(ownerId, slot, serial);
        if (!record || record->quarantined || boOffset >= record->range.bytes)
            return false;
        physOut = geometry_.physBase + record->range.offset + boOffset;
        return true;
    }

    bool encodePagePte(uint64_t ownerId, uint32_t slot, uint64_t serial,
                       uint64_t boOffset, bool writable, uint64_t &pteOut) const {
        pteOut = 0;
        uint64_t phys = 0;
        if (!pagePhysAddress(ownerId, slot, serial, boOffset, phys))
            return false;
        pteOut = (phys & kPtAddrMask) | (writable ? kPteLocalRwFlags : kPteLocalReadFlags);
        return true;
    }

    Stats stats() const {
        Stats result{};
        result.admitted = admitted_;
        result.faulted = faulted_;
        result.capacityBytes = admitted_ ? window_.bytes : 0;
        for (uint32_t index = 0; index < kMaxAllocs; ++index) {
            const Record &record = records_[index];
            if (record.serial == 0)
                continue;
            result.usedBytes += record.range.bytes;
            result.liveCount++;
            if (record.quarantined) {
                result.quarantinedBytes += record.range.bytes;
                result.quarantinedCount++;
            }
        }
        return result;
    }

    uint64_t freeBytes() const {
        if (!admitted_ || faulted_)
            return 0;
        const Stats st = stats();
        return st.capacityBytes > st.usedBytes ? st.capacityBytes - st.usedBytes : 0;
    }

    Range window() const { return window_; }

private:
    struct Record {
        uint64_t ownerId{0};
        uint64_t serial{0};
        Range range{};
        bool quarantined{false};
    };

    const Record *lookup(uint64_t ownerId, uint32_t slot, uint64_t serial) const {
        if (!admitted_ || !ownerId || !serial || slot >= kMaxAllocs)
            return nullptr;
        const Record &record = records_[slot];
        if (record.ownerId != ownerId || record.serial != serial)
            return nullptr;
        return &record;
    }

    Record *lookup(uint64_t ownerId, uint32_t slot, uint64_t serial) {
        return const_cast<Record *>(static_cast<const HighUmaAllocator *>(this)->lookup(ownerId, slot, serial));
    }

    Geometry geometry_{};
    Range window_{};
    uint64_t nextSerial_{0};
    bool admitted_{false};
    bool faulted_{false};
    Record records_[kMaxAllocs]{};
};

} // namespace phx::uma
