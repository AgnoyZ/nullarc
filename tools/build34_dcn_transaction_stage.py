"""Pair the checked build34 flip with the R2a transaction caller."""

import build34_dcn_bar5_stage as bar5
import build34_dcn_present_handoff_stage as handoff
from build34_exact_submit import once
from test_build34_exact_ownership import method


STUBS = 'src/phxaccel/accel/nvaccel_stubs.h'
NATIVE = 'IOReturn PhxBringup::submitDcnPresent('
PERFORM = 'IOReturn NVDisplayPipe::performTransaction('
COMPLETE = 'bool NVDisplayPipe::isTransactionComplete('
FIELDS = '''    build34::dcn::DcnSubmitGate dcnPresentGate;
    OSObject *dcnPresentPipe{nullptr};
    IOService *dcnPresentFramebuffer{nullptr};
    bool dcnPresentUncertain{false};
    IOReturn submitDcnPresent(build34::dcn::DcnPresentTransaction &);
'''
METHOD = '''IOReturn PhxBringup::submitDcnPresent(build34::dcn::DcnPresentTransaction &request) {
    using namespace build34::dcn;
    request.result = DcnPresentResult::Blocked;
    DcnSubmitGate::Lease gate;
    phx34_exact::CallbackGate<>::Lease callback(exactCallbacks);
    if (!gate.reserve(dcnPresentGate) || !callback || !request.pipe || !request.framebuffer || !request.transaction ||
        !pci || request.framebuffer->getProvider() != pci || !request.framebuffer->metaCast("PhxAMDFB") ||
        request.framebuffer->isInactive() || dcnPresentUncertain || dcnFlip.pending() ||
        (dcnPresentPipe && (dcnPresentPipe != request.pipe || dcnPresentFramebuffer != request.framebuffer)))
        return kIOReturnNotReady;

    const auto front = dcnFlip.front();
    const auto old = dcnFlip.frontAddress();
    if (bool(front.serial) != bool(dcnPresentPipe)) return kIOReturnNotReady;

    const auto submit = [&](ScanoutFlipIntent &intent) {
        const uint64_t start = mach_absolute_time();
        uint64_t previous = start;
        const auto inBudget = [&] {
            const uint64_t now = mach_absolute_time();
            if (now < previous || exactCallbacks.closed()) return false;
            previous = now;
            uint64_t elapsed = 0;
            absolutetime_to_nanoseconds(now - start, &elapsed);
            return elapsed < 100000000;
        };
        if (beginDcnFlip(intent) != kIOReturnSuccess) return ScanoutFlipResult::Refused;
        if (!dcnPresentPipe) {
            request.pipe->retain();
            request.framebuffer->retain();
            dcnPresentPipe = request.pipe;
            dcnPresentFramebuffer = request.framebuffer;
        }
        const auto operation = intent.operation;
        if (operation.provider != this || operation == intent.nextPin ||
            !waitDcnPresent(operation, intent.result, [&](ScanoutFlipPoll &poll) { return pollDcnFlip(poll); },
                            inBudget, [] { IOSleep(2); }) || !(dcnFlip.front() == intent.nextPin)) {
            dcnPresentUncertain = true;
            return ScanoutFlipResult::Uncertain;
        }
        return ScanoutFlipResult::Presented;
    };

    const auto *present = request.backing;
    if (present && present->transaction != request.transaction) return kIOReturnBadArgument;
    if (present && dcnQualifiedFlipRoute &&
        validFlipGeometry(present->scanout) && present->scanout.mappedBytes == present->slice.bytes &&
        livePresentPreparation(present->slice) == present->preparation && present->preparation) {
        const auto *qualified = dcnQualifiedFlipRoute(pci);
        const auto route = qualified ? *qualified : HubpFlipRoute{};
        const bool direct = route.presentWindows.domain == DcnPresentDomain::Direct;
        if (route.owner && route.generation && route.lifetime && route.framebuffer == request.framebuffer &&
            (direct ? dcnQualifyDirect != nullptr : dcnQualifyMapper != nullptr) &&
            dcnFlip.matchesPresentWindows(route.presentWindows) && route.presentWindows.valid(present->slice.bytes)) {
            Phx34ScopedReference routeLifetime(route.lifetime);
            auto home = dcnFlip.firmwareSample();
            if (!front.serial && request.framebuffer->callPlatformFunction(BUILD34_DCN_SAMPLE_FIRMWARE, false,
                pci, &home, nullptr, nullptr) != kIOReturnSuccess) home = {};
            const auto previous = front.serial ? old : home.scanout;
            const auto next = route.presentWindows.select(previous, present->slice.bytes);
            auto windows = route.presentWindows.exclusions();
            ScanoutPinToken pin{};
            if (next.valid() && home.valid() && sameFlipGeometry(home.surface, present->scanout) &&
                request.framebuffer->callPlatformFunction(BUILD34_DCN_CHECK_FIRMWARE, false,
                    pci, &home, &windows, nullptr) == kIOReturnSuccess) {
                const size_t entries = present->slice.bytes / kPageBytes;
                auto *runs = static_cast<DmaRun *>(IOMallocZero(entries * sizeof(DmaRun)));
                auto *pages = static_cast<uint64_t *>(IOMallocZero(entries * sizeof(uint64_t)));
                if (runs && pages) {
                    ScanoutDmaRequest map{present, next.address, runs, entries, pages, entries, {}, {}};
                    if (mapDcnPin(map, direct) == kIOReturnSuccess) pin = map.token;
                }
                if (pages) IOFree(pages, entries * sizeof(uint64_t));
                if (runs) IOFree(runs, entries * sizeof(DmaRun));
            }
            if (pin.serial) {
                ScanoutFlipIntent intent{previous, next, pin, {}, ScanoutFlipResult::Refused, request.framebuffer, &route};
                const auto result = submit(intent);
                if (result == ScanoutFlipResult::Presented) {
                    request.result = DcnPresentResult::Direct;
                    return kIOReturnSuccess;
                }
                if (result != ScanoutFlipResult::Refused) return kIOReturnNotReady;
                (void)cancelDcnPin(pin);
            }
        }
    }

    if (front.serial) {
        ScanoutFlipIntent home{old, dcnFlip.firmwareAddress(), {}, {}, ScanoutFlipResult::Refused, request.framebuffer};
        if (submit(home) != ScanoutFlipResult::Presented) return kIOReturnNotReady;
        auto *pipe = dcnPresentPipe;
        auto *framebuffer = dcnPresentFramebuffer;
        dcnPresentPipe = nullptr;
        dcnPresentFramebuffer = nullptr;
        framebuffer->release();
        pipe->release();
    }
    request.result = DcnPresentResult::Copy;
    return kIOReturnSuccess;
}

'''


def stage_native(driver, abi):
    source = bar5.stage_native(driver, abi)
    include = '#include "build34_dcn_bar5.h"\n'
    source = once(source, include, include + '#include "build34_dcn_transaction.h"\n')
    source = once(source, bar5.FIELDS, bar5.FIELDS + FIELDS)
    source = once(source, bar5.METHODS, METHOD + bar5.METHODS)
    begin = method(source, bar5.flip.BEGIN)
    source = once(source, begin, once(begin, '    if (!route || !route->framebuffer ||',
        '    if (!route || !route->framebuffer || (intent.framebuffer && route->framebuffer != intent.framebuffer) ||'))
    dispatch = method(source, handoff.DISPATCH)
    start = dispatch.index('    if (name && name->isEqualTo(BUILD34_DCN_FLIP_BEGIN)) {\n')
    end = dispatch.index('    if (!name || !name->isEqualTo("phxBuild34CheckAccelClaimV1"))\n')
    return once(source, dispatch, once(dispatch, dispatch[start:end], '''    if (name && name->isEqualTo(BUILD34_DCN_PRESENT_TRANSACTION)) {
        if (wait || !device || p2 || p3 || p4) return kIOReturnBadArgument;
        return submitDcnPresent(*static_cast<build34::dcn::DcnPresentTransaction *>(device));
    }
'''))


ACCEL_STATE = '''static bool nvAccelDcnLookupSeen{false};
static bool (*nvAccelDcnSleepable)(NVDisplayPipe &, IOService &){nullptr};
static build34::dcn::DcnSubmitGate nvAccelDcnPresentGate;
static IOService *nvAccelDcnProvider;
static SInt64 gCntIopDcnPresented;

static build34::dcn::DcnPresentResult nvAccelSubmitDcnPresent(NVAccel &accel,
    build34::dcn::DcnPresentTransaction &request) {
    using namespace build34::dcn;
    auto *provider = nvAccelDcnProvider ? nvAccelDcnProvider : accel.fNative;
    if (!provider || !provider->metaCast("PhxBringup") || provider->getProvider() != request.framebuffer->getProvider() ||
        provider->getProvider() != accel.fPCI || provider->isInactive())
        return nvAccelDcnProvider ? DcnPresentResult::Blocked : DcnPresentResult::Copy;

    provider->retain();
    const auto status = provider->callPlatformFunction(BUILD34_DCN_PRESENT_TRANSACTION, false, &request, nullptr, nullptr, nullptr);
    auto result = status == kIOReturnSuccess ? request.result : DcnPresentResult::Blocked;
    if (result == DcnPresentResult::Copy && nvAccelDcnProvider) {
        nvAccelDcnProvider->release();
        nvAccelDcnProvider = nullptr;
    } else if (result != DcnPresentResult::Copy && !nvAccelDcnProvider) {
        provider->retain();
        nvAccelDcnProvider = provider;
    }
    provider->release();
    return result;
}
'''


def stage_stubs(stubs):
    include = '#include "IOAccelVideoContext2.h"\n'
    stubs = once(stubs, include, include + '''#if defined(NMX_ACCEL) && defined(PHX_FB)
#include "build34_dcn_transaction.h"
#endif
''')
    anchor = '    unsigned fIopNext;\n'
    return once(stubs, anchor, anchor + '''#if defined(NMX_ACCEL) && defined(PHX_FB)
    build34::dcn::DcnPresentCompletion fDcnPresent;
#endif
''')


def stage_accelerator(accelerator):
    source = handoff.stage_accelerator(accelerator)
    observer = 'static void (*nvAccelObserveDcnCopyBacking)(const build34::dcn::PresentCopyBacking &){nullptr};\n'
    source = once(source, '#if defined(NMX_ACCEL) && defined(PHX_FB)\n' + handoff.ACCEL_CALL +
        observer.replace('{nullptr}', '{nvAccelCheckDcnCopyBacking}') + '#else\n' + observer + '#endif\n',
        '#if defined(NMX_ACCEL) && defined(PHX_FB)\n' + ACCEL_STATE + '#endif\n')
    counter = 'NVACCEL_CNT(nvaccel_iop_dcn_backing_matches, gCntIopDcnBackingMatches, "exact writer page matches; no change to scanout");'
    source = once(source, counter, 'NVACCEL_CNT(nvaccel_iop_dcn_presented, gCntIopDcnPresented, "matched DCN presents that skipped the final CPU copy");')
    before = method(source, COMPLETE)
    after = once(before, 'IOAccelDisplayPipeTransaction2 *)\n{', 'IOAccelDisplayPipeTransaction2 *txn __attribute__((unused)))\n{')
    after = once(after, '    if (gNvIop == 0 || nvAccelIopAsyncBusy(this)) return false;\n', '''    if (gNvIop == 0 || nvAccelIopAsyncBusy(this)) return false;
#if defined(NMX_ACCEL) && defined(PHX_FB)
    bool complete = false;
    if (fDcnPresent.check(txn, complete)) return complete;
#endif
''')
    source = once(source, before, after)
    before = method(source, PERFORM)
    after = once(before, '    IOSurface *s  = txn->getPlaneIOSurface(0, 0);\n', '''#if defined(NMX_ACCEL) && defined(PHX_FB)
    using namespace build34::dcn;
    DcnSubmitGate::Lease dcnPresentGate;
    if (nvAccelDcnSleepable && !dcnPresentGate.reserve(nvAccelDcnPresentGate)) return kIOReturnBusy;
    const bool dcnRoute = nvAccelDcnSleepable && fb->metaCast("PhxAMDFB");
    const bool dcnAttempt = dcnRoute && (nvAccelDcnProvider || __atomic_load_n(&nvAccelDcnLookupSeen, __ATOMIC_ACQUIRE)) &&
        nvAccelDcnSleepable(*this, *fb);
    if (nvAccelDcnSleepable && nvAccelDcnProvider && !dcnAttempt) {
        fDcnPresent.block();
        return kIOReturnNotReady;
    }
    fDcnPresent.legacy();
#endif
    IOSurface *s  = txn->getPlaneIOSurface(0, 0);
''')
    readiness = '''        nvSurfWaitReady(s->getSurfaceID());   // a copied frame is read here, so its GPU work must be done first
        if (!nvAccelSurfCopyReady(s, head)) return kIOReturnSuccess;
'''
    after = once(after, readiness, '''#if defined(NMX_ACCEL) && defined(PHX_FB)
        if (!dcnAttempt)
#endif
        {
''' + ''.join('    ' + line for line in readiness.splitlines(True)) + '''        }
''')
    start = after.index('    if (nvAccelObserveDcnCopyBacking && ')
    end = after.index('    nvAccelIopHome(fb, head);\n', start)
    after = once(after, after[start:end], '''#if defined(NMX_ACCEL) && defined(PHX_FB)
    if (dcnAttempt) {
        const auto sameSource = [&] {
            return copyDescriptor && txn->getPlaneIOSurface(0, 0) == s && s->getMemoryDescriptor() == copyDescriptor &&
                s->getWidth() == w && s->getHeight() == h && s->getBytesPerRow() == pitch &&
                s->getPixelFormat() == (l10r ? 0x6C313072u : 0x42475241u);
        };
        PresentCopyBacking observed{};
        if (!fromRes && !l10r && sameSource())
            observed = observePreparedCopyBacking(txn, s, copyDescriptor, s->getPixelFormat(), w, h, pitch, q.width, q.height);
        const bool mayRehome = nvAccelDcnProvider != nullptr;
        DcnPresentTransaction request{this, fb, txn, observed.preparation ? &observed : nullptr, DcnPresentResult::Blocked};
        fDcnPresent.block();
        const auto result = nvAccelSubmitDcnPresent(*a, request);
        if (result == DcnPresentResult::Direct) {
            fIopVblSeq = 0;
            fDcnPresent.presented(txn);
            OSAddAtomic64(1, &gCntIopDcnPresented);
            OSAddAtomic64(1, &gCntIopSrcSurf);
            OSAddAtomic64(1, &gCntIopOk);
            OSAddAtomic64(1, &gCntIopOkHead[head]);
            return kIOReturnSuccess;
        }
        if (result != DcnPresentResult::Copy) return kIOReturnNotReady;
        if (s) {
            if (!sameSource()) return kIOReturnNotReady;
            nvSurfWaitReady(s->getSurfaceID());
            if (!nvAccelSurfCopyReady(s, head)) { fDcnPresent.legacy(); return kIOReturnSuccess; }
            if (!sameSource()) return kIOReturnNotReady;
        }
        if (mayRehome) {
            NVRMVramRequest home{};
            home.version = NVRM_VRAM_ABI_VERSION;
            unsigned currentHead = 0;
            if (a->pipeFramebuffer(this, &currentHead) != fb || currentHead != head ||
                a->askFramebufferForScanout(&home, fb) != kIOReturnSuccess || home.kva != q.kva ||
                home.width != q.width || home.height != q.height || home.pitch != q.pitch)
                return kIOReturnNotReady;
        }
        fDcnPresent.legacy();
    }
#endif
''')
    after = once(after, '    IOMemoryDescriptor *copyDescriptor = nullptr;\n', '''#if defined(NMX_ACCEL) && defined(PHX_FB)
    IOMemoryDescriptor *copyDescriptor = nullptr;
#endif
''')
    after = once(after, '        copyDescriptor = md;\n', '''#if defined(NMX_ACCEL) && defined(PHX_FB)
        copyDescriptor = md;
#endif
''')
    return once(source, before, after)
