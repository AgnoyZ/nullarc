#pragma once

#include <IOKit/IODMACommand.h>
#include <IOKit/IOLib.h>
#include <IOKit/IOMapper.h>

#include "build34_dcn_present_backing.h"
#include "build34_dcn_scanout_pin.h"
#include "build34_dcn_flat_table.h"

#define BUILD34_DCN_PIN_MAP "phx34DcnPinMapV1"

namespace build34::dcn {

struct ScanoutDmaMapper {
    IOMapper *mapper;
    bool (*resolveMappedPage)(IOMapper &, const IODMACommand &, uint64_t, uint64_t &);
    bool (*confirmUnusedUnmap)(IOMapper &, const IODMACommand &);

    bool completeContract() const { return mapper && resolveMappedPage && confirmUnusedUnmap; }
};

struct ScanoutDmaRequest {
    const PresentCopyBacking *present;
    uint64_t windowStart;
    DmaRun *scratch;
    size_t runCapacity;
    uint64_t *pages;
    size_t pageCapacity;
    FlatPageLayout layout;
    ScanoutPinToken token;
};

inline bool validScanoutDmaStorage(const ScanoutDmaRequest &request, uint64_t bytes) {
    const size_t entries = static_cast<size_t>(bytes / kPageBytes);
    const size_t runs = request.runCapacity < entries ? request.runCapacity : entries;
    if (!request.present || !bytes || bytes > kMaxBackingBytes || bytes % kPageBytes || !request.scratch || !runs ||
        !request.pages || request.pageCapacity < entries || request.windowStart % kPageBytes ||
        request.windowStart >= kAddressLimit || bytes > kAddressLimit - request.windowStart)
        return false;
    const auto scratch = reinterpret_cast<uintptr_t>(request.scratch);
    const auto pages = reinterpret_cast<uintptr_t>(request.pages);
    const auto requestAddress = reinterpret_cast<uintptr_t>(&request);
    const auto presentAddress = reinterpret_cast<uintptr_t>(request.present);
    const auto overlap = [](uintptr_t first, size_t firstBytes, uintptr_t second, size_t secondBytes) {
        return first <= second ? second - first < firstBytes : first - second < secondBytes;
    };
    const size_t scratchBytes = runs * sizeof(DmaRun), pageBytes = entries * sizeof(uint64_t);
    return scratch % alignof(DmaRun) == 0 && pages % alignof(uint64_t) == 0 &&
        scratchBytes <= UINTPTR_MAX - scratch && pageBytes <= UINTPTR_MAX - pages &&
        !overlap(scratch, scratchBytes, pages, pageBytes) &&
        !overlap(requestAddress, sizeof(request), scratch, scratchBytes) &&
        !overlap(requestAddress, sizeof(request), pages, pageBytes) &&
        !overlap(requestAddress, sizeof(request), presentAddress, sizeof(PresentCopyBacking)) &&
        !overlap(presentAddress, sizeof(PresentCopyBacking), scratch, scratchBytes) &&
        !overlap(presentAddress, sizeof(PresentCopyBacking), pages, pageBytes);
}

class ScanoutDmaLease {
public:
    ScanoutDmaLease() = default;
    ScanoutDmaLease(const ScanoutDmaLease &) = delete;
    ScanoutDmaLease &operator=(const ScanoutDmaLease &) = delete;

    bool uncertain() const { return uncertain_; }

    size_t prepareRuns(ScanoutDescriptorPin &pin, const ScanoutDmaMapper &qualified, const PresentCopyBacking &present,
                       DmaRun *scratch, size_t capacity) {
        if (command_ || !pin.cancellable() || !qualified.completeContract()) return 0;
        auto &lease = pin.lease_;
        const auto &slice = lease.slice_;
        if (slice.bytes != present.slice.bytes || !present.preparation ||
            livePresentPreparation(present.slice) != present.preparation)
            return 0;
        const auto preparation = livePresentPreparation(slice);
        if (!preparation) return 0;

        command_ = IODMACommand::withSpecification(kIODMACommandOutputHost64, 48, 0, IODMACommand::kMapped,
                                                   slice.bytes, kPageBytes, qualified.mapper);
        if (!command_) return 0;
        qualified.mapper->retain();
        qualified_ = qualified;
        if (command_->setMemoryDescriptor(slice.descriptor, false) != kIOReturnSuccess) {
            if (command_->getMemoryDescriptor()) uncertain_ = true;
            else releaseObjects();
            return 0;
        }
        if (command_->prepare(slice.offset, slice.bytes, false, false) != kIOReturnSuccess) {
            uncertain_ = true;
            return 0;
        }
        if (command_->getIOMemoryDescriptor() != slice.descriptor) {
            uncertain_ = true;
            return 0;
        }
        UInt64 offset = 0, bytes = 0;
        if (command_->getPreparedOffsetAndLength(&offset, &bytes) != kIOReturnSuccess ||
            offset != slice.offset || bytes != slice.bytes)
            return 0;

        auto presented = present.slice;
        const PreparedDmaMapping mapping{bytes, qualified_.mapper, this, readBatch, resolvePage};
        const auto count = collectScanoutRuns(bytes, mapping, qualified.mapper, lease.backing(),
                                             {&presented, readPinnedDescriptorPage}, scratch, capacity);
        return livePresentPreparation(slice) == preparation &&
            livePresentPreparation(presented) == present.preparation ? count : 0;
    }

    bool releaseUnused(const ScanoutDescriptorPin &pin) {
        return pin.cancellable() && releaseUnmapped();
    }

    bool preparePlan(const ScanoutDmaRequest &request, uint64_t bytes, size_t runCount) {
        if (!command_ || uncertain_ || pages_ || !validScanoutDmaStorage(request, bytes)) return false;
        const size_t entryCount = static_cast<size_t>(bytes / kPageBytes);
        const size_t tableBytes = entryCount * sizeof(uint64_t);
        auto *pages = static_cast<uint64_t *>(IOMallocZero(tableBytes));
        if (!pages) return false;
        const auto layout = buildFlatPageLayout(request.windowStart, bytes, request.scratch, runCount, pages, entryCount);
        if (layout.entryCount != entryCount) {
            IOFree(pages, tableBytes);
            return false;
        }
        pages_ = pages;
        layout_ = layout;
        return true;
    }

    bool publishPlan(ScanoutDmaRequest &request, uint64_t bytes) const {
        if (!pages_ || uncertain_ || !validScanoutDmaStorage(request, bytes) ||
            layout_.firstLogicalPage != request.windowStart / kPageBytes || layout_.entryCount != bytes / kPageBytes)
            return false;
        for (size_t index = 0; index < layout_.entryCount; ++index) request.pages[index] = pages_[index];
        request.layout = layout_;
        return true;
    }

private:
    friend class ScanoutFlipCommit;

    bool releaseUnmapped() {
        if (uncertain_) return false;
        if (!command_) return true;
        if (!table_.withdraw(*command_) || command_->complete(false, false) != kIOReturnSuccess ||
            !qualified_.confirmUnusedUnmap(*qualified_.mapper, *command_) ||
            command_->clearMemoryDescriptor(false) != kIOReturnSuccess) {
            uncertain_ = true;
            return false;
        }
        releaseObjects();
        return true;
    }

    void releaseObjects() {
        table_.release();
        command_->release();
        qualified_.mapper->release();
        if (pages_) IOFree(pages_, layout_.tableBytes);
        command_ = nullptr;
        qualified_ = {};
        pages_ = nullptr;
        layout_ = {};
    }

    static bool readBatch(void *context, uint64_t *offset, DmaSegment *segments, uint32_t *count) {
        auto &self = *static_cast<ScanoutDmaLease *>(context);
        IODMACommand::Segment64 batch[8]{};
        UInt64 cursor = *offset;
        UInt32 actual = *count;
        if (!actual || actual > sizeof(batch) / sizeof(batch[0]) ||
            self.command_->gen64IOVMSegments(&cursor, batch, &actual) != kIOReturnSuccess || actual > *count)
            return false;
        for (UInt32 index = 0; index < actual; ++index)
            segments[index] = {batch[index].fIOVMAddr, batch[index].fLength};
        *offset = cursor;
        *count = actual;
        return true;
    }

    static bool resolvePage(void *context, const void *mapper, uint64_t address, uint64_t *physical) {
        auto &self = *static_cast<ScanoutDmaLease *>(context);
        return mapper == self.qualified_.mapper && self.qualified_.resolveMappedPage(
            *self.qualified_.mapper, *self.command_, address, *physical);
    }

    IODMACommand *command_{nullptr};
    ScanoutDmaMapper qualified_{};
    uint64_t *pages_{nullptr};
    FlatPageLayout layout_{};
    DcnFlatTable table_;
    bool uncertain_{false};
};

struct ScanoutDmaJob {
    const ScanoutDmaMapper &qualified;
    ScanoutDmaLease &lease;
    ScanoutDmaRequest &request;
};

}
