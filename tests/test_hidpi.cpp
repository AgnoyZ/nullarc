// Fake IOKit exercises the actual driver's callback, including its flag values.
#include "PhxHiDPI.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
using IOReturn = int;
using IODisplayModeID = uint32_t;
using IOFixed1616 = uint32_t;
constexpr int kIOReturnSuccess = 0, kIOReturnBadArgument = -1;
constexpr uint32_t kDisplayModeValidFlag = 1, kDisplayModeSafeFlag = 2, kDisplayModeDefaultFlag = 4;
constexpr uint32_t kDisplayModeValidForHiResFlag = 0x00800000, kDisplayModeNativeFlag = 0x02000000;
struct IODisplayModeInformation {
    uint32_t nominalWidth, nominalHeight, refreshRate, maxDepthIndex, flags;
    uint16_t imageWidth, imageHeight;
    uint32_t reserved[3];
};
#define bzero(p, bytes) std::memset(p, 0, bytes)
struct Framebuffer {
    uint32_t fWidth = 2560, fHeight = 1600, fRefreshMilliHz = 120000;
    bool fHiDPI = false;
    // ACTUAL_FRAMEBUFFER_METHOD
};

int main() {
    using phx780m::nativeHiDPIEligible;
    static_assert(nativeHiDPIEligible(2560, 1600, 10240), "native 16:10");
    static_assert(nativeHiDPIEligible(2880, 1800, 11776), "padded pitch");
    static_assert(!nativeHiDPIEligible(UINT32_MAX, 1600, UINT32_MAX), "overflow");
    static_assert(!nativeHiDPIEligible(2560, UINT32_MAX, 10240), "height bound");
    for (uint32_t w = 638; w <= 644; w++)
        for (uint32_t h = 398; h <= 404; h++)
            for (uint32_t row = w * 4 - 4; row <= w * 4 + 4; row++)
                assert(nativeHiDPIEligible(w, h, row) ==
                       (w >= 640 && h >= 400 && !(w % 2) && !(h % 2) && row >= w * 4 && !(row % 4)));
    assert(nativeHiDPIEligible(16384, 16384, 65536));
    assert(!nativeHiDPIEligible(16386, 1600, 65544));
    assert(!nativeHiDPIEligible(2560, 16386, 10240));
    assert(!nativeHiDPIEligible(0, 0, 0));
    Framebuffer fb;
    IODisplayModeInformation low{}, high{}, unchanged;
    assert(fb.getInformationForDisplayMode(1, &low) == kIOReturnSuccess);
    assert(low.flags == 7 && low.nominalWidth == 2560 && low.nominalHeight == 1600);
    assert(low.refreshRate == 120u << 16 && low.maxDepthIndex == 0);
    fb.fHiDPI = true;
    assert(fb.getInformationForDisplayMode(1, &high) == kIOReturnSuccess);
    assert(high.flags == (7u | 0x00800000u | 0x02000000u));
    high.flags = low.flags;
    assert(!std::memcmp(&low, &high, sizeof low));  // only flags change, never geometry or refresh
    std::memset(&unchanged, 0xA5, sizeof unchanged);
    const auto before = unchanged;
    assert(fb.getInformationForDisplayMode(0, &unchanged) == kIOReturnBadArgument);
    assert(!std::memcmp(&before, &unchanged, sizeof before));
    assert(fb.getInformationForDisplayMode(2, &unchanged) == kIOReturnBadArgument);
    assert(fb.getInformationForDisplayMode(1, nullptr) == kIOReturnBadArgument);
    fb.fRefreshMilliHz = 59940;
    assert(fb.getInformationForDisplayMode(1, &high) == kIOReturnSuccess);
    assert(high.refreshRate == (59940ull << 16) / 1000);
    std::puts("PASS: native HiDPI policy and actual framebuffer callback; no GPU execution");
}
