// Fake IOKit exercises the actual driver's callback, including its flag values.
#include "PhxHiDPI.hpp"
#include "accel/phx_panel_timing.h"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <initializer_list>
using IOReturn = int;
using IODisplayModeID = uint32_t;
using IOFixed1616 = uint32_t;
using UInt32 = uint32_t;
using IOOptionBits = uint32_t;
struct IOColorEntry { uint16_t index, red, green, blue; };
constexpr int kIOReturnSuccess = 0, kIOReturnBadArgument = -1;
constexpr int kIOReturnUnsupported = -2;
constexpr int kIOReturnUnsupportedMode = -3;
// Test doubles exercise the callback logic; native SDK compilation checks the actual ABI.
constexpr uint32_t kIOTimingIDInvalid = 0xffffffffu, kIODetailedTimingValid = 1;
constexpr uint32_t kIODigitalSignal = 1, kIOSyncPositivePolarity = 1;
struct TimingV2 {
    uint64_t pixelClock, minPixelClock, maxPixelClock;
    uint32_t horizontalActive, horizontalBlanking, horizontalSyncOffset, horizontalSyncPulseWidth;
    uint32_t verticalActive, verticalBlanking, verticalSyncOffset, verticalSyncPulseWidth;
    uint32_t signalConfig, horizontalSyncConfig, verticalSyncConfig;
};
struct IOTimingInformation {
    uint32_t appleTimingID, flags;
    struct { TimingV2 v2; } detailedInfo;
    uint32_t reserved[4];
};
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
    phx::PanelTiming fPanelTiming = {};
    bool fPanelTimingValid = false;
    // ACTUAL_FRAMEBUFFER_METHOD
    // ACTUAL_FRAMEBUFFER_COLOR_METHODS
    // ACTUAL_FRAMEBUFFER_TIMING_METHOD
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
    IOTimingInformation timing; std::memset(&timing, 0xA5, sizeof timing);
    const auto timingBefore = timing;
    assert(fb.getTimingInfoForDisplayMode(0, &timing) == kIOReturnUnsupportedMode);
    assert(!std::memcmp(&timing, &timingBefore, sizeof timing));
    assert(fb.getTimingInfoForDisplayMode(2, &timing) == kIOReturnUnsupportedMode);
    assert(!std::memcmp(&timing, &timingBefore, sizeof timing));
    assert(fb.getTimingInfoForDisplayMode(1, nullptr) == kIOReturnUnsupportedMode);
    assert(fb.getTimingInfoForDisplayMode(1, &timing) == kIOReturnSuccess);
    IOTimingInformation fallback; std::memset(&fallback, 0, sizeof fallback);
    fallback.appleTimingID = kIOTimingIDInvalid;
    assert(!std::memcmp(&timing, &fallback, sizeof timing));
    fb.fPanelTiming = {2560, 1600, 2720, 1694, 48, 32, 3, 6, false, false, 552921600};
    fb.fPanelTimingValid = true;
    for (bool hires : {false, true}) {
        fb.fHiDPI = hires; std::memset(&timing, 0xA5, sizeof timing);
        assert(fb.getTimingInfoForDisplayMode(1, &timing) == kIOReturnSuccess);
        assert(timing.appleTimingID == kIOTimingIDInvalid && timing.flags == kIODetailedTimingValid);
        const auto &t = timing.detailedInfo.v2;
        assert(t.pixelClock == 552921600 && t.minPixelClock == 0 && t.maxPixelClock == 0);
        assert(t.horizontalActive == 2560 && t.horizontalBlanking == 160);
        assert(t.horizontalSyncOffset == 48 && t.horizontalSyncPulseWidth == 32);
        assert(t.verticalActive == 1600 && t.verticalBlanking == 94);
        assert(t.verticalSyncOffset == 3 && t.verticalSyncPulseWidth == 6);
        assert(t.signalConfig == kIODigitalSignal && !t.horizontalSyncConfig && !t.verticalSyncConfig);
        for (auto value : timing.reserved) assert(value == 0);
    }
    fb.fPanelTiming.hPositive = fb.fPanelTiming.vPositive = true;
    assert(fb.getTimingInfoForDisplayMode(1, &timing) == kIOReturnSuccess);
    assert(timing.detailedInfo.v2.horizontalSyncConfig == kIOSyncPositivePolarity);
    assert(timing.detailedInfo.v2.verticalSyncConfig == kIOSyncPositivePolarity);
    fb.fPanelTimingValid = false;
    assert(fb.getTimingInfoForDisplayMode(1, &timing) == kIOReturnSuccess);
    assert(!std::memcmp(&timing, &fallback, sizeof timing));
    unsigned char table[128]; std::memset(table, 0xA5, sizeof table);
    unsigned char saved[128]; std::memcpy(saved, table, sizeof saved);
    IOColorEntry entries[2] = {{0, 1, 2, 3}, {1, 4, 5, 6}};
    const auto first = entries[0], second = entries[1];
    for (const auto count : {0u, 1u, 256u, UINT32_MAX}) {
        assert(fb.setGammaTable(3, count, 16, table) == kIOReturnUnsupported);
        assert(fb.setGammaTable(3, count, 16, table, false) == kIOReturnUnsupported);
        assert(fb.setGammaTable(3, count, 16, table, true) == kIOReturnUnsupported);
        assert(fb.setCLUTWithEntries(entries, 0, count, 0) == kIOReturnUnsupported);
    }
    assert(fb.setGammaTable(0, 0, 0, nullptr) == kIOReturnUnsupported);
    assert(fb.setGammaTable(0, 0, 0, nullptr, true) == kIOReturnUnsupported);
    assert(fb.setCLUTWithEntries(nullptr, 0, 0, 0) == kIOReturnUnsupported);
    assert(!std::memcmp(table, saved, sizeof table));
    assert(!std::memcmp(&entries[0], &first, sizeof first) && !std::memcmp(&entries[1], &second, sizeof second));
    std::puts("PASS: native HiDPI policy and actual framebuffer mode/timing/color callbacks; no GPU execution");
}
