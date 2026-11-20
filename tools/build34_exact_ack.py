#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Stage wait-pinned receipt acknowledgement, CPU only; no native selector.

Forgetting releases receipt metadata only, never BOs, VMIDs or service pins.
Native negotiation, userspace payload ownership and healthy teardown are still
required. The deliberately quarantining staged driver is not deployable.
"""
from build34_exact_binding import CLIENT_VALID
from build34_exact_submit import once
from build34_exact_wait import stage as stage_wait, stage_header as wait_header


PINS = '''    // Caller holds the same client lock as lookup/observe/forget.
    Status pinWait(Ticket ticket) {
        if (closed_) return Status::Closed;
        Entry *e = entry(ticket);
        if (!e) return Status::Unknown;
        if (e->phase == Phase::Reserved) return Status::Unsubmitted;
        if (e->phase == Phase::Lost) return Status::Lost;
        if (e->waiters == UINT16_MAX) return Status::Exhausted;
        ++e->waiters;
        return Status::Ok;
    }
    Status unpinWait(Ticket ticket) {
        // Closing refuses new work but must allow admitted waiters to leave.
        Entry *e = entry(ticket);
        if (!e) return Status::Unknown;
        if (!e->waiters) return Status::Invalid;
        --e->waiters;
        return Status::Ok;
    }

'''

ACK = '''phx34_exact::Status IOAccelPhxNativeClient::ackExact(uint64_t sequence) {
    phx34_exact::CallbackGate<>::Lease callback(exactClientCallbacks);
    if (!(''' + CLIENT_VALID + ''')) return phx34_exact::Status::Invalid;
    if (!callback) return phx34_exact::Status::Closed;
    IOLockLock(lock);
    phx34_exact::Ticket ticket;
    auto result = exactClientCallbacks.closed() ? phx34_exact::Status::Closed :
                  exactOwnership->lookup(sequence, ticket);
    if (result == phx34_exact::Status::Ok)
        result = owner->observeExact(*exactOwnership, ticket, exactClientCallbacks, this);
    if (result == phx34_exact::Status::Complete)
        result = exactOwnership->forget(ticket); // Busy while any admitted wait pins it
    IOLockUnlock(lock);
    return result; // receipt metadata only; no CPU fence or native resource release
}

'''


def stage_header(source):
    source = wait_header(source)
    source = once(source, 'Complete, Lost, InvalidObservation, TimedOut\n',
                  'Complete, Lost, InvalidObservation, TimedOut, Busy\n')
    source = once(source, '        uint64_t serial = 0;\n',
                  '        uint64_t serial = 0;\n        uint16_t waiters = 0;\n')
    source = once(source, '    Status forget(Ticket ticket) {\n', PINS + '    Status forget(Ticket ticket) {\n')
    source = once(source, '        if (e->phase != Phase::Complete) return Status::Invalid;\n',
                  '        if (e->phase != Phase::Complete) return Status::Invalid;\n'
                  '        if (e->waiters) return Status::Busy;\n')
    return once(source, '    // Closing refuses all future mutations/observations without losing records.\n',
                '    // Closing refuses new work/observations without losing records.\n'
                '    // Admitted waiters may still release their metadata pins.\n')


def stage(source):
    source = stage_wait(source)
    source = once(source, '    phx34_exact::Status waitExact(uint64_t sequence, uint64_t timeout); // internal fallback only\n',
                  '    phx34_exact::Status waitExact(uint64_t sequence, uint64_t timeout); // internal fallback only\n'
                  '    phx34_exact::Status ackExact(uint64_t sequence); // internal, receipt metadata only\n')
    start = source.index('phx34_exact::Status IOAccelPhxNativeClient::waitExact(')
    end = source.index('\n}\n', start) + 3
    old = source[start:end]
    new = once(old, '    IOLockUnlock(lock);\n    if (result != phx34_exact::Status::Ok) return result;\n',
               '    if (result == phx34_exact::Status::Ok) result = exactOwnership->pinWait(ticket);\n'
               '    IOLockUnlock(lock);\n    if (result != phx34_exact::Status::Ok) return result;\n'
               '    auto finish = [&](phx34_exact::Status status) {\n'
               '        IOLockLock(lock);\n'
               '        const auto released = exactOwnership->unpinWait(ticket);\n'
               '        IOLockUnlock(lock);\n'
               '        return released == phx34_exact::Status::Ok ? status : phx34_exact::Status::Invalid;\n'
               '    };\n')
    new = once(new, '        if (result != phx34_exact::Status::Pending) return result;\n',
               '        if (result != phx34_exact::Status::Pending) return finish(result);\n')
    new = once(new, '        if (elapsed >= timeout) return phx34_exact::Status::TimedOut;\n',
               '        if (elapsed >= timeout) return finish(phx34_exact::Status::TimedOut);\n')
    source = once(source, old, new)
    return once(source, 'uint64_t PhxBringup::queueFence(const GpuQueue &q) const {\n',
                ACK + 'uint64_t PhxBringup::queueFence(const GpuQueue &q) const {\n')
