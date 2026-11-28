// SPDX-License-Identifier: MIT OR GPL-2.0-only
#include "../src/phxbringup/PhxUmaPool.h"

#include <array>
#include <cstdio>
#include <cstdlib>
#include <cstring>

using namespace phx::uma;

static uint64_t gChecks = 0;

static void check(bool condition, const char *label) {
    if (!condition) {
        std::fprintf(stderr, "FAIL phx_uma_pool check %llu: %s\n",
                     static_cast<unsigned long long>(gChecks + 1), label);
        std::abort();
    }
    ++gChecks;
}

static void storeLe(uint8_t *dst, unsigned width, uint64_t value) {
    for (unsigned idx = 0; idx < width; ++idx)
        dst[idx] = static_cast<uint8_t>(value >> (idx * 8u));
}

static void initBootArgs(uint8_t args[4096], uint32_t mapPhys, uint32_t mapLen, uint32_t stride) {
    std::memset(args, 0, 4096);
    storeLe(args + 0, 2, 1);
    storeLe(args + 2, 2, 2);
    args[4] = 64;
    storeLe(args + 1032, 4, mapPhys);
    storeLe(args + 1036, 4, mapLen);
    storeLe(args + 1040, 4, stride);
    storeLe(args + 1044, 4, 1);
}

static void initDescriptor(uint8_t *entry, uint32_t kind, uint64_t phys, uint64_t pages, uint64_t attrs) {
    std::memset(entry, 0, 48);
    storeLe(entry + 0, 4, kind);
    storeLe(entry + 8, 8, phys);
    storeLe(entry + 24, 8, pages);
    storeLe(entry + 32, 8, attrs);
}

static void testGeometryAndWindows() {
    const Geometry live780m{kExpectedMcBase, 0x780000000ull, 4ull << 30, kExpectedBar0Bytes};
    check(geometryValid(live780m), "live 780M 4 GiB geometry valid");
    check(!geometryValid({kExpectedMcBase + 4096, 0x780000000ull, 4ull << 30, kExpectedBar0Bytes}), "bad mcBase");
    check(!geometryValid({kExpectedMcBase, 0, 4ull << 30, kExpectedBar0Bytes}), "zero physBase");
    check(!geometryValid({kExpectedMcBase, 0x780000000ull, 256ull << 20, kExpectedBar0Bytes}), "fb <= bar0");
    check(!geometryValid({kExpectedMcBase, 0x780000000ull, 4ull << 30, 128ull << 20}), "bad bar0 size");

    const uint64_t discOff = (4ull << 30) - kDiscoveryTmrOffset;
    const DiscoveryProbe goodDisc = classifyDiscoveryProbe(live780m.fbBytes, 4096u, 3u, discOff, kDiscoveryTmrSize,
                                                           kDiscoverySignature);
    check(goodDisc.memsizeMatchesFb && goodDisc.signatureValid, "good discovery probe");

    const WindowPlan plan = planHighUmaWindows(live780m, goodDisc);
    check(plan.valid, "window plan valid");
    check(plan.pilotWindow.offset == kExpectedBar0Bytes && plan.pilotWindow.bytes == kPilotWindowBytes,
          "pilot window [256 MiB, 320 MiB)");
    check(plan.fullHighWindow.offset == kExpectedBar0Bytes &&
              plan.fullHighWindow.bytes == (4ull << 30) - kExpectedBar0Bytes - kDefaultTopReserveBytes,
          "full high window [256 MiB, 4032 MiB)");
    check(plan.topReserveBytes == kDefaultTopReserveBytes, "top reserve 64 MiB");
    check(!rangesOverlap(plan.fullHighWindow, plan.discoveryRange), "full window clear of discovery");

    const DiscoveryProbe lowDisc = classifyDiscoveryProbe(live780m.fbBytes, 4096u, 3u,
                                                          (4ull << 30) - (128ull << 20), kDiscoveryTmrSize,
                                                          kDiscoverySignature);
    const WindowPlan tightPlan = planHighUmaWindows(live780m, lowDisc);
    check(tightPlan.valid && tightPlan.fullHighWindow.end() == ((4ull << 30) - (128ull << 20)),
          "upper limit clamps below discovery offset");

    const DiscoveryProbe badSig = classifyDiscoveryProbe(live780m.fbBytes, 4096u, 3u, discOff, kDiscoveryTmrSize,
                                                         0xDEADBEEFu);
    check(!planHighUmaWindows(live780m, badSig).valid, "bad discovery signature refused");

    const DiscoveryProbe mismatchMb = classifyDiscoveryProbe(live780m.fbBytes, 2048u, 3u, discOff, kDiscoveryTmrSize,
                                                             kDiscoverySignature);
    check(!planHighUmaWindows(live780m, mismatchMb).valid, "memsize mismatch refused");

    check(aliasVerificationMatches(64, 64, 8), "alias match minimum");
    check(!aliasVerificationMatches(63, 64, 8), "alias single mismatch fails");
    check(!aliasVerificationMatches(64, 64, 7), "alias too few non-zero fails");
    check(!aliasVerificationMatches(32, 32, 16), "alias too few samples fails");
}

static void testBootMapClassifier() {
    constexpr uint32_t kMapPhys = 0x10000u;
    constexpr uint32_t kStride = 48u;
    uint8_t args[4096];
    uint8_t entries[3 * kStride];

    const uint64_t umaBase = 0x780000000ull;
    const uint64_t highBase = umaBase + kExpectedBar0Bytes;
    const uint64_t highBytes = (3ull << 30) + (704ull << 20);

    initBootArgs(args, kMapPhys, sizeof(entries), kStride);
    initDescriptor(entries + 0 * kStride, 7u, 0x100000000ull, (umaBase - 0x100000000ull) >> 12, 0);
    initDescriptor(entries + 1 * kStride, 0u, umaBase, (4ull << 30) >> 12, 0);
    initDescriptor(entries + 2 * kStride, 11u, 0x8b0000000ull, kExpectedBar0Bytes >> 12, 0);

    check(classifyBootMap(args, sizeof(args), entries, sizeof(entries), kMapPhys, highBase, highBytes) ==
              HostExclusionStatus::ReservedTypeOnly,
          "full 4 GiB reserved range accepted");

    initDescriptor(entries + 1 * kStride, 7u, umaBase, (4ull << 30) >> 12, 0);
    check(classifyBootMap(args, sizeof(args), entries, sizeof(entries), kMapPhys, highBase, kPilotWindowBytes) ==
              HostExclusionStatus::HostUsableOverlap,
          "conventional memory overlap rejected");

    initDescriptor(entries + 1 * kStride, 10u, umaBase, (4ull << 30) >> 12, 0);
    check(classifyBootMap(args, sizeof(args), entries, sizeof(entries), kMapPhys, highBase, kPilotWindowBytes) ==
              HostExclusionStatus::OtherOverlap,
          "ACPI NVS overlap classified as OtherOverlap");

    initDescriptor(entries + 1 * kStride, 0u, umaBase, (4ull << 30) >> 12, 1ull << 63);
    check(classifyBootMap(args, sizeof(args), entries, sizeof(entries), kMapPhys, highBase, kPilotWindowBytes) ==
              HostExclusionStatus::OtherOverlap,
          "runtime attribute classified as OtherOverlap");

    initDescriptor(entries + 1 * kStride, 0u, umaBase, (260ull << 20) >> 12, 0);
    check(classifyBootMap(args, sizeof(args), entries, sizeof(entries), kMapPhys, highBase, kPilotWindowBytes) ==
              HostExclusionStatus::Incomplete,
          "partial reserved coverage classified as Incomplete");

    initDescriptor(entries + 1 * kStride, 0u, umaBase, (4ull << 30) >> 12, 0);
    check(classifyBootMap(args, sizeof(args), entries, sizeof(entries), kMapPhys + 8, highBase, kPilotWindowBytes) ==
              HostExclusionStatus::Refused,
          "mismatched map physical base refused");
}

static void testAllocatorLifecycleAndStress() {
    const Geometry geom{kExpectedMcBase, 0x780000000ull, 4ull << 30, kExpectedBar0Bytes};
    const Range pilot{kExpectedBar0Bytes, kPilotWindowBytes};
    const Range disc{(4ull << 30) - kDiscoveryTmrOffset, kDiscoveryTmrOffset};

    HighUmaAllocator pool;
    HighUmaAllocator::Allocation alloc{};
    check(!pool.allocate(1, kPageBytes, kPageBytes, alloc), "cannot allocate before admit");
    check(!pool.admit(geom, pilot, disc, HostExclusionStatus::Incomplete, true), "incomplete host map refused");
    check(!pool.admit(geom, pilot, disc, HostExclusionStatus::ReservedTypeOnly, false), "unverified alias refused");
    check(!pool.admit(geom, {kExpectedBar0Bytes - kPageBytes, kPilotWindowBytes}, disc,
                      HostExclusionStatus::ReservedTypeOnly, true),
          "window overlapping BAR0 refused");
    check(pool.admit(geom, pilot, disc, HostExclusionStatus::ReservedTypeOnly, true), "pilot admitted");
    check(!pool.admit(geom, pilot, disc, HostExclusionStatus::ReservedTypeOnly, true), "double admit refused");

    check(pool.allocate(10, 8192, 65536, alloc), "64 KiB aligned alloc");
    check(alloc.vramOffset == kExpectedBar0Bytes && alloc.bytes == 8192, "alloc offset and size");
    check(alloc.physBase == geom.physBase + kExpectedBar0Bytes, "alloc physBase");
    check(alloc.mcBase == geom.mcBase + kExpectedBar0Bytes, "alloc mcBase");

    uint64_t pteRo = 0, pteRw = 0;
    check(pool.encodePagePte(10, alloc.slot, alloc.serial, 0, false, pteRo), "encode RO local PTE");
    check(pool.encodePagePte(10, alloc.slot, alloc.serial, 4096, true, pteRw), "encode RW local PTE");
    check(pteRo == ((alloc.physBase & kPtAddrMask) | kPteLocalReadFlags), "RO local PTE value");
    check(pteRw == (((alloc.physBase + 4096) & kPtAddrMask) | kPteLocalRwFlags), "RW local PTE value");
    // amdgpu_vm.h: VALID=0x1 SYSTEM=0x2 SNOOPED=0x4 EXECUTABLE=0x10 READABLE=0x20 WRITEABLE=0x40
    check((pteRw & 0x6ull) == 0, "local PTE clears SYSTEM and SNOOPED bits");
    check((pteRo & 0x31ull) == 0x31ull && (pteRw & 0x31ull) == 0x31ull, "local PTE keeps VALID, EXEC and READ bits");
    check((pteRw & 0x40ull) != 0 && (pteRo & 0x40ull) == 0, "WRITE only on the writable encoding");
    check(!pool.encodePagePte(11, alloc.slot, alloc.serial, 0, true, pteRw), "wrong owner refused");
    check(!pool.encodePagePte(10, alloc.slot, alloc.serial, 8192, true, pteRw), "out of range offset refused");
    check(!pool.release(11, alloc.slot, alloc.serial), "wrong owner release refused");
    check(pool.release(10, alloc.slot, alloc.serial), "owner release succeeds");
    check(!pool.release(10, alloc.slot, alloc.serial), "double release refused");

    HighUmaAllocator::Allocation qAlloc{};
    check(pool.allocate(20, 4096, 4096, qAlloc), "pre-quarantine alloc");
    check(pool.quarantine(20, qAlloc.slot, qAlloc.serial), "quarantine alloc");
    check(pool.stats().faulted && pool.stats().quarantinedBytes == 4096 && pool.freeBytes() == 0,
          "faulted pool reports zero free");
    check(!pool.allocate(20, 4096, 4096, alloc), "alloc refused after fault");
    check(!pool.release(20, qAlloc.slot, qAlloc.serial), "quarantined release refused");
    check(!pool.encodePagePte(20, qAlloc.slot, qAlloc.serial, 0, true, pteRw), "PTE encode refused after fault");

    pool.reset();
    const Range smallWindow{kExpectedBar0Bytes, 256 * kPageBytes};
    check(pool.admit(geom, smallWindow, disc, HostExclusionStatus::ReservedTypeOnly, true), "stress window admitted");
    std::array<HighUmaAllocator::Allocation, 32> live{};
    std::array<bool, 256> bitmap{};
    uint32_t rng = 0x51a7c0deu;
    for (unsigned step = 0; step < 5000; ++step) {
        rng = rng * 1664525u + 1013904223u;
        const size_t idx = (rng >> 16) % live.size();
        if (live[idx].serial != 0) {
            check(pool.release(idx + 1, live[idx].slot, live[idx].serial), "stress release");
            const uint64_t startPage = (live[idx].vramOffset - smallWindow.offset) / kPageBytes;
            const uint64_t count = live[idx].bytes / kPageBytes;
            for (uint64_t page = 0; page < count; ++page)
                bitmap[startPage + page] = false;
            live[idx] = {};
        } else {
            const uint64_t align = kPageBytes << ((rng >> 10) % 4);
            const uint64_t pages = 1 + ((rng >> 5) % 12);
            const uint64_t bytes = pages * kPageBytes;
            uint64_t expectedOff = 0;
            for (uint64_t off = smallWindow.offset; off + bytes <= smallWindow.end(); off += kPageBytes) {
                if (off & (align - 1))
                    continue;
                bool free = true;
                const uint64_t first = (off - smallWindow.offset) / kPageBytes;
                for (uint64_t page = 0; page < pages; ++page)
                    if (bitmap[first + page]) {
                        free = false;
                        break;
                    }
                if (free) {
                    expectedOff = off;
                    break;
                }
            }
            const bool ok = pool.allocate(idx + 1, bytes, align, live[idx]);
            check(ok == (expectedOff != 0), "stress allocator matches bitmap");
            if (ok) {
                check(live[idx].vramOffset == expectedOff && live[idx].bytes == bytes, "stress offset matches");
                const uint64_t first = (expectedOff - smallWindow.offset) / kPageBytes;
                for (uint64_t page = 0; page < pages; ++page)
                    bitmap[first + page] = true;
            }
        }
    }
}

int main() {
    testGeometryAndWindows();
    testBootMapClassifier();
    testAllocatorLifecycleAndStress();
    std::printf("PASS test_phx_uma_pool: %llu checks\n", static_cast<unsigned long long>(gChecks));
    return 0;
}
