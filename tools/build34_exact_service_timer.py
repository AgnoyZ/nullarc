#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Stage owned ONCE timer/drain callbacks; GPU/service reclamation is not admitted."""
from build34_exact_watchdog import stage as previous_stage, stage_header
from build34_exact_submit import once
from test_build34_exact_ownership import method


FIELDS = '''    // One-shot timer lifecycle: 0 fresh, 1 initializing, 2 active,
    // 3 drain queued, 4 draining, 5 handles released, 6 uncertain/failed.
    uint32_t hangState{0};
    IOLock *hangLock{nullptr}; // retained with the service until native healthy teardown
    thread_call_t hangDrainCall{nullptr};
    bool hangServicePinned{false}; // hangLock held, except unpublished initialization
    phx34_exact::CallbackGate<> hangWorkers;
    bool hangStopping() const { return __atomic_load_n(&hangStop, __ATOMIC_ACQUIRE); }
    bool hangTimerReady() const {
        return __atomic_load_n(&hangState, __ATOMIC_ACQUIRE) == 2 && !hangStopping() &&
               __atomic_load_n(&hangCall, __ATOMIC_ACQUIRE) != nullptr;
    }
    bool hangTimerDrained() const {
        return __atomic_load_n(&hangState, __ATOMIC_ACQUIRE) == 5 && hangWorkers.drained();
    } // CPU timer prerequisite only; NEVER GPU drain or service/module-unload permission
    bool startHangTimer();
    void armHangTimer();
    void requestHangDrain();
    void sealStoppedQueues();
    static void hangDrainTick(thread_call_param_t, thread_call_param_t);
'''

START = '''bool PhxBringup::startHangTimer() {
    phx34_exact::CallbackGate<>::Lease callback(exactCallbacks);
    uint32_t expected = 0;
    if (!callback || !__atomic_compare_exchange_n(&hangState, &expected, 1, false,
                                                   __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) return false;
    retain(); // BEFORE allocation/publication; a scheduled callback cannot retain a dead owner
    hangServicePinned = true;
    IOLock *timerLock = IOLockAlloc();
    __atomic_store_n(&hangLock, timerLock, __ATOMIC_RELEASE);
    if (!timerLock) {
        hangServicePinned = false;
        __atomic_store_n(&hangState, 6u, __ATOMIC_RELEASE);
        release();
        return false;
    }
    __atomic_store_n(&hangCall, thread_call_allocate_with_options(hangTick, this, THREAD_CALL_PRIORITY_KERNEL, THREAD_CALL_OPTIONS_ONCE), __ATOMIC_RELEASE);
    __atomic_store_n(&hangDrainCall, thread_call_allocate_with_options(hangDrainTick, this, THREAD_CALL_PRIORITY_KERNEL, THREAD_CALL_OPTIONS_ONCE), __ATOMIC_RELEASE);
    IOLockLock(timerLock);
    if (!hangCall || !hangDrainCall || exactCallbacks.closed() || hangStopping()) {
        // Neither handle has ever been submitted. Check every free and retain
        // exact failed handles/pin instead of forgetting uncertain ownership.
        thread_call_t periodic = hangCall, drain = hangDrainCall;
        __atomic_store_n(&hangState, 6u, __ATOMIC_RELEASE);
        IOLockUnlock(timerLock);
        const bool periodicFreed = !periodic || thread_call_free(periodic);
        const bool drainFreed = !drain || thread_call_free(drain);
        IOLockLock(timerLock);
        if (periodicFreed) __atomic_store_n(&hangCall, static_cast<thread_call_t>(nullptr), __ATOMIC_RELEASE);
        if (drainFreed) __atomic_store_n(&hangDrainCall, static_cast<thread_call_t>(nullptr), __ATOMIC_RELEASE);
        const bool releasePin = periodicFreed && drainFreed;
        if (releasePin) hangServicePinned = false;
        IOLockUnlock(timerLock);
        if (releasePin) release();
        return false;
    }
    __atomic_store_n(&hangState, 2u, __ATOMIC_RELEASE);
    uint64_t deadline;
    clock_interval_to_deadline(500, kMillisecondScale, &deadline);
    // FALSE means newly enqueued, not enqueue failure. The lock serializes
    // publication with the stop worker's no-more-rearm transition.
    thread_call_enter_delayed(hangCall, deadline);
    IOLockUnlock(timerLock);
    return true;
}
'''

ARM = '''void PhxBringup::armHangTimer() {
    if (exactCallbacks.closed() || hangStopping()) return;
    IOLock *timerLock = __atomic_load_n(&hangLock, __ATOMIC_ACQUIRE);
    if (!timerLock) return;
    IOLockLock(timerLock);
    if (!exactCallbacks.closed() && hangTimerReady() && hangCall) {
        uint64_t deadline;
        clock_interval_to_deadline(500, kMillisecondScale, &deadline);
        thread_call_enter_delayed(hangCall, deadline);
    }
    IOLockUnlock(timerLock);
}
'''

REQUEST = '''void PhxBringup::requestHangDrain() {
    __atomic_store_n(&hangStop, true, __ATOMIC_RELEASE);
    IOLock *timerLock = __atomic_load_n(&hangLock, __ATOMIC_ACQUIRE);
    if (!timerLock) return; // initialization observes the stop before publishing
    IOLockLock(timerLock);
    if (__atomic_load_n(&hangState, __ATOMIC_ACQUIRE) == 2) {
        if (hangDrainCall && hangServicePinned) {
            __atomic_store_n(&hangState, 3u, __ATOMIC_RELEASE);
            thread_call_enter(hangDrainCall); // distinct callback; stop never waits on itself
        } else __atomic_store_n(&hangState, 6u, __ATOMIC_RELEASE);
    }
    IOLockUnlock(timerLock);
}
'''

SEAL = '''void PhxBringup::sealStoppedQueues() {
    if (gpuLock) IOLockLock(gpuLock);
    if (!exactStopped) {
        exactStopped = true;
        if (watchdogRecovery.active) watchdogRecovery.terminal = true;
        invalidateExactQueues();
    }
    if (gpuLock) IOLockUnlock(gpuLock);
}
'''

DRAIN = '''void PhxBringup::hangDrainTick(thread_call_param_t self, thread_call_param_t) {
    PhxBringup *me = static_cast<PhxBringup *>(self);
    Phx34ScopedReference reference(me); // persistent timer pin protects entry before this retain
    phx34_exact::CallbackGate<>::Lease worker(me->hangWorkers);
    if (!worker) return;
    IOLock *timerLock = __atomic_load_n(&me->hangLock, __ATOMIC_ACQUIRE);
    if (!timerLock) return;
    IOLockLock(timerLock);
    if (__atomic_load_n(&me->hangState, __ATOMIC_ACQUIRE) != 3 || !me->hangServicePinned ||
        !me->exactCallbacks.closed() || !me->hangStopping() || !me->hangCall || !me->hangDrainCall) {
        IOLockUnlock(timerLock);
        return;
    }
    __atomic_store_n(&me->hangState, 4u, __ATOMIC_RELEASE);
    thread_call_t periodic = me->hangCall, drain = me->hangDrainCall;
    IOLockUnlock(timerLock);
    // No GPU, client or timer lock is held. Both calls were allocated ONCE;
    // stop/rearm serialization prevents any later periodic submission.
    (void)thread_call_cancel_wait(periodic); // boolean is cancellation, not completion status
    me->sealStoppedQueues(); // also handles stop first observed during an admitted callback
    const bool periodicFreed = thread_call_free(periodic);
    const bool drainFreed = thread_call_free(drain); // documented own-callback free, no future use
    IOLockLock(timerLock);
    if (periodicFreed) __atomic_store_n(&me->hangCall, static_cast<thread_call_t>(nullptr), __ATOMIC_RELEASE);
    if (drainFreed) __atomic_store_n(&me->hangDrainCall, static_cast<thread_call_t>(nullptr), __ATOMIC_RELEASE);
    const bool releasePin = periodicFreed && drainFreed;
    if (releasePin) me->hangServicePinned = false;
    __atomic_store_n(&me->hangState, releasePin ? 5u : 6u, __ATOMIC_RELEASE);
    IOLockUnlock(timerLock);
    me->hangWorkers.close(); // drained remains false until this admitted worker leaves
    if (releasePin) me->release(); // exactly the registration pin, not the service quarantine
    // No GPU resource/BO/VM cleanup, PMstop, base stop, or unload permission.
}
'''

TICK = '''void PhxBringup::hangTick(thread_call_param_t self, thread_call_param_t) {
    PhxBringup *me = static_cast<PhxBringup *>(self);
    Phx34ScopedReference reference(me);
    phx34_exact::CallbackGate<>::Lease callback(me->exactCallbacks);
    if (!callback) return;
    me->reapLegacyClients();
    me->hangCheck();
    me->armHangTimer();
}
'''

STOP = '''void PhxBringup::stop(IOService *provider) {
    (void)provider;
    if (!exactCallbacks.close()) return;
    retain(); // existing service/GPU quarantine; timer drain does NOT remove it
    requestHangDrain(); // asynchronous, including stop from the timer itself
    if (!exactCallbacks.drained()) return;
    sealStoppedQueues();
    // Native queue/writer drain and healthy resource teardown are still required.
}
'''


def stage(source):
    source = previous_stage(source)
    source = once(source, '    bool vmWorkCurrent(const VmCtx &) const; // gpuLock held\n',
                  FIELDS + '    bool vmWorkCurrent(const VmCtx &) const; // gpuLock held\n')
    old = method(source, 'bool PhxBringup::start(')
    block = '''    hangCall = thread_call_allocate(hangTick, this);
    if (hangCall) {
        uint64_t d;
        clock_interval_to_deadline(500, kMillisecondScale, &d);
        thread_call_enter_delayed(hangCall, d);
    }
'''
    new = once(old, block, '''    if (!startHangTimer()) {
        exactCallbacks.close();
        retain(); // failed native start has mapped resources; no healthy unwind is proved
        return false;
    }
''')
    source = once(source, old, new)
    for sig in ['void PhxBringup::hangCheck(', 'bool PhxBringup::captureWatchdogLocked(',
                'bool PhxBringup::watchdogRecoveryCurrentLocked(',
                'bool PhxBringup::registerLegacyClient(', 'bool PhxBringup::bindExactClient(']:
        old = method(source, sig)
        new = old.replace('!hangCall', '!hangTimerReady()').replace('hangStop', 'hangStopping()')
        source = once(source, old, new)
    source = once(source, method(source, 'void PhxBringup::hangTick('), TICK.rstrip() + '\n')
    source = once(source, method(source, 'void PhxBringup::stop('),
                  '\n'.join([STOP, START, ARM, REQUEST, SEAL, DRAIN]))
    return source
