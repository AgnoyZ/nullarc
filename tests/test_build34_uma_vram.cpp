#include "../tools/build34_uma_vram.h"

#include <array>
#include <cstdio>
#include <cstdlib>

using namespace build34::uma;

static constexpr Geometry kGeometry{kMcBase, 0x200000000ull, 4ull << 30, kBarBytes};
static constexpr Range kWindow{kBarBytes, kPilotBytes};
static constexpr Reservations kReserved{{0, 16ull << 20}, {128ull << 20, 64ull << 20},
                                         {(4ull << 30) - (64ull << 10), 64ull << 10}, nullptr, 0};
static uint64_t checks = 0;

static void check(bool value) {
    if (!value) {
        std::fprintf(stderr, "build34 UMA check %llu failed\n", static_cast<unsigned long long>(checks + 1));
        std::abort();
    }
    ++checks;
}

static void admission() {
    Pool pool;
    Allocation allocation{};
    check(!pool.reserve(1, kPageBytes, kPageBytes, allocation));
    check(!pool.admit({kMcBase + 1, kGeometry.backingBase, kGeometry.bytes, kBarBytes}, kWindow, kReserved));
    check(!pool.admit({kMcBase, kAddressLimit - (16ull << 20), kGeometry.bytes, kBarBytes}, kWindow, kReserved));
    check(!pool.admit({kMcBase, 0, kGeometry.bytes, kBarBytes}, kWindow, kReserved));
    check(!pool.admit({kMcBase, kGeometry.backingBase, kGeometry.bytes, kBarBytes * 2}, kWindow, kReserved));
    check(!pool.admit(kGeometry, {kBarBytes - kPageBytes, kPageBytes}, kReserved));
    check(!pool.admit(kGeometry, {kBarBytes, kPilotBytes + kPageBytes}, kReserved));
    check(!pool.admit(kGeometry, {kBarBytes + 1, kPageBytes}, kReserved));
    check(!pool.admit(kGeometry, {kGeometry.bytes - kPageBytes, UINT64_MAX}, kReserved));
    check(!pool.admit(kGeometry, {kGeometry.bytes - kPageBytes, kPageBytes}, kReserved));
    check(!pool.admit(kGeometry, kWindow, {}));

    Reservations reservations = kReserved;
    reservations.scanout = {kWindow.end() - 1, 1};
    check(!pool.admit(kGeometry, kWindow, reservations));
    reservations = kReserved;
    reservations.firmware = {kWindow.offset, 1};
    check(!pool.admit(kGeometry, kWindow, reservations));
    reservations = kReserved;
    reservations.extraCount = 1;
    check(!pool.admit(kGeometry, kWindow, reservations));
    const Range extra[] = {{kWindow.offset - 1, 2}, {kWindow.end(), kPageBytes}};
    reservations.extra = extra;
    check(!pool.admit(kGeometry, kWindow, reservations));
    reservations.extra = extra + 1;
    check(pool.admit(kGeometry, kWindow, reservations));
    check(!pool.admit(kGeometry, kWindow, reservations));
    check(pool.usage().capacity == kPilotBytes);
}

static void lifecycle() {
    Pool pool;
    check(pool.admit(kGeometry, kWindow, kReserved));
    constexpr uint64_t owner = 123, otherOwner = 456;
    Allocation allocation{};
    MappingId mapping{};
    Leaf leaf{123, 456};
    check(!pool.reserve(0, 1, kPageBytes, allocation));
    check(!pool.reserve(owner, UINT64_MAX, kPageBytes, allocation));
    check(!pool.reserve(owner, 1, 8193, allocation));
    check(pool.reserve(owner, kPageBytes + 1, 65536, allocation));
    check(allocation.range.offset == kWindow.offset && allocation.range.bytes == 2 * kPageBytes);
    check(allocation.mcAddress == kGeometry.mcBase + kWindow.offset);
    check(allocation.backingAddress == kGeometry.backingBase + kWindow.offset);
    check(!pool.finishZero(otherOwner, allocation.id, Completion::Complete));
    check(!pool.finishZero(owner, allocation.id, Completion::Pending));
    check(!pool.release(owner, allocation.id));
    check(!pool.beginMap(owner, allocation.id, 0x10000, {0, kPageBytes}, Access::ReadWrite, mapping));
    check(pool.finishZero(owner, allocation.id, Completion::Complete));
    check(!pool.beginMap(owner, allocation.id, 0x10000, {kPageBytes, UINT64_MAX}, Access::ReadOnly, mapping));
    check(!pool.beginMap(owner, allocation.id, kAddressLimit - kPageBytes, {0, 2 * kPageBytes}, Access::ReadOnly, mapping));
    check(!pool.beginMap(owner, allocation.id, 0x10001, {0, kPageBytes}, Access::ReadOnly, mapping));
    check(!pool.beginMap(owner, allocation.id, 0x10000, {0, kPageBytes}, static_cast<Access>(2), mapping));
    check(pool.beginMap(owner, allocation.id, 0x10000, {kPageBytes, kPageBytes}, Access::ReadOnly, mapping));
    check(!pool.encodePte(otherOwner, mapping, 0, leaf));
    check(!pool.encodePte(owner, mapping, kPageBytes, leaf));
    check(!pool.encodePte(owner, mapping, 1, leaf));
    check(leaf.va == 123 && leaf.value == 456);
    check(pool.encodePte(owner, mapping, 0, leaf));
    check(leaf.va == 0x10000 && leaf.value == (allocation.backingAddress + kPageBytes + 0x21));
    check(!pool.release(owner, allocation.id));
    check(!pool.finishMap(owner, mapping, Completion::Pending));
    check(pool.finishMap(owner, mapping, Completion::Complete));
    check(!pool.encodePte(owner, mapping, 0, leaf));
    check(!pool.finishUnmap(owner, mapping, Completion::Complete));
    check(!pool.beginUnmap(owner, mapping, Completion::Pending));
    check(!pool.release(owner, allocation.id));
    check(pool.beginUnmap(owner, mapping, Completion::Complete));
    check(!pool.finishUnmap(owner, mapping, Completion::Pending));
    check(!pool.release(owner, allocation.id));
    check(pool.finishUnmap(owner, mapping, Completion::Complete));
    MappingId next{};
    check(pool.beginMap(owner, allocation.id, 0x20000, {0, 2 * kPageBytes}, Access::ReadWrite, next));
    check(!pool.finishMap(owner, mapping, Completion::Complete));
    check(pool.encodePte(owner, next, kPageBytes, leaf));
    check(leaf.va == 0x21000 && leaf.value == (allocation.backingAddress + kPageBytes + 0x61));
    check(pool.finishMap(owner, next, Completion::Complete));
    check(pool.beginUnmap(owner, next, Completion::Complete));
    check(pool.finishUnmap(owner, next, Completion::Complete));
    check(!pool.release(otherOwner, allocation.id));
    check(pool.release(owner, allocation.id));
    check(!pool.release(owner, allocation.id));
    Allocation reused{};
    check(pool.reserve(owner, 1, kPageBytes, reused));
    check(reused.id.slot == allocation.id.slot && reused.id.serial != allocation.id.serial);
    check(!pool.finishZero(owner, allocation.id, Completion::Complete));
    check(reused.range.offset == allocation.range.offset);
}

static void quarantine() {
    for (unsigned phase = 0; phase < 4; ++phase) {
        Pool pool;
        check(pool.admit(kGeometry, kWindow, kReserved));
        Allocation held{}, other{};
        MappingId mapping{};
        check(pool.reserve(1, 1, kPageBytes, held));
        check(pool.reserve(2, 1, kPageBytes, other));
        check(pool.finishZero(2, other.id, Completion::Complete));
        if (phase == 0) {
            check(!pool.finishZero(1, held.id, Completion::Uncertain));
        } else {
            check(pool.finishZero(1, held.id, Completion::Complete));
            check(pool.beginMap(1, held.id, 0x10000, {0, kPageBytes}, Access::ReadOnly, mapping));
            if (phase == 1) {
                check(!pool.finishMap(1, mapping, Completion::Uncertain));
            } else {
                check(pool.finishMap(1, mapping, Completion::Complete));
                if (phase == 2) {
                    check(!pool.beginUnmap(1, mapping, Completion::Uncertain));
                } else {
                    check(pool.beginUnmap(1, mapping, Completion::Complete));
                    check(!pool.finishUnmap(1, mapping, Completion::Uncertain));
                }
            }
        }
        check(!pool.release(1, held.id));
        check(!pool.release(2, other.id));
        check(!pool.reserve(3, 1, kPageBytes, held));
        check(!pool.admit(kGeometry, kWindow, kReserved));
        const Usage usage = pool.usage();
        check(usage.faulted && usage.quarantined == kPageBytes && usage.reserved == 2 * kPageBytes);
    }
}

static void overlapAndCapacity() {
    Pool pool;
    check(pool.admit(kGeometry, kWindow, kReserved));
    std::array<Allocation, Pool::kSlots> allocations{};
    for (size_t index = 0; index < allocations.size(); ++index) {
        const uint64_t owner = index == 2 ? 2 : 1;
        check(pool.reserve(owner, 2 * kPageBytes, kPageBytes, allocations[index]));
        check(pool.finishZero(owner, allocations[index].id, Completion::Complete));
    }
    Allocation extra{};
    check(!pool.reserve(1, 1, kPageBytes, extra));
    check(pool.usage().reserved == allocations.size() * 2 * kPageBytes);

    MappingId first{}, second{}, independent{};
    check(pool.beginMap(1, allocations[0].id, 0x10000, {0, 2 * kPageBytes}, Access::ReadOnly, first));
    check(!pool.beginMap(1, allocations[1].id, 0x11000, {0, kPageBytes}, Access::ReadOnly, second));
    check(pool.beginMap(2, allocations[2].id, 0x11000, {0, kPageBytes}, Access::ReadOnly, independent));
    check(pool.finishMap(1, first, Completion::Complete));
    check(!pool.beginMap(1, allocations[1].id, 0x11000, {0, kPageBytes}, Access::ReadOnly, second));
    check(pool.beginUnmap(1, first, Completion::Complete));
    check(!pool.beginMap(1, allocations[1].id, 0x11000, {0, kPageBytes}, Access::ReadOnly, second));
    check(pool.finishUnmap(1, first, Completion::Complete));
    check(pool.beginMap(1, allocations[1].id, 0x11000, {0, kPageBytes}, Access::ReadOnly, second));
    check(pool.release(1, allocations[0].id));
    check(pool.reserve(1, 1, kPageBytes, extra));
}

static void allocationStress() {
    Pool pool;
    constexpr Range window{kBarBytes + kPageBytes, 128 * kPageBytes};
    check(pool.admit(kGeometry, window, kReserved));
    std::array<Allocation, Pool::kSlots> live{};
    uint32_t random = 0x900d9c35u;
    for (unsigned step = 0; step < 8000; ++step) {
        random = random * 1664525u + 1013904223u;
        const size_t slot = (random >> 16) % live.size();
        if (live[slot].id.serial) {
            check(pool.release(slot + 1, live[slot].id));
            live[slot] = {};
        } else {
            const uint64_t alignment = kPageBytes << ((random >> 10) % 4);
            const uint64_t bytes = (1 + ((random >> 5) % 8)) * kPageBytes;
            std::array<bool, 128> occupied{};
            for (const auto &entry : live) {
                if (!entry.id.serial) continue;
                for (uint64_t offset = entry.range.offset; offset < entry.range.end(); offset += kPageBytes)
                    occupied[(offset - window.offset) / kPageBytes] = true;
            }
            uint64_t expected = 0;
            for (uint64_t start = window.offset; start + bytes <= window.end(); start += kPageBytes) {
                if (start & (alignment - 1)) continue;
                bool free = true;
                for (uint64_t offset = start; offset < start + bytes; offset += kPageBytes)
                    free = free && !occupied[(offset - window.offset) / kPageBytes];
                if (free) { expected = start; break; }
            }
            check(pool.reserve(slot + 1, bytes, alignment, live[slot]) == (expected != 0));
            if (expected) {
                check(live[slot].range.offset == expected && live[slot].range.bytes == bytes);
                check(pool.finishZero(slot + 1, live[slot].id, Completion::Complete));
            }
        }
        uint64_t total = 0;
        for (const auto &entry : live) total += entry.range.bytes;
        check(pool.usage().reserved == total);
    }
}

int main() {
    admission();
    lifecycle();
    quarantine();
    overlapAndCapacity();
    allocationStress();
    std::printf("PASS build34 UMA: %llu checks (CPU only)\n", static_cast<unsigned long long>(checks));
}
