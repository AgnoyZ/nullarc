#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Source-only transactional BO cleanup on the quarantined VM experiment.

No native reader, mode, healthy close/reclaimer or deployment is admitted.
"""
from build34_exact_vm_lifetime import stage as previous_stage, stage_header
from build34_exact_submit import once
from test_build34_exact_ownership import method

SNAPSHOT = '''IOReturn PhxBringup::vmBoSnapshot(uint32_t handle, uint64_t generation,
                                    const void *client, bool idle, uint64_t *out) {
    phx34_exact::CallbackGate<>::Lease callback(exactCallbacks);
    if (!callback || !gpuLock || !client || !out) return kIOReturnNotReady;
    IOLockLock(gpuLock);
    if (exactCallbacks.closed() || exactStopped || isSleeping || exactVMFault) {
        IOLockUnlock(gpuLock);
        return kIOReturnNotReady;
    }
    if (!handle && !generation) {
        *out = 0; // no VM allocation and no submitted GPU work; caller checks lastSeq
        IOLockUnlock(gpuLock);
        return kIOReturnSuccess;
    }
    VmCtx *c = vmOwned(handle, generation, client);
    uint64_t retired;
    if (!c || !exactGlobalRetiredLocked(retired)) {
        IOLockUnlock(gpuLock);
        return kIOReturnNotReady;
    }
    if (idle && retired < c->newest) {
        IOLockUnlock(gpuLock);
        return kIOReturnBusy; // never publish an unvalidated or busy release proof
    }
    *out = retired; // genuine global prefix, never an exact target
    IOLockUnlock(gpuLock);
    return kIOReturnSuccess;
}

'''

FENCE = '''bool IOAccelPhxNativeClient::publishCpuFence(uint64_t retired) {
    // Client lock held. Preserve build34's cache flush before CPU fence store.
    // Finish publication BEFORE BO handle reuse, including BOFREE without WAITSEQ.
    if (boCleanupFault) return false;
    Bo *fb = nullptr;
    if (pendFenceSeq && pendFenceSeq <= retired) {
        fb = findBo(pendFenceHandle);
        if (!fb || !fb->kva || pendFenceOffset > fb->size || fb->size - pendFenceOffset < 8) {
            boCleanupFault = true;
            return false;
        }
    }
    flushBos();
    if (fb) {
        bcopy(&pendFenceSeq, fb->kva + pendFenceOffset, 8);
        pendFenceSeq = 0;
        pendFenceHandle = pendFenceOffset = 0;
    }
    return true;
}

'''

BOFREE = '''IOReturn IOAccelPhxNativeClient::doBoFree(IOExternalMethodArguments *a) {
    phx34_exact::CallbackGate<>::Lease callback(exactClientCallbacks);
    if (!callback || exactClientCallbacks.closed() || boCleanupFault) return kIOReturnNotReady;
    if (!a || !shape(a, 1, 0, 0, 0) || !a->scalarInput || a->scalarInput[0] > UINT32_MAX)
        return kIOReturnBadArgument;
    const uint32_t h = static_cast<uint32_t>(a->scalarInput[0]);
    Bo *b = findBo(h);
    if (!b) return kIOReturnNotFound;
    if (exactClientPinned && exactResourcesExposed) return kIOReturnBusy; // quarantine stays
    if (!owner || !maps || (!vmid && (vmGeneration || lastSeq))) return kIOReturnNotReady;
    uint64_t *used = b->host ? &hostUsed : b->domain == 2 ? &gttUsed :
                     (b->bits & PHXN_PLACED_HI_POOL) ? &hiUsed : &visUsed;
    if (!b->size || *used < b->size) return kIOReturnBadArgument;
    // Preflight ALL metadata before the first PTE mutation or fence publication.
    for (int i = 0; i < kMaxMaps; ++i) {
        const Map &m = maps[i];
        if (!m.used || m.handle != h) continue;
        if (!m.size || ((m.va | m.size | m.off) & 4095) || m.va < 0x10000 ||
            m.va >= (1ull << 48) || m.size > (1ull << 48) - m.va ||
            m.off > b->size || m.size > b->size - m.off) return kIOReturnBadArgument;
    }
    uint64_t retired;
    const IOReturn proof = owner->vmBoSnapshot(vmid, vmGeneration, this, true, &retired);
    if (proof != kIOReturnSuccess) return proof;
    if (retired < lastSeq || (pendFenceSeq && pendFenceSeq > retired)) return kIOReturnBusy;
    if (!publishCpuFence(retired)) return kIOReturnNotReady;
    bool mutated = false;
    for (int i = 0; i < kMaxMaps; ++i) {
        const Map &m = maps[i];
        if (!m.used || m.handle != h || !vmid) continue;
        const IOReturn r = owner->vmUnmap(vmid, vmGeneration, this, m.va, m.size);
        if (r != kIOReturnSuccess) {
            // Busy before any mutation is retryable. Partial/uncertain cleanup
            // retains every BO/map record and permanently blocks more dispatch.
            if (mutated || r != kIOReturnBusy) boCleanupFault = true;
            return r;
        }
        mutated = true;
    }
    for (int i = 0; i < kMaxMaps; ++i)
        if (maps[i].used && maps[i].handle == h) maps[i] = Map{};
    *used -= b->size;
    boRelease(*b); // all mappings removed; clears the slot before MD callbacks
    return kIOReturnSuccess;
}

'''

RELEASE = '''void IOAccelPhxNativeClient::boRelease(Bo &b) {
    if (boCleanupFault || (exactClientPinned && exactResourcesExposed) || !b.md) return;
    IOMemoryDescriptor *md = b.md;
    const bool host = b.host;
    b = Bo{}; // consume this exact descriptor before complete/release can reenter
    if (host) md->complete();
    md->release();
}

'''

WAIT = '''IOReturn IOAccelPhxNativeClient::doWaitSeq(IOExternalMethodArguments *a) {
    phx34_exact::CallbackGate<>::Lease callback(exactClientCallbacks);
    if (!callback || !a || !shape(a, 3, 3, 0, 0) || !a->scalarInput || !a->scalarOutput)
        return kIOReturnBadArgument;
    const uint64_t start = mach_absolute_time(); // includes queued client/GPU locks
    uint64_t timeout = a->scalarInput[1];
    if (timeout > PHXN_WAIT_CAP_NS) timeout = PHXN_WAIT_CAP_NS;
    IOLockLock(lock);
    const uint64_t em = emitted;
    const uint64_t target = a->scalarInput[0] == PHXN_SEQ_LAST ? em : a->scalarInput[0];
    const bool admitted = hello && owner && !boCleanupFault && !exactClientCallbacks.closed();
    IOLockUnlock(lock);
    if (!admitted) return kIOReturnNotReady;
    if (target > em) return kIOReturnBadArgument;
    uint64_t retired = 0;
    for (;;) {
        IOLockLock(lock);
        IOReturn result = kIOReturnNotReady;
        if (!boCleanupFault && !exactClientCallbacks.closed() &&
            (vmid || (!vmGeneration && !lastSeq))) {
            result = owner->vmBoSnapshot(vmid, vmGeneration, this, false, &retired);
            if (result == kIOReturnSuccess && !vmid) retired = em; // E1 only; no real GPU work
            if (result == kIOReturnSuccess && retired >= target && !publishCpuFence(retired))
                result = kIOReturnNotReady;
        }
        IOLockUnlock(lock);
        if (result != kIOReturnSuccess) return result;
        if (retired >= target) break;
        uint64_t elapsed = 0;
        absolutetime_to_nanoseconds(mach_absolute_time() - start, &elapsed);
        if (elapsed >= timeout) break;
        if (elapsed < 1000000ull) IODelay(50);
        else IOSleep(1);
    }
    a->scalarOutput[0] = retired < target;
    a->scalarOutput[1] = retired;
    a->scalarOutput[2] = em;
    return kIOReturnSuccess;
}

'''


def stage(source):
    source = previous_stage(source)
    source = once(source, '    void boRelease(Bo &b);',
                  '    void boRelease(Bo &b);\n    bool publishCpuFence(uint64_t); // client lock held\n'
                  '    bool boCleanupFault{false}; // sticky uncertain BO/PTE cleanup; client lock held')
    source = once(source, '    bool vmFlushTlbChecked(uint32_t);',
                  '    IOReturn vmBoSnapshot(uint32_t, uint64_t, const void *, bool, uint64_t *);\n'
                  '    bool vmFlushTlbChecked(uint32_t);')
    anchor = method(source, 'bool PhxBringup::vmWorkCurrent(')
    source = once(source, anchor, SNAPSHOT + anchor)
    for sig, replacement in [
        ('IOReturn IOAccelPhxNativeClient::doBoFree(', BOFREE),
        ('void IOAccelPhxNativeClient::boRelease(', RELEASE),
        ('IOReturn IOAccelPhxNativeClient::doWaitSeq(', FENCE + WAIT),
    ]:
        source = once(source, method(source, sig), replacement.rstrip() + '\n')
    sig = 'IOReturn IOAccelPhxNativeClient::doGemVa('
    old = method(source, sig)
    new = once(old, '    if (!shape(a,',
               '    phx34_exact::CallbackGate<>::Lease callback(exactClientCallbacks);\n'
               '    if (!callback || exactClientCallbacks.closed() || boCleanupFault) return kIOReturnNotReady;\n'
               '    if (!a || !a->structureInput || !shape(a,')
    new = once(new, '    const phxn_gem_va *v = static_cast<const phxn_gem_va *>(a->structureInput);',
               '    phxn_gem_va request;\n    memcpy(&request, a->structureInput, sizeof(request));\n'
               '    const phxn_gem_va *v = &request; // single immutable, possibly unaligned copy')
    new = once(new, 'va + v->map_size > (1ull << 48)',
               'va >= (1ull << 48) || v->map_size > (1ull << 48) - va')
    new = once(new, 'v->offset_in_bo + v->map_size > b->size',
               'v->offset_in_bo > b->size || v->map_size > b->size - v->offset_in_bo')
    new = once(new, '    if (v->operation == PHX_AMDGPU_VA_OP_MAP) {',
               '    if (!owner || !maps || (!vmid && (vmGeneration || lastSeq))) return kIOReturnNotReady;\n'
               '    if (v->operation == PHX_AMDGPU_VA_OP_MAP) {')
    assignment = '        maps[freei] = Map{true, v->handle, va, v->map_size, v->offset_in_bo, v->flags};\n'
    new = once(new, assignment, '')
    new = once(new, '        if (owner->gpuReady()) {',
               '        if (vmid || owner->gpuReady()) {')
    new = once(new, '                maps[freei].used = false;',
               '                if (r != kIOReturnBusy && vmid) boCleanupFault = true;')
    new = once(new, '        return kIOReturnSuccess;\n    }',
               assignment + '        return kIOReturnSuccess;\n    }')
    new = once(new, '            maps[i].used = false;\n            if (vmid)\n'
               '                owner->vmUnmap(vmid, vmGeneration, this, va, v->map_size);',
               '            if (vmid) {\n'
               '                const IOReturn r = owner->vmUnmap(vmid, vmGeneration, this, va, v->map_size);\n'
               '                if (r != kIOReturnSuccess) {\n'
               '                    if (r != kIOReturnBusy) boCleanupFault = true;\n'
               '                    return r;\n                }\n            }\n'
               '            maps[i] = Map{}; // publish only after backend success')
    source = once(source, old, new)
    # These two actual callers execute with the client lock held. Never inspect
    # the non-atomic sticky flag in the outer pre-lock externalMethod guard.
    for sig in ['IOReturn IOAccelPhxNativeClient::doSubmit(',
                'IOReturn IOAccelPhxNativeClient::submitExactReceipt(']:
        old = method(source, sig)
        brace = old.index('{') + 1
        source = once(source, old, old[:brace] + '\n    if (boCleanupFault) return kIOReturnNotReady;' + old[brace:])
    return source
