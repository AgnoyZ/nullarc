#include "../src/phxaccel/accel/phx_dcn_cursor.h"

#include <cassert>
#include <cstdint>
#include <vector>

using namespace phx::dcncur;

static void testRegisterOffsetsAndLayout() {
    assert(kRegCursorSettings == 0x03b1cu);
    assert(kRegCursorControl == 0x03b38u);
    assert(kRegCursorSurfAddrLo == 0x03b39u);
    assert(kRegCursorSurfAddrHi == 0x03b3au);
    assert(kRegCursorSize == 0x03b3bu);
    assert(kRegCursorPosition == 0x03b3cu);
    assert(kRegCursorHotSpot == 0x03b3du);
    assert(kRegCursorDstOffset == 0x03b3fu);
    assert(kRegCursorMemPwrCtrl == 0x03b40u);
    assert(kRegCnvcCur0Control == 0x041b1u);

    assert(kCursorSlotBytes == 65536u);
    assert(kCursorSlotPages == 16u);
    assert(kCursorTotalPages == 32u);
    assert(kCursorTotalBytes == 131072u);
    assert(kCursorPageStart == 8160u);
    assert(phx::dcnzc::kReservedCursorPages == 32u);
    assert(phx::dcnzc::kMaxScanoutPages == 8160u);

    const uint64_t slot0Buf0 = cursorVaForSlot(0, 0);
    const uint64_t slot0Buf1 = cursorVaForSlot(0, 1);
    const uint64_t slot1Buf0 = cursorVaForSlot(1, 0);
    assert(slot0Buf0 == phx::dcnzc::slotVa(0) + 8160ull * 4096ull);
    assert(slot0Buf1 == slot0Buf0 + 65536ull);
    assert(cursorVaForSlot(0, 2) == slot0Buf0);
    assert(slot1Buf0 == phx::dcnzc::slotVa(1) + 8160ull * 4096ull);
    assert(slot0Buf1 + kCursorSlotBytes == phx::dcnzc::slotVa(0) + phx::dcnzc::kMaxPages * phx::dcnzc::kPageBytes);

    uint64_t bytes = 0;
    uint32_t pages = 0;
    assert(phx::dcnzc::validSurfaceRequest(0x42475241u, 2560, 1600, 10240, 2560, 1600, 10240, bytes, pages));
    assert(pages == 4000u && pages <= phx::dcnzc::kMaxScanoutPages);
    // A 32 MiB surface (8192 pages) must be rejected because top 32 pages are reserved for cursor.
    assert(!phx::dcnzc::validSurfaceRequest(0x42475241u, 4096, 2048, 16384, 4096, 2048, 16384, bytes, pages));
}

static void testPitchAndLinesPerChunk() {
    uint32_t pitch = 0, hwPitch = 99, lpc = 99;
    assert(!selectCursorPitch(0, pitch, hwPitch));
    assert(!selectCursorPitch(129, pitch, hwPitch));
    assert(selectCursorPitch(1, pitch, hwPitch) && pitch == 64u && hwPitch == kCursorPitch64);
    assert(selectCursorPitch(32, pitch, hwPitch) && pitch == 64u && hwPitch == kCursorPitch64);
    assert(selectCursorPitch(64, pitch, hwPitch) && pitch == 64u && hwPitch == kCursorPitch64);
    assert(selectCursorPitch(65, pitch, hwPitch) && pitch == 128u && hwPitch == kCursorPitch128);
    assert(selectCursorPitch(128, pitch, hwPitch) && pitch == 128u && hwPitch == kCursorPitch128);

    assert(!selectLinesPerChunk32bpp(0, lpc));
    assert(!selectLinesPerChunk32bpp(257, lpc));
    assert(selectLinesPerChunk32bpp(16, lpc) && lpc == kCursorLpc16);
    assert(selectLinesPerChunk32bpp(32, lpc) && lpc == kCursorLpc16);
    assert(selectLinesPerChunk32bpp(33, lpc) && lpc == kCursorLpc8);
    assert(selectLinesPerChunk32bpp(64, lpc) && lpc == kCursorLpc8);
    assert(selectLinesPerChunk32bpp(65, lpc) && lpc == kCursorLpc4);
    assert(selectLinesPerChunk32bpp(128, lpc) && lpc == kCursorLpc4);
}

static void testRegisterEncodings() {
    assert(encodeCursorSize(64, 64) == ((64u << 16) | 64u));
    assert(encodeCursorSize(32, 48) == ((32u << 16) | 48u));

    const uint32_t priorCtl = 0x80000000u | kCurCtlMagnify2x;
    const uint32_t enabledCtl = encodeCursorControl(
        priorCtl, true, kCursorModeColorUnPreMultAlpha, kCursorPitch64, kCursorLpc8);
    assert((enabledCtl & 0x80000000u) == 0x80000000u);
    assert((enabledCtl & kCurCtlEnable) == kCurCtlEnable);
    assert((enabledCtl & kCurCtlReqMode) == kCurCtlReqMode);
    assert((enabledCtl & kCurCtlMagnify2x) == 0u);
    assert(((enabledCtl & kCurCtlModeMask) >> kCurCtlModeShift) == kCursorModeColorUnPreMultAlpha);
    assert(((enabledCtl & kCurCtlPitchMask) >> kCurCtlPitchShift) == kCursorPitch64);
    assert(((enabledCtl & kCurCtlLinesPerChunkMask) >> kCurCtlLinesPerChunkShift) == kCursorLpc8);

    const uint32_t disabledCtl = encodeCursorControl(
        enabledCtl, false, kCursorModeColorUnPreMultAlpha, kCursorPitch128, kCursorLpc4);
    assert((disabledCtl & kCurCtlEnable) == 0u);
    assert(((disabledCtl & kCurCtlPitchMask) >> kCurCtlPitchShift) == kCursorPitch128);
    assert(((disabledCtl & kCurCtlLinesPerChunkMask) >> kCurCtlLinesPerChunkShift) == kCursorLpc4);

    const uint32_t priorCnvc = 0x0000ff00u | kCnvcCur0ExpansionMask | kCnvcCur0RomEnMask;
    const uint32_t enabledCnvc = encodeCnvcCursorControl(priorCnvc, true, kCursorModeColorUnPreMultAlpha);
    assert((enabledCnvc & 0x0000ff00u) == 0x0000ff00u);
    assert((enabledCnvc & kCnvcCur0Enable) == kCnvcCur0Enable);
    assert((enabledCnvc & kCnvcCur0ExpansionMask) == 0u);
    assert((enabledCnvc & kCnvcCur0RomEnMask) == 0u);
    assert(((enabledCnvc & kCnvcCur0ModeMask) >> kCnvcCur0ModeShift) == kCursorModeColorUnPreMultAlpha);

    const uint32_t disabledCnvc = encodeCnvcCursorControl(enabledCnvc, false, kCursorModeColorUnPreMultAlpha);
    assert((disabledCnvc & kCnvcCur0Enable) == 0u);
}

static void testCursorPositionAndOffscreen() {
    const PositionRegs normal = computeCursorPosition(320, 240, true, 64, 64, 2560, 1600, 100000, 500000);
    assert(normal.visible);
    assert(normal.positionReg == ((320u << 16) | 240u));
    assert(normal.hotSpotReg == 0u);
    assert(normal.dstOffsetReg == 64u);

    // Negative top-left shifts into hotspot while clamping position to 0.
    const PositionRegs neg = computeCursorPosition(-12, -5, true, 64, 64, 2560, 1600, 100000, 500000);
    assert(neg.visible);
    assert(neg.positionReg == 0u);
    assert(neg.hotSpotReg == ((12u << 16) | 5u));
    assert(neg.dstOffsetReg == 0u);

    // Partial offscreen at right/bottom edge stays visible.
    const PositionRegs edge = computeCursorPosition(2559, 1599, true, 64, 64, 2560, 1600, 0, 0);
    assert(edge.visible);
    assert(edge.positionReg == ((2559u << 16) | 1599u));
    assert(edge.hotSpotReg == 0u);
    assert(edge.dstOffsetReg == 0u);

    // Completely offscreen left/top/right/bottom or hidden -> not visible.
    assert(!computeCursorPosition(-64, 100, true, 64, 64, 2560, 1600).visible);
    assert(!computeCursorPosition(100, -64, true, 64, 64, 2560, 1600).visible);
    assert(!computeCursorPosition(2560, 100, true, 64, 64, 2560, 1600).visible);
    assert(!computeCursorPosition(100, 1600, true, 64, 64, 2560, 1600).visible);
    assert(!computeCursorPosition(100, 100, false, 64, 64, 2560, 1600).visible);
    assert(!computeCursorPosition(100, 100, true, 0, 64, 2560, 1600).visible);

    // dst_x_offset clamps at 0x1fff.
    const PositionRegs clamped = computeCursorPosition(2500, 10, true, 32, 32, 2560, 1600, 1000000, 1000);
    assert(clamped.visible && clamped.dstOffsetReg == 0x1fffu);
}

static void testRepackCursorImage32() {
    const uint32_t width = 36u, height = 20u, pitch = 64u;
    std::vector<uint32_t> src(width * height);
    for (uint32_t row = 0; row < height; ++row)
        for (uint32_t col = 0; col < width; ++col)
            src[row * width + col] = 0xff000000u | (row << 8) | col;

    std::vector<uint32_t> dst(kCursorSlotBytes / sizeof(uint32_t), 0xdeadbeefu);
    assert(repackCursorImage32(src.data(), width, height, dst.data(), pitch, static_cast<uint32_t>(dst.size())));
    for (uint32_t row = 0; row < height; ++row) {
        for (uint32_t col = 0; col < width; ++col)
            assert(dst[row * pitch + col] == src[row * width + col]);
        for (uint32_t col = width; col < pitch; ++col)
            assert(dst[row * pitch + col] == 0u);
    }

    assert(!repackCursorImage32(nullptr, width, height, dst.data(), pitch, static_cast<uint32_t>(dst.size())));
    assert(!repackCursorImage32(src.data(), 0, height, dst.data(), pitch, static_cast<uint32_t>(dst.size())));
    assert(!repackCursorImage32(src.data(), 65, height, dst.data(), 64, static_cast<uint32_t>(dst.size())));
    assert(!repackCursorImage32(src.data(), width, height, dst.data(), 96, static_cast<uint32_t>(dst.size())));
    assert(!repackCursorImage32(src.data(), width, height, dst.data(), pitch, pitch * height - 1u));
}

int main() {
    testRegisterOffsetsAndLayout();
    testPitchAndLinesPerChunk();
    testRegisterEncodings();
    testCursorPositionAndOffscreen();
    testRepackCursorImage32();
    return 0;
}
