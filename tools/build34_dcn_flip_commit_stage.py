"""Stage scanout-pin transfer across a qualified build34 display flip."""

import build34_dcn_scanout_dma_stage as dma
from build34_exact_binding import CLIENT_VALID
from build34_exact_submit import once
from test_build34_exact_ownership import method


BEGIN = 'IOReturn PhxBringup::beginDcnFlip('
POLL = 'IOReturn PhxBringup::pollDcnFlip('
LOOKUP = 'PhxBringup::DcnPinSlot *PhxBringup::findDcnFlipPin('
BIND = 'build34::dcn::ScanoutFlipBinding PhxBringup::dcnFlipBinding('
WRITER_CURRENT = 'bool IOAccelPhxNativeClient::dcnScanoutWriterCurrent('
SUBMIT = 'IOReturn PhxBringup::gpuSubmit('
MAP = 'IOReturn PhxBringup::vmMap('
VM_BIND = 'uint32_t PhxBringup::vmBind('
SUBMIT_EPOCH = '        if (exact && !retried) admissionEpoch = exactInvalidationEpoch;\n'
SUBMIT_GATE = '''        if (dcnSubmitGate.held()) {
            IOLockUnlock(gpuLock);
            uint64_t elapsed = 0;
            absolutetime_to_nanoseconds(mach_absolute_time() - start, &elapsed);
            if (elapsed >= 2000000000ull) return kIOReturnBusy;
            IOSleep(1);
            continue;
        }
        if (dcnManagedWrites.blocksContext(handle)) {
            IOLockUnlock(gpuLock);
            return kIOReturnBusy;
        }
'''
DRAIN_DECL = once(dma.pin.handoff.DRAIN_DECL, 'DcnDrainStamp * = nullptr);', '''DcnDrainStamp * = nullptr,
        build34::dcn::DcnSubmitGate::Lease * = nullptr, const DcnDrainStamp * = nullptr,
        const build34::dcn::ScanoutDmaLease * = nullptr);''')
CLIENT = '''    bool dcnScanoutWriterCurrent(const build34::dcn::ScanoutDescriptorPin &,
        const build34::dcn::ScanoutDmaLease &, build34::dcn::DcnSubmitGate::Lease *);
'''
FIELDS = '''    build34::dcn::DcnSubmitGate dcnSubmitGate;
    build34::dcn::DcnManagedWriteHolds dcnManagedWrites;
    build34::dcn::DcnGpuWriteHistory<> dcnGpuWrites;
    bool (*dcnProveGpuVmOwnership)(const PhxBringup &, build34::dcn::PhysicalPageSet){nullptr};
    build34::dcn::ScanoutFlipCommit dcnFlip;
    const build34::dcn::HubpFlipRoute *(*dcnQualifiedFlipRoute)(IOPCIDevice *){nullptr};
    DcnPinSlot *findDcnFlipPin(build34::dcn::ScanoutPinToken);
    build34::dcn::ScanoutFlipBinding dcnFlipBinding(DcnPinSlot *);
    IOReturn beginDcnFlip(build34::dcn::ScanoutFlipIntent &);
    IOReturn pollDcnFlip(build34::dcn::ScanoutFlipPoll &);
'''
SLOT = '''        uint64_t dmaWindow{0};
        build34::dcn::ScanoutSurface dmaSurface{};
'''
MAP_PREFLIGHT = '''    if (dcnManagedWrites.active()) {
        for (uint64_t offset = 0; offset < size; offset += 4096) {
            IOByteCount contiguous = 0;
            const auto physical = md->getPhysicalSegment(off + offset, &contiguous, kIOMemoryMapperNone);
            if (!physical || (physical & ~kPtAddrMask) || contiguous < 4096 || dcnManagedWrites.excludes(physical)) {
                IOLockUnlock(gpuLock);
                return kIOReturnBusy;
            }
        }
    }
'''
MAP_PAGE_GATE = '''        if (validPage && dcnManagedWrites.excludes(pa)) {
            r = kIOReturnVMError;
            break;
        }
'''
MAP_RECORD = '        dcnGpuWrites.mapped(handle, pa);\n'
BOUND_SLOT_GATE = '        if (dcnManagedWrites.blocksSlot(c.hw - kFirstUserVmid)) return 0;\n'
FREE_SLOT_GATE = '        if (dcnManagedWrites.blocksSlot(i)) continue;\n'

METHODS = '''bool IOAccelPhxNativeClient::dcnScanoutWriterCurrent(const build34::dcn::ScanoutDescriptorPin &pin,
    const build34::dcn::ScanoutDmaLease &dma, build34::dcn::DcnSubmitGate::Lease *reserve) {
    using namespace build34::dcn;
    phx34_exact::CallbackGate<>::Lease callback(exactClientCallbacks);
    if (!callback || !lock || __atomic_load_n(&legacyState, __ATOMIC_ACQUIRE) != 2 || !IOLockTryLock(lock))
        return false;
    const auto &proof = dma.writerProof();
    const auto &native = proof.writer.native;
    const auto live = [&] {
        return owner && (''' + CLIENT_VALID + ''') && !exactClientCallbacks.closed() && !owner->exactAdmissionClosed() &&
            exactWriter.complete && native.context && native.context <= PHXN_MAX_CTX && ctx[native.context];
    };
    const bool current = live() && [&] {
        const auto mapping = exactWriterMapLocked(proof.writer.range);
        PhxBringup::DcnDrainStamp drain{};
        return proof.writer.complete && exactWriter.matches(native, proof.writer.range, mapping.identity) &&
            proof.writer.map.matches(mapping.identity) && dma.matchesWriterBacking(pin, mapping) &&
            owner->exactWriterVmCurrent(mapping.identity, native, this, &drain, reserve, &proof.drain, &dma) && live();
    }();
    IOLockUnlock(lock);
    return current;
}

PhxBringup::DcnPinSlot *PhxBringup::findDcnFlipPin(build34::dcn::ScanoutPinToken token) {
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
    if (!route || !route->framebuffer || route->framebuffer->isInactive() ||
        route->framebuffer->getProvider() != pci || !route->framebuffer->metaCast("PhxAMDFB") ||
        !gDcnPinSerials.take(serial)) return kIOReturnNotReady;
    const ScanoutPinToken token{this, serial};
    DcnSubmitGate::Lease programming;
    const auto result = dcnFlip.begin(intent, token, *route, pci, dcnFlipBinding(old), dcnFlipBinding(next),
        [&] { return !exactCallbacks.closed(); },
        [&](bool reserve) {
            if (!next) return false;
            if (!programming.held())
                return next->client->dcnScanoutWriterCurrent(next->descriptor, next->dma, reserve ? &programming : nullptr);
            const auto &proof = next->dma.writerProof();
            DcnDrainStamp drain{};
            return !reserve && !next->client->exactClientCallbacks.closed() &&
                exactWriterVmCurrent(proof.writer.map, proof.writer.native, next->client, &drain, nullptr, &proof.drain) &&
                !next->client->exactClientCallbacks.closed();
        });
    if (result == ScanoutFlipResult::Refused) {
        if (programming.held()) {
            IOLockLock(gpuLock);
            dcnManagedWrites.release(next->dma.physicalPages());
            IOLockUnlock(gpuLock);
        }
        return kIOReturnNotReady;
    }
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
    IOService *framebuffer = nullptr;
    const auto result = dcnFlip.poll(poll.operation, [&] { return !exactCallbacks.closed(); }, route, framebuffer,
        [&](PhysicalPageSet retired) {
            IOLockLock(gpuLock);
            dcnManagedWrites.release(retired);
            IOLockUnlock(gpuLock);
        });
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
    if (framebuffer) framebuffer->release();
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
    source = once(source, include, include + '#include "build34_dcn_flip_commit.h"\n'
                  '#include "build34_dcn_gpu_write_history.h"\n')
    source = once(source, dma.DMA_FIELDS, dma.DMA_FIELDS + SLOT)
    source = once(source, dma.MAPPER_GATE, dma.MAPPER_GATE + FIELDS)
    source = once(source, dma.DMA_PROBE_DECL, dma.DMA_PROBE_DECL + CLIENT)
    source = once(source, dma.pin.handoff.DRAIN_DECL, DRAIN_DECL)
    writer = dma.pin.handoff.writer.CURRENT
    replace(writer, 'DcnDrainStamp *drain) {', '''DcnDrainStamp *drain,
    build34::dcn::DcnSubmitGate::Lease *reserve, const DcnDrainStamp *expected, const build34::dcn::ScanoutDmaLease *dma) {''')
    replace(writer, '    IOLockUnlock(gpuLock);\n', '''    if (current && expected) current = drain && drain->matches(*expected);
    if (current && reserve) {
        const auto pages = dma ? dma->physicalPages() : build34::dcn::PhysicalPageSet{};
        build34::dcn::DcnManagedWriteExclusion blocked{};
        current = expected && dcnProveGpuVmOwnership && dcnGpuWrites.exclusion(pages, blocked) &&
            dcnProveGpuVmOwnership(*this, pages) && !exactCallbacks.closed() &&
            reserve->reserve(dcnSubmitGate) && dcnManagedWrites.acquire(pages, blocked);
    }
    IOLockUnlock(gpuLock);
''')
    replace(MAP, '    for (uint64_t p = 0; p < size; p += 4096) {\n',
            MAP_PREFLIGHT + '    for (uint64_t p = 0; p < size; p += 4096) {\n')
    replace(MAP, '        uint64_t *pte = validPage ? vmPte(c, va + p, true) : nullptr;\n',
            MAP_PAGE_GATE + '        uint64_t *pte = validPage ? vmPte(c, va + p, true) : nullptr;\n')
    replace(MAP, '        *pte = (pa & kPtAddrMask) | kPteSysFlags;\n',
            MAP_RECORD + '        *pte = (pa & kPtAddrMask) | kPteSysFlags;\n')
    replace(VM_BIND, '    VmCtx &c = *context;\n', '''    static_assert(kMaxCtx <= build34::dcn::DcnManagedWriteExclusion::kContexts);
    static_assert(kNumUserVmids <= build34::dcn::DcnManagedWriteExclusion::kVmidSlots);
    if (dcnManagedWrites.blocksContext(handle)) return 0;
    VmCtx &c = *context;
''')
    replace(VM_BIND, '        hwv[c.hw - kFirstUserVmid].lastUse = now;\n',
            BOUND_SLOT_GATE + '        hwv[c.hw - kFirstUserVmid].lastUse = now;\n')
    replace(VM_BIND, '        if (!hwv[i].ctx)', FREE_SLOT_GATE + '        if (!hwv[i].ctx)')
    replace(VM_BIND, '    wreg(kRegCtx0BaseLo + 2 * vmid,',
            '    dcnGpuWrites.bound(handle, static_cast<uint32_t>(pick));\n    wreg(kRegCtx0BaseLo + 2 * vmid,')
    submit_anchor = '        // Re-select and validate under the lock after every sleep: adoption,\n'
    replace(SUBMIT, SUBMIT_EPOCH, '')
    replace(SUBMIT, submit_anchor, SUBMIT_EPOCH + SUBMIT_GATE + submit_anchor)
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
