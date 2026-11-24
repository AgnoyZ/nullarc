"""Stage one native writer observation without admitting a native open or flip."""

import hashlib

from build34_dcn_render_map_stage import ABI, ABI_SHA256, DRIVER, DRIVER_SHA256
from build34_exact_binding import CLIENT_VALID
from build34_exact_open import stage as exact_open
from build34_exact_submit import once
from build34_exact_submit_pressure import HANDLER, PROGRESS, stage as pressure
from test_build34_exact_ownership import method


SNAPSHOT = 'build34::dcn::WriterMapping IOAccelPhxNativeClient::exactWriterMapLocked('
CURRENT = 'bool PhxBringup::exactWriterVmCurrent('
COMPLETE = 'void IOAccelPhxNativeClient::completeExactWriterLocked('
PROBE = 'bool IOAccelPhxNativeClient::probeExactWriterBacking('
WAIT = 'phx34_exact::Status IOAccelPhxNativeClient::waitExactReceipt('
ACK = 'phx34_exact::Status IOAccelPhxNativeClient::ackExactReceipt('
MAP = 'IOReturn IOAccelPhxNativeClient::doGemVa('
CONTEXT = 'IOReturn IOAccelPhxNativeClient::doCtx('
CLOSE = 'IOReturn IOAccelPhxNativeClient::finishExactClose('

SERVICE_DECL = '''    bool exactWriterVmCurrent(const build34::dcn::WriterMapIdentity &,
        const build34_dcn_native_submit &, const IOAccelPhxNativeClient *);
'''
CLIENT_STATE = '''    build34::dcn::WriterReceipt exactWriter{};
    uint64_t exactWriterMapSerial{0};
    build34::dcn::WriterMapping exactWriterMapLocked(const build34_dcn_writer_range &);
    void completeExactWriterLocked(phx34_exact::Ticket, const phx34_exact::Receipt &);
'''
PROBE_DECL = '''    bool probeExactWriterBacking(build34_dcn_native_submit, build34_dcn_writer_range,
        const build34::dcn::PresentCopyBacking &);
'''
MAP_FIELDS = '''        uint64_t writerGeneration{0}, writerPreparation{0};
'''

SERVICE_METHOD = '''bool PhxBringup::exactWriterVmCurrent(const build34::dcn::WriterMapIdentity &mapping,
    const build34_dcn_native_submit &native, const IOAccelPhxNativeClient *client) {
    phx34_exact::CallbackGate<>::Lease callback(exactCallbacks);
    if (!callback || !gpuLock || !IOLockTryLock(gpuLock))
        return false;
    const auto *context = vmOwned(mapping.vmContext, mapping.vmAllocation, client);
    const bool current = context && !exactCallbacks.closed() && !exactStopped && !isSleeping && !exactVMFault &&
        !watchdogRecovery.active && !watchdogRecovery.terminal &&
        native.queue == 1 && native.sequence && context->newest == native.sequence &&
        context->queueSequence[1] == native.sequence && context->queueGeneration[1] == native.generation;
    IOLockUnlock(gpuLock);
    return current;
}

'''

CLIENT_METHODS = '''build34::dcn::WriterMapping IOAccelPhxNativeClient::exactWriterMapLocked(
    const build34_dcn_writer_range &span) {
    using namespace build34::dcn;
    if (!build34_dcn_valid_writer_range(&span) || !maps || !vmid || !vmGeneration || boCleanupFault)
        return {};
    for (int index = 0; index < kMaxMaps; ++index) {
        const Map &entry = maps[index];
        if (!entry.used || !entry.materialized || !entry.writerGeneration || entry.handle != span.bo || span.va < entry.va)
            continue;
        const uint64_t relative = span.va - entry.va;
        if (relative >= entry.size || span.bytes > entry.size - relative)
            continue;
        const Bo *bo = findBo(entry.handle);
        if (!bo || !bo->host || bo->size != bo->md->getLength() || entry.off > bo->size || relative > bo->size - entry.off)
            return {};
        PinnedDescriptorSlice slice{bo->md, entry.off + relative, span.bytes};
        const auto preparation = livePresentPreparation(slice);
        if (!preparation || preparation != entry.writerPreparation)
            return {};
        return {{entry.writerGeneration, preparation, vmGeneration, slice.offset, vmid}, slice};
    }
    return {};
}

void IOAccelPhxNativeClient::completeExactWriterLocked(phx34_exact::Ticket ticket, const phx34_exact::Receipt &receipt) {
    const build34_dcn_native_submit native{receipt.sequence, ticket.owner, ticket.serial,
        receipt.generation, ticket.slot, receipt.queue, exactWriter.native.context};
    if (build34::dcn::sameWriterReceipt(exactWriter.native, native))
        exactWriter.complete = true;
}

bool IOAccelPhxNativeClient::probeExactWriterBacking(build34_dcn_native_submit native,
    build34_dcn_writer_range span, const build34::dcn::PresentCopyBacking &present) {
    using namespace build34::dcn;
    phx34_exact::CallbackGate<>::Lease callback(exactClientCallbacks);
    if (!callback || !lock || __atomic_load_n(&legacyState, __ATOMIC_ACQUIRE) != 2 || !IOLockTryLock(lock))
        return false;
    auto live = [&] {
        return (''' + CLIENT_VALID + ''') && !exactClientCallbacks.closed() && !owner->exactAdmissionClosed() &&
            exactWriter.complete && native.context && native.context <= PHXN_MAX_CTX && ctx[native.context];
    };
    bool same = false;
    if (live() && sameWriterReceipt(exactWriter.native, native)) {
        auto mapping = exactWriterMapLocked(span);
        if (exactWriter.matches(native, span, mapping.identity) && owner->exactWriterVmCurrent(mapping.identity, native, this) &&
            comparePreparedCopyBacking(present, {&mapping.slice, readPinnedDescriptorPage}, mapping.slice.bytes)) {
            const auto current = exactWriterMapLocked(span);
            same = live() && mapping.slice.descriptor == current.slice.descriptor &&
                exactWriter.matches(native, span, current.identity) && owner->exactWriterVmCurrent(current.identity, native, this) &&
                live() && livePresentPreparation(present.slice) == present.preparation;
        }
    }
    IOLockUnlock(lock);
    return same;
}

'''


def stage(driver, abi):
    if (hashlib.sha256(driver).hexdigest() != DRIVER_SHA256 or
            hashlib.sha256(abi).hexdigest() != ABI_SHA256):
        raise ValueError('Build34 DCN exact writer source or ABI drift')
    source = pressure(exact_open(driver.decode()))

    def replace(signature, old, new):
        nonlocal source
        before = method(source, signature)
        source = once(source, before, once(before, old, new))

    anchor = '#include "build34_exact_open_wire.h"\n'
    source = once(source, anchor, anchor + '#include "build34_dcn_writer_receipt.h"\n')
    anchor = '    bool exactAdmissionClosed() const;\n'
    source = once(source, anchor, anchor + SERVICE_DECL)
    anchor = '    Phx34ExactOpen requestedExactOpen{};\n'
    source = once(source, anchor, anchor + CLIENT_STATE)
    anchor = '    IOReturn clientMemoryForType(UInt32 type, IOOptionBits *options, IOMemoryDescriptor **memory) override;\n'
    source = once(source, anchor, anchor + PROBE_DECL)
    anchor = '        bool materialized;\n'
    source = once(source, anchor, anchor + MAP_FIELDS)

    replace(MAP, '    if (v->operation == PHX_AMDGPU_VA_OP_MAP) {\n',
            '    if (exactOwnership) exactWriter = {};\n'
            '    if (v->operation == PHX_AMDGPU_VA_OP_MAP) {\n')
    replace(MAP, '        if (materialize) {\n',
            '        const uint64_t preparation = materialize && exactOwnership && b->host ? b->md->getPreparationID() : 0;\n'
            '        if (materialize) {\n')
    replace(MAP, '        if (!materialize) mayHaveLogicalMappings = true;\n',
            '        if (preparation > kIOPreparationIDAlwaysPrepared && preparation != UINT64_MAX &&\n'
            '            b->md->getPreparationID() == preparation && exactWriterMapSerial < UINT64_MAX - 1) {\n'
            '            maps[freei].writerGeneration = ++exactWriterMapSerial;\n'
            '            maps[freei].writerPreparation = preparation;\n'
            '        }\n'
            '        if (!materialize) mayHaveLogicalMappings = true;\n')
    replace(CONTEXT, '        ctx[in.ctx_id] = false;\n',
            '        if (in.ctx_id == exactWriter.native.context) exactWriter = {};\n'
            '        ctx[in.ctx_id] = false;\n')
    replace(CLOSE, '    IOLockLock(lock);\n', '    IOLockLock(lock);\n    exactWriter = {};\n')
    replace(PROGRESS, 'reply.flags = PHX34_R3_PRESSURE_FLAGS;', 'reply.flags = PHX34_R3_DCN_FLAGS;')
    replace(HANDLER, '        a->structureInputSize != sizeof(phx34_r3_submit_request) ||\n',
            '        (a->structureInputSize != sizeof(phx34_r3_submit_request) &&\n'
            '         a->structureInputSize != sizeof(build34_dcn_writer_request)) ||\n')
    replace(HANDLER, '''    phx34_r3_submit_request request;
    memcpy(&request, a->structureInput, sizeof(request)); // one immutable, possibly unaligned copy
    if (request.version != PHX34_R3_WIRE_VERSION || request.size != sizeof(request) ||
''', '''    build34_dcn_writer_request envelope;
    const auto bytes = a->structureInputSize;
    memcpy(&envelope, a->structureInput, bytes);
    const auto &request = envelope.submit;
    if (request.version != PHX34_R3_WIRE_VERSION || request.size != bytes ||
''')
    replace(HANDLER, '    bool receiptFull = false;\n', '    bool receiptFull = false, writerAccepted = false;\n')
    replace(HANDLER, '''        else result = submitExactReceipt(payload,
                    sizeof(request.submit) + request.submit.num_ibs * sizeof(phxn_cs_ib), ticket, receipt, receiptFull);
''', '''        else {
            exactWriter = {};
            build34::dcn::WriterMapping before{};
            if (bytes == sizeof(envelope) && build34_dcn_matches_writer_ib(&request, &envelope.writer))
                before = exactWriterMapLocked(envelope.writer.range);
            result = submitExactReceipt(payload,
                sizeof(request.submit) + request.submit.num_ibs * sizeof(phxn_cs_ib), ticket, receipt, receiptFull);
            if (result == kIOReturnSuccess && !receiptFull && before.slice.descriptor) {
                const auto after = exactWriterMapLocked(envelope.writer.range);
                const build34_dcn_native_submit native{receipt.sequence, ticket.owner, ticket.serial,
                    receipt.generation, ticket.slot, receipt.queue, request.submit.ctx_id};
                if (build34::dcn::sameWriterReceipt(native, native) && before.identity.matches(after.identity) &&
                    before.slice.descriptor == after.slice.descriptor && owner->exactWriterVmCurrent(after.identity, native, this)) {
                    exactWriter = {native, envelope.writer.range, after.identity, false};
                    writerAccepted = true;
                }
            }
        }
''')
    replace(HANDLER, '        reply.status = PHX34_R3_REPLY_SUBMITTED;\n',
            '        reply.status = writerAccepted ? PHX34_R3_REPLY_WRITER_SUBMITTED : PHX34_R3_REPLY_SUBMITTED;\n')
    replace(WAIT, '                 owner->observeExact(*exactOwnership, ticket, exactClientCallbacks, this);\n',
            '                 owner->observeExact(*exactOwnership, ticket, exactClientCallbacks, this);\n'
            '        if (result == phx34_exact::Status::Complete) completeExactWriterLocked(ticket, receipt);\n')
    replace(ACK, '    if (result == phx34_exact::Status::Complete)\n'
                 '        result = exactOwnership->forget(ticket); // Busy while any admitted wait pins it\n',
            '    if (result == phx34_exact::Status::Complete) {\n'
            '        completeExactWriterLocked(ticket, receipt);\n'
            '        result = exactOwnership->forget(ticket); // Busy while any admitted wait pins it\n'
            '    }\n')
    anchor = 'bool PhxBringup::exactNativeOpenAdmitted() const {\n'
    return once(source, anchor, SERVICE_METHOD + CLIENT_METHODS + anchor)
