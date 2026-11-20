#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Stage complete-token wait/ACK and strict structure dispatch, never deploy.

No native admission, capability, hardware reader, global snapshot, CPU-fence
publication or healthy drain is enabled. Earlier permanent quarantine remains.
"""
from build34_exact_ack import stage as stage_ack, stage_header as ack_header
from build34_exact_binding import CLIENT_VALID
from build34_exact_submit import once
from test_build34_exact_ownership import method

AUTHENTICATE = '''    // Caller holds the client lock. A sequence alone never authenticates a
    // receipt; bind all submitted identity fields to one stable slot/serial.
    Status authenticate(Ticket ticket, const Receipt &expected) {
        Receipt actual;
        const auto result = inspect(ticket, actual);
        if (result != Status::Ok) return result;
        return actual.sequence == expected.sequence && actual.generation == expected.generation &&
               actual.queue == expected.queue ? Status::Ok : Status::Unknown;
    }

'''

WIRE = '''bool PhxBringup::exactAdmissionClosed() const {
    return exactCallbacks.closed();
}

IOReturn IOAccelPhxNativeClient::doExactReceipt(uint32_t selector, IOExternalMethodArguments *a) {
    const uint64_t start = mach_absolute_time(); // include parsing and the outer handshake lock queue
    phx34_exact::CallbackGate<>::Lease callback(exactClientCallbacks);
    if (!callback) return kIOReturnNotReady;
    if (!a || (selector != PHX34_R3_SEL_WAIT_RECEIPT && selector != PHX34_R3_SEL_ACK_RECEIPT) ||
        a->selector != selector || a->version != kIOExternalMethodArgumentsCurrentVersion ||
        a->scalarInputCount || a->scalarOutputCount ||
        a->structureInputSize != sizeof(phx34_r3_request) ||
        a->structureOutputSize != sizeof(phx34_r3_reply) ||
        !a->structureInput || !a->structureOutput ||
        a->structureInputDescriptor || a->structureOutputDescriptor || a->structureOutputDescriptorSize ||
        a->structureVariableOutputData || a->asyncWakePort || a->asyncReference || a->asyncReferenceCount)
        return kIOReturnBadArgument;
    phx34_r3_request request;
    memcpy(&request, a->structureInput, sizeof(request)); // input may be unaligned or overlap output
    const bool ack = selector == PHX34_R3_SEL_ACK_RECEIPT;
    if (request.version != PHX34_R3_WIRE_VERSION || request.size != sizeof(request) || request.reserved ||
        !request.owner || request.owner == UINT64_MAX || !request.serial || request.serial == UINT64_MAX ||
        !request.sequence || request.sequence == UINT64_MAX ||
        !request.generation || request.generation == UINT64_MAX ||
        request.slot >= phx34_exact::Registry::capacity || request.queue >= 2 ||
        request.timeout_ns > PHXN_WAIT_CAP_NS || (ack && request.timeout_ns))
        return kIOReturnBadArgument;
    // Read handshake state under the same lock as doHello. Identity is frozen
    // by start; the actual native mode request is deliberately still absent.
    IOLockLock(lock);
    const bool admitted = hello && (''' + CLIENT_VALID + ''') && !exactClientCallbacks.closed();
    IOLockUnlock(lock);
    if (!admitted) return kIOReturnNotReady;
    const phx34_exact::Ticket ticket{request.owner, request.serial, request.slot};
    const phx34_exact::Receipt receipt{request.sequence, request.generation, request.queue};
    const auto result = ack ? ackExactReceipt(ticket, receipt) :
                             waitExactReceipt(ticket, receipt, request.timeout_ns, start);
    uint32_t status;
    if (ack && result == phx34_exact::Status::Ok) status = PHX34_R3_REPLY_ACKED;
    else if (!ack && result == phx34_exact::Status::Complete) status = PHX34_R3_REPLY_COMPLETE;
    else if (!ack && result == phx34_exact::Status::TimedOut) status = PHX34_R3_REPLY_PENDING;
    else if (result == phx34_exact::Status::Busy || result == phx34_exact::Status::Pending) return kIOReturnBusy;
    else if (result == phx34_exact::Status::Unknown) return kIOReturnNotFound;
    else if (result == phx34_exact::Status::Exhausted) return kIOReturnNoResources;
    else if (result == phx34_exact::Status::Closed || result == phx34_exact::Status::Lost ||
             result == phx34_exact::Status::InvalidObservation) return kIOReturnNotReady;
    else return kIOReturnBadArgument;
    if (exactClientCallbacks.closed() || owner->exactAdmissionClosed()) return kIOReturnNotReady;
    phx34_r3_reply reply{}; // reserved bytes never expose kernel storage
    reply.version = PHX34_R3_WIRE_VERSION;
    reply.size = sizeof(reply);
    reply.status = status;
    reply.owner = request.owner; reply.serial = request.serial; reply.sequence = request.sequence;
    reply.generation = request.generation; reply.slot = request.slot; reply.queue = request.queue;
    memcpy(a->structureOutput, &reply, sizeof(reply)); // sole output write, after successful result
    return kIOReturnSuccess;
}

'''


def stage_header(source):
    return once(ack_header(source), '    Status observe(Ticket ticket, bool service_live, const QueueObservation queues[2]) {\n',
                AUTHENTICATE + '    Status observe(Ticket ticket, bool service_live, const QueueObservation queues[2]) {\n')


def stage(source):
    source = stage_ack(source)
    source = once(source, '#include "build34_exact_ownership.h"\n',
                  '#include "build34_exact_ownership.h"\n#include "build34_exact_receipt_wire.h"\n')
    source = once(source, '    bool bindExactClient(phx34_exact::Registry &, OSObject *);\n',
                  '    bool bindExactClient(phx34_exact::Registry &, OSObject *);\n'
                  '    bool exactAdmissionClosed() const;\n')
    source = once(source, '    phx34_exact::Status ackExact(uint64_t sequence); // internal, receipt metadata only\n',
                  '    phx34_exact::Status ackExact(uint64_t sequence); // internal, receipt metadata only\n'
                  '    phx34_exact::Status waitExactReceipt(phx34_exact::Ticket, const phx34_exact::Receipt &, uint64_t, uint64_t);\n'
                  '    phx34_exact::Status ackExactReceipt(phx34_exact::Ticket, const phx34_exact::Receipt &);\n'
                  '    IOReturn doExactReceipt(uint32_t, IOExternalMethodArguments *);\n')
    wait = method(source, 'phx34_exact::Status IOAccelPhxNativeClient::waitExact(')
    wait = once(wait, 'waitExact(uint64_t sequence, uint64_t timeout)',
                'waitExactReceipt(phx34_exact::Ticket ticket, const phx34_exact::Receipt &receipt, uint64_t timeout, uint64_t start)')
    wait = once(wait, '    const uint64_t start = mach_absolute_time(); // include queued lock and reader time\n',
                '    // start is captured by the wire handler before parsing/outer lock queueing.\n')
    wait = once(wait, '    phx34_exact::Ticket ticket;\n', '')
    wait = once(wait, 'exactOwnership->lookup(sequence, ticket);', 'exactOwnership->authenticate(ticket, receipt);')
    ack = method(source, 'phx34_exact::Status IOAccelPhxNativeClient::ackExact(')
    ack = once(ack, 'ackExact(uint64_t sequence)',
               'ackExactReceipt(phx34_exact::Ticket ticket, const phx34_exact::Receipt &receipt)')
    ack = once(ack, '    phx34_exact::Ticket ticket;\n', '')
    ack = once(ack, 'exactOwnership->lookup(sequence, ticket);', 'exactOwnership->authenticate(ticket, receipt);')
    source = once(source, 'uint64_t PhxBringup::queueFence(const GpuQueue &q) const {\n',
                  wait + '\n' + ack + '\n' + WIRE + 'uint64_t PhxBringup::queueFence(const GpuQueue &q) const {\n')
    return once(source, '    if (selector == PHXN_SEL_WAITSEQ)\n',
                '    if (selector == PHX34_R3_SEL_WAIT_RECEIPT || selector == PHX34_R3_SEL_ACK_RECEIPT)\n'
                '        return doExactReceipt(selector, a); // new waits must not inherit the legacy client lock\n'
                '    if (selector == PHXN_SEL_WAITSEQ)\n')
