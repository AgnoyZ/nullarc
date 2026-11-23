#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Derive the paired R3 receipt-capacity protocol without admitting native use."""

from build34_exact_submit import once
from build34_exact_progress_wire import PROGRESS
from test_build34_exact_ownership import method


SUBMIT = 'IOReturn IOAccelPhxNativeClient::submitExactReceipt('
HANDLER = 'IOReturn IOAccelPhxNativeClient::doExactSubmit('
SIGNATURE = '    IOReturn submitExactReceipt(const void *, uint32_t, phx34_exact::Ticket &, phx34_exact::Receipt &);'
SUBMIT_ARGS = 'phx34_exact::Receipt &receiptOut)'
RESERVE = ('        if (exactOwnership && exactOwnership->reserve(ticket) != phx34_exact::Status::Ok)\n'
           '            return kIOReturnNoResources;\n')
TYPED_RESERVE = '''        const auto admission = exactOwnership->reserve(ticket);
        if (admission == phx34_exact::Status::Full) {
            receiptFull = true;
            return kIOReturnSuccess;
        }
        if (admission != phx34_exact::Status::Ok) return kIOReturnNoResources;
'''
REPLY = '''    reply.status = PHX34_R3_REPLY_SUBMITTED;
    reply.owner = ticket.owner; reply.serial = ticket.serial; reply.slot = ticket.slot;
    reply.sequence = receipt.sequence; reply.generation = receipt.generation; reply.queue = receipt.queue;
'''
TYPED_REPLY = '''    if (receiptFull) {
        reply.status = PHX34_R3_REPLY_RECEIPT_FULL;
        reply.owner = request.owner;
    } else {
        reply.status = PHX34_R3_REPLY_SUBMITTED;
        reply.owner = ticket.owner; reply.serial = ticket.serial; reply.slot = ticket.slot;
        reply.sequence = receipt.sequence; reply.generation = receipt.generation; reply.queue = receipt.queue;
    }
'''
RAW_PRESSURE = '''      if (no_dispatch && ((uint32_t)result == ACD_KR_BUSY || (uint32_t)result == ACD_KR_NO_RESOURCES)) {
         *no_dispatch = true;
         return -EAGAIN;
      }
'''
PARSE_PRESSURE = '''   if (no_dispatch && reply->status == PHX34_R3_REPLY_RECEIPT_FULL) {
      if (reply->owner != wire->owner || reply->serial || reply->sequence || reply->generation ||
          reply->slot || reply->queue)
         return -EPROTO;
      *no_dispatch = true;
      return -EAGAIN;
   }
'''
CAP = 'PHX34_R3_CAP_SUBMIT_RECEIPT_FULL'
FLAGS = 'PHX34_R3_PRESSURE_FLAGS'


def stage_native(source):
    submit, handler = (method(source, name) for name in (SUBMIT, HANDLER))
    typed = once(once(submit, SUBMIT_ARGS, SUBMIT_ARGS[:-1] + ', bool &receiptFull)'), RESERVE, TYPED_RESERVE)
    checked = once(handler, '    phx34_exact::Ticket ticket;\n',
                   '    bool receiptFull = false;\n    phx34_exact::Ticket ticket;\n')
    checked = once(checked, ', ticket, receipt);', ', ticket, receipt, receiptFull);')
    return once(once(source, submit, typed), handler, once(checked, REPLY, TYPED_REPLY))


def stage_declaration(source):
    return once(source, SIGNATURE, SIGNATURE[:-2] + ', bool &);')


def stage_progress_method(source):
    block = method(source, PROGRESS)
    return once(source, block, once(block, 'reply.flags = PHX34_R3_PROGRESS_FLAGS;', f'reply.flags = {FLAGS};'))


def stage(source):
    return stage_progress_method(stage_declaration(stage_native(source)))


def stage_ownership(source):
    anchor = '    bool take(uint64_t &value) {\n'
    source = once(source, anchor, '    bool available() const { return last_ < UINT64_MAX - 1; }\n' + anchor)
    source = once(source, '        if (last_ >= UINT64_MAX - 1) return false;', '        if (!available()) return false;')
    return once(source, '        return Status::Full;',
                '        return serial_.available() ? Status::Full : Status::Exhausted;')


def stage_submit_wire(source):
    anchor = '#define PHX34_R3_REPLY_SUBMITTED 3u\n'
    return once(source, anchor, anchor + '#define PHX34_R3_REPLY_RECEIPT_FULL 4u\n')


def stage_progress_wire(source):
    anchor = '#define PHX34_R3_PROGRESS_FLAGS (PHX34_R3_CAP_EXACT_RECEIPTS | PHX34_R3_CAP_CHECKED_PREFIX)\n'
    return once(source, anchor, anchor + f'#define {CAP} (1u << 2)\n'
                f'#define {FLAGS} (PHX34_R3_PROGRESS_FLAGS | {CAP})\n')


def stage_mesa(source):
    source = once(source, RAW_PRESSURE, '      if (no_dispatch) return -EIO;\n')
    source = once(source, 'reply.flags != PHX34_R3_PROGRESS_FLAGS', f'reply.flags != {FLAGS}')
    anchor = '   *decoded = (struct acd_exact_receipt)'
    return once(source, anchor, PARSE_PRESSURE + anchor)
