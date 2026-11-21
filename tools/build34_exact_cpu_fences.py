#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Stage bounded multi-pending CPU fence publication; no native deployment."""
from build34_exact_close import stage as previous_stage, stage_header
from build34_exact_submit import once
from test_build34_exact_ownership import method


FIELDS = '''    static constexpr uint32_t kMaxCpuFences = 128;
    struct CpuFence {
        uint64_t sequence{0};
        IOMemoryDescriptor *md{nullptr};
        uint8_t *kva{nullptr};
        uint64_t size{0};
        uint32_t handle{0}, offset{0};
    };
    CpuFence cpuFences[kMaxCpuFences]{};
    uint32_t cpuFenceHead{0}, cpuFenceCount{0};
    bool checkCpuFences(); // client lock held, sticky fault on inconsistent ownership
    bool appendCpuFence(uint32_t, uint32_t, uint64_t);
    IOReturn prepareCpuFence();
'''

CHECK = '''bool IOAccelPhxNativeClient::checkCpuFences() {
    // The existing BO owns each descriptor throughout its pending record.
    // No added MD retain, allocation, user pointer or completion-as-ownership shortcut.
    if (boCleanupFault) return false;
    bool valid = cpuFenceHead < kMaxCpuFences && cpuFenceCount <= kMaxCpuFences;
    uint64_t previous = 0;
    if (valid) for (uint32_t i = 0; i < kMaxCpuFences; ++i) {
        const CpuFence &f = cpuFences[(cpuFenceHead + i) % kMaxCpuFences];
        if (i >= cpuFenceCount) {
            if (f.sequence || f.md || f.kva || f.size || f.handle || f.offset) valid = false;
            continue;
        }
        Bo *b = findBo(f.handle);
        if (!f.sequence || f.sequence == UINT64_MAX || f.sequence <= previous || f.sequence > lastSeq ||
            !b || !b->md || !b->kva || b->md != f.md || b->kva != f.kva || b->size != f.size ||
            (f.offset & 7) || f.offset > f.size || f.size - f.offset < 8) valid = false;
        previous = f.sequence;
    }
    if (valid && cpuFenceCount) {
        const CpuFence &last = cpuFences[(cpuFenceHead + cpuFenceCount - 1) % kMaxCpuFences];
        valid = pendFenceSeq == last.sequence && pendFenceHandle == last.handle && pendFenceOffset == last.offset;
    } else if (valid) {
        valid = !pendFenceSeq && !pendFenceHandle && !pendFenceOffset;
    }
    if (!valid) boCleanupFault = true; // retain all records, mappings and descriptors
    return valid;
}

bool IOAccelPhxNativeClient::appendCpuFence(uint32_t handle, uint32_t offset, uint64_t sequence) {
    if (!checkCpuFences()) return false;
    Bo *b = findBo(handle);
    if (cpuFenceCount == kMaxCpuFences || !sequence || sequence == UINT64_MAX || sequence > lastSeq ||
        (cpuFenceCount && sequence <= pendFenceSeq) || !b || !b->md || !b->kva ||
        (offset & 7) || offset > b->size || b->size - offset < 8) {
        boCleanupFault = true; // unexpected post-dispatch bookkeeping failure cannot authorize cleanup
        return false;
    }
    cpuFences[(cpuFenceHead + cpuFenceCount) % kMaxCpuFences] =
        CpuFence{sequence, b->md, b->kva, b->size, handle, offset};
    ++cpuFenceCount;
    pendFenceSeq = sequence; pendFenceHandle = handle; pendFenceOffset = offset;
    return true;
}

IOReturn IOAccelPhxNativeClient::prepareCpuFence() {
    // Full-ledger refusal precedes ensureVmid, packet writes, doorbells and output.
    // Completed records may be collected only from the checked genuine prefix.
    if (!checkCpuFences()) return kIOReturnNotReady;
    if (cpuFenceCount < kMaxCpuFences) return kIOReturnSuccess;
    uint64_t retired = 0;
    if (!owner || !vmid || !vmGeneration) return kIOReturnNotReady;
    const IOReturn proof = owner->vmBoSnapshot(vmid, vmGeneration, this, false, &retired);
    if (proof != kIOReturnSuccess) return proof;
    if (!publishCpuFence(retired)) return kIOReturnNotReady;
    return cpuFenceCount < kMaxCpuFences ? kIOReturnSuccess : kIOReturnBusy;
}

'''

PUBLISH = '''bool IOAccelPhxNativeClient::publishCpuFence(uint64_t retired) {
    // Preflight the ENTIRE ledger before the first CPU store, including later
    // pending records. Handle reuse must never redirect an old fence store.
    if (!checkCpuFences() || retired == UINT64_MAX) {
        boCleanupFault = true;
        return false;
    }
    flushBos(); // preserve build34's existing cache operation before CPU publication
    while (cpuFenceCount) {
        CpuFence &f = cpuFences[cpuFenceHead];
        if (f.sequence > retired) break;
        bcopy(&f.sequence, f.kva + f.offset, 8);
        f = CpuFence{}; // consume only after its store, in submission order
        cpuFenceHead = (cpuFenceHead + 1) % kMaxCpuFences;
        --cpuFenceCount;
    }
    if (!cpuFenceCount) pendFenceSeq = pendFenceHandle = pendFenceOffset = 0;
    // A remaining suffix has the same last record and unchanged mirrors.
    return true;
}

'''


def stage(source):
    source = previous_stage(source)
    source = once(source, '    bool publishCpuFence(uint64_t); // client lock held\n',
                  FIELDS + '    bool publishCpuFence(uint64_t); // client lock held\n')
    source = once(source, method(source, 'bool IOAccelPhxNativeClient::publishCpuFence('),
                  CHECK + PUBLISH.rstrip() + '\n')
    sig = 'IOReturn IOAccelPhxNativeClient::doSubmit('
    old = method(source, sig)
    new = once(old, '    Bo *fb = nullptr;\n',
               '    if (exactOwnership && (h.flags & PHXN_CS_HAS_FENCE)) return kIOReturnUnsupported;\n'
               '    Bo *fb = nullptr;\n')
    new = once(new, '    if (owner->gpuReady()) {\n',
               '    if (!checkCpuFences()) return kIOReturnNotReady;\n'
               '    if (owner->gpuReady()) {\n'
               '        if (fb) {\n'
               '            const IOReturn prepared = prepareCpuFence();\n'
               '            if (prepared != kIOReturnSuccess) return prepared;\n'
               '        }\n')
    new = once(new, '''        if (fb) {
            pendFenceHandle = h.fence_handle;
            pendFenceOffset = h.fence_offset;
            pendFenceSeq = seq;
        }
''', '''        if (fb && !appendCpuFence(h.fence_handle, h.fence_offset, seq)) return kIOReturnNotReady;
''')
    new = once(new, '    const uint64_t seq = ++emitted;\n',
               '    if (vmid || vmGeneration || lastSeq || cpuFenceCount) return kIOReturnNotReady;\n'
               '    if (emitted >= UINT64_MAX - 1) return kIOReturnNoResources;\n'
               '    const uint64_t seq = ++emitted;\n')
    source = once(source, old, new)
    sig = 'IOReturn IOAccelPhxNativeClient::doWaitSeq('
    old = method(source, sig)
    new = once(old, '            if (result == kIOReturnSuccess && retired >= target && !publishCpuFence(retired))\n',
               '            if (result == kIOReturnSuccess && !checkCpuFences()) result = kIOReturnNotReady;\n'
               '            if (result == kIOReturnSuccess && (retired >= target ||\n'
               '                (cpuFenceCount && cpuFences[cpuFenceHead].sequence <= retired)) && !publishCpuFence(retired))\n')
    source = once(source, old, new)
    sig = 'bool IOAccelPhxNativeClient::freeAll('
    old = method(source, sig)
    new = once(old, 'bool IOAccelPhxNativeClient::freeAll() {\n',
               'bool IOAccelPhxNativeClient::freeAll() {\n    if (!checkCpuFences()) return false;\n')
    new = once(new, 'boCleanupFault || pendFenceSeq || releaseHeld.md',
               'boCleanupFault || pendFenceSeq || cpuFenceCount || releaseHeld.md')
    source = once(source, old, new)
    sig = 'bool IOAccelPhxNativeClient::boRelease('
    old = method(source, sig)
    new = once(old, '    if (boCleanupFault || ', '    if (boCleanupFault || cpuFenceCount || ')
    return once(source, old, new)
