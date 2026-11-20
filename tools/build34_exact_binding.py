#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Stage embedded exact receipts with module-lifetime owner identity, CPU only.

No selector requests this mode; no hardware reader or deployment recipe exists.
Native IOKit finalization/unload and safe reclamation remain unproved.
"""
from build34_exact_client_lifetime import ENTRY_GUARD, body, prepend
from build34_exact_observer import stage as stage_observer, stage_header as inspect_header
from build34_exact_submit import once


OWNERS = '''// Shared across all service instances for this module lifetime. Never reset.
// Bounded CAS admission can refuse contention; it never wraps or reuses an ID.
class OwnerEpochs {
    uint64_t last_;
public:
    explicit constexpr OwnerEpochs(uint64_t previous = 0) : last_(previous) {}
    OwnerEpochs(const OwnerEpochs &) = delete;
    OwnerEpochs &operator=(const OwnerEpochs &) = delete;
    bool take(uint64_t &out) {
        uint64_t value = __atomic_load_n(&last_, __ATOMIC_RELAXED);
        for (unsigned attempt = 0; attempt < 32; ++attempt) {
            if (value >= UINT64_MAX - 1) return false;
            const uint64_t next = value + 1;
            if (__atomic_compare_exchange_n(&last_, &value, next, false,
                                            __ATOMIC_RELAXED, __ATOMIC_RELAXED)) {
                out = next;
                return true;
            }
        }
        return false;
    }
};
static_assert(__atomic_always_lock_free(sizeof(uint64_t), nullptr), "owner admission must be lock-free");

'''

BIND = '''    // Only a never-used embedded Registry may bind, under the provider lock.
    // Raw pointers are internal identity labels; they never come from userspace.
    Status bind(const void *provider, const void *client, OwnerEpochs &owners) {
        if (!provider || !client || owner_ || provider_ || client_ || occupied_ || !closed_)
            return Status::Invalid;
        uint64_t owner;
        if (!owners.take(owner)) return Status::Exhausted;
        provider_ = provider;
        client_ = client;
        owner_ = owner;
        closed_ = false;
        return Status::Ok;
    }
    bool boundTo(const void *provider, const void *client) const {
        return provider && client && provider_ == provider && client_ == client &&
               owner_ && owner_ != UINT64_MAX;
    }

'''

BIND_CLIENT = '''bool PhxBringup::bindExactClient(phx34_exact::Registry &registry, OSObject *client) {
    phx34_exact::CallbackGate<>::Lease callback(exactCallbacks);
    if (!callback || !client || !gpuLock) return false;
    auto *native = OSDynamicCast(IOAccelPhxNativeClient, client);
    if (!native || &registry != &native->exactRegistry || native->owner != this ||
        !native->exactRequested || !native->exactStartAttempted || native->exactClientPinned ||
        native->exactOwnership || native->exactClientCallbacks.closed()) return false;
    IOLockLock(gpuLock);
    const bool live = !exactCallbacks.closed() && !native->exactClientCallbacks.closed() &&
                      !exactStopped && !isSleeping;
    const bool bound = live && registry.bind(this, native, gExactOwners) == phx34_exact::Status::Ok;
    if (bound) {
        client->retain(); // embed lifetime starts before publishing exactOwnership
        retain(); // provider identity cannot be reused while this client is quarantined
    }
    IOLockUnlock(gpuLock);
    return bound;
}

'''

CLIENT_VALID = ('exactOwnership == &exactRegistry && exactClientPinned && '
                'exactRegistry.boundTo(owner, this)')


def stage_header(source):
    source = inspect_header(source)
    source = once(source, 'class Counter {\n', OWNERS + 'class Counter {\n')
    source = once(source, '    const uint64_t owner_;\n',
                  '    uint64_t owner_;\n'
                  '    const void *provider_ = nullptr, *client_ = nullptr;\n')
    return once(source, '    uint32_t occupied() const { return occupied_; }\n',
                BIND + '    uint32_t occupied() const { return occupied_; }\n')


def stage(source):
    source = stage_observer(source)
    source = once(source, '#include "build34_exact_ownership.h"\n',
                  '#include "build34_exact_ownership.h"\n'
                  'static phx34_exact::OwnerEpochs gExactOwners; // module lifetime, never reset\n')
    source = once(source, '    phx34_exact::Registry *exactOwnership{nullptr};\n',
                  '    phx34_exact::Registry exactRegistry{0}; // embedded, initially unbound\n'
                  '    phx34_exact::Registry *exactOwnership{nullptr};\n'
                  '    bool exactRequested{false}, exactStartAttempted{false}; // no native assignment/selector\n')
    source = once(source, 'class IOAccelPhxNativeClient : public IOUserClient {\n',
                  'class IOAccelPhxNativeClient : public IOUserClient {\n'
                  '    friend class PhxBringup; // only the service can admit this embedded registry\n')
    source = once(source, '    uint64_t gpuRetired() const;\n',
                  '    uint64_t gpuRetired() const;\n'
                  '    bool bindExactClient(phx34_exact::Registry &, OSObject *);\n')
    source = once(source, 'phx34_exact::Ticket ticket = {});',
                  'phx34_exact::Ticket ticket = {}, const void *exactClient = nullptr);')
    source = once(source, 'phx34_exact::Ticket ticket) {',
                  'phx34_exact::Ticket ticket, const void *exactClient) {')
    source = body(source, 'IOReturn PhxBringup::gpuSubmit(', lambda text: prepend(text,
                  '    if (exact && !exact->boundTo(this, exactClient)) return kIOReturnNotReady;\n'))
    source = once(source, 'const phx34_exact::CallbackGate<> &);\n',
                  'const phx34_exact::CallbackGate<> &, const void *);\n')
    source = once(source, 'const phx34_exact::CallbackGate<> &clientAdmission) {\n',
                  'const phx34_exact::CallbackGate<> &clientAdmission, const void *client) {\n')
    source = body(source, 'phx34_exact::Status PhxBringup::observeExact(', lambda text:
                  once(prepend(text, '    if (!registry.boundTo(this, client)) return phx34_exact::Status::Invalid;\n'),
                       '    // Caller holds the client lock and binds Registry lifetime to this provider.\n'
                       '    // That binding is still CPU-fixture-only, not authenticated native allocation.\n',
                       '    // Caller holds the client lock; immutable identity comes from staged start.\n'))
    source = body(source, 'bool IOAccelPhxNativeClient::start(', lambda text:
                  once(once(text, '    if (exactClientPinned) return false;\n',
                            '    if (exactClientPinned || (exactRequested && exactStartAttempted) || exactOwnership) return false;\n'
                            '    if (exactRequested) exactStartAttempted = true; // failed starts cannot rebind\n'),
                       '    if (started && exactOwnership) {\n'
                       '        // CPU fixture binding only, immutable and pre-start.\n'
                       '        retain(); // pin before exposing an exact-capable client\n'
                       '        owner->retain(); // provider outlives every retained client resource\n'
                       '        exactClientPinned = true;\n'
                       '    }\n',
                       '    if (started && exactRequested) {\n'
                       '        if (!owner->bindExactClient(exactRegistry, this)) return false;\n'
                       '        exactOwnership = &exactRegistry; // publish only after binding and both pins\n'
                       '        exactClientPinned = true;\n'
                       '    }\n'))
    for sig in ['IOReturn IOAccelPhxNativeClient::externalMethod(',
                'IOReturn IOAccelPhxNativeClient::clientMemoryForType(',
                'IOReturn IOAccelPhxNativeClient::doSubmit(']:
        source = body(source, sig, lambda text: once(text, ENTRY_GUARD,
                      '    phx34_exact::CallbackGate<>::Lease clientCallback(exactClientCallbacks);\n'
                      '    if ((exactRequested || exactOwnership) && (!(' + CLIENT_VALID +
                      ') || !clientCallback)) return kIOReturnNotReady;\n'))
    source = body(source, 'IOReturn IOAccelPhxNativeClient::doSubmit(', lambda text: once(text,
                  '&seq, exactOwnership, ticket);\n', '&seq, exactOwnership, ticket, this);\n'))
    source = body(source, 'IOReturn IOAccelPhxNativeClient::clientClose(', lambda text: once(text,
                  '    if (exactOwnership) {\n', '    if (exactRequested || exactOwnership) {\n'))
    source = body(source, 'phx34_exact::Status IOAccelPhxNativeClient::queryExact(', lambda text:
                  once(once(text, '    if (!exactOwnership || !exactClientPinned)',
                            '    if (!(' + CLIENT_VALID + '))'),
                       'owner->observeExact(*exactOwnership, ticket, exactClientCallbacks);',
                       'owner->observeExact(*exactOwnership, ticket, exactClientCallbacks, this);'))
    return once(source, 'bool IOAccelPhxNativeClient::start(IOService *provider) {\n',
                BIND_CLIENT + 'bool IOAccelPhxNativeClient::start(IOService *provider) {\n')
