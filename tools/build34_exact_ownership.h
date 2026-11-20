// SPDX-License-Identifier: MIT
// R3 source-only ownership prototype. No production caller or native ABI.
// A future caller must serialize access, allocate a unique nonzero owner epoch,
// reserve before submission and publish the actual queue/epoch/sequence before
// its doorbell. Queue observations must be coherent and authenticated by that
// caller. This class neither reads fences nor frees GPU resources.
#ifndef BUILD34_EXACT_OWNERSHIP_H
#define BUILD34_EXACT_OWNERSHIP_H

#include <stdint.h>

namespace phx34_exact {

enum class Status : uint8_t {
    Ok, Invalid, Unknown, Full, Exhausted, Closed, Unsubmitted, Pending,
    Complete, Lost, InvalidObservation
};

// Epochs and lease serials must never wrap into an old identity. UINT64_MAX
// remains reserved, like the existing native LAST-sequence sentinel.
class Counter {
    uint64_t last_;
public:
    explicit Counter(uint64_t previous = 0) : last_(previous) {}
    bool take(uint64_t &value) {
        if (last_ >= UINT64_MAX - 1) return false;
        value = ++last_;
        return true;
    }
};

struct Ticket {
    uint64_t owner = 0, serial = 0;
    uint32_t slot = 0;
};
struct Receipt {
    uint64_t sequence = 0, generation = 0;
    uint32_t queue = 0;
};
struct QueueObservation {
    uint64_t generation = 0, submitted = 0, completed = 0;
    bool ready = false, faulted = false;
};

class Registry {
public:
    static constexpr uint32_t capacity = 64;
private:
    enum class Phase : uint8_t { Empty, Reserved, Pending, Complete, Lost };
    struct Entry {
        Receipt receipt;
        uint64_t serial = 0;
        Phase phase = Phase::Empty;
    };
    Entry entries_[capacity]{};
    const uint64_t owner_;
    Counter serial_;
    uint64_t newest_ = 0;
    uint32_t occupied_ = 0;
    bool closed_;

    Entry *entry(Ticket ticket) {
        if (ticket.owner != owner_ || !ticket.serial || ticket.slot >= capacity) return nullptr;
        Entry &e = entries_[ticket.slot];
        return e.phase != Phase::Empty && e.serial == ticket.serial ? &e : nullptr;
    }
    void clear(Entry &e) {
        e = Entry{};
        --occupied_;
    }
public:
    explicit Registry(uint64_t owner) : owner_(owner), closed_(!owner || owner == UINT64_MAX) {}
    Registry(const Registry &) = delete;
    Registry &operator=(const Registry &) = delete;

    uint32_t occupied() const { return occupied_; }

    Status reserve(Ticket &ticket) {
        if (closed_) return Status::Closed;
        for (uint32_t i = 0; i < capacity; ++i) {
            Entry &e = entries_[i];
            if (e.phase != Phase::Empty) continue;
            uint64_t serial;
            if (!serial_.take(serial)) return Status::Exhausted;
            e.serial = serial;
            e.phase = Phase::Reserved;
            ++occupied_;
            ticket = Ticket{owner_, serial, i};
            return Status::Ok;
        }
        return Status::Full;
    }

    // Only definitely unpublished reservations can be cancelled. A successful
    // publication is irrevocable here, including after uncertain transport.
    Status cancel(Ticket ticket) {
        if (closed_) return Status::Closed;
        Entry *e = entry(ticket);
        if (!e) return Status::Unknown;
        if (e->phase != Phase::Reserved) return Status::Invalid;
        clear(*e);
        return Status::Ok;
    }

    Status publish(Ticket ticket, Receipt receipt) {
        if (closed_) return Status::Closed;
        Entry *e = entry(ticket);
        if (!e) return Status::Unknown;
        if (e->phase != Phase::Reserved || !receipt.sequence || receipt.sequence == UINT64_MAX ||
            receipt.sequence <= newest_ || !receipt.generation || receipt.generation == UINT64_MAX ||
            receipt.queue >= 2) return Status::Invalid;
        e->receipt = receipt;
        e->phase = Phase::Pending;
        newest_ = receipt.sequence;
        return Status::Ok;
    }

    // A global sequence upper bound is not ownership. Missing/expired receipts
    // return Unknown even when a caller's conservative prefix covers the target.
    Status lookup(uint64_t sequence, Ticket &ticket) {
        if (closed_) return Status::Closed;
        if (!sequence || sequence == UINT64_MAX) return Status::Invalid;
        for (uint32_t i = 0; i < capacity; ++i) {
            Entry &e = entries_[i];
            if (e.phase != Phase::Empty && e.phase != Phase::Reserved && e.receipt.sequence == sequence) {
                ticket = Ticket{owner_, e.serial, i};
                return Status::Ok;
            }
        }
        return Status::Unknown;
    }

    Status observe(Ticket ticket, bool service_live, const QueueObservation queues[2]) {
        if (closed_) return Status::Closed;
        Entry *e = entry(ticket);
        if (!e) return Status::Unknown;
        if (e->phase == Phase::Reserved) return Status::Unsubmitted;
        if (e->phase == Phase::Lost) return Status::Lost;
        const QueueObservation &q = queues[e->receipt.queue];
        // Check identity/lifetime before interpreting any completion value.
        if (!service_live || !q.ready || q.faulted || q.generation != e->receipt.generation) {
            e->phase = Phase::Lost;
            return Status::Lost;
        }
        if (q.submitted == UINT64_MAX || q.submitted < e->receipt.sequence || q.completed > q.submitted)
            return Status::InvalidObservation;
        if (q.completed < e->receipt.sequence) {
            // A lower/stale observation cannot undo an already proved result.
            return e->phase == Phase::Complete ? Status::InvalidObservation : Status::Pending;
        }
        e->phase = Phase::Complete;
        return Status::Complete;
    }

    // This releases only a receipt, never a BO/VMID/page table. Lost or pending
    // work is retained for external drain/teardown; no eviction or reset exists.
    Status forget(Ticket ticket) {
        if (closed_) return Status::Closed;
        Entry *e = entry(ticket);
        if (!e) return Status::Unknown;
        if (e->phase != Phase::Complete) return Status::Invalid;
        clear(*e);
        return Status::Ok;
    }

    // Closing refuses all future mutations/observations without losing records.
    // Destruction of the containing native resources still needs a real drain.
    void close() { closed_ = true; }
};

static_assert(sizeof(Registry) <= 4096, "ownership metadata must remain bounded");
} // namespace phx34_exact
#endif
