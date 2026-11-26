#include "../src/phxaccel/accel/phx_dcn_zerocopy.h"

#include <cassert>
#include <cstdint>
#include <unordered_map>

using namespace phx::dcnzc;

static void testPhysicalEntries() {
    uint64_t encoded = 0;
    assert(validPhysPage(0x12345000ull));
    assert(!validPhysPage(0));
    assert(!validPhysPage(kAddressLimit));
    assert(encodeRootEntry(0x12345000ull, encoded));
    assert(encoded == (0x12345000ull | kPteRootFlags));
    assert(encodeLeafPte(0x12345000ull, encoded));
    assert(encoded == (0x12345000ull | kPteLeafFlags));
    assert(!encodeLeafPte(0x12345001ull, encoded));
}

static void testApertures() {
    const ApertureSnapshot aperture{0x100, 0x1ff, 0, 0};
    assert(addressInFbAperture(0x100000000ull, kPageBytes, aperture));
    assert(!addressInFbAperture(0x0ffffff000ull, kPageBytes, aperture));
    assert(slotVaClearOfApertures(kSlotVaBase, kMaxPages * kPageBytes, aperture));
    assert(!slotVaClearOfApertures(0, kPageBytes, aperture));
    assert(!slotVaClearOfApertures(kSlotVaBase, kPageBytes, {0x100, 0x1ff, 0x10000, 0x10001}));
    assert(rangesOverlap(4, 8, 8, 12));
    assert(!rangesOverlap(4, 7, 8, 12));
}

static void testSurfaceGeometry() {
    uint64_t bytes = 0;
    uint32_t pages = 0;
    assert(validSurfaceRequest(kPixelFormatBgra, 1280, 800, 5120, 1280, 800, 5120, bytes, pages));
    assert(bytes == 4096000ull);
    assert(pages == 1000);
    assert(!validSurfaceRequest(kPixelFormatBgra, 1280, 800, 5116, 1280, 800, 5120, bytes, pages));
    assert(validSurfaceRequest(kPixelFormatL10r, 1280, 800, 5120, 1280, 800, 5120, bytes, pages));
    assert(!validSurfaceRequest(0x52474241u, 1280, 800, 5120, 1280, 800, 5120, bytes, pages));
    uint32_t dcnFmt = 0;
    assert(dcnPixelFormatFor(kPixelFormatBgra, dcnFmt) && dcnFmt == kDcnFormatArgb8888);
    assert(dcnPixelFormatFor(kPixelFormatL10r, dcnFmt) && dcnFmt == kDcnFormatArgb2101010);
    assert(!dcnPixelFormatFor(0x52474241u, dcnFmt));
    assert(mmhubInvalidateReq(1) == (kMmhubInvLegacyL2L1Mask | (1u << 1)));
    assert(mmhubInvalidateReq(4) == (kMmhubInvLegacyL2L1Mask | (1u << 4)));
    assert(!validSurfaceRequest(kPixelFormatBgra, 0x4000, 1, 0, 0x4000, 1, 0, bytes, pages));
    assert(!validSurfaceRequest(kPixelFormatBgra, 1280, 800, 4, 1280, 800, 4, bytes, pages));
}

static void testContextOwnershipChecks() {
    const uint32_t expected[kContextFieldCount] = {0, 0, 0x45007, 0, 0x10000, 0, 0x10010};
    uint32_t current[kContextFieldCount] = {0, 0, 0x45007, 0, 0x10000, 0, 0x10010};
    assert(contextMatchesOwnedState(expected, current));
    current[2] = 0;
    assert(contextMatchesOwnedState(expected, current));
    current[4] = 0x20000;
    assert(!contextMatchesOwnedState(expected, current));
    assert(!contextFieldsClear(expected));
    const uint32_t empty[kContextFieldCount] = {};
    assert(contextFieldsClear(empty));
    assert(contextMatchesExactState(expected, expected));
    assert(!contextMatchesExactState(expected, empty));
    assert(slotUnconsumed(0, 0));
    assert(!slotUnconsumed(0, 1));
    assert(!slotUnconsumed(kSlotCount, 0));
}

static void testHubpGeometry() {
    std::unordered_map<uint32_t, uint32_t> registers = {
        {kRegHubpCntl, 0},
        {kRegOtgControl, kOtgEnabledMask},
        {kRegOdmSelect, 0},
        {kRegOtgGlobalCtl2, 0},
        {kRegHubpSurfaceConfig, kDcnFormatArgb8888},
        {kRegHubpReturnCtl, kArgbRedBlue},
        {kRegHubpSurfaceCtl, 0},
        {kRegHubpTilingConfig, 0},
        {kRegHubpViewportStart, 0},
        {kRegHubpViewportDim, (1600u << 16) | 2560u},
        {kRegHubpPitch, 2559u},
        {kRegHubpFlipCtl, 0},
        {kRegHubpFlipCtl2, 0},
    };
    const auto read = [&registers](uint32_t reg) {
        const auto found = registers.find(reg);
        return found == registers.end() ? 0u : found->second;
    };
    assert(hubpGeometryReady(2560, 1600, 10240, read));
    registers[kRegHubpSurfaceConfig] = kDcnFormatArgb2101010;
    assert(hubpGeometryReady(2560, 1600, 10240, read));
    registers[kRegHubpSurfaceConfig] = 1u;
    assert(!hubpGeometryReady(2560, 1600, 10240, read));
    registers[kRegHubpSurfaceConfig] = kDcnFormatArgb8888;
    assert(!hubpGeometryReady(2560, 1600, 10240, read, true));
    registers[kRegHubpFlipCtl] = kFlipUpdateLocked;
    assert(!hubpGeometryReady(2560, 1600, 10240, read));
    assert(hubpGeometryReady(2560, 1600, 10240, read, true));
    registers[kRegHubpFlipCtl] = kFlipPending;
    assert(!hubpGeometryReady(2560, 1600, 10240, read));
    assert(hubpGeometryReady(2560, 1600, 10240, read, false, true));
    registers[kRegHubpFlipCtl] = kFlipPending | kFlipImmediate;
    assert(!hubpGeometryReady(2560, 1600, 10240, read, false, true));
    registers[kRegHubpFlipCtl] = kFlipImmediate;
    assert(!hubpGeometryReady(2560, 1600, 10240, read));
    registers[kRegHubpFlipCtl] = 0;
    registers[kRegHubpViewportDim] = (1600u << 16) | 1280u;
    assert(!hubpGeometryReady(2560, 1600, 10240, read));
}

static void testHubpPeerRoute() {
    std::unordered_map<uint32_t, uint32_t> registers;
    const uint32_t idleMask = kHubpBlank | kHubpNoOutstanding | (1u << 12);
    for (uint32_t index = 0; index < 3; ++index) {
        const uint32_t pipe = index + 1;
        registers[kRegHubpCntl + pipe * kHubpStride] = idleMask;
        registers[kRegHubpFlipCtl + pipe * kHubpStride] = 0;
        registers[kRegHubpPeerPower1 + index * kHubpPeerPowerStride] = 0;
    }
    const auto read = [&registers](uint32_t reg) {
        const auto found = registers.find(reg);
        return found == registers.end() ? 0u : found->second;
    };
    assert(hubpPeersIdle(read));
    registers[kRegOtgControl + kOtgStride] = kOtgEnabledMask;
    assert(!hubpPeersIdle(read));
    registers[kRegOtgControl + kOtgStride] = 0;
    registers[kRegHubpFlipCtl + 2 * kHubpStride] = kFlipPending;
    assert(!hubpPeersIdle(read));
    registers[kRegHubpFlipCtl + 2 * kHubpStride] = 0;
    registers[kRegHubpPeerPower1 + kHubpPeerPowerStride] = kHubpPeerPowerGated;
    assert(hubpPeersIdle(read));
}

int main() {
    testPhysicalEntries();
    testApertures();
    testSurfaceGeometry();
    testContextOwnershipChecks();
    testHubpGeometry();
    testHubpPeerRoute();
    return 0;
}
