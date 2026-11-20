#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Stage checked global snapshots and one-pass VMID binding, CPU admission only.

No reader is bound. The old timeout cleanup and permanent quarantine remain;
this is not a native resource-drain or deployable kernel implementation.
"""
from build34_exact_window import stage as previous_stage, stage_header
from build34_exact_submit import once
from test_build34_exact_ownership import method

GLOBAL = '''bool PhxBringup::exactGlobalRetiredLocked(uint64_t &out) {
    // Caller holds gpuLock and a service callback lease. Never publish a
    // partial/target/client-local watermark or silently skip a lost queue.
    if (exactCallbacks.closed() || exactStopped || isSleeping || gSeq == UINT64_MAX) return false;
    uint64_t retired = gSeq;
    for (uint32_t qi = 0; qi < 2; ++qi) {
        const GpuQueue &q = gq[qi];
        if (!exactQueueGeneration[qi]) {
            if (q.ready || exactQueueLive[qi] || q.head || q.tail || exactQueueSubmitted[qi]) return false;
            continue; // never-adopted metadata only, NOT proof about external hardware writers
        }
        uint64_t done;
        if (!readExactFence32(qi, &done) || exactQueueSubmitted[qi] > gSeq ||
            done > exactQueueSubmitted[qi]) return false;
        const uint32_t head = q.head, tail = q.tail;
        if (tail - head > 63u) return false;
        uint64_t previous = 0, pending = 0;
        for (uint32_t i = head; i != tail; ++i) {
            const uint64_t seq = q.fseq[i & 63u];
            if (!seq || seq == UINT64_MAX || seq <= previous || seq > exactQueueSubmitted[qi]) return false;
            previous = seq;
            if (!pending && seq > done) pending = seq;
        }
        if (head == tail) {
            if (done != exactQueueSubmitted[qi]) return false; // missing pending history
        } else if (previous != exactQueueSubmitted[qi]) return false;
        if (pending && pending - 1 < retired) retired = pending - 1;
    }
    if (exactCallbacks.closed() || exactStopped || isSleeping) return false;
    out = retired; // sole output write, after every queue/history is validated
    return true;
}

uint64_t PhxBringup::gpuRetired() const {
    phx34_exact::CallbackGate<>::Lease callback(exactCallbacks);
    if (!callback || !gpuLock) return 0;
    IOLockLock(gpuLock);
    uint64_t retired = 0;
    // Decoding advances the serialized observation cache of this logical read.
    const bool valid = const_cast<PhxBringup *>(this)->exactGlobalRetiredLocked(retired);
    IOLockUnlock(gpuLock);
    return valid ? retired : 0; // old scalar ABI; native exact protocol still needs explicit validity
}
'''

BIND = '''uint32_t PhxBringup::vmBind(uint32_t handle, uint64_t retired) {
    // Caller owns gpuLock and has just validated the genuine global snapshot.
    // One bounded scan only; gpuSubmit owns unlocked, monotonic-budget retries.
    VmCtx *context = vmCtx(handle);
    if (!context || retired == UINT64_MAX || retired > gSeq) return 0;
    VmCtx &c = *context;
    const uint64_t now = ++hwTick;
    if (c.hw) {
        if (c.hw < kFirstUserVmid || c.hw >= kFirstUserVmid + kNumUserVmids ||
            hwv[c.hw - kFirstUserVmid].ctx != handle) return 0;
        hwv[c.hw - kFirstUserVmid].lastUse = now;
        return c.hw;
    }
    int pick = -1;
    uint64_t oldest = UINT64_MAX;
    for (uint32_t i = 0; i < kNumUserVmids; ++i) {
        if (!hwv[i].ctx) { pick = static_cast<int>(i); break; }
        if (hwv[i].lastSeq <= retired && hwv[i].lastUse < oldest) {
            oldest = hwv[i].lastUse;
            pick = static_cast<int>(i);
        }
    }
    if (pick < 0) return 0;
    HwVmid &h = hwv[pick];
    if (h.ctx) {
        VmCtx *old = vmCtx(h.ctx);
        if (!old || old->hw != kFirstUserVmid + static_cast<uint32_t>(pick)) return 0;
        old->hw = 0;
    }
    h.ctx = handle;
    h.lastSeq = 0;
    h.lastUse = now;
    const uint32_t vmid = kFirstUserVmid + static_cast<uint32_t>(pick);
    c.hw = vmid;
    wreg(kRegCtx0BaseLo + 2 * vmid, static_cast<uint32_t>(c.phys | 3));
    wreg(kRegCtx0BaseLo + 2 * vmid + 1, static_cast<uint32_t>(c.phys >> 32));
    wreg(kRegCtx0Cntl + vmid, 0x01fffe07);
    wreg(kRegCtx0StartLo + 2 * vmid, 0);
    wreg(kRegCtx0StartLo + 2 * vmid + 1, 0);
    wreg(kRegCtx0EndLo + 2 * vmid, 0xffffffff);
    wreg(kRegCtx0EndLo + 2 * vmid + 1, 0xf);
    vmFlushTlb(vmid);
    return vmid;
}
'''


def stage(source):
    source = previous_stage(source)
    source = once(source,
                  '// or the least recently used one whose submissions the GPU has all finished (waits for one, bounded ~2 s). 0 on timeout.\n',
                  '// or the least recently used completed one. One scan; gpuSubmit owns unlocked bounded retries.\n')
    source = once(source,
                  '// Lock-free reader: an entry is written before `tail` moves past it.\n',
                  '// Checked under gpuLock; failure is distinct from a valid zero in the internal helper.\n')
    source = once(source, '    uint32_t vmBind(uint32_t handle);\n',
                  '    uint32_t vmBind(uint32_t handle, uint64_t retired);\n'
                  '    bool exactGlobalRetiredLocked(uint64_t &); // caller holds gpuLock and service lease\n')
    source = once(source, method(source, 'uint32_t PhxBringup::vmBind('), BIND)
    source = once(source, method(source, 'uint64_t PhxBringup::gpuRetired('), GLOBAL)
    submit = method(source, 'IOReturn PhxBringup::gpuSubmit(')
    submit = once(submit, '    GpuQueue *qp = nullptr;\n', '    GpuQueue *qp = nullptr;\n    uint32_t vmid = 0;\n')
    start = submit.index('    if (gSeq >= UINT64_MAX - 1) { // every shared-queue submit must preserve the window\n')
    end = submit.index('    // Fallible publication precedes every ring/WB/doorbell write.\n', start)
    old = submit[start:end]
    assert 'const uint32_t vmid = vmBind(handle);' in old
    submit = once(submit, old, '')
    # Keep the existing pre-retry deadline check, and add a post-VM-refusal
    # check so a delayed first admission cannot sleep again after expiry.
    submit = once(submit, '        if (hasSpace)\n            break;  // Keep the lock through VM binding, packet emission and doorbell.\n',
        '        if (hasSpace) {\n'
        '            const uint32_t selected = qp == &gq[1] ? 1u : 0u;\n'
        '            if (gSeq >= UINT64_MAX - 1) {\n'
        '                IOLockUnlock(gpuLock);\n                return kIOReturnNoResources;\n            }\n'
        '            if (!exactFenceWindow[selected].canSubmit(exactQueueGeneration[selected], gSeq + 1)) {\n'
        '                IOLockUnlock(gpuLock);\n                return kIOReturnBusy;\n            }\n'
        '            uint64_t retired;\n'
        '            if (!exactGlobalRetiredLocked(retired)) {\n'
        '                IOLockUnlock(gpuLock);\n                return kIOReturnNotReady;\n            }\n'
        '            vmid = vmBind(handle, retired);\n'
        '            if (vmid) break; // keep the lock through publication/packet/doorbell\n'
        '        }\n'
        '        uint64_t elapsed = 0;\n'
        '        absolutetime_to_nanoseconds(mach_absolute_time() - start, &elapsed);\n'
        '        if (elapsed >= 2000000000ull) {\n'
        '            IOLockUnlock(gpuLock);\n            return kIOReturnBusy;\n        }\n')
    return once(source, method(source, 'IOReturn PhxBringup::gpuSubmit('), submit)
