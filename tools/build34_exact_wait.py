#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Stage an owned-ticket exact wait with real elapsed-time budget, CPU only.

This is the polling fallback, not an AMD completion interrupt/event route.
Native request, hardware reader and safe resource reclamation remain absent.
"""
from build34_exact_binding import CLIENT_VALID, stage as stage_binding, stage_header as bind_header
from build34_exact_submit import once


WAIT = '''phx34_exact::Status IOAccelPhxNativeClient::waitExact(uint64_t sequence, uint64_t timeout) {
    const uint64_t start = mach_absolute_time(); // include queued lock and reader time
    phx34_exact::CallbackGate<>::Lease callback(exactClientCallbacks);
    if (!(''' + CLIENT_VALID + ''')) return phx34_exact::Status::Invalid;
    if (!callback) return phx34_exact::Status::Closed;
    if (timeout > PHXN_WAIT_CAP_NS) timeout = PHXN_WAIT_CAP_NS;
    phx34_exact::Ticket ticket;
    IOLockLock(lock);
    auto result = exactClientCallbacks.closed() ? phx34_exact::Status::Closed :
                  exactOwnership->lookup(sequence, ticket);
    IOLockUnlock(lock);
    if (result != phx34_exact::Status::Ok) return result;
    // Capture owner/slot/serial ONCE. Never re-resolve a sequence after sleeping.
    for (;;) {
        IOLockLock(lock);
        result = exactClientCallbacks.closed() ? phx34_exact::Status::Closed :
                 owner->observeExact(*exactOwnership, ticket, exactClientCallbacks, this);
        IOLockUnlock(lock);
        if (result != phx34_exact::Status::Pending) return result;
        uint64_t elapsed = 0;
        absolutetime_to_nanoseconds(mach_absolute_time() - start, &elapsed);
        if (elapsed >= timeout) return phx34_exact::Status::TimedOut;
        // Yield for every positive pending wait, even below one millisecond.
        // Both locks are released. Scheduling can overshoot; final observation
        // after wake wins over timeout, but no additional sleep follows expiry.
        IOSleep(1);
    }
}

'''


def stage_header(source):
    return once(bind_header(source), '    Complete, Lost, InvalidObservation\n',
                '    Complete, Lost, InvalidObservation, TimedOut\n')


def stage(source):
    source = stage_binding(source)
    source = once(source, '    phx34_exact::Status queryExact(uint64_t sequence); // no selector/ABI exposure\n',
                  '    phx34_exact::Status queryExact(uint64_t sequence); // no selector/ABI exposure\n'
                  '    phx34_exact::Status waitExact(uint64_t sequence, uint64_t timeout); // internal fallback only\n')
    return once(source, 'uint64_t PhxBringup::queueFence(const GpuQueue &q) const {\n',
                WAIT + 'uint64_t PhxBringup::queueFence(const GpuQueue &q) const {\n')
