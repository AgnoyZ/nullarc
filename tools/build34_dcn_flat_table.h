#pragma once

#include "build34_dcn_flat_context.h"
#include "build34_dcn_flat_dma.h"

namespace build34::dcn {

struct DcnPixelMapping {
    const IODMACommand *command;
    const DcnDirectDomain *direct;
};

struct DcnFlatMapping {
    DcnPixelMapping pixels;
    const IODMACommand *table;
    const IOMapper *mapper;
    const IOMemoryDescriptor *directTable;
    uint64_t address;
    size_t bytes;
};

struct DcnFlatFormat {
    bool (*encodeLeaf)(void *, const DcnFlatMapping &, uint64_t, uint64_t &);
    bool (*decodeLeaf)(void *, const DcnFlatMapping &, uint64_t, uint64_t &);
    bool (*encodeRoot)(void *, const DcnFlatMapping &, uint64_t &);
    bool (*visible)(void *, const DcnFlatMapping &, const DcnFlatContext &);

    bool complete(DcnPixelMapping pixels) const {
        return visible && (pixels.direct ? !pixels.command && pixels.direct->complete() :
            pixels.command && encodeLeaf && decodeLeaf && encodeRoot);
    }

    bool rootWord(void *context, const DcnFlatMapping &mapping, uint64_t &word) const {
        return mapping.pixels.direct ? mapping.directTable && !mapping.table && !mapping.mapper &&
            DcnHostFlatWords::root(mapping.pixels.direct->encoding, mapping.address, mapping.bytes, word) :
            encodeRoot(context, mapping, word);
    }

    bool leafWord(void *context, const DcnFlatMapping &mapping, uint64_t address, uint64_t &word) const {
        return mapping.pixels.direct ? DcnHostFlatWords::leaf(mapping.pixels.direct->encoding, address, word) :
            encodeLeaf(context, mapping, address, word);
    }

    bool leafAddress(void *context, const DcnFlatMapping &mapping, uint64_t word, uint64_t &address) const {
        return mapping.pixels.direct ? DcnHostFlatWords::decode(mapping.pixels.direct->encoding, word, address) :
            decodeLeaf(context, mapping, word, address);
    }
};

class DcnFlatTable {
    friend class ScanoutFlipCommit;
    friend class ScanoutDmaLease;

    bool overlaps(const DcnFlatTable *front, uint64_t root) const {
        if (!front || !dma_.dmaAddress_) return false;
        const auto first = dma_.dmaAddress_, second = front->dma_.dmaAddress_;
        return (root && root == front->vm_.rootEntry) || (first <= second ? second - first < dma_.bytes_ :
                                                                           first - second < front->dma_.bytes_);
    }

    template<typename Current>
    bool prepare(DcnFlatFormat format, void *ownerContext, OSObject &ownerLifetime, const HubpFlipRequest &request,
                 const ScanoutDmaMapper &mapper,
                 DcnPixelMapping pixels, const FlatPageLayout &layout, const uint64_t *pages,
                 const DcnFlatTable *front, const Current &live) {
        const size_t bytes = (layout.tableBytes + kPageBytes - 1) & ~(kPageBytes - 1);
        if (!live() || !bytes) return false;
        if (dma_.buffer_) {
            collided_ = collided_ || overlaps(front, vm_.rootEntry);
            return !collided_ && matches(request, ownerLifetime, request.nextPin, request.next.vmid) &&
                current(mapper, pixels) && live();
        }
        if (!format.complete(pixels)) return false;
        ownerLifetime.retain();
        ownerLifetime_ = &ownerLifetime;
        const bool ready = dma_.prepare(mapper, bytes, live);
        if (!dma_.buffer_) {
            release();
            return false;
        }
        collided_ = overlaps(front, 0);
        if (!ready || collided_ || !live()) return false;
        const auto mapping = view(mapper, pixels);
        uint64_t root = 0;
        const bool encoded = format.rootWord(ownerContext, mapping, root);
        collided_ = overlaps(front, root);
        const DcnFlatContext vm{root, layout.firstLogicalPage, layout.lastLogicalPage, request.next.vmid};
        if (!encoded || collided_ || !vm.valid()) return false;
        for (size_t index = 0; index < bytes / sizeof(uint64_t); ++index) {
            uint64_t word = 0;
            if (!live() || (index < layout.entryCount &&
                (!format.leafWord(ownerContext, mapping, pages[index], word) || !word))) return false;
            dma_.words_[index] = word;
        }
        if (!live() || !dma_.store() || !live()) return false;
        vm_ = vm;
        owner_ = request.routeOwner;
        generation_ = request.routeGeneration;
        token_ = request.nextPin;
        format_ = format;
        context_ = ownerContext;
        return current(mapper, pixels) && live();
    }

    bool matches(const HubpFlipRequest &request, const OSObject &ownerLifetime, ScanoutPinToken token, uint32_t vmid) const {
        return vm_.valid() && vm_.vmid == vmid && owner_ == request.routeOwner && generation_ == request.routeGeneration &&
            ownerLifetime_ == &ownerLifetime && token_ == token;
    }

    DcnFlatMapping view(const ScanoutDmaMapper &mapper, DcnPixelMapping pixels) const {
        return {pixels, dma_.command_, mapper.mapper, pixels.direct ? dma_.buffer_ : nullptr, dma_.dmaAddress_, dma_.bytes_};
    }

    bool current(const ScanoutDmaMapper &mapper, DcnPixelMapping pixels) const {
        return dma_.mapped() && vm_.valid() && token_.serial && mapper.current() &&
            format_.visible(context_, view(mapper, pixels), vm_) && mapper.current();
    }

    template<typename Current>
    bool matchesPages(const ScanoutDmaMapper &mapper, DcnPixelMapping pixels, const FlatPageLayout &layout,
                      const uint64_t *pages, const Current &live) const {
        if (!live() || !current(mapper, pixels) || !dma_.pagesCurrent(mapper, live)) return false;
        const auto mapping = view(mapper, pixels);
        for (size_t index = 0; index < mapping.bytes / sizeof(uint64_t); ++index) {
            if (!live()) return false;
            const auto word = dma_.words_[index];
            if (index >= layout.entryCount) {
                if (word) return false;
                continue;
            }
            uint64_t observed = 0;
            if (!word || !format_.leafAddress(context_, mapping, word, observed) || observed != pages[index]) return false;
        }
        return live() && current(mapper, pixels) && live();
    }

    bool withdraw(const ScanoutDmaMapper &mapper) {
        return !collided_ && dma_.withdraw(mapper);
    }

    void release() {
        dma_.release();
        if (ownerLifetime_) ownerLifetime_->release();
        *this = {};
    }

    DcnFlatDma dma_;
    DcnFlatFormat format_{};
    void *context_{nullptr};
    OSObject *ownerLifetime_{nullptr};
    const void *owner_{nullptr};
    uint64_t generation_{0};
    ScanoutPinToken token_{};
    DcnFlatContext vm_{};
    bool collided_{false};
};

}
