#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Stage clean-room Phase 1 + Phase 2 UMA carve-out support onto exact build34 PhxBringup.cpp.

Phase 1 (read-only on start):
- Reads RCC_CONFIG_MEMSIZE, IP_DISCOVERY_VERSION, DRIVER_SCRATCH_0..2 and probes
  the IP Discovery signature via MM_INDEX/MM_DATA (same read-only sequence as PhxProbe).
- Verifies phx-fb-phys against BAR0 by sampling dwords inside the lower aperture.
- Checks PE_state.bootArgs EFI memory map coverage of the planned high-UMA window
  using the freestanding classifier in PhxUmaPool.h.
- Publishes read-only IORegistry metadata (phx-uma-*) without altering default behavior.

Phase 2 (opt-in via sysctl debug.phx_uma_vram):
- Mode 0 (default): completely off; ordinary build34 system-RAM BO path unchanged.
- Mode 1 (pilot): admits a bounded 64 MiB window [256 MiB, 320 MiB) only when Phase 1
  proved geometry, discovery signature, alias match, and EFI ReservedTypeOnly coverage.
- Mode 2 (full): admits [256 MiB, fbSize - topReserve) only when Phase 1 proved full
  window coverage; reports real pool capacity/free bytes in vram_hi_total/vram_hi_free.
- High-UMA BOs refuse CPU mmap via clientMemoryForType, are zeroed before use via
  write-combining alias mapping, and are mapped with local VRAM PTEs (0x31 / 0x71 |
  MTYPE 4, EXEC kept: RADV maps every VRAM BO EXECUTABLE) and unmapped +
  retirement-drained before release.
"""
import argparse
import hashlib
from pathlib import Path
import platform
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
DRIVER_REL = 'src/phxbringup/PhxBringup.cpp'
DRIVER_SHA256 = '81f45aa2e8166bc6ebed4106129bebebfd70f9b4bbea6dbe389be46263e3c699'

ANCHOR_INCLUDES = '#include "PhxNativeABI.h"\n'
INSERT_INCLUDES = '''#include <sys/proc.h>
#include "PhxNativeABI.h"
#include "PhxUmaPool.h"
#include "PhxTelemetry.h"
'''

ANCHOR_SYSCTL = 'static volatile UInt32 gSysctlUp;\n'
INSERT_SYSCTL = '''static volatile UInt32 gSysctlUp;
// debug.phx_uma_vram: opt-in GPU-local UMA carve-out high-VRAM allocator.
// 0 = off (default build34 behavior), 1 = 64 MiB pilot window [256 MiB, 320 MiB),
// 2 = full verified high-UMA window [256 MiB, fbSize - topReserve).
static int gUmaVramMode = 0;
static volatile SInt64 gUmaVramAllocs;
static volatile SInt64 gUmaVramFrees;
static volatile SInt64 gUmaVramFallbacks;
static volatile SInt64 gUmaVramBytesLive;
static volatile SInt32 gUmaVramFaults;
static int gGpuTsEnable = 1;
static volatile SInt32 gGpuUtilPct;
static volatile SInt64 gVramUsedBytes;
SYSCTL_INT(_debug, OID_AUTO, phx_uma_vram, CTLFLAG_RW | CTLFLAG_LOCKED, &gUmaVramMode, 0,
           "UMA carve-out high-VRAM mode: 0 off, 1 pilot 64 MiB, 2 full verified window");
SYSCTL_QUAD(_debug, OID_AUTO, phx_uma_vram_allocs, CTLFLAG_RD | CTLFLAG_LOCKED, (SInt64 *)&gUmaVramAllocs,
            "successful UMA-backed high-VRAM BO allocations");
SYSCTL_QUAD(_debug, OID_AUTO, phx_uma_vram_frees, CTLFLAG_RD | CTLFLAG_LOCKED, (SInt64 *)&gUmaVramFrees,
            "completed UMA-backed high-VRAM BO releases");
SYSCTL_QUAD(_debug, OID_AUTO, phx_uma_vram_fallbacks, CTLFLAG_RD | CTLFLAG_LOCKED, (SInt64 *)&gUmaVramFallbacks,
            "high-VRAM requests that fell back to system memory");
SYSCTL_QUAD(_debug, OID_AUTO, phx_uma_vram_bytes, CTLFLAG_RD | CTLFLAG_LOCKED, (SInt64 *)&gUmaVramBytesLive,
            "bytes currently allocated in the UMA high-VRAM pool");
SYSCTL_INT(_debug, OID_AUTO, phx_uma_vram_faults, CTLFLAG_RD | CTLFLAG_LOCKED, (int *)&gUmaVramFaults, 0,
           "UMA pool fault or quarantine events");
SYSCTL_INT(_debug, OID_AUTO, phx_gpu_ts, CTLFLAG_RW | CTLFLAG_LOCKED, &gGpuTsEnable, 0,
           "emit GFX11 RELEASE_MEM hardware timestamps around GPU submissions: 0 off, 1 on");
SYSCTL_INT(_debug, OID_AUTO, phx_gpu_util, CTLFLAG_RD | CTLFLAG_LOCKED, (int *)&gGpuUtilPct, 0,
           "last sampled GPU utilization percentage (0..100)");
SYSCTL_QUAD(_debug, OID_AUTO, phx_vram_used_bytes, CTLFLAG_RD | CTLFLAG_LOCKED, (SInt64 *)&gVramUsedBytes,
            "total live VRAM bytes tracked across all GPU clients");
'''

ANCHOR_PUBLIC_METHODS = '    IOReturn vmUnmap(uint32_t vmid, uint64_t va, uint64_t size);\n'
INSERT_PUBLIC_METHODS = '''    IOReturn vmUnmap(uint32_t vmid, uint64_t va, uint64_t size);
    IOReturn vmMapUma(uint32_t vmid, uint64_t va, uint64_t ownerId, uint32_t umaSlot, uint64_t umaSerial,
                      uint64_t off, uint64_t size, bool writable);
    bool umaAlloc(uint64_t ownerId, uint64_t size, uint64_t align, phx::uma::HighUmaAllocator::Allocation &out);
    void umaFree(uint64_t ownerId, uint32_t slot, uint64_t serial, uint64_t lastSeq);
    void umaQuarantine(uint64_t ownerId, uint32_t slot, uint64_t serial);
    bool umaQueryHiPool(uint64_t &totalOut, uint64_t &freeOut, int *activeModeOut = nullptr);
    void telemetryClientOpen(int32_t pid, const char *procName);
    void telemetryClientClose(int32_t pid);
    void telemetryAddMemory(int32_t pid, int64_t vramDelta, int64_t gttDelta, int64_t hostDelta);
    void telemetryNoteSubmit(int32_t pid, uint64_t submitAbs);
    IOReturn callPlatformFunction(const OSSymbol *functionName, bool waitForFunction,
                                  void *param1, void *param2, void *param3, void *param4) override;
'''

ANCHOR_GPUSUBMIT_DECL = '    IOReturn gpuSubmit(uint32_t vmid, bool gfx, const uint64_t *ibVa, const uint32_t *ibDw, uint32_t n, uint64_t *seq);\n'
INSERT_GPUSUBMIT_DECL = '    IOReturn gpuSubmit(uint32_t vmid, bool gfx, const uint64_t *ibVa, const uint32_t *ibDw, uint32_t n, uint64_t *seq, int32_t pid = 0);\n'

ANCHOR_GPUQUEUE_STRUCT = '''    struct GpuQueue {
        bool ready, gfx;
        uint32_t ringOff, ringDw, wbOff, fenceOff;
        uint64_t dbByte, wptr, doneEnd;
        uint64_t fseq[64], fend[64];
        uint32_t fvmid[64];                     // the hardware VMID each outstanding submission runs under
        volatile uint32_t head, tail;
        uint64_t lastDone, lastProgress;        // the hang watchdog's view: fence seen last, and when it last moved
        uint64_t killedSeq; bool killedAll;
    };
'''
INSERT_GPUQUEUE_STRUCT = '''    struct GpuQueue {
        bool ready, gfx;
        uint32_t ringOff, ringDw, wbOff, fenceOff, tsOff;
        uint64_t dbByte, wptr, doneEnd;
        uint64_t fseq[64], fend[64];
        uint32_t fvmid[64];                     // the hardware VMID each outstanding submission runs under
        int32_t fpid[64];
        uint64_t fSubmitNs[64];
        bool fHasTs[64];
        volatile uint32_t head, tail;
        uint64_t lastDone, lastProgress;        // the hang watchdog's view: fence seen last, and when it last moved
        uint64_t killedSeq; bool killedAll;
    };
'''

ANCHOR_PT_CHUNKS = '    static constexpr uint32_t kPtChunkBytes = 64u << 10, kPtChunkPages = kPtChunkBytes / 4096, kPtChunks = 64;\n'
INSERT_PT_CHUNKS = '    static constexpr uint32_t kPtChunkBytes = 64u << 10, kPtChunkPages = kPtChunkBytes / 4096, kPtChunks = 192;\n'

ANCHOR_GTT_CAP = '''static constexpr uint64_t kGttCap = 512ull << 20;
static constexpr uint64_t kGttMaxBo = 256ull << 20;
'''
INSERT_GTT_CAP = '''static constexpr uint64_t kGttCap = 512ull << 20;
static constexpr uint64_t kGttMaxBo = 256ull << 20;
static constexpr uint64_t kUmaFullGttCap = 2048ull << 20;
'''

ANCHOR_PRIVATE_MEMBERS = '    volatile SInt32 sessionOpen{0};\n'
INSERT_PRIVATE_MEMBERS = '''    volatile SInt32 sessionOpen{0};
    void probeUmaReadOnly();
    bool verifyUmaAliasReadOnly(bool publishProps);
    bool ensureUmaAdmittedLocked(int requestedMode);
    uint32_t vramReadMmIndex(uint64_t pos) const;
    bool zeroUmaRange(uint64_t physBase, uint64_t bytes) const;
    void retireQueueLocked(GpuQueue &q);
    void snapshotTelemetry(PhxGpuTelemetrySnapshot &out);
    IOLock *umaLock{nullptr};
    IOLock *telemetryLock{nullptr};
    phx::telemetry::PhxTelemetryTracker telemetry{};
    phx::uma::Geometry umaGeom{};
    phx::uma::DiscoveryProbe umaDisc{};
    phx::uma::WindowPlan umaPlan{};
    phx::uma::HostExclusionStatus umaPilotHostStatus{phx::uma::HostExclusionStatus::Unchecked};
    phx::uma::HostExclusionStatus umaFullHostStatus{phx::uma::HostExclusionStatus::Unchecked};
    bool umaAliasMatched{false};
    int umaActiveMode{0};
    phx::uma::HighUmaAllocator umaPool{};
'''

ANCHOR_BO_STRUCT = '''    struct Bo {
        IOMemoryDescriptor *md;   // an IOBufferMemoryDescriptor, or the caller's own pages (host, prepared)
        uint64_t size;
        uint32_t domain;
        uint32_t bits;
        uint8_t *kva;             // the kernel's view of the BO; NULL for host imports, which the kernel never reads
        bool host;
    };
'''
INSERT_BO_STRUCT = '''    struct Bo {
        IOMemoryDescriptor *md;   // an IOBufferMemoryDescriptor, or the caller's own pages (host, prepared)
        uint64_t size;
        uint32_t domain;
        uint32_t bits;
        uint8_t *kva;             // the kernel's view of the BO; NULL for host imports or UMA-backed BOs
        bool host;
        bool uma;
        uint32_t umaSlot;
        uint64_t umaSerial;
        uint64_t umaOffset;
    };
'''

ANCHOR_CLIENT_MEMBERS = '    uint64_t emitted{0};\n'
INSERT_CLIENT_MEMBERS = '''    uint64_t emitted{0};
    uint64_t umaOwnerId{0};
    int32_t clientPid{0};
    char clientProcName[PHX_TELEMETRY_NAME_LEN]{};
    bool telemetryOpen{false};
    uint64_t umaUsed{0};
'''

ANCHOR_START_LOCK = '    gpuLock = IOLockAlloc();\n'
INSERT_START_LOCK = '    gpuLock = IOLockAlloc();\n    umaLock = IOLockAlloc();\n    telemetryLock = IOLockAlloc();\n'

ANCHOR_START_PROBE = '    setProperty("phx-fb-aper-len", fbAperLen, 64);\n'
INSERT_START_PROBE = '''    setProperty("phx-fb-aper-len", fbAperLen, 64);
    probeUmaReadOnly();
    {
        int bootUmaMode = 0;
        if (PE_parse_boot_argn("phx_uma_vram", &bootUmaMode, sizeof(bootUmaMode)) &&
            (bootUmaMode == 1 || bootUmaMode == 2)) {
            gUmaVramMode = bootUmaMode;
            if (umaLock) {
                IOLockLock(umaLock);
                ensureUmaAdmittedLocked(gUmaVramMode);
                IOLockUnlock(umaLock);
            }
        }
    }
'''

ANCHOR_STOP_SYSCTL = '''        sysctl_unregister_oid(&sysctl__debug_phx_hang_kills);
        gSysctlUp = 0;
    }
'''
INSERT_STOP_SYSCTL = '''        sysctl_unregister_oid(&sysctl__debug_phx_hang_kills);
        sysctl_unregister_oid(&sysctl__debug_phx_uma_vram);
        sysctl_unregister_oid(&sysctl__debug_phx_uma_vram_allocs);
        sysctl_unregister_oid(&sysctl__debug_phx_uma_vram_frees);
        sysctl_unregister_oid(&sysctl__debug_phx_uma_vram_fallbacks);
        sysctl_unregister_oid(&sysctl__debug_phx_uma_vram_bytes);
        sysctl_unregister_oid(&sysctl__debug_phx_uma_vram_faults);
        sysctl_unregister_oid(&sysctl__debug_phx_gpu_ts);
        sysctl_unregister_oid(&sysctl__debug_phx_gpu_util);
        sysctl_unregister_oid(&sysctl__debug_phx_vram_used_bytes);
        gSysctlUp = 0;
    }
    if (umaLock) {
        IOLockLock(umaLock);
        umaPool.reset();
        umaActiveMode = 0;
        IOLockUnlock(umaLock);
        IOLockFree(umaLock);
        umaLock = nullptr;
    }
    if (telemetryLock) {
        IOLockLock(telemetryLock);
        telemetry.reset();
        IOLockUnlock(telemetryLock);
        IOLockFree(telemetryLock);
        telemetryLock = nullptr;
    }
'''

ANCHOR_SLEEP = '''    if (ordinal == 0) {
        IOLog("PhxBringup: powerStateWillChange to sleep (state 0)\\n");
        isSleeping = true;
    } else {
'''
INSERT_SLEEP = '''    if (ordinal == 0) {
        IOLog("PhxBringup: powerStateWillChange to sleep (state 0)\\n");
        isSleeping = true;
        if (umaLock) {
            IOLockLock(umaLock);
            if (umaActiveMode != 0)
                umaPool.tripFault();
            IOLockUnlock(umaLock);
        }
    } else {
'''

ANCHOR_READ_FB_END = '''    if (fbSize)
        pci->setProperty("VRAM,totalMB", fbSize >> 20, 32);
}
'''
INSERT_UMA_HELPERS = '''    if (fbSize)
        pci->setProperty("VRAM,totalMB", fbSize >> 20, 32);
}

uint32_t PhxBringup::vramReadMmIndex(uint64_t pos) const {
    wreg(phx::uma::kRegMmIndex, static_cast<uint32_t>(pos) | 0x80000000u);
    wreg(phx::uma::kRegMmIndexHi, static_cast<uint32_t>(pos >> 31));
    return rreg(phx::uma::kRegMmData);
}

bool PhxBringup::verifyUmaAliasReadOnly(bool publishProps) {
    if (!fbAper || fbAperLen < (16ull << 20) || !fbPhys)
        return false;
    // Read-only alias check: sample across the first 16 MiB of phx-fb-phys
    // against BAR0 (4096 stride-spaced dwords so even a mostly-black boot
    // screen hits non-zero pixels, and re-callable once desktop scanout is up).
    const uint64_t probeBytes = 16ull << 20;
    IODeviceMemory *dm = IODeviceMemory::withRange(fbPhys, probeBytes);
    if (!dm)
        return false;
    IOMemoryMap *alias = dm->map(kIOMapWriteCombineCache);
    dm->release();
    if (!alias)
        return false;
    const volatile uint32_t *a = reinterpret_cast<const volatile uint32_t *>(alias->getVirtualAddress());
    const volatile uint32_t *b = reinterpret_cast<const volatile uint32_t *>(fbAper->getVirtualAddress());
    const uint64_t words = probeBytes / 4;
    const uint64_t step = words / 4096u;
    uint32_t same = 0, total = 0, nonZero = 0;
    for (uint64_t w = 0; w < words && total < 4096u; w += step, ++total) {
        const uint32_t va = a[w], vb = b[w];
        same += (va == vb) ? 1u : 0u;
        nonZero += (vb != 0) ? 1u : 0u;
    }
    alias->release();
    const bool matched = phx::uma::aliasVerificationMatches(same, total, nonZero);
    umaAliasMatched = matched;
    if (publishProps) {
        setProperty("phx-uma-alias-matched", umaAliasMatched);
        setProperty("phx-uma-alias-same", same, 32);
        setProperty("phx-uma-alias-total", total, 32);
        setProperty("phx-uma-alias-nonzero", nonZero, 32);
    }
    return matched;
}

void PhxBringup::probeUmaReadOnly() {
    umaGeom = phx::uma::Geometry{fbMcBase, fbPhys, fbSize, fbAperLen};
    umaDisc = phx::uma::DiscoveryProbe{};
    umaPlan = phx::uma::WindowPlan{};
    umaPilotHostStatus = phx::uma::HostExclusionStatus::Unchecked;
    umaFullHostStatus = phx::uma::HostExclusionStatus::Unchecked;
    umaAliasMatched = false;

    if (mmio && phx::uma::geometryValid(umaGeom)) {
        const uint32_t memsizeMb = rreg(phx::uma::kRegRccConfigMemsize);
        const uint32_t ipVer = rreg(phx::uma::kRegIpDiscoveryVersion);
        const uint32_t scratch0 = rreg(phx::uma::kRegDriverScratch0);
        const uint32_t scratch1 = rreg(phx::uma::kRegDriverScratch1);
        const uint32_t scratch2 = rreg(phx::uma::kRegDriverScratch2);

        uint64_t discOff = 0;
        uint32_t discBytes = phx::uma::kDiscoveryTmrSize;
        uint32_t discSig = 0;
        if (memsizeMb != 0 && memsizeMb != 0xFFFFFFFFu &&
            (static_cast<uint64_t>(memsizeMb) << 20) >= phx::uma::kDiscoveryTmrOffset) {
            discOff = (static_cast<uint64_t>(memsizeMb) << 20) - phx::uma::kDiscoveryTmrOffset;
            discSig = vramReadMmIndex(discOff);
        }
        if (discSig != phx::uma::kDiscoverySignature && scratch2 != 0) {
            discOff = (static_cast<uint64_t>(scratch1) << 32) | scratch0;
            discBytes = scratch2;
            if (discOff + 4 <= fbSize)
                discSig = vramReadMmIndex(discOff);
        }
        umaDisc = phx::uma::classifyDiscoveryProbe(fbSize, memsizeMb, ipVer, discOff, discBytes, discSig);
        umaPlan = phx::uma::planHighUmaWindows(umaGeom, umaDisc);
        verifyUmaAliasReadOnly(true);

        if (umaPlan.valid) {
            const uint8_t *bootArgsBytes = reinterpret_cast<const uint8_t *>(PE_state.bootArgs);
            if (!bootArgsBytes) {
                umaPilotHostStatus = phx::uma::HostExclusionStatus::BootArgsUnavailable;
                umaFullHostStatus = phx::uma::HostExclusionStatus::BootArgsUnavailable;
            } else {
                const uint64_t mapPhys = phx::uma::readLittleEndian(bootArgsBytes + 1032, 4);
                const uint64_t mapLen = phx::uma::readLittleEndian(bootArgsBytes + 1036, 4);
                if (!mapPhys || !mapLen || mapLen > (1u << 20)) {
                    umaPilotHostStatus = phx::uma::HostExclusionStatus::Refused;
                    umaFullHostStatus = phx::uma::HostExclusionStatus::Refused;
                } else if (IODeviceMemory *mapDm = IODeviceMemory::withRange(mapPhys, mapLen)) {
                    if (IOMemoryMap *mapView = mapDm->map(kIOMapInhibitCache)) {
                        const void *mapPtr = reinterpret_cast<const void *>(mapView->getVirtualAddress());
                        umaPilotHostStatus = phx::uma::classifyBootMap(
                            bootArgsBytes, 4096, mapPtr, static_cast<size_t>(mapLen), mapPhys,
                            fbPhys + umaPlan.pilotWindow.offset, umaPlan.pilotWindow.bytes);
                        umaFullHostStatus = phx::uma::classifyBootMap(
                            bootArgsBytes, 4096, mapPtr, static_cast<size_t>(mapLen), mapPhys,
                            fbPhys + umaPlan.fullHighWindow.offset, umaPlan.fullHighWindow.bytes);
                        mapView->release();
                    } else {
                        umaPilotHostStatus = phx::uma::HostExclusionStatus::BootMapUnreadable;
                        umaFullHostStatus = phx::uma::HostExclusionStatus::BootMapUnreadable;
                    }
                    mapDm->release();
                } else {
                    umaPilotHostStatus = phx::uma::HostExclusionStatus::BootMapUnreadable;
                    umaFullHostStatus = phx::uma::HostExclusionStatus::BootMapUnreadable;
                }
            }
        }
    }

    setProperty("phx-uma-discovery-valid", umaDisc.signatureValid);
    setProperty("phx-uma-discovery-offset", umaDisc.discoveryOffset, 64);
    setProperty("phx-uma-discovery-sig", umaDisc.discoverySignature, 32);
    setProperty("phx-uma-rcc-memsize-mb", umaDisc.rccMemsizeMb, 32);
    setProperty("phx-uma-plan-valid", umaPlan.valid);
    setProperty("phx-uma-pilot-offset", umaPlan.pilotWindow.offset, 64);
    setProperty("phx-uma-pilot-bytes", umaPlan.pilotWindow.bytes, 64);
    setProperty("phx-uma-full-bytes", umaPlan.fullHighWindow.bytes, 64);
    setProperty("phx-uma-pilot-host-status", static_cast<uint32_t>(umaPilotHostStatus), 32);
    setProperty("phx-uma-full-host-status", static_cast<uint32_t>(umaFullHostStatus), 32);
    IOLog("PhxBringup: UMA probe disc=%d rcc=%uMB alias=%d plan=%d pilotHost=%u fullHost=%u fullHi=%lluMiB\\n",
          umaDisc.signatureValid, umaDisc.rccMemsizeMb, umaAliasMatched, umaPlan.valid,
          static_cast<unsigned>(umaPilotHostStatus), static_cast<unsigned>(umaFullHostStatus),
          static_cast<unsigned long long>(umaPlan.fullHighWindow.bytes >> 20));
}

bool PhxBringup::zeroUmaRange(uint64_t physBase, uint64_t bytes) const {
    if (!bytes || (physBase & 4095ull) || (bytes & 4095ull))
        return false;
    IODeviceMemory *dm = IODeviceMemory::withRange(physBase, bytes);
    if (!dm)
        return false;
    IOMemoryMap *map = dm->map(kIOMapWriteCombineCache);
    dm->release();
    if (!map)
        return false;
    bzero(reinterpret_cast<void *>(map->getVirtualAddress()), static_cast<size_t>(bytes));
    __asm__ __volatile__("sfence" ::: "memory");
    map->release();
    hdpFlush();
    return true;
}

bool PhxBringup::ensureUmaAdmittedLocked(int requestedMode) {
    if (requestedMode <= 0 || isSleeping || !umaPlan.valid)
        return false;
    if (umaPool.stats().faulted)
        return false;
    const int targetMode = (requestedMode >= 2) ? 2 : 1;
    if (umaActiveMode != 0) {
        if (umaActiveMode == targetMode)
            return true;
        const auto st = umaPool.stats();
        if (st.liveCount == 0 && st.quarantinedCount == 0 && !st.faulted) {
            umaPool.reset();
            umaActiveMode = 0;
        } else {
            return true;
        }
    }
    if (!umaAliasMatched && !verifyUmaAliasReadOnly(false))
        return false;
    const phx::uma::Range target = (targetMode == 2) ? umaPlan.fullHighWindow : umaPlan.pilotWindow;
    const phx::uma::HostExclusionStatus hostStatus =
        (targetMode == 2) ? umaFullHostStatus : umaPilotHostStatus;
    if (!umaPool.admit(umaGeom, target, umaPlan.discoveryRange, hostStatus, umaAliasMatched))
        return false;
    umaActiveMode = targetMode;
    IOLog("PhxBringup: UMA high-VRAM pool admitted (mode=%d, offset=0x%llx, size=%llu MiB)\\n",
          umaActiveMode, static_cast<unsigned long long>(target.offset),
          static_cast<unsigned long long>(target.bytes >> 20));
    return true;
}

bool PhxBringup::umaAlloc(uint64_t ownerId, uint64_t size, uint64_t align,
                          phx::uma::HighUmaAllocator::Allocation &out) {
    out = phx::uma::HighUmaAllocator::Allocation{};
    const int mode = gUmaVramMode;
    if (mode <= 0 || !umaLock)
        return false;
    IOLockLock(umaLock);
    const bool ok = ensureUmaAdmittedLocked(mode) && umaPool.allocate(ownerId, size, align, out);
    IOLockUnlock(umaLock);
    if (!ok) {
        OSAddAtomic64(1, &gUmaVramFallbacks);
        return false;
    }
    if (!zeroUmaRange(out.physBase, out.bytes)) {
        IOLockLock(umaLock);
        umaPool.quarantine(ownerId, out.slot, out.serial);
        IOLockUnlock(umaLock);
        OSAddAtomic(1, &gUmaVramFaults);
        OSAddAtomic64(1, &gUmaVramFallbacks);
        out = phx::uma::HighUmaAllocator::Allocation{};
        return false;
    }
    OSAddAtomic64(1, &gUmaVramAllocs);
    OSAddAtomic64(static_cast<SInt64>(out.bytes), &gUmaVramBytesLive);
    return true;
}

void PhxBringup::umaFree(uint64_t ownerId, uint32_t slot, uint64_t serial, uint64_t lastSeq) {
    if (!umaLock || !serial)
        return;
    if (gpuReady() && lastSeq != 0) {
        for (int i = 0; i < 2000 && gpuRetired() < lastSeq; i++)
            IOSleep(1);
        if (gpuRetired() < lastSeq) {
            umaQuarantine(ownerId, slot, serial);
            return;
        }
    }
    uint64_t freedBytes = 0;
    IOLockLock(umaLock);
    const auto before = umaPool.stats();
    const bool released = umaPool.release(ownerId, slot, serial);
    const auto after = umaPool.stats();
    if (released && before.usedBytes >= after.usedBytes)
        freedBytes = before.usedBytes - after.usedBytes;
    IOLockUnlock(umaLock);
    if (released) {
        OSAddAtomic64(1, &gUmaVramFrees);
        OSAddAtomic64(-static_cast<SInt64>(freedBytes), &gUmaVramBytesLive);
    }
}

void PhxBringup::umaQuarantine(uint64_t ownerId, uint32_t slot, uint64_t serial) {
    if (!umaLock || !serial)
        return;
    IOLockLock(umaLock);
    umaPool.quarantine(ownerId, slot, serial);
    IOLockUnlock(umaLock);
    OSAddAtomic(1, &gUmaVramFaults);
}

bool PhxBringup::umaQueryHiPool(uint64_t &totalOut, uint64_t &freeOut, int *activeModeOut) {
    if (activeModeOut)
        *activeModeOut = 0;
    const int mode = gUmaVramMode;
    if (mode <= 0 || !umaLock)
        return false;
    IOLockLock(umaLock);
    if (!ensureUmaAdmittedLocked(mode)) {
        IOLockUnlock(umaLock);
        return false;
    }
    const auto st = umaPool.stats();
    const int activeMode = umaActiveMode;
    IOLockUnlock(umaLock);
    if (!st.admitted || st.faulted || !st.capacityBytes)
        return false;
    totalOut = st.capacityBytes;
    freeOut = st.capacityBytes > st.usedBytes ? st.capacityBytes - st.usedBytes : 0;
    if (activeModeOut)
        *activeModeOut = activeMode;
    return true;
}
'''

ANCHOR_VMUNMAP = '''    if (c.hw)
        vmFlushTlb(c.hw);
    IOLockUnlock(gpuLock);
    return kIOReturnSuccess;
}
'''
INSERT_VMMAP_UMA = '''    if (c.hw)
        vmFlushTlb(c.hw);
    IOLockUnlock(gpuLock);
    return kIOReturnSuccess;
}

IOReturn PhxBringup::vmMapUma(uint32_t handle, uint64_t va, uint64_t ownerId, uint32_t umaSlot,
                              uint64_t umaSerial, uint64_t off, uint64_t size, bool writable) {
    if (!vmCtx(handle) || !umaLock)
        return kIOReturnNotReady;
    VmCtx &c = vm[handle - 1];
    IOReturn r = kIOReturnSuccess;
    IOLockLock(gpuLock);
    IOLockLock(umaLock);
    for (uint64_t p = 0; p < size; p += 4096) {
        uint64_t leaf = 0;
        if (!umaPool.encodePagePte(ownerId, umaSlot, umaSerial, off + p, writable, leaf)) {
            r = kIOReturnVMError;
            break;
        }
        uint64_t *pte = vmPte(c, va + p, true);
        if (!pte) {
            r = kIOReturnNoMemory;
            break;
        }
        *pte = leaf;
        flushLine(pte);
    }
    IOLockUnlock(umaLock);
    if (r != kIOReturnSuccess) {
        for (uint64_t p = 0; p < size; p += 4096) {
            uint64_t *pte = vmPte(c, va + p, false);
            if (pte) {
                *pte = 0;
                flushLine(pte);
            }
        }
    }
    if (c.hw)
        vmFlushTlb(c.hw);
    IOLockUnlock(gpuLock);
    return r;
}
'''

ANCHOR_SYSCTL_REG = '''        sysctl_register_oid(&sysctl__debug_phx_hang_kills);
    }
'''
INSERT_SYSCTL_REG = '''        sysctl_register_oid(&sysctl__debug_phx_hang_kills);
        sysctl_register_oid(&sysctl__debug_phx_uma_vram);
        sysctl_register_oid(&sysctl__debug_phx_uma_vram_allocs);
        sysctl_register_oid(&sysctl__debug_phx_uma_vram_frees);
        sysctl_register_oid(&sysctl__debug_phx_uma_vram_fallbacks);
        sysctl_register_oid(&sysctl__debug_phx_uma_vram_bytes);
        sysctl_register_oid(&sysctl__debug_phx_uma_vram_faults);
        sysctl_register_oid(&sysctl__debug_phx_gpu_ts);
        sysctl_register_oid(&sysctl__debug_phx_gpu_util);
        sysctl_register_oid(&sysctl__debug_phx_vram_used_bytes);
    }
'''

ANCHOR_ADOPT_QUEUE = '''    q.fenceOff = static_cast<uint32_t>(fenceOff);
    q.dbByte = dbByte;
    q.wptr = q.doneEnd = wptr;
    volatile uint32_t *fence = reinterpret_cast<volatile uint32_t *>(fbAper->getVirtualAddress() + fenceOff);
    fence[0] = static_cast<uint32_t>(gSeq);
    fence[1] = static_cast<uint32_t>(gSeq >> 32);
    hdpFlush();
    q.ready = true;
'''
INSERT_ADOPT_QUEUE = '''    q.fenceOff = static_cast<uint32_t>(fenceOff);
    q.tsOff = 0;
    if ((fenceOff & 0xFFFull) == 0 && fenceOff + 0x500ull <= fbAperLen) {
        const uint64_t tsStart = fenceOff + 0x100ull;
        const uint64_t tsEnd = tsStart + 0x400ull;
        const uint64_t ringEnd = ringOff + ringDw * 4ull;
        const uint64_t wbEnd = wbOff + 32ull;
        bool overlap = (tsStart < ringEnd && ringOff < tsEnd) || (tsStart < wbEnd && wbOff < tsEnd);
        const GpuQueue &peer = gq[qi ^ 1];
        if (peer.ready) {
            const uint64_t pRingEnd = static_cast<uint64_t>(peer.ringOff) + static_cast<uint64_t>(peer.ringDw) * 4ull;
            const uint64_t pWbEnd = static_cast<uint64_t>(peer.wbOff) + 32ull;
            const uint64_t pFenceEnd = static_cast<uint64_t>(peer.fenceOff) + 8ull;
            if ((tsStart < pRingEnd && peer.ringOff < tsEnd) ||
                (tsStart < pWbEnd && peer.wbOff < tsEnd) ||
                (tsStart < pFenceEnd && peer.fenceOff < tsEnd))
                overlap = true;
            if (peer.tsOff) {
                const uint64_t pTsEnd = static_cast<uint64_t>(peer.tsOff) + 0x400ull;
                if (tsStart < pTsEnd && peer.tsOff < tsEnd)
                    overlap = true;
            }
        }
        if (!overlap) {
            q.tsOff = static_cast<uint32_t>(tsStart);
            volatile uint64_t *tsBuf = reinterpret_cast<volatile uint64_t *>(fbAper->getVirtualAddress() + q.tsOff);
            for (uint32_t ti = 0; ti < 128; ti++)
                tsBuf[ti] = 0;
        }
    }
    q.dbByte = dbByte;
    q.wptr = q.doneEnd = wptr;
    volatile uint32_t *fence = reinterpret_cast<volatile uint32_t *>(fbAper->getVirtualAddress() + fenceOff);
    fence[0] = static_cast<uint32_t>(gSeq);
    fence[1] = static_cast<uint32_t>(gSeq >> 32);
    hdpFlush();
    q.ready = true;
'''

ANCHOR_GPUSUBMIT_BODY = '''IOReturn PhxBringup::gpuSubmit(uint32_t handle, bool gfx, const uint64_t *ibVa, const uint32_t *ibDw, uint32_t n, uint64_t *seqOut) {
    // doSubmit retains the client lock/BO ownership throughout this call.
    // Do not reserve ring or history space while waiting with gpuLock released.
    const uint64_t start = mach_absolute_time();
    GpuQueue *qp = nullptr;
    for (bool retried = false;; retried = true) {
        IOLockLock(gpuLock);
        // Re-select and validate under the lock after every sleep: adoption,
        // queue geometry, retirement and other submitters may have changed.
        qp = gfx ? (gq[1].ready ? &gq[1] : &gq[0]) : (gq[0].ready ? &gq[0] : &gq[1]);
        if (!qp->ready || !vmCtx(handle)) {
            IOLockUnlock(gpuLock);
            return kIOReturnNotReady;
        }
        GpuQueue &q = *qp;
        const uint32_t need = n * 4 + 8 + (q.gfx ? 0u : 8u);
        if (need + 16 > q.ringDw) {
            IOLockUnlock(gpuLock);
            return kIOReturnBadArgument;
        }
        const uint64_t done = queueFence(q);
        while (q.head != q.tail && q.fseq[q.head & 63] <= done) {
            q.doneEnd = q.fend[q.head & 63];
            q.head++;
        }
        const bool hasSpace = q.tail - q.head < 63 && q.wptr + need - q.doneEnd <= q.ringDw - 16;
        if (retried || !hasSpace) {
            uint64_t elapsed = 0;
            absolutetime_to_nanoseconds(mach_absolute_time() - start, &elapsed);
            if (elapsed >= 2000000000ull) {
                IOLockUnlock(gpuLock);
                return kIOReturnBusy;
            }
        }
        if (hasSpace)
            break;  // Keep the lock through VM binding, packet emission and doorbell.
        IOLockUnlock(gpuLock);
        IOSleep(1);
    }
    GpuQueue &q = *qp;
    const uint32_t vmid = vmBind(handle);
    if (!vmid) {
        IOLockUnlock(gpuLock);
        return kIOReturnBusy;
    }
    uint32_t k = 0;
    if (!q.gfx) {
        ringPut(q, k++, 0xc0065800u);
        ringPut(q, k++, 0x00000000u);
        ringPut(q, k++, 0xffffffffu);
        ringPut(q, k++, 0x00ffffffu);
        ringPut(q, k++, 0x00000000u);
        ringPut(q, k++, 0x00000000u);
        ringPut(q, k++, 0x0000000au);
        ringPut(q, k++, 0x0000c3b1u);
    }
    for (uint32_t i = 0; i < n; i++) {
        ringPut(q, k++, 0xC0023F00);                               // INDIRECT_BUFFER
        // the CP wants the canonical (sign-extended) address: an upper-half IB (bit 47, where RADV puts them) with a
        // bare 16-bit high word silently wedges the queue
        const uint64_t cva = (ibVa[i] & (1ull << 47)) ? (ibVa[i] | 0xFFFF000000000000ull) : ibVa[i];
        ringPut(q, k++, static_cast<uint32_t>(cva) & ~3u);
        ringPut(q, k++, static_cast<uint32_t>(cva >> 32));
        // size | VMID, plus VALID on compute (gfx_v11_0_ring_emit_ib_compute; the gfx variant has no VALID bit)
        ringPut(q, k++, ibDw[i] | (q.gfx ? 0u : (1u << 23)) | (vmid << 24));
    }
    const uint64_t seq = ++gSeq;
    hwv[vmid - kFirstUserVmid].lastSeq = seq;
    const uint64_t fenceMc = fbMcBase + q.fenceOff;
    ringPut(q, k++, 0xC0064900);                                   // RELEASE_MEM, as gfx_v11_0_ring_emit_fence
    ringPut(q, k++, 0x06603514);                                   // GCR SEQ|GL2_WB|GLM_INV|GLM_WB, CP 3, CACHE_FLUSH_AND_INV_TS, idx 5
    ringPut(q, k++, 0x40000000);                                   // DATA_SEL 2 (64-bit), no interrupt
    ringPut(q, k++, static_cast<uint32_t>(fenceMc));
    ringPut(q, k++, static_cast<uint32_t>(fenceMc >> 32));
    ringPut(q, k++, static_cast<uint32_t>(seq));
    ringPut(q, k++, static_cast<uint32_t>(seq >> 32));
    ringPut(q, k++, 0);
    q.wptr += k;
    q.fseq[q.tail & 63] = seq;
    q.fend[q.tail & 63] = q.wptr;
    q.fvmid[q.tail & 63] = vmid;
    __asm__ __volatile__("" ::: "memory");
    q.tail = q.tail + 1;
'''
INSERT_GPUSUBMIT_BODY = '''void PhxBringup::retireQueueLocked(GpuQueue &q) {
    if (!q.ready)
        return;
    const uint64_t done = queueFence(q);
    if (q.head == q.tail || q.fseq[q.head & 63] > done)
        return;
    uint64_t nowNs = 0;
    absolutetime_to_nanoseconds(mach_absolute_time(), &nowNs);
    const uintptr_t aperBase = fbAper ? fbAper->getVirtualAddress() : 0;
    while (q.head != q.tail && q.fseq[q.head & 63] <= done) {
        const uint32_t idx = q.head & 63;
        uint64_t gpuNs = 0;
        bool fromHw = false;
        if (q.fHasTs[idx] && q.tsOff && aperBase) {
            const volatile uint32_t *tp = reinterpret_cast<const volatile uint32_t *>(aperBase + q.tsOff + idx * 16u);
            const uint64_t tsStart = static_cast<uint64_t>(tp[0]) | (static_cast<uint64_t>(tp[1]) << 32);
            const uint64_t tsEnd = static_cast<uint64_t>(tp[2]) | (static_cast<uint64_t>(tp[3]) << 32);
            gpuNs = phx::telemetry::ticksToNs(tsStart, tsEnd);
            if (gpuNs > 0)
                fromHw = true;
        }
        if (gpuNs == 0 && q.fSubmitNs[idx] > 0)
            gpuNs = phx::telemetry::clampFallbackNs(q.fSubmitNs[idx], nowNs);
        if (gpuNs > 0 && telemetryLock) {
            IOLockLock(telemetryLock);
            telemetry.addGpuTime(q.fpid[idx], gpuNs, fromHw);
            IOLockUnlock(telemetryLock);
        }
        q.doneEnd = q.fend[idx];
        q.head++;
    }
}

void PhxBringup::telemetryClientOpen(int32_t pid, const char *procName) {
    if (!telemetryLock || pid <= 0)
        return;
    IOLockLock(telemetryLock);
    telemetry.clientOpen(pid, procName);
    IOLockUnlock(telemetryLock);
}

void PhxBringup::telemetryClientClose(int32_t pid) {
    if (!telemetryLock || pid <= 0)
        return;
    IOLockLock(telemetryLock);
    telemetry.clientClose(pid);
    IOLockUnlock(telemetryLock);
}

void PhxBringup::telemetryAddMemory(int32_t pid, int64_t vramDelta, int64_t gttDelta, int64_t hostDelta) {
    if (!telemetryLock)
        return;
    IOLockLock(telemetryLock);
    telemetry.addMemory(pid, vramDelta, gttDelta, hostDelta);
    gVramUsedBytes = static_cast<SInt64>(telemetry.vramUsedBytes());
    IOLockUnlock(telemetryLock);
}

void PhxBringup::telemetryNoteSubmit(int32_t pid, uint64_t submitAbs) {
    if (!telemetryLock || pid <= 0)
        return;
    IOLockLock(telemetryLock);
    telemetry.noteSubmit(pid, submitAbs);
    IOLockUnlock(telemetryLock);
}

void PhxBringup::snapshotTelemetry(PhxGpuTelemetrySnapshot &out) {
    if (gpuLock) {
        IOLockLock(gpuLock);
        for (GpuQueue &q : gq)
            retireQueueLocked(q);
        IOLockUnlock(gpuLock);
    }
    uint64_t vramTotal = fbSize;
    uint64_t gttTotal = kGttCap;
    uint64_t umaHiTotal = 0, umaHiFree = 0;
    int umaMode = 0;
    if (umaQueryHiPool(umaHiTotal, umaHiFree, &umaMode) && umaMode >= 2) {
        if (vramTotal == 0)
            vramTotal = kVisTotal + umaHiTotal;
        gttTotal = kUmaFullGttCap;
    } else if (vramTotal == 0) {
        vramTotal = kVisTotal + kHiTotal;
    }
    uint64_t nowNs = 0;
    absolutetime_to_nanoseconds(mach_absolute_time(), &nowNs);
    if (telemetryLock) {
        IOLockLock(telemetryLock);
        telemetry.snapshot(out, nowNs, vramTotal, gttTotal);
        gGpuUtilPct = static_cast<SInt32>(out.gpuUtilPct);
        gVramUsedBytes = static_cast<SInt64>(out.vramUsedBytes);
        IOLockUnlock(telemetryLock);
    } else {
        bzero(&out, sizeof(out));
        out.version = PHX_TELEMETRY_ABI_VERSION;
        out.vramTotalBytes = vramTotal;
        out.gttTotalBytes = gttTotal;
    }
}

IOReturn PhxBringup::callPlatformFunction(const OSSymbol *functionName, bool waitForFunction,
                                          void *param1, void *param2, void *param3, void *param4) {
    if (functionName && functionName->isEqualTo(PHX_TELEMETRY_FN)) {
        if (!param1)
            return kIOReturnBadArgument;
        PhxGpuTelemetrySnapshot *snap = static_cast<PhxGpuTelemetrySnapshot *>(param1);
        snapshotTelemetry(*snap);
        return kIOReturnSuccess;
    }
    return IOService::callPlatformFunction(functionName, waitForFunction, param1, param2, param3, param4);
}

IOReturn PhxBringup::gpuSubmit(uint32_t handle, bool gfx, const uint64_t *ibVa, const uint32_t *ibDw, uint32_t n, uint64_t *seqOut, int32_t pid) {
    // doSubmit retains the client lock/BO ownership throughout this call.
    // Do not reserve ring or history space while waiting with gpuLock released.
    const uint64_t start = mach_absolute_time();
    GpuQueue *qp = nullptr;
    bool emitTs = false;
    for (bool retried = false;; retried = true) {
        IOLockLock(gpuLock);
        // Re-select and validate under the lock after every sleep: adoption,
        // queue geometry, retirement and other submitters may have changed.
        qp = gfx ? (gq[1].ready ? &gq[1] : &gq[0]) : (gq[0].ready ? &gq[0] : &gq[1]);
        if (!qp->ready || !vmCtx(handle)) {
            IOLockUnlock(gpuLock);
            return kIOReturnNotReady;
        }
        GpuQueue &q = *qp;
        emitTs = (gGpuTsEnable != 0) && (q.tsOff != 0);
        const uint32_t need = n * 4 + 8 + (q.gfx ? 0u : 8u) + (emitTs ? 16u : 0u);
        if (need + 16 > q.ringDw) {
            IOLockUnlock(gpuLock);
            return kIOReturnBadArgument;
        }
        retireQueueLocked(q);
        const bool hasSpace = q.tail - q.head < 63 && q.wptr + need - q.doneEnd <= q.ringDw - 16;
        if (retried || !hasSpace) {
            uint64_t elapsed = 0;
            absolutetime_to_nanoseconds(mach_absolute_time() - start, &elapsed);
            if (elapsed >= 2000000000ull) {
                IOLockUnlock(gpuLock);
                return kIOReturnBusy;
            }
        }
        if (hasSpace)
            break;  // Keep the lock through VM binding, packet emission and doorbell.
        IOLockUnlock(gpuLock);
        IOSleep(1);
    }
    GpuQueue &q = *qp;
    const uint32_t vmid = vmBind(handle);
    if (!vmid) {
        IOLockUnlock(gpuLock);
        return kIOReturnBusy;
    }
    const uint32_t slot = q.tail & 63;
    const uint64_t tsStartMc = emitTs ? (fbMcBase + q.tsOff + slot * 16ull) : 0;
    const uint64_t tsEndMc = emitTs ? (tsStartMc + 8ull) : 0;
    if (emitTs) {
        volatile uint64_t *tp = reinterpret_cast<volatile uint64_t *>(fbAper->getVirtualAddress() + q.tsOff + slot * 16u);
        tp[0] = 0;
        tp[1] = 0;
    }
    uint32_t k = 0;
    if (!q.gfx) {
        ringPut(q, k++, 0xc0065800u);
        ringPut(q, k++, 0x00000000u);
        ringPut(q, k++, 0xffffffffu);
        ringPut(q, k++, 0x00ffffffu);
        ringPut(q, k++, 0x00000000u);
        ringPut(q, k++, 0x00000000u);
        ringPut(q, k++, 0x0000000au);
        ringPut(q, k++, 0x0000c3b1u);
    }
    if (emitTs) {
        // GFX11 RELEASE_MEM: CACHE_FLUSH_AND_INV_TS (event 0x14, idx 5), DATA_SEL=3 (64-bit GPU clock)
        ringPut(q, k++, 0xC0064900u);
        ringPut(q, k++, 0x00000514u);
        ringPut(q, k++, 0x60000000u);
        ringPut(q, k++, static_cast<uint32_t>(tsStartMc));
        ringPut(q, k++, static_cast<uint32_t>(tsStartMc >> 32));
        ringPut(q, k++, 0u);
        ringPut(q, k++, 0u);
        ringPut(q, k++, 0u);
    }
    for (uint32_t i = 0; i < n; i++) {
        ringPut(q, k++, 0xC0023F00);                               // INDIRECT_BUFFER
        // the CP wants the canonical (sign-extended) address: an upper-half IB (bit 47, where RADV puts them) with a
        // bare 16-bit high word silently wedges the queue
        const uint64_t cva = (ibVa[i] & (1ull << 47)) ? (ibVa[i] | 0xFFFF000000000000ull) : ibVa[i];
        ringPut(q, k++, static_cast<uint32_t>(cva) & ~3u);
        ringPut(q, k++, static_cast<uint32_t>(cva >> 32));
        // size | VMID, plus VALID on compute (gfx_v11_0_ring_emit_ib_compute; the gfx variant has no VALID bit)
        ringPut(q, k++, ibDw[i] | (q.gfx ? 0u : (1u << 23)) | (vmid << 24));
    }
    if (emitTs) {
        ringPut(q, k++, 0xC0064900u);
        ringPut(q, k++, 0x00000514u);
        ringPut(q, k++, 0x60000000u);
        ringPut(q, k++, static_cast<uint32_t>(tsEndMc));
        ringPut(q, k++, static_cast<uint32_t>(tsEndMc >> 32));
        ringPut(q, k++, 0u);
        ringPut(q, k++, 0u);
        ringPut(q, k++, 0u);
    }
    const uint64_t seq = ++gSeq;
    hwv[vmid - kFirstUserVmid].lastSeq = seq;
    const uint64_t fenceMc = fbMcBase + q.fenceOff;
    ringPut(q, k++, 0xC0064900);                                   // RELEASE_MEM, as gfx_v11_0_ring_emit_fence
    ringPut(q, k++, 0x06603514);                                   // GCR SEQ|GL2_WB|GLM_INV|GLM_WB, CP 3, CACHE_FLUSH_AND_INV_TS, idx 5
    ringPut(q, k++, 0x40000000);                                   // DATA_SEL 2 (64-bit), no interrupt
    ringPut(q, k++, static_cast<uint32_t>(fenceMc));
    ringPut(q, k++, static_cast<uint32_t>(fenceMc >> 32));
    ringPut(q, k++, static_cast<uint32_t>(seq));
    ringPut(q, k++, static_cast<uint32_t>(seq >> 32));
    ringPut(q, k++, 0);
    q.wptr += k;
    const uint64_t submitAbs = mach_absolute_time();
    uint64_t submitNs = 0;
    absolutetime_to_nanoseconds(submitAbs, &submitNs);
    q.fseq[slot] = seq;
    q.fend[slot] = q.wptr;
    q.fvmid[slot] = vmid;
    q.fpid[slot] = pid;
    q.fSubmitNs[slot] = submitNs;
    q.fHasTs[slot] = emitTs;
    __asm__ __volatile__("" ::: "memory");
    q.tail = q.tail + 1;
    telemetryNoteSubmit(pid, submitAbs);
'''

ANCHOR_HANG_CHECK = '''void PhxBringup::hangCheck() {
    const int limitMs = gHangMs;
    if (limitMs <= 0 || !mmio)
        return;
'''
INSERT_HANG_CHECK = '''void PhxBringup::hangCheck() {
    if (gpuLock) {
        IOLockLock(gpuLock);
        for (GpuQueue &q : gq)
            retireQueueLocked(q);
        IOLockUnlock(gpuLock);
    }
    const int limitMs = gHangMs;
    if (limitMs <= 0 || !mmio)
        return;
'''

ANCHOR_INIT_CLIENT = '    maps = static_cast<Map *>(IOMallocZero(sizeof(Map) * kMaxMaps));\n'
INSERT_INIT_CLIENT = '''    maps = static_cast<Map *>(IOMallocZero(sizeof(Map) * kMaxMaps));
    static volatile SInt64 nextUmaOwner;
    umaOwnerId = static_cast<uint64_t>(OSAddAtomic64(1, &nextUmaOwner) + 1);
    clientPid = proc_selfpid();
    if (clientPid > 0)
        proc_name(clientPid, clientProcName, sizeof(clientProcName));
    else
        clientProcName[0] = '\\0';
'''

ANCHOR_CLIENT_START = '''    if (owner->claimSession())
        sessionClaimed = true;
    return IOUserClient::start(provider);
'''
INSERT_CLIENT_START = '''    if (owner->claimSession())
        sessionClaimed = true;
    if (!IOUserClient::start(provider))
        return false;
    if (clientPid > 0 && !telemetryOpen) {
        owner->telemetryClientOpen(clientPid, clientProcName);
        telemetryOpen = true;
    }
    return true;
'''

ANCHOR_FREE_ALL = '''    for (uint32_t h = 1; h < PHXN_MAX_BOS; h++)
        if (bos[h].md)
            boRelease(bos[h]);
'''
INSERT_FREE_ALL = '''    for (uint32_t h = 1; h < PHXN_MAX_BOS; h++)
        if (bos[h].md || bos[h].uma)
            boRelease(bos[h]);
    if (owner && (visUsed || hiUsed || umaUsed || gttUsed || hostUsed)) {
        const uint64_t vramRem = visUsed + hiUsed + umaUsed;
        owner->telemetryAddMemory(clientPid,
                                  -static_cast<int64_t>(vramRem),
                                  -static_cast<int64_t>(gttUsed),
                                  -static_cast<int64_t>(hostUsed));
    }
    visUsed = hiUsed = umaUsed = gttUsed = hostUsed = 0;
'''

ANCHOR_CLIENT_CLOSE = '''IOReturn IOAccelPhxNativeClient::clientClose() {
    if (lock)
        IOLockLock(lock);
    freeAll();
    if (lock)
        IOLockUnlock(lock);
    if (vmid && owner) {
        owner->vmidFree(vmid, lastSeq);
        vmid = 0;
    }
'''
INSERT_CLIENT_CLOSE = '''IOReturn IOAccelPhxNativeClient::clientClose() {
    uint32_t closingVmid = 0;
    uint64_t closingSeq = 0;
    if (lock)
        IOLockLock(lock);
    closingVmid = vmid;
    closingSeq = lastSeq;
    vmid = 0;
    if (lock)
        IOLockUnlock(lock);
    // Tear down and retire the GPUVM context BEFORE releasing BOs so UMA
    // backing pages are never returned to the pool while PTEs or waves live.
    if (closingVmid && owner)
        owner->vmidFree(closingVmid, closingSeq);
    if (lock)
        IOLockLock(lock);
    freeAll();
    if (lock)
        IOLockUnlock(lock);
    if (telemetryOpen && owner) {
        owner->telemetryClientClose(clientPid);
        telemetryOpen = false;
    }
'''

ANCHOR_CLIENT_FREE = '''    if (sessionClaimed && owner)
        owner->releaseSession();
    if (bos)
'''
INSERT_CLIENT_FREE = '''    if (telemetryOpen && owner) {
        owner->telemetryClientClose(clientPid);
        telemetryOpen = false;
    }
    if (sessionClaimed && owner)
        owner->releaseSession();
    if (bos)
'''

ANCHOR_FIND_BO = '''IOAccelPhxNativeClient::Bo *IOAccelPhxNativeClient::findBo(uint32_t h) {
    if (h == 0 || h >= PHXN_MAX_BOS || !bos[h].md)
        return nullptr;
    return &bos[h];
}
'''
INSERT_FIND_BO = '''IOAccelPhxNativeClient::Bo *IOAccelPhxNativeClient::findBo(uint32_t h) {
    if (h == 0 || h >= PHXN_MAX_BOS || (!bos[h].md && !bos[h].uma))
        return nullptr;
    return &bos[h];
}
'''

ANCHOR_CLIENT_MEM = '''    Bo *b = findBo(type);
    if (!b) {
        IOLockUnlock(lock);
        return kIOReturnNotFound;
    }
    b->md->retain();
'''
INSERT_CLIENT_MEM = '''    Bo *b = findBo(type);
    if (!b) {
        IOLockUnlock(lock);
        return kIOReturnNotFound;
    }
    if (b->uma || !b->md) {
        IOLockUnlock(lock);
        return kIOReturnUnsupported;
    }
    b->md->retain();
'''

ANCHOR_QUERY_INFO = '''    inf.vram_vis_total = kVisTotal;
    inf.vram_vis_free = kVisTotal - visUsed;
    inf.vram_hi_total = kHiTotal;
    inf.vram_hi_free = kHiTotal - hiUsed;
    inf.gtt_cap = kGttCap;
    inf.gtt_used = gttUsed;
    inf.gtt_max_bo = kGttMaxBo;
'''
INSERT_QUERY_INFO = '''    uint64_t umaHiTotal = 0, umaHiFree = 0;
    int umaMode = 0;
    const uint64_t visFree = kVisTotal > visUsed ? kVisTotal - visUsed : 0;
    if (owner->umaQueryHiPool(umaHiTotal, umaHiFree, &umaMode)) {
        if (umaMode >= 2) {
            // On Phoenix APU (has_dedicated_vram == 0), RADV discards vram_hi_total
            // and computes DEVICE_LOCAL = 2/3 * (vram_vis_total + gtt_cap) and
            // GTT = 1/3 * (vram_vis_total + gtt_cap). Report the combined visible +
            // verified high-UMA pool in vram_vis_* with a 2 GiB GTT cap so RADV and
            // NVMTL see the real ~4 GiB VRAM heap while doBoCreate keeps CPU-mappable
            // allocations bounded to kVisTotal and backs NO_CPU_ACCESS VRAM BOs in UMA.
            inf.vram_vis_total = kVisTotal + umaHiTotal;
            inf.vram_vis_free = visFree + umaHiFree;
            inf.vram_hi_total = 0;
            inf.vram_hi_free = 0;
            inf.gtt_cap = kUmaFullGttCap;
            inf.gtt_used = gttUsed;
            inf.gtt_max_bo = kGttMaxBo;
        } else {
            inf.vram_vis_total = kVisTotal;
            inf.vram_vis_free = visFree;
            inf.vram_hi_total = umaHiTotal;
            inf.vram_hi_free = umaHiFree;
            inf.gtt_cap = kGttCap;
            inf.gtt_used = gttUsed;
            inf.gtt_max_bo = kGttMaxBo;
        }
    } else {
        inf.vram_vis_total = kVisTotal;
        inf.vram_vis_free = visFree;
        inf.vram_hi_total = kHiTotal;
        inf.vram_hi_free = kHiTotal > hiUsed ? kHiTotal - hiUsed : 0;
        inf.gtt_cap = kGttCap;
        inf.gtt_used = gttUsed;
        inf.gtt_max_bo = kGttMaxBo;
    }
'''

ANCHOR_BOCREATE_POOL = '''    uint32_t domain, bits;
    uint64_t *pool;
    if (d & PHX_AMDGPU_GEM_DOMAIN_VRAM) {
        if (visUsed + size <= kVisTotal) {
            domain = 4;
            bits = PHXN_PLACED_CPU_MAPPABLE | PHXN_PLACED_ZEROED;
            pool = &visUsed;
        } else if ((f & PHX_AMDGPU_GEM_CREATE_NO_CPU_ACCESS) && !(f & PHX_AMDGPU_GEM_CREATE_CPU_ACCESS_REQUIRED) &&
                   hiUsed + size <= kHiTotal) {
            domain = 4;
            bits = PHXN_PLACED_HI_POOL | PHXN_PLACED_ZEROED;
            pool = &hiUsed;
        } else {
            return kIOReturnNoMemory;
        }
    } else {
        if (size > kGttMaxBo || gttUsed + size > kGttCap)
            return kIOReturnNoMemory;
        domain = 2;
        bits = PHXN_PLACED_ZEROED;
        pool = &gttUsed;
    }

    uint32_t h = 1;
    while (h < PHXN_MAX_BOS && bos[h].md)
        h++;
    if (h >= PHXN_MAX_BOS)
        return kIOReturnNoResources;

    // Page alignment only: the GPU maps BOs page by page, and the client picks the VA (GEMVA) with its own alignment.
    // Handed to IOBufferMemoryDescriptor, RADV's 64 KiB..2 MiB alignment made every allocation PHYSICALLY CONTIGUOUS
    // (XNU allocates an alignment above the page size with kmem_alloc_contig): once memory was fragmented, every
    // buffer of 8 MiB or more failed after a 400 ms search, and each Metal app spent ~0.8 s at launch (2026-10-21).
    (void)align;
    IOBufferMemoryDescriptor *md = IOBufferMemoryDescriptor::inTaskWithOptions(
        kernel_task, kIODirectionInOut | kIOMemoryKernelUserShared, size, PAGE_SIZE);
    if (!md)
        return kIOReturnNoMemory;
    bzero(md->getBytesNoCopy(), size);
    *pool += size;
    bos[h] = Bo{md, size, domain, bits, static_cast<uint8_t *>(md->getBytesNoCopy()), false};
'''
INSERT_BOCREATE_POOL = '''    uint32_t domain, bits;
    uint64_t *pool;
    const bool wantsHiUma = (d & PHX_AMDGPU_GEM_DOMAIN_VRAM) &&
                            (f & PHX_AMDGPU_GEM_CREATE_NO_CPU_ACCESS) &&
                            !(f & PHX_AMDGPU_GEM_CREATE_CPU_ACCESS_REQUIRED);

    uint32_t h = 1;
    while (h < PHXN_MAX_BOS && (bos[h].md || bos[h].uma))
        h++;
    if (h >= PHXN_MAX_BOS)
        return kIOReturnNoResources;

    if (wantsHiUma) {
        phx::uma::HighUmaAllocator::Allocation umaAlloc{};
        if (owner->umaAlloc(umaOwnerId, size, align, umaAlloc)) {
            bos[h] = Bo{nullptr, umaAlloc.bytes, 4, PHXN_PLACED_HI_POOL | PHXN_PLACED_ZEROED, nullptr, false,
                        true, umaAlloc.slot, umaAlloc.serial, umaAlloc.vramOffset};
            umaUsed += umaAlloc.bytes;
            owner->telemetryAddMemory(clientPid, static_cast<int64_t>(umaAlloc.bytes), 0, 0);
            a->scalarOutput[0] = h;
            a->scalarOutput[1] = umaAlloc.bytes;
            a->scalarOutput[2] = 4;
            a->scalarOutput[3] = PHXN_PLACED_HI_POOL | PHXN_PLACED_ZEROED;
            return kIOReturnSuccess;
        }
    }

    if (d & PHX_AMDGPU_GEM_DOMAIN_VRAM) {
        if (visUsed + size <= kVisTotal) {
            domain = 4;
            bits = PHXN_PLACED_CPU_MAPPABLE | PHXN_PLACED_ZEROED;
            pool = &visUsed;
        } else if (wantsHiUma && hiUsed + size <= kHiTotal) {
            domain = 4;
            bits = PHXN_PLACED_HI_POOL | PHXN_PLACED_ZEROED;
            pool = &hiUsed;
        } else {
            return kIOReturnNoMemory;
        }
    } else {
        uint64_t umaHiTotal = 0, umaHiFree = 0;
        int umaMode = 0;
        const uint64_t effectiveGttCap =
            (owner->umaQueryHiPool(umaHiTotal, umaHiFree, &umaMode) && umaMode >= 2)
                ? kUmaFullGttCap : kGttCap;
        if (size > kGttMaxBo || gttUsed + size > effectiveGttCap)
            return kIOReturnNoMemory;
        domain = 2;
        bits = PHXN_PLACED_ZEROED;
        pool = &gttUsed;
    }

    // Page alignment only: the GPU maps BOs page by page, and the client picks the VA (GEMVA) with its own alignment.
    // Handed to IOBufferMemoryDescriptor, RADV's 64 KiB..2 MiB alignment made every allocation PHYSICALLY CONTIGUOUS
    // (XNU allocates an alignment above the page size with kmem_alloc_contig): once memory was fragmented, every
    // buffer of 8 MiB or more failed after a 400 ms search, and each Metal app spent ~0.8 s at launch (2026-10-21).
    (void)align;
    IOBufferMemoryDescriptor *md = IOBufferMemoryDescriptor::inTaskWithOptions(
        kernel_task, kIODirectionInOut | kIOMemoryKernelUserShared, size, PAGE_SIZE);
    if (!md)
        return kIOReturnNoMemory;
    bzero(md->getBytesNoCopy(), size);
    *pool += size;
    bos[h] = Bo{md, size, domain, bits, static_cast<uint8_t *>(md->getBytesNoCopy()), false, false, 0, 0, 0};
    if (domain == 4)
        owner->telemetryAddMemory(clientPid, static_cast<int64_t>(size), 0, 0);
    else
        owner->telemetryAddMemory(clientPid, 0, static_cast<int64_t>(size), 0);
'''

ANCHOR_BOFREE_BODY = '''    for (int i = 0; i < kMaxMaps; i++)
        if (maps[i].used && maps[i].handle == h)
            maps[i].used = false;
    if (b->host)
        hostUsed -= b->size;
    else if (b->domain == 2)
        gttUsed -= b->size;
    else if (b->bits & PHXN_PLACED_HI_POOL)
        hiUsed -= b->size;
    else
        visUsed -= b->size;
    boRelease(*b);
    return kIOReturnSuccess;
'''
INSERT_BOFREE_BODY = '''    for (int i = 0; i < kMaxMaps; i++) {
        if (maps[i].used && maps[i].handle == h) {
            if (b->uma && vmid)
                owner->vmUnmap(vmid, maps[i].va, maps[i].size);
            maps[i].used = false;
        }
    }
    if (b->uma) {
        const uint32_t slot = b->umaSlot;
        const uint64_t serial = b->umaSerial;
        const uint64_t seq = lastSeq;
        const uint64_t freedBytes = b->size;
        umaUsed = umaUsed >= freedBytes ? umaUsed - freedBytes : 0;
        *b = Bo{};
        if (owner) {
            owner->telemetryAddMemory(clientPid, -static_cast<int64_t>(freedBytes), 0, 0);
            IOLockUnlock(lock);
            owner->umaFree(umaOwnerId, slot, serial, seq);
            IOLockLock(lock);
        }
        return kIOReturnSuccess;
    }
    if (b->host) {
        hostUsed -= b->size;
        if (owner) owner->telemetryAddMemory(clientPid, 0, 0, -static_cast<int64_t>(b->size));
    } else if (b->domain == 2) {
        gttUsed -= b->size;
        if (owner) owner->telemetryAddMemory(clientPid, 0, -static_cast<int64_t>(b->size), 0);
    } else if (b->bits & PHXN_PLACED_HI_POOL) {
        hiUsed -= b->size;
        if (owner) owner->telemetryAddMemory(clientPid, -static_cast<int64_t>(b->size), 0, 0);
    } else {
        visUsed -= b->size;
        if (owner) owner->telemetryAddMemory(clientPid, -static_cast<int64_t>(b->size), 0, 0);
    }
    boRelease(*b);
    return kIOReturnSuccess;
'''

ANCHOR_BO_RELEASE = '''void IOAccelPhxNativeClient::boRelease(Bo &b) {
    if (b.host)
        b.md->complete();
    b.md->release();
    b = Bo{};
}
'''
INSERT_BO_RELEASE = '''void IOAccelPhxNativeClient::boRelease(Bo &b) {
    if (b.uma) {
        if (owner)
            owner->umaFree(umaOwnerId, b.umaSlot, b.umaSerial, lastSeq);
        b = Bo{};
        return;
    }
    if (b.host)
        b.md->complete();
    if (b.md)
        b.md->release();
    b = Bo{};
}
'''

ANCHOR_IMPORT_HOST_LOOP = '''    uint32_t h = 1;
    while (h < PHXN_MAX_BOS && bos[h].md)
        h++;
'''
INSERT_IMPORT_HOST_LOOP = '''    uint32_t h = 1;
    while (h < PHXN_MAX_BOS && (bos[h].md || bos[h].uma))
        h++;
'''

ANCHOR_IMPORT_HOST_SET = '    bos[h] = Bo{md, size, 2, 0, nullptr, true};\n'
INSERT_IMPORT_HOST_SET = '''    bos[h] = Bo{md, size, 2, 0, nullptr, true, false, 0, 0, 0};
    if (owner)
        owner->telemetryAddMemory(clientPid, 0, 0, static_cast<int64_t>(size));
'''

ANCHOR_DOSUBMIT_CALL = '        const IOReturn r = owner->gpuSubmit(vmid, ib0.ip_type == PHX_AMDGPU_HW_IP_GFX, va, dw, h.num_ibs, &seq);\n'
INSERT_DOSUBMIT_CALL = '        const IOReturn r = owner->gpuSubmit(vmid, ib0.ip_type == PHX_AMDGPU_HW_IP_GFX, va, dw, h.num_ibs, &seq, clientPid);\n'

ANCHOR_GEMVA_MAP = '''        maps[freei] = Map{true, v->handle, va, v->map_size, v->offset_in_bo, v->flags};
        if (owner->gpuReady()) {
            const IOReturn r = ensureVmid() ? owner->vmMap(vmid, va, b->md, v->offset_in_bo, v->map_size) : kIOReturnNoResources;
            if (r != kIOReturnSuccess) {
                maps[freei].used = false;
                return r;
            }
        }
        return kIOReturnSuccess;
'''
INSERT_GEMVA_MAP = '''        if (b->uma && (v->flags & PHX_AMDGPU_VM_PAGE_EXECUTABLE))
            (void)0;   // local VRAM PTE keeps EXEC (0x71 | MTYPE 4): RADV maps every VRAM BO EXECUTABLE
        maps[freei] = Map{true, v->handle, va, v->map_size, v->offset_in_bo, v->flags};
        if (owner->gpuReady()) {
            IOReturn r = kIOReturnNoResources;
            if (ensureVmid()) {
                if (b->uma)
                    r = owner->vmMapUma(vmid, va, umaOwnerId, b->umaSlot, b->umaSerial,
                                        v->offset_in_bo, v->map_size, (v->flags & (1u << 2)) != 0);
                else
                    r = owner->vmMap(vmid, va, b->md, v->offset_in_bo, v->map_size);
            }
            if (r != kIOReturnSuccess) {
                maps[freei].used = false;
                return r;
            }
        }
        return kIOReturnSuccess;
'''

ANCHOR_IB_COVERED = '''        for (int i = 0; i < kMaxMaps; i++) {
            const Map &mp = maps[i];
            if (mp.used && (mp.flags & PHX_AMDGPU_VM_PAGE_EXECUTABLE) && cur >= mp.va && cur < mp.va + mp.size) {
                cur = mp.va + mp.size < end ? mp.va + mp.size : end;
                ok = true;
                break;
            }
        }
'''
INSERT_IB_COVERED = '''        for (int i = 0; i < kMaxMaps; i++) {
            const Map &mp = maps[i];
            if (mp.used && (mp.flags & PHX_AMDGPU_VM_PAGE_EXECUTABLE) && cur >= mp.va && cur < mp.va + mp.size) {
                // CP instruction fetch from the high UMA carve-out faults on Phoenix (live
                // 2026-11-28: data reads/writes/copies all pass, an IB placed there GPUVM-faults
                // and hangs the queue). RADV keeps every IB in GTT; refuse it here so a client
                // can never trip the fault.
                const Bo *mapped = findBo(mp.handle);
                if (mapped && mapped->uma)
                    return false;
                cur = mp.va + mp.size < end ? mp.va + mp.size : end;
                ok = true;
                break;
            }
        }
'''

REPLACEMENTS = [
    (ANCHOR_INCLUDES, INSERT_INCLUDES),
    (ANCHOR_SYSCTL, INSERT_SYSCTL),
    (ANCHOR_GTT_CAP, INSERT_GTT_CAP),
    (ANCHOR_PUBLIC_METHODS, INSERT_PUBLIC_METHODS),
    (ANCHOR_GPUSUBMIT_DECL, INSERT_GPUSUBMIT_DECL),
    (ANCHOR_GPUQUEUE_STRUCT, INSERT_GPUQUEUE_STRUCT),
    (ANCHOR_PT_CHUNKS, INSERT_PT_CHUNKS),
    (ANCHOR_PRIVATE_MEMBERS, INSERT_PRIVATE_MEMBERS),
    (ANCHOR_BO_STRUCT, INSERT_BO_STRUCT),
    (ANCHOR_CLIENT_MEMBERS, INSERT_CLIENT_MEMBERS),
    (ANCHOR_START_LOCK, INSERT_START_LOCK),
    (ANCHOR_START_PROBE, INSERT_START_PROBE),
    (ANCHOR_STOP_SYSCTL, INSERT_STOP_SYSCTL),
    (ANCHOR_SLEEP, INSERT_SLEEP),
    (ANCHOR_READ_FB_END, INSERT_UMA_HELPERS),
    (ANCHOR_ADOPT_QUEUE, INSERT_ADOPT_QUEUE),
    (ANCHOR_VMUNMAP, INSERT_VMMAP_UMA),
    (ANCHOR_GPUSUBMIT_BODY, INSERT_GPUSUBMIT_BODY),
    (ANCHOR_HANG_CHECK, INSERT_HANG_CHECK),
    (ANCHOR_SYSCTL_REG, INSERT_SYSCTL_REG),
    (ANCHOR_INIT_CLIENT, INSERT_INIT_CLIENT),
    (ANCHOR_CLIENT_START, INSERT_CLIENT_START),
    (ANCHOR_FREE_ALL, INSERT_FREE_ALL),
    (ANCHOR_CLIENT_CLOSE, INSERT_CLIENT_CLOSE),
    (ANCHOR_CLIENT_FREE, INSERT_CLIENT_FREE),
    (ANCHOR_FIND_BO, INSERT_FIND_BO),
    (ANCHOR_CLIENT_MEM, INSERT_CLIENT_MEM),
    (ANCHOR_QUERY_INFO, INSERT_QUERY_INFO),
    (ANCHOR_BOCREATE_POOL, INSERT_BOCREATE_POOL),
    (ANCHOR_BOFREE_BODY, INSERT_BOFREE_BODY),
    (ANCHOR_BO_RELEASE, INSERT_BO_RELEASE),
    (ANCHOR_IMPORT_HOST_LOOP, INSERT_IMPORT_HOST_LOOP),
    (ANCHOR_IMPORT_HOST_SET, INSERT_IMPORT_HOST_SET),
    (ANCHOR_GEMVA_MAP, INSERT_GEMVA_MAP),
    (ANCHOR_IB_COVERED, INSERT_IB_COVERED),
    (ANCHOR_DOSUBMIT_CALL, INSERT_DOSUBMIT_CALL),
]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stage_driver(driver_bytes: bytes) -> bytes:
    if type(driver_bytes) is not bytes or sha256(driver_bytes) != DRIVER_SHA256:
        raise ValueError('PhxBringup.cpp SHA-256 mismatch; expected exact build34 baseline')
    text = driver_bytes.decode('utf-8')
    if '#define PHX_KEXT_BUILD 34u\n' not in text:
        raise ValueError('Expected build34 PhxBringup.cpp')
    for old, new in REPLACEMENTS:
        count = text.count(old)
        if count != 1:
            raise ValueError(f'Anchor count {count} != 1 for: {old[:60]!r}')
        text = text.replace(old, new, 1)
    return text.encode('utf-8')


def build_candidate(sdk_path: Path, out_dir: Path) -> Path:
    if platform.system() != 'Darwin' or platform.machine() != 'x86_64':
        raise RuntimeError('Native kext build requires Intel macOS')
    out_dir = out_dir.resolve()
    if out_dir.exists():
        raise FileExistsError(f'Output directory already exists: {out_dir}')
    if ROOT / 'build' not in out_dir.parents or not out_dir.name.endswith('-private'):
        raise ValueError('Output directory must live under build/*-private')

    src_dir = out_dir / 'src/phxbringup'
    src_dir.mkdir(parents=True, mode=0o700)
    amd_dir = out_dir / 'src/amd'
    amd_dir.mkdir(parents=True, mode=0o700)
    shutil.copy2(ROOT / 'src/amd/phx_topology.h', amd_dir / 'phx_topology.h')
    phx_dir = ROOT / 'src/phxbringup'
    for name in ('Info.plist', 'PhxNativeABI.h', 'PhxUmaPool.h', 'PhxTelemetry.h', 'kmod_info.c', 'build.sh'):
        shutil.copy2(phx_dir / name, src_dir / name)
    staged = stage_driver((phx_dir / 'PhxBringup.cpp').read_bytes())
    (src_dir / 'PhxBringup.cpp').write_bytes(staged)

    subprocess.run(['/bin/sh', str(src_dir / 'build.sh'), str(sdk_path.resolve())],
                   cwd=src_dir, check=True)
    kext = src_dir / 'build/PhxBringup.kext'
    exe = kext / 'Contents/MacOS/PhxBringup'
    if not exe.is_file():
        raise RuntimeError('PhxBringup binary missing after build')
    subprocess.run(['/usr/bin/codesign', '--force', '--sign', '-', str(kext)], check=True)
    return kext


def main() -> int:
    parser = argparse.ArgumentParser(description='Stage/build opt-in build34 UMA PhxBringup candidate')
    parser.add_argument('--sdk', type=Path, required=True, help='Path to MacKernelSDK')
    parser.add_argument('--out', type=Path, required=True, help='Fresh build/*-private output path')
    args = parser.parse_args()
    kext = build_candidate(args.sdk, args.out)
    exe = kext / 'Contents/MacOS/PhxBringup'
    print(f'staged PhxBringup.kext: {kext}')
    print(f'sha256: {sha256(exe.read_bytes())}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
