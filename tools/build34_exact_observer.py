#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Stage a source-only target observer with no admitted hardware fence reader.

Reader binding is immutable CPU-fixture injection only. A future reader must
prove device coherency and bounded/nonblocking operation; no fallback to the
legacy two-word read is admitted. No native ABI selector or runtime recipe.
"""
from build34_exact_client_lifetime import stage as stage_client
from build34_exact_submit import once


INSPECT = '''    // Caller serialization is mandatory; this copies identity, not a pointer.
    Status inspect(Ticket ticket, Receipt &receipt) {
        if (closed_) return Status::Closed;
        Entry *e = entry(ticket);
        if (!e) return Status::Unknown;
        if (e->phase == Phase::Reserved) return Status::Unsubmitted;
        if (e->phase == Phase::Lost) return Status::Lost;
        receipt = e->receipt;
        return Status::Ok;
    }

'''

OBSERVER = '''phx34_exact::Status PhxBringup::observeExact(phx34_exact::Registry &registry, phx34_exact::Ticket ticket,
                                               const phx34_exact::CallbackGate<> &clientAdmission) {
    // Caller holds the client lock and binds Registry lifetime to this provider.
    // That binding is still CPU-fixture-only, not authenticated native allocation.
    phx34_exact::CallbackGate<>::Lease callback(exactCallbacks);
    phx34_exact::Receipt receipt;
    const auto identity = registry.inspect(ticket, receipt);
    if (identity != phx34_exact::Status::Ok) return identity;
    phx34_exact::QueueObservation observations[2]{};
    if (!callback || !gpuLock || !fbAper) return registry.observe(ticket, false, observations);
    IOLockLock(gpuLock); // same client -> GPU lock order as submit
    const bool live = !exactCallbacks.closed() && !clientAdmission.closed() && !exactStopped && !isSleeping;
    auto &observed = observations[receipt.queue];
    const GpuQueue &q = gq[receipt.queue];
    observed.generation = exactQueueGeneration[receipt.queue];
    observed.submitted = exactQueueSubmitted[receipt.queue];
    observed.ready = q.ready && exactQueueLive[receipt.queue];
    bool sampled = false;
    // Identity/lifecycle loss needs no aperture read. Only the owned queue is sampled.
    if (live && observed.ready && observed.generation == receipt.generation && exactFenceReader &&
        !(q.fenceOff & 7) && q.fenceOff <= fbAperLen && fbAperLen - q.fenceOff >= 8) {
        const uint64_t length = fbAper->getLength();
        const uintptr_t base = fbAper->getVirtualAddress();
        if (q.fenceOff <= length && length - q.fenceOff >= 8 && base &&
            base <= UINTPTR_MAX - q.fenceOff && !((base + q.fenceOff) & 7)) {
            const auto *fence = reinterpret_cast<const volatile uint32_t *>(base + q.fenceOff);
            sampled = exactFenceReader(fence, &observed.completed);
        }
    }
    // Closure is independent of gpuLock. Recheck after the potentially delayed reader.
    const bool stillLive = live && !exactCallbacks.closed() && !clientAdmission.closed();
    phx34_exact::Status result;
    if (stillLive && observed.ready && observed.generation == receipt.generation && !sampled)
        result = phx34_exact::Status::InvalidObservation; // never fall back to legacy queueFence
    else
        result = registry.observe(ticket, stillLive, observations); // classify while both locks are held
    IOLockUnlock(gpuLock);
    return result;
}

phx34_exact::Status IOAccelPhxNativeClient::queryExact(uint64_t sequence) {
    phx34_exact::CallbackGate<>::Lease callback(exactClientCallbacks);
    if (!exactOwnership || !exactClientPinned) return phx34_exact::Status::Invalid;
    if (!callback) return phx34_exact::Status::Closed;
    IOLockLock(lock);
    if (exactClientCallbacks.closed()) {
        IOLockUnlock(lock);
        return phx34_exact::Status::Closed;
    }
    phx34_exact::Ticket ticket;
    auto result = exactOwnership->lookup(sequence, ticket);
    if (result == phx34_exact::Status::Ok)
        result = owner->observeExact(*exactOwnership, ticket, exactClientCallbacks);
    IOLockUnlock(lock);
    return result;
}

'''


def stage_header(source):
    return once(source, '    Status observe(Ticket ticket, bool service_live, const QueueObservation queues[2]) {\n',
                INSPECT + '    Status observe(Ticket ticket, bool service_live, const QueueObservation queues[2]) {\n')


def stage(source):
    source = stage_client(source)
    source = once(source, '    uint64_t gpuRetired() const;\n',
                  '    uint64_t gpuRetired() const;\n'
                  '    phx34_exact::Status observeExact(phx34_exact::Registry &, phx34_exact::Ticket,\n'
                  '                                        const phx34_exact::CallbackGate<> &);\n')
    source = once(source, '    uint64_t exactInvalidationEpoch{0};\n',
                  '    uint64_t exactQueueSubmitted[2]{}; // includes legacy submissions; protected by gpuLock\n'
                  '    using ExactFenceReader = bool (*)(const volatile uint32_t *, uint64_t *);\n'
                  '    ExactFenceReader exactFenceReader{nullptr}; // immutable CPU fixture binding only\n'
                  '    uint64_t exactInvalidationEpoch{0};\n')
    source = once(source, '    IOReturn doWaitSeq(IOExternalMethodArguments *a);\n',
                  '    IOReturn doWaitSeq(IOExternalMethodArguments *a);\n'
                  '    phx34_exact::Status queryExact(uint64_t sequence); // no selector/ABI exposure\n')
    source = once(source, '    q.ready = true;\n    exactQueueLive[qi] = true;\n',
                  '    exactQueueSubmitted[qi] = gSeq; // matches the adoption seed in this new generation\n'
                  '    q.ready = true;\n    exactQueueLive[qi] = true;\n')
    source = once(source, '    q.tail = q.tail + 1;\n',
                  '    q.tail = q.tail + 1;\n'
                  '    exactQueueSubmitted[actualQueue] = seq; // never substitute the global gSeq in an observation\n')
    return once(source, 'uint64_t PhxBringup::queueFence(const GpuQueue &q) const {\n',
                OBSERVER + 'uint64_t PhxBringup::queueFence(const GpuQueue &q) const {\n')
