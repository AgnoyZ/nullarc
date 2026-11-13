// SPDX-License-Identifier: MIT OR GPL-2.0-only
// One passive software snapshot request. No Hello, QueryInfo, polling or GPU calls.
#include <IOKit/IOKitLib.h>
#include <cstdio>
#include "../src/phxbringup/PhxNativeABI.h"
#include "../src/phxbringup/PhxAllocationDiagnostic.hpp"

static unsigned long long u64(uint64_t value) { return static_cast<unsigned long long>(value); }

int main(int argc, char **) {
    if (argc != 1) {
        std::fprintf(stderr, "usage: allocation-snapshot (administrator; one software snapshot)\n");
        return 64;
    }
    io_service_t service = IOServiceGetMatchingService(kIOMainPortDefault, IOServiceMatching("PhxBringup"));
    if (!service) { std::fprintf(stderr, "PhxBringup service unavailable\n"); return 69; }
    io_connect_t connection = 0;
    kern_return_t result = IOServiceOpen(service, mach_task_self(), PHXN_UC_TYPE, &connection);
    IOObjectRelease(service);
    if (result != KERN_SUCCESS) { std::fprintf(stderr, "snapshot open refused: 0x%08x\n", unsigned(result)); return 77; }
    phxn_allocation_snapshot snapshot{};
    size_t bytes = sizeof snapshot;
    uint32_t scalarCount = 0;
    const uint64_t version = PHXN_ALLOCATION_SNAPSHOT_VERSION;
    result = IOConnectCallMethod(connection, PHXN_SEL_ALLOCATION_SNAPSHOT, &version, 1,
                                 nullptr, 0, nullptr, &scalarCount, &snapshot, &bytes);
    const kern_return_t closeResult = IOServiceClose(connection);
    if (result != KERN_SUCCESS || closeResult != KERN_SUCCESS || bytes != sizeof snapshot || scalarCount ||
        snapshot.version != version || snapshot.reason_count != PHXN_ALLOCATION_REASON_COUNT ||
        snapshot.samples_per_reason != PHXN_ALLOCATION_SAMPLES) {
        std::fprintf(stderr, "snapshot refused or reply/close invalid: 0x%08x close=0x%08x\n", unsigned(result), unsigned(closeResult));
        return 74;
    }
    uint64_t total = 0;
    for (unsigned reason = 0; reason < PHXN_ALLOCATION_REASON_COUNT; ++reason) {
        const uint64_t count = snapshot.counts[reason];
        if (count > snapshot.observed) { std::fprintf(stderr, "invalid snapshot count\n"); return 74; }
        total = count > UINT64_MAX - total ? UINT64_MAX : total + count;
        for (unsigned i = 0; i < PHXN_ALLOCATION_SAMPLES && i < count; ++i) {
            const auto &r = snapshot.records[reason][i];
            if (r.reason != reason || !r.ordinal || r.ordinal > snapshot.observed || r.reserved || r.observation_valid > 1) {
                std::fprintf(stderr, "invalid snapshot record\n"); return 74;
            }
            for (const auto &q : r.queue) {
                if (q.reason > static_cast<uint32_t>(PhxQueueObservationReason::UnknownFence) || q.fence_read > 1 || q.reserved) {
                    std::fprintf(stderr, "invalid snapshot queue\n"); return 74;
                }
            }
        }
    }
    if (total != snapshot.observed) { std::fprintf(stderr, "invalid snapshot total\n"); return 74; }
    static const char *names[] = {"map-retirement-pending", "map-retirement-invalid",
        "unmap-retirement-pending", "unmap-retirement-invalid", "map-pending-overlap",
        "host-descriptor", "host-prepare"};
    std::printf("{\"version\":%u,\"kext_build\":%u,\"observed\":%llu,\"samples_per_reason\":%u,\"reasons\":[",
                snapshot.version, snapshot.kext_build, u64(snapshot.observed), snapshot.samples_per_reason);
    for (unsigned reason = 0; reason < PHXN_ALLOCATION_REASON_COUNT; ++reason) {
        std::printf("%s{\"reason\":\"%s\",\"count\":%llu,\"records\":[", reason ? "," : "", names[reason], u64(snapshot.counts[reason]));
        for (unsigned i = 0; i < PHXN_ALLOCATION_SAMPLES && i < snapshot.counts[reason]; ++i) {
            const auto &r = snapshot.records[reason][i];
            std::printf("%s{\"ordinal\":%llu,\"status\":%u,\"status_hex\":\"0x%08x\",\"bytes\":%llu,"
                        "\"last_seq\":%llu,\"submitted\":%llu,\"retired\":%llu,\"observation_valid\":%u,\"queues\":[",
                        i ? "," : "", u64(r.ordinal), r.status, r.status, u64(r.bytes),
                        u64(r.last_seq), u64(r.submitted), u64(r.retired), r.observation_valid);
            for (unsigned q = 0; q < 2; ++q) {
                const auto &o = r.queue[q];
                std::printf("%s{\"reason\":\"%s\",\"fence_read\":%u,\"done\":%llu,\"floor\":%llu,\"count\":%u,\"first_pending\":%llu}",
                            q ? "," : "", phxQueueObservationName(static_cast<PhxQueueObservationReason>(o.reason)),
                            o.fence_read, u64(o.done), u64(o.floor), o.count, u64(o.first_pending));
            }
            std::printf("]}");
        }
        std::printf("]}");
    }
    std::printf("]}\n");
    return 0;
}
