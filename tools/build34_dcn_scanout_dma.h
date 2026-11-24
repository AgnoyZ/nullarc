#pragma once

#include <IOKit/IODMACommand.h>
#include <IOKit/IOLib.h>
#include <IOKit/IOMapper.h>
#include <build34_dcn_writer_receipt.h>

#include "build34_dcn_present_backing.h"
#include "build34_dcn_scanout_pin.h"
#include "build34_dcn_flat_table.h"

#define BUILD34_DCN_PIN_MAP "phx34DcnPinMapV1"
#define BUILD34_DCN_PIN_MAP_DIRECT "phx34DcnPinMapDirectV1"

namespace build34::dcn {

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

    bool uncertain() const { return uncertain_ || presentPin_.uncertain(); }

    size_t prepareRuns(ScanoutDescriptorPin &pin, const ScanoutDmaMapper &qualified, const PresentCopyBacking &present,
                       DmaRun *scratch, size_t capacity) {
        if (hasBacking() || presentPin_.bytes() || uncertain() || !pin.cancellable() || !qualified.current()) return 0;
        auto &lease = pin.lease_;
        const auto &slice = lease.slice_;
        if (slice.bytes != present.slice.bytes || !present.preparation ||
            livePresentPreparation(present.slice) != present.preparation)
            return 0;
        const auto preparation = livePresentPreparation(slice);
        if (!preparation || !presentPin_.acquire(present.slice, present.preparation)) return 0;
        renderPreparation_ = preparation;
        presentPreparation_ = present.preparation;

        if (qualified.direct.complete()) {
            qualified.direct.device->retain();
            qualified_ = qualified;
            return prepareDirectRuns(lease, scratch, capacity);
        }
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

        const PreparedDmaMapping mapping{bytes, qualified_.mapper, this, readBatch, resolvePage};
        const auto count = collectScanoutRuns(bytes, mapping, qualified.mapper, lease.backing(),
                                             presentPin_.backing(), scratch, capacity);
        return livePresentPreparation(slice) == preparation &&
            livePresentPreparation(presentPin_.slice_) == presentPreparation_ ? count : 0;
    }

    bool releaseUnused(const ScanoutDescriptorPin &pin) {
        return pin.cancellable() && releaseUnmapped();
    }

    bool preparePlan(const ScanoutDmaRequest &request, uint64_t bytes, size_t runCount) {
        if (!hasBacking() || uncertain() || pages_ || !validScanoutDmaStorage(request, bytes)) return false;
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

    bool publishPlan(ScanoutDmaRequest &request, uint64_t bytes, const WriterReceipt &writer, WriterDrainStamp drain) {
        if (!pages_ || uncertain() || !validScanoutDmaStorage(request, bytes) ||
            layout_.firstLogicalPage != request.windowStart / kPageBytes || layout_.entryCount != bytes / kPageBytes ||
            !writer.complete || writer.range.bytes != bytes || writer.map.preparation != renderPreparation_ ||
            !drain.computeGeneration || drain.gfxGeneration != writer.native.generation)
            return false;
        writerProof_ = {writer, drain};
        for (size_t index = 0; index < layout_.entryCount; ++index) request.pages[index] = pages_[index];
        request.layout = layout_;
        return true;
    }

    const ScanoutWriterProof &writerProof() const { return writerProof_; }

    bool matchesWriterBacking(const ScanoutDescriptorPin &pin, const WriterMapping &mapping) const {
        const auto &slice = pin.lease_.slice_;
        return pin.held() && pages_ && !uncertain() && mapping.slice.descriptor == slice.descriptor &&
            mapping.slice.offset == slice.offset && mapping.slice.bytes == slice.bytes;
    }

private:
    friend class ScanoutFlipCommit;

    bool hasBacking() const { return command_ || qualified_.direct.complete(); }

    DcnPixelMapping mapping() const {
        return {command_, qualified_.direct.complete() ? &qualified_.direct : nullptr};
    }

    size_t prepareDirectRuns(RenderDescriptorLease &render, DmaRun *scratch, size_t capacity) {
        const auto source = render.backing();
        const auto present = presentPin_.backing();
        if (!scratch || !capacity || !source.readPage || !present.readPage) return 0;
        size_t count = 0;
        for (uint64_t offset = 0; offset < render.bytes(); offset += kPageBytes) {
            uint64_t physical = 0, presented = 0;
            if (!source.readPage(source.context, offset, &physical) || !present.readPage(present.context, offset, &presented) ||
                presented != physical || !qualified_.direct.permits(*render.slice_.descriptor, render.slice_.offset + offset,
                                                                    physical, DcnDirectUse::Pixel)) return 0;
            if (count && scratch[count - 1].dmaAddress + scratch[count - 1].bytes == physical) {
                scratch[count - 1].bytes += kPageBytes;
            } else {
                if (count == capacity) return 0;
                scratch[count++] = {offset, physical, kPageBytes};
            }
        }
        return qualified_.current() && livePresentPreparation(render.slice_) == renderPreparation_ &&
            livePresentPreparation(presentPin_.slice_) == presentPreparation_ ? count : 0;
    }

    template<typename Current>
    bool matchesPixels(const ScanoutDescriptorPin &pin, const Current &live) const {
        auto render = pin.lease_.slice_;
        auto present = presentPin_.slice_;
        const auto current = [&] {
            UInt64 offset = 0, bytes = 0;
            return live() && qualified_.current() && (!command_ || (command_->getIOMemoryDescriptor() == render.descriptor &&
                command_->getPreparedOffsetAndLength(&offset, &bytes) == kIOReturnSuccess &&
                offset == render.offset && bytes == render.bytes)) && livePresentPreparation(render) == renderPreparation_ &&
                livePresentPreparation(present) == presentPreparation_ && live();
        };
        if (!hasBacking() || !pages_ || uncertain() || !pin.held() || presentPin_.bytes() != render.bytes ||
            layout_.entryCount != render.bytes / kPageBytes || !current()) return false;
        for (size_t index = 0; index < layout_.entryCount; ++index) {
            const uint64_t offset = index * kPageBytes;
            uint64_t rendered = 0, presented = 0, resolved = 0;
            if (!live() || !readPinnedDescriptorPage(&render, offset, &rendered) ||
                !readPinnedDescriptorPage(&present, offset, &presented) || presented != rendered || (command_ ?
                !qualified_.resolveMappedPage(*qualified_.mapper, *command_, pages_[index], resolved) || resolved != rendered :
                pages_[index] != rendered || !qualified_.direct.permits(*render.descriptor, render.offset + offset,
                                                                       rendered, DcnDirectUse::Pixel))) return false;
        }
        return current();
    }

    bool releaseUnmapped() {
        if (uncertain()) return false;
        if (!table_.withdraw(qualified_) || (command_ && (command_->complete(false, false) != kIOReturnSuccess ||
            !qualified_.confirmUnusedUnmap(*qualified_.mapper, *command_) ||
            command_->clearMemoryDescriptor(false) != kIOReturnSuccess))) {
            uncertain_ = true;
            return false;
        }
        if (presentPin_.bytes() && !presentPin_.releaseAfterRetirement()) return false;
        presentPin_.recycleClosed();
        if (hasBacking()) releaseObjects();
        renderPreparation_ = presentPreparation_ = 0;
        return true;
    }

    void releaseObjects() {
        table_.release();
        if (command_) command_->release();
        if (qualified_.mapper) qualified_.mapper->release();
        if (qualified_.direct.device) qualified_.direct.device->release();
        if (pages_) IOFree(pages_, layout_.tableBytes);
        command_ = nullptr;
        qualified_ = {};
        pages_ = nullptr;
        layout_ = {};
        writerProof_ = {};
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
    ScanoutWriterProof writerProof_{};
    DcnFlatTable table_;
    RenderDescriptorLease presentPin_;
    uint64_t renderPreparation_{0}, presentPreparation_{0};
    bool uncertain_{false};
};

struct ScanoutDmaJob {
    const ScanoutDmaMapper &qualified;
    ScanoutDmaLease &lease;
    ScanoutDmaRequest &request;
};

}
