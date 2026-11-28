// SPDX-License-Identifier: MIT
// Freestanding GPU telemetry tracker & cross-kext snapshot ABI for PhxBringup <-> PhxAccel.
#pragma once

#include <stddef.h>
#include <stdint.h>

#define PHX_TELEMETRY_FN "phxGpuTelemetry"
#define PHX_TELEMETRY_ABI_VERSION 1u
#define PHX_TELEMETRY_MAX_PIDS 128u
#define PHX_TELEMETRY_NAME_LEN 32u

struct PhxPidTelemetry {
    int32_t pid;
    uint32_t activeClients;
    uint64_t accumulatedGpuNs;
    uint64_t lastSubmittedAbs;
    uint64_t vramBytes;
    uint64_t gttBytes;
    uint64_t hostBytes;
    uint64_t submitCount;
    char procName[PHX_TELEMETRY_NAME_LEN];
};

struct PhxGpuTelemetrySnapshot {
    uint32_t version;
    uint32_t pidCount;
    uint64_t vramTotalBytes;
    uint64_t vramUsedBytes;
    uint64_t gttTotalBytes;
    uint64_t gttUsedBytes;
    uint64_t hostUsedBytes;
    uint64_t totalGpuBusyNs;
    uint32_t gpuUtilPct;
    uint32_t reserved;
    PhxPidTelemetry pids[PHX_TELEMETRY_MAX_PIDS];
};

namespace phx::telemetry {

static constexpr uint64_t kGoldenTscNsPerTick = 10ull;       // Phoenix 100 MHz GPU clock counter
static constexpr uint64_t kMaxSingleSubmitNs = 10000000000ull; // 10 s sanity cap
static constexpr uint64_t kFallbackSubmitMaxNs = 50000000ull;  // 50 ms cap when HW timestamps disabled
static constexpr uint64_t kMinUtilWindowNs = 100000000ull;     // 100 ms sliding window minimum

inline void copyProcName(char dst[PHX_TELEMETRY_NAME_LEN], const char *src) {
    if (!src) {
        dst[0] = '\0';
        return;
    }
    size_t idx = 0;
    for (; idx + 1 < PHX_TELEMETRY_NAME_LEN && src[idx] != '\0'; ++idx) {
        dst[idx] = src[idx];
    }
    dst[idx] = '\0';
}

inline uint64_t ticksToNs(uint64_t tsStart, uint64_t tsEnd) {
    if (tsStart == 0 || tsEnd <= tsStart) {
        return 0;
    }
    const uint64_t deltaTicks = tsEnd - tsStart;
    if (deltaTicks > (kMaxSingleSubmitNs / kGoldenTscNsPerTick)) {
        return 0;
    }
    return deltaTicks * kGoldenTscNsPerTick;
}

inline uint64_t clampFallbackNs(uint64_t submitNs, uint64_t retireNs) {
    if (retireNs <= submitNs) {
        return 0;
    }
    const uint64_t deltaNs = retireNs - submitNs;
    return deltaNs > kFallbackSubmitMaxNs ? kFallbackSubmitMaxNs : deltaNs;
}

class PhxTelemetryTracker {
public:
    void reset() {
        for (uint32_t idx = 0; idx < PHX_TELEMETRY_MAX_PIDS; ++idx) {
            entries_[idx] = Entry{};
        }
        vramUsedBytes_ = 0;
        gttUsedBytes_ = 0;
        hostUsedBytes_ = 0;
        totalGpuBusyNs_ = 0;
        hwTsCount_ = 0;
        fallbackTsCount_ = 0;
        utilWindowStartNs_ = 0;
        utilWindowStartBusyNs_ = 0;
        cachedUtilPct_ = 0;
    }

    bool clientOpen(int32_t pid, const char *procName) {
        if (pid <= 0) {
            return false;
        }
        Entry *slot = findOrAlloc(pid, procName);
        if (!slot) {
            return false;
        }
        slot->activeClients++;
        if (procName && procName[0] != '\0') {
            copyProcName(slot->procName, procName);
        }
        return true;
    }

    void clientClose(int32_t pid) {
        Entry *slot = find(pid);
        if (!slot) {
            return;
        }
        if (slot->activeClients > 0) {
            slot->activeClients--;
        }
        maybeReclaim(slot);
    }

    void addMemory(int32_t pid, int64_t vramDelta, int64_t gttDelta, int64_t hostDelta) {
        applyDelta(vramUsedBytes_, vramDelta);
        applyDelta(gttUsedBytes_, gttDelta);
        applyDelta(hostUsedBytes_, hostDelta);
        Entry *slot = find(pid);
        if (!slot && (vramDelta > 0 || gttDelta > 0 || hostDelta > 0)) {
            slot = findOrAlloc(pid, nullptr);
        }
        if (!slot) {
            return;
        }
        applyDelta(slot->vramBytes, vramDelta);
        applyDelta(slot->gttBytes, gttDelta);
        applyDelta(slot->hostBytes, hostDelta);
        maybeReclaim(slot);
    }

    void noteSubmit(int32_t pid, uint64_t submitAbs) {
        if (pid <= 0) {
            return;
        }
        Entry *slot = findOrAlloc(pid, nullptr);
        if (!slot) {
            return;
        }
        if (submitAbs > slot->lastSubmittedAbs) {
            slot->lastSubmittedAbs = submitAbs;
        }
        slot->submitCount++;
    }

    void addGpuTime(int32_t pid, uint64_t gpuNs, bool fromHwTimestamp) {
        if (gpuNs == 0 || gpuNs > kMaxSingleSubmitNs) {
            return;
        }
        totalGpuBusyNs_ += gpuNs;
        if (fromHwTimestamp) {
            hwTsCount_++;
        } else {
            fallbackTsCount_++;
        }
        if (pid <= 0) {
            return;
        }
        Entry *slot = find(pid);
        if (slot) {
            slot->accumulatedGpuNs += gpuNs;
        }
    }

    uint32_t computeUtilPct(uint64_t nowNs) {
        if (utilWindowStartNs_ == 0 || nowNs < utilWindowStartNs_) {
            utilWindowStartNs_ = nowNs;
            utilWindowStartBusyNs_ = totalGpuBusyNs_;
            cachedUtilPct_ = 0;
            return 0;
        }
        const uint64_t elapsedNs = nowNs - utilWindowStartNs_;
        if (elapsedNs < kMinUtilWindowNs) {
            return cachedUtilPct_;
        }
        const uint64_t busyDelta =
            totalGpuBusyNs_ >= utilWindowStartBusyNs_ ? (totalGpuBusyNs_ - utilWindowStartBusyNs_) : 0;
        uint64_t pct = (busyDelta * 100ull) / elapsedNs;
        if (pct > 100ull) {
            pct = 100ull;
        }
        utilWindowStartNs_ = nowNs;
        utilWindowStartBusyNs_ = totalGpuBusyNs_;
        cachedUtilPct_ = static_cast<uint32_t>(pct);
        return cachedUtilPct_;
    }

    void snapshot(PhxGpuTelemetrySnapshot &out, uint64_t nowNs, uint64_t vramTotalBytes,
                  uint64_t gttTotalBytes) {
        out.version = PHX_TELEMETRY_ABI_VERSION;
        out.pidCount = 0;
        out.vramTotalBytes = vramTotalBytes;
        out.vramUsedBytes = vramUsedBytes_;
        out.gttTotalBytes = gttTotalBytes;
        out.gttUsedBytes = gttUsedBytes_;
        out.hostUsedBytes = hostUsedBytes_;
        out.totalGpuBusyNs = totalGpuBusyNs_;
        out.gpuUtilPct = computeUtilPct(nowNs);
        out.reserved = 0;
        for (uint32_t idx = 0; idx < PHX_TELEMETRY_MAX_PIDS; ++idx) {
            const Entry &entry = entries_[idx];
            if (!entry.used) {
                continue;
            }
            PhxPidTelemetry &dst = out.pids[out.pidCount++];
            dst.pid = entry.pid;
            dst.activeClients = entry.activeClients;
            dst.accumulatedGpuNs = entry.accumulatedGpuNs;
            dst.lastSubmittedAbs = entry.lastSubmittedAbs;
            dst.vramBytes = entry.vramBytes;
            dst.gttBytes = entry.gttBytes;
            dst.hostBytes = entry.hostBytes;
            dst.submitCount = entry.submitCount;
            copyProcName(dst.procName, entry.procName);
        }
    }

    uint64_t vramUsedBytes() const { return vramUsedBytes_; }
    uint64_t gttUsedBytes() const { return gttUsedBytes_; }
    uint64_t hostUsedBytes() const { return hostUsedBytes_; }
    uint64_t totalGpuBusyNs() const { return totalGpuBusyNs_; }
    uint64_t hwTsCount() const { return hwTsCount_; }
    uint64_t fallbackTsCount() const { return fallbackTsCount_; }
    uint32_t cachedUtilPct() const { return cachedUtilPct_; }

private:
    struct Entry {
        bool used{false};
        int32_t pid{0};
        uint32_t activeClients{0};
        uint64_t accumulatedGpuNs{0};
        uint64_t lastSubmittedAbs{0};
        uint64_t vramBytes{0};
        uint64_t gttBytes{0};
        uint64_t hostBytes{0};
        uint64_t submitCount{0};
        char procName[PHX_TELEMETRY_NAME_LEN]{};
    };

    static void applyDelta(uint64_t &field, int64_t delta) {
        if (delta > 0) {
            field += static_cast<uint64_t>(delta);
        } else if (delta < 0) {
            const uint64_t sub = static_cast<uint64_t>(-(delta + 1)) + 1ull;
            field = field > sub ? field - sub : 0;
        }
    }

    Entry *find(int32_t pid) {
        if (pid <= 0) {
            return nullptr;
        }
        for (uint32_t idx = 0; idx < PHX_TELEMETRY_MAX_PIDS; ++idx) {
            if (entries_[idx].used && entries_[idx].pid == pid) {
                return &entries_[idx];
            }
        }
        return nullptr;
    }

    Entry *findOrAlloc(int32_t pid, const char *procName) {
        if (pid <= 0) {
            return nullptr;
        }
        if (Entry *existing = find(pid)) {
            return existing;
        }
        for (uint32_t idx = 0; idx < PHX_TELEMETRY_MAX_PIDS; ++idx) {
            if (!entries_[idx].used) {
                entries_[idx] = Entry{};
                entries_[idx].used = true;
                entries_[idx].pid = pid;
                copyProcName(entries_[idx].procName, procName);
                return &entries_[idx];
            }
        }
        return nullptr;
    }

    void maybeReclaim(Entry *slot) {
        if (!slot) {
            return;
        }
        if (slot->activeClients == 0 && slot->vramBytes == 0 && slot->gttBytes == 0 && slot->hostBytes == 0) {
            *slot = Entry{};
        }
    }

    Entry entries_[PHX_TELEMETRY_MAX_PIDS]{};
    uint64_t vramUsedBytes_{0};
    uint64_t gttUsedBytes_{0};
    uint64_t hostUsedBytes_{0};
    uint64_t totalGpuBusyNs_{0};
    uint64_t hwTsCount_{0};
    uint64_t fallbackTsCount_{0};
    uint64_t utilWindowStartNs_{0};
    uint64_t utilWindowStartBusyNs_{0};
    uint32_t cachedUtilPct_{0};
};

} // namespace phx::telemetry
