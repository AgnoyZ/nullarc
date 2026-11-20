#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Stage one R3 native-submit source experiment; never build/install a kext.

The caller pointer has no allocator/negotiation and stays null. Only the CPU
fixture supplies a Registry. Adoption epochs cover adoption only, not the
unimplemented stop/sleep/fault/teardown contracts. No runtime recipe uses this.
"""


def once(source, old, new):
    if source.count(old) != 1:
        raise ValueError('Exact-submit source anchor drift: ' + old[:100])
    return source.replace(old, new, 1)


def stage(source):
    source = once(source, '#include "PhxNativeABI.h"\n',
                  '#include "PhxNativeABI.h"\n#include "build34_exact_ownership.h"\n')
    source = once(source, 'uint32_t n, uint64_t *seq);',
                  'uint32_t n, uint64_t *seq, phx34_exact::Registry *exact = nullptr, '
                  'phx34_exact::Ticket ticket = {});')
    source = once(source, '    uint64_t gSeq{0};\n',
                  '    uint64_t gSeq{0};\n'
                  '    uint64_t exactQueueGeneration[2]{}; // outside resettable queue history\n')
    source = once(source, '    uint64_t lastSeq{0};',
                  '    // Source experiment only: no production assignment or capability.\n'
                  '    phx34_exact::Registry *exactOwnership{nullptr};\n'
                  '    uint64_t lastSeq{0};')
    source = once(source, '    GpuQueue &q = gq[qi];\n    bzero(&q, sizeof(q));',
                  '    if (exactQueueGeneration[qi] >= UINT64_MAX - 1) {\n'
                  '        IOLockUnlock(gpuLock);\n'
                  '        return kIOReturnNoResources;\n'
                  '    }\n'
                  '    ++exactQueueGeneration[qi];\n'
                  '    GpuQueue &q = gq[qi];\n    bzero(&q, sizeof(q));')
    source = once(source, 'uint32_t n, uint64_t *seqOut) {',
                  'uint32_t n, uint64_t *seqOut, phx34_exact::Registry *exact, '
                  'phx34_exact::Ticket ticket) {')
    source = once(source, '    GpuQueue &q = *qp;\n    const uint32_t vmid = vmBind(handle);',
                  '    GpuQueue &q = *qp;\n'
                  '    const uint32_t actualQueue = qp == &gq[1] ? 1u : 0u;\n'
                  '    if (exact && gSeq >= UINT64_MAX - 1) {\n'
                  '        IOLockUnlock(gpuLock);\n'
                  '        return kIOReturnNoResources;\n'
                  '    }\n'
                  '    const uint32_t vmid = vmBind(handle);')
    source = once(source, '    uint32_t k = 0;\n    if (!q.gfx) {',
                  '    // Fallible publication precedes every ring/WB/doorbell write.\n'
                  '    // vmBind can change VM registers; this is not side-effect-free admission.\n'
                  '    const uint64_t seq = gSeq + 1;\n'
                  '    if (exact && exact->publish(ticket, {seq, exactQueueGeneration[actualQueue], actualQueue})\n'
                  '                     != phx34_exact::Status::Ok) {\n'
                  '        IOLockUnlock(gpuLock);\n'
                  '        return kIOReturnNotReady;\n'
                  '    }\n'
                  '    uint32_t k = 0;\n    if (!q.gfx) {')
    # Keep publication of the global high-water mark at its legacy site.
    source = once(source, '    const uint64_t seq = ++gSeq;\n', '    gSeq = seq;\n')
    source = once(source,
                  '        const IOReturn r = owner->gpuSubmit(vmid, ib0.ip_type == PHX_AMDGPU_HW_IP_GFX, va, dw, h.num_ibs, &seq);\n'
                  '        if (r != kIOReturnSuccess)\n'
                  '            return r;\n',
                  '        phx34_exact::Ticket ticket;\n'
                  '        if (exactOwnership && exactOwnership->reserve(ticket) != phx34_exact::Status::Ok)\n'
                  '            return kIOReturnNoResources;\n'
                  '        const IOReturn r = owner->gpuSubmit(vmid, ib0.ip_type == PHX_AMDGPU_HW_IP_GFX, va, dw, h.num_ibs, &seq, exactOwnership, ticket);\n'
                  '        if (r != kIOReturnSuccess) {\n'
                  '            // Only Reserved can cancel; a published receipt is never erased.\n'
                  '            if (exactOwnership) exactOwnership->cancel(ticket);\n'
                  '            return r;\n'
                  '        }\n')
    return once(source, '    // E1: no GPU behind the call; the submission retires at once, as in the mock.\n',
                '    if (exactOwnership) return kIOReturnNotReady; // no mock success for exact clients\n'
                '    // E1: no GPU behind the call; the submission retires at once, as in the mock.\n')
