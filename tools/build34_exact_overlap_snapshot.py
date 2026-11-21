# SPDX-License-Identifier: MIT
"""Stage an internal R3 observation; no native reader, selector or export."""

from build34_exact_event_iokit import stage as previous_stage
from build34_exact_submit import once
from test_build34_exact_ownership import method


GLOBAL = 'bool PhxBringup::exactGlobalRetiredLocked('
COLLECT = 'bool PhxBringup::captureExactOverlap('
OLD_DECLARATION = '    bool exactGlobalRetiredLocked(uint64_t &); // caller holds gpuLock and service lease\n'
DECLARATIONS = '''    struct ExactOverlapSnapshot {
        struct Queue {
            uint64_t generation, submitted, completed;
        } queues[2]; // Compute, GFX
        uint64_t serviceEpoch, beginNs, endNs, retired;
    };
    bool captureExactOverlap(ExactOverlapSnapshot &); // retained service; no caller lock
    // Optional scratch belongs to captureExactOverlap, never to an external caller.
    bool exactGlobalRetiredLocked(uint64_t &, ExactOverlapSnapshot *scratch = nullptr);
'''
COLLECTOR = '''bool PhxBringup::captureExactOverlap(ExactOverlapSnapshot &out) {
    phx34_exact::CallbackGate<>::Lease callback(exactCallbacks);
    if (!callback || !gpuLock) return false;
    ExactOverlapSnapshot sample{};
    // Registry entry identity is boot-local. Resolve it outside gpuLock.
    sample.serviceEpoch = getRegistryEntryID();
    if (!sample.serviceEpoch || sample.serviceEpoch == UINT64_MAX) return false;

    IOLockLock(gpuLock);
    absolutetime_to_nanoseconds(mach_absolute_time(), &sample.beginNs);
    const bool valid = exactGlobalRetiredLocked(sample.retired, &sample);
    absolutetime_to_nanoseconds(mach_absolute_time(), &sample.endNs);
    const bool publish = valid && sample.beginNs && sample.endNs != UINT64_MAX &&
                         sample.endNs >= sample.beginNs && !exactCallbacks.closed();
    if (publish) out = sample;
    IOLockUnlock(gpuLock);
    return publish;
}

'''


def stage(source):
    source = once(previous_stage(source), OLD_DECLARATION, DECLARATIONS)
    old = method(source, GLOBAL)
    new = once(old, '(uint64_t &out)', '(uint64_t &out, ExactOverlapSnapshot *scratch)')
    new = once(new, '        if (!exactQueueGeneration[qi]) {\n',
               '        if (scratch && (!exactQueueAdopted[qi] || !exactQueueGeneration[qi])) return false;\n'
               '        if (!exactQueueGeneration[qi]) {\n')
    new = once(new, '        if (pending && pending - 1 < retired) retired = pending - 1;\n',
               '        if (pending && pending - 1 < retired) retired = pending - 1;\n'
               '        if (scratch) scratch->queues[qi] = {exactQueueGeneration[qi], exactQueueSubmitted[qi], done};\n')
    return once(source, old, COLLECTOR + new)
