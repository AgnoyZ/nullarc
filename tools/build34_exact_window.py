#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Stage bounded raw-dword observation on every shared-queue submission.

No device reader is bound and no mapping or packet is changed. The earlier
permanent quarantine remains unsuitable for kernel build or deployment.
"""
from build34_exact_submit_receipt import stage as previous_stage, stage_header
from build34_exact_submit import once

READ = '''bool PhxBringup::readExactFence32(uint32_t qi, uint64_t *completed) {
    // Caller holds gpuLock and a service callback lease. No internal sleep/lock.
    if (qi >= 2 || !completed || !fbAper || !exactDwordReader ||
        exactCallbacks.closed() || exactStopped || isSleeping || !exactQueueLive[qi] || !gq[qi].ready)
        return false;
    const uint64_t offset = gq[qi].fenceOff;
    const uint64_t length = fbAper->getLength();
    const uintptr_t base = fbAper->getVirtualAddress();
    if ((offset & 3) || offset > fbAperLen || fbAperLen - offset < 4 ||
        offset > length || length - offset < 4 || !base || base > UINTPTR_MAX - offset ||
        ((base + offset) & 3)) return false;
    uint32_t raw = 0;
    if (!exactDwordReader(reinterpret_cast<const volatile uint32_t *>(base + offset), &raw) ||
        exactCallbacks.closed()) return false;
    uint64_t value;
    if (!exactFenceWindow[qi].observe(exactQueueGeneration[qi], raw, value)) return false;
    *completed = value;
    return true;
}

'''


def stage(source):
    source = previous_stage(source)
    source = once(source, '#include "build34_exact_submit_wire.h"\n',
                  '#include "build34_exact_submit_wire.h"\n#include "build34_exact_fence32.h"\n')
    source = once(source, '    uint64_t exactQueueSubmitted[2]{}; // includes legacy submissions; protected by gpuLock\n',
                  '    uint64_t exactQueueSubmitted[2]{}; // includes legacy submissions; protected by gpuLock\n'
                  '    phx34_exact::FenceWindow32 exactFenceWindow[2]; // protected by gpuLock\n'
                  '    using ExactDwordReader = bool (*)(const volatile uint32_t *, uint32_t *);\n'
                  '    ExactDwordReader exactDwordReader{nullptr}; // no native binding or legacy fallback\n'
                  '    bool readExactFence32(uint32_t, uint64_t *); // caller holds gpuLock and callback lease\n')
    source = once(source, '    ++exactQueueGeneration[qi];\n    GpuQueue &q = gq[qi];\n',
                  '    if (gSeq == UINT64_MAX) {\n        IOLockUnlock(gpuLock);\n        return kIOReturnNoResources;\n    }\n'
                  '    exactFenceWindow[qi].invalidate();\n'
                  '    ++exactQueueGeneration[qi];\n'
                  '    if (!exactFenceWindow[qi].seed(exactQueueGeneration[qi], gSeq)) {\n'
                  '        exactQueueLive[qi] = false;\n        IOLockUnlock(gpuLock);\n        return kIOReturnNotReady;\n    }\n'
                  '    GpuQueue &q = gq[qi];\n')
    source = once(source, '        exactQueueLive[i] = false;\n',
                  '        exactFenceWindow[i].invalidate();\n        exactQueueLive[i] = false;\n')
    source = once(source, '    if (exact && gSeq >= UINT64_MAX - 1) {\n',
                  '    if (gSeq >= UINT64_MAX - 1) { // every shared-queue submit must preserve the window\n')
    source = once(source, '        const uint64_t done = queueFence(q);\n        while (q.head != q.tail',
                  '        uint64_t done;\n'
                  '        if (!readExactFence32(qp == &gq[1] ? 1u : 0u, &done)) {\n'
                  '            IOLockUnlock(gpuLock);\n            return kIOReturnNotReady;\n        }\n'
                  '        while (q.head != q.tail')
    source = once(source, '    const uint32_t vmid = vmBind(handle);\n',
                  '    // Enforce global sequence distance, not job count, before VM/publication/packet writes.\n'
                  '    // A failed preflight changes no window upper bound; retry never reuses a published receipt.\n'
                  '    if (!exactFenceWindow[actualQueue].canSubmit(exactQueueGeneration[actualQueue], gSeq + 1)) {\n'
                  '        IOLockUnlock(gpuLock);\n        return kIOReturnBusy;\n    }\n'
                  '    const uint32_t vmid = vmBind(handle);\n')
    source = once(source, '    uint32_t k = 0;\n    if (!q.gfx) {\n',
                  '    if (!exactFenceWindow[actualQueue].submit(exactQueueGeneration[actualQueue], seq)) {\n'
                  '        IOLockUnlock(gpuLock);\n'
                  '        return kIOReturnNotReady; // an already-published receipt remains retained\n    }\n'
                  '    uint32_t k = 0;\n    if (!q.gfx) {\n')
    start = source.index('    // Identity/lifecycle loss needs no aperture read. Only the owned queue is sampled.\n')
    end = source.index('    // Closure is independent of gpuLock.', start)
    old = source[start:end]
    source = once(source, old,
                  '    // Only an admitted coherent dword from the owned generation enters the bounded decoder.\n'
                  '    if (live && observed.ready && observed.generation == receipt.generation)\n'
                  '        sampled = readExactFence32(receipt.queue, &observed.completed);\n')
    return once(source, 'uint64_t PhxBringup::queueFence(const GpuQueue &q) const {\n',
                READ + 'uint64_t PhxBringup::queueFence(const GpuQueue &q) const {\n')
