// Native 2x HiDPI policy for PhxAMDFB. No resampling or display-engine writes.
// This component retains src/phxaccel's PolyForm Noncommercial 1.0.0 license.
#pragma once
#include <stdint.h>

namespace phx780m {
// A 2x desktop must have integral logical dimensions and fit the existing
// 32-bit GOP surface. Keep the firmware geometry; never invent a larger buffer.
constexpr bool nativeHiDPIEligible(uint32_t width, uint32_t height, uint32_t rowBytes) {
    return width >= 640 && height >= 400 && width <= 16384 && height <= 16384
        && !(width & 1) && !(height & 1) && !(rowBytes & 3)
        && (uint64_t)rowBytes >= (uint64_t)width * 4;
}
}
