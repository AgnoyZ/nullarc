# SPDX-License-Identifier: MIT
"""Stage unbound public IOKit sleep/wake helpers with bounded enrollment."""

from build34_exact_event_wait import PARK, SNAPSHOT, stage as previous_stage, stage_header
from build34_exact_submit import once
from test_build34_exact_ownership import method


DECLARATIONS = '''    static void sleepExactIOKit(IOLock *, void *, uint64_t sampledAt, uint64_t intervalNs);
    static void wakeExactIOKit(IOLock *, void *);
    static constexpr uint32_t kExactEventSleepers = 32;
    uint32_t exactEventSleepers{0}; // gpuLock; includes sleepers reacquiring the lock
'''
FIELDS_AT = '    const ExactEventOps *exactEventOps{nullptr};\n'
SLEEP = 'void PhxBringup::sleepExactIOKit('
WAKE = 'void PhxBringup::wakeExactIOKit('

IOKIT_METHODS = '''void PhxBringup::sleepExactIOKit(IOLock *lock, void *key, uint64_t sampledAt, uint64_t intervalNs) {
    uint64_t ticks = 0;
    nanoseconds_to_absolutetime(intervalNs, &ticks);
    if (!ticks || ticks > UINT64_MAX - sampledAt) return;
    const uint64_t deadline = sampledAt + ticks;
    if (mach_absolute_time() >= deadline) return;
    // IOKit atomically enrolls on key, drops lock, and reacquires it on return.
    (void)IOLockSleepDeadline(lock, key, deadline, THREAD_ABORTSAFE);
}

void PhxBringup::wakeExactIOKit(IOLock *lock, void *key) {
    IOLockWakeup(lock, key, false); // all waiters for this queue recheck their own fence
}

'''
LIMIT_AT = '        exactEventSerial[receipt.queue] == stamp) {\n'
LIMIT = '''        if (exactEventSleepers >= kExactEventSleepers) {
            IOLockUnlock(gpuLock);
            return false; // re-observe, then use one polling turn if still pending
        }
'''
PARK_CALL = '            exactEventOps->sleep(gpuLock, &exactEventSerial[receipt.queue], now, slice);\n'
COUNTED_PARK = '            ++exactEventSleepers;\n' + PARK_CALL + '            --exactEventSleepers;\n'


def stage(source):
    source = previous_stage(source)
    source = once(source, FIELDS_AT, DECLARATIONS + FIELDS_AT)
    source = once(source, SNAPSHOT, IOKIT_METHODS + SNAPSHOT)
    old = method(source, PARK)
    new = once(once(old, LIMIT_AT, LIMIT_AT + LIMIT), PARK_CALL, COUNTED_PARK)
    return once(source, old, new)
