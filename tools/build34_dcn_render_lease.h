#pragma once

#include "build34_dcn_descriptor_backing.h"

namespace build34::dcn {

class RenderDescriptorLease {
public:
    RenderDescriptorLease() = default;
    RenderDescriptorLease(const RenderDescriptorLease &) = delete;
    RenderDescriptorLease &operator=(const RenderDescriptorLease &) = delete;

    bool acquire(const PinnedDescriptorSlice &slice, uint64_t expectedPreparation) {
        return expectedPreparation && hold(slice, expectedPreparation);
    }

    OriginalBacking backing() {
        return state_ == State::Held ? OriginalBacking{this, readPage} : OriginalBacking{};
    }

    uint64_t bytes() const { return state_ == State::Held ? slice_.bytes : 0; }

    bool releaseAfterRetirement() {
        if (state_ != State::Held)
            return false;
        state_ = State::Transition;
        return finish();
    }

    bool uncertain() const { return state_ == State::Uncertain; }

private:
    friend class ScanoutDescriptorPin;
    friend class ScanoutDmaLease;
    enum class State { Empty, Transition, Held, Closed, Uncertain };

    bool hold(const PinnedDescriptorSlice &slice, uint64_t &preparation) {
        const auto validPreparation = [](uint64_t value) {
            return value > kIOPreparationIDAlwaysPrepared && value != UINT64_MAX;
        };
        if (state_ != State::Empty || (preparation && !validPreparation(preparation))) return false;

        state_ = State::Transition;
        const auto candidate = slice;
        auto *descriptor = candidate.descriptor;
        if (!validDescriptorSlice(candidate) || descriptor->getLength() > kMaxBackingBytes ||
            (preparation && descriptor->getPreparationID() != preparation)) {
            state_ = State::Empty;
            return false;
        }
        descriptor->retain();
        if (descriptor->prepare() != kIOReturnSuccess) {
            descriptor->release();
            state_ = State::Empty;
            return false;
        }
        slice_ = candidate;
        const auto observed = descriptor->getPreparationID();
        if (!validPreparation(observed) || (preparation && observed != preparation)) {
            finish();
            return false;
        }
        preparation = observed;
        state_ = State::Held;
        return true;
    }

    void recycleClosed() {
        if (state_ == State::Closed)
            state_ = State::Empty;
    }

    static bool readPage(void *context, uint64_t offset, uint64_t *physical) {
        auto *lease = static_cast<RenderDescriptorLease *>(context);
        return lease && lease->state_ == State::Held && readPinnedDescriptorPage(&lease->slice_, offset, physical);
    }

    bool finish() {
        auto *descriptor = slice_.descriptor;
        if (descriptor->complete() != kIOReturnSuccess) {
            state_ = State::Uncertain;
            return false;
        }
        slice_ = {};
        descriptor->release();
        state_ = State::Closed;
        return true;
    }

    State state_ = State::Empty;
    PinnedDescriptorSlice slice_{};
};

}  // namespace build34::dcn
