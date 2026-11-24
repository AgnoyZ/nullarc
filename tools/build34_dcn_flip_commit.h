#pragma once

#include "build34_dcn_flat_program.h"
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
    uint64_t window;
    ScanoutSurface surface;
};

struct HubpFlipRoute {
    const void *owner;
    uint64_t generation;
    OSObject *lifetime;
    HubpFlipReader reader;
    HubpFlipWriter writer;
    bool (*qualify)(void *, const HubpFlipRequest &, const IODMACommand *, const IODMACommand *);
    DcnFlatFormat flatFormat;
    bool (*fetchesRetired)(void *, const HubpFlipRequest &);
    bool (*canInstallFlatVm)(void *, const HubpFlipRequest &, const DcnFlatContext &);
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
            !route.flatFormat.complete() || !route.canInstallFlatVm || !route.fetchesRetired ||
            !(old.token == front_) || !(next.token == intent.nextPin) ||
            !validBinding(old, intent.previous, operation.provider, true) ||
            !validBinding(next, intent.next, operation.provider, false) ||
            ((old.pin || next.pin) && intent.previous.vmid == intent.next.vmid) ||
            (old.pin && next.pin && (!sameFlipGeometry(old.surface, next.surface) ||
                (old.window <= next.window ? next.window - old.window < old.surface.mappedBytes :
                                            old.window - next.window < next.surface.mappedBytes))) ||
            (old.token.serial && (!(frontAddress_ == intent.previous) || route.owner != routeOwner_ ||
                                  route.generation != routeGeneration_ || route.lifetime != routeLifetime_)))
            return ScanoutFlipResult::Refused;

        const HubpFlipRequest request{route.owner, route.generation, operation.serial, intent.previous, intent.next,
                                      old.token, next.token};
        const auto surface = next.pin ? next.surface : old.surface;
        readback_.recycle();
        if (!routeLifetime_) route.lifetime->retain();
        auto withinBudget = [&] { return live() && readback_.stillInBudget(); };
        auto translationCurrent = [&] {
            return withinBudget() && route.reader.current(route.reader.context, request) && withinBudget();
        };
        auto *oldTable = old.dma ? &old.dma->table_ : nullptr;
        auto *nextTable = next.dma ? &next.dma->table_ : nullptr;
        const auto nextCurrent = [&] { return !nextTable || tableCurrent(next.dma, nextTable->vm_, translationCurrent); };
        const auto oldCurrent = [&] { return tableCurrent(old.dma, frontVm_, translationCurrent); };
        auto inactive = [&] {
            return nextTable && nextCurrent() &&
                route.canInstallFlatVm(route.reader.context, request, nextTable->vm_) && translationCurrent();
        };
        auto oldInstalled = [&] { return oldCurrent() && contextCurrent(frontVm_, route.reader, translationCurrent); };
        auto contextsCurrent = [&] {
            return oldInstalled() && nextCurrent() &&
                (!nextTable || contextCurrent(nextTable->vm_, route.reader, translationCurrent));
        };
        const auto nextEmpty = [&] { return !nextTable || DcnFlatProgram::empty(intent.next.vmid, route.reader, inactive); };
        if (!route.qualify(route.reader.context, request, old.dma ? old.dma->command_ : nullptr,
                           next.dma ? next.dma->command_ : nullptr) ||
            !live() || !readback_.begin(request, route.reader) ||
            (oldTable && !oldTable->matches(request, *route.lifetime, old.token, intent.previous.vmid)) || !oldInstalled() ||
            !HubpFlipProgram::preflight(request, route.reader, route.writer, surface, withinBudget) ||
            (nextTable && !nextTable->prepare(route.flatFormat, route.reader.context, *route.lifetime, request,
                next.dma->qualified_, *next.dma->command_, next.dma->layout_, next.dma->pages_, oldTable, translationCurrent)) ||
            !nextEmpty() || !matchesTranslation(old.dma, translationCurrent) || !matchesTranslation(next.dma, translationCurrent) ||
            !oldInstalled() || !nextEmpty() || !live() ||
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
        nextDma_ = next.dma;
        nextVm_ = nextTable ? nextTable->vm_ : DcnFlatContext{};
        surface_ = surface;
        if ((nextTable && !DcnFlatProgram::install(nextVm_, route_.reader, route_.writer, inactive)) ||
            !HubpFlipProgram::issue(request_, route_.reader, route_.writer, surface_, withinBudget, contextsCurrent) ||
            !route_.reader.current(route_.reader.context, request_) || !live())
            return fail();
        return ScanoutFlipResult::Issued;
    }

    template<typename IsLive>
    ScanoutFlipResult poll(ScanoutPinToken operation, IsLive live, OSObject *&releaseRoute) {
        if (!matches(operation)) return ScanoutFlipResult::Refused;
        if (uncertain_) return ScanoutFlipResult::Uncertain;
        auto withinBudget = [&] { return live() && readback_.stillInBudget(); };
        auto translationCurrent = [&] {
            return withinBudget() && route_.reader.current(route_.reader.context, request_) && withinBudget();
        };
        auto nextCurrent = [&] {
            return tableCurrent(nextDma_, nextVm_, translationCurrent) && contextCurrent(nextVm_, route_.reader, translationCurrent);
        };
        auto oldCurrent = [&] {
            return retirementStarted_ || (tableCurrent(old_.dma, frontVm_, translationCurrent) &&
                contextCurrent(frontVm_, route_.reader, translationCurrent));
        };
        if (!live() || !nextCurrent() || !oldCurrent()) return fail();
        const auto progress = readback_.poll();
        if (progress == HubpFlipProgress::Uncertain || !live()) return fail();
        if (progress != HubpFlipProgress::OldAddressAbsent) return ScanoutFlipResult::Waiting;
        auto currentGeometry = [&] {
            return HubpFlipProgram::geometryCurrent(request_, route_.reader, surface_, withinBudget);
        };
        if (!currentGeometry() || !oldCurrent() || !nextCurrent()) return fail();
        retirementStarted_ = true;
        const bool retired = route_.fetchesRetired(route_.reader.context, request_);
        if (!nextCurrent() || !currentGeometry()) return fail();
        if (!retired) return ScanoutFlipResult::Waiting;
        if (old_.pin) {
            auto detached = [&] { return DcnFlatProgram::empty(frontVm_.vmid, route_.reader, translationCurrent); };
            if (!detached() || !old_.dma->table_.withdraw(old_.dma->qualified_) || !nextCurrent() || !currentGeometry() ||
                !detached() || !old_.dma->releaseUnmapped() || !old_.pin->retireDisplayUse()) return fail();
        }
        front_ = request_.nextPin;
        frontAddress_ = request_.next;
        frontVm_ = nextVm_;
        routeOwner_ = request_.routeOwner;
        routeGeneration_ = request_.routeGeneration;
        operation_ = {};
        old_ = {};
        request_ = {};
        route_ = {};
        nextDma_ = nullptr;
        nextVm_ = {};
        surface_ = {};
        retirementStarted_ = false;
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
        if (!binding.token.serial)
            return !binding.token.provider && !binding.pin && !binding.dma && !binding.surface.mappedBytes;
        return address.vmid && binding.token.provider == provider && binding.pin && binding.dma &&
            binding.window == address.address &&
            validFlipGeometry(binding.surface) && binding.surface.mappedBytes == binding.pin->lease_.bytes() &&
            binding.surface.mappedBytes <= kAddressLimit - binding.window &&
            binding.dma->command_ && binding.dma->pages_ && !binding.dma->uncertain() &&
            binding.dma->layout_.firstLogicalPage == binding.window / kPageBytes &&
            binding.dma->layout_.entryCount == binding.surface.mappedBytes / kPageBytes && binding.pin->held() &&
            binding.pin->displayUse_ == displayed;
    }

    template<typename Current>
    static bool tableCurrent(const ScanoutDmaLease *dma, const DcnFlatContext &context, const Current &current) {
        return !dma ? !context.vmid : current() && dma->table_.vm_ == context &&
            dma->table_.current(dma->qualified_, *dma->command_) && current();
    }

    template<typename Current>
    static bool contextCurrent(const DcnFlatContext &context, const HubpFlipReader &reader, const Current &current) {
        return !context.vmid || matchDcnFlatContext(context, reader, current);
    }

    template<typename Current>
    static bool matchesTranslation(const ScanoutDmaLease *dma, const Current &current) {
        return !dma || dma->table_.matchesPages(dma->qualified_, *dma->command_, dma->layout_, dma->pages_, current);
    }

    ScanoutFlipResult fail() {
        uncertain_ = true;
        return ScanoutFlipResult::Uncertain;
    }

    HubpFlipReadback readback_;
    ScanoutPinToken front_{}, operation_{};
    HubpAddress frontAddress_{};
    DcnFlatContext frontVm_{}, nextVm_{};
    const void *routeOwner_{nullptr};
    OSObject *routeLifetime_{nullptr};
    uint64_t routeGeneration_{0};
    HubpFlipRequest request_{};
    HubpFlipRoute route_{};
    ScanoutFlipBinding old_{};
    ScanoutDmaLease *nextDma_{nullptr};
    ScanoutSurface surface_{};
    bool retirementStarted_{false};
    bool uncertain_{false};
};

}
