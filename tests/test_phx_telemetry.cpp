// SPDX-License-Identifier: MIT
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "PhxTelemetry.h"

using phx::telemetry::PhxTelemetryTracker;
using phx::telemetry::clampFallbackNs;
using phx::telemetry::ticksToNs;

static void testTicksToNs() {
    assert(ticksToNs(0, 1000) == 0);
    assert(ticksToNs(1000, 1000) == 0);
    assert(ticksToNs(2000, 1000) == 0);
    assert(ticksToNs(1000, 1100) == 1000ull);
    assert(ticksToNs(50000, 150000) == 1000000ull);
    assert(ticksToNs(10, 10 + 1000000001ull) == 0);
    assert(ticksToNs(10, 10 + 1000000000ull) == 10000000000ull);

    assert(clampFallbackNs(100, 100) == 0);
    assert(clampFallbackNs(200, 100) == 0);
    assert(clampFallbackNs(1000, 5000) == 4000);
    assert(clampFallbackNs(1000, 1000 + 200000000ull) == 50000000ull);
}

static void testPidLifecycleAndMemory() {
    PhxTelemetryTracker tracker;
    tracker.reset();

    assert(tracker.clientOpen(100, "WindowServer"));
    assert(tracker.clientOpen(100, "WindowServer"));
    assert(tracker.clientOpen(200, "Safari"));
    assert(!tracker.clientOpen(0, "invalid"));
    assert(!tracker.clientOpen(-5, "invalid"));

    tracker.addMemory(100, 64 * 1024 * 1024, 16 * 1024 * 1024, 4 * 1024 * 1024);
    tracker.addMemory(200, 128 * 1024 * 1024, 32 * 1024 * 1024, 0);
    tracker.noteSubmit(100, 123456789ull);
    tracker.addGpuTime(100, 25000000ull, true);
    tracker.noteSubmit(200, 223456789ull);
    tracker.addGpuTime(200, 50000000ull, false);

    PhxGpuTelemetrySnapshot snap{};
    tracker.snapshot(snap, 1000000000ull, 4ull << 30, 2ull << 30);
    assert(snap.version == PHX_TELEMETRY_ABI_VERSION);
    assert(snap.pidCount == 2);
    assert(snap.vramTotalBytes == (4ull << 30));
    assert(snap.vramUsedBytes == (192ull << 20));
    assert(snap.gttTotalBytes == (2ull << 30));
    assert(snap.gttUsedBytes == (48ull << 20));
    assert(snap.hostUsedBytes == (4ull << 20));
    assert(snap.totalGpuBusyNs == 75000000ull);
    assert(tracker.hwTsCount() == 1);
    assert(tracker.fallbackTsCount() == 1);

    assert(snap.pids[0].pid == 100);
    assert(snap.pids[0].activeClients == 2);
    assert(snap.pids[0].accumulatedGpuNs == 25000000ull);
    assert(snap.pids[0].lastSubmittedAbs == 123456789ull);
    assert(snap.pids[0].vramBytes == (64ull << 20));
    assert(snap.pids[0].gttBytes == (16ull << 20));
    assert(snap.pids[0].hostBytes == (4ull << 20));
    assert(snap.pids[0].submitCount == 1);
    assert(strcmp(snap.pids[0].procName, "WindowServer") == 0);

    tracker.clientClose(100);
    tracker.snapshot(snap, 1050000000ull, 4ull << 30, 2ull << 30);
    assert(snap.pidCount == 2);
    assert(snap.pids[0].activeClients == 1);

    tracker.clientClose(200);
    tracker.snapshot(snap, 1050000000ull, 4ull << 30, 2ull << 30);
    assert(snap.pidCount == 2);

    tracker.addMemory(200, -(256 * 1024 * 1024), -(64 * 1024 * 1024), 0);
    tracker.snapshot(snap, 1050000000ull, 4ull << 30, 2ull << 30);
    assert(snap.pidCount == 1);
    assert(snap.pids[0].pid == 100);
    assert(snap.vramUsedBytes == 0);
}

static void testUtilSlidingWindow() {
    PhxTelemetryTracker tracker;
    tracker.reset();
    assert(tracker.clientOpen(42, "Bench"));

    assert(tracker.computeUtilPct(1000000000ull) == 0);

    tracker.addGpuTime(42, 50000000ull, true);
    assert(tracker.computeUtilPct(1050000000ull) == 0);
    assert(tracker.computeUtilPct(1200000000ull) == 25);

    assert(tracker.computeUtilPct(1250000000ull) == 25);

    tracker.addGpuTime(42, 300000000ull, true);
    assert(tracker.computeUtilPct(1400000000ull) == 100);

    assert(tracker.computeUtilPct(1600000000ull) == 0);
}

static void testMaxPidsBound() {
    PhxTelemetryTracker tracker;
    tracker.reset();
    for (int32_t pid = 1; pid <= static_cast<int32_t>(PHX_TELEMETRY_MAX_PIDS); ++pid) {
        assert(tracker.clientOpen(pid, "proc"));
    }
    assert(!tracker.clientOpen(9999, "overflow"));
    tracker.clientClose(1);
    assert(tracker.clientOpen(9999, "reused"));
}

int main() {
    testTicksToNs();
    testPidLifecycleAndMemory();
    testUtilSlidingWindow();
    testMaxPidsBound();
    printf("test_phx_telemetry: PASS\n");
    return 0;
}
