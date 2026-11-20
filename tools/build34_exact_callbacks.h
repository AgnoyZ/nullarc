// SPDX-License-Identifier: MIT
// CPU callback admission only. The enclosing object must already be alive.
// Neither closing nor draining proves GPU completion or permits BO/VM release.
#ifndef BUILD34_EXACT_CALLBACKS_H
#define BUILD34_EXACT_CALLBACKS_H

#include <stdint.h>

namespace phx34_exact {

template<uint32_t Limit = 0x7fffffffu>
class CallbackGate {
    static constexpr uint32_t closing = 0x80000000u;
    static_assert(Limit > 0 && Limit < closing, "bounded callback count");
    static_assert(__atomic_always_lock_free(sizeof(uint32_t), nullptr),
                  "no out-of-line atomic runtime or allocated lifetime lock");
    alignas(uint32_t) uint32_t state_ = 0;

    bool enter() {
        uint32_t state = __atomic_load_n(&state_, __ATOMIC_ACQUIRE);
        for (;;) {
            if ((state & closing) || state == Limit) return false;
            if (__atomic_compare_exchange_n(&state_, &state, state + 1, false,
                                            __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) return true;
        }
    }
    void leave() { __atomic_fetch_sub(&state_, 1, __ATOMIC_RELEASE); }
public:
    CallbackGate() = default;
    CallbackGate(const CallbackGate &) = delete;
    CallbackGate &operator=(const CallbackGate &) = delete;
    class Lease {
        CallbackGate *gate_;
    public:
        explicit Lease(CallbackGate &gate) : gate_(gate.enter() ? &gate : nullptr) {}
        ~Lease() { if (gate_) gate_->leave(); }
        Lease(const Lease &) = delete;
        Lease &operator=(const Lease &) = delete;
        explicit operator bool() const { return gate_ != nullptr; }
    };
    // One winner, no reopen, no reset and no callback from the last releaser.
    bool close() { return !(__atomic_fetch_or(&state_, closing, __ATOMIC_ACQ_REL) & closing); }
    bool closed() const { return (__atomic_load_n(&state_, __ATOMIC_ACQUIRE) & closing) != 0; }
    uint32_t active() const { return __atomic_load_n(&state_, __ATOMIC_ACQUIRE) & ~closing; }
    bool drained() const { return __atomic_load_n(&state_, __ATOMIC_ACQUIRE) == closing; }
};

} // namespace phx34_exact
#endif
