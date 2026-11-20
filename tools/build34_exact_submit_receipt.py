#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Stage exact-submit receipts without enabling native mode or device access.

Derive the typed submit from the already tested actual submit. Legacy submit,
wait/ACK, lifetime quarantine and null hardware reader remain unchanged.
"""
from build34_exact_binding import CLIENT_VALID
from build34_exact_receipt import stage as previous_stage, stage_header as previous_header
from build34_exact_submit import once
from test_build34_exact_ownership import method

WIRE = '''IOReturn IOAccelPhxNativeClient::doExactSubmit(IOExternalMethodArguments *a) {
    phx34_exact::CallbackGate<>::Lease callback(exactClientCallbacks);
    if (!callback) return kIOReturnNotReady;
    if (!a || a->selector != PHX34_R3_SEL_SUBMIT_RECEIPT ||
        a->version != kIOExternalMethodArgumentsCurrentVersion ||
        a->scalarInputCount || a->scalarOutputCount ||
        a->structureInputSize != sizeof(phx34_r3_submit_request) ||
        a->structureOutputSize != sizeof(phx34_r3_reply) ||
        !a->structureInput || !a->structureOutput ||
        a->structureInputDescriptor || a->structureOutputDescriptor || a->structureOutputDescriptorSize ||
        a->structureVariableOutputData || a->asyncWakePort || a->asyncReference || a->asyncReferenceCount)
        return kIOReturnBadArgument;
    phx34_r3_submit_request request;
    memcpy(&request, a->structureInput, sizeof(request)); // one immutable, possibly unaligned copy
    if (request.version != PHX34_R3_WIRE_VERSION || request.size != sizeof(request) ||
        !request.owner || request.owner == UINT64_MAX || request.reserved[0] || request.reserved[1] ||
        request.submit.num_ibs < 1 || request.submit.num_ibs > PHXN_MAX_IBS)
        return kIOReturnBadArgument;
    const phxn_cs_ib zero{};
    for (uint32_t i = request.submit.num_ibs; i < PHXN_MAX_IBS; ++i)
        if (memcmp(&request.ibs[i], &zero, sizeof(zero))) return kIOReturnBadArgument;
    phx34_exact::Ticket ticket;
    phx34_exact::Receipt receipt;
    const uint8_t *payload = reinterpret_cast<const uint8_t *>(&request) + offsetof(phx34_r3_submit_request, submit);
    IOLockLock(lock);
    IOReturn result = kIOReturnNotReady;
    if (hello && (''' + CLIENT_VALID + ''') && !exactClientCallbacks.closed() &&
        !owner->exactAdmissionClosed()) {
        if (!exactRegistry.hasOwner(request.owner)) result = kIOReturnNotFound;
        else result = submitExactReceipt(payload,
                    sizeof(request.submit) + request.submit.num_ibs * sizeof(phxn_cs_ib), ticket, receipt);
    }
    IOLockUnlock(lock);
    if (result != kIOReturnSuccess) return result;
    if (exactClientCallbacks.closed() || owner->exactAdmissionClosed()) return kIOReturnNotReady;
    phx34_r3_reply reply{};
    reply.version = PHX34_R3_WIRE_VERSION; reply.size = sizeof(reply);
    reply.status = PHX34_R3_REPLY_SUBMITTED;
    reply.owner = ticket.owner; reply.serial = ticket.serial; reply.slot = ticket.slot;
    reply.sequence = receipt.sequence; reply.generation = receipt.generation; reply.queue = receipt.queue;
    memcpy(a->structureOutput, &reply, sizeof(reply)); // sole output write; errors retain dispatched receipts
    return kIOReturnSuccess;
}

'''


def stage_header(source):
    return once(previous_header(source), '    uint32_t occupied() const { return occupied_; }\n',
                '    bool hasOwner(uint64_t value) const { return value && value != UINT64_MAX && value == owner_; }\n'
                '    uint32_t occupied() const { return occupied_; }\n')


def stage(source):
    source = previous_stage(source)
    source = once(source, '#include "build34_exact_receipt_wire.h"\n',
                  '#include "build34_exact_receipt_wire.h"\n#include "build34_exact_submit_wire.h"\n')
    source = once(source, '    IOReturn doExactReceipt(uint32_t, IOExternalMethodArguments *);\n',
                  '    IOReturn doExactReceipt(uint32_t, IOExternalMethodArguments *);\n'
                  '    IOReturn doExactSubmit(IOExternalMethodArguments *);\n'
                  '    IOReturn submitExactReceipt(const void *, uint32_t, phx34_exact::Ticket &, phx34_exact::Receipt &);\n')
    typed = method(source, 'IOReturn IOAccelPhxNativeClient::doSubmit(')
    typed = once(typed, 'doSubmit(IOExternalMethodArguments *a)',
                 'submitExactReceipt(const void *data, uint32_t size, phx34_exact::Ticket &ticketOut, phx34_exact::Receipt &receiptOut)')
    typed = once(typed, '    if (a->scalarInputCount != 0 || a->scalarOutputCount != 1 || a->structureOutputSize != 0 ||\n'
                 '        a->structureInputDescriptor || a->structureInputSize < 64 ||\n'
                 '        a->structureInputSize > 32 + 32 * PHXN_MAX_IBS)\n',
                 '    if (!exactOwnership) return kIOReturnNotReady;\n'
                 '    if (!data || size < 64 || size > 32 + 32 * PHXN_MAX_IBS)\n')
    typed = typed.replace('a->structureInputSize', 'size').replace('a->structureInput', 'data')
    typed = once(typed, '    for (uint32_t i = 0; i < h.num_ibs; i++) {\n        phxn_cs_ib ib;\n',
                 '    // Exact CPU user-fence publication has no protocol yet; never accept it silently.\n'
                 '    if (h.flags) return kIOReturnUnsupported;\n'
                 '    phxn_cs_ib first;\n    bcopy(in + sizeof(h), &first, sizeof(first));\n'
                 '    for (uint32_t i = 0; i < h.num_ibs; i++) {\n        phxn_cs_ib ib;\n')
    typed = once(typed, '        if (!ibCovered(ib.va_start, ib.ib_bytes))\n',
                 '        if (ib.ip_type != first.ip_type) return kIOReturnUnsupported; // one native batch/queue only\n'
                 '        if (!ibCovered(ib.va_start, ib.ib_bytes))\n')
    typed = once(typed, '        a->scalarOutput[0] = seq;\n',
                 '        phx34_exact::Receipt receipt;\n'
                 '        if (exactOwnership->inspect(ticket, receipt) != phx34_exact::Status::Ok ||\n'
                 '            receipt.sequence != seq || exactClientCallbacks.closed() || owner->exactAdmissionClosed())\n'
                 '            return kIOReturnNotReady; // published work remains retained on uncertainty\n'
                 '        ticketOut = ticket; receiptOut = receipt;\n')
    fallback = typed.index('    if (exactOwnership) return kIOReturnNotReady; // no mock success for exact clients\n')
    typed = typed[:fallback] + '    return kIOReturnNotReady; // no synthetic success when no GPU is ready\n}\n'
    source = once(source, 'uint64_t PhxBringup::queueFence(const GpuQueue &q) const {\n',
                  typed + '\n' + WIRE + 'uint64_t PhxBringup::queueFence(const GpuQueue &q) const {\n')
    return once(source, '    if (selector == PHX34_R3_SEL_WAIT_RECEIPT || selector == PHX34_R3_SEL_ACK_RECEIPT)\n',
                '    if (selector == PHX34_R3_SEL_SUBMIT_RECEIPT)\n'
                '        return doExactSubmit(a); // this handler owns its client lock\n'
                '    if (selector == PHX34_R3_SEL_WAIT_RECEIPT || selector == PHX34_R3_SEL_ACK_RECEIPT)\n')
