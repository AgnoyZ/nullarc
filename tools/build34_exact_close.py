#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Stage conditional exact-client drain/reap; no native reader or mode binding."""
from build34_exact_legacy_close import stage as previous_stage, stage_header as previous_header
from build34_exact_submit import once
from test_build34_exact_ownership import method


DRAIN = '''    // Client lock held, CPU admission closed AND drained by the caller.
    // Retain publication history even after ACK: empty entries are not a drain.
    Status proveClosedDrain(uint64_t prefix, const QueueObservation queues[2], const Receipt owned[2]) {
        if (!closed_ || drained_) return Status::Invalid;
        if (closeFault_) return Status::Lost;
        if (prefix == UINT64_MAX) return Status::InvalidObservation;
        uint64_t newest = 0;
        for (uint32_t qi = 0; qi < 2; ++qi) {
            const Receipt &r = published_[qi];
            if (!r.sequence) {
                if (r.generation || r.queue) return Status::InvalidObservation;
                continue;
            }
            const QueueObservation &q = queues[qi];
            if (!r.generation || r.generation == UINT64_MAX || r.queue != qi ||
                !q.ready || q.faulted || q.generation != r.generation) return Status::Lost;
            if (owned[qi].queue != qi || owned[qi].generation != r.generation ||
                owned[qi].sequence < r.sequence) return Status::InvalidObservation;
            if (r.sequence == UINT64_MAX || q.submitted == UINT64_MAX ||
                q.submitted < r.sequence || q.completed > q.submitted)
                return Status::InvalidObservation;
            if (prefix < r.sequence || q.completed < r.sequence) return Status::Pending;
            if (r.sequence > newest) newest = r.sequence;
        }
        if (newest != newest_) return Status::InvalidObservation;
        uint32_t occupied = 0;
        for (const Entry &e : entries_) {
            if (e.phase == Phase::Empty) {
                if (e.waiters) return Status::Invalid;
                continue;
            }
            ++occupied;
            if (e.waiters) return Status::Busy;
            if (e.phase == Phase::Reserved) return Status::Unsubmitted;
            if (e.phase == Phase::Lost) return Status::Lost;
            const Receipt &r = e.receipt;
            if (!e.serial || !r.sequence || r.queue >= 2 ||
                r.sequence > published_[r.queue].sequence ||
                r.generation != published_[r.queue].generation) return Status::InvalidObservation;
        }
        if (occupied != occupied_) return Status::InvalidObservation;
        drainProved_ = true; // no metadata cleared on any failed proof
        return Status::Ok;
    }
    bool closedDrainProved() const { return closed_ && drainProved_; }
    bool closedDrained() const { return closed_ && drained_; }
    Status retireClosed() {
        if (!closedDrainProved() || drained_) return Status::Invalid;
        for (const Entry &e : entries_) if (e.waiters) return Status::Busy;
        for (Entry &e : entries_) e = Entry{};
        occupied_ = 0;
        drained_ = true; // identity and publication history remain nonrebindable
        return Status::Ok;
    }

'''

BIND = '''bool PhxBringup::bindExactClient(phx34_exact::Registry &registry, OSObject *object) {
    phx34_exact::CallbackGate<>::Lease callback(exactCallbacks);
    auto *client = OSDynamicCast(IOAccelPhxNativeClient, object);
    if (!callback || !gpuLock || !client || &registry != &client->exactRegistry ||
        client->owner != this || !client->exactRequested || !client->exactStartAttempted ||
        __atomic_load_n(&client->legacyState, __ATOMIC_ACQUIRE) != 1) return false;
    IOLockLock(gpuLock);
    if (exactCallbacks.closed() || exactStopped || isSleeping || exactVMFault || !hangCall || hangStop ||
        client->exactClientCallbacks.closed() || client->exactOwnership || client->exactClientPinned ||
        client->legacyClientPinned || client->legacyProviderPinned) {
        IOLockUnlock(gpuLock);
        return false;
    }
    int slot = -1;
    for (uint32_t i = 0; i < kMaxCtx; ++i) {
        if (legacyClients[i].client == client) { IOLockUnlock(gpuLock); return false; }
        if (!legacyClients[i].client && slot < 0) slot = static_cast<int>(i);
    }
    if (slot < 0 || registry.bind(this, client, gExactOwners) != phx34_exact::Status::Ok) {
        IOLockUnlock(gpuLock);
        return false;
    }
    client->retain(); // shared registration pin, not a second exact reference
    retain(); // follows the client object through its final free
    client->legacyClientPinned = true;
    client->legacyProviderPinned = true;
    client->exactClientPinned = true;
    client->exactOwnership = &registry;
    legacyClients[slot].pending = false;
    legacyClients[slot].client = client; // both pins and identity before publication
    IOLockUnlock(gpuLock);
    return true;
}

'''

START = '''bool IOAccelPhxNativeClient::start(IOService *provider) {
    uint32_t expected = 0;
    if (!__atomic_compare_exchange_n(&legacyState, &expected, 1, false,
                                    __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) return false;
    if (exactRequested) exactStartAttempted = true;
    owner = OSDynamicCast(PhxBringup, provider);
    if (!owner || !IOUserClient::start(provider) ||
        !(exactRequested ? owner->bindExactClient(exactRegistry, this) : owner->registerLegacyClient(this))) {
        __atomic_store_n(&legacyState, 4u, __ATOMIC_RELEASE);
        return false;
    }
    if (owner->claimSession()) sessionClaimed = true;
    __atomic_store_n(&legacyState, 2u, __ATOMIC_RELEASE); // same publication/admission in both modes
    return true;
}

'''

SNAPSHOT = '''IOReturn PhxBringup::exactCloseSnapshot(phx34_exact::Registry &registry,
                            IOAccelPhxNativeClient *client, uint32_t handle, uint64_t generation,
                            uint64_t last, uint64_t *out) {
    // Caller owns client lock, a transient reference and closed/drained CPU admission.
    phx34_exact::CallbackGate<>::Lease callback(exactCallbacks);
    if (!callback || !gpuLock || !client || !out ||
        !registry.boundTo(this, client) || !client->exactClientCallbacks.drained())
        return kIOReturnNotReady;
    IOLockLock(gpuLock);
    uint64_t retired = 0;
    VmCtx *context = handle ? vmOwned(handle, generation, client) : nullptr;
    for (uint32_t i = 0; i < kMaxCtx; ++i) {
        if (vm[i].busy && vm[i].client == client && &vm[i] != context) {
            IOLockUnlock(gpuLock);
            return kIOReturnNotReady; // missing/mismatched tuple or duplicate allocation
        }
    }
    if (exactCallbacks.closed() || exactStopped || isSleeping || exactVMFault ||
        (handle ? !context : (generation || last)) || !exactGlobalRetiredLocked(retired)) {
        IOLockUnlock(gpuLock);
        return kIOReturnNotReady;
    }
    if (retired < last || (context && retired < context->newest)) {
        IOLockUnlock(gpuLock);
        return kIOReturnBusy;
    }
    phx34_exact::QueueObservation queues[2]{};
    phx34_exact::Receipt owned[2]{};
    for (uint32_t qi = 0; qi < 2; ++qi) {
        if (context && context->queueSequence[qi])
            owned[qi] = {context->queueSequence[qi], context->queueGeneration[qi], qi};
        queues[qi].generation = exactQueueGeneration[qi];
        queues[qi].submitted = exactQueueSubmitted[qi];
        queues[qi].ready = exactQueueLive[qi] && gq[qi].ready;
        if (exactQueueGeneration[qi] && !readExactFence32(qi, &queues[qi].completed)) {
            IOLockUnlock(gpuLock);
            return kIOReturnNotReady;
        }
    }
    if (exactCallbacks.closed() || exactStopped || isSleeping) {
        IOLockUnlock(gpuLock);
        return kIOReturnNotReady;
    }
    const auto proof = registry.proveClosedDrain(retired, queues, owned);
    IOLockUnlock(gpuLock);
    if (proof == phx34_exact::Status::Pending || proof == phx34_exact::Status::Busy)
        return kIOReturnBusy;
    if (proof != phx34_exact::Status::Ok) return kIOReturnNotReady;
    *out = retired; // genuine checked global prefix, never an exact target
    return kIOReturnSuccess;
}

'''

FINISH = '''IOReturn IOAccelPhxNativeClient::finishExactClose() {
    uint32_t state = __atomic_load_n(&legacyState, __ATOMIC_ACQUIRE);
    if (state == 3) return kIOReturnSuccess;
    if (state != 2) return kIOReturnNotReady;
    if (!exactClientCallbacks.drained()) return kIOReturnBusy;
    Phx34ReapClaim claim(legacyReaping);
    if (!claim) return kIOReturnBusy;
    IOLockLock(lock);
    state = __atomic_load_n(&legacyState, __ATOMIC_ACQUIRE);
    if (state != 2 || !legacyClientPinned || !legacyProviderPinned || !exactClientPinned ||
        !owner || exactOwnership != &exactRegistry || !exactRegistry.boundTo(owner, this) ||
        boCleanupFault || (!vmid && (vmGeneration || lastSeq))) {
        __atomic_store_n(&legacyState, 5u, __ATOMIC_RELEASE);
        IOLockUnlock(lock);
        return kIOReturnNotReady;
    }
    exactRegistry.close(); // only AFTER admitted submit/wait/ACK callbacks have left
    uint64_t retired = 0;
    const IOReturn proof = owner->exactCloseSnapshot(exactRegistry, this, vmid, vmGeneration, lastSeq, &retired);
    if (proof == kIOReturnBusy) { IOLockUnlock(lock); return proof; }
    if (proof != kIOReturnSuccess || (pendFenceSeq && pendFenceSeq > retired) || !publishCpuFence(retired) ||
        (vmid && !owner->vmidFree(vmid, vmGeneration, this, lastSeq))) {
        __atomic_store_n(&legacyState, 5u, __ATOMIC_RELEASE);
        IOLockUnlock(lock);
        return kIOReturnNotReady; // uncertain receipts/VM/BOs and both references remain retained
    }
    vmid = 0; vmGeneration = 0; lastSeq = 0; // checked VM release before BO release permission
    exactReleaseAuthorized = true;
    legacyReleaseAuthorized = true;
    const bool released = freeAll();
    exactReleaseAuthorized = false;
    if (!released || exactRegistry.retireClosed() != phx34_exact::Status::Ok ||
        !owner->detachLegacyClient(this)) {
        boCleanupFault = true;
        __atomic_store_n(&legacyState, 5u, __ATOMIC_RELEASE);
        IOLockUnlock(lock);
        return kIOReturnNotReady;
    }
    if (sessionClaimed) { owner->releaseSession(); sessionClaimed = false; }
    exactClientPinned = false;
    legacyClientPinned = false;
    __atomic_store_n(&legacyState, 3u, __ATOMIC_RELEASE);
    IOLockUnlock(lock);
    terminate();
    release(); // shared registration's client pin; caller's temporary reference still exists
    return kIOReturnSuccess;
}

'''


def stage_header(source):
    source = previous_header(source)
    source = once(source, '    uint64_t newest_ = 0;',
                  '    Receipt published_[2]{}; // never erased by per-ticket ACK\n'
                  '    bool closeFault_ = false, drainProved_ = false, drained_ = false;\n'
                  '    uint64_t newest_ = 0;')
    source = once(source, '        e->receipt = receipt;',
                  '        Receipt &previous = published_[receipt.queue];\n'
                  '        if (previous.sequence && previous.generation != receipt.generation) closeFault_ = true;\n'
                  '        previous = receipt;\n        e->receipt = receipt;')
    return once(source, '    void close() { closed_ = true; }', DRAIN + '    void close() { closed_ = true; }')


def stage(source):
    source = previous_stage(source)
    for sig, new in [('bool PhxBringup::bindExactClient(', BIND),
                     ('bool IOAccelPhxNativeClient::start(', START)]:
        source = once(source, method(source, sig), new.rstrip() + '\n')
    source = once(source, '    bool registerLegacyClient(OSObject *);',
                  '    IOReturn exactCloseSnapshot(phx34_exact::Registry &, IOAccelPhxNativeClient *,\n'
                  '                                uint32_t, uint64_t, uint64_t, uint64_t *);\n'
                  '    bool registerLegacyClient(OSObject *);')
    source = once(source, '    IOReturn finishLegacyClose();',
                  '    bool exactReleaseAuthorized{false};\n    IOReturn finishExactClose();\n'
                  '    IOReturn finishLegacyClose();')
    source = once(source, method(source, 'IOReturn IOAccelPhxNativeClient::clientClose('),
                  method(source, 'IOReturn IOAccelPhxNativeClient::clientClose(').replace('''    if (exactRequested || exactOwnership) {
        if (!exactClientPinned) return kIOReturnNotReady;
        exactClientCallbacks.close();
        return kIOReturnSuccess; // exact quarantine remains; no unpin/terminate
    }
''', ''))
    source = once(source, 'IOReturn IOAccelPhxNativeClient::finishLegacyClose() {\n',
                  SNAPSHOT + FINISH + 'IOReturn IOAccelPhxNativeClient::finishLegacyClose() {\n'
                  '    if (exactRequested || exactOwnership) return finishExactClose();\n')
    source = once(source, '    if (!legacyReleaseAuthorized || exactClientPinned || !exactClientCallbacks.drained() ||',
                  '    if (!legacyReleaseAuthorized ||\n'
                  '        (exactClientPinned && !(exactReleaseAuthorized && exactRegistry.closedDrainProved())) ||\n'
                  '        !exactClientCallbacks.drained() ||')
    source = once(source, '    if (boCleanupFault || (exactClientPinned && exactResourcesExposed) || !b.md ||',
                  '    if (boCleanupFault || (exactClientPinned && exactResourcesExposed &&\n'
                  '        !(exactReleaseAuthorized && exactRegistry.closedDrainProved() &&\n'
                  '          exactClientCallbacks.drained() && !vmid && !vmGeneration && !lastSeq)) || !b.md ||')
    # A rejected lease must return before reading mutable identity/pin fields.
    for name in ['queryExact', 'waitExact', 'ackExact', 'waitExactReceipt', 'ackExactReceipt']:
        sig = 'phx34_exact::Status IOAccelPhxNativeClient::' + name + '('
        old = method(source, sig)
        line = '    if (!callback) return phx34_exact::Status::Closed;\n'
        new = once(old, line, '')
        anchor = '    phx34_exact::CallbackGate<>::Lease callback(exactClientCallbacks);\n'
        new = once(new, anchor, anchor + line +
                   '    if (__atomic_load_n(&legacyState, __ATOMIC_ACQUIRE) != 2) return phx34_exact::Status::Closed;\n')
        source = once(source, old, new)
    for name in ['externalMethod', 'clientMemoryForType', 'doSubmit']:
        sig = 'IOReturn IOAccelPhxNativeClient::' + name + '('
        old = method(source, sig)
        new = once(old, '    if (!clientCallback || (!(exactRequested || exactOwnership) &&\n'
                       '        __atomic_load_n(&legacyState, __ATOMIC_ACQUIRE) != 2) ||',
                       '    if (!clientCallback || __atomic_load_n(&legacyState, __ATOMIC_ACQUIRE) != 2 ||')
        source = once(source, old, new)
    return source
