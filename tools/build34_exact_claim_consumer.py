# SPDX-License-Identifier: MIT
"""Stage a paired kernel-only build34 accelerator start admission, offline."""

from build34_exact_claim_lifecycle import CLAIM, RECHECKED, change, stage as previous_stage, stage_header
from build34_exact_submit import once


KEY = '-'.join(('phx', 'r3', 'paired', 'claim', 'v1'))
FUNCTION = 'phxBuild34CheckAccelClaimV1'
FIELDS = '''    // Issued at most once per service instance, under gpuLock.
    IOPCIDevice *exactClaimDevice{nullptr}; // identity only
    uint64_t exactClaimEpoch{0}, exactClaimGeneration[2]{};
    bool exactClaimArmed{false};
    bool exactClaimReadyLocked() const;
    bool exactClaimCurrentLocked(const void *device) const;
'''
OLD_FIELD = '    bool exactClaimRequested{false}; // exclusive claim lease held\n'
OVERRIDE = ('    IOReturn callPlatformFunction(const OSSymbol *name, bool wait, void *device,\n'
            '                                  void *p2, void *p3, void *p4) override;\n')

HELPERS = '''bool PhxBringup::exactClaimReadyLocked() const {
    return !exactCallbacks.closed() && !exactStopped && !isSleeping && !exactVMFault &&
        gq[0].ready && gq[1].ready && exactQueueLive[0] && exactQueueLive[1] &&
        exactQueueGeneration[0] && exactQueueGeneration[1];
}

bool PhxBringup::exactClaimCurrentLocked(const void *device) const {
    return device && pci == device && exactClaimDevice == device && exactClaimArmed && exactClaimReadyLocked() &&
        exactInvalidationEpoch == exactClaimEpoch && exactQueueGeneration[0] == exactClaimGeneration[0] &&
        exactQueueGeneration[1] == exactClaimGeneration[1];
}

IOReturn PhxBringup::callPlatformFunction(const OSSymbol *name, bool wait, void *device,
                                        void *p2, void *p3, void *p4) {
    if (!name || !name->isEqualTo("@FUNCTION@"))
        return IOService::callPlatformFunction(name, wait, device, p2, p3, p4);
    if (wait || !device || p2 || p3 || p4) return kIOReturnBadArgument;
    phx34_exact::CallbackGate<>::Lease callback(exactCallbacks);
    if (!callback || !gpuLock) return kIOReturnNotReady;
    if (!IOLockTryLock(gpuLock)) return kIOReturnBusy;
    const bool current = exactClaimCurrentLocked(device);
    IOLockUnlock(gpuLock);
    return current ? kIOReturnSuccess : kIOReturnNotReady;
}

'''.replace('@FUNCTION@', FUNCTION)

PAIRED = '''    phx34_exact::CallbackGate<>::Lease callback(exactCallbacks);
    if (!callback || !gpuLock) return kIOReturnNotReady;
    phx34_exact::CallbackGate<1>::Lease writer(exactClaimWriters);
    if (!writer) return exactCallbacks.closed() ? kIOReturnNotReady : kIOReturnBusy;

    IOLockLock(gpuLock);
    IOPCIDevice *device = exactClaimReadyLocked() ? pci : nullptr;
    const uint64_t epoch = exactInvalidationEpoch;
    const uint64_t generation[2] = {exactQueueGeneration[0], exactQueueGeneration[1]};
    const bool issued = exactClaimDevice != nullptr;
    if (device) device->retain();
    IOLockUnlock(gpuLock);
    if (!device) return kIOReturnNotReady;

    const auto sameQueuesLocked = [&] {
        return exactClaimReadyLocked() && pci == device && exactInvalidationEpoch == epoch &&
            exactQueueGeneration[0] == generation[0] && exactQueueGeneration[1] == generation[1];
    };
    const char *const key = "@KEY@";
    const auto current = [&] {
        if (device->getProperty(key) != kOSBooleanTrue) return false;
        IOLockLock(gpuLock);
        const bool live = exactClaimCurrentLocked(device);
        IOLockUnlock(gpuLock);
        return live;
    };
    // Registry work and matching may call into another service. Neither holds gpuLock.
    const IOReturn result = [&]() -> IOReturn {
        const auto *existing = device->getProperty(key);
        IOLockLock(gpuLock);
        const bool live = sameQueuesLocked();
        IOLockUnlock(gpuLock);
        if (!live) return kIOReturnNotReady;
        if (issued) {
            if (!current()) return kIOReturnNotReady;
            // A previous start may have refused a contended lock. Allow an explicit retry.
            device->registerService(kIOServiceAsynchronous);
            return current() ? kIOReturnSuccess : kIOReturnNotReady;
        }
        if (existing) return kIOReturnExclusiveAccess;
        if (!device->setProperty(key, kOSBooleanTrue)) return kIOReturnNoResources;

        const bool marked = device->getProperty(key) == kOSBooleanTrue;
        IOLockLock(gpuLock);
        const bool arm = marked && sameQueuesLocked();
        if (arm) {
            exactClaimDevice = device;
            exactClaimEpoch = epoch;
            exactClaimGeneration[0] = generation[0];
            exactClaimGeneration[1] = generation[1];
            exactClaimArmed = true;
        }
        IOLockUnlock(gpuLock);
        if (arm) {
            device->registerService(kIOServiceAsynchronous);
            if (current()) return kIOReturnSuccess;
            IOLockLock(gpuLock);
            exactClaimArmed = false; // Any deferred matching must refuse this issued claim.
            IOLockUnlock(gpuLock);
        }
        if (device->getProperty(key) == kOSBooleanTrue) device->removeProperty(key);
        return kIOReturnNotReady;
    }();
    device->release();
    return result;
'''.replace('@KEY@', KEY)

ACCEL = 'src/phxaccel/accel/nvrm-accel.cpp'
PLIST = 'src/phxaccel/Info.plist'
ACCEL_START = '    virtual bool start(IOService *provider) APPLE_KEXT_OVERRIDE {\n        { if (nvrm_driver_off()) return false; }\n'
FAMILY_START = '        bool r = IOGraphicsAccelerator2::start(provider);\n'

ACCEL_HELPER = '''#if defined(NMX_ACCEL) && defined(PHX_FB)
    bool startClaimedFamily(IOService *provider) {
        auto *pci = OSDynamicCast(IOPCIDevice, provider);
        if (!pci || pci->getProperty("@KEY@") != kOSBooleanTrue) return false;
        const auto *category = OSSymbol::withCStringNoCopy("PhxBringup");
        const auto *check = OSSymbol::withCStringNoCopy("@FUNCTION@");
        auto *native = category && check ? pci->copyClientWithCategory(category) : nullptr;
        const auto current = [&] {
            return native && native->getProvider() == pci && !native->isInactive() &&
                pci->getProperty("@KEY@") == kOSBooleanTrue &&
                native->callPlatformFunction(check, false, pci, nullptr, nullptr, nullptr) == kIOReturnSuccess;
        };
        bool started = false;
        if (native && native->metaCast(category) && current()) {
            started = IOGraphicsAccelerator2::start(provider);
            if (started && !current()) {
                IOGraphicsAccelerator2::stop(provider);
                started = false;
            }
        }
        if (native) native->release();
        if (check) check->release();
        if (category) category->release();
        return started;
    }
#endif
'''.replace('@KEY@', KEY).replace('@FUNCTION@', FUNCTION)


def stage(source):
    source = once(previous_stage(source), OLD_FIELD, FIELDS)
    source = once(source, '    IOReturn claimAccel();\n', '    IOReturn claimAccel();\n' + OVERRIDE)
    source = change(source, CLAIM, (RECHECKED, PAIRED))
    return once(source, CLAIM, HELPERS + CLAIM)


def stage_accel(source):
    source = once(source, ACCEL_START + '#ifdef NMX_ACCEL\n',
                  ACCEL_HELPER + ACCEL_START + '#if defined(NMX_ACCEL) && defined(PHX_FB)\n'
                  '        bool r = startClaimedFamily(provider);\n'
                  '#else\n#ifdef NMX_ACCEL\n')
    return once(source, FAMILY_START, FAMILY_START + '#endif\n')


def stage_plist(source):
    return once(once(source, 'after PhxBringup sets nmxgpu-claimed.', 'after paired build34 claim admission.'),
                '<key>nmxgpu-claimed</key>', '<key>' + KEY + '</key>')
