#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Stage conditional legacy client close/reap, never a deployable candidate."""
from build34_exact_bo_lifetime import stage as previous_stage, stage_header
from build34_exact_submit import once
from test_build34_exact_ownership import method

REFERENCE = '''class Phx34ScopedReference {
    OSObject *object;
public:
    explicit Phx34ScopedReference(OSObject *p, bool takeReference = true) : object(p) {
        if (object && takeReference) object->retain();
    }
    ~Phx34ScopedReference() { if (object) object->release(); }
    Phx34ScopedReference(const Phx34ScopedReference &) = delete;
    Phx34ScopedReference &operator=(const Phx34ScopedReference &) = delete;
};

class Phx34ReapClaim {
    uint32_t *state;
public:
    explicit Phx34ReapClaim(uint32_t &value) : state(&value) {
        uint32_t expected = 0;
        if (!__atomic_compare_exchange_n(state, &expected, 1, false,
                                         __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) state = nullptr;
    }
    ~Phx34ReapClaim() { if (state) __atomic_store_n(state, 0u, __ATOMIC_RELEASE); }
    explicit operator bool() const { return state != nullptr; }
    Phx34ReapClaim(const Phx34ReapClaim &) = delete;
    Phx34ReapClaim &operator=(const Phx34ReapClaim &) = delete;
};

'''

REGISTER = '''bool PhxBringup::registerLegacyClient(OSObject *object) {
    phx34_exact::CallbackGate<>::Lease callback(exactCallbacks);
    auto *client = OSDynamicCast(IOAccelPhxNativeClient, object);
    if (!callback || !gpuLock || !client || client->owner != this || client->exactRequested ||
        client->exactOwnership || __atomic_load_n(&client->legacyState, __ATOMIC_ACQUIRE) != 1)
        return false;
    IOLockLock(gpuLock);
    if (exactCallbacks.closed() || exactStopped || isSleeping || exactVMFault || !hangCall || hangStop ||
        client->exactClientCallbacks.closed() || client->legacyClientPinned || client->legacyProviderPinned) {
        IOLockUnlock(gpuLock);
        return false;
    }
    int slot = -1;
    for (uint32_t i = 0; i < kMaxCtx; ++i) {
        if (legacyClients[i].client == client) {
            IOLockUnlock(gpuLock);
            return false;
        }
        if (!legacyClients[i].client && slot < 0) slot = static_cast<int>(i);
    }
    if (slot < 0) {
        IOLockUnlock(gpuLock);
        return false;
    }
    client->retain(); // established while starting, before any legacy entry admission
    retain(); // provider identity/locks outlive this registration
    client->legacyClientPinned = true;
    client->legacyProviderPinned = true; // provider belongs to the client object until final free
    legacyClients[slot].pending = false;
    legacyClients[slot].client = client; // publish only after both references
    IOLockUnlock(gpuLock);
    return true;
}

bool PhxBringup::requestLegacyClose(IOAccelPhxNativeClient *client) {
    if (!gpuLock || !client) return false;
    IOLockLock(gpuLock);
    for (uint32_t i = 0; i < kMaxCtx; ++i) {
        if (legacyClients[i].client == client) {
            legacyClients[i].pending = true;
            IOLockUnlock(gpuLock);
            return true;
        }
    }
    IOLockUnlock(gpuLock);
    return false;
}

bool PhxBringup::detachLegacyClient(IOAccelPhxNativeClient *client) {
    // Client lock held, all CPU/GPU cleanup succeeded. Registration pins still
    // protect these retained service locks even if stop has closed admission.
    if (!gpuLock || !client) return false;
    IOLockLock(gpuLock);
    int slot = -1;
    for (uint32_t i = 0; i < kMaxCtx; ++i) {
        if (legacyClients[i].client != client) continue;
        if (slot >= 0) { IOLockUnlock(gpuLock); return false; }
        slot = static_cast<int>(i);
    }
    if (slot >= 0) legacyClients[slot] = LegacyClientSlot{};
    IOLockUnlock(gpuLock);
    return slot >= 0; // reference drops happen outside both locks
}

void PhxBringup::reapLegacyClients() {
    Phx34ScopedReference reference(this); // before Lease: leave gate before final release
    phx34_exact::CallbackGate<>::Lease callback(exactCallbacks);
    if (!callback || !gpuLock) return;
    IOAccelPhxNativeClient *batch[4]{};
    uint32_t count = 0;
    IOLockLock(gpuLock);
    if (!exactCallbacks.closed() && !exactStopped && !isSleeping) {
        for (uint32_t scanned = 0; scanned < kMaxCtx && count < 4; ++scanned) {
            LegacyClientSlot &slot = legacyClients[legacyReapCursor];
            legacyReapCursor = (legacyReapCursor + 1) % kMaxCtx;
            if (!slot.client || !slot.pending) continue;
            slot.client->retain(); // acquire while the registration pin still exists
            batch[count++] = slot.client;
        }
    }
    IOLockUnlock(gpuLock);
    for (uint32_t i = 0; i < count; ++i) {
        IOAccelPhxNativeClient *client = batch[i];
        const IOReturn result = client->finishLegacyClose(); // NEVER under gpuLock
        if (result != kIOReturnSuccess && result != kIOReturnBusy) {
            IOLockLock(gpuLock);
            for (uint32_t k = 0; k < kMaxCtx; ++k)
                if (legacyClients[k].client == client) legacyClients[k].pending = false;
            IOLockUnlock(gpuLock); // sticky faults retain pins without repeated polling
        }
        client->release(); // transient batch reference; no access afterwards
    }
}

'''

START = '''bool IOAccelPhxNativeClient::start(IOService *provider) {
    if (!exactRequested && !exactOwnership) {
        uint32_t expected = 0;
        if (!__atomic_compare_exchange_n(&legacyState, &expected, 1, false,
                                        __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) return false;
        owner = OSDynamicCast(PhxBringup, provider);
        if (!owner || !IOUserClient::start(provider) || !owner->registerLegacyClient(this)) {
            __atomic_store_n(&legacyState, 4u, __ATOMIC_RELEASE);
            return false; // no GPU entry was admitted and no successful registration was lost
        }
        if (owner->claimSession()) sessionClaimed = true;
        __atomic_store_n(&legacyState, 2u, __ATOMIC_RELEASE); // fields/pins before entry admission
        return true;
    }
    // The earlier exact binding and permanent retention are intentionally unchanged.
    if (exactClientPinned || (exactRequested && exactStartAttempted) || exactOwnership) return false;
    if (exactRequested) exactStartAttempted = true;
    owner = OSDynamicCast(PhxBringup, provider);
    if (!owner) return false;
    if (owner->claimSession()) sessionClaimed = true;
    const bool started = IOUserClient::start(provider);
    if (started && exactRequested) {
        if (!owner->bindExactClient(exactRegistry, this)) return false;
        exactOwnership = &exactRegistry;
        exactClientPinned = true;
    }
    return started;
}

'''

CLOSE = '''IOReturn IOAccelPhxNativeClient::clientClose() {
    if (exactRequested || exactOwnership) {
        if (!exactClientPinned) return kIOReturnNotReady;
        exactClientCallbacks.close();
        return kIOReturnSuccess; // exact quarantine remains; no unpin/terminate
    }
    const uint32_t state = __atomic_load_n(&legacyState, __ATOMIC_ACQUIRE);
    if (state == 3) return kIOReturnSuccess;
    if (state != 2) return kIOReturnNotReady;
    Phx34ScopedReference reference(this); // existing live entry, never resurrection in free
    exactClientCallbacks.close(); // both modes refuse new entries BEFORE any drain check
    if (!owner->requestLegacyClose(this))
        return __atomic_load_n(&legacyState, __ATOMIC_ACQUIRE) == 3 ? kIOReturnSuccess : kIOReturnNotReady;
    return finishLegacyClose(); // busy clients are retried by the existing hangTick
}

IOReturn IOAccelPhxNativeClient::finishLegacyClose() {
    // Only clientClose and the service's pinned batch may call this helper.
    // A caller owns a transient reference in addition to registration pins.
    uint32_t state = __atomic_load_n(&legacyState, __ATOMIC_ACQUIRE);
    if (state == 3) return kIOReturnSuccess;
    if (state != 2) return kIOReturnNotReady;
    if (!exactClientCallbacks.drained()) return kIOReturnBusy; // no client lock while draining
    Phx34ReapClaim claim(legacyReaping);
    if (!claim) return kIOReturnBusy; // includes reentry from MD/terminate callbacks
    IOLockLock(lock);
    state = __atomic_load_n(&legacyState, __ATOMIC_ACQUIRE);
    if (state == 3) { IOLockUnlock(lock); return kIOReturnSuccess; }
    if (state != 2 || !legacyClientPinned || !owner || boCleanupFault ||
        (!vmid && (vmGeneration || lastSeq))) {
        __atomic_store_n(&legacyState, 5u, __ATOMIC_RELEASE);
        IOLockUnlock(lock);
        return kIOReturnNotReady;
    }
    uint64_t retired;
    const IOReturn proof = owner->vmBoSnapshot(vmid, vmGeneration, this, true, &retired);
    if (proof == kIOReturnBusy) { IOLockUnlock(lock); return proof; }
    if (proof != kIOReturnSuccess || retired < lastSeq ||
        (pendFenceSeq && pendFenceSeq > retired) || !publishCpuFence(retired)) {
        __atomic_store_n(&legacyState, 5u, __ATOMIC_RELEASE);
        IOLockUnlock(lock);
        return kIOReturnNotReady;
    }
    if (vmid && !owner->vmidFree(vmid, vmGeneration, this, lastSeq)) {
        __atomic_store_n(&legacyState, 5u, __ATOMIC_RELEASE);
        IOLockUnlock(lock);
        return kIOReturnNotReady; // retain tuple, BOs, pools, maps, session and both pins
    }
    vmid = 0; vmGeneration = 0; lastSeq = 0; // ONLY after checked VM release
    legacyReleaseAuthorized = true;
    if (!freeAll() || !owner->detachLegacyClient(this)) {
        boCleanupFault = true;
        __atomic_store_n(&legacyState, 5u, __ATOMIC_RELEASE);
        IOLockUnlock(lock);
        return kIOReturnNotReady;
    }
    PhxBringup *provider = owner;
    if (sessionClaimed) { provider->releaseSession(); sessionClaimed = false; }
    legacyClientPinned = false;
    __atomic_store_n(&legacyState, 3u, __ATOMIC_RELEASE);
    IOLockUnlock(lock);
    terminate();
    release(); // registration's client reference; caller's transient pin remains
    // Provider reference follows the client OBJECT, including other close
    // callers that still retain it, and is adopted in final free.
    return kIOReturnSuccess;
}

'''

FREEALL = '''bool IOAccelPhxNativeClient::freeAll() {
    if (!legacyReleaseAuthorized || exactClientPinned || !exactClientCallbacks.drained() ||
        vmid || vmGeneration || lastSeq || boCleanupFault || pendFenceSeq || releaseHeld.md || releasePermit)
        return false;
    legacyReleaseAuthorized = false; // one drain authorization, not a reusable release capability
    uint64_t totals[4]{};
    if (bos) for (uint32_t h = 1; h < PHXN_MAX_BOS; ++h) {
        const Bo &b = bos[h];
        if (!b.md) continue;
        const unsigned pool = b.host ? 3 : b.domain == 2 ? 2 : (b.bits & PHXN_PLACED_HI_POOL) ? 1 : 0;
        if (!b.size || b.size > UINT64_MAX - totals[pool]) return false;
        totals[pool] += b.size;
    }
    if (totals[0] != visUsed || totals[1] != hiUsed || totals[2] != gttUsed || totals[3] != hostUsed)
        return false; // no descriptor/pool/map mutation on invalid accounting
    if (maps) for (int i = 0; i < kMaxMaps; ++i) maps[i] = Map{};
    visUsed = hiUsed = gttUsed = hostUsed = 0;
    if (bos) for (uint32_t h = 1; h < PHXN_MAX_BOS; ++h) {
        if (!bos[h].md) continue;
        releasePermit = &bos[h]; // exact one-BO permission, consumed before any MD callback
        if (!boRelease(bos[h])) return false;
    }
    return true;
}

'''

RELEASE = '''bool IOAccelPhxNativeClient::boRelease(Bo &b) {
    if (boCleanupFault || (exactClientPinned && exactResourcesExposed) || !b.md ||
        releasePermit != &b || releaseHeld.md) return false;
    releasePermit = nullptr;
    releaseHeld = b;
    b = Bo{}; // consume handle before a host callback can reenter
    IOMemoryDescriptor *md = releaseHeld.md;
    if (releaseHeld.host && md->complete() != kIOReturnSuccess) {
        boCleanupFault = true;
        return false; // retain the exact uncertain descriptor in releaseHeld; never release/retry it
    }
    releaseHeld = Bo{};
    md->release();
    return true;
}

'''

FREE = '''void IOAccelPhxNativeClient::free() {
    // Start/registration pins must prevent this call while any GPU lifetime is
    // uncertain. These are defense checks, not late retain/resurrection.
    if (exactClientPinned || legacyClientPinned || vmid || vmGeneration || lastSeq ||
        boCleanupFault || releaseHeld.md || releasePermit ||
        __atomic_load_n(&legacyReaping, __ATOMIC_ACQUIRE)) return;
    const uint32_t state = __atomic_load_n(&legacyState, __ATOMIC_ACQUIRE);
    if (state == 1 || state == 2 || state == 5) return;
    exactClientCallbacks.close(); // failed/unstarted initialization owns no GPU resources
    if (!exactClientCallbacks.drained()) return;
    legacyReleaseAuthorized = true;
    if (!freeAll()) return;
    Phx34ScopedReference providerReference(legacyProviderPinned ? owner : nullptr, false);
    legacyProviderPinned = false; // adopt the existing reference, never retain/resurrect here
    if (sessionClaimed && owner) { owner->releaseSession(); sessionClaimed = false; }
    if (bos) { IOFree(bos, sizeof(Bo) * PHXN_MAX_BOS); bos = nullptr; }
    if (maps) { IOFree(maps, sizeof(Map) * kMaxMaps); maps = nullptr; }
    if (lock) { IOLockFree(lock); lock = nullptr; }
    IOUserClient::free();
}

'''


def stage(source):
    source = previous_stage(source)
    source = once(source, 'static phx34_exact::OwnerEpochs gExactOwners;', REFERENCE + 'static phx34_exact::OwnerEpochs gExactOwners;')
    source = once(source, '    IOReturn vmBoSnapshot(uint32_t, uint64_t, const void *, bool, uint64_t *);\n', '')
    source = once(source, '    uint32_t vmidAlloc(const void *client, uint64_t *generation);',
                  '    IOReturn vmBoSnapshot(uint32_t, uint64_t, const void *, bool, uint64_t *);\n'
                  '    bool registerLegacyClient(OSObject *);\n'
                  '    bool requestLegacyClose(IOAccelPhxNativeClient *);\n'
                  '    bool detachLegacyClient(IOAccelPhxNativeClient *);\n'
                  '    uint32_t vmidAlloc(const void *client, uint64_t *generation);')
    source = once(source, '    bool vmFlushTlbChecked(uint32_t);',
                  '    struct LegacyClientSlot { IOAccelPhxNativeClient *client; bool pending; };\n'
                  '    LegacyClientSlot legacyClients[kMaxCtx]{};\n    uint32_t legacyReapCursor{0};\n'
                  '    void reapLegacyClients();\n    bool vmFlushTlbChecked(uint32_t);')
    source = once(source, '    void boRelease(Bo &b);',
                  '    bool boRelease(Bo &b);\n    Bo *releasePermit{nullptr};\n    Bo releaseHeld{};\n'
                  '    uint32_t legacyState{0}, legacyReaping{0}; // atomic lifecycle and one-reaper claim\n'
                  '    bool legacyClientPinned{false}, legacyProviderPinned{false}, legacyReleaseAuthorized{false};\n'
                  '    IOReturn finishLegacyClose();')
    source = once(source, '    void freeAll();', '    bool freeAll();')
    anchor = method(source, 'bool PhxBringup::bindExactClient(')
    source = once(source, anchor, REGISTER + anchor)
    for sig, replacement in [
        ('bool IOAccelPhxNativeClient::start(', START),
        ('IOReturn IOAccelPhxNativeClient::clientClose(', CLOSE),
        ('void IOAccelPhxNativeClient::freeAll(', FREEALL),
        ('void IOAccelPhxNativeClient::boRelease(', RELEASE),
        ('void IOAccelPhxNativeClient::free(', FREE),
    ]:
        source = once(source, method(source, sig), replacement.rstrip() + '\n')
    old = method(source, 'IOReturn IOAccelPhxNativeClient::doBoFree(')
    new = once(old, '    boRelease(*b); // all mappings removed; clears the slot before MD callbacks\n    return kIOReturnSuccess;',
               '    releasePermit = b;\n    return boRelease(*b) ? kIOReturnSuccess : kIOReturnNotReady;')
    source = once(source, old, new)
    for sig in ['IOReturn IOAccelPhxNativeClient::externalMethod(',
                'IOReturn IOAccelPhxNativeClient::clientMemoryForType(',
                'IOReturn IOAccelPhxNativeClient::doSubmit(']:
        old = method(source, sig)
        marker = '    phx34_exact::CallbackGate<>::Lease clientCallback(exactClientCallbacks);\n'
        new = once(old, marker, marker +
                   '    if (!clientCallback || (!(exactRequested || exactOwnership) &&\n'
                   '        __atomic_load_n(&legacyState, __ATOMIC_ACQUIRE) != 2) ||\n'
                   '        !owner || owner->exactAdmissionClosed()) return kIOReturnNotReady;\n')
        new = new.replace('if (exactOwnership && exactClientCallbacks.closed())',
                          'if (exactClientCallbacks.closed() || boCleanupFault)')
        source = once(source, old, new)
    old = method(source, 'void PhxBringup::hangTick(')
    new = once(old, '    phx34_exact::CallbackGate<>::Lease callback(me->exactCallbacks);',
               '    Phx34ScopedReference reference(me);\n'
               '    phx34_exact::CallbackGate<>::Lease callback(me->exactCallbacks);')
    new = once(new, '    me->hangCheck();', '    me->reapLegacyClients();\n    me->hangCheck();')
    source = once(source, old, new)
    return source
