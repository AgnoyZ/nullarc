#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Stage a public IOKit periodic timer with a separate public drain call.

No native reader, mode or healthy GPU/service reclaimer is admitted here.
"""
from build34_exact_native_sdk import stage as previous_stage, stage_header
from build34_exact_service_timer import FIELDS as OLD_FIELDS
from build34_exact_submit import once
from test_build34_exact_ownership import method

FIELDS = '''    // One-shot lifecycle: 0 fresh, 1 initializing, 2 active, 3 drain
    // queued, 4 detaching, 5 timer handles released, 6 uncertain/failed.
    uint32_t hangState{0};
    IOLock *hangLock{nullptr}; // retained until a separately proved healthy service teardown
    IOWorkLoop *hangLoop{nullptr};
    IOTimerEventSource *hangEvent{nullptr};
    thread_call_t hangDrainCall{nullptr};
    bool hangServicePinned{false}; // hangLock held, except unpublished initialization
    phx34_exact::CallbackGate<> hangWorkers;
    bool hangStopping() const { return __atomic_load_n(&hangStop, __ATOMIC_ACQUIRE); }
    bool hangTimerReady() const {
        return __atomic_load_n(&hangState, __ATOMIC_ACQUIRE) == 2 && !hangStopping() &&
               __atomic_load_n(&hangEvent, __ATOMIC_ACQUIRE) != nullptr &&
               __atomic_load_n(&hangLoop, __ATOMIC_ACQUIRE) != nullptr &&
               __atomic_load_n(&hangDrainCall, __ATOMIC_ACQUIRE) != nullptr;
    }
    bool hangTimerDrained() const {
        return __atomic_load_n(&hangState, __ATOMIC_ACQUIRE) == 5 && hangWorkers.drained();
    } // timer prerequisite only; NEVER GPU drain, service release or module-unload permission
    bool startHangTimer();
    bool abortHangTimerStart();
    bool armHangTimer();
    void requestHangDrain();
    void sealStoppedQueues();
    static IOReturn armHangTimerAction(OSObject *, void *, void *, void *, void *);
    static IOReturn closeHangTimerAction(OSObject *, void *, void *, void *, void *);
    static void hangDrainTick(thread_call_param_t, thread_call_param_t);
'''

START = '''bool PhxBringup::startHangTimer() {
    phx34_exact::CallbackGate<>::Lease callback(exactCallbacks);
    uint32_t expected = 0;
    if (!callback || !__atomic_compare_exchange_n(&hangState, &expected, 1, false,
                                                   __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) return false;
    retain(); // persistent registration pin precedes every publication
    hangServicePinned = true;
    IOLock *timerLock = IOLockAlloc();
    __atomic_store_n(&hangLock, timerLock, __ATOMIC_RELEASE);
    if (!timerLock) {
        hangServicePinned = false;
        __atomic_store_n(&hangState, 6u, __ATOMIC_RELEASE);
        release();
        return false;
    }
    IOWorkLoop *loop = IOWorkLoop::workLoop();
    IOTimerEventSource *timer = IOTimerEventSource::timerEventSource(
        kIOTimerEventSourceOptionsPriorityKernel, this, hangTick);
    __atomic_store_n(&hangLoop, loop, __ATOMIC_RELEASE);
    __atomic_store_n(&hangEvent, timer, __ATOMIC_RELEASE);
    __atomic_store_n(&hangDrainCall, thread_call_allocate_with_options(
        hangDrainTick, this, THREAD_CALL_PRIORITY_KERNEL, THREAD_CALL_OPTIONS_ONCE), __ATOMIC_RELEASE);
    // No timer/client/GPU lock is held while acquiring the workloop gate.
    // During state 1 stop cannot submit the drain call; this initializer
    // either publishes under the gate or owns the entire failed-start cleanup.
    if (!loop || !timer || !hangDrainCall || loop->addEventSource(timer) != kIOReturnSuccess ||
        !armHangTimer()) return abortHangTimerStart();
    return true;
}
'''

ABORT = '''bool PhxBringup::abortHangTimerStart() {
    IOLock *timerLock = __atomic_load_n(&hangLock, __ATOMIC_ACQUIRE);
    IOLockLock(timerLock);
    __atomic_store_n(&hangState, 6u, __ATOMIC_RELEASE);
    IOWorkLoop *loop = hangLoop;
    IOTimerEventSource *timer = hangEvent;
    thread_call_t drain = hangDrainCall;
    IOLockUnlock(timerLock);
    const bool detached = !timer || (!loop ? timer->getWorkLoop() == nullptr :
        loop->runAction(closeHangTimerAction, this, timer, loop) == kIOReturnSuccess);
    const bool freed = !drain || thread_call_free(drain); // never submitted in state 1
    const bool releasePin = detached && freed;
    IOLockLock(timerLock);
    if (freed) __atomic_store_n(&hangDrainCall, static_cast<thread_call_t>(nullptr), __ATOMIC_RELEASE);
    if (releasePin) {
        __atomic_store_n(&hangEvent, static_cast<IOTimerEventSource *>(nullptr), __ATOMIC_RELEASE);
        __atomic_store_n(&hangLoop, static_cast<IOWorkLoop *>(nullptr), __ATOMIC_RELEASE);
        hangServicePinned = false;
    }
    IOLockUnlock(timerLock);
    if (releasePin) {
        if (timer) timer->release();
        if (loop) loop->release();
        release();
    }
    return false;
}
'''

ARM_ACTION = '''IOReturn PhxBringup::armHangTimerAction(OSObject *target, void *arg0, void *arg1, void *, void *) {
    PhxBringup *me = static_cast<PhxBringup *>(target);
    IOTimerEventSource *timer = static_cast<IOTimerEventSource *>(arg0);
    IOWorkLoop *loop = static_cast<IOWorkLoop *>(arg1);
    if (!loop || !timer || !loop->inGate()) return kIOReturnNotReady;
    IOLock *timerLock = __atomic_load_n(&me->hangLock, __ATOMIC_ACQUIRE);
    IOLockLock(timerLock);
    const uint32_t state = __atomic_load_n(&me->hangState, __ATOMIC_ACQUIRE);
    IOReturn result = kIOReturnNotReady;
    if ((state == 1 || state == 2) && me->hangLoop == loop && me->hangEvent == timer &&
        me->hangDrainCall && me->hangServicePinned && !me->exactCallbacks.closed() &&
        !me->hangStopping() && timer->getWorkLoop() == loop && timer->isEnabled()) {
        uint64_t deadline;
        clock_interval_to_deadline(500, kMillisecondScale, &deadline);
        result = timer->wakeAtTime(deadline);
        if (result == kIOReturnSuccess) __atomic_store_n(&me->hangState, 2u, __ATOMIC_RELEASE);
    }
    IOLockUnlock(timerLock);
    return result;
}
'''

ARM = '''bool PhxBringup::armHangTimer() {
    if (exactCallbacks.closed() || hangStopping()) return false;
    IOLock *timerLock = __atomic_load_n(&hangLock, __ATOMIC_ACQUIRE);
    if (!timerLock) return false;
    IOLockLock(timerLock);
    IOWorkLoop *loop = hangLoop;
    IOTimerEventSource *timer = hangEvent;
    if (loop) loop->retain();
    if (timer) timer->retain();
    IOLockUnlock(timerLock);
    // Captured references protect even an arm queued behind stop/detachment.
    // Both native callers hold no GPU/client lock here; the callback already
    // has this same recursive workloop gate. Never wait for it under hangLock.
    const bool armed = loop && timer && loop->runAction(armHangTimerAction, this, timer, loop) == kIOReturnSuccess;
    if (timer) timer->release();
    if (loop) loop->release();
    return armed;
}
'''

CLOSE_ACTION = '''IOReturn PhxBringup::closeHangTimerAction(OSObject *target, void *arg0, void *arg1, void *, void *) {
    PhxBringup *me = static_cast<PhxBringup *>(target);
    IOTimerEventSource *timer = static_cast<IOTimerEventSource *>(arg0);
    IOWorkLoop *loop = static_cast<IOWorkLoop *>(arg1);
    if (!loop || !timer || !loop->inGate()) return kIOReturnNotReady;
    IOLock *timerLock = __atomic_load_n(&me->hangLock, __ATOMIC_ACQUIRE);
    IOLockLock(timerLock);
    const uint32_t state = __atomic_load_n(&me->hangState, __ATOMIC_ACQUIRE);
    IOReturn result = kIOReturnNotReady;
    if ((state == 4 || state == 6) && me->hangLoop == loop && me->hangEvent == timer && me->hangServicePinned &&
        (!timer->getWorkLoop() || timer->getWorkLoop() == loop)) {
        timer->disable();
        timer->cancelTimeout();
        result = timer->getWorkLoop() ? loop->removeEventSource(timer) : kIOReturnSuccess;
        if (result == kIOReturnSuccess && timer->getWorkLoop()) result = kIOReturnNotReady;
    }
    IOLockUnlock(timerLock);
    return result;
}
'''

DRAIN = '''void PhxBringup::hangDrainTick(thread_call_param_t self, thread_call_param_t) {
    PhxBringup *me = static_cast<PhxBringup *>(self);
    Phx34ScopedReference reference(me); // registration pin protects entry
    phx34_exact::CallbackGate<>::Lease worker(me->hangWorkers);
    if (!worker) return;
    IOLock *timerLock = __atomic_load_n(&me->hangLock, __ATOMIC_ACQUIRE);
    if (!timerLock) return;
    IOLockLock(timerLock);
    if (__atomic_load_n(&me->hangState, __ATOMIC_ACQUIRE) != 3 || !me->hangServicePinned ||
        !me->exactCallbacks.closed() || !me->hangStopping() || !me->hangLoop || !me->hangEvent || !me->hangDrainCall) {
        IOLockUnlock(timerLock);
        return;
    }
    __atomic_store_n(&me->hangState, 4u, __ATOMIC_RELEASE);
    IOWorkLoop *loop = me->hangLoop;
    IOTimerEventSource *timer = me->hangEvent;
    thread_call_t drain = me->hangDrainCall;
    IOLockUnlock(timerLock);
    // The distinct KERNEL/ONCE worker owns NO GPU, client or timer lock while
    // it waits for an in-flight timer action and invalidates pending actions.
    const bool detached = loop->runAction(closeHangTimerAction, me, timer, loop) == kIOReturnSuccess;
    me->sealStoppedQueues();
    const bool freed = thread_call_free(drain); // public, checked own-callback free
    const bool releasePin = detached && freed;
    IOLockLock(timerLock);
    if (freed) __atomic_store_n(&me->hangDrainCall, static_cast<thread_call_t>(nullptr), __ATOMIC_RELEASE);
    if (releasePin) {
        __atomic_store_n(&me->hangEvent, static_cast<IOTimerEventSource *>(nullptr), __ATOMIC_RELEASE);
        __atomic_store_n(&me->hangLoop, static_cast<IOWorkLoop *>(nullptr), __ATOMIC_RELEASE);
        me->hangServicePinned = false;
    }
    __atomic_store_n(&me->hangState, releasePin ? 5u : 6u, __ATOMIC_RELEASE);
    IOLockUnlock(timerLock);
    if (releasePin) { timer->release(); loop->release(); }
    me->hangWorkers.close();
    if (releasePin) me->release(); // registration only; service/GPU quarantine stays
}
'''

TICK = '''void PhxBringup::hangTick(OSObject *owner, IOTimerEventSource *sender) {
    PhxBringup *me = static_cast<PhxBringup *>(owner);
    Phx34ScopedReference reference(me);
    phx34_exact::CallbackGate<>::Lease callback(me->exactCallbacks);
    if (!callback || !me->hangTimerReady() ||
        sender != __atomic_load_n(&me->hangEvent, __ATOMIC_ACQUIRE)) return;
    me->reapLegacyClients();
    me->hangCheck();
    if (!me->armHangTimer() && !me->exactCallbacks.closed()) me->stop(nullptr);
}
'''


def stage(source):
    source = previous_stage(source)
    source = once(source, '#include <IOKit/IOLocks.h>\n',
                  '#include <IOKit/IOLocks.h>\n#include <IOKit/IOWorkLoop.h>\n#include <IOKit/IOTimerEventSource.h>\n')
    source = once(source, OLD_FIELDS, FIELDS)
    source = once(source, '    thread_call_t hangCall{nullptr};\n', '')
    source = once(source, '    static void hangTick(thread_call_param_t self, thread_call_param_t);',
                  '    static void hangTick(OSObject *, IOTimerEventSource *);')
    for signature, text in [('bool PhxBringup::startHangTimer(', START + '\n' + ABORT),
                            ('void PhxBringup::armHangTimer(', ARM_ACTION + '\n' + ARM + '\n' + CLOSE_ACTION),
                            ('void PhxBringup::hangDrainTick(', DRAIN),
                            ('void PhxBringup::hangTick(', TICK)]:
        source = once(source, method(source, signature), text.rstrip() + '\n')
    return source
