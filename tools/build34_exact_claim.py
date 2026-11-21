# SPDX-License-Identifier: MIT
"""Require two live queues for native accelerator claim in the offline R3 stage."""

from build34_exact_smu_uncertainty import change, stage as previous_stage, stage_header


CLAIM = 'IOReturn PhxBringup::claimAccel('
OLD = '''    if (!pci || !gpuReady())
        return kIOReturnNotReady;
    pci->setProperty("nmxgpu-claimed", kOSBooleanTrue);
    pci->registerService();
    IOLog("PhxBringup: GPU claimed for PhxAccel, matching re-run\\n");
    return kIOReturnSuccess;
'''
CHECKED = '''    phx34_exact::CallbackGate<>::Lease callback(exactCallbacks);
    if (!callback || !gpuLock) return kIOReturnNotReady;
    IOLockLock(gpuLock);
    const bool ready = !exactCallbacks.closed() && !exactStopped && !isSleeping && !exactVMFault &&
        gq[0].ready && gq[1].ready && exactQueueLive[0] && exactQueueLive[1];
    IOPCIDevice *device = ready ? pci : nullptr;
    if (device) device->retain();
    IOLockUnlock(gpuLock);
    if (!device) return kIOReturnNotReady;

    // Matching may enter other services. Hold the PCI reference, not gpuLock.
    IOReturn result = kIOReturnNotReady;
    if (!exactCallbacks.closed()) {
        result = kIOReturnNoResources;
        if (device->setProperty("nmxgpu-claimed", kOSBooleanTrue)) {
            device->registerService();
            IOLog("PhxBringup: GPU claimed for PhxAccel, matching re-run\\n");
            result = kIOReturnSuccess;
        }
    }
    device->release();
    return result;
'''


def stage(source):
    return change(previous_stage(source), CLAIM, (OLD, CHECKED))
