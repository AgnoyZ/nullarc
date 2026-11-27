#pragma once

#include <stdint.h>
#include "phx_dcn_zerocopy.h"

namespace phx::dcncur {

inline constexpr uint32_t kDcnSeg2Base = phx::dcnzc::kDcnSeg2Base;

// HUBP0 / HUBPREQ0 cursor registers (DCN 3.1.4 DMU segment 2, dword offsets)
inline constexpr uint32_t kRegCursorSettings = kDcnSeg2Base + 0x065cu;    // 0x03b1c
inline constexpr uint32_t kRegCursorControl = kDcnSeg2Base + 0x0678u;     // 0x03b38
inline constexpr uint32_t kRegCursorSurfAddrLo = kDcnSeg2Base + 0x0679u;  // 0x03b39
inline constexpr uint32_t kRegCursorSurfAddrHi = kDcnSeg2Base + 0x067au;  // 0x03b3a
inline constexpr uint32_t kRegCursorSize = kDcnSeg2Base + 0x067bu;        // 0x03b3b
inline constexpr uint32_t kRegCursorPosition = kDcnSeg2Base + 0x067cu;    // 0x03b3c
inline constexpr uint32_t kRegCursorHotSpot = kDcnSeg2Base + 0x067du;     // 0x03b3d
inline constexpr uint32_t kRegCursorDstOffset = kDcnSeg2Base + 0x067fu;   // 0x03b3f
inline constexpr uint32_t kRegCursorMemPwrCtrl = kDcnSeg2Base + 0x0680u;  // 0x03b40

// DPP0 / CNVC0 cursor registers (DCN 3.1.4 DMU segment 2, dword offsets)
inline constexpr uint32_t kRegCnvcCur0Control = kDcnSeg2Base + 0x0cf1u;   // 0x041b1

// CURSOR0_0_CURSOR_CONTROL fields
inline constexpr uint32_t kCurCtlEnable = 1u << 0;
inline constexpr uint32_t kCurCtlReqMode = 1u << 2;
inline constexpr uint32_t kCurCtlMagnify2x = 1u << 4;
inline constexpr uint32_t kCurCtlModeShift = 8u;
inline constexpr uint32_t kCurCtlModeMask = 0x7u << kCurCtlModeShift;
inline constexpr uint32_t kCurCtlPitchShift = 16u;
inline constexpr uint32_t kCurCtlPitchMask = 0x3u << kCurCtlPitchShift;
inline constexpr uint32_t kCurCtlLinesPerChunkShift = 24u;
inline constexpr uint32_t kCurCtlLinesPerChunkMask = 0x1fu << kCurCtlLinesPerChunkShift;

// CNVC_CUR0_CURSOR0_CONTROL fields
inline constexpr uint32_t kCnvcCur0Enable = 1u << 0;
inline constexpr uint32_t kCnvcCur0ExpansionMask = 1u << 1;
inline constexpr uint32_t kCnvcCur0RomEnMask = 1u << 3;
inline constexpr uint32_t kCnvcCur0ModeShift = 4u;
inline constexpr uint32_t kCnvcCur0ModeMask = 0x7u << kCnvcCur0ModeShift;

// HUBPREQ0_CURSOR_SETTINGS fields
inline constexpr uint32_t kCurSettingsChunkHdlAdjust = 3u << 8;

// CURSOR0_0_CURSOR_MEM_PWR_CTRL fields
inline constexpr uint32_t kCurMemPwrForceMask = 0x3u;
inline constexpr uint32_t kCurMemPwrDis = 1u << 2;

// DCN cursor color modes (dc_cursor_color_format)
inline constexpr uint32_t kCursorModeMono = 0u;
inline constexpr uint32_t kCursorModeColor1BitAnd = 1u;
inline constexpr uint32_t kCursorModeColorPreMultAlpha = 2u;
inline constexpr uint32_t kCursorModeColorUnPreMultAlpha = 3u;

// DCN cursor pitch codes (enum cursor_pitch)
inline constexpr uint32_t kCursorPitch64 = 0u;
inline constexpr uint32_t kCursorPitch128 = 1u;
inline constexpr uint32_t kCursorPitch256 = 2u;

// DCN cursor lines per chunk codes (enum cursor_lines_per_chunk)
inline constexpr uint32_t kCursorLpc1 = 0u;
inline constexpr uint32_t kCursorLpc2 = 1u;
inline constexpr uint32_t kCursorLpc4 = 2u;
inline constexpr uint32_t kCursorLpc8 = 3u;
inline constexpr uint32_t kCursorLpc16 = 4u;

// Double-buffered 128x128 32bpp cursor surface mapped in the top 32 PTEs of each zero-copy VMID slot.
inline constexpr uint32_t kMaxCursorDim = 128u;
inline constexpr uint32_t kCursorBufferCount = 2u;
inline constexpr uint32_t kCursorSlotBytes = kMaxCursorDim * kMaxCursorDim * 4u; // 64 KiB
inline constexpr uint32_t kCursorSlotPages = kCursorSlotBytes / static_cast<uint32_t>(phx::dcnzc::kPageBytes); // 16
inline constexpr uint32_t kCursorTotalPages = kCursorSlotPages * kCursorBufferCount; // 32
inline constexpr uint64_t kCursorTotalBytes = static_cast<uint64_t>(kCursorTotalPages) * phx::dcnzc::kPageBytes; // 128 KiB
inline constexpr uint32_t kCursorPageStart = phx::dcnzc::kMaxPages - kCursorTotalPages; // 8160
inline constexpr uint64_t kCursorVaOffset = static_cast<uint64_t>(kCursorPageStart) * phx::dcnzc::kPageBytes;

static_assert(kCursorPageStart == 8160u, "cursor pages occupy top 32 PTEs of the 8192-PTE flat table");
static_assert(kCursorPageStart + kCursorTotalPages == phx::dcnzc::kMaxPages, "cursor range matches kMaxPages");

inline constexpr uint64_t cursorVaForSlot(uint32_t zcSlotIndex, uint32_t bufferIndex) {
    return phx::dcnzc::slotVa(zcSlotIndex) + kCursorVaOffset +
        static_cast<uint64_t>(bufferIndex % kCursorBufferCount) * kCursorSlotBytes;
}

inline constexpr bool selectCursorPitch(uint32_t width, uint32_t &pitchPixelsOut, uint32_t &hwPitchOut) {
    if (width == 0 || width > kMaxCursorDim) return false;
    if (width <= 64u) {
        pitchPixelsOut = 64u;
        hwPitchOut = kCursorPitch64;
        return true;
    }
    pitchPixelsOut = 128u;
    hwPitchOut = kCursorPitch128;
    return true;
}

inline constexpr bool selectLinesPerChunk32bpp(uint32_t width, uint32_t &lpcOut) {
    if (width == 0 || width > 256u) return false;
    if (width <= 32u) { lpcOut = kCursorLpc16; return true; }
    if (width <= 64u) { lpcOut = kCursorLpc8; return true; }
    if (width <= 128u) { lpcOut = kCursorLpc4; return true; }
    lpcOut = kCursorLpc2;
    return true;
}

inline constexpr uint32_t encodeCursorSize(uint32_t width, uint32_t height) {
    return ((width & 0x1ffu) << 16) | (height & 0x1ffu);
}

inline constexpr uint32_t encodeCursorControl(uint32_t prior, bool enable, uint32_t mode,
                                              uint32_t hwPitch, uint32_t lpc) {
    constexpr uint32_t kClearMask = kCurCtlEnable | kCurCtlReqMode | kCurCtlMagnify2x |
        kCurCtlModeMask | kCurCtlPitchMask | kCurCtlLinesPerChunkMask;
    uint32_t value = (prior & ~kClearMask) | kCurCtlReqMode;
    if (enable) value |= kCurCtlEnable;
    value |= (mode & 0x7u) << kCurCtlModeShift;
    value |= (hwPitch & 0x3u) << kCurCtlPitchShift;
    value |= (lpc & 0x1fu) << kCurCtlLinesPerChunkShift;
    return value;
}

inline constexpr uint32_t encodeCnvcCursorControl(uint32_t prior, bool enable, uint32_t mode) {
    constexpr uint32_t kClearMask = kCnvcCur0Enable | kCnvcCur0ExpansionMask |
        kCnvcCur0RomEnMask | kCnvcCur0ModeMask;
    uint32_t value = prior & ~kClearMask;
    if (enable) value |= kCnvcCur0Enable;
    value |= (mode & 0x7u) << kCnvcCur0ModeShift;
    return value;
}

struct PositionRegs {
    bool visible;
    uint32_t positionReg;
    uint32_t hotSpotReg;
    uint32_t dstOffsetReg;
};

// Compute DCN cursor position, hotspot, and dst_x_offset from IOFramebuffer top-left (x, y).
// IOFramebuffer::setCursorState(x, y, visible) already subtracts the cursor hotspot from the
// pointer position, so (x, y) is the signed top-left corner of the cursor bitmap.
inline constexpr PositionRegs computeCursorPosition(int32_t topLeftX, int32_t topLeftY, bool visible,
                                                    uint32_t cursorWidth, uint32_t cursorHeight,
                                                    uint32_t fbWidth, uint32_t fbHeight,
                                                    uint32_t refClkKhz = 0, uint32_t pixelClkKhz = 0) {
    PositionRegs out{false, 0u, 0u, 0u};
    if (!visible || !cursorWidth || !cursorHeight || !fbWidth || !fbHeight) return out;
    if (cursorWidth > kMaxCursorDim || cursorHeight > kMaxCursorDim) return out;
    if (topLeftX >= static_cast<int32_t>(fbWidth) || topLeftY >= static_cast<int32_t>(fbHeight)) return out;
    if (topLeftX + static_cast<int32_t>(cursorWidth) <= 0 ||
        topLeftY + static_cast<int32_t>(cursorHeight) <= 0) return out;

    uint32_t posX = 0u;
    uint32_t posY = 0u;
    uint32_t hotX = 0u;
    uint32_t hotY = 0u;
    if (topLeftX < 0) {
        const uint32_t negX = static_cast<uint32_t>(-topLeftX);
        hotX = negX < cursorWidth ? negX : (cursorWidth - 1u);
    } else {
        posX = static_cast<uint32_t>(topLeftX);
    }
    if (topLeftY < 0) {
        const uint32_t negY = static_cast<uint32_t>(-topLeftY);
        hotY = negY < cursorHeight ? negY : (cursorHeight - 1u);
    } else {
        posY = static_cast<uint32_t>(topLeftY);
    }

    uint32_t dstXOffset = 0u;
    if (posX > 0u && refClkKhz > 0u && pixelClkKhz > 0u) {
        const uint64_t scaled = (static_cast<uint64_t>(posX) * refClkKhz) / pixelClkKhz;
        dstXOffset = scaled > 0x1fffu ? 0x1fffu : static_cast<uint32_t>(scaled);
    }

    out.visible = true;
    out.positionReg = ((posX & 0x3fffu) << 16) | (posY & 0x3fffu);
    out.hotSpotReg = ((hotX & 0xffu) << 16) | (hotY & 0xffu);
    out.dstOffsetReg = dstXOffset & 0x1fffu;
    return out;
}

// Repack tightly-packed width*height 32bpp pixels (from IOFramebuffer::convertCursorImage)
// into a DCN cursor buffer with row stride `pitchPixels`, zero-filling padding pixels.
inline bool repackCursorImage32(const uint32_t *src, uint32_t width, uint32_t height,
                                uint32_t *dst, uint32_t pitchPixels, uint32_t dstPixelsCapacity) {
    if (!src || !dst || !width || !height || width > kMaxCursorDim || height > kMaxCursorDim) return false;
    if (pitchPixels < width || (pitchPixels != 64u && pitchPixels != 128u)) return false;
    if (static_cast<uint64_t>(pitchPixels) * height > dstPixelsCapacity) return false;
    for (uint32_t row = 0; row < height; ++row) {
        const uint32_t *srcRow = src + static_cast<uint64_t>(row) * width;
        uint32_t *dstRow = dst + static_cast<uint64_t>(row) * pitchPixels;
        for (uint32_t col = 0; col < width; ++col) dstRow[col] = srcRow[col];
        for (uint32_t col = width; col < pitchPixels; ++col) dstRow[col] = 0u;
    }
    return true;
}

} // namespace phx::dcncur
