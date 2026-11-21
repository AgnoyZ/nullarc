# SPDX-License-Identifier: MIT
"""Revalidate a staged build34 claim across unlocked registry operations."""

from build34_exact_claim import CHECKED, CLAIM, change, stage as previous_stage, stage_header
from build34_exact_submit import once


FIELDS = '''    phx34_exact::CallbackGate<1> exactClaimWriters;
    bool exactClaimRequested{false}; // exclusive claim lease held
'''
ANCHOR = '    bool exactQueueAdopted[2]{}; // gpuLock held; no inferred old-writer drain\n'

RECHECKED = '''    phx34_exact::CallbackGate<>::Lease callback(exactCallbacks);
    if (!callback || !gpuLock) return kIOReturnNotReady;
    phx34_exact::CallbackGate<1>::Lease writer(exactClaimWriters);
    if (!writer) return exactCallbacks.closed() ? kIOReturnNotReady : kIOReturnBusy;

    const auto readyLocked = [this] {
        return !exactCallbacks.closed() && !exactStopped && !isSleeping && !exactVMFault &&
            gq[0].ready && gq[1].ready && exactQueueLive[0] && exactQueueLive[1];
    };
    IOLockLock(gpuLock);
    IOPCIDevice *device = readyLocked() ? pci : nullptr;
    const uint64_t epoch = exactInvalidationEpoch;
    if (device) device->retain();
    IOLockUnlock(gpuLock);
    if (!device) return kIOReturnNotReady;

    const auto stillCurrent = [&] {
        IOLockLock(gpuLock);
        const bool live = readyLocked() && pci == device && exactInvalidationEpoch == epoch;
        IOLockUnlock(gpuLock);
        return live;
    };
    // Registry access and asynchronous matching can enter other services.
    const IOReturn result = [&]() -> IOReturn {
        const char *const key = "nmxgpu-claimed";
        const auto *existing = device->getProperty(key);
        if (!stillCurrent()) return kIOReturnNotReady;
        if (exactClaimRequested) return existing == kOSBooleanTrue ? kIOReturnSuccess : kIOReturnNotReady;
        if (existing) return kIOReturnExclusiveAccess;
        if (!device->setProperty(key, kOSBooleanTrue)) return kIOReturnNoResources;

        const auto stillMarked = [&] { return device->getProperty(key) == kOSBooleanTrue && stillCurrent(); };
        if (stillMarked()) {
            device->registerService();
            if (stillMarked()) {
                exactClaimRequested = true;
                IOLog("PhxBringup: GPU claimed for PhxAccel, matching re-run\\n");
                return kIOReturnSuccess;
            }
        }
        // The slot began empty. Leave any observed different value alone.
        // This cannot cancel matching that may already have been scheduled.
        if (device->getProperty(key) == kOSBooleanTrue) device->removeProperty(key);
        return kIOReturnNotReady;
    }();
    device->release();
    return result;
'''


def stage(source):
    source = once(previous_stage(source), ANCHOR, FIELDS + ANCHOR)
    return change(source, CLAIM, (CHECKED, RECHECKED))
