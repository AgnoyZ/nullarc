// Validated, immutable-after-start panel EDID cache. No MMIO, AUX or mode programming.
// PolyForm Noncommercial 1.0.0; see LICENSES/PolyForm-Noncommercial-1.0.0.txt.
// Required Notice: Copyright (c) 2026 NullMoth Systems (https://nullmothsystems.com)
#pragma once
#include <stddef.h>
#include <stdint.h>

namespace phx {
static constexpr size_t kEdidBlockBytes = 128;
static constexpr size_t kEdidMaxBytes = 4096;

// A supplied EDID must describe the fixed boot raster in a base-block DTD.
// This conservative source-binding check is not independent monitor identification.
inline bool edidDescribesRaster(const uint8_t *p, size_t size, uint32_t width, uint32_t height) {
    if (!p || size < kEdidBlockBytes || !width || !height) return false;
    for (size_t off = 54; off <= 108; off += 18) {
        const uint8_t *d = p + off;
        if (!d[0] && !d[1]) continue;
        const uint32_t w = d[2] | ((uint32_t)(d[4] & 0xf0) << 4);
        const uint32_t h = d[5] | ((uint32_t)(d[7] & 0xf0) << 4);
        if (w == width && h == height && !(d[17] & 0x80)) return true;
    }
    return false;
}

inline bool edidValid(const uint8_t *p, size_t size) {
    if (!p || size < kEdidBlockBytes || size > kEdidMaxBytes || size % kEdidBlockBytes) return false;
    static constexpr uint8_t header[8] = {0, 255, 255, 255, 255, 255, 255, 0};
    for (size_t i = 0; i < sizeof header; ++i) if (p[i] != header[i]) return false;
    if (p[18] != 1 || p[19] > 4 || size / kEdidBlockBytes != (size_t)p[126] + 1) return false;
    for (size_t off = 0; off < size; off += kEdidBlockBytes) {
        uint8_t sum = 0;
        for (size_t i = 0; i < kEdidBlockBytes; ++i) sum = (uint8_t)(sum + p[off + i]);
        if (sum) return false;
    }
    return true;
}

class EdidCache {
    uint8_t bytes_[kEdidMaxBytes] = {};
    size_t size_ = 0;
public:
    void clear() { size_ = 0; }
    bool adopt(const uint8_t *p, size_t size, uint32_t width, uint32_t height) {
        clear();
        if (!edidValid(p, size) || !edidDescribesRaster(p, size, width, height)) return false;
        for (size_t i = 0; i < size; ++i) bytes_[i] = p[i];
        size_ = size;   // publish readiness only after the full bounded snapshot
        return true;
    }
    bool ready() const { return size_ >= kEdidBlockBytes; }
    size_t size() const { return size_; }
    const uint8_t *data() const { return bytes_; }
    bool copyBlock(uint32_t oneBasedBlock, uint8_t *out, size_t capacity) const {
        // Divide before calculating the offset: UINT32_MAX must never wrap into block zero.
        if (!out || !ready() || !oneBasedBlock || oneBasedBlock > size_ / kEdidBlockBytes || capacity < kEdidBlockBytes)
            return false;
        const size_t off = ((size_t)oneBasedBlock - 1) * kEdidBlockBytes;
        for (size_t i = 0; i < kEdidBlockBytes; ++i) out[i] = bytes_[off + i];
        return true;
    }
};
} // namespace phx
