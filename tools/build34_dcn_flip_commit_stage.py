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
VM_FREE = 'bool PhxBringup::vmidFree('
PERMISSION_CURRENT = 'PhxBringup::VmCtx *PhxBringup::dcnGpuPermissionCurrentLocked('
PERMISSION_TABLE = 'build34::dcn::DcnGpuPteTable PhxBringup::dcnGpuPermissionTable('
PERMISSION_CHANGE = 'bool PhxBringup::changeDcnGpuAccessLocked('
PERMISSION_RESTORE = 'build34::dcn::DcnRetirement PhxBringup::restoreDcnGpuAccessLocked('
SUBMIT_EPOCH = '        if (exact && !retried) admissionEpoch = exactInvalidationEpoch;\n'
SUBMIT_GATE = '''        if (!dcnManagedWrites.permissionsCurrent(exactInvalidationEpoch)) {
            IOLockUnlock(gpuLock);
            return kIOReturnNotReady;
        }
        if (dcnSubmitGate.held()) {
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
    uint64_t dcnGpuPermissionSerial{0};
    build34::dcn::DcnGpuPermissionAck (*dcnGpuPermissionEvidence)(PhxBringup &,
        const build34::dcn::DcnGpuPermissionUse &, build34::dcn::DcnGpuPermissionPhase){nullptr};
    VmCtx *dcnGpuPermissionCurrentLocked(build34::dcn::DcnGpuWriteOwner);
    static build34::dcn::DcnGpuPteTable dcnGpuPermissionTable(const VmCtx &, uint64_t);
    bool changeDcnGpuAccessLocked(build34::dcn::PhysicalPageSet, build34::dcn::DcnGpuWriteOwner, bool);
    build34::dcn::DcnRetirement restoreDcnGpuAccessLocked(build34::dcn::PhysicalPageSet);
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
FREE_SLOT_GATE = '        if (dcnManagedWrites.blocksSlot(i) || dcnManagedWrites.pinsSlot(i)) continue;\n'

PERMISSION_METHODS = '''PhxBringup::VmCtx *PhxBringup::dcnGpuPermissionCurrentLocked(build34::dcn::DcnGpuWriteOwner owner) {
    if (!owner.allocation || !owner.root || owner.slot >= kNumUserVmids || owner.epoch != exactInvalidationEpoch ||
        exactCallbacks.closed() || exactStopped || isSleeping || exactVMFault ||
        watchdogRecovery.active || watchdogRecovery.terminal) return nullptr;
    auto *context = vmCtx(owner.context);
    const auto &slot = hwv[owner.slot];
    return context && context->generation == owner.allocation && context->phys == owner.root &&
        context->hw == kFirstUserVmid + owner.slot && slot.ctx == owner.context && slot.generation == owner.allocation &&
        vmWorkCurrent(*context) ? context : nullptr;
}

build34::dcn::DcnGpuPteTable PhxBringup::dcnGpuPermissionTable(const VmCtx &context, uint64_t physical) {
    using namespace build34::dcn;
    static_assert(kPtChunks * kPtChunkPages <= 1024);
    for (uint32_t chunk = 0; chunk < kPtChunks && chunk * kPtChunkPages < context.used; ++chunk) {
        if (!context.chunk[chunk] || !context.chunkPhys[chunk] || (context.chunkPhys[chunk] & ~kPtAddrMask)) return {};
        const uint64_t offset = physical - context.chunkPhys[chunk];
        if (offset >= kPtChunkBytes) continue;
        auto *bytes = static_cast<uint8_t *>(context.chunk[chunk]->getBytesNoCopy());
        const auto length = context.chunk[chunk]->getLength();
        if (!bytes || offset % kPageBytes || length < kPageBytes || offset > length - kPageBytes) return {};
        return {reinterpret_cast<uint64_t *>(bytes + offset), chunk * kPtChunkPages + static_cast<uint32_t>(offset / kPageBytes)};
    }
    return {};
}

bool PhxBringup::changeDcnGpuAccessLocked(build34::dcn::PhysicalPageSet pages, build34::dcn::DcnGpuWriteOwner owner,
    bool restore) {
    using namespace build34::dcn;
    static_assert(kPteSysFlags & kGpuPteWrite);
    auto *context = dcnGpuPermissionCurrentLocked(owner);
    if (!context || !dcnGpuPermissionEvidence || dcnGpuPermissionSerial >= UINT64_MAX - 1 ||
        !context->used || context->used > context->pages || !pages.count) return false;
    const auto begin = restore ? DcnGpuPermissionPhase::CanRestore : DcnGpuPermissionPhase::CanRestrict;
    const auto finish = restore ? DcnGpuPermissionPhase::Restored : DcnGpuPermissionPhase::Restricted;
    const DcnGpuPermissionUse use{++dcnGpuPermissionSerial, owner, pages};
    const uint64_t started = mach_absolute_time();
    uint64_t previous = started;
    const auto inBudget = [&] {
        const uint64_t now = mach_absolute_time();
        if (now < previous) return false;
        previous = now;
        uint64_t elapsed = 0;
        absolutetime_to_nanoseconds(now - started, &elapsed);
        return elapsed < 10000000;
    };
    const auto resolve = [&](uint64_t physical) {
        return inBudget() ? dcnGpuPermissionTable(*context, physical) : DcnGpuPteTable{};
    };
    size_t expected = 0, changed = 0;
    if (!walkDcnGpuPtes(owner.root, context->used, kPtAddrMask, kPteSysFlags, resolve,
            [&](uint64_t word, uint64_t page) {
                if (!pages.contains(page)) return true;
                ++expected;
                return bool(word & kGpuPteWrite) != restore;
            }) || (!restore && !expected) || !inBudget() || !dcnGpuPermissionEvidence(*this, use, begin).matches(use, begin) ||
        !inBudget() || dcnGpuPermissionCurrentLocked(owner) != context || (!restore && !dcnManagedWrites.pinReadOnly(pages, owner)))
        return false;
    if (!walkDcnGpuPtes(owner.root, context->used, kPtAddrMask, kPteSysFlags, resolve,
            [&](uint64_t &word, uint64_t page) {
                if (!pages.contains(page)) return true;
                if (bool(word & kGpuPteWrite) == restore) return false;
                word ^= kGpuPteWrite;
                flushLine(&word);
                ++changed;
                return true;
            }) || changed != expected) {
        exactVMFault = true;
        return false;
    }
    __asm__ __volatile__("mfence" ::: "memory");
    if (!inBudget() || !dcnGpuPermissionEvidence(*this, use, finish).matches(use, finish) || !inBudget() ||
        dcnGpuPermissionCurrentLocked(owner) != context ||
        (!restore && !dcnManagedWrites.setReadOnlyAccess(pages, true))) {
        exactVMFault = true;
        return false;
    }
    return true;
}

build34::dcn::DcnRetirement PhxBringup::restoreDcnGpuAccessLocked(build34::dcn::PhysicalPageSet pages) {
    using namespace build34::dcn;
    const auto owner = dcnManagedWrites.readOnly(pages);
    if (!owner.context) return DcnRetirement::Complete;
    const auto *context = dcnGpuPermissionCurrentLocked(owner);
    uint64_t retired = 0;
    if (!context || !dcnManagedWrites.setReadOnlyAccess(pages, false) || !exactGlobalRetiredLocked(retired))
        return DcnRetirement::Lost;
    if (retired < context->newest) return DcnRetirement::Pending;
    return changeDcnGpuAccessLocked(pages, owner, true) ? DcnRetirement::Complete : DcnRetirement::Lost;
}

'''

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
            if (__atomic_load_n(&slot.serial, __ATOMIC_ACQUIRE) == token.serial && slot.client && slot.dmaSurface.mappedBytes) return &slot;
    }
    return nullptr;
}

build34::dcn::ScanoutFlipBinding PhxBringup::dcnFlipBinding(DcnPinSlot *slot) {
    if (!slot) return {};
    return {{this, __atomic_load_n(&slot->serial, __ATOMIC_ACQUIRE)}, &slot->descriptor, &slot->dma, slot->dmaWindow, slot->dmaSurface};
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
            const auto pages = next->dma.physicalPages();
            if (restoreDcnGpuAccessLocked(pages) != DcnRetirement::Complete) exactVMFault = true;
            dcnManagedWrites.release(pages);
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
            if (!IOLockTryLock(gpuLock)) return DcnRetirement::Pending;
            const auto state = restoreDcnGpuAccessLocked(retired);
            IOLockUnlock(gpuLock);
            return state;
        },
        [&](PhysicalPageSet retired) {
            IOLockLock(gpuLock);
            dcnManagedWrites.release(retired);
            IOLockUnlock(gpuLock);
        });
    if (old) IOLockUnlock(old->client->lock);
    if (old && result == ScanoutFlipResult::Presented) {
        auto *surface = old->surface;
        auto *client = old->client;
        __atomic_store_n(&old->serial, uint64_t{0}, __ATOMIC_RELEASE);
        __atomic_store_n(&old->cancelPending, uint64_t{0}, __ATOMIC_RELEASE);
        old->dmaWindow = 0;
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
                  '#include "build34_dcn_gpu_write_history.h"\n#include "build34_dcn_gpu_permissions.h"\n')
    source = once(source, dma.DMA_FIELDS, dma.DMA_FIELDS + SLOT)
    source = once(source, dma.MAPPER_GATE, dma.MAPPER_GATE + FIELDS)
    source = once(source, dma.pin.RELEASE_PIN_RESET,
                  dma.pin.RELEASE_PIN_RESET + '        slot.dmaWindow = 0;\n        slot.dmaSurface = {};\n')
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
        if (current && dcnGpuPermissionEvidence) {
            if (context->hw < kFirstUserVmid || context->hw >= kFirstUserVmid + kNumUserVmids) current = false;
            else current = changeDcnGpuAccessLocked(pages, {mapping.vmAllocation, context->phys, exactInvalidationEpoch,
                mapping.vmContext, context->hw - kFirstUserVmid}, false);
        }
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
    if (!dcnManagedWrites.permissionsCurrent(exactInvalidationEpoch) || dcnManagedWrites.blocksContext(handle)) return 0;
    VmCtx &c = *context;
''')
    replace(VM_BIND, '        hwv[c.hw - kFirstUserVmid].lastUse = now;\n',
            BOUND_SLOT_GATE + '        hwv[c.hw - kFirstUserVmid].lastUse = now;\n')
    replace(VM_BIND, '        if (!hwv[i].ctx)', FREE_SLOT_GATE + '        if (!hwv[i].ctx)')
    replace(VM_BIND, '    wreg(kRegCtx0BaseLo + 2 * vmid,',
            '    dcnGpuWrites.bound(handle, static_cast<uint32_t>(pick));\n    wreg(kRegCtx0BaseLo + 2 * vmid,')
    replace(VM_FREE, '        VmCtx &c = *context;\n', '''        if (dcnManagedWrites.pinsContext(handle)) {
            IOLockUnlock(gpuLock);
            return false;
        }
        VmCtx &c = *context;
''')
    submit_anchor = '        // Re-select and validate under the lock after every sleep: adoption,\n'
    replace(SUBMIT, SUBMIT_EPOCH, '')
    replace(SUBMIT, submit_anchor, SUBMIT_EPOCH + SUBMIT_GATE + submit_anchor)
    source = once(source, dma.MAP_METHOD, PERMISSION_METHODS + METHODS + dma.MAP_METHOD)
    replace(dma.pin.PREPARE, '    for (auto &slot : dcnPins) {\n        if (slot.client || slot.descriptor.held() || slot.descriptor.uncertain()) continue;\n', '''    const auto surface = request ? present.scanout : build34::dcn::ScanoutSurface{};
    if (request && (!build34::dcn::validFlipGeometry(surface) || surface.mappedBytes != present.slice.bytes))
        return kIOReturnBadArgument;
    for (auto &slot : dcnPins) {
        if (slot.client || slot.descriptor.held() || slot.descriptor.uncertain()) continue;
''')
    replace(dma.pin.PREPARE, '        __atomic_store_n(&slot.serial, serial, __ATOMIC_RELEASE);\n',
            '        __atomic_store_n(&slot.serial, serial, __ATOMIC_RELEASE);\n'
            '        slot.dmaWindow = request ? request->windowStart : 0;\n'
            '        slot.dmaSurface = surface;\n')
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
