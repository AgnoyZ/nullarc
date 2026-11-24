#pragma once

#include "build34_dcn_flip_readback.h"

namespace build34::dcn {

namespace hubp0 {
inline constexpr uint32_t kSurfaceConfig = 0x03aa5, kTilingConfig = 0x03aa7;
inline constexpr uint32_t kViewportStart = 0x03aa9, kViewportDimensions = 0x03aaa;
inline constexpr uint32_t kSurfacePitch = 0x03ac7, kSurfaceControl = 0x03ada;
inline constexpr uint32_t kReturnControl = 0x03b2c;
inline constexpr uint32_t kOdmSelect = 0x04f8b, kOtgControl = 0x05001;
inline constexpr uint32_t kFormatMask = 0x7f, kUnsupportedOrientation = 0xf00, kSwizzleMask = 0x1f;
inline constexpr uint32_t kRedBlueMask = 0x00f00000, kArgbRedBlue = 0x00e00000;
inline constexpr uint32_t kStrideMask = 0x3fff, kExtentMask = 0x3fff3fff;
inline constexpr uint32_t kUnsafeSurface = 0x000f1313;
inline constexpr uint32_t kOtgEnabled = 0x00010001, kOdmSinglePipeMask = 0x000f0303;
}

inline bool validFlipGeometry(const ScanoutSurface &surface) {
    using namespace hubp0;
    if (!surface.width || surface.width > kStrideMask || !surface.height || surface.height > kStrideMask ||
        surface.dcnPixelFormat != kDcnArgb8888 || surface.pitchPixelsMinusOne > kStrideMask ||
        surface.pitchPixelsMinusOne + 1 < surface.width)
        return false;
    const uint64_t footprint = (uint64_t{surface.pitchPixelsMinusOne} + 1) * 4 * surface.height;
    return footprint <= kMaxBackingBytes && surface.mappedBytes == ((footprint + kPageBytes - 1) & ~(kPageBytes - 1));
}

inline bool sameFlipGeometry(const ScanoutSurface &first, const ScanoutSurface &second) {
    return first.width == second.width && first.height == second.height &&
        first.pitchPixelsMinusOne == second.pitchPixelsMinusOne && first.dcnPixelFormat == second.dcnPixelFormat &&
        first.mappedBytes == second.mappedBytes;
}

template<typename Read>
bool matchHubpFlipGeometry(const ScanoutSurface &surface, const Read &read) {
    using namespace hubp0;
    if (!validFlipGeometry(surface)) return false;
    uint32_t config = 0, tiling = 0, start = 0, dimensions = 0, pitch = 0;
    uint32_t control = 0, formatControl = 0, returnControl = 0, odm = 0, otg = 0;
    return read(kControl, control) && !(control & kUnsupportedControl) &&
        read(kOtgControl, otg) && (otg & kOtgEnabled) == kOtgEnabled &&
        read(kOdmSelect, odm) && !(odm & kOdmSinglePipeMask) &&
        read(kSurfaceConfig, config) && (config & (kFormatMask | kUnsupportedOrientation)) == surface.dcnPixelFormat &&
        read(kReturnControl, returnControl) && (returnControl & kRedBlueMask) == kArgbRedBlue &&
        read(kSurfaceControl, formatControl) && !(formatControl & kUnsafeSurface) &&
        read(kTilingConfig, tiling) && !(tiling & kSwizzleMask) &&
        read(kViewportStart, start) && !(start & kExtentMask) &&
        read(kViewportDimensions, dimensions) && (dimensions & kExtentMask) == ((surface.height << 16) | surface.width) &&
        read(kSurfacePitch, pitch) && (pitch & kStrideMask) == surface.pitchPixelsMinusOne;
}

}
