#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Stage selected native callback leases and a resource-retaining stop.

Not a deployable stop implementation: all resources and a service self-reference
are deliberately retained, even after CPU drain. Client BO/VMID teardown and
other service entrypoints are not covered. No runtime recipe uses this file.
"""
from build34_exact_lifecycle import stage as stage_lifecycle
from build34_exact_submit import once


GUARDS = {
    'IOReturn PhxBringup::gpuSubmit(': 'return kIOReturnNotReady;',
    'IOReturn PhxBringup::adoptQueue(': 'return kIOReturnNotReady;',
    'IOReturn PhxBringup::setPowerState(': 'return IOPMAckImplied;',
    'uint64_t PhxBringup::gpuRetired(': 'return 0;',
    'void PhxBringup::hangCheck(': 'return;',
    'void PhxBringup::killWaves(': 'return;',
}


def guard(signature, denial):
    return ('    phx34_exact::CallbackGate<>::Lease callback(exactCallbacks);\n'
            '    if (!callback) ' + denial + '\n')


def stage(source):
    source = stage_lifecycle(source)
    source = once(source, '#include "build34_exact_ownership.h"\n',
                  '#include "build34_exact_ownership.h"\n#include "build34_exact_callbacks.h"\n')
    source = once(source, '    uint64_t exactInvalidationEpoch{0};\n',
                  '    mutable phx34_exact::CallbackGate<> exactCallbacks;\n'
                  '    uint64_t exactInvalidationEpoch{0};\n')
    for signature, denial in GUARDS.items():
        start = source.index(signature)
        brace = source.index('{\n', start) + 2
        source = source[:brace] + guard(signature, denial) + source[brace:]
    source = once(source, '    PhxBringup *me = static_cast<PhxBringup *>(self);\n',
                  '    PhxBringup *me = static_cast<PhxBringup *>(self);\n'
                  '    phx34_exact::CallbackGate<>::Lease callback(me->exactCallbacks);\n'
                  '    if (!callback) return;\n')
    source = once(source, '    if (me->hangStop)\n',
                  '    if (me->exactCallbacks.closed() || me->hangStop)\n')
    # Holding a lease protects pointers across R1b's unlocked sleep, but an old
    # submit must also refuse dispatch when it next reacquires gpuLock.
    source = once(source, '        IOLockLock(gpuLock);\n        // Re-select and validate',
                  '        IOLockLock(gpuLock);\n'
                  '        if (exactCallbacks.closed()) {\n'
                  '            IOLockUnlock(gpuLock);\n'
                  '            return kIOReturnNotReady;\n'
                  '        }\n        // Re-select and validate')
    for signature, denial in [
        ('IOReturn PhxBringup::adoptQueue(', 'return kIOReturnNotReady;'),
        ('IOReturn PhxBringup::setPowerState(', 'return IOPMAckImplied;'),
        ('void PhxBringup::killWaves(', 'return;'),
    ]:
        start = source.index(signature)
        end = source.index('\n}\n', start) + 3
        old = source[start:end]
        # The power method uses an optional lock, the other two require one.
        lock = '    if (gpuLock) IOLockLock(gpuLock);\n' if 'setPowerState' in signature else '    IOLockLock(gpuLock);\n'
        unlock = 'if (gpuLock) IOLockUnlock(gpuLock);' if 'setPowerState' in signature else 'IOLockUnlock(gpuLock);'
        new = once(old, lock, lock + '    if (exactCallbacks.closed()) {\n'
                   '        ' + unlock + '\n        ' + denial + '\n    }\n')
        source = once(source, old, new)
    start = source.index('void PhxBringup::stop(IOService *provider) {\n')
    end = source.index('\n}\n', start) + 3
    # There is deliberately NO branch that performs the old resource releases.
    # A closed-but-busy stop must not wait for a callback while owning its lock;
    # a drained stop must not mistake CPU quiescence for GPU retirement either.
    source = source[:start] + '''void PhxBringup::stop(IOService *provider) {
    (void)provider;
    if (!exactCallbacks.close()) return;
    retain(); // quarantine service object as well as its mappings and locks
    if (!exactCallbacks.drained()) return;
    if (gpuLock) IOLockLock(gpuLock);
    exactStopped = true;
    invalidateExactQueues();
    if (gpuLock) IOLockUnlock(gpuLock);
    // CPU drain is NOT GPU drain: no release, PMstop, base stop or retry here.
}
''' + source[end:]
    return source
