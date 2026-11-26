// Read-only DCN 3.1.4 panel timing description. No display programming.
#pragma once
#include <stddef.h>
#include <stdint.h>

namespace phx {
struct OtgTimingRegisters {
    uint32_t hTotal, hBlank, hSync, hPolarity;
    uint32_t vTotal, vBlank, vSync, vPolarity;
    uint32_t control, interlace, vTotalControl;
};

struct PanelTiming {
    uint32_t width, height, hTotal, vTotal;
    uint32_t hSyncOffset, hSyncWidth, vSyncOffset, vSyncWidth;
    bool hPositive, vPositive;
    uint64_t pixelClock; // Estimated from the existing measured/snapped refresh.
};

// Offsets and masks: AMD's dcn_3_1_4_offset.h / dcn_3_1_4_sh_mask.h.
// The caller must supply a BAR5 mapping covering at least 0x5100 dwords.
inline OtgTimingRegisters readOtgTiming(const volatile uint32_t *mmio) {
    constexpr uint32_t base = 0x34c0;
    return {mmio[base + 0x1b2a], mmio[base + 0x1b2b],
            mmio[base + 0x1b2c], mmio[base + 0x1b2d],
            mmio[base + 0x1b2f], mmio[base + 0x1b36],
            mmio[base + 0x1b37], mmio[base + 0x1b38],
            mmio[base + 0x1b41], mmio[base + 0x1b44],
            mmio[base + 0x1b33]};
}

inline bool sameTiming(const OtgTimingRegisters &a, const OtgTimingRegisters &b) {
    return a.hTotal == b.hTotal && a.hBlank == b.hBlank
        && a.hSync == b.hSync && a.hPolarity == b.hPolarity
        && a.vTotal == b.vTotal && a.vBlank == b.vBlank
        && a.vSync == b.vSync && a.vPolarity == b.vPolarity
        && a.control == b.control && a.interlace == b.interlace
        && a.vTotalControl == b.vTotalControl;
}

inline bool decodeAxis(uint32_t active, uint32_t rawTotal, uint32_t rawBlank,
                       uint32_t rawSync, uint32_t &total, uint32_t &offset, uint32_t &pulse) {
    if ((rawTotal & ~0x7fffu) || (rawBlank & 0x80008000u) || (rawSync & 0x80008000u)) return false;
    total = (rawTotal & 0x7fff) + 1;
    const uint32_t blankStart = rawBlank & 0x7fff, blankEnd = (rawBlank >> 16) & 0x7fff;
    const uint32_t syncStart = rawSync & 0x7fff, syncEnd = (rawSync >> 16) & 0x7fff;
    // Require the firmware's active scanout to match the boot console, with no inferred borders/scaling.
    if (!active || active > 16384 || total <= active || blankStart >= total
        || blankEnd >= blankStart || blankStart - blankEnd != active
        || syncStart >= total || syncEnd >= total) return false;
    offset = (total - blankStart + syncStart) % total;
    pulse = (total - syncStart + syncEnd) % total;
    const uint32_t blank = total - active;
    return pulse && offset <= blank && pulse <= blank - offset;
}

inline bool decodePanelTiming(const OtgTimingRegisters &before, const OtgTimingRegisters &after,
                              uint32_t width, uint32_t height, uint32_t refreshMilliHz,
                              PanelTiming &out) {
    out = {};
    // Fixed-rate progressive, separate sync only. Unknown/variable modes retain the old fallback.
    if (!sameTiming(before, after) || !(after.control & 1) || (after.interlace & 1)
        || (after.vTotalControl & 0x3f) || (after.hPolarity & 0x30000)
        || (after.vPolarity & 0x100) || refreshMilliHz < 24000 || refreshMilliHz > 360000) return false;
    PanelTiming t = {};
    if (!decodeAxis(width, after.hTotal, after.hBlank, after.hSync,
                    t.hTotal, t.hSyncOffset, t.hSyncWidth)
        || !decodeAxis(height, after.vTotal, after.vBlank, after.vSync,
                       t.vTotal, t.vSyncOffset, t.vSyncWidth)) return false;
    t.width = width; t.height = height;
    // DCN encodes negative sync as one, positive as zero.
    t.hPositive = !(after.hPolarity & 1); t.vPositive = !(after.vPolarity & 1);
    // 15-bit hardware totals and the refresh bound above keep this product within uint64_t.
    t.pixelClock = ((uint64_t)t.hTotal * t.vTotal * refreshMilliHz + 500) / 1000;
    out = t;
    return true;
}

// Parse physical active image dimensions (millimetres) from an EDID 1.x base block.
// Prefers DTD byte 12..14 millimetre precision (matching the active raster when available)
// and falls back to EDID bytes 21..22 (centimetres * 10) when both are non-zero.
inline bool decodeEdidPanelSizeMm(const uint8_t *edid, size_t len,
                                  uint32_t activeWidth, uint32_t activeHeight,
                                  uint16_t &widthMm, uint16_t &heightMm) {
    widthMm = 0;
    heightMm = 0;
    if (!edid || len < 128) return false;
    static constexpr uint8_t kHeader[8] = {0x00, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0x00};
    for (size_t index = 0; index < 8; ++index)
        if (edid[index] != kHeader[index]) return false;
    uint8_t sum = 0;
    for (size_t index = 0; index < 128; ++index) sum = static_cast<uint8_t>(sum + edid[index]);
    if (sum != 0) return false;

    uint16_t firstDtdW = 0, firstDtdH = 0;
    for (size_t slot = 0; slot < 4; ++slot) {
        const uint8_t *dtd = edid + 54 + slot * 18;
        const uint16_t pixelClock = static_cast<uint16_t>(dtd[0] | (static_cast<uint16_t>(dtd[1]) << 8));
        if (!pixelClock) continue;
        const uint32_t dtdActiveW = static_cast<uint32_t>(dtd[2]) | (static_cast<uint32_t>(dtd[4] & 0xf0u) << 4);
        const uint32_t dtdActiveH = static_cast<uint32_t>(dtd[5]) | (static_cast<uint32_t>(dtd[7] & 0xf0u) << 4);
        const uint16_t dtdMmW = static_cast<uint16_t>(dtd[12] | (static_cast<uint16_t>(dtd[14] & 0xf0u) << 4));
        const uint16_t dtdMmH = static_cast<uint16_t>(dtd[13] | (static_cast<uint16_t>(dtd[14] & 0x0fu) << 8));
        if (!dtdMmW || !dtdMmH) continue;
        if (!firstDtdW) {
            firstDtdW = dtdMmW;
            firstDtdH = dtdMmH;
        }
        if (activeWidth && activeHeight && dtdActiveW == activeWidth && dtdActiveH == activeHeight) {
            widthMm = dtdMmW;
            heightMm = dtdMmH;
            return true;
        }
    }
    if (firstDtdW && firstDtdH) {
        widthMm = firstDtdW;
        heightMm = firstDtdH;
        return true;
    }
    if (edid[21] && edid[22]) {
        widthMm = static_cast<uint16_t>(edid[21]) * 10u;
        heightMm = static_cast<uint16_t>(edid[22]) * 10u;
        return true;
    }
    return false;
}
} // namespace phx
