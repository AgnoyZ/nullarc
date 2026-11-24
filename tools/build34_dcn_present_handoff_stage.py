"""Connect the exact native writer to the real R2a transaction without changing scanout."""

import build34_dcn_exact_writer_stage as writer
import build34_dcn_present_backing_stage as backing
from build34_exact_binding import CLIENT_VALID
from build34_exact_submit import once
from test_build34_exact_ownership import method


OFFER = 'IOReturn IOAccelPhxNativeClient::doDcnPresentOffer('
ATTACH = 'bool PhxBringup::offerDcnPresent('
CONSUME = 'bool PhxBringup::checkDcnPresent('
GLOBAL = 'bool PhxBringup::exactGlobalRetiredLocked('
DISPATCH = 'IOReturn PhxBringup::callPlatformFunction('
CLIENT_MATCH = 'bool IOAccelPhxNativeClient::matchesDcnOfferLocked('
CLOSE = 'bool PhxBringup::requestLegacyClose('
SEAL = 'void PhxBringup::sealStoppedQueues('
RESOLVE = 'static OSObject *nvAccelResolveDcnSurface('
CALL = 'static void nvAccelCheckDcnCopyBacking('

PROVIDER_PUBLIC = '''    bool offerDcnPresent(IOAccelPhxNativeClient *, OSObject *&, const build34_dcn_present_offer &);
'''
DRAIN_DECL = '''    struct DcnDrainStamp {
        uint64_t epoch, computeGeneration, gfxGeneration;
        bool matches(const DcnDrainStamp &other) const {
            return epoch == other.epoch && computeGeneration == other.computeGeneration &&
                gfxGeneration == other.gfxGeneration;
        }
    };
    bool exactWriterVmCurrent(const build34::dcn::WriterMapIdentity &,
        const build34_dcn_native_submit &, const IOAccelPhxNativeClient *, DcnDrainStamp * = nullptr);
'''
PROVIDER_FIELDS = '''    struct DcnPresent {
        IOAccelPhxNativeClient *client;
        OSObject *surface;
        build34_dcn_present_offer offer;
    } dcnPresent{};
    bool checkDcnPresent(const build34::dcn::PresentCopyBacking &);
'''
CLIENT_FIELDS = '''    bool exactWriterOffered{false};
    bool matchesDcnOfferLocked(const build34_dcn_present_offer &);
    IOReturn doDcnPresentOffer(IOExternalMethodArguments *);
'''

NATIVE = '''bool PhxBringup::offerDcnPresent(IOAccelPhxNativeClient *client, OSObject *&surface,
    const build34_dcn_present_offer &offer) {
    phx34_exact::CallbackGate<>::Lease callback(exactCallbacks);
    if (!callback || !gpuLock || !client || !surface || !IOLockTryLock(gpuLock))
        return false;
    bool stored = false;
    if (!exactCallbacks.closed() && !exactStopped && !isSleeping && !exactVMFault &&
        !watchdogRecovery.active && !watchdogRecovery.terminal && !client->exactClientCallbacks.closed()) {
        for (const auto &registration : legacyClients) {
            if (registration.client != client || registration.pending)
                continue;
            const auto &receipt = client->exactWriter;
            const auto *context = vmOwned(receipt.map.vmContext, receipt.map.vmAllocation, client);
            if (!context || context->newest != offer.native.sequence ||
                context->queueSequence[1] != offer.native.sequence || context->queueGeneration[1] != offer.native.generation)
                break;
            auto *previous = dcnPresent.surface;
            dcnPresent = {client, surface, offer};
            surface = previous;
            stored = true;
            break;
        }
    }
    IOLockUnlock(gpuLock);
    return stored;
}

bool PhxBringup::checkDcnPresent(const build34::dcn::PresentCopyBacking &present) {
    phx34_exact::CallbackGate<>::Lease callback(exactCallbacks);
    if (!callback || !gpuLock || !IOLockTryLock(gpuLock))
        return false;
    DcnPresent taken{};
    if (dcnPresent.client && dcnPresent.surface == present.surface && !exactCallbacks.closed() &&
        !exactStopped && !isSleeping && !exactVMFault && !watchdogRecovery.active && !watchdogRecovery.terminal) {
        taken = dcnPresent;
        taken.client->retain();
        dcnPresent = {};
    }
    IOLockUnlock(gpuLock);
    Phx34ScopedReference client(taken.client, false), surface(taken.surface, false);
    return taken.client && taken.client->probeExactWriterBacking(taken.offer.native, taken.offer.range, present);
}

bool IOAccelPhxNativeClient::matchesDcnOfferLocked(const build34_dcn_present_offer &offer) {
    return (''' + CLIENT_VALID + ''') && hello && !exactClientCallbacks.closed() && !owner->exactAdmissionClosed() &&
        exactWriter.complete && !exactWriterOffered && offer.native.context && offer.native.context <= PHXN_MAX_CTX &&
        ctx[offer.native.context] && build34::dcn::sameWriterReceipt(exactWriter.native, offer.native) &&
        exactWriter.matches(offer.native, offer.range, exactWriterMapLocked(offer.range).identity);
}

IOReturn IOAccelPhxNativeClient::doDcnPresentOffer(IOExternalMethodArguments *a) {
    phx34_exact::CallbackGate<>::Lease callback(exactClientCallbacks);
    if (!callback || !task || current_task() != task)
        return kIOReturnNotPermitted;
    if (!a || a->selector != BUILD34_DCN_SEL_OFFER || a->version != kIOExternalMethodArgumentsCurrentVersion ||
        a->scalarInputCount || a->scalarOutputCount || a->structureInputSize != sizeof(build34_dcn_present_offer) ||
        a->structureOutputSize || !a->structureInput || a->structureInputDescriptor ||
        a->structureOutputDescriptor || a->structureOutputDescriptorSize || a->structureVariableOutputData ||
        a->asyncWakePort || a->asyncReference || a->asyncReferenceCount)
        return kIOReturnBadArgument;
    build34_dcn_present_offer offer;
    memcpy(&offer, a->structureInput, sizeof(offer));
    if (offer.version != BUILD34_DCN_PRESENT_VERSION || offer.size != sizeof(offer) || !offer.surface || offer.reserved ||
        !build34_dcn_valid_writer_range(&offer.range))
        return kIOReturnBadArgument;
    if (!lock || !IOLockTryLock(lock)) return kIOReturnBusy;
    const bool before = matchesDcnOfferLocked(offer);
    IOLockUnlock(lock);
    if (!before) return kIOReturnNotReady;

    auto *accel = IOService::copyMatchingService(IOService::serviceMatching("NMXAccel"));
    if (!accel) return kIOReturnNotAttached;
    Phx34ScopedReference accelLifetime(accel, false);
    OSObject *surface = nullptr;
    const IOReturn lookup = accel->callPlatformFunction(BUILD34_DCN_PRESENT_LOOKUP, false, &offer.surface, task, &surface, nullptr);
    bool stored = false;
    if (lookup == kIOReturnSuccess && surface && IOLockTryLock(lock)) {
        if (matchesDcnOfferLocked(offer) && owner->offerDcnPresent(this, surface, offer)) {
            exactWriterOffered = true;
            stored = true;
        }
        IOLockUnlock(lock);
    }
    if (surface) surface->release();
    return stored ? kIOReturnSuccess : kIOReturnNotReady;
}

'''

ACCEL_RESOLVE = '''static OSObject *nvAccelResolveDcnSurface(uint32_t id, task_t task) {
    if (!id || !task) return nullptr;
    auto *root = IOService::copyMatchingService(IOService::serviceMatching("IOSurfaceRoot"));
    if (!root) return nullptr;
    auto *surface = static_cast<OSObject *>(_ZN13IOSurfaceRoot13lookupSurfaceEjP4task(root, id, task));
    root->release();
    if (surface) __atomic_store_n(&nvAccelDcnLookupSeen, true, __ATOMIC_RELEASE);
    return surface;
}

'''

ACCEL_CALL = '''static bool nvAccelDcnLookupSeen{false};
static SInt64 gCntIopDcnBackingMatches;
static void nvAccelCheckDcnCopyBacking(const build34::dcn::PresentCopyBacking &observed) {
    if (!__atomic_load_n(&nvAccelDcnLookupSeen, __ATOMIC_ACQUIRE)) return;
    auto *provider = IOService::copyMatchingService(IOService::serviceMatching("PhxBringup"));
    if (!provider) return;
    auto probe = observed;
    const auto result = provider->callPlatformFunction(BUILD34_DCN_PRESENT_PROBE, false, &probe, nullptr, nullptr, nullptr);
    provider->release();
    if (result == kIOReturnSuccess) OSAddAtomic64(1, &gCntIopDcnBackingMatches);
}
'''


def stage_native(driver, abi):
    source = writer.stage(driver, abi)

    def replace(signature, old, new):
        nonlocal source
        before = method(source, signature)
        source = once(source, before, once(before, old, new))

    include = '#include "build34_dcn_writer_receipt.h"\n'
    source = once(source, include, include + '#include "build34_dcn_present_route.h"\n#include <kern/task.h>\n')
    anchor = '    bool exactAdmissionClosed() const;\n'
    source = once(source, anchor, anchor + PROVIDER_PUBLIC)
    source = once(source, writer.SERVICE_DECL, DRAIN_DECL)
    replace(writer.CURRENT, '    const build34_dcn_native_submit &native, const IOAccelPhxNativeClient *client) {',
            '    const build34_dcn_native_submit &native, const IOAccelPhxNativeClient *client, DcnDrainStamp *drain) {')
    replace(writer.CURRENT, '    const bool current = context &&', '    bool current = context &&')
    replace(writer.CURRENT, '    IOLockUnlock(gpuLock);\n',
            '''    if (current && drain) {
        ExactOverlapSnapshot snapshot{};
        uint64_t retired = 0;
        current = exactInvalidationEpoch < UINT64_MAX - 1 && gSeq == native.sequence &&
            exactGlobalRetiredLocked(retired, &snapshot) && retired == native.sequence &&
            snapshot.queues[1].generation == native.generation;
        if (current) *drain = {exactInvalidationEpoch, snapshot.queues[0].generation, snapshot.queues[1].generation};
    }
    IOLockUnlock(gpuLock);
''')
    replace(writer.PROBE, '        auto mapping = exactWriterMapLocked(span);\n',
            '        PhxBringup::DcnDrainStamp before{}, after{};\n        auto mapping = exactWriterMapLocked(span);\n')
    replace(writer.PROBE, 'owner->exactWriterVmCurrent(mapping.identity, native, this)',
            'owner->exactWriterVmCurrent(mapping.identity, native, this, &before)')
    replace(writer.PROBE, 'owner->exactWriterVmCurrent(current.identity, native, this) &&\n',
            'owner->exactWriterVmCurrent(current.identity, native, this, &after) && before.matches(after) &&\n')
    anchor = '    LegacyClientSlot legacyClients[kMaxCtx]{};\n'
    source = once(source, anchor, anchor + PROVIDER_FIELDS)
    source = once(source, writer.CLIENT_STATE, writer.CLIENT_STATE + CLIENT_FIELDS)
    external = 'IOReturn IOAccelPhxNativeClient::externalMethod('
    replace(external, '    const bool exactSelector = selector == PHX34_R3_SEL_SUBMIT_RECEIPT ||\n',
            '    const bool exactSelector = selector == BUILD34_DCN_SEL_OFFER || selector == PHX34_R3_SEL_SUBMIT_RECEIPT ||\n')
    anchor = '    if (selector == PHX34_R3_SEL_SESSION || selector == PHX34_R3_SEL_PREFIX)\n'
    replace(external, anchor, '    if (selector == BUILD34_DCN_SEL_OFFER) return doDcnPresentOffer(a);\n' + anchor)
    replace(writer.HANDLER, '            exactWriter = {};\n', '            exactWriter = {};\n            exactWriterOffered = false;\n')
    replace(writer.PROGRESS, 'reply.flags = PHX34_R3_DCN_FLAGS;', 'reply.flags = PHX34_R3_DCN_PRESENT_FLAGS;')
    replace(CLOSE, '            legacyClients[i].pending = true;\n            IOLockUnlock(gpuLock);\n',
            '''            legacyClients[i].pending = true;
            OSObject *surface = nullptr;
            if (dcnPresent.client == client) {
                surface = dcnPresent.surface;
                dcnPresent = {};
            }
            IOLockUnlock(gpuLock);
            if (surface) surface->release();
''')
    replace(SEAL, '    if (gpuLock) IOLockUnlock(gpuLock);\n',
            '    auto *surface = dcnPresent.surface;\n    dcnPresent = {};\n'
            '    if (gpuLock) IOLockUnlock(gpuLock);\n    if (surface) surface->release();\n')
    anchor = '    if (!name || !name->isEqualTo("phxBuild34CheckAccelClaimV1"))\n'
    replace(DISPATCH, anchor, '''    if (name && name->isEqualTo(BUILD34_DCN_PRESENT_PROBE)) {
        if (wait || !device || p2 || p3 || p4) return kIOReturnBadArgument;
        return checkDcnPresent(*static_cast<const build34::dcn::PresentCopyBacking *>(device)) ?
            kIOReturnSuccess : kIOReturnNotReady;
    }
''' + anchor)
    anchor = 'IOReturn IOAccelPhxNativeClient::doExactSubmit(IOExternalMethodArguments *a) {\n'
    return once(source, anchor, NATIVE + anchor)


def stage_accelerator(accelerator):
    source = backing.stage(accelerator)
    include = '#include "build34_dcn_present_backing.h"\n'
    source = once(source, include, include + '#if defined(NMX_ACCEL) && defined(PHX_FB)\n#include "build34_dcn_present_route.h"\n#endif\n')
    anchor = 'static void (*nvAccelObserveDcnCopyBacking)(const build34::dcn::PresentCopyBacking &){nullptr};\n'
    source = once(source, anchor, '#if defined(NMX_ACCEL) && defined(PHX_FB)\n' + ACCEL_CALL +
                  anchor.replace('{nullptr}', '{nvAccelCheckDcnCopyBacking}') + '#else\n' + anchor + '#endif\n')
    anchor = 'NVACCEL_CNT(nvaccel_iop_ok,           gCntIopOk,'
    source = once(source, anchor, '''#if defined(NMX_ACCEL) && defined(PHX_FB)
NVACCEL_CNT(nvaccel_iop_dcn_backing_matches, gCntIopDcnBackingMatches, "exact writer page matches; no change to scanout");
#endif
''' + anchor)
    anchor = 'IOReturn NVAccel::callPlatformFunction(const OSSymbol *fn, bool wait, void *p1, void *p2, void *p3, void *p4)\n{\n'
    return once(source, anchor, '#if defined(NMX_ACCEL) && defined(PHX_FB)\n' + ACCEL_RESOLVE + '#endif\n' + anchor + '''#if defined(NMX_ACCEL) && defined(PHX_FB)
    if (fn && fn->isEqualTo(BUILD34_DCN_PRESENT_LOOKUP)) {
        if (wait || this != gAccel || !p1 || !p2 || !p3 || p4)
            return kIOReturnBadArgument;
        auto *out = static_cast<OSObject **>(p3);
        *out = nvAccelResolveDcnSurface(*static_cast<const uint32_t *>(p1), static_cast<task_t>(p2));
        return *out ? kIOReturnSuccess : kIOReturnNotFound;
    }
#endif
''')
