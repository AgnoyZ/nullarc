"""Stage scanout-pin transfer across a qualified build34 display flip."""

import build34_dcn_scanout_dma_stage as dma
from build34_exact_submit import once
from test_build34_exact_ownership import method


BEGIN = 'IOReturn PhxBringup::beginDcnFlip('
POLL = 'IOReturn PhxBringup::pollDcnFlip('
LOOKUP = 'PhxBringup::DcnPinSlot *PhxBringup::findDcnFlipPin('
BIND = 'build34::dcn::ScanoutFlipBinding PhxBringup::dcnFlipBinding('
FIELDS = '''    build34::dcn::ScanoutFlipCommit dcnFlip;
    const build34::dcn::HubpFlipRoute *(*dcnQualifiedFlipRoute)(IOPCIDevice *){nullptr};
    DcnPinSlot *findDcnFlipPin(build34::dcn::ScanoutPinToken);
    build34::dcn::ScanoutFlipBinding dcnFlipBinding(DcnPinSlot *);
    IOReturn beginDcnFlip(build34::dcn::ScanoutFlipIntent &);
    IOReturn pollDcnFlip(build34::dcn::ScanoutFlipPoll &);
'''
SLOT = '''        uint64_t dmaWindow{0};
        build34::dcn::ScanoutSurface dmaSurface{};
'''

METHODS = '''PhxBringup::DcnPinSlot *PhxBringup::findDcnFlipPin(build34::dcn::ScanoutPinToken token) {
    if (token.provider == this && token.serial) {
        for (auto &slot : dcnPins)
            if (slot.serial == token.serial && slot.client && slot.dmaSurface.mappedBytes) return &slot;
    }
    return nullptr;
}

build34::dcn::ScanoutFlipBinding PhxBringup::dcnFlipBinding(DcnPinSlot *slot) {
    if (!slot) return {};
    return {{this, slot->serial}, &slot->descriptor, &slot->dma, slot->dmaWindow, slot->dmaSurface};
}

IOReturn PhxBringup::beginDcnFlip(build34::dcn::ScanoutFlipIntent &intent) {
    using namespace build34::dcn;
    phx34_exact::CallbackGate<>::Lease callback(exactCallbacks);
    if (!callback || !pci || !dcnQualifiedFlipRoute) return kIOReturnNotReady;
    phx34_exact::CallbackGate<1>::Lease operation(dcnPinOperation);
    if (!operation || dcnFlip.pending()) return kIOReturnBusy;
    const auto current = dcnFlip.front();
    auto *old = findDcnFlipPin(current);
    auto *next = findDcnFlipPin(intent.nextPin);
    if ((current.serial && !old) || ((intent.nextPin.provider || intent.nextPin.serial) && !next) || (!old && !next))
        return kIOReturnNotFound;
    auto *route = dcnQualifiedFlipRoute(pci);
    uint64_t serial = 0;
    if (!route || !gDcnPinSerials.take(serial)) return kIOReturnNotReady;
    const ScanoutPinToken token{this, serial};
    const auto result = dcnFlip.begin(intent, token, *route, dcnFlipBinding(old), dcnFlipBinding(next),
        [&] { return !exactCallbacks.closed(); });
    if (result == ScanoutFlipResult::Refused) return kIOReturnNotReady;
    intent.operation = token;
    intent.result = result;
    return kIOReturnSuccess;
}

IOReturn PhxBringup::pollDcnFlip(build34::dcn::ScanoutFlipPoll &poll) {
    using namespace build34::dcn;
    phx34_exact::CallbackGate<>::Lease callback(exactCallbacks);
    if (!callback) return kIOReturnNotReady;
    phx34_exact::CallbackGate<1>::Lease operation(dcnPinOperation);
    if (!operation) return kIOReturnBusy;
    if (!dcnFlip.matches(poll.operation)) return kIOReturnNotFound;
    const auto current = dcnFlip.front();
    auto *old = findDcnFlipPin(current);
    if (current.serial && !old) return kIOReturnNotReady;
    if (old && !IOLockTryLock(old->client->lock)) return kIOReturnBusy;
    OSObject *route = nullptr;
    const auto result = dcnFlip.poll(poll.operation, [&] { return !exactCallbacks.closed(); }, route);
    if (old) IOLockUnlock(old->client->lock);
    if (old && result == ScanoutFlipResult::Presented) {
        auto *surface = old->surface;
        auto *client = old->client;
        old->serial = old->dmaWindow = 0;
        old->dmaSurface = {};
        old->surface = nullptr;
        old->client = nullptr;
        surface->release();
        client->release();
    }
    if (route) route->release();
    poll.result = result;
    return kIOReturnSuccess;
}

'''


def stage_native(driver, abi):
    source = dma.stage_native(driver, abi)

    def replace(signature, old, new):
        nonlocal source
        before = method(source, signature)
        source = once(source, before, once(before, old, new))

    include = '#include "build34_dcn_scanout_dma.h"\n'
    source = once(source, include, include + '#include "build34_dcn_flip_commit.h"\n')
    source = once(source, dma.DMA_FIELDS, dma.DMA_FIELDS + SLOT)
    source = once(source, dma.MAPPER_GATE, dma.MAPPER_GATE + FIELDS)
    source = once(source, dma.MAP_METHOD, METHODS + dma.MAP_METHOD)
    replace(dma.pin.PREPARE, '    for (auto &slot : dcnPins) {\n', '''    const auto surface = request ? present.scanout : build34::dcn::ScanoutSurface{};
    if (request && (!build34::dcn::validFlipGeometry(surface) || surface.mappedBytes != present.slice.bytes))
        return kIOReturnBadArgument;
    for (auto &slot : dcnPins) {
''')
    replace(dma.pin.PREPARE, '        slot.serial = serial;\n', '''        slot.serial = serial;
        slot.dmaWindow = request ? request->windowStart : 0;
        slot.dmaSurface = surface;
''')
    replace(dma.pin.CANCEL, '        slot.serial = 0;\n', '''        slot.serial = slot.dmaWindow = 0;
        slot.dmaSurface = {};
''')
    anchor = '    if (name && name->isEqualTo(BUILD34_DCN_PIN_MAP)) {\n'
    replace(dma.pin.handoff.DISPATCH, anchor, '''    if (name && name->isEqualTo(BUILD34_DCN_FLIP_BEGIN)) {
        if (wait || !device || p2 || p3 || p4) return kIOReturnBadArgument;
        return beginDcnFlip(*static_cast<build34::dcn::ScanoutFlipIntent *>(device));
    }
    if (name && name->isEqualTo(BUILD34_DCN_FLIP_POLL)) {
        if (wait || !device || p2 || p3 || p4) return kIOReturnBadArgument;
        return pollDcnFlip(*static_cast<build34::dcn::ScanoutFlipPoll *>(device));
    }
''' + anchor)
    return source
