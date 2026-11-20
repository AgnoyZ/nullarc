#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Extend the CPU-only R3 submit staging with conservative lifecycle invalidation.

This is not a deployable kernel: no complete native observation/owner/drain
protocol exists. Invalidation preserves metadata and cannot authorize release.
The accepted production source and earlier source experiment remain unchanged.
"""
from build34_exact_submit import once, stage as stage_submit


def stage(source):
    source = stage_submit(source)
    source = once(source,
                  '    uint64_t exactQueueGeneration[2]{}; // outside resettable queue history\n',
                  '    uint64_t exactQueueGeneration[2]{}; // outside resettable queue history\n'
                  '    uint64_t exactInvalidationEpoch{0};\n'
                  '    bool exactQueueLive[2]{}, exactStopped{false};\n'
                  '    void invalidateExactQueues(); // caller must hold gpuLock when allocated\n')
    source = once(source, '    if (exactQueueGeneration[qi] >= UINT64_MAX - 1) {\n',
                  '    if (exactStopped || isSleeping) {\n'
                  '        IOLockUnlock(gpuLock);\n'
                  '        return kIOReturnNotReady;\n'
                  '    }\n'
                  '    if (exactQueueGeneration[qi] >= UINT64_MAX - 1) {\n')
    source = once(source, '    q.ready = true;\n    IOLockUnlock(gpuLock);\n',
                  '    q.ready = true;\n    exactQueueLive[qi] = true;\n    IOLockUnlock(gpuLock);\n')
    source = once(source, '    GpuQueue *qp = nullptr;\n',
                  '    GpuQueue *qp = nullptr;\n    uint64_t admissionEpoch = 0;\n')
    source = once(source,
                  '        GpuQueue &q = *qp;\n        const uint32_t need = n * 4 + 8 + (q.gfx ? 0u : 8u);',
                  '        if (exact && !retried) admissionEpoch = exactInvalidationEpoch;\n'
                  '        if (exact && (exactStopped || isSleeping || !exactQueueLive[qp == &gq[1] ? 1 : 0] ||\n'
                  '                      admissionEpoch != exactInvalidationEpoch)) {\n'
                  '            IOLockUnlock(gpuLock);\n'
                  '            return kIOReturnNotReady;\n'
                  '        }\n'
                  '        GpuQueue &q = *qp;\n        const uint32_t need = n * 4 + 8 + (q.gfx ? 0u : 8u);')
    source = once(source, 'void PhxBringup::stop(IOService *provider) {\n',
                  'void PhxBringup::stop(IOService *provider) {\n'
                  '    // Terminal metadata invalidation, not GPU/resource drain or callback fencing.\n'
                  '    if (gpuLock) IOLockLock(gpuLock);\n'
                  '    exactStopped = true;\n'
                  '    invalidateExactQueues();\n'
                  '    if (gpuLock) IOLockUnlock(gpuLock);\n')
    old_power = '''IOReturn PhxBringup::setPowerState(unsigned long ordinal, IOService *whichDevice) {
    if (ordinal == 0) {
        IOLog("PhxBringup: powerStateWillChange to sleep (state 0)\\n");
        isSleeping = true;
    } else {
        IOLog("PhxBringup: powerStateDidChange from sleep (state 1)\\n");
        isSleeping = false;
    }
    return IOPMAckImplied;
}
'''
    new_power = '''IOReturn PhxBringup::setPowerState(unsigned long ordinal, IOService *whichDevice) {
    if (gpuLock) IOLockLock(gpuLock);
    if (ordinal == 0) {
        if (!isSleeping) invalidateExactQueues();
        IOLog("PhxBringup: powerStateWillChange to sleep (state 0)\\n");
        isSleeping = true;
    } else {
        IOLog("PhxBringup: powerStateDidChange from sleep (state 1)\\n");
        isSleeping = false;
        // Wake does not prove queue continuity; fresh adoption is required.
    }
    if (gpuLock) IOLockUnlock(gpuLock);
    return IOPMAckImplied;
}

void PhxBringup::invalidateExactQueues() {
    if (exactInvalidationEpoch < UINT64_MAX - 1) ++exactInvalidationEpoch;
    if (exactInvalidationEpoch == UINT64_MAX - 1) exactStopped = true;
    for (uint32_t i = 0; i < 2; ++i) {
        exactQueueLive[i] = false;
        // Saturation stays permanently unavailable; adoption also refuses it.
        if (exactQueueGeneration[i] < UINT64_MAX - 1) ++exactQueueGeneration[i];
    }
}
'''
    source = once(source, old_power, new_power)
    source = once(source, 'void PhxBringup::killWaves(uint32_t vmid, bool all) {\n',
                  'void PhxBringup::killWaves(uint32_t vmid, bool all) {\n'
                  '    if (!gpuLock) return;\n'
                  '    IOLockLock(gpuLock);\n'
                  '    // Conservatively invalidate both queues before ANY recovery register write.\n'
                  '    invalidateExactQueues();\n')
    return once(source, '    OSIncrementAtomic(&gHangKills);\n}\n',
                '    OSIncrementAtomic(&gHangKills);\n    IOLockUnlock(gpuLock);\n}\n')
