# SPDX-License-Identifier: MIT
"""Stage the completion-hint handshake without binding an AMD event source."""

from build34_exact_hqd_observation import stage as previous_stage, stage_header
from build34_exact_submit import once
from test_build34_exact_ownership import method


WAIT = 'phx34_exact::Status IOAccelPhxNativeClient::waitExactReceipt('
INVALIDATE = 'void PhxBringup::invalidateExactQueues()'
SNAPSHOT = 'uint64_t PhxBringup::exactEventStamp('
PARK = 'bool PhxBringup::parkExactEvent('
NOTIFY = 'bool PhxBringup::notifyExactEvent('
AVAILABLE = 'bool PhxBringup::exactEventAvailable('

ENTRY = '''    uint64_t exactEventStamp(const phx34_exact::Receipt &);
    bool parkExactEvent(const phx34_exact::Receipt &, uint64_t, const phx34_exact::CallbackGate<> &,
                        uint64_t start, uint64_t timeout);
'''

FIELDS = '''    struct ExactEventOps {
        // Stable for the service lifetime. Sleep atomically enrolls and drops gpuLock,
        // returns holding it. The deadline is sampled mach time plus the given ns
        // interval, never relative to when the backend finally enrolls. Wake broadcasts
        // on the same key with gpuLock held. Neither callback takes a client lock.
        void (*sleep)(IOLock *, void *key, uint64_t sampledAt, uint64_t intervalNs);
        void (*wake)(IOLock *, void *key);
        uint32_t queues;
    };
    const ExactEventOps *exactEventOps{nullptr};
    uint64_t exactEventSerial[2]{}; // gpuLock; saturates instead of reusing a stamp
    bool exactEventAvailable(uint32_t queue, uint64_t generation) const; // gpuLock
    bool notifyExactEvent(uint32_t queue, uint64_t generation); // deferred context only
'''

METHODS = '''bool PhxBringup::exactEventAvailable(uint32_t queue, uint64_t generation) const {
    return queue < 2 && exactEventOps && exactEventOps->sleep && exactEventOps->wake &&
           (exactEventOps->queues & (1u << queue)) && !exactCallbacks.closed() &&
           !exactStopped && !isSleeping && exactQueueLive[queue] &&
           exactQueueGeneration[queue] == generation && exactEventSerial[queue] != UINT64_MAX;
}

uint64_t PhxBringup::exactEventStamp(const phx34_exact::Receipt &receipt) {
    phx34_exact::CallbackGate<>::Lease callback(exactCallbacks);
    if (!callback || !exactEventOps || !gpuLock) return UINT64_MAX;
    IOLockLock(gpuLock);
    const uint64_t stamp = exactEventAvailable(receipt.queue, receipt.generation) ?
                           exactEventSerial[receipt.queue] : UINT64_MAX;
    IOLockUnlock(gpuLock);
    return stamp;
}

bool PhxBringup::parkExactEvent(const phx34_exact::Receipt &receipt, uint64_t stamp,
                              const phx34_exact::CallbackGate<> &client,
                              uint64_t start, uint64_t timeout) {
    phx34_exact::CallbackGate<>::Lease callback(exactCallbacks);
    if (!callback || !gpuLock) return true; // re-observe lifecycle
    IOLockLock(gpuLock);
    bool retryEvent = true;
    if (exactEventAvailable(receipt.queue, receipt.generation) && !client.closed() &&
        exactEventSerial[receipt.queue] == stamp) {
        const uint64_t now = mach_absolute_time();
        uint64_t elapsed = 0;
        absolutetime_to_nanoseconds(now - start, &elapsed);
        if (elapsed < timeout) {
            const uint64_t remaining = timeout - elapsed;
            // Keep the existing 1 ms polling cadence if delivery fails.
            const uint64_t slice = remaining < 1000000 ? remaining : 1000000;
            exactEventOps->sleep(gpuLock, &exactEventSerial[receipt.queue], now, slice);
            uint64_t parked = 0;
            absolutetime_to_nanoseconds(mach_absolute_time() - now, &parked);
            // A spurious/failed early sleep gets one polling turn, after observing again.
            retryEvent = exactEventSerial[receipt.queue] != stamp || parked >= slice;
        }
    }
    IOLockUnlock(gpuLock);
    return retryEvent;
}

bool PhxBringup::notifyExactEvent(uint32_t queue, uint64_t generation) {
    phx34_exact::CallbackGate<>::Lease callback(exactCallbacks);
    if (!callback || !exactEventOps || !gpuLock) return false;
    IOLockLock(gpuLock);
    const bool live = exactEventAvailable(queue, generation);
    if (live) {
        ++exactEventSerial[queue]; // a hint only: never write a fence or retire anything
        exactEventOps->wake(gpuLock, &exactEventSerial[queue]);
    }
    IOLockUnlock(gpuLock);
    return live;
}

'''

# All invalidation paths already serialize here, including service stop and recovery.
WAKE_INVALIDATED = '''        if (gpuLock && exactEventOps && exactEventOps->wake && (exactEventOps->queues & (1u << i)))
            exactEventOps->wake(gpuLock, &exactEventSerial[i]);
'''


def stage(source):
    source = previous_stage(source)
    entry = '    bool exactAdmissionClosed() const;\n'
    fields = '    uint64_t exactQueueGeneration[2]{}; // outside resettable queue history\n'
    source = once(source, entry, entry + ENTRY)
    source = once(source, fields, fields + FIELDS)
    source = once(source, INVALIDATE, METHODS + INVALIDATE)
    invalidate = method(source, INVALIDATE)
    lost = '        exactQueueLive[i] = false;\n'
    source = once(source, invalidate, once(invalidate, lost, lost + WAKE_INVALIDATED))
    wait = method(source, WAIT)
    staged = once(wait, '    for (;;) {\n',
                  '    bool retryEvent = true;\n'
                  '    for (;;) {\n'
                  '        // Snapshot before the authoritative fence recheck. Zero-budget calls only poll.\n'
                  '        const uint64_t stamp = timeout && retryEvent ? owner->exactEventStamp(receipt) : UINT64_MAX;\n')
    staged = once(staged, '        IOSleep(1);\n',
                  '        if (stamp == UINT64_MAX) {\n'
                  '            IOSleep(1);\n'
                  '            retryEvent = true;\n'
                  '        } else {\n'
                  '            retryEvent = owner->parkExactEvent(receipt, stamp, exactClientCallbacks, start, timeout);\n'
                  '        }\n')
    return once(source, wait, staged)
