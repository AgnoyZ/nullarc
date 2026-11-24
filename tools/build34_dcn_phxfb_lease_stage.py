"""Gate paired build34 scanout against the exact framebuffer lifecycle."""

import build34_dcn_bar5_stage as bar5
import build34_dcn_firmware_home_stage as firmware
import build34_dcn_transaction_stage as transaction
from build34_exact_submit import once
from test_build34_exact_ownership import method


FB_FIELDS = '''    build34::dcn::DcnFramebufferRouteGate fDcnRoute;

    IOReturn acquireDcnRoute(const void *expectedPci, build34::dcn::DcnFramebufferRouteClaim &claim,
                             const build34::dcn::FirmwareScanoutSample &home) {
        using namespace build34::dcn;
        if (!fDcnFirmwareLock || !home.valid() || !claim.provider) return kIOReturnNotReady;
        if (!IOLockTryLock(fDcnFirmwareLock)) return kIOReturnBusy;
        const auto live = [&] {
            if (!fDcnFirmwareReady || !fDcnFirmwarePower || fDcnFirmwareClosed || fBeside || !fSurfMap || !fMmio ||
                !fPCI || fPCI != expectedPci || getProvider() != fPCI || isInactive() || fPCI->isInactive() ||
                claim.provider->getProvider() != fPCI || claim.provider->isInactive() || !claim.provider->metaCast("PhxBringup"))
                return false;
            const auto command = fPCI->configRead16(kIOPCIConfigCommand);
            return command != UINT16_MAX && (command & 2) && fPCI->configRead32(kIOPCIConfigVendorID) == 0x19001002;
        };
        const auto extent = home.surface.mappedBytes;
        const bool acquired = [&] {
            if (!fDcnRoute.canAcquireLocked(claim, extent) || !live()) return false;
            const auto *regs = reinterpret_cast<const volatile uint32_t *>(fMmio->getVirtualAddress());
            auto *resource = fPCI->getDeviceMemoryWithRegister(kIOPCIConfigBaseAddress5);
            if (!regs || !resource || fMmio->getMemoryDescriptor() != resource ||
                fMmio->getLength() != resource->getLength() || fMmio->getPhysicalAddress() != resource->getPhysicalAddress())
                return false;
            const auto read = [&](uint32_t reg, uint32_t &value) { value = regs[reg]; return true; };
            if (!checkUnclaimedDcnContexts(claim.windows, home.scanout, extent, fMmio->getLength(), read) ||
                !live() || !fDcnRoute.acquireLocked(claim, extent)) return false;
            claim.provider->retain();
            return true;
        }();
        IOLockUnlock(fDcnFirmwareLock);
        return acquired ? kIOReturnSuccess : kIOReturnNotReady;
    }

    IOReturn releaseDcnRoute(const void *expectedPci, const build34::dcn::DcnFramebufferRouteClaim &claim) {
        if (!fDcnFirmwareLock) return kIOReturnNotReady;
        IOLockLock(fDcnFirmwareLock);
        const bool released = fPCI == expectedPci && fDcnRoute.releaseLocked(claim);
        IOLockUnlock(fDcnFirmwareLock);
        if (released) claim.provider->release();
        return released ? kIOReturnSuccess : kIOReturnNotFound;
    }

'''

FB_QUERY = '''        if (fn && fn->isEqualTo(BUILD34_DCN_ACQUIRE_FB_ROUTE)) {
            if (wait || !p1 || !p2 || !p3 || p4) return kIOReturnBadArgument;
            return acquireDcnRoute(p1, *static_cast<build34::dcn::DcnFramebufferRouteClaim *>(p2),
                *static_cast<const build34::dcn::FirmwareScanoutSample *>(p3));
        }
        if (fn && fn->isEqualTo(BUILD34_DCN_RELEASE_FB_ROUTE)) {
            if (wait || !p1 || !p2 || p3 || p4) return kIOReturnBadArgument;
            return releaseDcnRoute(p1, *static_cast<const build34::dcn::DcnFramebufferRouteClaim *>(p2));
        }
'''

NATIVE_FIELDS = '''    build34::dcn::DcnFramebufferRouteClaim dcnFbRoute{};
    IOService *dcnFbRouteService{nullptr};
    bool acquireDcnFbRoute(const build34::dcn::HubpFlipRoute &, build34::dcn::FirmwareScanoutSample &);
    bool releaseDcnFbRoute();
'''

ACQUIRE = 'bool PhxBringup::acquireDcnFbRoute('
RELEASE = 'bool PhxBringup::releaseDcnFbRoute('
NATIVE_METHODS = '''bool PhxBringup::acquireDcnFbRoute(const build34::dcn::HubpFlipRoute &route,
    build34::dcn::FirmwareScanoutSample &home) {
    using namespace build34::dcn;
    DcnFramebufferRouteClaim claim{this, route.owner, route.generation, route.presentWindows, nullptr, 0};
    if (dcnFbRouteService) return dcnFbRouteService == route.framebuffer && dcnFbRoute.sameOwner(claim) &&
        dcnFbRoute.gate && dcnFbRoute.gate->access(dcnFbRoute, [] { return true; });
    if (!route.framebuffer || !pci || !exactRawWriters.drained() || !home.valid() || exactCallbacks.closed() ||
        __atomic_load_n(&dcnBar5Revoked, __ATOMIC_ACQUIRE) ||
        route.framebuffer->callPlatformFunction(BUILD34_DCN_ACQUIRE_FB_ROUTE, false,
            pci, &claim, &home, nullptr) != kIOReturnSuccess) return false;
    route.framebuffer->retain();
    dcnFbRouteService = route.framebuffer;
    dcnFbRoute = claim;
    return claim.gate && claim.serial;
}

bool PhxBringup::releaseDcnFbRoute() {
    using namespace build34::dcn;
    if (!dcnFbRouteService) return true;
    if (dcnFlip.pending() || dcnFlip.front().serial || !pci ||
        dcnFbRouteService->callPlatformFunction(BUILD34_DCN_RELEASE_FB_ROUTE, false,
            pci, &dcnFbRoute, nullptr, nullptr) != kIOReturnSuccess) return false;
    auto *framebuffer = dcnFbRouteService;
    dcnFbRoute = {};
    dcnFbRouteService = nullptr;
    framebuffer->release();
    return true;
}

'''


def stage_framebuffer(framebuffer):
    source = firmware.stage(framebuffer)
    include = '#include "build34_dcn_firmware_home.h"\n'
    source = once(source, include, include + '#include "build34_dcn_framebuffer_route.h"\n')
    source = once(source, firmware.FIELDS, firmware.FIELDS + FB_FIELDS)
    source = once(source, '        fDcnFirmwareLock = IOLockAlloc();\n',
                  '        fDcnFirmwareLock = IOLockAlloc();\n        fDcnRoute.setLock(fDcnFirmwareLock);\n')
    source = once(source, '        if (!on && fDcnFirmwareReady) fDcnFirmwareClosed = true;\n', '''        if (!on && fDcnFirmwareReady) {
            fDcnFirmwareClosed = true;
            fDcnRoute.closeLocked();
        }
''')
    source = once(source, '        fDcnFirmwareClosed = true;\n        IOLockUnlock(fDcnFirmwareLock);\n',
                  '        fDcnFirmwareClosed = true;\n        fDcnRoute.closeLocked();\n        IOLockUnlock(fDcnFirmwareLock);\n')
    return once(source, firmware.QUERY, FB_QUERY + firmware.QUERY)


def stage_native(driver, abi):
    source = transaction.stage_native(driver, abi)
    include = '#include "build34_dcn_transaction.h"\n'
    source = once(source, include, include + '#include "build34_dcn_framebuffer_route.h"\n')
    source = once(source, transaction.FIELDS, transaction.FIELDS + NATIVE_FIELDS)
    source = once(source, transaction.METHOD, NATIVE_METHODS + transaction.METHOD)

    def replace(signature, old, new):
        nonlocal source
        before = method(source, signature)
        source = once(source, before, once(before, old, new))

    replace(transaction.NATIVE, 'pci, &home, &windows, nullptr) == kIOReturnSuccess) {',
            'pci, &home, &windows, nullptr) == kIOReturnSuccess && acquireDcnFbRoute(route, home)) {')
    replace(transaction.NATIVE, '    request.result = DcnPresentResult::Copy;\n',
            '    if (!releaseDcnFbRoute()) return kIOReturnNotReady;\n    request.result = DcnPresentResult::Copy;\n')
    replace(bar5.BIND, '    dcnBar5Window = window;\n', '''    const DcnFramebufferRouteClaim claim{this, route.owner, route.generation, route.presentWindows, nullptr, 0};
    if (dcnFbRouteService != route.framebuffer || !dcnFbRoute.sameOwner(claim) || !dcnFbRoute.gate ||
        !dcnFbRoute.gate->access(dcnFbRoute, [] { return true; })) return false;
    dcnBar5Window = window;
''')
    replace(bar5.READ, '''    const auto sampled = self->dcnBar5.registers[reg];
    if (sampled == UINT32_MAX || !self->dcnBar5Live()) return false;
    value = sampled;
    return true;
''', '''    return self->dcnFbRoute.gate && self->dcnFbRoute.gate->access(self->dcnFbRoute, [&] {
        if (!self->dcnBar5Live()) return false;
        const auto sampled = self->dcnBar5.registers[reg];
        if (sampled == UINT32_MAX || !self->dcnBar5Live()) return false;
        value = sampled;
        return true;
    });
''')
    replace(bar5.WRITE, '''    self->dcnBar5.registers[reg] = value;
    __asm__ __volatile__("mfence" ::: "memory");
    uint32_t posted = 0;
    return readDcnBar5(context, reg, posted) && self->dcnBar5Current();
''', '''    return self->dcnFbRoute.gate && self->dcnFbRoute.gate->access(self->dcnFbRoute, [&] {
        if (!self->dcnBar5Live()) return false;
        self->dcnBar5.registers[reg] = value;
        __asm__ __volatile__("mfence" ::: "memory");
        return self->dcnBar5.registers[reg] != UINT32_MAX && self->dcnBar5Live();
    }) && self->dcnBar5Current();
''')
    return source
