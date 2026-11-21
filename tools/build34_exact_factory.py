#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Stage leased native client construction and atomic configured-queue discovery.

No native reader/mode, platform publication barrier or healthy service teardown
is admitted. The prior paired bootstrap remains required and unchanged.
"""
from build34_exact_raw_handoff import stage as previous_stage, stage_header, stage_bootstrap
from build34_exact_submit import once
from test_build34_exact_ownership import method

FACTORY = '''IOReturn PhxBringup::newUserClient(task_t owningTask, void *securityID, UInt32 type, IOUserClient **handler) {
    if (!handler) return kIOReturnBadArgument;
    *handler = nullptr;
    phx34_exact::CallbackGate<>::Lease callback(exactCallbacks);
    if (!callback || !hangTimerReady()) return kIOReturnNotReady;
    if (type != PHXN_UC_TYPE) return kIOReturnBadArgument;
    // No unsynchronized plain read of a value updated with OSCompareAndSwap.
    // The lease includes registration and every allocation/attach/start path.
    if (OSCompareAndSwap(0, 1, &gSysctlUp)) {
        sysctl_register_oid(&sysctl__debug_phxbos_flush);
        sysctl_register_oid(&sysctl__debug_phxbos_flush_bytes);
        sysctl_register_oid(&sysctl__debug_phx_hang_ms);
        sysctl_register_oid(&sysctl__debug_phx_hang_kills);
    }
    IOAccelPhxNativeClient *client = OSTypeAlloc(IOAccelPhxNativeClient);
    if (!client) return kIOReturnNoMemory;
    if (!client->initWithTask(owningTask, securityID, type) || !client->attach(this)) {
        client->release();
        return kIOReturnNoMemory;
    }
    if (exactCallbacks.closed()) {
        client->detach(this);
        client->release();
        return kIOReturnNotReady;
    }
    if (!client->start(this)) {
        client->detach(this);
        client->release();
        return exactCallbacks.closed() ? kIOReturnNotReady : kIOReturnExclusiveAccess;
    }
    if (exactCallbacks.closed()) {
        // No handler escaped. Close admission before dropping the factory's
        // initial reference; the existing registration/provider pins remain
        // authoritative if service closure makes cleanup uncertain.
        (void)client->clientClose();
        client->detach(this);
        client->release();
        return kIOReturnNotReady;
    }
    *handler = client;
    return kIOReturnSuccess;
}
'''


def stage(source):
    source = previous_stage(source)
    source = once(source, '    bool gpuReady() const { return gq[0].ready || gq[1].ready; }',
                  '    // Configured-queue discovery only, NOT current completion/health/drain.\n'
                  '    bool gpuReady() const { return __atomic_load_n(&exactConfiguredQueues, __ATOMIC_ACQUIRE) != 0; }')
    source = once(source, '    bool exactQueueAdopted[2]{}; // gpuLock held; no inferred old-writer drain\n',
                  '    bool exactQueueAdopted[2]{}; // gpuLock held; no inferred old-writer drain\n'
                  '    uint32_t exactConfiguredQueues{0}; // atomic, monotonic; lost real work must never fall into E1 mock\n')
    old = method(source, 'IOReturn PhxBringup::adoptQueue(')
    new = once(old, '    exactQueueLive[qi] = true;\n',
               '    exactQueueLive[qi] = true;\n'
               '    __atomic_fetch_or(&exactConfiguredQueues, 1u << qi, __ATOMIC_RELEASE);\n')
    source = once(source, old, new)
    return once(source, method(source, 'IOReturn PhxBringup::newUserClient('), FACTORY)
