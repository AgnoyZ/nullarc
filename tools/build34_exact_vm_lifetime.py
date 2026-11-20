#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Stage context identities and checked VM cleanup, never a kernel candidate.

The exact client/service quarantine, null device reader and legacy BO teardown
blockers remain. This tests service VM admission, not a complete healthy drain.
"""
from build34_exact_global import stage as previous_stage, stage_header
from build34_exact_submit import once
from test_build34_exact_ownership import method

WORK = '''bool PhxBringup::vmWorkCurrent(const VmCtx &c) const {
    // Both queues matter: a newer GFX submission cannot erase old compute work.
    // Generation loss is uncertainty, never completion from a new adoption seed.
    uint64_t newest = 0;
    for (uint32_t qi = 0; qi < 2; ++qi) {
        const uint64_t seq = c.queueSequence[qi], generation = c.queueGeneration[qi];
        if (!seq) {
            if (generation) return false;
            continue;
        }
        if (!generation || generation == UINT64_MAX || seq == UINT64_MAX ||
            seq > c.newest || seq > gSeq || seq > exactQueueSubmitted[qi] ||
            generation != exactQueueGeneration[qi] || !exactQueueLive[qi] || !gq[qi].ready) return false;
        if (seq > newest) newest = seq;
    }
    return newest == c.newest;
}

'''

OWNED = '''PhxBringup::VmCtx *PhxBringup::vmOwned(uint32_t handle, uint64_t generation,
                                               const void *client, bool closing) {
    // Caller owns gpuLock; no cached context pointer may survive an unlock.
    VmCtx *c = vmCtx(handle);
    return c && client && generation && generation != UINT64_MAX &&
           c->generation == generation && c->client == client &&
           (closing || !c->closing) && vmWorkCurrent(*c) ? c : nullptr;
}

'''

FLUSH = '''bool PhxBringup::vmFlushTlbChecked(uint32_t vmid) {
    // Same request/register protocol as build34; mapping/ACK hardware semantics
    // still require native evidence. Callers quarantine on any uncertain result.
    if (vmid < kFirstUserVmid || vmid >= kFirstUserVmid + kNumUserVmids ||
        exactCallbacks.closed() || exactStopped || isSleeping || exactVMFault) return false;
    const uint64_t start = mach_absolute_time();
    __asm__ __volatile__("mfence" ::: "memory");
    wreg(kRegInvEng17Req, 0x00F80000u | (1u << vmid) | 1u);
    for (uint32_t attempt = 0; attempt <= 1000; ++attempt) {
        if (exactCallbacks.closed() || exactStopped || isSleeping) return false;
        const uint32_t ack = rreg(kRegInvEng17Ack);
        if (exactCallbacks.closed() || exactStopped || isSleeping) return false;
        if (ack & (1u << vmid)) return true;
        uint64_t elapsed = 0;
        absolutetime_to_nanoseconds(mach_absolute_time() - start, &elapsed);
        if (elapsed >= 1000000ull || attempt == 1000) return false;
        IODelay(1); // no extra delay after budget expiry; bounded even if clock stops
    }
    return false;
}

'''

ALLOC = '''uint32_t PhxBringup::vmidAlloc(const void *client, uint64_t *generation) {
    phx34_exact::CallbackGate<>::Lease callback(exactCallbacks);
    if (!callback || !gpuLock || !client || !generation) return 0;
    IOLockLock(gpuLock);
    if (*generation || exactCallbacks.closed() || exactStopped || isSleeping || exactVMFault || !gpuReady()) {
        IOLockUnlock(gpuLock);
        return 0;
    }
    for (uint32_t i = 0; i < kMaxCtx; ++i) {
        VmCtx &c = vm[i];
        if (c.busy || c.closing || c.generation >= UINT64_MAX - 1) continue;
        if (!c.chunk[0]) {
            c.phys = ptTablePhys(c, 0);
            if (!c.phys) break;
            c.pages = kPtChunks * kPtChunkPages;
        }
        if (!c.phys || (c.phys & ~kPtAddrMask) || c.chunkPhys[0] != c.phys ||
            c.pages != kPtChunks * kPtChunkPages || !c.chunk[0]->getBytesNoCopy()) continue;
        ++c.generation; // outside queue history; preserved across successful free
        c.client = client;
        c.newest = 0;
        for (uint32_t qi = 0; qi < 2; ++qi) c.queueSequence[qi] = c.queueGeneration[qi] = 0;
        c.used = 1;
        c.hw = 0;
        c.closing = false;
        c.busy = true;
        *generation = c.generation; // output only after complete admission
        IOLockUnlock(gpuLock);
        return i + 1;
    }
    IOLockUnlock(gpuLock);
    return 0;
}

'''

FREE = '''bool PhxBringup::vmidFree(uint32_t handle, uint64_t generation, const void *client, uint64_t lastSeq) {
    phx34_exact::CallbackGate<>::Lease callback(exactCallbacks);
    if (!callback || !gpuLock) return false;
    const uint64_t start = mach_absolute_time();
    for (;;) {
        IOLockLock(gpuLock);
        VmCtx *context = vmOwned(handle, generation, client, true);
        if (!context || exactCallbacks.closed() || exactStopped || isSleeping || exactVMFault ||
            lastSeq > gSeq || context->newest > gSeq) {
            IOLockUnlock(gpuLock);
            return false;
        }
        VmCtx &c = *context;
        c.closing = true; // blocks every later map/unmap/bind/submit of this allocation
        uint64_t retired;
        if (!exactGlobalRetiredLocked(retired)) {
            IOLockUnlock(gpuLock);
            return false; // unknown completion never authorizes timeout cleanup
        }
        const uint64_t target = c.newest > lastSeq ? c.newest : lastSeq;
        if (retired < target) {
            uint64_t elapsed = 0;
            absolutetime_to_nanoseconds(mach_absolute_time() - start, &elapsed);
            IOLockUnlock(gpuLock);
            if (elapsed >= 2000000000ull) return false;
            IOSleep(1);
            continue; // revalidate the complete identity after every unlock
        }
        if (!c.used || c.used > kPtChunks * kPtChunkPages || c.used > c.pages) {
            IOLockUnlock(gpuLock);
            return false;
        }
        // Validate all needed chunks before the first table/register mutation.
        for (uint32_t k = 0; k * kPtChunkPages < c.used; ++k) {
            if (!c.chunk[k] || !c.chunk[k]->getBytesNoCopy()) {
                IOLockUnlock(gpuLock);
                return false;
            }
        }
        if (c.hw) {
            if (c.hw < kFirstUserVmid || c.hw >= kFirstUserVmid + kNumUserVmids ||
                hwv[c.hw - kFirstUserVmid].ctx != handle ||
                hwv[c.hw - kFirstUserVmid].generation != generation) {
                IOLockUnlock(gpuLock);
                return false;
            }
            // Do not clear a byte or free metadata if invalidation is uncertain.
            if (!vmFlushTlbChecked(c.hw)) {
                exactVMFault = true;
                IOLockUnlock(gpuLock);
                return false;
            }
        } else {
            for (uint32_t i = 0; i < kNumUserVmids; ++i) {
                if (hwv[i].ctx == handle) {
                    IOLockUnlock(gpuLock);
                    return false;
                }
            }
        }
        for (uint32_t k = 0; k * kPtChunkPages < c.used; ++k) {
            const uint32_t remaining = c.used - k * kPtChunkPages;
            const uint32_t n = remaining < kPtChunkPages ? remaining : kPtChunkPages;
            uint8_t *p = static_cast<uint8_t *>(c.chunk[k]->getBytesNoCopy());
            bzero(p, static_cast<size_t>(n) * 4096);
            for (uint32_t o = 0; o < n * 4096u; o += 64) flushLine(p + o);
        }
        if (c.hw) {
            HwVmid &h = hwv[c.hw - kFirstUserVmid];
            h.ctx = 0; h.generation = 0; h.lastSeq = 0;
            c.hw = 0;
        }
        c.used = 1;
        c.newest = 0;
        for (uint32_t qi = 0; qi < 2; ++qi) c.queueSequence[qi] = c.queueGeneration[qi] = 0;
        c.client = nullptr;
        c.busy = false;
        c.closing = false;
        // c.generation is deliberately retained: old tokens never acquire reuse.
        IOLockUnlock(gpuLock);
        return true;
    }
}

'''


def stage(source):
    source = previous_stage(source)
    source = once(source, '        bool busy;\n',
        '        bool busy;\n        uint64_t generation, newest;\n'
        '        uint64_t queueSequence[2], queueGeneration[2];\n'
        '        const void *client;\n        bool closing;\n')
    source = once(source, '        uint64_t lastSeq, lastUse;        // its newest submission; when it was last bound or used\n',
        '        uint64_t lastSeq, lastUse;        // its newest submission; when it was last bound or used\n'
        '        uint64_t generation; // reciprocal context allocation identity\n')
    source = once(source, '    uint64_t hwTick{0};\n',
        '    uint64_t hwTick{0};\n    bool exactVMFault{false}; // sticky; no speculative recovery/reuse\n'
        '    bool vmWorkCurrent(const VmCtx &) const; // gpuLock held\n'
        '    VmCtx *vmOwned(uint32_t, uint64_t, const void *, bool = false); // gpuLock held\n'
        '    bool vmFlushTlbChecked(uint32_t); // gpuLock and service lease held\n')
    replacements = [
        ('uint32_t vmidAlloc();','uint32_t vmidAlloc(const void *client, uint64_t *generation);'),
        ('void vmidFree(uint32_t vmid, uint64_t lastSeq);',
         'bool vmidFree(uint32_t vmid, uint64_t generation, const void *client, uint64_t lastSeq);'),
        ('IOReturn vmMap(uint32_t vmid, uint64_t va,',
         'IOReturn vmMap(uint32_t vmid, uint64_t generation, const void *client, uint64_t va,'),
        ('IOReturn vmUnmap(uint32_t vmid, uint64_t va,',
         'IOReturn vmUnmap(uint32_t vmid, uint64_t generation, const void *client, uint64_t va,'),
        ('uint32_t vmBind(uint32_t handle, uint64_t retired);',
         'uint32_t vmBind(uint32_t handle, uint64_t generation, const void *client, uint64_t retired);'),
        ('    uint64_t lastSeq{0};     // its newest submission:',
         '    uint64_t vmGeneration{0}; // paired with vmid; never a userspace value\n'
         '    uint64_t lastSeq{0};     // its newest submission:'),
        ('bool ensureVmid() { return vmid || (vmid = owner->vmidAlloc()) != 0; }',
         'bool ensureVmid() { return vmid ? vmGeneration != 0 : (vmid = owner->vmidAlloc(this, &vmGeneration)) != 0; }'),
    ]
    for old,new in replacements: source=once(source,old,new)
    for old,new,count in [
        ('gpuSubmit(uint32_t handle, bool gfx,','gpuSubmit(uint32_t handle, uint64_t generation, const void *client, bool gfx,',1),
        ('gpuSubmit(uint32_t vmid, bool gfx,','gpuSubmit(uint32_t vmid, uint64_t generation, const void *client, bool gfx,',1),
        ('owner->gpuSubmit(vmid, ','owner->gpuSubmit(vmid, vmGeneration, this, ',2),
        ('owner->vmidFree(vmid, lastSeq);','owner->vmidFree(vmid, vmGeneration, this, lastSeq);',2),
        ('owner->vmMap(vmid, va,','owner->vmMap(vmid, vmGeneration, this, va,',1),
        ('owner->vmUnmap(vmid, va,','owner->vmUnmap(vmid, vmGeneration, this, va,',1),
    ]:
        if source.count(old)!=count: raise ValueError('Context token callsite drift: '+old)
        source=source.replace(old,new)
    source=once(source,method(source,'uint32_t PhxBringup::vmidAlloc('),WORK+OWNED+FLUSH+ALLOC.rstrip()+'\n')
    source=once(source,method(source,'void PhxBringup::vmidFree('),FREE.rstrip()+'\n')
    bind=method(source,'uint32_t PhxBringup::vmBind(')
    bind=once(bind,'vmBind(uint32_t handle, uint64_t retired)',
        'vmBind(uint32_t handle, uint64_t generation, const void *client, uint64_t retired)')
    bind=once(bind,'    VmCtx *context = vmCtx(handle);',
        '    VmCtx *context = vmOwned(handle, generation, client);')
    bind=once(bind,'    if (!context || retired == UINT64_MAX || retired > gSeq) return 0;',
        '    if (!context || exactVMFault || retired == UINT64_MAX || retired > gSeq) return 0;')
    bind=once(bind,'            hwv[c.hw - kFirstUserVmid].ctx != handle) return 0;',
        '            hwv[c.hw - kFirstUserVmid].ctx != handle ||\n'
        '            hwv[c.hw - kFirstUserVmid].generation != generation) return 0;')
    bind=once(bind,'    if (h.ctx) {\n        VmCtx *old = vmCtx(h.ctx);\n'
        '        if (!old || old->hw != kFirstUserVmid + static_cast<uint32_t>(pick)) return 0;\n'
        '        old->hw = 0;\n    }\n    h.ctx = handle;\n    h.lastSeq = 0;\n'
        '    h.lastUse = now;\n    const uint32_t vmid = kFirstUserVmid + static_cast<uint32_t>(pick);\n    c.hw = vmid;',
        '    VmCtx *old = h.ctx ? vmCtx(h.ctx) : nullptr;\n'
        '    if (h.ctx && (!old || !vmWorkCurrent(*old) || old->generation != h.generation ||\n'
        '        old->hw != kFirstUserVmid + static_cast<uint32_t>(pick))) return 0;\n'
        '    const uint32_t vmid = kFirstUserVmid + static_cast<uint32_t>(pick);')
    bind=once(bind,'    vmFlushTlb(vmid);\n    return vmid;',
        '    if (!vmFlushTlbChecked(vmid)) {\n'
        '        exactVMFault = true; // registers may have changed; retain both allocations\n'
        '        return 0;\n    }\n'
        '    if (old) old->hw = 0;\n'
        '    h.ctx = handle; h.generation = generation; h.lastSeq = 0; h.lastUse = now;\n'
        '    c.hw = vmid;\n    return vmid;')
    source=once(source,method(source,'uint32_t PhxBringup::vmBind('),bind)
    for name in ['vmMap','vmUnmap']:
        sig='IOReturn PhxBringup::'+name+'('
        old=method(source,sig)
        new=once(old,name+'(uint32_t handle, uint64_t va,',
            name+'(uint32_t handle, uint64_t generation, const void *client, uint64_t va,')
        new=once(new,'    if (!vmCtx(handle))\n        return kIOReturnNotReady;\n    VmCtx &c = vm[handle - 1];\n',
            '    phx34_exact::CallbackGate<>::Lease callback(exactCallbacks);\n'
            '    if (!callback || !gpuLock) return kIOReturnNotReady;\n')
        new=once(new,'    IOLockLock(gpuLock);\n',
            '    IOLockLock(gpuLock);\n'
            '    VmCtx *context = vmOwned(handle, generation, client);\n'
            '    if (!context || exactCallbacks.closed() || exactStopped || isSleeping || exactVMFault) {\n'
            '        IOLockUnlock(gpuLock);\n        return kIOReturnNotReady;\n    }\n'
            '    VmCtx &c = *context;\n')
        # Validate VA/ranges before a segment lookup, PTE mutation or register write.
        marker='    VmCtx &c = *context;\n'
        checks='    if (!size || ((va | size) & 4095) || va < 0x10000 || va >= (1ull << 48) || size > (1ull << 48) - va'
        if name=='vmMap': checks+=' || !md || (off & 4095) || off > md->getLength() || size > md->getLength() - off'
        new=once(new,marker,marker+checks+') {\n'
            '        IOLockUnlock(gpuLock);\n        return kIOReturnBadArgument;\n    }\n')
        new=once(new,'    for (uint64_t p = 0; p < size; p += 4096) {\n',
            '    uint64_t retired;\n'
            '    if (!exactGlobalRetiredLocked(retired)) {\n'
            '        IOLockUnlock(gpuLock);\n        return kIOReturnNotReady;\n    }\n'
            '    if (retired < c.newest) {\n'
            '        IOLockUnlock(gpuLock);\n        return kIOReturnBusy;\n    }\n'
            '    for (uint64_t p = 0; p < size; p += 4096) {\n')
        if name=='vmMap':
            new=once(new,'        uint64_t *pte = pa ? vmPte(c, va + p, true) : nullptr;',
                '        const bool validPage = pa && !(pa & ~kPtAddrMask) && segLen >= 4096;\n'
                '        uint64_t *pte = validPage ? vmPte(c, va + p, true) : nullptr;')
            new=once(new,'            r = pa ? kIOReturnNoMemory : kIOReturnVMError;',
                '            r = validPage ? kIOReturnNoMemory : kIOReturnVMError;')
            new=once(new,'    if (c.hw)   // an unbound context is flushed when it is next bound\n',
                '    if (r != kIOReturnSuccess) exactVMFault = true; // partial PTE mutation is uncertain\n'
                '    if (c.hw && !exactVMFault) // an unbound context is flushed when next bound\n')
        new=once(new,'        vmFlushTlb(c.hw);',
            '        if (!vmFlushTlbChecked(c.hw)) {\n'
            '            exactVMFault = true;\n            IOLockUnlock(gpuLock);\n'
            '            return kIOReturnNotReady; // do not report a successful mapping mutation\n        }')
        source=once(source,old,new)
    submit=method(source,'IOReturn PhxBringup::gpuSubmit(')
    submit=once(submit,'    if (exact && !exact->boundTo(this, exactClient)) return kIOReturnNotReady;',
        '    if (!client || !generation || generation == UINT64_MAX ||\n'
        '        (exact && (client != exactClient || !exact->boundTo(this, exactClient)))) return kIOReturnNotReady;')
    submit=once(submit,'        if (!qp->ready || !vmCtx(handle)) {',
        '        if (!qp->ready || !vmOwned(handle, generation, client) || exactVMFault) {')
    submit=once(submit,'            vmid = vmBind(handle, retired);',
        '            vmid = vmBind(handle, generation, client, retired);\n'
        '            if (exactVMFault) {\n                IOLockUnlock(gpuLock);\n'
        '                return kIOReturnNotReady;\n            }')
    submit=once(submit,'    hwv[vmid - kFirstUserVmid].lastSeq = seq;',
        '    hwv[vmid - kFirstUserVmid].lastSeq = seq;\n'
        '    vm[handle - 1].newest = seq; // authoritative; never trust a client-supplied lastSeq alone\n'
        '    vm[handle - 1].queueSequence[actualQueue] = seq;\n'
        '    vm[handle - 1].queueGeneration[actualQueue] = exactQueueGeneration[actualQueue];')
    source=once(source,method(source,'IOReturn PhxBringup::gpuSubmit('),submit)
    global_method=method(source,'bool PhxBringup::exactGlobalRetiredLocked(')
    checked=once(global_method,' || gSeq == UINT64_MAX) return false;',
        ' || exactVMFault || gSeq == UINT64_MAX) return false;')
    checked=once(checked,'    uint64_t retired = gSeq;',
        '    for (uint32_t i = 0; i < kMaxCtx; ++i)\n'
        '        if (vm[i].busy && !vmWorkCurrent(vm[i])) return false;\n'
        '    uint64_t retired = gSeq;')
    source=once(source,global_method,checked)
    return source
