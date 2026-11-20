#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Stage exact-client admission and conservative resource retention, CPU only.

The Registry pointer is still supplied only by CPU fixtures, before start.
Successful start pins client/provider before admitting any exact operation.
There is deliberately no unpin/reclaim protocol and no deployable candidate.
"""
from build34_exact_callbacks import stage as stage_callbacks
from build34_exact_submit import once


ENTRY_GUARD = ('    phx34_exact::CallbackGate<>::Lease clientCallback(exactClientCallbacks);\n'
               '    if (exactOwnership && (!exactClientPinned || !clientCallback)) return kIOReturnNotReady;\n')
LOCK_RECHECK = ('    if (exactOwnership && exactClientCallbacks.closed()) {\n'
                '        IOLockUnlock(lock);\n        return kIOReturnNotReady;\n    }\n')


def body(source, signature, transform):
    start = source.index(signature)
    end = source.index('\n}\n', start) + 3
    old = source[start:end]
    return once(source, old, transform(old))


def prepend(text, addition):
    brace = text.index('{\n') + 2
    return text[:brace] + addition + text[brace:]


def stage(source):
    source = stage_callbacks(source)
    source = once(source, '    phx34_exact::Registry *exactOwnership{nullptr};\n',
                  '    phx34_exact::Registry *exactOwnership{nullptr};\n'
                  '    phx34_exact::CallbackGate<> exactClientCallbacks;\n'
                  '    bool exactClientPinned{false}, exactResourcesExposed{false};\n')
    source = body(source, 'bool IOAccelPhxNativeClient::start(', lambda text:
                  once(prepend(text, '    if (exactClientPinned) return false;\n'),
                       '    return IOUserClient::start(provider);\n',
                       '    const bool started = IOUserClient::start(provider);\n'
                       '    if (started && exactOwnership) {\n'
                       '        // CPU fixture binding only, immutable and pre-start.\n'
                       '        retain(); // pin before exposing an exact-capable client\n'
                       '        owner->retain(); // provider outlives every retained client resource\n'
                       '        exactClientPinned = true;\n'
                       '    }\n    return started;\n'))
    for sig in ['IOReturn IOAccelPhxNativeClient::externalMethod(',
                'IOReturn IOAccelPhxNativeClient::clientMemoryForType(',
                'IOReturn IOAccelPhxNativeClient::doSubmit(']:
        source = body(source, sig, lambda text: prepend(text, ENTRY_GUARD))
    for sig in ['IOReturn IOAccelPhxNativeClient::externalMethod(',
                'IOReturn IOAccelPhxNativeClient::clientMemoryForType(']:
        source = body(source, sig, lambda text: once(text, '    IOLockLock(lock);\n',
                                                    '    IOLockLock(lock);\n' + LOCK_RECHECK))
    source = body(source, 'IOReturn IOAccelPhxNativeClient::clientClose(', lambda text: prepend(text,
                  '    if (exactOwnership) {\n'
                  '        if (!exactClientPinned) return kIOReturnNotReady;\n'
                  '        exactClientCallbacks.close();\n'
                  '        // Keep Registry writable for a submit admitted BEFORE close.\n'
                  '        return kIOReturnSuccess; // quarantine; no drain/terminate/unpin\n'
                  '    }\n'))
    # free() is not a valid place to resurrect an OSObject. The start-time pin
    # must prevent native finalization; this guard is only defense in depth.
    source = body(source, 'void IOAccelPhxNativeClient::free(', lambda text: prepend(text,
                  '    if (exactClientPinned) return; // no late retain/resurrection in free\n'))
    source = body(source, 'void IOAccelPhxNativeClient::freeAll(', lambda text: prepend(text,
                  '    if (exactClientPinned) return; // only a future proved drain may unpin\n'))
    source = body(source, 'void IOAccelPhxNativeClient::boRelease(', lambda text: prepend(text,
                  '    if (exactClientPinned && exactResourcesExposed) return;\n'))
    source = once(source, '        phx34_exact::Ticket ticket;\n',
                  '        if (exactOwnership) exactResourcesExposed = true; // sticky BEFORE fallible GPU admission\n'
                  '        phx34_exact::Ticket ticket;\n')
    source = body(source, 'IOReturn IOAccelPhxNativeClient::doBoFree(', lambda text:
                  once(text, '    for (int i = 0; i < kMaxMaps; i++)\n',
                       '    if (exactClientPinned && exactResourcesExposed) return kIOReturnBusy;\n'
                       '    for (int i = 0; i < kMaxMaps; i++)\n'))
    source = body(source, 'IOReturn IOAccelPhxNativeClient::doGemVa(', lambda text:
                  once(text, '    for (int i = 0; i < kMaxMaps; i++) {\n        if (maps[i].used &&',
                       '    if (exactClientPinned && exactResourcesExposed) return kIOReturnBusy;\n'
                       '    for (int i = 0; i < kMaxMaps; i++) {\n        if (maps[i].used &&'))
    return source
