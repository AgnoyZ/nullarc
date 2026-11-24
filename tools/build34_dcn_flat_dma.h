#pragma once

#include <IOKit/IOBufferMemoryDescriptor.h>
#include <IOKit/IODMACommand.h>
#include <IOKit/IOMapper.h>

#include "build34_dcn_page_layout.h"

namespace build34::dcn {

enum class DcnDirectUse { Pixel, Table };

struct DcnDirectDomain {
    IOService *device;
    uint64_t generation;
    bool (*live)(IOService &, uint64_t);
    bool (*canFetch)(IOService &, uint64_t, const IOMemoryDescriptor &, uint64_t, uint64_t, DcnDirectUse);

    bool empty() const { return !device && !generation && !live && !canFetch; }
    bool complete() const { return device && generation && live && canFetch; }
    bool current() const { return complete() && !device->isInactive() && live(*device, generation); }
    bool operator==(const DcnDirectDomain &other) const {
        return device == other.device && generation == other.generation && live == other.live && canFetch == other.canFetch;
    }

    bool permits(const IOMemoryDescriptor &descriptor, uint64_t offset, uint64_t physical, DcnDirectUse use) const {
        return validDmaSegment(physical, kPageBytes, kPageBytes) && current() &&
            canFetch(*device, generation, descriptor, offset, physical, use) && current();
    }
};

struct ScanoutDmaMapper {
    IOMapper *mapper;
    bool (*resolveMappedPage)(IOMapper &, const IODMACommand &, uint64_t, uint64_t &);
    bool (*confirmUnusedUnmap)(IOMapper &, const IODMACommand &);
    DcnDirectDomain direct{};

    bool completeContract() const {
        return direct.empty() ? mapper && resolveMappedPage && confirmUnusedUnmap :
            !mapper && !resolveMappedPage && !confirmUnusedUnmap && direct.complete();
    }

    bool current() const {
        return completeContract() && (mapper ? !mapper->isInactive() : direct.current());
    }
};

class DcnFlatDma {
    friend class DcnFlatTable;

    template<typename Current>
    bool prepare(const ScanoutDmaMapper &mapper, size_t bytes, const Current &live) {
        if (buffer_ || !mapper.current() || !bytes || bytes % kPageBytes ||
            bytes > kMaxBackingBytes / kPageBytes * sizeof(uint64_t) || !live()) return false;
        const size_t capacity = bytes + kPageBytes;
        direct_ = !mapper.mapper;
        const auto options = kIODirectionOut | kIOMemoryMapperNone | (direct_ ? kIOMemoryPhysicallyContiguous : 0);
        buffer_ = IOBufferMemoryDescriptor::inTaskWithOptions(kernel_task, options, capacity, kPageBytes);
        if (!buffer_) return false;
        words_ = static_cast<volatile uint64_t *>(buffer_->getBytesNoCopy());
        const auto address = reinterpret_cast<uintptr_t>(words_);
        if (!address || address % kPageBytes || capacity > UINTPTR_MAX - address ||
            buffer_->getLength() != capacity || !live()) return false;
        bytes_ = bytes;
        if (direct_) {
            IOByteCount contiguous = 0;
            const auto base = buffer_->getPhysicalSegment(0, &contiguous, kIOMemoryMapperNone);
            if (!validDmaSegment(base, bytes, bytes) || contiguous < bytes) return false;
            dmaAddress_ = base;
            return pagesCurrent(mapper, live);
        }
        command_ = IODMACommand::withSpecification(kIODMACommandOutputHost64, 48, 0, IODMACommand::kMapped,
                                                   bytes, kPageBytes, mapper.mapper);
        if (!command_) return false;
        if (command_->setMemoryDescriptor(buffer_, false) != kIOReturnSuccess) {
            if (command_->getMemoryDescriptor()) uncertain_ = true;
            else {
                command_->release();
                command_ = nullptr;
            }
            return false;
        }
        if (!live()) {
            if (command_->clearMemoryDescriptor(false) != kIOReturnSuccess) uncertain_ = true;
            else {
                command_->release();
                command_ = nullptr;
            }
            return false;
        }
        if (command_->prepare(0, bytes, false, false) != kIOReturnSuccess || command_->getIOMemoryDescriptor() != buffer_) {
            uncertain_ = true;
            return false;
        }
        UInt64 start = 0, length = 0;
        if (command_->getPreparedOffsetAndLength(&start, &length) != kIOReturnSuccess || start || length != bytes)
            return false;

        uint64_t base = 0;
        for (UInt64 cursor = 0; cursor < bytes;) {
            const auto covered = cursor;
            IODMACommand::Segment64 segment{};
            UInt32 count = 1;
            if (!live() || command_->gen64IOVMSegments(&cursor, &segment, &count) != kIOReturnSuccess || count != 1 ||
                !validDmaSegment(segment.fIOVMAddr, segment.fLength, bytes - covered) || cursor != covered + segment.fLength)
                return false;
            if (!covered) base = segment.fIOVMAddr;
            if (bytes > kAddressLimit - base || segment.fIOVMAddr != base + covered) return false;
        }
        dmaAddress_ = base;
        return pagesCurrent(mapper, live);
    }

    template<typename Current>
    bool pagesCurrent(const ScanoutDmaMapper &mapper, const Current &live) const {
        if (!mapped() || !mapper.current() || direct_ != mapper.direct.complete()) return false;
        for (size_t offset = 0; offset < bytes_; offset += kPageBytes) {
            IOByteCount contiguous = 0;
            const auto physical = buffer_->getPhysicalSegment(offset, &contiguous, kIOMemoryMapperNone);
            uint64_t resolved = 0;
            if (!live() || !physical || physical % kPageBytes || contiguous < kPageBytes || (direct_ ?
                physical != dmaAddress_ + offset || !mapper.direct.permits(*buffer_, offset, physical, DcnDirectUse::Table) :
                !mapper.resolveMappedPage(*mapper.mapper, *command_, dmaAddress_ + offset, resolved) || resolved != physical))
                return false;
        }
        return live();
    }

    bool store() const { return buffer_->performOperation(kIOMemoryIncoherentIOStore, 0, bytes_) == kIOReturnSuccess; }

    bool mapped() const {
        return dmaAddress_ && !withdrawn_ && !uncertain_ && (direct_ || (command_ && command_->getIOMemoryDescriptor() == buffer_));
    }

    bool withdraw(const ScanoutDmaMapper &mapper) {
        if (uncertain_) return false;
        if (!buffer_ || withdrawn_) return true;
        if (!command_) {
            withdrawn_ = true;
            return true;
        }
        if (command_->complete(false, false) != kIOReturnSuccess || !mapper.confirmUnusedUnmap(*mapper.mapper, *command_) ||
            command_->clearMemoryDescriptor(false) != kIOReturnSuccess) {
            uncertain_ = true;
            return false;
        }
        withdrawn_ = true;
        return true;
    }

    void release() {
        if (command_) command_->release();
        if (buffer_) buffer_->release();
        *this = {};
    }

    IOBufferMemoryDescriptor *buffer_{nullptr};
    IODMACommand *command_{nullptr};
    volatile uint64_t *words_{nullptr};
    size_t bytes_{0};
    uint64_t dmaAddress_{0};
    bool direct_{false}, uncertain_{false}, withdrawn_{false};
};

}
