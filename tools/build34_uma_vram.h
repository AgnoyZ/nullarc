#pragma once

#include <stddef.h>
#include <stdint.h>

namespace build34::uma {

constexpr uint64_t kPageBytes = 4096;
constexpr uint64_t kBarBytes = 256ull << 20;
constexpr uint64_t kPilotBytes = 64ull << 20;
constexpr uint64_t kMcBase = 0x8000000000ull;
constexpr uint64_t kAddressLimit = 1ull << 48;

struct Range {
    uint64_t offset, bytes;

    bool within(uint64_t limit) const {
        return bytes && offset < limit && bytes <= limit - offset;
    }

    uint64_t end() const { return offset + bytes; }
};

struct Geometry {
    uint64_t mcBase, backingBase, bytes, barBytes;
};

struct Reservations {
    Range scanout, firmware, discovery;
    const Range *extra;
    size_t extraCount;
};

struct AllocationId {
    uint64_t serial;
    size_t slot;
};

struct Allocation {
    AllocationId id;
    Range range;
    uint64_t mcAddress, backingAddress;
};

struct MappingId {
    AllocationId allocation;
    uint64_t serial;
};

struct Leaf {
    uint64_t va, value;
};

enum class Access { ReadOnly, ReadWrite };
enum class Completion { Pending, Complete, Uncertain };

struct Usage {
    uint64_t capacity, reserved, quarantined;
    bool faulted;
};

class Pool {
public:
    static constexpr size_t kSlots = 64;

    Pool() = default;
    Pool(const Pool &) = delete;
    Pool &operator=(const Pool &) = delete;

    bool admit(Geometry geometry, Range ownedWindow, Reservations reserved) {
        constexpr uint64_t fbAlignment = 16ull << 20;
        if (window_.bytes || geometry.mcBase != kMcBase || !geometry.backingBase ||
            ((geometry.mcBase | geometry.backingBase | geometry.bytes) & (fbAlignment - 1)) ||
            !Range{geometry.mcBase, geometry.bytes}.within(kAddressLimit) ||
            !Range{geometry.backingBase, geometry.bytes}.within(kAddressLimit) ||
            geometry.barBytes != kBarBytes || !ownedWindow.within(geometry.bytes) ||
            ownedWindow.offset < geometry.barBytes || ownedWindow.bytes > kPilotBytes ||
            ((ownedWindow.offset | ownedWindow.bytes) & (kPageBytes - 1)) ||
            reserved.extraCount > 32 || (reserved.extraCount && !reserved.extra)) return false;

        const Range required[] = {reserved.scanout, reserved.firmware, reserved.discovery};
        for (const Range range : required)
            if (!range.within(geometry.bytes) || overlaps(ownedWindow, range)) return false;
        for (size_t index = 0; index < reserved.extraCount; ++index)
            if (!reserved.extra[index].within(geometry.bytes) || overlaps(ownedWindow, reserved.extra[index])) return false;

        geometry_ = geometry;
        window_ = ownedWindow;
        return true;
    }

    bool reserve(uint64_t owner, uint64_t bytes, uint64_t alignment, Allocation &out) {
        if (faulted_ || !owner || !bytes || bytes > window_.bytes || nextSerial_ == UINT64_MAX ||
            alignment < kPageBytes || alignment > (2ull << 20) || (alignment & (alignment - 1))) return false;
        bytes = alignUp(bytes, kPageBytes);

        size_t slot = 0;
        while (slot < kSlots && records_[slot].serial) ++slot;
        if (slot == kSlots) return false;

        for (uint64_t offset = alignUp(window_.offset, alignment);
             offset < window_.end() && bytes <= window_.end() - offset;) {
            const Range proposed{offset, bytes};
            uint64_t next = offset;
            for (const Record &record : records_)
                if (record.serial && overlaps(proposed, record.range) && record.range.end() > next)
                    next = record.range.end();
            if (next != offset) {
                offset = alignUp(next, alignment);
                continue;
            }
            Record &record = records_[slot];
            record = {owner, ++nextSerial_, proposed, State::Zeroing, {}};
            out = {{record.serial, slot}, proposed, geometry_.mcBase + offset, geometry_.backingBase + offset};
            return true;
        }
        return false;
    }

    bool finishZero(uint64_t owner, AllocationId allocation, Completion completion) {
        Record *record = find(owner, allocation);
        return record && record->state == State::Zeroing && transition(*record, completion, State::Ready);
    }

    bool beginMap(uint64_t owner, AllocationId allocation, uint64_t va, Range boRange, Access access, MappingId &out) {
        Record *record = find(owner, allocation);
        if (!record || record->state != State::Ready || nextSerial_ == UINT64_MAX ||
            !boRange.within(record->range.bytes) || !Range{va, boRange.bytes}.within(kAddressLimit) ||
            va < 0x10000 || ((va | boRange.offset | boRange.bytes) & (kPageBytes - 1)) ||
            (access != Access::ReadOnly && access != Access::ReadWrite)) return false;
        for (const Record &other : records_)
            if (other.owner == owner && other.mapping.serial &&
                overlaps({va, boRange.bytes}, {other.mapping.va, other.mapping.boRange.bytes})) return false;

        record->mapping = {++nextSerial_, va, boRange, access};
        record->state = State::Mapping;
        out = {allocation, record->mapping.serial};
        return true;
    }

    bool encodePte(uint64_t owner, MappingId mapping, uint64_t pageOffset, Leaf &out) const {
        const Record *record = find(owner, mapping.allocation);
        if (!record || record->state != State::Mapping || record->mapping.serial != mapping.serial ||
            pageOffset >= record->mapping.boRange.bytes || (pageOffset & (kPageBytes - 1))) return false;

        constexpr uint64_t validReadable = 0x21, writable = 0x40;
        const uint64_t address = geometry_.backingBase + record->range.offset + record->mapping.boRange.offset + pageOffset;
        out = {record->mapping.va + pageOffset,
               address | validReadable | (record->mapping.access == Access::ReadWrite ? writable : 0)};
        return true;
    }

    bool finishMap(uint64_t owner, MappingId mapping, Completion completion) {
        Record *record = find(owner, mapping.allocation);
        return record && record->state == State::Mapping && record->mapping.serial == mapping.serial &&
            transition(*record, completion, State::Mapped);
    }

    bool beginUnmap(uint64_t owner, MappingId mapping, Completion retirement) {
        Record *record = find(owner, mapping.allocation);
        return record && record->state == State::Mapped && record->mapping.serial == mapping.serial &&
            transition(*record, retirement, State::Unmapping);
    }

    bool finishUnmap(uint64_t owner, MappingId mapping, Completion completion) {
        Record *record = find(owner, mapping.allocation);
        if (!record || record->state != State::Unmapping || record->mapping.serial != mapping.serial ||
            !transition(*record, completion, State::Ready)) return false;
        record->mapping = {};
        return true;
    }

    bool release(uint64_t owner, AllocationId allocation) {
        Record *record = find(owner, allocation);
        if (!record || record->state != State::Ready) return false;
        *record = {};
        return true;
    }

    Usage usage() const {
        Usage result{window_.bytes, 0, 0, faulted_};
        for (const Record &record : records_) {
            if (!record.serial) continue;
            result.reserved += record.range.bytes;
            if (record.state == State::Quarantined) result.quarantined += record.range.bytes;
        }
        return result;
    }

private:
    enum class State { Zeroing, Ready, Mapping, Mapped, Unmapping, Quarantined };

    struct Mapping {
        uint64_t serial, va;
        Range boRange;
        Access access;
    };

    struct Record {
        uint64_t owner, serial;
        Range range;
        State state;
        Mapping mapping;
    };

    static uint64_t alignUp(uint64_t value, uint64_t alignment) {
        return (value + alignment - 1) & ~(alignment - 1);
    }

    static bool overlaps(Range left, Range right) {
        return left.offset < right.end() && right.offset < left.end();
    }

    const Record *find(uint64_t owner, AllocationId allocation) const {
        if (faulted_ || !owner || !allocation.serial || allocation.slot >= kSlots) return nullptr;
        const Record &record = records_[allocation.slot];
        return record.owner == owner && record.serial == allocation.serial ? &record : nullptr;
    }

    Record *find(uint64_t owner, AllocationId allocation) {
        return const_cast<Record *>(static_cast<const Pool *>(this)->find(owner, allocation));
    }

    bool transition(Record &record, Completion completion, State next) {
        if (completion == Completion::Uncertain) {
            record.state = State::Quarantined;
            faulted_ = true;
        }
        if (completion != Completion::Complete) return false;
        record.state = next;
        return true;
    }

    Geometry geometry_{};
    Range window_{};
    uint64_t nextSerial_{0};
    bool faulted_{false};
    Record records_[kSlots]{};
};

}
