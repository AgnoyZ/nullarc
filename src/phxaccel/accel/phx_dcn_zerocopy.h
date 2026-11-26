#pragma once

#include <stdint.h>

namespace phx::dcnzc {

inline constexpr uint32_t kDcnSeg2Base = 0x034c0u;
inline constexpr uint32_t kRegFbBase = kDcnSeg2Base + 0x0475u;
inline constexpr uint32_t kRegFbTop = kDcnSeg2Base + 0x0476u;
inline constexpr uint32_t kRegFbOffset = kDcnSeg2Base + 0x0477u;
inline constexpr uint32_t kRegAgpBot = kDcnSeg2Base + 0x0478u;
inline constexpr uint32_t kRegAgpTop = kDcnSeg2Base + 0x0479u;

inline constexpr uint32_t kRegVmCtx0 = kDcnSeg2Base + 0x0559u;
inline constexpr uint32_t kVmCtxStride = 7u;
inline constexpr uint32_t kRegVmFaultCntl = kDcnSeg2Base + 0x05cbu;
inline constexpr uint32_t kRegVmFaultStatus = kDcnSeg2Base + 0x05ccu;

inline constexpr uint32_t kRegHubpSurfaceConfig = 0x03aa5u;
inline constexpr uint32_t kRegHubpTilingConfig = 0x03aa7u;
inline constexpr uint32_t kRegHubpViewportStart = 0x03aa9u;
inline constexpr uint32_t kRegHubpViewportDim = 0x03aaau;
inline constexpr uint32_t kRegHubpCntl = 0x03ab3u;
inline constexpr uint32_t kRegHubpPitch = 0x03ac7u;
inline constexpr uint32_t kRegHubpVmid0 = 0x03ac9u;
inline constexpr uint32_t kRegHubpPrimLo = 0x03acau;
inline constexpr uint32_t kRegHubpPrimHi = 0x03acbu;
inline constexpr uint32_t kRegHubpInUseLo = 0x03ae1u;
inline constexpr uint32_t kRegHubpInUseHi = 0x03ae2u;
inline constexpr uint32_t kRegHubpSurfaceCtl = 0x03adau;
inline constexpr uint32_t kRegHubpFlipCtl = 0x03adbu;
inline constexpr uint32_t kRegHubpFlipCtl2 = 0x03adcu;
inline constexpr uint32_t kRegHubpEarliestLo = 0x03ae5u;
inline constexpr uint32_t kRegHubpEarliestHi = 0x03ae6u;
inline constexpr uint32_t kRegHubpSysAperLow = 0x03af5u;
inline constexpr uint32_t kRegHubpSysAperHigh = 0x03af6u;
inline constexpr uint32_t kRegHubpL1TlbCntl = 0x03b03u;
inline constexpr uint32_t kRegHubpReturnCtl = 0x03b2cu;
inline constexpr uint32_t kRegCnvcPixelFormat = kDcnSeg2Base + 0x0ccfu; // 0x0418f

// MMHUB 3.0.1 segment 1 (0x1a000): ENG16 TLB invalidation + L2 reserved CID2 flush
inline constexpr uint32_t kMmhubSeg1Base = 0x1a000u;
inline constexpr uint32_t kRegMmhubL2ReservedCid2 = kMmhubSeg1Base + 0x071bu;
inline constexpr uint32_t kRegMmhubInvEng16Sem = kMmhubSeg1Base + 0x0761u;
inline constexpr uint32_t kRegMmhubInvEng16Req = kMmhubSeg1Base + 0x0773u;
inline constexpr uint32_t kRegMmhubInvEng16Ack = kMmhubSeg1Base + 0x0785u;
inline constexpr uint32_t kMmhubInvLegacyL2L1Mask = 0x00f80000u; // L2 PTE/PDE0..2 + L1 PTE
inline constexpr uint32_t kMmhubL2PrivateInvBit = 1u << 25;

inline constexpr uint32_t kRegOdmSelect = 0x04f8bu;
inline constexpr uint32_t kRegOtgControl = 0x05001u;
inline constexpr uint32_t kRegOtgFrameCount = 0x0500cu;
inline constexpr uint32_t kRegOtgMasterLock = 0x0504au;
inline constexpr uint32_t kRegOtgGlobalCtl2 = 0x05051u;

inline constexpr uint32_t kPixelFormatBgra = 0x42475241u;
inline constexpr uint32_t kPixelFormatL10r = 0x6c313072u;
inline constexpr uint32_t kDcnFormatArgb8888 = 8u;
inline constexpr uint32_t kDcnFormatArgb2101010 = 10u;
inline constexpr uint32_t kFormatMask = 0x7fu;
inline constexpr uint32_t kOrientationMask = 0xf00u;
inline constexpr uint32_t kSwizzleMask = 0x1fu;
inline constexpr uint32_t kStrideMask = 0x3fffu;
inline constexpr uint32_t kExtentMask = 0x3fff3fffu;
inline constexpr uint32_t kRedBlueMask = 0x00f00000u;
inline constexpr uint32_t kArgbRedBlue = 0x00e00000u;
inline constexpr uint32_t kUnsafeSurfaceCtl = 0x000f1313u;
inline constexpr uint32_t kOtgEnabledMask = 0x00010001u;
inline constexpr uint32_t kOdmSinglePipeMask = 0x000f0303u;
inline constexpr uint32_t kOtgLockReqStatus = 0x00000101u;
inline constexpr uint32_t kOtgLockSelMask = 0x0e000000u;
inline constexpr uint32_t kOtgStride = 0x80u;
inline constexpr uint32_t kHubpStride = 0xdcu;
inline constexpr uint32_t kRegHubpPeerPower1 = 0x03543u;
inline constexpr uint32_t kHubpPeerPowerStride = 2u;
inline constexpr uint32_t kHubpPeerPowerMask = 0xc0000000u;
inline constexpr uint32_t kHubpPeerPowerGated = 0x80000000u;
inline constexpr uint64_t kMinMmioBytes =
    (static_cast<uint64_t>(kRegMmhubInvEng16Ack) + 1ull) * sizeof(uint32_t);

inline constexpr uint32_t kHubpBlank = 1u << 0;
inline constexpr uint32_t kHubpNoOutstanding = 1u << 1;
inline constexpr uint32_t kHubpSoftReset = 1u << 2;
inline constexpr uint32_t kHubpVtgSel = 0x000000f0u;
inline constexpr uint32_t kHubpSegAllocErr = 1u << 11;
inline constexpr uint32_t kHubpTimeoutStatus = 0x00f00000u;
inline constexpr uint32_t kHubpUnderflowStatus = 0x70000000u;
// UEFI GOP leaves HUBP_TTU_DISABLE (bit 12) set on Phoenix; do not reject it.
inline constexpr uint32_t kHubpUnsafeCntl =
    kHubpBlank | kHubpSoftReset | kHubpVtgSel | kHubpSegAllocErr | kHubpTimeoutStatus | kHubpUnderflowStatus;

inline constexpr uint32_t kFlipImmediate = 1u << 1;
inline constexpr uint32_t kFlipPending = 1u << 8;
inline constexpr uint32_t kFlipUpdateLocked = 1u << 9;
inline constexpr uint32_t kFlipStereoMask = 0x00013000u;
inline constexpr uint32_t kFlip2UnsafeMask = (1u << 8) | (1u << 10);
inline constexpr uint32_t kL1TlbEnableSysMode3 = 0x19u; // ENABLE_L1_TLB=1 | SYSTEM_ACCESS_MODE=3

inline constexpr uint64_t kPageBytes = 4096ull;
inline constexpr uint64_t kAddressLimit = 1ull << 48;
inline constexpr uint64_t kPhysPageMask = (kAddressLimit - 1ull) & ~(kPageBytes - 1ull);
inline constexpr uint64_t kPteRootFlags = 0x7ull;                    // VALID | SYSTEM | SNOOPED
inline constexpr uint64_t kPteLeafFlags = 0x27ull | (3ull << 48);    // VALID | SYSTEM | SNOOPED | READABLE | MTYPE_UC

inline constexpr uint32_t kSlotCount = 4u;
inline constexpr uint32_t kFirstVmid = 1u;
inline constexpr uint32_t kContextFieldCount = 7u;
inline constexpr uint32_t kAllSlotBits = (1u << kSlotCount) - 1u;
inline constexpr uint32_t kMaxPages = 8192u; // 32 MiB scanout capacity (64 KiB flat page table)
inline constexpr uint64_t kPageTableBytes = static_cast<uint64_t>(kMaxPages) * sizeof(uint64_t);
inline constexpr uint64_t kSlotVaBase = 0x0000010000000000ull; // 1 TiB
inline constexpr uint64_t kSlotVaStride = 0x0000000100000000ull; // 4 GiB per slot

enum Status : int {
    kOk = 0,
    kDisabled = 1,
    kTripped = 2,
    kBadArgs = 3,
    kUnsupportedFormat = 4,
    kGeometryMismatch = 5,
    kNoMmio = 6,
    kVmFault = 7,
    kHwNotReady = 8,
    kApertureConflict = 9,
    kNoEvictableSlot = 10,
    kPrepareFailed = 11,
    kBadPhysPage = 12,
    kCtxTimeout = 13,
    kLockTimeout = 14,
};

struct ApertureSnapshot {
    uint32_t fbBase;
    uint32_t fbTop;
    uint32_t agpBot;
    uint32_t agpTop;
};

inline constexpr uint32_t vmCtxBase(uint32_t vmid) {
    return kRegVmCtx0 + vmid * kVmCtxStride;
}

inline constexpr uint32_t mmhubInvalidateReq(uint32_t vmid) {
    return kMmhubInvLegacyL2L1Mask | (1u << (vmid & 0xfu));
}

inline constexpr bool dcnPixelFormatFor(uint32_t pixelFormat, uint32_t &dcnFormatOut) {
    if (pixelFormat == kPixelFormatBgra) {
        dcnFormatOut = kDcnFormatArgb8888;
        return true;
    }
    if (pixelFormat == kPixelFormatL10r) {
        dcnFormatOut = kDcnFormatArgb2101010;
        return true;
    }
    return false;
}

inline constexpr bool supportedDcnFormat(uint32_t dcnFormat) {
    return dcnFormat == kDcnFormatArgb8888 || dcnFormat == kDcnFormatArgb2101010;
}

inline constexpr uint64_t slotVa(uint32_t slotIndex) {
    return kSlotVaBase + static_cast<uint64_t>(slotIndex) * kSlotVaStride;
}

inline constexpr bool slotUnconsumed(uint32_t slotIndex, uint32_t consumedMask) {
    return slotIndex < kSlotCount && (consumedMask & (1u << slotIndex)) == 0;
}

inline bool rangesOverlap(uint64_t firstA, uint64_t lastA, uint64_t firstB, uint64_t lastB) {
    return firstB <= lastB && firstA <= lastB && firstB <= lastA;
}

inline bool validPhysPage(uint64_t phys) {
    return phys != 0 && (phys & ~kPhysPageMask) == 0;
}

inline bool encodeRootEntry(uint64_t ptPhys, uint64_t &rootOut) {
    if (!validPhysPage(ptPhys)) return false;
    rootOut = ptPhys | kPteRootFlags;
    return true;
}

inline bool encodeLeafPte(uint64_t pagePhys, uint64_t &pteOut) {
    if (!validPhysPage(pagePhys)) return false;
    pteOut = pagePhys | kPteLeafFlags;
    return true;
}

inline bool slotVaClearOfApertures(uint64_t vaBase, uint64_t bytes, const ApertureSnapshot &ap) {
    if (!vaBase || !bytes || (vaBase % kPageBytes) != 0 || (bytes % kPageBytes) != 0) return false;
    if (vaBase >= kAddressLimit || bytes > kAddressLimit - vaBase) return false;
    if (ap.fbBase > ap.fbTop) return false;
    const uint64_t firstUnit = vaBase >> 24;
    const uint64_t lastUnit = (vaBase + bytes - 1ull) >> 24;
    if (rangesOverlap(firstUnit, lastUnit, ap.fbBase, ap.fbTop)) return false;
    if (ap.agpBot <= ap.agpTop && (ap.agpBot != 0 || ap.agpTop != 0)) {
        if (rangesOverlap(firstUnit, lastUnit, ap.agpBot, ap.agpTop)) return false;
    }
    return true;
}

inline bool addressInFbAperture(uint64_t addr, uint64_t bytes, const ApertureSnapshot &ap) {
    if (!addr || !bytes || (addr % kPageBytes) != 0 || addr >= kAddressLimit || bytes > kAddressLimit - addr)
        return false;
    if (ap.fbBase > ap.fbTop) return false;
    const uint64_t firstUnit = addr >> 24;
    const uint64_t lastUnit = (addr + bytes - 1ull) >> 24;
    return firstUnit >= ap.fbBase && lastUnit <= ap.fbTop;
}

inline void computeSystemApertureRegs(const ApertureSnapshot &ap, uint32_t &lowReg, uint32_t &highReg) {
    const uint64_t fbStart = static_cast<uint64_t>(ap.fbBase & 0x00ffffffu) << 24;
    const uint64_t fbEnd = ((static_cast<uint64_t>(ap.fbTop & 0x00ffffffu) + 1ull) << 24) - 1ull;
    lowReg = static_cast<uint32_t>(fbStart >> 18);
    highReg = static_cast<uint32_t>(fbEnd >> 18);
}

inline bool validSurfaceRequest(uint32_t pixelFormat, uint32_t width, uint32_t height, uint32_t pitch,
                                uint32_t fbWidth, uint32_t fbHeight, uint32_t fbPitch,
                                uint64_t &bytesOut, uint32_t &pagesOut) {
    uint32_t dcnFormat = 0;
    if (!dcnPixelFormatFor(pixelFormat, dcnFormat)) return false;
    if (!width || !height || width > 0x3fffu || height > 0x3fffu ||
        width != fbWidth || height != fbHeight || pitch != fbPitch) return false;
    if (static_cast<uint64_t>(pitch) < static_cast<uint64_t>(width) * 4ull || (pitch & 3u) != 0) return false;
    const uint64_t footprint = static_cast<uint64_t>(pitch) * static_cast<uint64_t>(height);
    const uint64_t alignedBytes = (footprint + kPageBytes - 1ull) & ~(kPageBytes - 1ull);
    const uint64_t pages = alignedBytes / kPageBytes;
    if (!pages || pages > kMaxPages) return false;
    bytesOut = alignedBytes;
    pagesOut = static_cast<uint32_t>(pages);
    return true;
}

inline bool contextFieldsClear(const uint32_t fields[kContextFieldCount]) {
    for (uint32_t field = 0; field < kContextFieldCount; ++field)
        if (fields[field] != 0) return false;
    return true;
}

inline bool contextMatchesOwnedState(const uint32_t expected[kContextFieldCount],
                                     const uint32_t current[kContextFieldCount]) {
    for (uint32_t field = 0; field < kContextFieldCount; ++field)
        if (current[field] != 0 && current[field] != expected[field]) return false;
    return true;
}

inline bool contextMatchesExactState(const uint32_t expected[kContextFieldCount],
                                     const uint32_t current[kContextFieldCount]) {
    for (uint32_t field = 0; field < kContextFieldCount; ++field)
        if (current[field] != expected[field]) return false;
    return true;
}

template<typename ReadReg>
bool hubpGeometryReady(uint32_t width, uint32_t height, uint32_t pitchBytes, const ReadReg &readReg,
                       bool expectUpdateLocked = false) {
    if (!width || !height || (pitchBytes & 3u) != 0) return false;
    const uint32_t pitchPixels = pitchBytes / 4u;
    if (pitchPixels < width || pitchPixels - 1u > kStrideMask) return false;
    const uint32_t cntl = readReg(kRegHubpCntl);
    if (cntl == 0xffffffffu || (cntl & kHubpUnsafeCntl) != 0) return false;
    const uint32_t otg = readReg(kRegOtgControl);
    if ((otg & kOtgEnabledMask) != kOtgEnabledMask) return false;
    const uint32_t odm = readReg(kRegOdmSelect);
    if ((odm & kOdmSinglePipeMask) != 0) return false;
    const uint32_t lockSel = readReg(kRegOtgGlobalCtl2);
    if ((lockSel & kOtgLockSelMask) != 0) return false;
    const uint32_t surfCfg = readReg(kRegHubpSurfaceConfig);
    if ((surfCfg & kOrientationMask) != 0 || !supportedDcnFormat(surfCfg & kFormatMask)) return false;
    const uint32_t retCtl = readReg(kRegHubpReturnCtl);
    if ((retCtl & kRedBlueMask) != kArgbRedBlue) return false;
    const uint32_t surfCtl = readReg(kRegHubpSurfaceCtl);
    if ((surfCtl & kUnsafeSurfaceCtl) != 0) return false;
    const uint32_t tiling = readReg(kRegHubpTilingConfig);
    if ((tiling & kSwizzleMask) != 0) return false;
    const uint32_t vpStart = readReg(kRegHubpViewportStart);
    if ((vpStart & kExtentMask) != 0) return false;
    const uint32_t vpDim = readReg(kRegHubpViewportDim);
    if ((vpDim & kExtentMask) != ((height << 16) | width)) return false;
    const uint32_t pitchReg = readReg(kRegHubpPitch);
    if ((pitchReg & kStrideMask) != (pitchPixels - 1u)) return false;
    const uint32_t flipCtl = readReg(kRegHubpFlipCtl);
    if ((flipCtl & (kFlipImmediate | kFlipPending | kFlipStereoMask)) != 0) return false;
    if (bool(flipCtl & kFlipUpdateLocked) != expectUpdateLocked) return false;
    const uint32_t flipCtl2 = readReg(kRegHubpFlipCtl2);
    if ((flipCtl2 & kFlip2UnsafeMask) != 0) return false;
    return true;
}

template<typename ReadReg>
bool hubpPeersIdle(const ReadReg &readReg) {
    const auto checkedRead = [&](uint32_t reg, uint32_t &value) {
        value = readReg(reg);
        return value != UINT32_MAX;
    };
    const auto sample = [&](uint32_t (&powerStates)[3]) {
        for (uint32_t index = 0; index < 3; ++index) {
            const uint32_t pipe = index + 1;
            uint32_t otg = 0, power = 0;
            if (!checkedRead(kRegOtgControl + pipe * kOtgStride, otg) || (otg & kOtgEnabledMask) ||
                !checkedRead(kRegHubpPeerPower1 + index * kHubpPeerPowerStride, power)) return false;
            powerStates[index] = power & kHubpPeerPowerMask;
            if (powerStates[index] == kHubpPeerPowerGated) continue;
            uint32_t control = 0, flip = 0;
            const uint32_t idleMask = kHubpBlank | kHubpNoOutstanding | (1u << 12);
            if (powerStates[index] || !checkedRead(kRegHubpCntl + pipe * kHubpStride, control) ||
                (control & idleMask) != idleMask ||
                !checkedRead(kRegHubpFlipCtl + pipe * kHubpStride, flip) ||
                (flip & (kFlipPending | kFlipUpdateLocked))) return false;
        }
        return true;
    };
    for (uint32_t attempt = 0; attempt < 2; ++attempt) {
        uint32_t before = 0, after = 0, powerBefore[3]{}, powerAfter[3]{};
        if (!checkedRead(kRegOtgFrameCount, before) || !sample(powerBefore) || !sample(powerAfter) ||
            !checkedRead(kRegOtgFrameCount, after)) return false;
        for (uint32_t index = 0; index < 3; ++index)
            if (powerBefore[index] != powerAfter[index]) return false;
        const uint32_t frames = (after - before) & 0x00ffffffu;
        if (!frames) return true;
        if (frames != 1) return false;
    }
    return false;
}

} // namespace phx::dcnzc
