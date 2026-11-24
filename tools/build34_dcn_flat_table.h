#pragma once

#include <IOKit/IODMACommand.h>

#include "build34_dcn_flat_context.h"
#include "build34_dcn_page_layout.h"

namespace build34::dcn {

struct DcnFlatAllocation {
    OSObject *lease;
    volatile uint64_t *words;
    size_t bytes;
    bool (*encodeLeaf)(const OSObject &, uint64_t, uint64_t &);
    bool (*decodeLeaf)(const OSObject &, uint64_t, uint64_t &);
    bool (*publish)(OSObject &, const IODMACommand &, uint64_t &);
    bool (*current)(const OSObject &, const IODMACommand &, uint64_t);
    bool (*withdraw)(OSObject &, const IODMACommand &);
};

using AllocateDcnFlat = DcnFlatAllocation (*)(void *, const HubpFlipRequest &, const IODMACommand &, size_t);

class DcnFlatTable {
    friend class ScanoutFlipCommit;
    friend class ScanoutDmaLease;

    static bool disjoint(uintptr_t first, size_t firstBytes, uintptr_t second, size_t secondBytes) {
        return first < second ? second - first >= firstBytes : first - second >= secondBytes;
    }

    bool overlaps(const DcnFlatTable *front, size_t bytes, uint64_t root) const {
        if (!front) return false;
        const auto address = reinterpret_cast<uintptr_t>(allocation_.words);
        return allocation_.lease == front->allocation_.lease || (root && root == front->vm_.rootEntry) ||
            (address && !disjoint(address, bytes, reinterpret_cast<uintptr_t>(front->allocation_.words), front->allocation_.bytes));
    }

    template<typename Current>
    bool prepare(AllocateDcnFlat allocate, void *ownerContext, OSObject &ownerLifetime, const HubpFlipRequest &request,
                 const IODMACommand &command, const FlatPageLayout &layout, const uint64_t *pages,
                 const DcnFlatTable *front, const Current &live) {
        const size_t bytes = (layout.tableBytes + kPageBytes - 1) & ~(kPageBytes - 1);
        if (!live() || !bytes) return false;
        if (allocation_.lease) {
            collided_ = collided_ || overlaps(front, bytes, vm_.rootEntry);
            return !collided_ && matches(request, ownerLifetime, request.nextPin, request.next.vmid) && current(command) && live();
        }
        allocation_ = allocate(ownerContext, request, command, bytes);
        if (!allocation_.lease) return false;
        ownerLifetime.retain();
        ownerLifetime_ = &ownerLifetime;
        const auto &storage = allocation_;
        const auto address = reinterpret_cast<uintptr_t>(storage.words);
        collided_ = overlaps(front, bytes, 0);
        if (collided_ || !address || address % kPageBytes || storage.bytes != bytes ||
            bytes > UINTPTR_MAX - address || !storage.encodeLeaf || !storage.decodeLeaf || !storage.publish ||
            !storage.current || !storage.withdraw || !live() ||
            !disjoint(address, bytes, reinterpret_cast<uintptr_t>(pages), layout.tableBytes))
            return false;

        for (size_t index = 0; index < bytes / sizeof(uint64_t); ++index) {
            uint64_t word = 0;
            if (!live() || (index < layout.entryCount &&
                (!storage.encodeLeaf(*storage.lease, pages[index], word) || !word))) return false;
            storage.words[index] = word;
        }
        uint64_t root = 0;
        if (!live()) return false;
        const bool published = storage.publish(*storage.lease, command, root);
        collided_ = overlaps(front, bytes, root);
        if (!published || collided_ || !live()) return false;
        vm_ = {root, layout.firstLogicalPage, layout.lastLogicalPage, request.next.vmid};
        if (!vm_.valid()) return false;
        owner_ = request.routeOwner;
        generation_ = request.routeGeneration;
        token_ = request.nextPin;
        return current(command) && live();
    }

    bool matches(const HubpFlipRequest &request, const OSObject &ownerLifetime, ScanoutPinToken token, uint32_t vmid) const {
        return vm_.valid() && vm_.vmid == vmid && owner_ == request.routeOwner && generation_ == request.routeGeneration &&
            ownerLifetime_ == &ownerLifetime && token_ == token;
    }

    bool current(const IODMACommand &command) const {
        return allocation_.lease && !withdrawn_ && vm_.valid() && token_.serial &&
            allocation_.current(*allocation_.lease, command, vm_.rootEntry);
    }

    template<typename Current>
    bool matchesPages(const IODMACommand &command, const FlatPageLayout &layout, const uint64_t *pages,
                      const Current &live) const {
        if (!live() || !current(command)) return false;
        for (size_t index = 0; index < allocation_.bytes / sizeof(uint64_t); ++index) {
            if (!live()) return false;
            const auto word = allocation_.words[index];
            if (index >= layout.entryCount) {
                if (word) return false;
                continue;
            }
            uint64_t observed = 0;
            if (!word || !allocation_.decodeLeaf(*allocation_.lease, word, observed) || observed != pages[index]) return false;
        }
        return live() && current(command) && live();
    }

    bool withdraw(const IODMACommand &command) {
        if (!allocation_.lease || withdrawn_) return true;
        return (withdrawn_ = !collided_ && allocation_.withdraw && allocation_.withdraw(*allocation_.lease, command));
    }

    void release() {
        if (allocation_.lease) allocation_.lease->release();
        if (ownerLifetime_) ownerLifetime_->release();
        *this = {};
    }

    DcnFlatAllocation allocation_{};
    OSObject *ownerLifetime_{nullptr};
    const void *owner_{nullptr};
    uint64_t generation_{0};
    ScanoutPinToken token_{};
    DcnFlatContext vm_{};
    bool withdrawn_{false};
    bool collided_{false};
};

}
