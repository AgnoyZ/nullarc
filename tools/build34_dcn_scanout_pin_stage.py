"""Stage the pre-programming scanout pin on the exact build34 present path."""

import build34_dcn_present_handoff_stage as handoff
from build34_exact_submit import once
from test_build34_exact_ownership import method


PREPARE = 'IOReturn PhxBringup::prepareDcnPin('
CANCEL = 'IOReturn PhxBringup::cancelDcnPin('
OPERATIONS_DECL = '''    IOReturn prepareDcnPin(const build34::dcn::PresentCopyBacking &, build34::dcn::ScanoutPinToken &);
    IOReturn cancelDcnPin(build34::dcn::ScanoutPinToken);
'''
FIELDS = '''    struct DcnPinSlot {
        build34::dcn::ScanoutDescriptorPin descriptor;
        IOAccelPhxNativeClient *client{nullptr};
        OSObject *surface{nullptr};
        uint64_t serial{0};
    } dcnPins[2];
    phx34_exact::CallbackGate<1> dcnPinOperation;
    bool checkDcnPresent(const build34::dcn::PresentCopyBacking &, DcnPinSlot * = nullptr);
'''
PROBE_DECL = '''    bool probeExactWriterBacking(build34_dcn_native_submit, build34_dcn_writer_range,
        const build34::dcn::PresentCopyBacking &, build34::dcn::ScanoutDescriptorPin * = nullptr);
'''
OPERATIONS = '''static phx34_exact::OwnerEpochs gDcnPinSerials;

IOReturn PhxBringup::prepareDcnPin(const build34::dcn::PresentCopyBacking &present,
    build34::dcn::ScanoutPinToken &out) {
    phx34_exact::CallbackGate<1>::Lease operation(dcnPinOperation);
    if (!operation) return kIOReturnBusy;
    for (auto &slot : dcnPins) {
        if (slot.client || slot.descriptor.held() || slot.descriptor.uncertain()) continue;
        uint64_t serial = 0;
        if (!gDcnPinSerials.take(serial)) return kIOReturnNoResources;
        if (!checkDcnPresent(present, &slot)) return kIOReturnNotReady;
        slot.serial = serial;
        out = {this, slot.serial};
        return kIOReturnSuccess;
    }
    return kIOReturnNoResources;
}

IOReturn PhxBringup::cancelDcnPin(build34::dcn::ScanoutPinToken token) {
    if (token.provider != this || !token.serial) return kIOReturnBadArgument;
    phx34_exact::CallbackGate<1>::Lease operation(dcnPinOperation);
    if (!operation) return kIOReturnBusy;
    for (auto &slot : dcnPins) {
        if (slot.serial != token.serial || !slot.client || !slot.descriptor.cancellable()) continue;
        auto *client = slot.client;
        if (!IOLockTryLock(client->lock)) return kIOReturnBusy;
        const bool released = slot.descriptor.releaseUnused();
        IOLockUnlock(client->lock);
        slot.serial = 0;
        if (!released) return kIOReturnNotReady;
        auto *surface = slot.surface;
        slot.surface = nullptr;
        slot.client = nullptr;
        surface->release();
        client->release();
        return kIOReturnSuccess;
    }
    return kIOReturnNotFound;
}

'''


def stage_native(driver, abi):
    source = handoff.stage_native(driver, abi)

    def replace(signature, old, new):
        nonlocal source
        before = method(source, signature)
        source = once(source, before, once(before, old, new))

    include = '#include "build34_dcn_present_route.h"\n'
    source = once(source, include, include + '#include "build34_dcn_scanout_pin.h"\n')
    declaration = '    bool checkDcnPresent(const build34::dcn::PresentCopyBacking &);\n'
    source = once(source, declaration, FIELDS + OPERATIONS_DECL)
    source = once(source, handoff.writer.PROBE_DECL, PROBE_DECL)
    anchor = '    if (name && name->isEqualTo(BUILD34_DCN_PRESENT_PROBE)) {\n'
    replace(handoff.DISPATCH, anchor, '''    if (name && name->isEqualTo(BUILD34_DCN_PIN_PREPARE)) {
        if (wait || !device || !p2 || p3 || p4) return kIOReturnBadArgument;
        return prepareDcnPin(*static_cast<const build34::dcn::PresentCopyBacking *>(device),
            *static_cast<build34::dcn::ScanoutPinToken *>(p2));
    }
    if (name && name->isEqualTo(BUILD34_DCN_PIN_CANCEL)) {
        if (wait || !device || p2 || p3 || p4) return kIOReturnBadArgument;
        return cancelDcnPin(*static_cast<const build34::dcn::ScanoutPinToken *>(device));
    }
''' + anchor)
    replace(handoff.CONSUME, 'const build34::dcn::PresentCopyBacking &present) {',
            'const build34::dcn::PresentCopyBacking &present, DcnPinSlot *slot) {')
    replace(handoff.CONSUME,
            '    return taken.client && taken.client->probeExactWriterBacking(taken.offer.native, taken.offer.range, present);\n',
            '''    if (!taken.client) return false;
    const bool matched = taken.client->probeExactWriterBacking(taken.offer.native, taken.offer.range, present,
        slot ? &slot->descriptor : nullptr);
    if (slot && (matched || slot->descriptor.uncertain())) {
        taken.client->retain();
        taken.surface->retain();
        slot->client = taken.client;
        slot->surface = taken.surface;
    }
    return matched;
''')
    probe = handoff.writer.PROBE
    replace(probe, 'const build34::dcn::PresentCopyBacking &present) {',
            'const build34::dcn::PresentCopyBacking &present, build34::dcn::ScanoutDescriptorPin *pin) {')
    replace(probe, '            const auto current = exactWriterMapLocked(span);\n'
                   '            same = live() && mapping.slice.descriptor == current.slice.descriptor &&',
            '            const bool pinned = !pin || (live() && pin->acquire(mapping.slice, mapping.identity.preparation));\n'
            '            const auto current = exactWriterMapLocked(span);\n'
            '            same = pinned && live() && mapping.slice.descriptor == current.slice.descriptor &&')
    replace(probe, '    IOLockUnlock(lock);\n',
            '    if (pin && pin->held() && !same) (void)pin->releaseUnused();\n    IOLockUnlock(lock);\n')
    anchor = handoff.CLIENT_MATCH
    return once(source, anchor, OPERATIONS + anchor)
