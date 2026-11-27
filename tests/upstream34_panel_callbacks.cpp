// CPU doubles for actual refresh measurement and timing callback; no real MMIO.
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <initializer_list>
#include <vector>
#include "accel/phx_panel_timing.h"
#include "accel/phx_dcn_zerocopy.h"
using IOReturn = int;
using IODisplayModeID = uint32_t;
using IOFixed1616 = uint32_t;
using IOSelect = uint32_t;
constexpr int kIOReturnSuccess = 0, kIOReturnBadArgument = -2, kIOReturnUnsupportedMode = -3, kIOReturnUnsupported = -4;
constexpr uint32_t kDisplayModeValidFlag = 1, kDisplayModeSafeFlag = 2, kDisplayModeDefaultFlag = 4;
constexpr uint32_t kFramebufferSupportsGammaCorrection = 0x00040000, kDisplayModeAcceleratorBackedFlag = 0x00400000,
    kDisplayModeValidForHiResFlag = 0x00800000;
constexpr uint32_t kIOFBRedGammaScaleAttribute = 'gslr', kIOFBGreenGammaScaleAttribute = 'gslg',
    kIOFBBlueGammaScaleAttribute = 'gslb', kIOWindowServerActiveAttribute = 'wsrv', kIOPowerAttribute = 'powr';
constexpr uint32_t kIOHardwareCursorAttribute = 'crsr';
constexpr uint32_t kIOFBNotifyDidPowerOn = 1, kIOFBNotifyWillPowerOff = 2;
struct IODisplayModeInformation {
    uint32_t nominalWidth, nominalHeight, refreshRate, maxDepthIndex, flags;
    uint16_t imageWidth, imageHeight;
    uint32_t reserved[3];
};
// The native SDK build separately verifies actual Apple structures and constants.
constexpr uint32_t kIOTimingIDInvalid = 0xffffffffu, kIODetailedTimingValid = 1;
constexpr uint32_t kIODigitalSignal = 1, kIOSyncPositivePolarity = 1;
constexpr unsigned kIOPCIConfigBaseAddress5 = 0x24;
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
#define PFBLOG(...) ((void)0)
#define OSSafeReleaseNULL(object) do { if (object) (object)->release(); (object) = nullptr; } while (0)
#define OSDynamicCast(type, object) dynamic_cast<type *>(object)
struct OSObject {
    virtual ~OSObject() = default;
    unsigned copies = 0, releases = 0;
    void release() { assert(releases < copies); ++releases; }
};
struct OSData : OSObject {
    OSData(std::initializer_list<uint8_t> value) : bytes(value) {}
    std::vector<uint8_t> bytes;
    unsigned getLength() const { return bytes.size(); }
    const void *getBytesNoCopy() const { assert(!bytes.empty()); return bytes.data(); }
};
static constexpr auto gIODTPlane = "IODeviceTree";
struct IORegistryEntry : OSObject {
    static IORegistryEntry *options;
    OSObject *property = nullptr;
    static IORegistryEntry *fromPath(const char *path, const char *plane) {
        assert(std::strcmp(path, "/options") == 0 && plane == gIODTPlane);
        if (options) ++options->copies;
        return options;
    }
    OSObject *copyProperty(const char *key) {
        assert(std::strcmp(key, "phxfb-hidpi") == 0);
        if (property) ++property->copies;
        return property;
    }
};
IORegistryEntry *IORegistryEntry::options = nullptr;
static int bootArg = -1;
static bool PE_parse_boot_argn(const char *name, void *out, int length) {
    assert(std::strcmp(name, "phxfbhires") == 0 && length == sizeof(uint32_t));
    if (bootArg < 0) return false;
    *static_cast<uint32_t *>(out) = bootArg;
    return true;
}
// ACTUAL_HIRES_REQUEST
struct IOMemoryMap {
    std::vector<uint32_t> regs = std::vector<uint32_t>(0x5100);
    uint64_t length = 0x5100 * 4;
    unsigned releases = 0;
    uint64_t getLength() { return length; }
    uintptr_t getVirtualAddress() { return reinterpret_cast<uintptr_t>(regs.data()); }
    void release() { ++releases; }
};
struct MockPCI {
    IOMemoryMap *mapping = nullptr;
    IOMemoryMap *mapDeviceMemoryWithRegister(unsigned value) { assert(value == kIOPCIConfigBaseAddress5); return mapping; }
};
static constexpr unsigned counter = 0x34c0 + 0x1b4c;
static IOMemoryMap *activeMap;
static uint64_t clockNow;
static uint32_t rateMilliHz, fixedFrameAdvance;
static int counterPhase;
static uint64_t extraSleepNs;
static unsigned sleeps, sleptMilliseconds;
static bool changeMode, zeroElapsed;
static uint64_t mach_absolute_time() { return clockNow; }
static void absolutetime_to_nanoseconds(uint64_t value, uint64_t *out) { *out = value; }
static void IOSleep(unsigned milliseconds) {
    assert(milliseconds == 200 || milliseconds == 2000); ++sleeps;
    sleptMilliseconds += milliseconds;
    const uint64_t elapsed = uint64_t(milliseconds) * 1000000 + extraSleepNs;
    if (!zeroElapsed) clockNow += elapsed;
    const uint32_t frames = fixedFrameAdvance != UINT32_MAX ? fixedFrameAdvance
        : uint32_t(int64_t(elapsed * rateMilliHz / 1000000000000ULL) + counterPhase);
    activeMap->regs[counter] = (activeMap->regs[counter] + frames) & 0xffffff;
    if (changeMode) ++activeMap->regs[0x34c0 + 0x1b2a];
}
struct IOFramebuffer {
    static IOReturn setAttribute(IOSelect, uintptr_t) { return kIOReturnUnsupported; }
    static IOReturn getAttribute(IOSelect, uintptr_t *) { return kIOReturnUnsupported; }
};
struct Fixture {
    IOMemoryMap memory; MockPCI pci; MockPCI *fPCI = &pci;
    IOMemoryMap *fMmio = nullptr;
    bool fCurBufReady = false, fCurTripped = false;
    uint32_t fWidth = 2560, fHeight = 1600, fRefreshMilliHz = 60000, fHTotal = 0, fVTotal = 0;
    uint64_t fFrameNs = 16666667;
    phx::PanelTiming fPanelTiming = {};
    bool fPanelTimingValid = false;
    uint16_t fPanelWidthMm = 0, fPanelHeightMm = 0;
    uintptr_t fGammaScale[3] = { 0x10000, 0x10000, 0x10000 };
    bool fHiRes = false;
    const uint8_t *edidBytes = nullptr;
    size_t edidLength = 0;
    void trace(const char *, uint32_t, uint64_t) {}
    void displayPower(bool) {}
    void handleEvent(uint32_t) {}
    void refreshPanelSizeFromEdid() {
        if (fPanelWidthMm && fPanelHeightMm) return;
        uint16_t widthMm = 0, heightMm = 0;
        if (phx::decodeEdidPanelSizeMm(edidBytes, edidLength, fWidth, fHeight, widthMm, heightMm)) {
            fPanelWidthMm = widthMm;
            fPanelHeightMm = heightMm;
        }
    }
    Fixture() {
        // Reviewed upstream fixture; these are not new target observations.
        const unsigned offsets[] = {0x1b2a,0x1b2b,0x1b2c,0x1b2d,0x1b2f,0x1b36,0x1b37,0x1b38,0x1b41,0x1b44,0x1b33};
        const uint32_t values[] = {0xa9f,0x00700a70,0x00200000,1,0x69d,0x005b069b,0x00060000,1,0x11201,0,0};
        for (unsigned i = 0; i < 11; ++i) memory.regs[0x34c0 + offsets[i]] = values[i];
        pci.mapping = &memory; activeMap = &memory; clockNow = 1000000;
        rateMilliHz = 120000; fixedFrameAdvance = UINT32_MAX; counterPhase = 0;
        extraSleepNs = 0; sleeps = sleptMilliseconds = 0; changeMode = zeroElapsed = false;
    }
    // ACTUAL_REFRESH_METHOD
    // ACTUAL_TIMING_METHOD
    // ACTUAL_MODE_INFO_METHOD
    // ACTUAL_SET_ATTR_METHOD
    // ACTUAL_GET_ATTR_METHOD
};
static unsigned checks = 0;
static void check(bool value) { assert(value); ++checks; }
static void fallback(Fixture &f) {
    IOTimingInformation info; std::memset(&info, 0xa5, sizeof info);
    check(!f.fPanelTimingValid);
    check(f.getTimingInfoForDisplayMode(1, &info) == kIOReturnSuccess);
    IOTimingInformation expected{}; expected.appleTimingID = kIOTimingIDInvalid;
    check(std::memcmp(&info, &expected, sizeof info) == 0);
}
static void testHiResRequest() {
    check(!hiResRequested());
    IORegistryEntry options;
    IORegistryEntry::options = &options;
    check(!hiResRequested());
    OSObject wrongType;
    OSData empty{}, off{'0'}, binary{1}, trailingNul{'1', 0}, longer{'1', '1'}, enabled{'1'};
    OSObject *properties[] = {&wrongType, &empty, &off, &binary, &trailingNul, &longer, &enabled};
    for (OSObject *property : properties) {
        options.property = property;
        check(hiResRequested() == (property == &enabled));
        check(property->copies == 1 && property->releases == 1);
    }
    bootArg = 0;
    check(hiResRequested());
    options.property = nullptr;
    check(!hiResRequested());
    bootArg = 2;
    check(!hiResRequested());
    bootArg = 1;
    check(hiResRequested());
    check(options.copies == 11 && options.releases == 11);
    IORegistryEntry::options = nullptr;
    bootArg = -1;
}
static void buildSyntheticEdid(uint8_t out[128], uint8_t widthCm, uint8_t heightCm,
                               uint32_t dtdActiveW, uint32_t dtdActiveH,
                               uint16_t dtdMmW, uint16_t dtdMmH) {
    std::memset(out, 0, 128);
    static constexpr uint8_t kHeader[8] = {0x00, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0x00};
    std::memcpy(out, kHeader, 8);
    out[18] = 1; out[19] = 4;
    out[21] = widthCm; out[22] = heightCm;
    if (dtdActiveW && dtdActiveH) {
        uint8_t *dtd = out + 54;
        dtd[0] = 0x01; dtd[1] = 0x20;
        dtd[2] = static_cast<uint8_t>(dtdActiveW & 0xffu);
        dtd[4] = static_cast<uint8_t>(((dtdActiveW >> 8) & 0x0fu) << 4);
        dtd[5] = static_cast<uint8_t>(dtdActiveH & 0xffu);
        dtd[7] = static_cast<uint8_t>(((dtdActiveH >> 8) & 0x0fu) << 4);
        dtd[12] = static_cast<uint8_t>(dtdMmW & 0xffu);
        dtd[13] = static_cast<uint8_t>(dtdMmH & 0xffu);
        dtd[14] = static_cast<uint8_t>((((dtdMmW >> 8) & 0x0fu) << 4) | ((dtdMmH >> 8) & 0x0fu));
    }
    uint8_t sum = 0;
    for (size_t index = 0; index < 127; ++index) sum = static_cast<uint8_t>(sum + out[index]);
    out[127] = static_cast<uint8_t>(0 - sum);
}
static void testEdidPanelSizeDecode() {
    uint8_t edid[128];
    buildSyntheticEdid(edid, 34, 22, 2560, 1600, 344, 215);
    uint16_t widthMm = 99, heightMm = 99;
    check(phx::decodeEdidPanelSizeMm(edid, sizeof edid, 2560, 1600, widthMm, heightMm));
    check(widthMm == 344 && heightMm == 215);

    // Bad checksum must be rejected and leave outputs zeroed.
    edid[127] ^= 1;
    check(!phx::decodeEdidPanelSizeMm(edid, sizeof edid, 2560, 1600, widthMm, heightMm));
    check(widthMm == 0 && heightMm == 0);
    edid[127] ^= 1;

    // Short buffer or bad header must be rejected.
    check(!phx::decodeEdidPanelSizeMm(edid, 127, 2560, 1600, widthMm, heightMm));
    edid[0] = 0x55;
    check(!phx::decodeEdidPanelSizeMm(edid, sizeof edid, 2560, 1600, widthMm, heightMm));
    edid[0] = 0x00;

    // When DTDs carry no millimetre size, fall back to EDID bytes 21/22 (cm * 10).
    uint8_t cmOnly[128];
    buildSyntheticEdid(cmOnly, 34, 22, 0, 0, 0, 0);
    check(phx::decodeEdidPanelSizeMm(cmOnly, sizeof cmOnly, 2560, 1600, widthMm, heightMm));
    check(widthMm == 340 && heightMm == 220);

    // Aspect-ratio encoding (one of bytes 21/22 is zero) must not produce a bogus size.
    buildSyntheticEdid(cmOnly, 34, 0, 0, 0, 0, 0);
    check(!phx::decodeEdidPanelSizeMm(cmOnly, sizeof cmOnly, 2560, 1600, widthMm, heightMm));
    check(widthMm == 0 && heightMm == 0);
}
int main() {
    testHiResRequest();
    testEdidPanelSizeDecode();
    // Replay the logged 25-frame / 200,965-us input with a one-frame endpoint
    // phase. At 2 s the corresponding synthetic input is 241 / 2,000,965 us.
    // The assumed 120-Hz clock here is a CPU model, not a panel-rate finding.
    Fixture replay; extraSleepNs = 965000; counterPhase = 1; replay.measureRefresh();
    std::fprintf(stderr, "short-window regression replay: %u mHz\n", replay.fRefreshMilliHz);
    check(replay.fRefreshMilliHz == 120000 && replay.fPanelTimingValid);

    Fixture good; auto expectedRegisters = good.memory.regs;
    expectedRegisters[counter] = 240;
    good.measureRefresh();
    check(good.fPanelTimingValid && good.fRefreshMilliHz == 120000 && good.fFrameNs == 8333333);
    constexpr uint32_t baseFlags = kDisplayModeValidFlag | kDisplayModeSafeFlag
        | kDisplayModeDefaultFlag | kFramebufferSupportsGammaCorrection
        | kDisplayModeAcceleratorBackedFlag;
    uint8_t sampleEdid[128];
    buildSyntheticEdid(sampleEdid, 34, 22, 2560, 1600, 344, 215);
    // Without an EDID, physical dimensions stay zero until an EDID becomes available.
    {
        IODisplayModeInformation mode;
        std::memset(&mode, 0xa5, sizeof mode);
        check(good.getInformationForDisplayMode(1, &mode) == kIOReturnSuccess);
        check(mode.imageWidth == 0 && mode.imageHeight == 0 && mode.flags == baseFlags);
    }
    good.edidBytes = sampleEdid;
    good.edidLength = sizeof sampleEdid;
    for (bool hiRes : {false, true}) {
        good.fHiRes = hiRes;
        IODisplayModeInformation mode;
        std::memset(&mode, 0xa5, sizeof mode);
        check(good.getInformationForDisplayMode(1, &mode) == kIOReturnSuccess);
        IODisplayModeInformation expected{};
        expected.nominalWidth = 2560;
        expected.nominalHeight = 1600;
        expected.imageWidth = 344;
        expected.imageHeight = 215;
        expected.refreshRate = 120u << 16;
        expected.flags = baseFlags | (hiRes ? kDisplayModeValidForHiResFlag : 0);
        check(std::memcmp(&mode, &expected, sizeof mode) == 0);
        check(good.getInformationForDisplayMode(2, &mode) == kIOReturnBadArgument);
        check(good.getInformationForDisplayMode(1, nullptr) == kIOReturnBadArgument);
        check(std::memcmp(&mode, &expected, sizeof mode) == 0);
    }
    check(good.fHTotal == 2720 && good.fVTotal == 1694 && sleeps == 1 && sleptMilliseconds == 2000 && good.memory.releases == 1);
    check(good.memory.regs == expectedRegisters); // Only the CPU fake's frame counter update is permitted.
    IOTimingInformation info; std::memset(&info, 0xa5, sizeof info);
    check(good.getTimingInfoForDisplayMode(1, &info) == kIOReturnSuccess);
    check(info.appleTimingID == kIOTimingIDInvalid && info.flags == kIODetailedTimingValid);
    const auto &t = info.detailedInfo.v2;
    check(t.pixelClock == 552921600 && !t.minPixelClock && !t.maxPixelClock);
    check(t.horizontalActive == 2560 && t.horizontalBlanking == 160 && t.horizontalSyncOffset == 48 && t.horizontalSyncPulseWidth == 32);
    check(t.verticalActive == 1600 && t.verticalBlanking == 94 && t.verticalSyncOffset == 3 && t.verticalSyncPulseWidth == 6);
    check(t.signalConfig == kIODigitalSignal && !t.horizontalSyncConfig && !t.verticalSyncConfig);
    for (auto value : info.reserved) check(value == 0);
    auto before = info;
    check(good.getTimingInfoForDisplayMode(0, &info) == kIOReturnUnsupportedMode);
    check(std::memcmp(&info, &before, sizeof info) == 0);
    check(good.getTimingInfoForDisplayMode(2, &info) == kIOReturnUnsupportedMode);
    check(good.getTimingInfoForDisplayMode(1, nullptr) == kIOReturnUnsupportedMode);
    good.fPanelTiming.hPositive = good.fPanelTiming.vPositive = true;
    check(good.getTimingInfoForDisplayMode(1, &info) == kIOReturnSuccess);
    check(info.detailedInfo.v2.horizontalSyncConfig == kIOSyncPositivePolarity && info.detailedInfo.v2.verticalSyncConfig == kIOSyncPositivePolarity);
    good.fPanelTimingValid = false; fallback(good);

    Fixture wrap; wrap.memory.regs[counter] = 0xfffff8; wrap.measureRefresh();
    check(wrap.fPanelTimingValid && wrap.fRefreshMilliHz == 120000);
    Fixture missing; missing.fPCI = nullptr; missing.measureRefresh(); fallback(missing); check(sleeps == 0);
    Fixture noMap; noMap.pci.mapping = nullptr; noMap.measureRefresh(); fallback(noMap); check(sleeps == 0);
    Fixture shortMap; shortMap.memory.length -= 4; shortMap.measureRefresh(); fallback(shortMap);
    check(shortMap.memory.releases == 1 && sleeps == 0);
    Fixture changing; changeMode = true; changing.measureRefresh(); fallback(changing);
    Fixture inactive; inactive.memory.regs[0x34c0 + 0x1b41] = 0; inactive.measureRefresh(); fallback(inactive);
    Fixture interlaced; interlaced.memory.regs[0x34c0 + 0x1b44] = 1; interlaced.measureRefresh(); fallback(interlaced);
    Fixture variable; variable.memory.regs[0x34c0 + 0x1b33] = 1; variable.measureRefresh(); fallback(variable);
    Fixture wrongArea; wrongArea.fWidth = 1920; wrongArea.measureRefresh(); fallback(wrongArea);
    Fixture slow; fixedFrameAdvance = 3; slow.measureRefresh(); fallback(slow);
    Fixture highRate; rateMilliHz = 500000; highRate.measureRefresh(); fallback(highRate);
    Fixture noTime; zeroElapsed = true; noTime.measureRefresh(); fallback(noTime);

    const uint32_t standardRates[] = {48000,50000,60000,75000,90000,100000,120000,144000,165000,240000};
    for (uint32_t rate : standardRates) {
        for (int phase : {-1, 0, 1}) {
            for (uint64_t extra : {0ULL, 965000ULL, 1000000000ULL}) {
                Fixture f; rateMilliHz = rate; counterPhase = phase; extraSleepNs = extra;
                f.memory.regs[counter] = 0xfffff8;
                auto expected = f.memory.regs;
                const uint64_t elapsed = 2000000000ULL + extra;
                const uint32_t advance = uint32_t(int64_t(elapsed * rate / 1000000000000ULL) + phase);
                expected[counter] = (expected[counter] + advance) & 0xffffff;
                f.measureRefresh();
                check(f.fPanelTimingValid && f.fRefreshMilliHz == rate);
                check(f.fFrameNs == 1000000000000ULL / rate);
                check(f.fPanelTiming.pixelClock == (2720ULL * 1694 * rate + 500) / 1000);
                check(sleeps == 1 && sleptMilliseconds == 2000 && f.memory.releases == 1);
                check(f.memory.regs == expected);
            }
        }
    }
    Fixture nonstandard; rateMilliHz = 130000; nonstandard.measureRefresh();
    check(nonstandard.fPanelTimingValid && nonstandard.fRefreshMilliHz == 130000);

    // Verify RGB gamma scale defaults to 1.0 (16.16) and echoes written values.
    {
        Fixture gamma;
        uintptr_t val = 0;
        const IOSelect attrs[3] = { kIOFBRedGammaScaleAttribute, kIOFBGreenGammaScaleAttribute, kIOFBBlueGammaScaleAttribute };
        const uintptr_t custom[3] = { 0x0f000, 0x0d800, 0x0b000 };
        for (unsigned ch = 0; ch < 3; ++ch) {
            check(gamma.getAttribute(attrs[ch], &val) == kIOReturnSuccess && val == 0x10000);
            check(gamma.setAttribute(attrs[ch], custom[ch]) == kIOReturnSuccess);
            check(gamma.getAttribute(attrs[ch], &val) == kIOReturnSuccess && val == custom[ch]);
        }
        check(gamma.getAttribute(kIOWindowServerActiveAttribute, &val) == kIOReturnSuccess && val == 1);
        check(gamma.getAttribute(kIOHardwareCursorAttribute, &val) == kIOReturnSuccess && val == 0);
        IOMemoryMap fullMmio;
        fullMmio.length = phx::dcnzc::kMinMmioBytes;
        gamma.fMmio = &fullMmio;
        gamma.fCurBufReady = true;
        check(gamma.getAttribute(kIOHardwareCursorAttribute, &val) == kIOReturnSuccess && val == 1);
        gamma.fCurTripped = true;
        check(gamma.getAttribute(kIOHardwareCursorAttribute, &val) == kIOReturnSuccess && val == 0);
        gamma.fCurTripped = false;
        fullMmio.length = phx::dcnzc::kMinMmioBytes - 4;
        check(gamma.getAttribute(kIOHardwareCursorAttribute, &val) == kIOReturnSuccess && val == 0);
        check(gamma.getAttribute('unkn', &val) == kIOReturnUnsupported);
    }
    std::printf("actual refresh/timing/mode callbacks: %u CPU assertions passed\n", checks);
}
