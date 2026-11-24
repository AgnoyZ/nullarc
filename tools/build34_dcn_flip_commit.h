#pragma once

#include "build34_dcn_flat_program.h"
#include "build34_dcn_firmware_home.h"
#include "build34_dcn_scanout_dma.h"

#define BUILD34_DCN_FLIP_BEGIN "phx34DcnFlipBeginV3"
#define BUILD34_DCN_FLIP_POLL "phx34DcnFlipPollV2"

namespace build34::dcn {

enum class ScanoutFlipResult { Refused, Issued, Waiting, Presented, Uncertain };
enum class DcnRetirement { Pending, Complete, Lost };

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
    bool (*qualify)(void *, const HubpFlipRequest &, DcnPixelMapping, DcnPixelMapping);
    DcnFlatFormat flatFormat;
    bool (*fetchesRetired)(void *, const HubpFlipRequest &);
    bool (*canInstallFlatVm)(void *, const HubpFlipRequest &, const DcnFlatContext &);
    bool (*canClearFlatVm)(void *, const HubpFlipRequest &, const DcnFlatContext &);
    DcnRetirement (*translationsRetired)(void *, const HubpFlipRequest &, const DcnFlatContext &);
    IOService *framebuffer;
};

class ScanoutFlipCommit {
public:
    bool pending() const { return operation_.serial != 0; }
    ScanoutPinToken front() const { return front_; }
    bool matches(ScanoutPinToken token) const { return pending() && operation_ == token; }

    template<typename IsLive, typename WriterCurrent>
    ScanoutFlipResult begin(ScanoutFlipIntent intent, ScanoutPinToken operation, HubpFlipRoute route,
                           void *pci, ScanoutFlipBinding old, ScanoutFlipBinding next, IsLive live, WriterCurrent writerCurrent) {
        if (pending() || !live() || !operation.provider || !operation.serial ||
            !intent.previous.valid() || !intent.next.valid() || !route.lifetime || !route.qualify ||
            !route.canInstallFlatVm || !route.fetchesRetired ||
            !route.canClearFlatVm || !route.translationsRetired || !route.framebuffer || !pci ||
            !(old.token == front_) || !(next.token == intent.nextPin) ||
            !validBinding(old, intent.previous, operation.provider, pci, true) ||
            !validBinding(next, intent.next, operation.provider, pci, false) ||
            (old.pin && !route.flatFormat.complete(mapping(old))) || (next.pin && !route.flatFormat.complete(mapping(next))) ||
            (old.dma && next.dma && !(old.dma->qualified_.direct == next.dma->qualified_.direct)) ||
            ((old.pin || next.pin) && intent.previous.vmid == intent.next.vmid) ||
            (old.pin && next.pin && (!sameFlipGeometry(old.surface, next.surface) ||
                (old.window <= next.window ? next.window - old.window < old.surface.mappedBytes :
                                            old.window - next.window < next.surface.mappedBytes))) ||
            (old.token.serial && (!(frontAddress_ == intent.previous) || route.owner != routeOwner_ ||
                                  route.generation != routeGeneration_ || route.lifetime != routeLifetime_ ||
                                  route.framebuffer != framebuffer_ || pci != pci_)) ||
            (next.pin && !writerCurrent()))
            return ScanoutFlipResult::Refused;

        const HubpFlipRequest request{route.owner, route.generation, operation.serial, intent.previous, intent.next,
                                      old.token, next.token};
        const auto surface = next.pin ? next.surface : old.surface;
        const FirmwareFlatWindows windows{directWindow(old), directWindow(next)};
        readback_.recycle();
        if (!routeLifetime_) {
            route.lifetime->retain();
            route.framebuffer->retain();
        }
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
                (!nextTable || (contextCurrent(nextTable->vm_, route.reader, translationCurrent) && writerCurrent() && withinBudget()));
        };
        FirmwareScanoutSample home = firmwareHome_;
        const auto captureHome = [&] {
            if (!old.pin && (!translationCurrent() || route.framebuffer->callPlatformFunction(BUILD34_DCN_SAMPLE_FIRMWARE,
                false, pci, &home, nullptr, nullptr) != kIOReturnSuccess || !translationCurrent())) return false;
            return home.valid() && sameFlipGeometry(home.surface, surface) &&
                (old.pin || intent.previous == home.scanout) && (next.pin || intent.next == home.scanout);
        };
        const auto homeCurrent = [&] { return checkFirmware(*route.framebuffer, pci, home, windows, translationCurrent); };
        const auto peersIdle = [&] { return HubpFlipProgram::peersIdle(request, route.reader, withinBudget); };
        const auto nextEmpty = [&] { return !nextTable || DcnFlatProgram::empty(intent.next.vmid, route.reader, inactive); };
        if (!route.qualify(route.reader.context, request, mapping(old), mapping(next)) ||
            !live() || !readback_.begin(request, route.reader) || !captureHome() || !homeCurrent() ||
            (oldTable && !oldTable->matches(request, *route.lifetime, old.token, intent.previous.vmid)) || !oldInstalled() ||
            !HubpFlipProgram::preflight(request, route.reader, route.writer, surface, withinBudget) ||
            (nextTable && !nextTable->prepare(route.flatFormat, route.reader.context, *route.lifetime, request,
                next.dma->qualified_, mapping(next), next.dma->layout_, next.dma->pages_, oldTable, translationCurrent)) ||
            !nextEmpty() || !matchesTranslation(old, translationCurrent) || !matchesTranslation(next, translationCurrent) ||
            !homeCurrent() || !oldInstalled() || !nextEmpty() || !peersIdle() ||
            (next.pin && (!writerCurrent() || !withinBudget() || !next.pin->beginDisplayUse()))) {
            if (!routeLifetime_) {
                route.framebuffer->release();
                route.lifetime->release();
            }
            readback_.recycle();
            return ScanoutFlipResult::Refused;
        }

        routeLifetime_ = route.lifetime;
        framebuffer_ = route.framebuffer;
        pci_ = pci;
        firmwareHome_ = home;
        windows_ = windows;
        operation_ = operation;
        request_ = request;
        route_ = route;
        old_ = old;
        nextDma_ = next.dma;
        nextVm_ = nextTable ? nextTable->vm_ : DcnFlatContext{};
        surface_ = surface;
        if ((nextTable && (!DcnFlatProgram::install(nextVm_, route_.reader, route_.writer, inactive, peersIdle) ||
                           !homeCurrent() || !writerCurrent() || !withinBudget())) ||
            !HubpFlipProgram::issue(request_, route_.reader, route_.writer, surface_, withinBudget, contextsCurrent) ||
            !route_.reader.current(route_.reader.context, request_) || !live())
            return fail();
        return ScanoutFlipResult::Issued;
    }

    template<typename IsLive>
    ScanoutFlipResult poll(ScanoutPinToken operation, IsLive live, OSObject *&releaseRoute, IOService *&releaseFramebuffer) {
        if (!matches(operation)) return ScanoutFlipResult::Refused;
        if (uncertain_) return ScanoutFlipResult::Uncertain;
        auto withinBudget = [&] { return live() && readback_.stillInBudget(); };
        auto translationCurrent = [&] {
            return withinBudget() && route_.reader.current(route_.reader.context, request_) && withinBudget();
        };
        auto nextCurrent = [&] {
            return tableCurrent(nextDma_, nextVm_, translationCurrent) && contextCurrent(nextVm_, route_.reader, translationCurrent);
        };
        const auto detached = [&] { return DcnFlatProgram::empty(frontVm_.vmid, route_.reader, translationCurrent); };
        const auto oldCurrent = [&] {
            return tableCurrent(old_.dma, frontVm_, translationCurrent) &&
                (contextCleared_ ? detached() : contextCurrent(frontVm_, route_.reader, translationCurrent));
        };
        const auto peersIdle = [&] { return HubpFlipProgram::peersIdle(request_, route_.reader, withinBudget); };
        if (!peersIdle() || !nextCurrent() || !oldCurrent()) return fail();
        const auto progress = readback_.poll();
        if (progress == HubpFlipProgress::Uncertain || !live()) return fail();
        if (progress != HubpFlipProgress::OldAddressAbsent) return ScanoutFlipResult::Waiting;
        const auto displayCurrent = [&] {
            return nextCurrent() && checkFirmware(*framebuffer_, pci_, firmwareHome_, windows_, translationCurrent) &&
                HubpFlipProgram::frontCurrent(request_, route_.reader, surface_, withinBudget);
        };
        if (!displayCurrent() || !oldCurrent()) return fail();
        if (!contextCleared_) {
            const bool retired = route_.fetchesRetired(route_.reader.context, request_);
            if (!displayCurrent() || !oldCurrent()) return fail();
            if (!retired) return ScanoutFlipResult::Waiting;
            if (old_.pin) {
                const auto writeAllowed = [&] {
                    return translationCurrent() && route_.canClearFlatVm(route_.reader.context, request_, frontVm_) &&
                        HubpFlipProgram::frontCurrent(request_, route_.reader, surface_, withinBudget);
                };
                if (!DcnFlatProgram::clear(frontVm_, route_.reader, route_.writer, translationCurrent, writeAllowed)) return fail();
                contextCleared_ = true;
            }
        }
        if (old_.pin) {
            if (!displayCurrent() || !oldCurrent()) return fail();
            const auto translations = route_.translationsRetired(route_.reader.context, request_, frontVm_);
            if (!displayCurrent() || !oldCurrent()) return fail();
            if (translations == DcnRetirement::Pending) return ScanoutFlipResult::Waiting;
            if (translations != DcnRetirement::Complete || !old_.dma->table_.withdraw(old_.dma->qualified_) ||
                !displayCurrent() || !detached() || !old_.dma->releaseUnmapped() || !old_.pin->retireDisplayUse()) return fail();
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
        windows_ = {};
        contextCleared_ = false;
        readback_.recycle();
        if (!front_.serial) {
            releaseRoute = routeLifetime_;
            releaseFramebuffer = framebuffer_;
            routeLifetime_ = nullptr;
            framebuffer_ = nullptr;
            pci_ = nullptr;
            firmwareHome_ = {};
            routeOwner_ = nullptr;
            routeGeneration_ = 0;
        }
        return ScanoutFlipResult::Presented;
    }

private:
    template<typename Current>
    static bool checkFirmware(IOService &framebuffer, void *pci, const FirmwareScanoutSample &home,
                              FirmwareFlatWindows windows, const Current &current) {
        auto expected = home;
        return current() && framebuffer.callPlatformFunction(BUILD34_DCN_CHECK_FIRMWARE, false, pci, &expected,
            windows.empty() ? nullptr : &windows, nullptr) == kIOReturnSuccess && current();
    }

    static bool validBinding(ScanoutFlipBinding binding, HubpAddress address, const void *provider,
                             const void *pci, bool displayed) {
        if (!binding.token.serial)
            return !binding.token.provider && !binding.pin && !binding.dma && !binding.surface.mappedBytes;
        return address.vmid && binding.token.provider == provider && binding.pin && binding.dma &&
            binding.window == address.address &&
            validFlipGeometry(binding.surface) && binding.surface.mappedBytes == binding.pin->lease_.bytes() &&
            binding.surface.mappedBytes <= kAddressLimit - binding.window &&
            binding.dma->hasBacking() && binding.dma->pages_ && !binding.dma->uncertain() &&
            (!binding.dma->qualified_.direct.device || binding.dma->qualified_.direct.device == pci) &&
            binding.dma->layout_.firstLogicalPage == binding.window / kPageBytes &&
            binding.dma->layout_.entryCount == binding.surface.mappedBytes / kPageBytes && binding.pin->held() &&
            binding.pin->displayUse_ == displayed;
    }

    static DcnPixelMapping mapping(ScanoutFlipBinding binding) {
        return binding.dma ? binding.dma->mapping() : DcnPixelMapping{};
    }

    static FirmwareFlatWindow directWindow(ScanoutFlipBinding binding) {
        return mapping(binding).direct ? FirmwareFlatWindow{binding.window, binding.surface.mappedBytes} : FirmwareFlatWindow{};
    }

    template<typename Current>
    static bool tableCurrent(const ScanoutDmaLease *dma, const DcnFlatContext &context, const Current &current) {
        return !dma ? !context.vmid : current() && dma->table_.vm_ == context &&
            dma->table_.current(dma->qualified_, dma->mapping()) && current();
    }

    template<typename Current>
    static bool contextCurrent(const DcnFlatContext &context, const HubpFlipReader &reader, const Current &current) {
        return !context.vmid || matchDcnFlatContext(context, reader, current);
    }

    template<typename Current>
    static bool matchesTranslation(ScanoutFlipBinding binding, const Current &current) {
        const auto *dma = binding.dma;
        return !dma || (dma->table_.matchesPages(dma->qualified_, mapping(binding), dma->layout_, dma->pages_, current) &&
                        dma->matchesPixels(*binding.pin, current));
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
    IOService *framebuffer_{nullptr};
    void *pci_{nullptr};
    FirmwareScanoutSample firmwareHome_{};
    FirmwareFlatWindows windows_{};
    uint64_t routeGeneration_{0};
    HubpFlipRequest request_{};
    HubpFlipRoute route_{};
    ScanoutFlipBinding old_{};
    ScanoutDmaLease *nextDma_{nullptr};
    ScanoutSurface surface_{};
    bool contextCleared_{false};
    bool uncertain_{false};
};

}
