#pragma once

#include "build34_dcn_flip_program.h"
#include "build34_dcn_scanout_dma.h"

#define BUILD34_DCN_FLIP_BEGIN "phx34DcnFlipBeginV1"
#define BUILD34_DCN_FLIP_POLL "phx34DcnFlipPollV1"

namespace build34::dcn {

enum class ScanoutFlipResult { Refused, Issued, Waiting, Presented, Uncertain };

struct ScanoutFlipIntent {
    HubpAddress previous, next;
    ScanoutPinToken nextPin, operation;
    ScanoutFlipResult result;
};

struct ScanoutFlipPoll {
    ScanoutPinToken operation;
    ScanoutFlipResult result;
};

struct ScanoutFlipBinding {
    ScanoutPinToken token;
    ScanoutDescriptorPin *pin;
    ScanoutDmaLease *dma;
    uint64_t window, bytes;
};

struct HubpFlipRoute {
    const void *owner;
    uint64_t generation;
    OSObject *lifetime;
    HubpFlipReader reader;
    HubpFlipWriter writer;
    bool (*qualify)(void *, const HubpFlipRequest &, const IODMACommand *, const IODMACommand *);
    bool (*fetchesRetired)(void *, const HubpFlipRequest &);
};

class ScanoutFlipCommit {
public:
    bool pending() const { return operation_.serial != 0; }
    ScanoutPinToken front() const { return front_; }
    bool matches(ScanoutPinToken token) const { return pending() && operation_ == token; }

    template<typename IsLive>
    ScanoutFlipResult begin(ScanoutFlipIntent intent, ScanoutPinToken operation, HubpFlipRoute route,
                           ScanoutFlipBinding old, ScanoutFlipBinding next, IsLive live) {
        if (pending() || !live() || !operation.provider || !operation.serial ||
            !intent.previous.valid() || !intent.next.valid() || !route.lifetime || !route.qualify ||
            !route.fetchesRetired || !(old.token == front_) || !(next.token == intent.nextPin) ||
            !validBinding(old, intent.previous, operation.provider, true) ||
            !validBinding(next, intent.next, operation.provider, false) ||
            (old.bytes && next.bytes && (old.window <= next.window ? next.window - old.window < old.bytes :
                                         old.window - next.window < next.bytes)) ||
            (old.token.serial && (!(frontAddress_ == intent.previous) || route.owner != routeOwner_ ||
                                  route.generation != routeGeneration_ || route.lifetime != routeLifetime_)))
            return ScanoutFlipResult::Refused;

        const HubpFlipRequest request{route.owner, route.generation, operation.serial, intent.previous, intent.next,
                                      old.token, next.token};
        readback_.recycle();
        if (!routeLifetime_) route.lifetime->retain();
        if (!route.qualify(route.reader.context, request, old.dma ? old.dma->command_ : nullptr,
                           next.dma ? next.dma->command_ : nullptr) ||
            !live() || !readback_.begin(request, route.reader) ||
            !HubpFlipProgram::preflight(request, route.reader, route.writer, [&] { return live() && readback_.stillInBudget(); }) ||
            !live() ||
            (next.pin && !next.pin->beginDisplayUse())) {
            if (!routeLifetime_) route.lifetime->release();
            readback_.recycle();
            return ScanoutFlipResult::Refused;
        }

        routeLifetime_ = route.lifetime;
        operation_ = operation;
        request_ = request;
        route_ = route;
        old_ = old;
        if (!HubpFlipProgram::issue(request_, route_.reader, route_.writer,
                                    [&] { return live() && readback_.stillInBudget(); }) ||
            !route_.reader.current(route_.reader.context, request_) || !live())
            return fail();
        return ScanoutFlipResult::Issued;
    }

    template<typename IsLive>
    ScanoutFlipResult poll(ScanoutPinToken operation, IsLive live, OSObject *&releaseRoute) {
        if (!matches(operation)) return ScanoutFlipResult::Refused;
        if (uncertain_) return ScanoutFlipResult::Uncertain;
        if (!live()) return fail();
        const auto progress = readback_.poll();
        if (progress == HubpFlipProgress::Uncertain || !live()) return fail();
        if (progress != HubpFlipProgress::OldAddressAbsent) return ScanoutFlipResult::Waiting;
        const bool retired = route_.fetchesRetired(route_.reader.context, request_);
        if (!route_.reader.current(route_.reader.context, request_) || !readback_.stillInBudget() || !live()) return fail();
        if (!retired) return ScanoutFlipResult::Waiting;
        if (old_.pin && (!old_.dma->releaseUnmapped() || !old_.pin->retireDisplayUse())) return fail();
        front_ = request_.nextPin;
        frontAddress_ = request_.next;
        routeOwner_ = request_.routeOwner;
        routeGeneration_ = request_.routeGeneration;
        operation_ = {};
        old_ = {};
        request_ = {};
        route_ = {};
        readback_.recycle();
        if (!front_.serial) {
            releaseRoute = routeLifetime_;
            routeLifetime_ = nullptr;
            routeOwner_ = nullptr;
            routeGeneration_ = 0;
        }
        return ScanoutFlipResult::Presented;
    }

private:
    static bool validBinding(ScanoutFlipBinding binding, HubpAddress address, const void *provider, bool displayed) {
        if (!binding.token.serial) return !binding.token.provider && !binding.pin && !binding.dma && !binding.bytes;
        return binding.token.provider == provider && binding.pin && binding.dma && binding.window == address.address &&
            binding.bytes == binding.pin->lease_.bytes() && binding.bytes <= kAddressLimit - binding.window &&
            binding.dma->command_ && !binding.dma->uncertain() && binding.pin->held() &&
            binding.pin->displayUse_ == displayed;
    }

    ScanoutFlipResult fail() {
        uncertain_ = true;
        return ScanoutFlipResult::Uncertain;
    }

    HubpFlipReadback readback_;
    ScanoutPinToken front_{}, operation_{};
    HubpAddress frontAddress_{};
    const void *routeOwner_{nullptr};
    OSObject *routeLifetime_{nullptr};
    uint64_t routeGeneration_{0};
    HubpFlipRequest request_{};
    HubpFlipRoute route_{};
    ScanoutFlipBinding old_{};
    bool uncertain_{false};
};

}
