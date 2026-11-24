"""Add a read-only firmware scanout query to the exact build34 PhxFB source."""

import hashlib

from build34_exact_submit import once


FRAMEBUFFER = 'src/phxaccel/accel/phxfb.cpp'
FRAMEBUFFER_SHA256 = '282d520c0284cd498d0bcf5226cf957793e7bc3f2e4ad95baceb6cb43398394e'
FIELDS = '''    IOLock *fDcnFirmwareLock = nullptr;
    bool fDcnFirmwareReady = false, fDcnFirmwarePower = false, fDcnFirmwareClosed = false;

    void noteDcnFirmwarePower(bool on) {
        if (!fDcnFirmwareLock) return;
        IOLockLock(fDcnFirmwareLock);
        fDcnFirmwarePower = on;
        if (!on && fDcnFirmwareReady) fDcnFirmwareClosed = true;
        IOLockUnlock(fDcnFirmwareLock);
    }

    void closeDcnFirmwareSample() {
        if (!fDcnFirmwareLock) return;
        IOLockLock(fDcnFirmwareLock);
        fDcnFirmwareClosed = true;
        IOLockUnlock(fDcnFirmwareLock);
    }

    IOReturn sampleDcnFirmware(const void *expectedPci, build34::dcn::FirmwareScanoutSample &out,
                              const build34::dcn::FirmwareScanoutSample *expected = nullptr) {
        out = {};
        if (!fDcnFirmwareLock) return kIOReturnNotReady;
        if (!IOLockTryLock(fDcnFirmwareLock)) return kIOReturnBusy;
        const auto sample = [&] {
            if (!fDcnFirmwareReady || !fDcnFirmwarePower || fDcnFirmwareClosed || !fPCI || fPCI != expectedPci ||
                fBeside || !fMmio || !fSurfMap) return false;
            const auto accessible = [&] {
                if (isInactive() || fPCI->isInactive() || getProvider() != fPCI) return false;
                const auto command = fPCI->configRead16(kIOPCIConfigCommand);
                return command != UINT16_MAX && (command & 2) && fPCI->configRead32(kIOPCIConfigVendorID) == 0x19001002;
            };
            if (!accessible()) return false;
            auto *bar = fPCI->getDeviceMemoryWithRegister(kIOPCIConfigBaseAddress0);
            const auto *mmio = reinterpret_cast<const volatile uint32_t *>(fMmio->getVirtualAddress());
            if (!bar || !mmio) return false;
            const auto barBase = bar->getPhysicalAddress();
            const auto barBytes = bar->getLength();
            if (!build34::dcn::sampleFirmwareScanout(fBase, barBase, barBytes,
                fSurfMap->getLength(), fWidth, fHeight, fRowBytes, fMmio->getLength(),
                [&](uint32_t reg, uint32_t &value) { value = mmio[reg]; return true; }, out, expected) || !accessible()) return false;
            auto *currentBar = fPCI->getDeviceMemoryWithRegister(kIOPCIConfigBaseAddress0);
            return currentBar == bar && currentBar->getPhysicalAddress() == barBase && currentBar->getLength() == barBytes;
        }();
        IOLockUnlock(fDcnFirmwareLock);
        if (!sample) out = {};
        return sample ? kIOReturnSuccess : kIOReturnNotReady;
    }

'''
LIFETIME = '''    bool init(OSDictionary *dictionary = nullptr) override {
        if (!IOFramebuffer::init(dictionary)) return false;
        fDcnFirmwareLock = IOLockAlloc();
        return true;
    }

    void free() override {
        if (fDcnFirmwareLock) IOLockFree(fDcnFirmwareLock);
        IOFramebuffer::free();
    }

'''
QUERY = '''        if (fn && fn->isEqualTo(BUILD34_DCN_SAMPLE_FIRMWARE)) {
            if (wait || !p1 || !p2 || p3 || p4) return kIOReturnBadArgument;
            return sampleDcnFirmware(p1, *static_cast<build34::dcn::FirmwareScanoutSample *>(p2));
        }
        if (fn && fn->isEqualTo(BUILD34_DCN_CHECK_FIRMWARE)) {
            if (wait || !p1 || !p2 || p3 || p4) return kIOReturnBadArgument;
            build34::dcn::FirmwareScanoutSample checked{};
            return sampleDcnFirmware(p1, checked, static_cast<const build34::dcn::FirmwareScanoutSample *>(p2));
        }
'''


def stage(framebuffer):
    if hashlib.sha256(framebuffer).hexdigest() != FRAMEBUFFER_SHA256:
        raise ValueError('Build34 DCN firmware sample source drift')
    source = framebuffer.decode()
    include = '#include "phx_panel_timing.h"\n'
    source = once(source, include, include + '#include "build34_dcn_firmware_home.h"\n')
    declaration = '    OSDeclareDefaultStructors(PhxAMDFB)\n'
    source = once(source, declaration, declaration + FIELDS)
    public = 'public:\n    // the backlight as 0..kBlMax'
    source = once(source, public, 'public:\n' + LIFETIME + public[len('public:\n'):])
    dispatch = '        if (fn && fn->isEqualTo(NVRM_VRAM_FN_SCANOUT)) {\n'
    source = once(source, dispatch, QUERY + dispatch)
    ordinal = '        handleEvent(ordinal ? kIOFBNotifyDidPowerOn : kIOFBNotifyWillPowerOff);\n'
    source = once(source, ordinal, '        if (!ordinal) noteDcnFirmwarePower(false);\n' + ordinal +
                  '        if (ordinal) noteDcnFirmwarePower(true);\n')
    power = '        if (attribute == kIOPowerAttribute) {\n'
    source = once(source, power, power + '            if (!value) closeDcnFirmwareSample();\n')
    connection = '        case kConnectionPower:\n'
    source = once(source, connection, connection + '            if (!value) closeDcnFirmwareSample();\n')
    stop = 'void PhxAMDFB::stop(IOService *provider)\n{\n'
    source = once(source, stop, stop + '    closeDcnFirmwareSample();\n')
    tail = '    return true;\n}\n\n' + stop
    return once(source, tail, '''    if (fDcnFirmwareLock) {
        IOLockLock(fDcnFirmwareLock);
        fDcnFirmwareReady = true;
        IOLockUnlock(fDcnFirmwareLock);
    }
''' + tail)
