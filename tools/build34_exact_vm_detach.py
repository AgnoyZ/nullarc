# SPDX-License-Identifier: MIT
"""Stage post-clear TLB invalidation for R3 VM teardown; CPU validation only."""

from build34_exact_overlap_snapshot import stage as previous_stage
from build34_exact_submit import once
from test_build34_exact_ownership import method


FREE = 'bool PhxBringup::vmidFree('


def stage(source):
    return detach_after_clear(previous_stage(source))


def detach_after_clear(source):
    old = method(source, FREE)
    new = once(old, '''            // Do not clear a byte or free metadata if invalidation is uncertain.
            if (!vmFlushTlbChecked(c.hw)) {
                exactVMFault = true;
                IOLockUnlock(gpuLock);
                return false;
            }
''', '')
    new = once(new, '''        if (c.hw) {
            HwVmid &h = hwv[c.hw - kFirstUserVmid];
''', '''        if (c.hw) {
            // Invalidate the cleared tables before dropping the hardware owner.
            if (!vmFlushTlbChecked(c.hw)) {
                exactVMFault = true; // retain the context and backing; never retry or reuse
                IOLockUnlock(gpuLock);
                return false;
            }
            HwVmid &h = hwv[c.hw - kFirstUserVmid];
''')
    return once(source, old, new)
