"""Derive a mapper-qualified DMA page plan for an unused build34 display pin."""

import build34_dcn_scanout_pin_stage as pin
from build34_exact_submit import once
from test_build34_exact_ownership import method


MAP = 'IOReturn PhxBringup::mapDcnPin('
DMA_FIELDS = '''        build34::dcn::ScanoutDmaLease dma;
'''
MAPPER_GATE = '''    build34::dcn::ScanoutDmaMapper (*dcnQualifyMapper)(IOPCIDevice &, IOMapper &){nullptr};
    build34::dcn::DcnDirectDomain (*dcnQualifyDirect)(IOPCIDevice &){nullptr};
    IOReturn mapDcnPin(build34::dcn::ScanoutDmaRequest &, bool direct = false);
'''
CONSUME_DECL = '    bool checkDcnPresent(const build34::dcn::PresentCopyBacking &, DcnPinSlot * = nullptr);\n'
DMA_CONSUME = '''    bool checkDcnPresent(const build34::dcn::PresentCopyBacking &, DcnPinSlot * = nullptr,
        build34::dcn::ScanoutDmaRequest * = nullptr, const build34::dcn::ScanoutDmaMapper * = nullptr);
'''
DMA_PROBE_DECL = pin.PROBE_DECL.replace(' * = nullptr);', ' * = nullptr, build34::dcn::ScanoutDmaJob * = nullptr);')
DMA_OPERATIONS_DECL = pin.OPERATIONS_DECL.replace(' &);\n',
    ' &, build34::dcn::ScanoutDmaRequest * = nullptr, const build34::dcn::ScanoutDmaMapper * = nullptr);\n', 1)

MAP_METHOD = '''IOReturn PhxBringup::mapDcnPin(build34::dcn::ScanoutDmaRequest &request, bool direct) {
    using namespace build34::dcn;
    phx34_exact::CallbackGate<>::Lease callback(exactCallbacks);
    auto *device = pci;
    if (!callback || !device || device->isInactive() || (direct ? !dcnQualifyDirect : !dcnQualifyMapper))
        return kIOReturnNotReady;
    if (!request.present || !validScanoutDmaStorage(request, request.present->slice.bytes))
        return kIOReturnBadArgument;
    if (direct) {
        Phx34ScopedReference deviceLifetime(device);
        const ScanoutDmaMapper qualified{nullptr, nullptr, nullptr, dcnQualifyDirect(*device)};
        if (qualified.direct.device != device || !qualified.current() || exactCallbacks.closed() || pci != device)
            return kIOReturnNotReady;
        return prepareDcnPin(*request.present, request.token, &request, &qualified);
    }
    auto *mapper = IOMapper::copyMapperForDevice(device);
    if (!mapper) return kIOReturnNotReady;
    Phx34ScopedReference mapperLifetime(mapper, false);
    const auto current = [&] {
        return !exactCallbacks.closed() && pci == device && !device->isInactive() && !mapper->isInactive();
    };
    if (!current()) return kIOReturnNotReady;
    const auto qualified = dcnQualifyMapper(*device, *mapper);
    if (qualified.mapper != mapper || !qualified.completeContract() || !current()) return kIOReturnNotReady;
    return prepareDcnPin(*request.present, request.token, &request, &qualified);
}

'''


def stage_native(driver, abi):
    source = pin.stage_native(driver, abi)

    def replace(signature, old, new):
        nonlocal source
        before = method(source, signature)
        source = once(source, before, once(before, old, new))

    include = '#include "build34_dcn_scanout_pin.h"\n'
    source = once(source, include, include + '#include "build34_dcn_scanout_dma.h"\n')
    source = once(source, '        build34::dcn::ScanoutDescriptorPin descriptor;\n',
                  '        build34::dcn::ScanoutDescriptorPin descriptor;\n' + DMA_FIELDS)
    source = once(source, CONSUME_DECL, DMA_CONSUME + MAPPER_GATE)
    source = once(source, pin.OPERATIONS_DECL, DMA_OPERATIONS_DECL)
    source = once(source, pin.PROBE_DECL, DMA_PROBE_DECL)
    source = once(source, pin.PREPARE, MAP_METHOD + pin.PREPARE)
    replace(pin.PREPARE, 'build34::dcn::ScanoutPinToken &out) {',
            '''build34::dcn::ScanoutPinToken &out, build34::dcn::ScanoutDmaRequest *request,
    const build34::dcn::ScanoutDmaMapper *qualified) {''')
    replace(pin.PREPARE, '        if (!checkDcnPresent(present, &slot))',
            '        if (!checkDcnPresent(present, &slot, request, qualified))')
    replace(pin.CANCEL, '        const bool released = slot.descriptor.releaseUnused();',
            '        const bool released = slot.dma.releaseUnused(slot.descriptor) && slot.descriptor.releaseUnused();')
    consume = pin.handoff.CONSUME
    replace(consume, 'DcnPinSlot *slot) {', '''DcnPinSlot *slot,
    build34::dcn::ScanoutDmaRequest *request, const build34::dcn::ScanoutDmaMapper *qualified) {''')
    replace(consume, '''    const bool matched = taken.client->probeExactWriterBacking(taken.offer.native, taken.offer.range, present,
        slot ? &slot->descriptor : nullptr);
    if (slot && (matched || slot->descriptor.uncertain())) {''',
            '''    if (request && (!slot || !qualified)) return false;
    const bool matched = request ? [&] {
        build34::dcn::ScanoutDmaJob job{*qualified, slot->dma, *request};
        return taken.client->probeExactWriterBacking(taken.offer.native, taken.offer.range, present,
            &slot->descriptor, &job);
    }() : taken.client->probeExactWriterBacking(taken.offer.native, taken.offer.range, present,
        slot ? &slot->descriptor : nullptr);
    if (slot && (matched || slot->descriptor.uncertain() || slot->dma.uncertain())) {''')
    probe = pin.handoff.writer.PROBE
    replace(probe, 'build34::dcn::ScanoutDescriptorPin *pin) {',
            'build34::dcn::ScanoutDescriptorPin *pin, build34::dcn::ScanoutDmaJob *dma) {')
    replace(probe, '            const auto current = exactWriterMapLocked(span);\n',
            '''            const size_t runs = pinned && dma && live() ? dma->lease.prepareRuns(*pin, dma->qualified, present,
                dma->request.scratch, dma->request.runCapacity) : 0;
            const bool planned = runs && dma->lease.preparePlan(dma->request, span.bytes, runs);
            const auto current = exactWriterMapLocked(span);
''')
    replace(probe, '            same = pinned && live()', '            same = pinned && (!dma || planned) && live()')
    replace(probe, '                live() && livePresentPreparation(present.slice) == present.preparation;\n',
            '''                live() && livePresentPreparation(present.slice) == present.preparation;
            if (same && dma) same = dma->lease.publishPlan(dma->request, span.bytes, exactWriter, after);
''')
    replace(probe, '    if (pin && pin->held() && !same) (void)pin->releaseUnused();\n',
            '''    if (pin && pin->held() && !same && (!dma || dma->lease.releaseUnused(*pin)))
        (void)pin->releaseUnused();
''')
    anchor = '    if (name && name->isEqualTo(BUILD34_DCN_PIN_PREPARE)) {\n'
    replace(pin.handoff.DISPATCH, anchor, '''    if (name && name->isEqualTo(BUILD34_DCN_PIN_MAP)) {
        if (wait || !device || p2 || p3 || p4) return kIOReturnBadArgument;
        return mapDcnPin(*static_cast<build34::dcn::ScanoutDmaRequest *>(device));
    }
    if (name && name->isEqualTo(BUILD34_DCN_PIN_MAP_DIRECT)) {
        if (wait || !device || p2 || p3 || p4) return kIOReturnBadArgument;
        return mapDcnPin(*static_cast<build34::dcn::ScanoutDmaRequest *>(device), true);
    }
''' + anchor)
    return source
