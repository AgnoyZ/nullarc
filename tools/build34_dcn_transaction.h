#pragma once

#include "build34_dcn_flip_commit.h"

#define BUILD34_DCN_PRESENT_TRANSACTION "phx34DcnPresentTransactionV1"

namespace build34::dcn {

enum class DcnPresentResult { Blocked, Copy, Direct };

struct DcnPresentTransaction {
    OSObject *pipe;
    IOService *framebuffer;
    const void *transaction;
    const PresentCopyBacking *backing;
    DcnPresentResult result;
};

struct DcnPresentPlacement {
    HubpAddress next;
    bool direct;
};

class DcnPresentCompletion {
public:
    void legacy() { __atomic_store_n(&state_, uintptr_t{0}, __ATOMIC_RELEASE); }
    void block() { __atomic_store_n(&state_, uintptr_t{1}, __ATOMIC_RELEASE); }

    void presented(const void *transaction) {
        const auto identity = reinterpret_cast<uintptr_t>(transaction);
        if (identity > 1) __atomic_store_n(&state_, identity, __ATOMIC_RELEASE);
    }

    bool check(const void *transaction, bool &complete) const {
        const auto state = __atomic_load_n(&state_, __ATOMIC_ACQUIRE);
        complete = state > 1 && state == reinterpret_cast<uintptr_t>(transaction);
        return state != 0;
    }

private:
    uintptr_t state_{0};
};

template<typename Poll, typename InBudget, typename Pause>
bool waitDcnPresent(ScanoutPinToken operation, ScanoutFlipResult issued, Poll poll, InBudget inBudget, Pause pause) {
    if (!operation.provider || !operation.serial || issued != ScanoutFlipResult::Issued) return false;
    for (unsigned attempt = 0; attempt < 64 && inBudget(); ++attempt) {
        ScanoutFlipPoll sample{operation, ScanoutFlipResult::Uncertain};
        const auto status = poll(sample);
        if (!(sample.operation == operation)) return false;
        if (status == kIOReturnSuccess && sample.result == ScanoutFlipResult::Presented) return inBudget();
        if (status != kIOReturnBusy && (status != kIOReturnSuccess || sample.result != ScanoutFlipResult::Waiting)) return false;
        if (attempt + 1 < 64 && inBudget()) pause();
    }
    return false;
}

}
